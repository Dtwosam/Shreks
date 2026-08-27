use std::{sync::Mutex, time::Duration};

use async_trait::async_trait;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId};
use shreks_providers::{DiscoveryProvider, MarketDataProvider, ProviderError};
use shreks_storage::ShreksDb;
use tokio::sync::oneshot;

#[path = "../src/bin/observer_v2/sampling.rs"]
mod sampling;
#[path = "../src/bin/observer_v2/sampler.rs"]
mod sampler;

use sampler::{HighResolutionSampler, SamplerProvider};
use sampling::SamplingPolicy;

struct BlockingDiscovery {
    started: Mutex<Option<oneshot::Sender<()>>>,
}

#[async_trait]
impl DiscoveryProvider for BlockingDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        let started = self.started.lock().unwrap().take();
        if let Some(started) = started {
            let _ = started.send(());
        }
        std::future::pending().await
    }
}

struct EmptyMarket;

#[async_trait]
impl MarketDataProvider for EmptyMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, _token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        Ok(Vec::new())
    }
}

#[tokio::test(flavor = "current_thread")]
async fn shutdown_preempts_an_in_flight_sampler_cycle_and_flushes_registry() {
    let root = std::env::temp_dir().join(format!(
        "shreks-sampler-shutdown-inflight-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&root);
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let (started_tx, started_rx) = oneshot::channel();
    let discovery = std::sync::Arc::new(BlockingDiscovery {
        started: Mutex::new(Some(started_tx)),
    });
    let market = std::sync::Arc::new(EmptyMarket);
    let mut sampler = HighResolutionSampler::new(
        db,
        Some(discovery),
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    let run = sampler.run_until_shutdown(async move {
        let _ = shutdown_rx.await;
    });
    let signal = async move {
        started_rx.await.expect("sampler discovery cycle should start");
        let _ = shutdown_tx.send(());
    };

    let joined = async {
        let (run_result, _) = tokio::join!(run, signal);
        run_result
    };
    let cycles = tokio::time::timeout(Duration::from_secs(2), joined)
        .await
        .expect("shutdown must preempt an in-flight sampler provider call")
        .unwrap();

    assert_eq!(cycles, 0, "interrupted sampler work is not a completed cycle");
    assert!(
        ShreksDb::open(&db_path)
            .unwrap()
            .ingestion_checkpoint(ProviderId::DexScreener, "observer_v2_registry_v1")
            .unwrap()
            .is_some(),
        "shutdown must flush the sampler registry after cancelling in-flight work"
    );

    drop(sampler);
    let _ = std::fs::remove_dir_all(root);
}
