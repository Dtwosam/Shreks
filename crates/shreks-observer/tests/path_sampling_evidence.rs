use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, TransactionWindow, VenueId,
};
use shreks_observer::Observer;
use shreks_providers::{
    DiscoveryProvider, MarketDataProvider, ProviderError, ProviderErrorKind,
};
use shreks_storage::{OutcomeCheckpointStatus, PathSamplingStatus, ShreksDb};
use tokio::time::Instant;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-path-evidence-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn now_unix_ms() -> i64 {
    i64::try_from(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis(),
    )
    .unwrap()
}

fn candidate(mint: impl Into<String>, discovered_at_unix_ms: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.into(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms,
        source: ProviderId::DexScreener,
    }
}

fn seed_candidate(db: &ShreksDb, mint: &str, discovered_at_unix_ms: i64) -> i64 {
    let candidate = candidate(mint, discovered_at_unix_ms);
    let candidate_id = db.upsert_candidate(&candidate).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at_unix_ms)
        .unwrap();
    db.ensure_path_sampling(candidate_id, discovered_at_unix_ms)
        .unwrap();
    candidate_id
}

fn market_snapshot(
    provider: ProviderId,
    mint: &str,
    pair: &str,
    observed_at_unix_ms: i64,
    price_usd: f64,
) -> PairMarketData {
    let venue = match provider {
        ProviderId::DexScreener => VenueId::PumpSwap,
        ProviderId::Meteora => VenueId::MeteoraDlmm,
        _ => VenueId::OtherSolana,
    };
    PairMarketData {
        provider,
        venue,
        chain_id: "solana".to_owned(),
        dex_id: venue.as_str().to_owned(),
        pair_address: pair.to_owned(),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some(price_usd.to_string()),
        liquidity_usd: Some(10_000.0),
        volume_5m: Some(1_000.0),
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 10,
            sells: 4,
        }],
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: None,
        observed_at_unix_ms,
    }
}

#[derive(Debug, Clone, Copy)]
enum MarketMode {
    Empty,
    Valid { price_usd: f64 },
    InvalidMint,
    Failure,
    FixedDuplicate { observed_at_unix_ms: i64 },
}

#[derive(Clone)]
struct EvidenceMarket {
    provider: ProviderId,
    mode: MarketMode,
    calls: Arc<Mutex<Vec<(String, Instant)>>>,
}

impl EvidenceMarket {
    fn new(provider: ProviderId, mode: MarketMode) -> Self {
        Self {
            provider,
            mode,
            calls: Arc::new(Mutex::new(Vec::new())),
        }
    }

    fn instants(&self) -> Vec<Instant> {
        self.calls
            .lock()
            .unwrap()
            .iter()
            .map(|(_, instant)| *instant)
            .collect()
    }
}

#[async_trait]
impl MarketDataProvider for EvidenceMarket {
    fn provider_id(&self) -> ProviderId {
        self.provider
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls
            .lock()
            .unwrap()
            .push((token_mint.to_owned(), Instant::now()));
        match self.mode {
            MarketMode::Empty => Ok(Vec::new()),
            MarketMode::Valid { price_usd } => Ok(vec![market_snapshot(
                self.provider,
                token_mint,
                &format!("{token_mint}-{}", self.provider.as_str()),
                now_unix_ms(),
                price_usd,
            )]),
            MarketMode::InvalidMint => Ok(vec![market_snapshot(
                self.provider,
                "wrong-mint",
                "wrong-pair",
                now_unix_ms(),
                1.0,
            )]),
            MarketMode::Failure => Err(ProviderError::new(
                self.provider,
                ProviderErrorKind::Unavailable,
                "fixture market outage",
            )),
            MarketMode::FixedDuplicate {
                observed_at_unix_ms,
            } => Ok(vec![market_snapshot(
                self.provider,
                token_mint,
                "duplicate-pair",
                observed_at_unix_ms,
                1.0,
            )]),
        }
    }
}

#[derive(Clone)]
struct StaticDiscovery {
    item: DiscoveredToken,
}

#[async_trait]
impl DiscoveryProvider for StaticDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        Ok(vec![self.item.clone()])
    }
}

