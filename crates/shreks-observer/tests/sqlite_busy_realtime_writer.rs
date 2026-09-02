use std::{
    fs,
    path::PathBuf,
    process, thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::ProviderId;
use shreks_observer::Observer;
use shreks_providers::{pump_realtime::PumpRealtimeNotification, pump_trade::PumpTradeEvidence};
use shreks_storage::ShreksDb;
use tokio::sync::mpsc;

const BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT: Duration = Duration::from_millis(5_200);

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-sqlite-busy-realtime-writer-{}-{nanos}",
        process::id()
    ))
}

fn notification() -> PumpRealtimeNotification {
    PumpRealtimeNotification {
        provider: ProviderId::SolanaPublic,
        signature: "SqliteBusyRealtime111".to_owned(),
        slot: 1_234_567,
        lifecycle: None,
        trades: vec![PumpTradeEvidence {
            mint: "MintBusy111".to_owned(),
            quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
            user: "TraderBusy111".to_owned(),
            is_buy: true,
            token_amount_raw: 500_000_000,
            sol_amount_raw: 2_500_000_000,
            quote_amount_raw: 2_500_000_000,
            timestamp_unix_seconds: 1_777_000_000,
            virtual_sol_reserves_raw: 32_000_000_000,
            virtual_token_reserves_raw: 900_000_000_000_000,
            real_sol_reserves_raw: 10_000_000_000,
            real_token_reserves_raw: 600_000_000_000_000,
            virtual_quote_reserves_raw: 32_000_000_000,
            real_quote_reserves_raw: 10_000_000_000,
            fee_recipient: "FeeRecipientBusy111".to_owned(),
            fee_basis_points: 95,
            fee_raw: 23_750_000,
            creator: "CreatorBusy111".to_owned(),
            creator_fee_basis_points: 30,
            creator_fee_raw: 7_500_000,
            cashback_fee_basis_points: 5,
            cashback_raw: 1_250_000,
            buyback_fee_basis_points: 7,
            buyback_fee_raw: 1_750_000,
            ix_name: "buy".to_owned(),
        }],
        pump_swap_trades: Vec::new(),
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn realtime_writer_survives_one_transient_sqlite_busy_interval() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let writer_db = ShreksDb::open(&db_path).unwrap();

    // Acquire a real competing SQLite writer lock and hold it just beyond the
    // production ShreksDb 5-second busy timeout. This reproduces the physical
    // FL1.5 failure without changing SQLite configuration or mocking storage.
    let blocker = Connection::open(&db_path).unwrap();
    blocker
        .execute_batch("PRAGMA journal_mode=WAL; BEGIN IMMEDIATE;")
        .unwrap();
    let release_lock = thread::spawn(move || {
        thread::sleep(BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT);
        blocker.execute_batch("COMMIT;").unwrap();
    });

    let (sender, receiver) = mpsc::channel(1);
    sender.send(notification()).await.unwrap();
    drop(sender);

    let result = tokio::time::timeout(
        Duration::from_secs(8),
        Observer::run_pump_realtime_writer(writer_db, receiver),
    )
    .await
    .expect("bounded SQLite busy handling must complete after the competing lock clears");

    assert_eq!(
        result.expect("one transient SQLite busy interval must not terminate the mandatory writer"),
        1
    );
    release_lock.join().unwrap();

    let db = ShreksDb::open(&db_path).unwrap();
    let rows = db
        .pump_trade_evidence_for_signature("SqliteBusyRealtime111")
        .unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].provider, ProviderId::SolanaPublic);

    drop(db);
    let _ = fs::remove_dir_all(root);
}
