use std::{env, fs, path::PathBuf};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FuturePathCompleteness,
    FuturePathCoverage, FuturePathDecision, FuturePathLabel, LifecycleEventKind, ProviderId,
    TokenLifecycleEvent, VenueId, FUTURE_PATH_LABEL_VERSION,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-fl8-training";

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

#[test]
#[ignore = "invoked explicitly by the Python FL8.1 cross-language integration proof"]
fn write_fl8_python_integration_fixture() {
    let root = PathBuf::from(
        env::var("SHREKS_FL8_INTEGRATION_DIR")
            .expect("SHREKS_FL8_INTEGRATION_DIR must be set by the integration proof"),
    );
    assert!(!root.exists(), "integration fixture destination must be fresh");
    fs::create_dir_all(&root).unwrap();

    let database = root.join("shreks.db");
    let features = root.join("features.jsonl");
    let db = ShreksDb::open(&database).unwrap();

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

    // The same verified lifecycle event is future information for decision A and
    // historical information for decision B. That makes one fixture prove both
    // sides of the point-in-time boundary without inventing a second market.
    db.record_pump_migration_signal("graduation-between-decisions", 999, 1_350)
        .unwrap();
    db.complete_pump_migration(
        "graduation-between-decisions",
        1_410,
        &[TokenLifecycleEvent {
            kind: LifecycleEventKind::PumpGraduation,
            provider: ProviderId::Helius,
            mint: MINT.to_owned(),
            quote_mint: WSOL.to_owned(),
            from_venue: VenueId::PumpFunBondingCurve,
            to_venue: VenueId::PumpSwap,
            pool_address: "pool-between-decisions".to_owned(),
            signature: "graduation-between-decisions".to_owned(),
            slot: 999,
            detected_at_unix_ms: 1_400,
            occurred_at_unix_ms: Some(1_250),
        }],
    )
    .unwrap();

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

    let manifest = db
        .write_fast_training_feature_jsonl(FUTURE_PATH_LABEL_VERSION, &features)
        .unwrap();
    assert_eq!(manifest.row_count, 2);
    assert_eq!(manifest.min_decision_sequence, 2);
    assert_eq!(manifest.max_decision_sequence, 4);
    drop(db);

    assert!(database.is_file());
    assert!(features.is_file());
}
