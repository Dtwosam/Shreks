use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FuturePathCompleteness,
    FuturePathCoverage, FuturePathDecision, FuturePathLabel, ProviderId, VenueId,
    FUTURE_PATH_LABEL_VERSION,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-training-economics";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-training-economics-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw_trade(
    signature: &str,
    observed_at: i64,
    is_buy: bool,
    token_raw: u64,
    sol_raw: u64,
    real_token: u64,
) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 77,
        observed_at_unix_ms: observed_at,
        mint: MINT.to_owned(),
        quote_mint: WSOL.to_owned(),
        user: format!("wallet-{signature}"),
        is_buy,
        token_amount_raw: token_raw,
        sol_amount_raw: sol_raw,
        quote_amount_raw: 0,
        timestamp_unix_seconds: observed_at / 1_000,
        virtual_sol_reserves_raw: 10_000_000_000 + sol_raw,
        virtual_token_reserves_raw: 20_000_000_000 + token_raw,
        real_sol_reserves_raw: 5_000_000_000 + sol_raw,
        real_token_reserves_raw: real_token,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: if is_buy { "buy" } else { "sell" }.to_owned(),
    }
}

fn event(
    signature: &str,
    sequence: u64,
    observed_at: i64,
    kind: FastEventKind,
    price: f64,
    base: f64,
) -> FastEvent {
    let source_observed_at = observed_at - 20;
    let occurred_at_unix_ms = (source_observed_at / 1_000) * 1_000;
    FastEvent::new(
        FastEventId::new(signature, 0).unwrap(),
        sequence,
        ProviderId::Helius,
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        kind,
        Some(format!("wallet-{signature}")),
        77,
        occurred_at_unix_ms,
        observed_at,
        base,
        base * price,
        price,
    )
    .unwrap()
}

fn store_event(
    db: &ShreksDb,
    signature: &str,
    sequence: u64,
    observed_at: i64,
    kind: FastEventKind,
    price: f64,
    real_token: u64,
) {
    let is_buy = kind == FastEventKind::Buy;
    let sol_raw = (2.0 * price * 1_000_000_000.0).round() as u64;
    let raw = raw_trade(
        signature,
        observed_at - 20,
        is_buy,
        2_000_000,
        sol_raw,
        real_token,
    );
    db.record_pump_trade_evidence(&raw).unwrap();
    db.record_fast_event(
        &event(signature, sequence, observed_at, kind, price, 2.0),
        observed_at - 20,
        6,
        9,
    )
    .unwrap();
}

fn decision(
    signature: &str,
    sequence: u64,
    observed_at_unix_ms: i64,
    executable_entry_price_quote: f64,
) -> FuturePathDecision {
    FuturePathDecision::new(
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventId::new(signature, 0).unwrap(),
        sequence,
        observed_at_unix_ms,
        executable_entry_price_quote,
    )
    .unwrap()
    .with_entry_total_quote(executable_entry_price_quote * 2.05)
    .unwrap()
}

fn complete_label(
    horizon_ms: u64,
    endpoint_signature: &str,
    endpoint_observed_at_unix_ms: i64,
    endpoint_price_quote: f64,
) -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms,
        completeness: FuturePathCompleteness::Complete,
        event_count: 1,
        no_trade_events: false,
        endpoint_event_id: Some(FastEventId::new(endpoint_signature, 0).unwrap()),
        endpoint_observed_at_unix_ms: Some(endpoint_observed_at_unix_ms),
        endpoint_price_quote: Some(endpoint_price_quote),
        endpoint_return_bps: Some(181.8),
        mfe_bps: Some(250.0),
        mae_bps: Some(-30.0),
        time_to_peak_ms: Some(200),
        time_to_trough_ms: Some(50),
        reversal_occurred: Some(false),
        first_reversal_after_ms: None,
        min_exit_capacity_base: Some(8.0),
        endpoint_exit_capacity_base: Some(7.5),
        route_unavailability_observed: Some(false),
        best_cost_adjusted_return_bps: Some(120.0),
        endpoint_cost_adjusted_return_bps: Some(80.0),
    }
}

fn incomplete_label(horizon_ms: u64) -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms,
        completeness: FuturePathCompleteness::Incomplete,
        event_count: 0,
        no_trade_events: false,
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
    }
}

fn fixture(label: &str) -> (PathBuf, ShreksDb) {
    let root = unique_test_dir(label);
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    store_event(
        &db,
        "before",
        1,
        1_000,
        FastEventKind::Buy,
        0.050,
        12_000_000_000,
    );
    store_event(
        &db,
        "decision-a",
        2,
        1_100,
        FastEventKind::Buy,
        0.055,
        11_000_000_000,
    );
    store_event(
        &db,
        "future-a",
        3,
        1_300,
        FastEventKind::Sell,
        0.056,
        10_000_000_000,
    );
    store_event(
        &db,
        "decision-b",
        4,
        1_600,
        FastEventKind::Buy,
        0.060,
        9_000_000_000,
    );
    store_event(
        &db,
        "future-b",
        5,
        1_800,
        FastEventKind::Sell,
        0.058,
        8_000_000_000,
    );

    let decision_a = decision("decision-a", 2, 1_100, 0.055);
    db.record_future_path_label(
        &decision_a,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &complete_label(250, "future-a", 1_300, 0.056),
    )
    .unwrap();
    db.record_future_path_label(
        &decision_a,
        FuturePathCoverage::new(1_500, true).unwrap(),
        &incomplete_label(500),
    )
    .unwrap();

    let decision_b = decision("decision-b", 4, 1_600, 0.060);
    db.record_future_path_label(
        &decision_b,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &complete_label(250, "future-b", 1_800, 0.058),
    )
    .unwrap();
    db.record_future_path_label(
        &decision_b,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &incomplete_label(500),
    )
    .unwrap();

    (root, db)
}

#[test]
fn training_economics_overlay_has_exact_fl4_population() {
    let (root, db) = fixture("population");
    let features = db
        .fast_training_feature_records(FUTURE_PATH_LABEL_VERSION)
        .unwrap();

    let rows = db
        .fast_training_economics_overlay_rows(
            &features,
            FUTURE_PATH_LABEL_VERSION,
            "2",
            60_000,
        )
        .unwrap();

    assert_eq!(rows.len(), 4);
    assert!(rows.windows(2).all(|pair| {
        (
            pair[0].decision_sequence,
            pair[0].horizon_ms,
            pair[0].decision_signature.as_str(),
            pair[0].decision_ordinal,
        ) <= (
            pair[1].decision_sequence,
            pair[1].horizon_ms,
            pair[1].decision_signature.as_str(),
            pair[1].decision_ordinal,
        )
    }));
    assert_eq!(
        rows.iter()
            .map(|row| (
                row.decision_signature.as_str(),
                row.decision_ordinal,
                row.horizon_ms,
            ))
            .collect::<Vec<_>>(),
        vec![
            ("decision-a", 0, 250),
            ("decision-a", 0, 500),
            ("decision-b", 0, 250),
            ("decision-b", 0, 500),
        ]
    );

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn training_economics_overlay_rejects_feature_identity_drift() {
    let (root, db) = fixture("identity-drift");
    let mut features = db
        .fast_training_feature_records(FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    features[0].decision_sequence += 99;

    let error = db
        .fast_training_economics_overlay_rows(
            &features,
            FUTURE_PATH_LABEL_VERSION,
            "2",
            60_000,
        )
        .unwrap_err();

    assert!(error
        .to_string()
        .contains("training economics feature/FL4 decision identity mismatch"));

    drop(db);
    cleanup_dir(&root);
}
