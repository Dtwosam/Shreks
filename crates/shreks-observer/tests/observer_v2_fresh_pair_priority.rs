use std::{
    collections::VecDeque,
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, TransactionWindow, VenueId};
use shreks_providers::{DiscoveryProvider, MarketDataProvider, ProviderError};
use shreks_storage::ShreksDb;

#[path = "../src/bin/observer_v2/sampling.rs"]
mod sampling;
#[path = "../src/bin/observer_v2/sampler.rs"]
mod sampler;

use sampler::{HighResolutionSampler, SamplerProvider};
use sampling::SamplingPolicy;

const SECOND: i64 = 1_000;
const MINUTE: i64 = 60 * SECOND;
const HOUR: i64 = 60 * MINUTE;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-observer-v2-fresh-pair-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn discovered(mint: &str, at: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: None,
        venue: None,
        discovered_at_unix_ms: at,
        source: ProviderId::DexScreener,
    }
}

fn snapshot(
    mint: &str,
    pair_address: &str,
    observed_at_unix_ms: i64,
    pair_created_at_unix_ms: i64,
) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pump_swap".to_owned(),
        pair_address: pair_address.to_owned(),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some("1.0".to_owned()),
        liquidity_usd: Some(50_000.0),
        volume_5m: Some(10_000.0),
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 20,
            sells: 10,
        }],
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: Some(pair_created_at_unix_ms),
        observed_at_unix_ms,
    }
}

#[derive(Clone)]
struct StaticDiscovery {
    candidates: Vec<DiscoveredToken>,
}

#[async_trait]
impl DiscoveryProvider for StaticDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        Ok(self.candidates.clone())
    }
}

#[derive(Clone)]
struct SequenceMarket {
    responses: Arc<Mutex<VecDeque<Result<Vec<PairMarketData>, ProviderError>>>>,
    calls: Arc<Mutex<Vec<String>>>,
}

impl SequenceMarket {
    fn new(responses: Vec<Result<Vec<PairMarketData>, ProviderError>>) -> Self {
        Self {
            responses: Arc::new(Mutex::new(responses.into())),
            calls: Arc::new(Mutex::new(Vec::new())),
        }
    }

    fn call_count(&self) -> usize {
        self.calls.lock().unwrap().len()
    }
}

#[async_trait]
impl MarketDataProvider for SequenceMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls.lock().unwrap().push(mint.to_owned());
        self.responses
            .lock()
            .unwrap()
            .pop_front()
            .expect("test market response exhausted")
    }
}

#[tokio::test]
async fn old_candidate_with_fresh_pair_is_prioritized_before_broad_schedule_is_due() {
    let root = unique_test_dir("old-token-new-pair");
    let db_path = root.join("shreks.db");

    let now = 20 * HOUR;
    let pair_created_at = now - 5 * MINUTE;
    let stale_observed_at = now - 5 * MINUTE;

    let discovery = Arc::new(StaticDiscovery {
        candidates: vec![discovered("mint-fresh-pair", 0)],
    });
    let market = Arc::new(SequenceMarket::new(vec![
        Ok(vec![snapshot(
            "mint-fresh-pair",
            "pair-fresh",
            stale_observed_at,
            pair_created_at,
        )]),
        Ok(vec![snapshot(
            "mint-fresh-pair",
            "pair-fresh",
            now + SECOND,
            pair_created_at,
        )]),
    ]));

    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market.clone())],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let first = sampler.run_cycle_at(now).await.unwrap();
    assert_eq!(first.sampled_candidate_count, 1);
    assert_eq!(market.call_count(), 1);

    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.next_due_at_unix_ms, now + 5 * MINUTE);

    let second = sampler.run_cycle_at(now + SECOND).await.unwrap();

    assert_eq!(second.priority_candidate_count, 1);
    assert_eq!(second.priority_persisted_snapshot_count, 1);
    assert_eq!(second.sampled_candidate_count, 0);
    assert_eq!(market.call_count(), 2);

    drop(sampler);
    cleanup_dir(&root);
}
