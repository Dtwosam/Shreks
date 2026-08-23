use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, VenueId};
use shreks_observer::Observer;
use shreks_providers::{pump::PumpCreationSignal, MarketDataProvider, ProviderError};
use shreks_storage::ShreksDb;
use tokio::sync::{mpsc, oneshot};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-adaptive-hardening-{label}-{}-{nanos}",
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

fn seed_adaptive_candidate(db: &ShreksDb, mint: &str, discovered_at_unix_ms: i64) -> i64 {
    let candidate = DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms,
        source: ProviderId::DexScreener,
    };
    let candidate_id = db.upsert_candidate(&candidate).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at_unix_ms)
        .unwrap();
    db.ensure_path_sampling(candidate_id, discovered_at_unix_ms)
        .unwrap();
    candidate_id
}

#[derive(Clone)]
struct CountingEmptyMarket {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl MarketDataProvider for CountingEmptyMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Jupiter
    }

    async fn token_pairs(&self, _token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(Vec::new())
    }
}

#[derive(Clone)]
struct CountingEvidenceMarket {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl MarketDataProvider for CountingEvidenceMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Jupiter
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        let call = self.calls.fetch_add(1, Ordering::SeqCst) + 1;
        Ok(vec![PairMarketData {
            provider: ProviderId::Jupiter,
            venue: VenueId::OtherSolana,
            chain_id: "solana".to_owned(),
            dex_id: "fixture".to_owned(),
            pair_address: format!("{token_mint}-pair-{call}"),
            base_mint: token_mint.to_owned(),
            base_name: None,
            base_symbol: None,
            quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
            quote_name: None,
            quote_symbol: None,
            price_native: None,
            price_usd: Some("1.0".to_owned()),
            liquidity_usd: Some(1_000.0),
            volume_5m: Some(100.0),
            volume_1h: None,
            volume_6h: None,
            volume_24h: None,
            transactions: Vec::new(),
            fdv_usd: None,
            market_cap_usd: None,
            pair_created_at_unix_ms: None,
            observed_at_unix_ms: now_unix_ms(),
        }])
    }
}

#[tokio::test(flavor = "current_thread")]
async fn realtime_pump_wake_does_not_trigger_adaptive_market_work_between_full_cycles() {
    let root = unique_test_dir("realtime-isolation");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    seed_adaptive_candidate(&db, "mint-realtime", now_unix_ms() - 40_000);

    let market_calls = Arc::new(AtomicUsize::new(0));
    let market = Arc::new(CountingEmptyMarket {
        calls: market_calls.clone(),
    });
    let (pump_tx, pump_rx) = mpsc::channel(8);
    let mut observer = Observer::new(db)
        .with_market_provider(market)
        .with_pump_signal_receiver(pump_rx);

    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    let watched_db = db_path.clone();
    let watched_calls = market_calls.clone();
    let run = observer.run_until_shutdown(Duration::from_secs(3_600), async move {
        let _ = shutdown_rx.await;
    });
    let signal = async move {
        for _ in 0..100 {
            if watched_calls.load(Ordering::SeqCst) == 1 {
                break;
            }
            tokio::task::yield_now().await;
        }
        assert_eq!(watched_calls.load(Ordering::SeqCst), 1);

        pump_tx
            .send(PumpCreationSignal {
                signature: "adaptive-wake-signal".to_owned(),
                slot: 777,
            })
            .await
            .unwrap();

        for _ in 0..100 {
            let connection = Connection::open(&watched_db).unwrap();
            let count: i64 = connection
                .query_row(
                    "SELECT COUNT(*) FROM pump_launch_signals WHERE signature = 'adaptive-wake-signal'",
                    [],
                    |row| row.get(0),
                )
                .unwrap();
            drop(connection);
            if count == 1 {
                assert_eq!(
                    watched_calls.load(Ordering::SeqCst),
                    1,
                    "realtime signal persistence must not run adaptive market work"
                );
                let _ = shutdown_tx.send(());
                return;
            }
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
        panic!("realtime Pump signal was not persisted during inter-cycle sleep");
    };

    let joined = async {
        let (run_result, _) = tokio::join!(run, signal);
        run_result
    };
    let cycles = tokio::time::timeout(Duration::from_millis(500), joined)
        .await
        .expect("realtime signal should wake durable ingestion without waiting one hour")
        .unwrap();

    assert_eq!(cycles, 1);
    assert_eq!(market_calls.load(Ordering::SeqCst), 1);

    drop(observer);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn overdue_adaptive_schedule_survives_restart_samples_once_and_does_not_catch_up() {
    let root = unique_test_dir("restart-backlog");
    let db_path = root.join("shreks.db");
    let discovered_at = now_unix_ms() - 40_000;

    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = seed_adaptive_candidate(&db, "mint-restart", discovered_at);
    let before = db.path_sampling(candidate_id).unwrap().unwrap();
    assert_eq!(before.sample_count, 0);
    let original_due = before.next_due_at_unix_ms.unwrap();
    drop(db);

    let calls = Arc::new(AtomicUsize::new(0));
    let db = ShreksDb::open(&db_path).unwrap();
    let same_row = db.path_sampling(candidate_id).unwrap().unwrap();
    assert_eq!(same_row.next_due_at_unix_ms, Some(original_due));
    let market = Arc::new(CountingEvidenceMarket {
        calls: calls.clone(),
    });
    let mut observer = Observer::new(db).with_market_provider(market.clone());
    observer.run_cycle().await.unwrap();
    drop(observer);

    let db = ShreksDb::open(&db_path).unwrap();
    let after = db.path_sampling(candidate_id).unwrap().unwrap();
    assert_eq!(after.candidate_id, candidate_id);
    assert_eq!(after.sample_count, 1);
    let sampled_at = after.last_sample_at_unix_ms.unwrap();
    assert!(sampled_at >= original_due);
    assert_eq!(after.next_due_at_unix_ms, Some(sampled_at + 30_000));
    drop(db);

    // Reopening and running immediately must not replay missed historical slots.
    let db = ShreksDb::open(&db_path).unwrap();
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();
    drop(observer);
    assert_eq!(calls.load(Ordering::SeqCst), 1);

    let connection = Connection::open(&db_path).unwrap();
    let schedule_rows: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM candidate_path_sampling WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(schedule_rows, 1);

    cleanup_dir(&root);
}
