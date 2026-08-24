use std::{
    collections::VecDeque,
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, TransactionWindow, VenueId,
};
use shreks_providers::{
    DiscoveryProvider, MarketDataProvider, ProviderError, ProviderErrorKind,
};
use shreks_storage::{OutcomeCheckpointStatus, ShreksDb};

#[path = "../src/bin/observer_v2/sampling.rs"]
mod sampling;
#[path = "../src/bin/observer_v2/sampler.rs"]
mod sampler;

use sampler::{HighResolutionSampler, SamplerProvider};
use sampling::SamplingPolicy;

const SECOND: i64 = 1_000;
const MINUTE: i64 = 60 * SECOND;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-observer-v2-{label}-{}-{nanos}",
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
    provider: ProviderId,
    mint: &str,
    pair_address: &str,
    at: i64,
    price: f64,
    liquidity: f64,
) -> PairMarketData {
    PairMarketData {
        provider,
        venue: if provider == ProviderId::Meteora {
            VenueId::MeteoraDlmm
        } else {
            VenueId::PumpSwap
        },
        chain_id: "solana".to_owned(),
        dex_id: provider.as_str().to_owned(),
        pair_address: pair_address.to_owned(),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some(price.to_string()),
        liquidity_usd: Some(liquidity),
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
        pair_created_at_unix_ms: Some(0),
        observed_at_unix_ms: at,
    }
}

#[derive(Clone)]
struct StaticDiscovery {
    candidates: Vec<DiscoveredToken>,
    calls: Arc<Mutex<usize>>,
}

impl StaticDiscovery {
    fn new(candidates: Vec<DiscoveredToken>) -> Self {
        Self {
            candidates,
            calls: Arc::new(Mutex::new(0)),
        }
    }
}

#[async_trait]
impl DiscoveryProvider for StaticDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        *self.calls.lock().unwrap() += 1;
        Ok(self.candidates.clone())
    }
}

#[derive(Clone)]
struct SequenceMarket {
    provider: ProviderId,
    responses: Arc<Mutex<VecDeque<Result<Vec<PairMarketData>, ProviderError>>>>,
    calls: Arc<Mutex<Vec<String>>>,
}

