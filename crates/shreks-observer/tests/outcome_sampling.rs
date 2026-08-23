use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    },
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, TokenMintState, TransactionWindow, VenueId,
};
use shreks_observer::Observer;
use shreks_providers::{ChainDataProvider, MarketDataProvider, ProviderError};
use shreks_storage::ShreksDb;
use tokio::time::Instant;

const EXPECTED_DUE_CANDIDATE_LIMIT: usize = 16;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-outcome-sampling-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn seed_candidate(db: &ShreksDb, mint: &str, discovered_at_unix_ms: i64) -> i64 {
    let candidate = DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms,
        source: ProviderId::Helius,
    };
    let candidate_id = db.upsert_candidate(&candidate).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at_unix_ms)
        .unwrap();
    candidate_id
}

fn market_snapshot(
    provider: ProviderId,
    venue: VenueId,
    mint: &str,
    pair_address: &str,
    observed_at_unix_ms: i64,
    price_usd: Option<f64>,
    liquidity_usd: Option<f64>,
    volume_5m: Option<f64>,
    flow_5m: Option<(u64, u64)>,
) -> PairMarketData {
    PairMarketData {
        provider,
        venue,
        chain_id: "solana".to_owned(),
        dex_id: venue.as_str().to_owned(),
        pair_address: pair_address.to_owned(),
        base_mint: mint.to_owned(),
        base_name: Some("Outcome Token".to_owned()),
        base_symbol: Some("OUT".to_owned()),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: Some("Wrapped SOL".to_owned()),
        quote_symbol: Some("SOL".to_owned()),
        price_native: None,
        price_usd: price_usd.map(|value| value.to_string()),
        liquidity_usd,
        volume_5m,
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: flow_5m
            .map(|(buys, sells)| {
                vec![TransactionWindow {
                    window: "m5".to_owned(),
                    buys,
                    sells,
                }]
            })
            .unwrap_or_default(),
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: None,
        observed_at_unix_ms,
    }
}

#[derive(Clone, Default)]
struct CountingMarket {
    calls: Arc<Mutex<Vec<(String, Instant)>>>,
}

impl CountingMarket {
    fn mints(&self) -> Vec<String> {
        self.calls
            .lock()
            .unwrap()
            .iter()
            .map(|(mint, _)| mint.clone())
            .collect()
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
impl MarketDataProvider for CountingMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls
            .lock()
            .unwrap()
            .push((token_mint.to_owned(), Instant::now()));
        Ok(Vec::new())
    }
}

#[derive(Clone)]
struct StaticSnapshotMarket {
    snapshot: PairMarketData,
}

#[async_trait]
impl MarketDataProvider for StaticSnapshotMarket {
    fn provider_id(&self) -> ProviderId {
        self.snapshot.provider
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        assert_eq!(token_mint, self.snapshot.base_mint);
        Ok(vec![self.snapshot.clone()])
    }
}

#[derive(Clone, Default)]
struct CountingChain {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl ChainDataProvider for CountingChain {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn token_mint_state(&self, token_mint: &str) -> Result<TokenMintState, ProviderError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(TokenMintState {
            provider: ProviderId::Helius,
            mint: token_mint.to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1,
            decimals: 0,
            mint_authority: None,
            freeze_authority: None,
            slot: 1,
            observed_at_unix_ms: 1,
        })
    }
}

