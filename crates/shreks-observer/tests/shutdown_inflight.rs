use std::{sync::Mutex, time::Duration};

use async_trait::async_trait;
use shreks_core::{DiscoveredToken, ProviderId};
use shreks_observer::Observer;
use shreks_providers::{DiscoveryProvider, ProviderError};
use shreks_storage::ShreksDb;
use tokio::sync::oneshot;

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

#[tokio::test(flavor = "current_thread")]
async fn shutdown_preempts_an_in_flight_provider_cycle() {
    let root = std::env::temp_dir().join(format!(
        "shreks-observer-shutdown-inflight-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&root);
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let (started_tx, started_rx) = oneshot::channel();
    let discovery = std::sync::Arc::new(BlockingDiscovery {
        started: Mutex::new(Some(started_tx)),
    });
    let mut observer = Observer::new(db).with_discovery_provider(discovery);

    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    let run = observer.run_until_shutdown(Duration::from_secs(3_600), async move {
        let _ = shutdown_rx.await;
    });
    let signal = async move {
        started_rx.await.expect("provider cycle should start");
        let _ = shutdown_tx.send(());
    };

    let joined = async {
        let (run_result, _) = tokio::join!(run, signal);
        run_result
    };
    let cycles = tokio::time::timeout(Duration::from_millis(100), joined)
        .await
        .expect("shutdown must preempt an in-flight provider call")
        .unwrap();

    assert_eq!(cycles, 0, "interrupted provider work is not a completed cycle");

    drop(observer);
    let _ = std::fs::remove_dir_all(root);
}