#[tokio::test(flavor = "current_thread")]
async fn valid_adaptive_evidence_advances_schedule_exactly_once() {
    let root = unique_test_dir("valid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = seed_candidate(&db, "mint-valid", now_unix_ms() - 40_000);
    let original_due = db
        .path_sampling(candidate_id)
        .unwrap()
        .unwrap()
        .next_due_at_unix_ms;

    let market = Arc::new(EvidenceMarket::new(
        ProviderId::Jupiter,
        MarketMode::Valid { price_usd: 1.2 },
    ));
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let reopened = ShreksDb::open(&db_path).unwrap();
    let schedule = reopened.path_sampling(candidate_id).unwrap().unwrap();
    assert_eq!(schedule.sample_count, 1);
    assert_eq!(schedule.status, PathSamplingStatus::Active);
    assert!(schedule.last_sample_at_unix_ms.is_some());
    assert!(schedule.next_due_at_unix_ms > original_due);

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn empty_market_response_leaves_adaptive_schedule_due_for_retry() {
    let root = unique_test_dir("empty");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = seed_candidate(&db, "mint-empty", now_unix_ms() - 40_000);
    let before = db.path_sampling(candidate_id).unwrap().unwrap();

    let market = Arc::new(EvidenceMarket::new(ProviderId::Jupiter, MarketMode::Empty));
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let reopened = ShreksDb::open(&db_path).unwrap();
    let after = reopened.path_sampling(candidate_id).unwrap().unwrap();
    assert_eq!(after.sample_count, 0);
    assert_eq!(after.next_due_at_unix_ms, before.next_due_at_unix_ms);
    assert_eq!(after.last_sample_at_unix_ms, None);

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn provider_failure_leaves_adaptive_schedule_due_for_retry() {
    let root = unique_test_dir("failure");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = seed_candidate(&db, "mint-failure", now_unix_ms() - 40_000);

    let market = Arc::new(EvidenceMarket::new(ProviderId::Jupiter, MarketMode::Failure));
    let mut observer = Observer::new(db).with_market_provider(market);
    let report = observer.run_cycle().await.unwrap();
    assert_eq!(report.provider_failures, 1);
    drop(observer);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        reopened.path_sampling(candidate_id).unwrap().unwrap().sample_count,
        0
    );

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn invalid_market_snapshot_does_not_advance_adaptive_schedule() {
    let root = unique_test_dir("invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = seed_candidate(&db, "mint-invalid", now_unix_ms() - 40_000);

    let market = Arc::new(EvidenceMarket::new(
        ProviderId::Jupiter,
        MarketMode::InvalidMint,
    ));
    let mut observer = Observer::new(db).with_market_provider(market);
    let report = observer.run_cycle().await.unwrap();
    assert_eq!(report.provider_failures, 1);
    drop(observer);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        reopened.path_sampling(candidate_id).unwrap().unwrap().sample_count,
        0
    );

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn duplicate_snapshot_that_sqlite_ignores_is_not_new_adaptive_evidence() {
    let root = unique_test_dir("duplicate");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let now = now_unix_ms();
    let candidate_id = seed_candidate(&db, "mint-duplicate", now - 40_000);
    let duplicate_time = now - 5_000;
    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot(
            ProviderId::Jupiter,
            "mint-duplicate",
            "duplicate-pair",
            duplicate_time,
            1.0,
        ),
    )
    .unwrap();

    let market = Arc::new(EvidenceMarket::new(
        ProviderId::Jupiter,
        MarketMode::FixedDuplicate {
            observed_at_unix_ms: duplicate_time,
        },
    ));
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        reopened.path_sampling(candidate_id).unwrap().unwrap().sample_count,
        0
    );

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn one_provider_failure_and_one_valid_provider_advance_schedule_once() {
    let root = unique_test_dir("mixed-providers");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = seed_candidate(&db, "mint-mixed", now_unix_ms() - 40_000);

    let failed = Arc::new(EvidenceMarket::new(ProviderId::Jupiter, MarketMode::Failure));
    let valid = Arc::new(EvidenceMarket::new(
        ProviderId::Meteora,
        MarketMode::Valid { price_usd: 1.5 },
    ));
    let mut observer = Observer::new(db)
        .with_market_provider(failed)
        .with_market_provider(valid);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        reopened.path_sampling(candidate_id).unwrap().unwrap().sample_count,
        1
    );

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn adaptive_revisits_reuse_existing_dexscreener_market_pacing() {
    let root = unique_test_dir("pacing");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let now = now_unix_ms();
    seed_candidate(&db, "mint-a", now - 40_000);
    seed_candidate(&db, "mint-b", now - 40_000);

    let market = Arc::new(EvidenceMarket::new(
        ProviderId::DexScreener,
        MarketMode::Valid { price_usd: 1.0 },
    ));
    let mut observer = Observer::new(db).with_market_provider(market.clone());
    observer.run_cycle().await.unwrap();

    let instants = market.instants();
    assert_eq!(instants.len(), 2);
    assert!(instants[1].duration_since(instants[0]).as_millis() >= 250);

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn checkpoint_and_path_due_share_one_market_pass_and_both_progress() {
    let root = unique_test_dir("checkpoint-overlap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let now = now_unix_ms();
    let discovered_at = now - 70_000;
    let candidate_id = seed_candidate(&db, "mint-overlap", discovered_at);
    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot(
            ProviderId::Jupiter,
            "mint-overlap",
            "baseline-pair",
            discovered_at + 1_000,
            1.0,
        ),
    )
    .unwrap();

    let market = Arc::new(EvidenceMarket::new(
        ProviderId::Jupiter,
        MarketMode::Valid { price_usd: 2.0 },
    ));
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let reopened = ShreksDb::open(&db_path).unwrap();
    let schedule = reopened.path_sampling(candidate_id).unwrap().unwrap();
    assert_eq!(schedule.sample_count, 1);
    let minute = reopened
        .outcome_checkpoints(candidate_id)
        .unwrap()
        .into_iter()
        .find(|checkpoint| checkpoint.horizon_seconds == 60)
        .unwrap();
    assert_eq!(minute.status, OutcomeCheckpointStatus::Completed);
    assert_eq!(minute.return_pct, Some(100.0));

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn rediscovered_path_due_candidate_advances_from_its_single_normal_market_pass() {
    let root = unique_test_dir("rediscovery");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let rediscovered = candidate("mint-rediscovered", now_unix_ms() - 40_000);
    let candidate_id = db.upsert_candidate(&rediscovered).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, rediscovered.discovered_at_unix_ms)
        .unwrap();
    db.ensure_path_sampling(candidate_id, rediscovered.discovered_at_unix_ms)
        .unwrap();

    let discovery = Arc::new(StaticDiscovery {
        item: rediscovered,
    });
    let market = Arc::new(EvidenceMarket::new(
        ProviderId::Jupiter,
        MarketMode::Valid { price_usd: 1.1 },
    ));
    let calls = market.calls.clone();
    let mut observer = Observer::new(db)
        .with_discovery_provider(discovery)
        .with_market_provider(market);
    observer.run_cycle().await.unwrap();
    drop(observer);

    assert_eq!(calls.lock().unwrap().len(), 1);
    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        reopened.path_sampling(candidate_id).unwrap().unwrap().sample_count,
        1
    );

    cleanup_dir(&root);
}
