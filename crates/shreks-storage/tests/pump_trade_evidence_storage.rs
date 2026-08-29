use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb, StorageError};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pump-trade-evidence-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn write() -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: "sig-trade-1".to_owned(),
        ordinal: 0,
        slot: u64::MAX,
        observed_at_unix_ms: 1_770_000_000_123,
        mint: "Mint111111111111111111111111111111111111111".to_owned(),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        user: "User111111111111111111111111111111111111111".to_owned(),
        is_buy: true,
        token_amount_raw: u64::MAX,
        sol_amount_raw: u64::MAX - 1,
        quote_amount_raw: u64::MAX - 2,
        timestamp_unix_seconds: 1_770_000_000,
        virtual_sol_reserves_raw: u64::MAX - 3,
        virtual_token_reserves_raw: u64::MAX - 4,
        real_sol_reserves_raw: u64::MAX - 5,
        real_token_reserves_raw: u64::MAX - 6,
        virtual_quote_reserves_raw: u64::MAX - 7,
        real_quote_reserves_raw: u64::MAX - 8,
        ix_name: "buy".to_owned(),
    }
}

#[test]
fn migration_ten_persists_full_width_raw_trade_economics_losslessly() {
    let root = unique_test_dir("roundtrip");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 13);

    let input = write();
    assert!(db.record_pump_trade_evidence(&input).unwrap());

    let rows = db
        .pump_trade_evidence_for_signature(&input.signature)
        .unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0], input);

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn identical_duplicate_is_idempotent_but_conflicting_identity_fails_closed() {
    let root = unique_test_dir("identity");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let input = write();
    assert!(db.record_pump_trade_evidence(&input).unwrap());
    assert!(!db.record_pump_trade_evidence(&input).unwrap());

    let mut conflict = input.clone();
    conflict.quote_amount_raw = 123;
    let error = db.record_pump_trade_evidence(&conflict).unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));

    let rows = db
        .pump_trade_evidence_for_signature(&input.signature)
        .unwrap();
    assert_eq!(rows, vec![input]);

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn ordinal_is_part_of_identity_and_queries_return_deterministic_order() {
    let root = unique_test_dir("ordinal");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let mut second = write();
    second.ordinal = 1;
    second.token_amount_raw = 2;
    let first = write();

    assert!(db.record_pump_trade_evidence(&second).unwrap());
    assert!(db.record_pump_trade_evidence(&first).unwrap());

    let rows = db
        .pump_trade_evidence_for_signature(&first.signature)
        .unwrap();
    assert_eq!(rows, vec![first, second]);

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn invalid_identity_and_timestamps_are_rejected_before_sql_write() {
    let root = unique_test_dir("validation");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let mut blank_signature = write();
    blank_signature.signature = "   ".to_owned();
    assert!(matches!(
        db.record_pump_trade_evidence(&blank_signature),
        Err(StorageError::InvalidData(_))
    ));

    let mut negative_observed = write();
    negative_observed.observed_at_unix_ms = -1;
    assert!(matches!(
        db.record_pump_trade_evidence(&negative_observed),
        Err(StorageError::InvalidData(_))
    ));

    let mut negative_chain_time = write();
    negative_chain_time.timestamp_unix_seconds = -1;
    assert!(matches!(
        db.record_pump_trade_evidence(&negative_chain_time),
        Err(StorageError::InvalidData(_))
    ));

    assert!(db
        .pump_trade_evidence_for_signature("sig-trade-1")
        .unwrap()
        .is_empty());

    drop(db);
    cleanup_dir(&root);
}
