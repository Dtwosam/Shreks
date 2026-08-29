use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
    StorageError,
};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-fork-replay-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn pump_trade() -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: "forked-pump-signature".to_owned(),
        ordinal: 0,
        slot: 100,
        observed_at_unix_ms: 1_000,
        mint: "mint-a".to_owned(),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
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

fn pump_swap_trade() -> PumpSwapTradeEvidenceWrite {
    let log_index = 17;
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: "forked-pumpswap-signature".to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 200,
        observed_at_unix_ms: 2_000,
        pool: "pool-a".to_owned(),
        user: "wallet-b".to_owned(),
        is_buy: false,
        base_amount_raw: 700_000_000,
        quote_amount_raw: 3_500_000_000,
        user_quote_amount_raw: 3_530_000_000,
        timestamp_unix_seconds: 1_770_000_100,
        pool_base_reserves_raw: 500_000_000_000_000,
        pool_quote_reserves_raw: 40_000_000_000,
    }
}

#[test]
fn pump_replay_on_new_fork_slot_preserves_first_provenance_when_economics_match() {
    let root = unique_test_dir("pump");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let first = pump_trade();
    assert!(db.record_pump_trade_evidence(&first).unwrap());

    let mut replay = first.clone();
    replay.provider = ProviderId::Chainstack;
    replay.slot = 102;
    replay.observed_at_unix_ms = 1_500;

    assert!(!db.record_pump_trade_evidence(&replay).unwrap());
    assert_eq!(
        db.pump_trade_evidence_for_signature(&first.signature)
            .unwrap(),
        vec![first.clone()]
    );

    let mut conflict = replay;
    conflict.sol_amount_raw += 1;
    assert!(matches!(
        db.record_pump_trade_evidence(&conflict),
        Err(StorageError::InvalidData(_))
    ));

    cleanup_dir(&root);
}

#[test]
fn pumpswap_replay_on_new_fork_slot_preserves_first_provenance_when_economics_match() {
    let root = unique_test_dir("pumpswap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let first = pump_swap_trade();
    assert!(db.record_pump_swap_trade_evidence(&first).unwrap());

    let mut replay = first.clone();
    replay.provider = ProviderId::Chainstack;
    replay.slot = 202;
    replay.observed_at_unix_ms = 2_500;

    assert!(!db.record_pump_swap_trade_evidence(&replay).unwrap());
    assert_eq!(
        db.pump_swap_trade_evidence_for_signature(&first.signature)
            .unwrap(),
        vec![first.clone()]
    );

    let mut conflict = replay;
    conflict.quote_amount_raw += 1;
    assert!(matches!(
        db.record_pump_swap_trade_evidence(&conflict),
        Err(StorageError::InvalidData(_))
    ));

    cleanup_dir(&root);
}
