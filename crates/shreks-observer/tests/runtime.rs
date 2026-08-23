use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    },
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, VenueId};
use shreks_observer::Observer;
use shreks_providers::{
    pump::{PumpCreationSignal, PumpLifecycleSignal},
    DiscoveryProvider, MarketDataProvider, ProviderError, ProviderErrorKind,
};
use shreks_storage::{OutcomeCheckpointStatus, ShreksDb};
use tokio::{
    sync::{mpsc, oneshot},
    time::Instant,
};

const DISCOVERY_WATERMARK_STREAM: &str = "discovery_watermark_unix_ms";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-observer-runtime-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate_at(mint: &str, discovered_at_unix_ms: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: None,
        venue: None,
        discovered_at_unix_ms,
        source: ProviderId::DexScreener,
    }
}

fn market_snapshot(mint: &str, price_usd: &str, observed_at_unix_ms: i64) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::OtherSolana,
        chain_id: "solana".to_owned(),
        dex_id: "fixture-dex".to_owned(),
        pair_address: format!("fixture-pair-{mint}"),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some(price_usd.to_owned()),
        liquidity_usd: Some(1_000.0),
        volume_5m: Some(100.0),
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: Vec::new(),
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: None,
        observed_at_unix_ms,
    }
}

struct FakeDiscovery {
    result: Result<Vec<DiscoveredToken>, ProviderError>,
}

#[async_trait]
impl DiscoveryProvider for FakeDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        self.result.clone()
    }
}

struct CountingDiscovery {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl DiscoveryProvider for CountingDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(Vec::new())
    }
}

struct TimedMarket {
    calls: Arc<Mutex<Vec<Instant>>>,
}

#[async_trait]
impl MarketDataProvider for TimedMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, _token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls.lock().unwrap().push(Instant::now());
        Ok(Vec::new())
    }
}

struct FixedMarket {
    snapshots: Vec<PairMarketData>,
}

#[async_trait]
impl MarketDataProvider for FixedMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, _token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        Ok(self.snapshots.clone())
    }
}

