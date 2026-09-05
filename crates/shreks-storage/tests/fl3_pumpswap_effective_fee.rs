use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_storage::{
    pump_swap_event_ordinal, EvidenceWriteOutcome, PumpSwapExecutionEconomicsWrite,
    PumpSwapTradeEvidenceWrite, ShreksDb, StorageError,
};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fl3-pumpswap-effective-fee-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn source(
    signature: &str,
    log_index: u32,
    is_buy: bool,
    market_quote_amount_raw: u64,
    user_quote_amount_raw: u64,
) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 700,
        observed_at_unix_ms: 20_000,
        pool: "pool-fee".to_owned(),
        user: "wallet-fee".to_owned(),
        is_buy,
        base_amount_raw: 500_000_000,
        quote_amount_raw: market_quote_amount_raw,
        user_quote_amount_raw,
        timestamp_unix_seconds: 20,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    }
}

#[test]
fn buy_and_sell_normalize_exact_user_market_fee_delta() {
    let root = unique_test_dir("exact");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let buy = source("fee-buy", 2, true, 2_500_000_000, 2_530_000_000);
    let sell = source("fee-sell", 4, false, 1_250_000_000, 1_235_000_000);
    assert!(db.record_pump_swap_trade_evidence(&buy).unwrap());
    assert!(db.record_pump_swap_trade_evidence(&sell).unwrap());

    let buy_fee = db
        .pump_swap_effective_fee_evidence(&buy.signature, buy.ordinal)
        .unwrap()
        .unwrap();
    assert_eq!(buy_fee.signature, buy.signature);
    assert_eq!(buy_fee.ordinal, buy.ordinal);
    assert!(buy_fee.is_buy);
    assert_eq!(buy_fee.market_quote_amount_raw, 2_500_000_000);
    assert_eq!(buy_fee.user_quote_amount_raw, 2_530_000_000);
    assert_eq!(buy_fee.signed_user_cost_quote_raw, 30_000_000);
    assert_eq!(buy_fee.effective_fee_bps, Some(120));

    let sell_fee = db
        .pump_swap_effective_fee_evidence(&sell.signature, sell.ordinal)
        .unwrap()
        .unwrap();
    assert!(!sell_fee.is_buy);
    assert_eq!(sell_fee.signed_user_cost_quote_raw, 15_000_000);
    assert_eq!(sell_fee.effective_fee_bps, Some(120));

    cleanup_dir(&root);
}

#[test]
fn non_integral_basis_points_remain_unknown_without_rounding() {
    let root = unique_test_dir("non-integral");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let raw = source("fee-non-integral", 6, true, 3, 4);
    assert!(db.record_pump_swap_trade_evidence(&raw).unwrap());

    let fee = db
        .pump_swap_effective_fee_evidence(&raw.signature, raw.ordinal)
        .unwrap()
        .unwrap();
    assert_eq!(fee.signed_user_cost_quote_raw, 1);
    assert_eq!(fee.effective_fee_bps, None);

    cleanup_dir(&root);
}

#[test]
fn net_user_benefit_stays_signed_and_does_not_become_negative_fee() {
    let root = unique_test_dir("rebate");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let raw = source("fee-rebate", 8, true, 100, 99);
    assert!(db.record_pump_swap_trade_evidence(&raw).unwrap());

    let fee = db
        .pump_swap_effective_fee_evidence(&raw.signature, raw.ordinal)
        .unwrap()
        .unwrap();
    assert_eq!(fee.signed_user_cost_quote_raw, -1);
    assert_eq!(fee.effective_fee_bps, None);

    cleanup_dir(&root);
}

#[test]
fn ambiguous_component_sidecar_does_not_override_user_market_delta() {
    let root = unique_test_dir("sidecar");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let raw = source("fee-sidecar", 10, true, 2_500_000_000, 2_530_000_000);
    assert!(db.record_pump_swap_trade_evidence(&raw).unwrap());
    assert!(db
        .record_pump_swap_execution_economics(&PumpSwapExecutionEconomicsWrite {
            signature: raw.signature.clone(),
            ordinal: raw.ordinal,
            lp_fee_basis_points: 500,
            lp_fee_raw: 125_000_000,
            protocol_fee_basis_points: 700,
            protocol_fee_raw: 175_000_000,
            quote_amount_with_or_without_lp_fee_raw: 2_625_000_000,
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
        })
        .unwrap());

    let fee = db
        .pump_swap_effective_fee_evidence(&raw.signature, raw.ordinal)
        .unwrap()
        .unwrap();
    assert_eq!(fee.signed_user_cost_quote_raw, 30_000_000);
    assert_eq!(fee.effective_fee_bps, Some(120));

    cleanup_dir(&root);
}

#[test]
fn conflict_quarantined_source_fails_closed_and_missing_source_is_none() {
    let root = unique_test_dir("conflict");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    assert!(db
        .pump_swap_effective_fee_evidence("missing-fee-source", pump_swap_event_ordinal(12).unwrap())
        .unwrap()
        .is_none());

    let first = source("fee-conflict", 14, false, 1_250_000_000, 1_235_000_000);
    assert_eq!(
        db.record_pump_swap_trade_evidence_or_quarantine(&first)
            .unwrap(),
        EvidenceWriteOutcome::Inserted
    );
    let mut conflict = first.clone();
    conflict.quote_amount_raw += 1;
    assert_eq!(
        db.record_pump_swap_trade_evidence_or_quarantine(&conflict)
            .unwrap(),
        EvidenceWriteOutcome::QuarantinedConflict
    );

    let error = db
        .pump_swap_effective_fee_evidence(&first.signature, first.ordinal)
        .unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));
    assert!(error.to_string().contains("conflict"));

    cleanup_dir(&root);
}