impl SequenceMarket {
    fn new(
        provider: ProviderId,
        responses: Vec<Result<Vec<PairMarketData>, ProviderError>>,
    ) -> Self {
        Self {
            provider,
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
        self.provider
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls.lock().unwrap().push(token_mint.to_owned());
        self.responses
            .lock()
            .unwrap()
            .pop_front()
            .expect("test market response exhausted")
    }
}

fn provider_error(provider: ProviderId) -> ProviderError {
    ProviderError::new(provider, ProviderErrorKind::RateLimited, "test rate limit")
}

fn scalar_i64(db_path: &Path, sql: &str) -> i64 {
    Connection::open(db_path)
        .unwrap()
        .query_row(sql, [], |row| row.get(0))
        .unwrap()
}

fn candidate_id(db_path: &Path, mint: &str) -> i64 {
    Connection::open(db_path)
        .unwrap()
        .query_row(
            "SELECT id FROM token_candidates WHERE mint = ?1 ORDER BY id LIMIT 1",
            [mint],
            |row| row.get(0),
        )
        .unwrap()
}

#[tokio::test]
async fn discovery_is_persisted_scheduled_and_sampled_before_first_checkpoint() {
    let root = unique_test_dir("early-resample");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-a", 0)]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-a",
                "pair-a",
                0,
                100.0,
                100_000.0,
            )]),
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-a",
                "pair-a",
                10 * SECOND,
                102.0,
                105_000.0,
            )]),
        ],
    ));

    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market.clone())],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let first = sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(first.discovered_candidate_count, 1);
    assert_eq!(first.sampled_candidate_count, 1);
    assert_eq!(first.persisted_snapshot_count, 1);
    assert_eq!(market.call_count(), 1);
    assert_eq!(scalar_i64(&db_path, "SELECT COUNT(*) FROM candidate_outcome_checkpoints"), 7);

    let second = sampler.run_cycle_at(10 * SECOND).await.unwrap();
    assert_eq!(second.sampled_candidate_count, 1);
    assert_eq!(market.call_count(), 2);
    assert_eq!(scalar_i64(&db_path, "SELECT COUNT(*) FROM market_snapshots"), 2);
    assert!(10 * SECOND < MINUTE);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn hot_price_path_shortens_next_sampling_interval() {
    let root = unique_test_dir("hot-cadence");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-hot", 0)]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-hot",
                "pair-hot",
                0,
                100.0,
                100_000.0,
            )]),
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-hot",
                "pair-hot",
                10 * SECOND,
                400.0,
                120_000.0,
            )]),
        ],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(sampler.registry().candidates()[0].next_due_at_unix_ms, 10 * SECOND);
    sampler.run_cycle_at(10 * SECOND).await.unwrap();
    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.high_price_usd, Some(400.0));
    assert_eq!(tracked.next_due_at_unix_ms, 15 * SECOND);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn all_provider_snapshots_are_persisted_and_representative_path_is_deterministic() {
    let root = unique_test_dir("multi-provider");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-multi", 0)]));
    let dex = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-multi",
            "pair-dex",
            0,
            100.0,
            50_000.0,
        )])],
    ));
    let meteora = Arc::new(SequenceMarket::new(
        ProviderId::Meteora,
        vec![Ok(vec![snapshot(
            ProviderId::Meteora,
            "mint-multi",
            "pair-meteora",
            0,
            105.0,
            200_000.0,
        )])],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![
            SamplerProvider::unpaced(dex),
            SamplerProvider::unpaced(meteora),
        ],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let report = sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(report.persisted_snapshot_count, 2);
    assert_eq!(scalar_i64(&db_path, "SELECT COUNT(*) FROM market_snapshots"), 2);
    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.first_price_usd, Some(105.0));
    assert_eq!(tracked.high_price_usd, Some(105.0));

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn one_provider_failure_does_not_backoff_when_another_provider_succeeds() {
    let root = unique_test_dir("partial-provider-success");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-partial", 0)]));
    let failing = Arc::new(SequenceMarket::new(
        ProviderId::Meteora,
        vec![Err(provider_error(ProviderId::Meteora))],
    ));
    let working = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-partial",
            "pair-working",
            0,
            100.0,
            100_000.0,
        )])],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![
            SamplerProvider::unpaced(failing),
            SamplerProvider::unpaced(working),
        ],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let report = sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(report.market_provider_failure_count, 1);
    assert_eq!(report.persisted_snapshot_count, 1);
    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.consecutive_failures, 0);
    assert_eq!(tracked.next_due_at_unix_ms, 10 * SECOND);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn all_provider_failure_backs_off_without_deleting_candidate() {
    let root = unique_test_dir("all-provider-failure");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-fail", 0)]));
    let failing = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Err(provider_error(ProviderId::DexScreener))],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(failing)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    sampler.run_cycle_at(0).await.unwrap();
    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.consecutive_failures, 1);
    assert_eq!(tracked.next_due_at_unix_ms, 20 * SECOND);
    assert_eq!(sampler.registry().len(), 1);
    assert_eq!(scalar_i64(&db_path, "SELECT COUNT(*) FROM token_candidates"), 1);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn dense_sample_finalizes_existing_a9_checkpoint() {
    let root = unique_test_dir("checkpoint-finalization");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-label", 0)]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-label",
                "pair-label",
                0,
                100.0,
                100_000.0,
            )]),
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-label",
                "pair-label",
                MINUTE,
                120.0,
                110_000.0,
            )]),
        ],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    sampler.run_cycle_at(0).await.unwrap();
    let report = sampler.run_cycle_at(MINUTE).await.unwrap();
    assert_eq!(report.completed_checkpoint_count, 1);

    let id = candidate_id(&db_path, "mint-label");
    let check = ShreksDb::open(&db_path).unwrap()
        .outcome_checkpoints(id)
        .unwrap()
        .into_iter()
        .find(|checkpoint| checkpoint.horizon_seconds == 60)
        .unwrap();
    assert_eq!(check.status, OutcomeCheckpointStatus::Completed);
    assert!((check.return_pct.unwrap() - 20.0).abs() < 1e-9);
    assert!((check.mfe_pct.unwrap() - 20.0).abs() < 1e-9);
    assert_eq!(check.mae_pct.unwrap(), 0.0);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn registry_restoration_resumes_tracking_after_database_reopen() {
    let root = unique_test_dir("restart");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-restart", 0)]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-restart",
            "pair-restart",
            0,
            100.0,
            100_000.0,
        )])],
    ));
    let mut first = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();
    first.run_cycle_at(0).await.unwrap();
    assert_eq!(first.registry().len(), 1);
    drop(first);

    let resumed_market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-restart",
            "pair-restart",
            10 * SECOND,
            110.0,
            100_000.0,
        )])],
    ));
    let mut resumed = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        None,
        vec![SamplerProvider::unpaced(resumed_market.clone())],
        SamplingPolicy::default_v1(),
    )
    .unwrap();
    resumed.restore_registry().unwrap();
    assert_eq!(resumed.registry().len(), 1);
    assert_eq!(resumed.registry().candidates()[0].first_price_usd, Some(100.0));
    resumed.run_cycle_at(10 * SECOND).await.unwrap();
    assert_eq!(resumed_market.call_count(), 1);
    assert_eq!(resumed.registry().candidates()[0].high_price_usd, Some(110.0));

    drop(resumed);
    cleanup_dir(&root);
}
