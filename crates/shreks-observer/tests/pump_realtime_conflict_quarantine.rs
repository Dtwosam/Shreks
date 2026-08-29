use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_observer::Observer;
use shreks_providers::{
    pump_realtime::PumpRealtimeNotification,
    pump_swap_trade::PumpSwapTradeEvidence,
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
        "shreks-pump-realtime-conflict-quarantine-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn pump_trade(sol_amount_raw: u64) -> PumpTradeEvidence {
    PumpTradeEvidence {
        mint: "MintConflict111".to_owned(),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        user: "TraderConflict111".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw,
        quote_amount_raw: sol_amount_raw,
        timestamp_unix_seconds: 1_780_000_000,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 32_000_000_000,
        real_quote_reserves_raw: 10_000_000_000,
        ix_name: "buy".to_owned(),
    }
}

fn pumpswap_trade(quote_amount_raw: u64) -> PumpSwapTradeEvidence {
    PumpSwapTradeEvidence {
        log_index: 46,
        pool: "PumpSwapPoolConflict111".to_owned(),
        user: "PumpSwapTraderConflict111".to_owned(),
        is_buy: false,
        base_amount_raw: 700_000_000,
        quote_amount_raw,
        user_quote_amount_raw: quote_amount_raw + 30_000_000,
        timestamp_unix_seconds: 1_780_000_100,
        pool_base_reserves_raw: 500_000_000_000_000,
        pool_quote_reserves_raw: 40_000_000_000,
    }
}

#[tokio::test]
async fn pump_conflict_is_quarantined_and_later_unrelated_evidence_still_persists() {
    let root = unique_test_dir("pump");
    let db_path = root.join("shreks.db");
    let writer_db = ShreksDb::open(&db_path).unwrap();
    let (sender, receiver) = mpsc::channel(4);

    sender
        .send(PumpRealtimeNotification {
            provider: ProviderId::Chainstack,
            signature: "PumpConflictSignature111".to_owned(),
            slot: 500,
            lifecycle: None,
            trades: vec![pump_trade(2_500_000_000)],
            pump_swap_trades: Vec::new(),
        })
        .await
        .unwrap();
    sender
        .send(PumpRealtimeNotification {
            provider: ProviderId::Chainstack,
            signature: "PumpConflictSignature111".to_owned(),
            slot: 502,
            lifecycle: None,
            trades: vec![pump_trade(2_500_000_001)],
            pump_swap_trades: Vec::new(),
        })
        .await
        .unwrap();
    sender
        .send(PumpRealtimeNotification {
            provider: ProviderId::Chainstack,
            signature: "PumpUnrelatedSignature111".to_owned(),
            slot: 503,
            lifecycle: None,
            trades: vec![pump_trade(2_600_000_000)],
            pump_swap_trades: Vec::new(),
        })
        .await
        .unwrap();
    drop(sender);

    let inserted = Observer::run_pump_realtime_writer(writer_db, receiver)
        .await
        .expect("fork conflict must not terminate the realtime writer");
    assert_eq!(inserted, 2);

    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.pump_quarantined_conflict_count().unwrap(), 1);
    assert_eq!(
        db.pump_trade_evidence_for_signature("PumpConflictSignature111")
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        db.pump_trade_evidence_for_signature("PumpUnrelatedSignature111")
            .unwrap()
            .len(),
        1
    );

    cleanup_dir(&root);
}

#[tokio::test]
async fn pumpswap_conflict_is_quarantined_and_later_unrelated_evidence_still_persists() {
    let root = unique_test_dir("pumpswap");
    let db_path = root.join("shreks.db");
    let writer_db = ShreksDb::open(&db_path).unwrap();
    let (sender, receiver) = mpsc::channel(4);

    sender
        .send(PumpRealtimeNotification {
            provider: ProviderId::Chainstack,
            signature: "PumpSwapConflictSignature111".to_owned(),
            slot: 600,
            lifecycle: None,
            trades: Vec::new(),
            pump_swap_trades: vec![pumpswap_trade(3_500_000_000)],
        })
        .await
        .unwrap();
    sender
        .send(PumpRealtimeNotification {
            provider: ProviderId::Chainstack,
            signature: "PumpSwapConflictSignature111".to_owned(),
            slot: 602,
            lifecycle: None,
            trades: Vec::new(),
            pump_swap_trades: vec![pumpswap_trade(3_500_000_001)],
        })
        .await
        .unwrap();
    sender
        .send(PumpRealtimeNotification {
            provider: ProviderId::Chainstack,
            signature: "PumpSwapUnrelatedSignature111".to_owned(),
            slot: 603,
            lifecycle: None,
            trades: Vec::new(),
            pump_swap_trades: vec![pumpswap_trade(3_600_000_000)],
        })
        .await
        .unwrap();
    drop(sender);

    let inserted = Observer::run_pump_realtime_writer(writer_db, receiver)
        .await
        .expect("PumpSwap fork conflict must not terminate the realtime writer");
    assert_eq!(inserted, 2);

    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.pumpswap_quarantined_conflict_count().unwrap(), 1);
    assert_eq!(
        db.pump_swap_trade_evidence_for_signature("PumpSwapConflictSignature111")
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        db.pump_swap_trade_evidence_for_signature("PumpSwapUnrelatedSignature111")
            .unwrap()
            .len(),
        1
    );

    cleanup_dir(&root);
}