#[tokio::test(flavor = "current_thread")]
async fn discovery_watermark_is_monotonic_and_survives_restart() {
    let root = unique_test_dir("watermark");
    let db_path = root.join("shreks.db");

    let db = ShreksDb::open(&db_path).unwrap();
    let discovery = Arc::new(FakeDiscovery {
        result: Ok(vec![
            candidate_at("mint-10", 10),
            candidate_at("mint-25", 25),
            candidate_at("mint-20", 20),
        ]),
    });
    let mut observer = Observer::new(db).with_discovery_provider(discovery);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        db.ingestion_checkpoint(ProviderId::DexScreener, DISCOVERY_WATERMARK_STREAM)
            .unwrap()
            .as_deref(),
        Some("25")
    );
    drop(db);

    let db = ShreksDb::open(&db_path).unwrap();
    let older_discovery = Arc::new(FakeDiscovery {
        result: Ok(vec![candidate_at("mint-12", 12)]),
    });
    let mut observer = Observer::new(db).with_discovery_provider(older_discovery);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        db.ingestion_checkpoint(ProviderId::DexScreener, DISCOVERY_WATERMARK_STREAM)
            .unwrap()
            .as_deref(),
        Some("25"),
        "a later cycle must not regress the durable discovery watermark"
    );

    drop(db);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn consecutive_provider_failure_streak_survives_restart_and_success_resets_it() {
    let root = unique_test_dir("failure-streak");
    let db_path = root.join("shreks.db");

    for _ in 0..2 {
        let db = ShreksDb::open(&db_path).unwrap();
        let failing = Arc::new(FakeDiscovery {
            result: Err(ProviderError::new(
                ProviderId::DexScreener,
                ProviderErrorKind::Unavailable,
                "fixture outage",
            )),
        });
        let mut observer = Observer::new(db).with_discovery_provider(failing);
        observer.run_cycle().await.unwrap();
    }

    let connection = Connection::open(&db_path).unwrap();
    let failures: i64 = connection
        .query_row(
            "SELECT consecutive_failures FROM provider_health WHERE provider = 'dexscreener'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(failures, 2, "failure streak must continue across process restart");
    drop(connection);

    let db = ShreksDb::open(&db_path).unwrap();
    let healthy = Arc::new(FakeDiscovery {
        result: Ok(Vec::new()),
    });
    let mut observer = Observer::new(db).with_discovery_provider(healthy);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let connection = Connection::open(&db_path).unwrap();
    let failures: i64 = connection
        .query_row(
            "SELECT consecutive_failures FROM provider_health WHERE provider = 'dexscreener'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(failures, 0, "a successful provider call resets the streak");

    drop(connection);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread", start_paused = true)]
async fn dexscreener_market_calls_respect_the_conservative_four_rps_budget() {
    let root = unique_test_dir("pacing");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let discovery = Arc::new(FakeDiscovery {
        result: Ok(vec![candidate_at("mint-a", 10), candidate_at("mint-b", 11)]),
    });
    let calls = Arc::new(Mutex::new(Vec::new()));
    let market = Arc::new(TimedMarket {
        calls: Arc::clone(&calls),
    });

    let mut observer = Observer::new(db)
        .with_discovery_provider(discovery)
        .with_market_provider(market);
    observer.run_cycle().await.unwrap();

    let calls = calls.lock().unwrap();
    assert_eq!(calls.len(), 2);
    assert!(
        calls[1].duration_since(calls[0]) >= Duration::from_millis(250),
        "four requests/second requires at least 250ms between market calls"
    );

    drop(calls);
    drop(observer);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn pending_outcome_checkpoint_survives_restart_and_completes_without_duplicate_schedule() {
    let root = unique_test_dir("outcome-restart");
    let db_path = root.join("shreks.db");
    let mint = "mint-outcome-restart";

    let db = ShreksDb::open(&db_path).unwrap();
    let candidate = candidate_at(mint, 0);
    let candidate_id = db.upsert_candidate(&candidate).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, candidate.discovered_at_unix_ms)
        .unwrap();
    db.insert_market_snapshot(candidate_id, &market_snapshot(mint, "1.0", 1_000))
        .unwrap();

    let before = db.outcome_checkpoints(candidate_id).unwrap();
    assert_eq!(before.len(), 7);
    let before_60s = before
        .iter()
        .find(|checkpoint| checkpoint.horizon_seconds == 60)
        .unwrap();
    assert_eq!(before_60s.status, OutcomeCheckpointStatus::Pending);
    let original_checkpoint_id = before_60s.id;
    drop(db);

    let db = ShreksDb::open(&db_path).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, candidate.discovered_at_unix_ms)
        .unwrap();
    let after_reopen = db.outcome_checkpoints(candidate_id).unwrap();
    assert_eq!(after_reopen.len(), 7, "restart must not duplicate the schedule");
    assert_eq!(
        after_reopen
            .iter()
            .find(|checkpoint| checkpoint.horizon_seconds == 60)
            .unwrap()
            .id,
        original_checkpoint_id,
        "restart must preserve the original durable checkpoint row"
    );

    let market = Arc::new(FixedMarket {
        snapshots: vec![market_snapshot(mint, "1.5", 61_000)],
    });
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();
    drop(observer);

    let db = ShreksDb::open(&db_path).unwrap();
    let completed = db.outcome_checkpoints(candidate_id).unwrap();
    assert_eq!(completed.len(), 7);
    assert_eq!(
        completed
            .iter()
            .filter(|checkpoint| checkpoint.horizon_seconds == 60)
            .count(),
        1,
        "the 60-second horizon must still have exactly one durable row"
    );
    let completed_60s = completed
        .iter()
        .find(|checkpoint| checkpoint.horizon_seconds == 60)
        .unwrap();
    assert_eq!(completed_60s.id, original_checkpoint_id);
    assert_eq!(completed_60s.status, OutcomeCheckpointStatus::Completed);
    assert!(
        (completed_60s.return_pct.unwrap() - 50.0).abs() < 1e-9,
        "1.0 -> 1.5 should complete the original checkpoint at +50%"
    );

    drop(db);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn shutdown_interrupts_a_long_inter_cycle_sleep() {
    let root = unique_test_dir("shutdown");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let discovery = Arc::new(CountingDiscovery {
        calls: Arc::clone(&calls),
    });
    let mut observer = Observer::new(db).with_discovery_provider(discovery);

    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    let run = observer.run_until_shutdown(Duration::from_secs(3_600), async move {
        let _ = shutdown_rx.await;
    });
    let signal = async move {
        tokio::task::yield_now().await;
        let _ = shutdown_tx.send(());
    };

    let joined = async {
        let (run_result, _) = tokio::join!(run, signal);
        run_result
    };
    let cycles = tokio::time::timeout(Duration::from_millis(100), joined)
        .await
        .expect("shutdown should interrupt the one-hour sleep")
        .unwrap();

    assert_eq!(cycles, 1, "one cycle should complete before shutdown");
    assert_eq!(calls.load(Ordering::SeqCst), 1);

    drop(observer);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn pump_signal_wakes_sleep_for_durable_write_without_forcing_full_cycle() {
    let root = unique_test_dir("pump-wake");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let discovery = Arc::new(CountingDiscovery {
        calls: Arc::clone(&calls),
    });
    let (pump_tx, pump_rx) = mpsc::channel(8);
    let mut observer = Observer::new(db)
        .with_discovery_provider(discovery)
        .with_pump_signal_receiver(pump_rx);

    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    let watched_db = db_path.clone();
    let run = observer.run_until_shutdown(Duration::from_secs(3_600), async move {
        let _ = shutdown_rx.await;
    });
    let signal = async move {
        tokio::task::yield_now().await;
        pump_tx
            .send(PumpLifecycleSignal::Creation(PumpCreationSignal {
                signature: "wake-signature".to_owned(),
                slot: 999,
            }))
            .await
            .unwrap();

        for _ in 0..50 {
            let connection = Connection::open(&watched_db).unwrap();
            let count: i64 = connection
                .query_row(
                    "SELECT COUNT(*) FROM pump_launch_signals WHERE signature = 'wake-signature'",
                    [],
                    |row| row.get(0),
                )
                .unwrap();
            if count == 1 {
                let _ = shutdown_tx.send(());
                return;
            }
            drop(connection);
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
        panic!("Pump signal was not persisted while observer waited between cycles");
    };

    let joined = async {
        let (run_result, _) = tokio::join!(run, signal);
        run_result
    };
    let cycles = tokio::time::timeout(Duration::from_millis(250), joined)
        .await
        .expect("Pump signal should wake the observer instead of waiting one hour")
        .unwrap();

    assert_eq!(cycles, 1, "durable signal ingestion must not force a full provider cycle");
    assert_eq!(calls.load(Ordering::SeqCst), 1);

    drop(observer);
    cleanup_dir(&root);
}
