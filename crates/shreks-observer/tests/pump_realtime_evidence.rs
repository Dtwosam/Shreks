use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_observer::Observer;
use shreks_providers::{
    pump::{PumpCreationSignal, PumpLifecycleSignal},
    pump_realtime::PumpRealtimeNotification,
    pump_trade::PumpTradeEvidence,
};
use shreks_storage::ShreksDb;
use tokio::sync::mpsc;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pump-realtime-evidence-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn trade() -> PumpTradeEvidence {
    PumpTradeEvidence {
        mint: "MintRealtime111".to_owned(),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        user: "TraderRealtime111".to_owned(),
        is_buy: true,
        token_amount_raw: u64::MAX,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 2_500_000_000,
        timestamp_unix_seconds: 1_770_000_000,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 32_000_000_000,
        real_quote_reserves_raw: 10_000_000_000,
        ix_name: "buy".to_owned(),
    }
}

fn notification() -> PumpRealtimeNotification {
    PumpRealtimeNotification {
        signature: "RealtimeSignature111".to_owned(),
        slot: u64::MAX,
        lifecycle: Some(PumpLifecycleSignal::Creation(PumpCreationSignal {
            signature: "RealtimeSignature111".to_owned(),
            slot: u64::MAX,
        })),
        trades: vec![trade()],
        pump_swap_trades: Vec::new(),
    }
}

#[tokio::test]
async fn realtime_writer_persists_lifecycle_and_trade_economics_immediately_and_idempotently() {
    let root = unique_test_dir("writer");
    let db_path = root.join("shreks.db");
    let writer_db = ShreksDb::open(&db_path).unwrap();
    let (sender, receiver) = mpsc::channel(4);

    let event = notification();
    sender.send(event.clone()).await.unwrap();
    sender.send(event).await.unwrap();
    drop(sender);

    let inserted = Observer::run_pump_realtime_writer(writer_db, receiver)
        .await
        .expect("realtime writer should drain the bounded channel");
    assert_eq!(inserted, 1, "duplicate economic replay must not create a second row");

    let db = ShreksDb::open(&db_path).unwrap();
    let pending = db.pending_pump_launch_signals(10).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].signature, "RealtimeSignature111");
    assert_eq!(pending[0].slot, u64::MAX);
    assert!(pending[0].observed_at_unix_ms >= 0);

    let rows = db
        .pump_trade_evidence_for_signature("RealtimeSignature111")
        .unwrap();
    assert_eq!(rows.len(), 1);
    let row = &rows[0];
    assert_eq!(row.provider, ProviderId::Helius);
    assert_eq!(row.signature, "RealtimeSignature111");
    assert_eq!(row.ordinal, 0);
    assert_eq!(row.slot, u64::MAX);
    assert!(row.observed_at_unix_ms >= 0);
    assert_eq!(row.mint, "MintRealtime111");
    assert_eq!(row.user, "TraderRealtime111");
    assert!(row.is_buy);
    assert_eq!(row.token_amount_raw, u64::MAX);
    assert_eq!(row.sol_amount_raw, 2_500_000_000);
    assert_eq!(row.quote_amount_raw, 2_500_000_000);
    assert_eq!(row.ix_name, "buy");

    cleanup_dir(&root);
}

#[tokio::test]
async fn realtime_writer_persists_migration_in_the_same_durable_boundary() {
    use shreks_providers::pump::{PumpMigrationSignal, PumpLifecycleSignal};

    let root = unique_test_dir("migration");
    let db_path = root.join("shreks.db");
    let writer_db = ShreksDb::open(&db_path).unwrap();
    let (sender, receiver) = mpsc::channel(1);

    sender
        .send(PumpRealtimeNotification {
            signature: "MigrationSignature111".to_owned(),
            slot: 88,
            lifecycle: Some(PumpLifecycleSignal::Migration(PumpMigrationSignal {
                signature: "MigrationSignature111".to_owned(),
                slot: 88,
            })),
            trades: Vec::new(),
            pump_swap_trades: Vec::new(),
        })
        .await
        .unwrap();
    drop(sender);

    assert_eq!(
        Observer::run_pump_realtime_writer(writer_db, receiver)
            .await
            .unwrap(),
        0
    );

    let db = ShreksDb::open(&db_path).unwrap();
    let pending = db.pending_pump_migration_signals(10).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].signature, "MigrationSignature111");
    assert_eq!(pending[0].slot, 88);

    cleanup_dir(&root);
}