#[tokio::test(start_paused = true)]
async fn due_candidate_gets_one_market_pass_even_when_all_horizons_are_overdue_and_no_chain_call() {
    let root = unique_test_dir("dedupe-no-chain");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    seed_candidate(&db, "mint-due", 0);

    let market = Arc::new(CountingMarket::default());
    let chain = Arc::new(CountingChain::default());
    let chain_calls = chain.calls.clone();
    let mut observer = Observer::new(db)
        .with_market_provider(market.clone())
        .with_chain_provider(chain);

    observer.run_cycle().await.unwrap();

    assert_eq!(market.mints(), vec!["mint-due"]);
    assert_eq!(chain_calls.load(Ordering::SeqCst), 0);

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn not_yet_due_candidate_causes_no_outcome_market_call() {
    let root = unique_test_dir("not-due");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    seed_candidate(&db, "mint-future", 4_000_000_000_000);

    let market = Arc::new(CountingMarket::default());
    let mut observer = Observer::new(db).with_market_provider(market.clone());
    observer.run_cycle().await.unwrap();

    assert!(market.mints().is_empty());

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn due_candidate_batch_is_capped_to_protect_free_provider_budgets() {
    let root = unique_test_dir("batch-cap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    for index in 0..=EXPECTED_DUE_CANDIDATE_LIMIT {
        seed_candidate(&db, &format!("mint-{index:02}"), 0);
    }

    let market = Arc::new(CountingMarket::default());
    let mut observer = Observer::new(db).with_market_provider(market.clone());
    observer.run_cycle().await.unwrap();

    let mints = market.mints();
    assert_eq!(mints.len(), EXPECTED_DUE_CANDIDATE_LIMIT);
    assert_eq!(mints.first().map(String::as_str), Some("mint-00"));
    assert_eq!(mints.last().map(String::as_str), Some("mint-15"));
    assert!(!mints.iter().any(|mint| mint == "mint-16"));

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn due_sampling_reuses_existing_dexscreener_market_pacing() {
    let root = unique_test_dir("pacing");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    seed_candidate(&db, "mint-a", 0);
    seed_candidate(&db, "mint-b", 0);

    let market = Arc::new(CountingMarket::default());
    let mut observer = Observer::new(db).with_market_provider(market.clone());
    observer.run_cycle().await.unwrap();

    let instants = market.instants();
    assert_eq!(instants.len(), 2);
    assert!(instants[1].duration_since(instants[0]).as_millis() >= 250);

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn due_checkpoint_finalization_uses_real_snapshot_ids_and_computes_negative_return_excursions_and_flow() {
    let root = unique_test_dir("metrics-negative");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let mint = "mint-metrics-negative";
    let candidate_id = seed_candidate(&db, mint, 1_000);

    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot(
            ProviderId::Meteora,
            VenueId::MeteoraDlmm,
            mint,
            "baseline-meteora",
            1_500,
            Some(10.0),
            Some(100.0),
            Some(200.0),
            Some((10, 5)),
        ),
    )
    .unwrap();
    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot(
            ProviderId::DexScreener,
            VenueId::PumpSwap,
            mint,
            "peak-pumpswap",
            30_000,
            Some(15.0),
            Some(120.0),
            Some(240.0),
            Some((12, 6)),
        ),
    )
    .unwrap();
    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot(
            ProviderId::DexScreener,
            VenueId::PumpSwap,
            mint,
            "trough-pumpswap",
            50_000,
            Some(7.0),
            Some(70.0),
            Some(260.0),
            Some((13, 8)),
        ),
    )
    .unwrap();

    let final_snapshot = market_snapshot(
        ProviderId::DexScreener,
        VenueId::PumpSwap,
        mint,
        "checkpoint-pumpswap",
        70_000,
        Some(8.0),
        Some(80.0),
        Some(300.0),
        Some((14, 9)),
    );
    let mut observer = Observer::new(db).with_market_provider(Arc::new(StaticSnapshotMarket {
        snapshot: final_snapshot,
    }));
    observer.run_cycle().await.unwrap();
    drop(observer);

    let connection = Connection::open(&db_path).unwrap();
    let row: (
        String,
        i64,
        i64,
        Option<f64>,
        Option<f64>,
        Option<f64>,
        Option<f64>,
        Option<f64>,
        Option<i64>,
        Option<i64>,
        Option<i64>,
        Option<String>,
    ) = connection
        .query_row(
            r#"SELECT status, baseline_snapshot_id, checkpoint_snapshot_id,
                      return_pct, mfe_pct, mae_pct, liquidity_change_pct,
                      volume_m5_change_pct, buys_m5_change, sells_m5_change,
                      rug_or_dead_pool, exitability
               FROM candidate_outcome_checkpoints
               WHERE candidate_id = ?1 AND horizon_seconds = 60"#,
            [candidate_id],
            |row| {
                Ok((
                    row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?, row.get(5)?,
                    row.get(6)?, row.get(7)?, row.get(8)?, row.get(9)?, row.get(10)?, row.get(11)?,
                ))
            },
        )
        .unwrap();

    assert_eq!(row.0, "completed");
    assert!((row.3.unwrap() - (-20.0)).abs() < 1e-9);
    assert!((row.4.unwrap() - 50.0).abs() < 1e-9);
    assert!((row.5.unwrap() - (-30.0)).abs() < 1e-9);
    assert!((row.6.unwrap() - (-20.0)).abs() < 1e-9);
    assert!((row.7.unwrap() - 50.0).abs() < 1e-9);
    assert_eq!(row.8, Some(4));
    assert_eq!(row.9, Some(4));
    assert_eq!(row.10, None);
    assert_eq!(row.11, None);

    let baseline_identity: (String, String, String) = connection
        .query_row(
            "SELECT source, venue, pair_address FROM market_snapshots WHERE id = ?1",
            [row.1],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    let checkpoint_identity: (String, String, String) = connection
        .query_row(
            "SELECT source, venue, pair_address FROM market_snapshots WHERE id = ?1",
            [row.2],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(baseline_identity, ("meteora".to_owned(), "meteora_dlmm".to_owned(), "baseline-meteora".to_owned()));
    assert_eq!(checkpoint_identity, ("dexscreener".to_owned(), "pump_swap".to_owned(), "checkpoint-pumpswap".to_owned()));

    let later_status: String = connection
        .query_row(
            "SELECT status FROM candidate_outcome_checkpoints WHERE candidate_id = ?1 AND horizon_seconds = 300",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(later_status, "pending");

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn finalization_computes_positive_return_but_leaves_zero_denominator_and_missing_flow_metrics_null() {
    let root = unique_test_dir("metrics-positive-null");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let mint = "mint-metrics-positive";
    let candidate_id = seed_candidate(&db, mint, 2_000);

    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot(
            ProviderId::DexScreener,
            VenueId::PumpSwap,
            mint,
            "baseline-zero-denominators",
            2_500,
            Some(10.0),
            Some(0.0),
            Some(0.0),
            None,
        ),
    )
    .unwrap();
    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot(
            ProviderId::DexScreener,
            VenueId::PumpSwap,
            mint,
            "downside",
            40_000,
            Some(7.0),
            Some(30.0),
            Some(50.0),
            None,
        ),
    )
    .unwrap();

    let final_snapshot = market_snapshot(
        ProviderId::DexScreener,
        VenueId::PumpSwap,
        mint,
        "positive-checkpoint",
        80_000,
        Some(12.0),
        Some(100.0),
        Some(200.0),
        Some((20, 11)),
    );
    let mut observer = Observer::new(db).with_market_provider(Arc::new(StaticSnapshotMarket {
        snapshot: final_snapshot,
    }));
    observer.run_cycle().await.unwrap();
    drop(observer);

    let connection = Connection::open(&db_path).unwrap();
    let row: (
        String,
        Option<f64>,
        Option<f64>,
        Option<f64>,
        Option<f64>,
        Option<f64>,
        Option<i64>,
        Option<i64>,
    ) = connection
        .query_row(
            r#"SELECT status, return_pct, mfe_pct, mae_pct,
                      liquidity_change_pct, volume_m5_change_pct,
                      buys_m5_change, sells_m5_change
               FROM candidate_outcome_checkpoints
               WHERE candidate_id = ?1 AND horizon_seconds = 60"#,
            [candidate_id],
            |row| {
                Ok((
                    row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?,
                    row.get(4)?, row.get(5)?, row.get(6)?, row.get(7)?,
                ))
            },
        )
        .unwrap();

    assert_eq!(row.0, "completed");
    assert!((row.1.unwrap() - 20.0).abs() < 1e-9);
    assert!((row.2.unwrap() - 20.0).abs() < 1e-9);
    assert!((row.3.unwrap() - (-30.0)).abs() < 1e-9);
    assert_eq!(row.4, None);
    assert_eq!(row.5, None);
    assert_eq!(row.6, None);
    assert_eq!(row.7, None);

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn checkpoint_stays_pending_when_due_observation_has_no_usable_price() {
    let root = unique_test_dir("no-post-due-price");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let mint = "mint-no-price";
    let candidate_id = seed_candidate(&db, mint, 1_000);

    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot(
            ProviderId::DexScreener,
            VenueId::PumpSwap,
            mint,
            "baseline-price",
            1_500,
            Some(10.0),
            Some(100.0),
            Some(200.0),
            Some((10, 5)),
        ),
    )
    .unwrap();

    let due_without_price = market_snapshot(
        ProviderId::DexScreener,
        VenueId::PumpSwap,
        mint,
        "due-without-price",
        70_000,
        None,
        Some(50.0),
        Some(400.0),
        Some((30, 20)),
    );
    let mut observer = Observer::new(db).with_market_provider(Arc::new(StaticSnapshotMarket {
        snapshot: due_without_price,
    }));
    observer.run_cycle().await.unwrap();
    drop(observer);

    let connection = Connection::open(&db_path).unwrap();
    let status: String = connection
        .query_row(
            "SELECT status FROM candidate_outcome_checkpoints WHERE candidate_id = ?1 AND horizon_seconds = 60",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    let snapshots: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM market_snapshots WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(status, "pending");
    assert_eq!(snapshots, 2);

    cleanup_dir(&root);
}
