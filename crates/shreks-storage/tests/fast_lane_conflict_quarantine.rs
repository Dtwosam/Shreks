use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_storage::{
    pump_swap_event_ordinal, EvidenceWriteOutcome, PumpSwapTradeEvidenceWrite,
    PumpTradeEvidenceWrite, ShreksDb, StorageError,
};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-conflict-quarantine-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn pump_trade(signature: &str) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Chainstack,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 500,
        observed_at_unix_ms: 10_000,
        mint: "mint-a".to_owned(),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 2_500_000_000,
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

fn pumpswap_trade(signature: &str) -> PumpSwapTradeEvidenceWrite {
    let log_index = 46;
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Chainstack,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 600,
        observed_at_unix_ms: 11_000,
        pool: "pool-a".to_owned(),
        user: "wallet-b".to_owned(),
        is_buy: false,
        base_amount_raw: 700_000_000,
        quote_amount_raw: 3_500_000_000,
        user_quote_amount_raw: 3_530_000_000,
        timestamp_unix_seconds: 1_780_000_100,
        pool_base_reserves_raw: 500_000_000_000_000,
        pool_quote_reserves_raw: 40_000_000_000,
    }
}

#[test]
fn pump_runtime_writer_quarantines_conflicting_fork_without_overwriting_source() {
    let root = unique_test_dir("pump");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let first = pump_trade("pump-conflict-signature");
    assert_eq!(
        db.record_pump_trade_evidence_or_quarantine(&first).unwrap(),
        EvidenceWriteOutcome::Inserted
    );

    let mut conflict = first.clone();
    conflict.slot += 2;
    conflict.observed_at_unix_ms += 500;
    conflict.sol_amount_raw += 1;

    assert!(matches!(
        db.record_pump_trade_evidence(&conflict),
        Err(StorageError::InvalidData(_))
    ));
    assert_eq!(
        db.record_pump_trade_evidence_or_quarantine(&conflict)
            .unwrap(),
        EvidenceWriteOutcome::QuarantinedConflict
    );

    assert_eq!(
        db.pump_trade_evidence_for_signature(&first.signature)
            .unwrap(),
        vec![first]
    );
    assert_eq!(db.pump_quarantined_conflict_count().unwrap(), 1);
    assert!(db
        .pending_unambiguous_pump_trade_evidence(10)
        .unwrap()
        .is_empty());

    cleanup_dir(&root);
}

#[test]
fn pumpswap_runtime_writer_quarantines_conflicting_fork_without_overwriting_source() {
    let root = unique_test_dir("pumpswap");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let first = pumpswap_trade("pumpswap-conflict-signature");
    assert_eq!(
        db.record_pump_swap_trade_evidence_or_quarantine(&first)
            .unwrap(),
        EvidenceWriteOutcome::Inserted
    );

    let mut conflict = first.clone();
    conflict.slot += 2;
    conflict.observed_at_unix_ms += 500;
    conflict.quote_amount_raw += 1;

    assert!(matches!(
        db.record_pump_swap_trade_evidence(&conflict),
        Err(StorageError::InvalidData(_))
    ));
    assert_eq!(
        db.record_pump_swap_trade_evidence_or_quarantine(&conflict)
            .unwrap(),
        EvidenceWriteOutcome::QuarantinedConflict
    );

    assert_eq!(
        db.pump_swap_trade_evidence_for_signature(&first.signature)
            .unwrap(),
        vec![first]
    );
    assert_eq!(db.pumpswap_quarantined_conflict_count().unwrap(), 1);
    assert!(db
        .pending_unambiguous_pump_swap_trade_evidence(10)
        .unwrap()
        .is_empty());

    cleanup_dir(&root);
}
