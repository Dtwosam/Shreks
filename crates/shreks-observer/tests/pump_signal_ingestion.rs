use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_observer::Observer;
use shreks_providers::pump::PumpCreationSignal;
use shreks_storage::ShreksDb;
use tokio::sync::mpsc;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pump-ingestion-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[tokio::test]
async fn queued_pump_signal_is_persisted_by_observer_before_cycle_processing() {
    let root = unique_test_dir("queued");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let (sender, receiver) = mpsc::channel(8);

    sender
        .send(PumpCreationSignal {
            signature: "stream-signature".to_owned(),
            slot: u64::MAX,
        })
        .await
        .unwrap();

    let mut observer = Observer::new(db).with_pump_signal_receiver(receiver);
    let report = observer.run_cycle().await.unwrap();

    assert_eq!(report.pump_signals_received, 1);
    assert_eq!(report.pump_signals_processed, 0);

    drop(observer);
    let connection = Connection::open(&db_path).unwrap();
    let row: (String, String, i64) = connection
        .query_row(
            "SELECT slot, status, observed_at_unix_ms FROM pump_launch_signals WHERE signature = 'stream-signature'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(row.0, u64::MAX.to_string());
    assert_eq!(row.1, "pending");
    assert!(row.2 > 0);

    cleanup_dir(&root);
}

#[tokio::test]
async fn duplicate_stream_delivery_remains_one_durable_signal() {
    let root = unique_test_dir("duplicate");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let (sender, receiver) = mpsc::channel(8);

    for _ in 0..2 {
        sender
            .send(PumpCreationSignal {
                signature: "duplicate-signature".to_owned(),
                slot: 42,
            })
            .await
            .unwrap();
    }

    let mut observer = Observer::new(db).with_pump_signal_receiver(receiver);
    let report = observer.run_cycle().await.unwrap();
    assert_eq!(report.pump_signals_received, 2);

    drop(observer);
    let connection = Connection::open(&db_path).unwrap();
    let row: (i64, String) = connection
        .query_row(
            "SELECT COUNT(*), MAX(slot) FROM pump_launch_signals WHERE signature = 'duplicate-signature'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(row.0, 1);
    assert_eq!(row.1, "42");

    cleanup_dir(&root);
}
