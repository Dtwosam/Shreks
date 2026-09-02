use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapExecutionEconomicsWrite, PumpSwapTradeEvidenceWrite,
    PumpTradeEvidenceWrite, PumpTradeExecutionEconomicsWrite, ShreksDb,
};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fl3-execution-economics-source-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn pump_raw(signature: &str) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 55,
        observed_at_unix_ms: 1_100,
        mint: "mint-a".to_owned(),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        token_amount_raw: 2_000_000,
        sol_amount_raw: 100_000_000,
        quote_amount_raw: 0,
        timestamp_unix_seconds: 1,
        virtual_sol_reserves_raw: 10_000_000_000,
        virtual_token_reserves_raw: 20_000_000_000,
        real_sol_reserves_raw: 5_000_000_000,
        real_token_reserves_raw: 10_000_000_000,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: "buy".to_owned(),
    }
}

fn pumpswap_raw(signature: &str, log_index: u32) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms: 1_100,
        pool: "pool-a".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_535_000_000,
        timestamp_unix_seconds: 1,
        pool_base_reserves_raw: 9_500_000_000,
        pool_quote_reserves_raw: 52_500_000_000,
    }
}

#[test]
fn pump_fee_evidence_round_trips_from_immutable_source_identity() {
    let root = unique_test_dir("pump");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 15);

    let raw = pump_raw("pump-fees");
    db.record_pump_trade_evidence(&raw).unwrap();
    assert!(db
        .pump_trade_execution_economics("pump-fees", 0)
        .unwrap()
        .is_none());

    let economics = PumpTradeExecutionEconomicsWrite {
        signature: "pump-fees".to_owned(),
        ordinal: 0,
        fee_recipient: "fee-recipient".to_owned(),
        fee_basis_points: 95,
        fee_raw: 23_750_000,
        creator: "creator".to_owned(),
        creator_fee_basis_points: 30,
        creator_fee_raw: 7_500_000,
        cashback_fee_basis_points: 5,
        cashback_raw: 1_250_000,
        buyback_fee_basis_points: 7,
        buyback_fee_raw: 1_750_000,
    };
    assert!(db
        .record_pump_trade_execution_economics(&economics)
        .unwrap());
    assert!(!db
        .record_pump_trade_execution_economics(&economics)
        .unwrap());
    assert_eq!(
        db.pump_trade_execution_economics("pump-fees", 0)
            .unwrap()
            .unwrap(),
        economics
    );

    let mut conflict = economics.clone();
    conflict.fee_raw += 1;
    assert!(db.record_pump_trade_execution_economics(&conflict).is_err());
    cleanup_dir(&root);
}

#[test]
fn pumpswap_fee_evidence_preserves_stable_fees_and_optional_current_suffix() {
    let root = unique_test_dir("pumpswap");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let raw = pumpswap_raw("pumpswap-fees", 7);
    let ordinal = raw.ordinal;
    db.record_pump_swap_trade_evidence(&raw).unwrap();

    let economics = PumpSwapExecutionEconomicsWrite {
        signature: "pumpswap-fees".to_owned(),
        ordinal,
        lp_fee_basis_points: 20,
        lp_fee_raw: 5_000_000,
        protocol_fee_basis_points: 93,
        protocol_fee_raw: 23_250_000,
        quote_amount_with_or_without_lp_fee_raw: 2_505_000_000,
        coin_creator: Some("creator".to_owned()),
        coin_creator_fee_basis_points: Some(30),
        coin_creator_fee_raw: Some(7_500_000),
        cashback_fee_basis_points: Some(5),
        cashback_raw: Some(1_250_000),
        buyback_fee_basis_points: Some(7),
        buyback_fee_raw: Some(1_750_000),
        virtual_quote_reserves_raw: Some(4_000_000_000_i128),
        can_boost: Some(true),
        base_supply_raw: Some(1_000_000_000_000_000),
    };
    assert!(db.record_pump_swap_execution_economics(&economics).unwrap());
    assert_eq!(
        db.pump_swap_execution_economics("pumpswap-fees", ordinal)
            .unwrap()
            .unwrap(),
        economics
    );

    let legacy = pumpswap_raw("pumpswap-legacy", 8);
    db.record_pump_swap_trade_evidence(&legacy).unwrap();
    let legacy_economics = PumpSwapExecutionEconomicsWrite {
        signature: legacy.signature.clone(),
        ordinal: legacy.ordinal,
        lp_fee_basis_points: 20,
        lp_fee_raw: 5_000_000,
        protocol_fee_basis_points: 93,
        protocol_fee_raw: 23_250_000,
        quote_amount_with_or_without_lp_fee_raw: 2_505_000_000,
        coin_creator: None,
        coin_creator_fee_basis_points: None,
        coin_creator_fee_raw: None,
        cashback_fee_basis_points: None,
        cashback_raw: None,
        buyback_fee_basis_points: None,
        buyback_fee_raw: None,
        virtual_quote_reserves_raw: None,
        can_boost: None,
        base_supply_raw: None,
    };
    db.record_pump_swap_execution_economics(&legacy_economics)
        .unwrap();
    assert_eq!(
        db.pump_swap_execution_economics(&legacy.signature, legacy.ordinal)
            .unwrap()
            .unwrap(),
        legacy_economics
    );
    cleanup_dir(&root);
}

#[test]
fn pumpswap_current_suffix_is_all_or_none() {
    let root = unique_test_dir("partial-suffix");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let raw = pumpswap_raw("partial-suffix", 7);
    let ordinal = raw.ordinal;
    db.record_pump_swap_trade_evidence(&raw).unwrap();

    let partial = PumpSwapExecutionEconomicsWrite {
        signature: "partial-suffix".to_owned(),
        ordinal,
        lp_fee_basis_points: 20,
        lp_fee_raw: 5_000_000,
        protocol_fee_basis_points: 93,
        protocol_fee_raw: 23_250_000,
        quote_amount_with_or_without_lp_fee_raw: 2_505_000_000,
        coin_creator: Some("creator".to_owned()),
        coin_creator_fee_basis_points: None,
        coin_creator_fee_raw: None,
        cashback_fee_basis_points: None,
        cashback_raw: None,
        buyback_fee_basis_points: None,
        buyback_fee_raw: None,
        virtual_quote_reserves_raw: None,
        can_boost: None,
        base_supply_raw: None,
    };
    assert!(db.record_pump_swap_execution_economics(&partial).is_err());
    cleanup_dir(&root);
}
