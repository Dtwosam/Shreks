use std::{fs, path::{Path, PathBuf}, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FuturePathCompleteness, FuturePathCoverage,
    FuturePathDecision, FuturePathLabel, ProviderId, VenueId, FUTURE_PATH_LABEL_VERSION,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb, StorageError};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    std::env::temp_dir().join(format!("shreks-fl4-labels-{label}-{}-{nanos}", process::id()))
}

fn cleanup_dir(path: &Path) { let _ = fs::remove_dir_all(path); }

fn raw_trade(signature: &str, observed_at_unix_ms: i64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 55,
        observed_at_unix_ms,
        mint: "mint-fl4".to_owned(),
        quote_mint: WSOL.to_owned(),
        user: "wallet-fl4".to_owned(),
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

fn canonical_event(
    signature: &str,
    sequence: u64,
    observed_at_unix_ms: i64,
    price_quote: f64,
) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, 0).unwrap(),
        sequence,
        ProviderId::Helius,
        FastMarketKey::new("mint-fl4", WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Buy,
        Some("wallet-fl4".to_owned()),
        55,
        1_000,
        observed_at_unix_ms,
        2.0,
        2.0 * price_quote,
        price_quote,
    ).unwrap()
}

fn decision() -> FuturePathDecision {
    FuturePathDecision::new(
        FastMarketKey::new("mint-fl4", WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventId::new("decision-fl4", 0).unwrap(),
        1,
        1_000,
        0.05,
    ).unwrap().with_entry_total_quote(0.11).unwrap()
}

fn label() -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms: 250,
        completeness: FuturePathCompleteness::Complete,
        event_count: 1,
        no_trade_events: false,
        endpoint_event_id: Some(FastEventId::new("future-fl4", 0).unwrap()),
        endpoint_observed_at_unix_ms: Some(1_250),
        endpoint_price_quote: Some(0.06),
        endpoint_return_bps: Some(2_000.0),
        mfe_bps: Some(2_000.0),
        mae_bps: Some(0.0),
        time_to_peak_ms: Some(250),
        time_to_trough_ms: Some(0),
        reversal_occurred: Some(false),
        first_reversal_after_ms: None,
        min_exit_capacity_base: Some(8.0),
        endpoint_exit_capacity_base: Some(8.0),
        route_unavailability_observed: Some(false),
        best_cost_adjusted_return_bps: Some(500.0),
        endpoint_cost_adjusted_return_bps: Some(500.0),
    }
}

#[test]
fn fl4_labels_are_versioned_exact_idempotent_and_source_linked() {
    let root = unique_test_dir("roundtrip");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 16);

    let raw_decision = raw_trade("decision-fl4", 900);
    let raw_future = raw_trade("future-fl4", 1_100);
    assert!(db.record_pump_trade_evidence(&raw_decision).unwrap());
    assert!(db.record_pump_trade_evidence(&raw_future).unwrap());
    assert!(db.record_fast_event(&canonical_event("decision-fl4", 1, 1_000, 0.05), 900, 6, 9).unwrap());
    assert!(db.record_fast_event(&canonical_event("future-fl4", 2, 1_250, 0.06), 1_100, 6, 9).unwrap());

    let decision = decision();
    let coverage = FuturePathCoverage::new(1_500, true).unwrap();
    let original = label();
    assert!(db.record_future_path_label(&decision, coverage, &original).unwrap());
    assert!(!db.record_future_path_label(&decision, coverage, &original).unwrap());

    let stored = db
        .future_path_labels_for_decision("decision-fl4", 0, FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    assert_eq!(stored.len(), 1);
    assert_eq!(stored[0].decision, decision);
    assert_eq!(stored[0].coverage, coverage);
    assert_eq!(stored[0].label, original);

    let mut conflict = original.clone();
    conflict.endpoint_return_bps = Some(9_999.0);
    let error = db.record_future_path_label(&decision, coverage, &conflict).unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));

    cleanup_dir(&root);
}

#[test]
fn complete_no_trade_label_round_trips_with_nullable_path_metrics() {
    let root = unique_test_dir("nullable");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let raw_decision = raw_trade("decision-fl4", 900);
    assert!(db.record_pump_trade_evidence(&raw_decision).unwrap());
    assert!(db.record_fast_event(&canonical_event("decision-fl4", 1, 1_000, 0.05), 900, 6, 9).unwrap());

    let decision = decision();
    let coverage = FuturePathCoverage::new(2_000, true).unwrap();
    let no_trade = FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms: 500,
        completeness: FuturePathCompleteness::Complete,
        event_count: 0,
        no_trade_events: true,
        endpoint_event_id: None,
        endpoint_observed_at_unix_ms: None,
        endpoint_price_quote: None,
        endpoint_return_bps: None,
        mfe_bps: None,
        mae_bps: None,
        time_to_peak_ms: None,
        time_to_trough_ms: None,
        reversal_occurred: None,
        first_reversal_after_ms: None,
        min_exit_capacity_base: None,
        endpoint_exit_capacity_base: None,
        route_unavailability_observed: None,
        best_cost_adjusted_return_bps: None,
        endpoint_cost_adjusted_return_bps: None,
    };
    assert!(db.record_future_path_label(&decision, coverage, &no_trade).unwrap());
    let stored = db
        .future_path_labels_for_decision("decision-fl4", 0, FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    assert_eq!(stored[0].label, no_trade);

    cleanup_dir(&root);
}

#[test]
fn direct_label_persistence_rejects_decision_price_that_disagrees_with_canonical_event() {
    let root = unique_test_dir("decision-price-source");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let raw_decision = raw_trade("decision-fl4", 900);
    let raw_future = raw_trade("future-fl4", 1_100);
    assert!(db.record_pump_trade_evidence(&raw_decision).unwrap());
    assert!(db.record_pump_trade_evidence(&raw_future).unwrap());
    assert!(db.record_fast_event(&canonical_event("decision-fl4", 1, 1_000, 0.05), 900, 6, 9).unwrap());
    assert!(db.record_fast_event(&canonical_event("future-fl4", 2, 1_250, 0.06), 1_100, 6, 9).unwrap());

    let mismatched_decision = FuturePathDecision::new(
        FastMarketKey::new("mint-fl4", WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventId::new("decision-fl4", 0).unwrap(),
        1,
        1_000,
        0.051,
    )
    .unwrap()
    .with_entry_total_quote(0.11)
    .unwrap();
    let coverage = FuturePathCoverage::new(1_500, true).unwrap();

    let error = db
        .record_future_path_label(&mismatched_decision, coverage, &label())
        .unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));
    assert!(db
        .future_path_labels_for_decision("decision-fl4", 0, FUTURE_PATH_LABEL_VERSION)
        .unwrap()
        .is_empty());

    cleanup_dir(&root);
}
