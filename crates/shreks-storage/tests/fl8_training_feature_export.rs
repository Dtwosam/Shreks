use std::{fs, path::{Path, PathBuf}, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FuturePathCompleteness,
    FuturePathCoverage, FuturePathDecision, FuturePathLabel, LifecycleEventKind,
    ProviderId, TokenLifecycleEvent, VenueId, DEFAULT_FAST_WINDOWS_MS,
    FUTURE_PATH_LABEL_VERSION,
};
use shreks_storage::{
    FastTrainingReserveContext, PumpTradeEvidenceWrite, ShreksDb,
    FAST_TRAINING_FEATURE_SCHEMA_NAME, FAST_TRAINING_FEATURE_SCHEMA_VERSION,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-fl8-training";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    std::env::temp_dir().join(format!("shreks-fl8-training-{label}-{}-{nanos}", process::id()))
}

fn cleanup_dir(path: &Path) { let _ = fs::remove_dir_all(path); }

fn raw_trade(signature: &str, observed_at: i64, is_buy: bool, token_raw: u64, sol_raw: u64, real_token: u64) -> PumpTradeEvidenceWrite {
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

fn event(signature: &str, sequence: u64, observed_at: i64, kind: FastEventKind, price: f64, base: f64) -> FastEvent {
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
    ).unwrap()
}

fn store_event(db: &ShreksDb, signature: &str, sequence: u64, observed_at: i64, kind: FastEventKind, price: f64, real_token: u64) {
    let is_buy = kind == FastEventKind::Buy;
    let sol_raw = (2.0 * price * 1_000_000_000.0).round() as u64;
    let raw = raw_trade(signature, observed_at - 20, is_buy, 2_000_000, sol_raw, real_token);
    db.record_pump_trade_evidence(&raw).unwrap();
    db.record_fast_event(&event(signature, sequence, observed_at, kind, price, 2.0), observed_at - 20, 6, 9).unwrap();
}

fn decision(signature: &str, sequence: u64, observed_at: i64, price: f64) -> FuturePathDecision {
    FuturePathDecision::new(
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventId::new(signature, 0).unwrap(),
        sequence,
        observed_at,
        price,
    ).unwrap().with_entry_total_quote(price * 2.05).unwrap()
}

fn label(horizon_ms: u64, endpoint: Option<(&str, i64, f64)>, complete: bool) -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms,
        completeness: if complete { FuturePathCompleteness::Complete } else { FuturePathCompleteness::Incomplete },
        event_count: if endpoint.is_some() { 1 } else { 0 },
        no_trade_events: endpoint.is_none() && complete,
        endpoint_event_id: endpoint.map(|(signature, _, _)| FastEventId::new(signature, 0).unwrap()),
        endpoint_observed_at_unix_ms: endpoint.map(|(_, at, _)| at),
        endpoint_price_quote: endpoint.map(|(_, _, price)| price),
        endpoint_return_bps: endpoint.map(|_| 100.0),
        mfe_bps: endpoint.map(|_| 150.0),
        mae_bps: endpoint.map(|_| -25.0),
        time_to_peak_ms: endpoint.map(|_| 100),
        time_to_trough_ms: endpoint.map(|_| 50),
        reversal_occurred: endpoint.map(|_| false),
        first_reversal_after_ms: None,
        min_exit_capacity_base: None,
        endpoint_exit_capacity_base: None,
        route_unavailability_observed: None,
        best_cost_adjusted_return_bps: None,
        endpoint_cost_adjusted_return_bps: None,
    }
}

fn seed(root: &Path) -> PathBuf {
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    store_event(&db, "before", 1, 1_000, FastEventKind::Buy, 0.050, 12_000_000_000);
    store_event(&db, "decision", 2, 1_100, FastEventKind::Buy, 0.055, 11_000_000_000);
    store_event(&db, "future", 3, 1_300, FastEventKind::Sell, 0.056, 10_000_000_000);

    let d = decision("decision", 2, 1_100, 0.055);
    db.record_future_path_label(
        &d,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &label(250, Some(("future", 1_300, 0.056)), true),
    ).unwrap();
    db.record_future_path_label(
        &d,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &label(500, Some(("future", 1_300, 0.056)), true),
    ).unwrap();

    // A verified lifecycle event exists, but its detection clock is in the future
    // relative to the decision and must not enter the exported decision feature row.
    db.record_pump_migration_signal("graduation-future", 999, 1_150).unwrap();
    db.complete_pump_migration(
        "graduation-future",
        1_210,
        &[TokenLifecycleEvent {
            kind: LifecycleEventKind::PumpGraduation,
            provider: ProviderId::Helius,
            mint: MINT.to_owned(),
            quote_mint: WSOL.to_owned(),
            from_venue: VenueId::PumpFunBondingCurve,
            to_venue: VenueId::PumpSwap,
            pool_address: "pool-future".to_owned(),
            signature: "graduation-future".to_owned(),
            slot: 999,
            detected_at_unix_ms: 1_200,
            occurred_at_unix_ms: Some(1_050),
        }],
    ).unwrap();
    drop(db);
    db_path
}

#[test]
fn fl8_training_feature_schema_constants_are_stable() {
    assert_eq!(FAST_TRAINING_FEATURE_SCHEMA_NAME, "shreks.fast_lane_training_features");
    assert_eq!(FAST_TRAINING_FEATURE_SCHEMA_VERSION, 1);
}

#[test]
fn read_only_open_requires_existing_current_schema_and_cannot_write() {
    let root = unique_test_dir("readonly");
    fs::create_dir_all(&root).unwrap();
    let missing = root.join("missing.db");
    assert!(ShreksDb::open_existing_read_only(&missing).is_err());
    assert!(!missing.exists());

    let db_path = seed(&root);
    let db = ShreksDb::open_existing_read_only(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 17);
    assert!(db.record_pump_migration_signal("must-not-write", 1, 1).is_err());
    drop(db);
    cleanup_dir(&root);
}

#[test]
fn exporter_replays_only_the_decision_prefix_and_deduplicates_label_horizons() {
    let root = unique_test_dir("prefix");
    fs::create_dir_all(&root).unwrap();
    let db_path = seed(&root);
    let db = ShreksDb::open_existing_read_only(&db_path).unwrap();

    let rows = db.fast_training_feature_records(FUTURE_PATH_LABEL_VERSION).unwrap();
    assert_eq!(rows.len(), 1, "two FL4 horizons for one decision must produce one feature row");
    let row = &rows[0];
    assert_eq!(row.schema_name, FAST_TRAINING_FEATURE_SCHEMA_NAME);
    assert_eq!(row.schema_version, FAST_TRAINING_FEATURE_SCHEMA_VERSION);
    assert_eq!(row.decision_signature, "decision");
    assert_eq!(row.decision_ordinal, 0);
    assert_eq!(row.decision_sequence, 2);
    assert_eq!(row.decision_observed_at_unix_ms, 1_100);
    assert_eq!(row.snapshot_last_sequence, Some(2));
    assert_eq!(row.snapshot_last_price_quote, Some(0.055));
    assert!(row.last_lifecycle_event.is_none(), "future-detected lifecycle evidence leaked into decision features");

    assert_eq!(row.windows.iter().map(|value| value.window_ms).collect::<Vec<_>>(), DEFAULT_FAST_WINDOWS_MS);
    let window_250 = row.windows.iter().find(|value| value.window_ms == 250).unwrap();
    assert_eq!(window_250.buy_count, 2);
    assert_eq!(window_250.sell_count, 0, "future sell leaked into point-in-time feature window");
    assert_eq!(window_250.last_price_quote, Some(0.055));

    match &row.last_reserve_context {
        Some(FastTrainingReserveContext::PumpCurve { real_base_reserve_raw, .. }) => {
            assert_eq!(*real_base_reserve_raw, 11_000_000_000, "reserve context must come from decision source, not future source");
        }
        other => panic!("expected PumpCurve reserve context, got {other:?}"),
    }

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn exporter_is_deterministic_and_jsonl_is_immutable_by_default() {
    let root = unique_test_dir("deterministic");
    fs::create_dir_all(&root).unwrap();
    let db_path = seed(&root);
    let db = ShreksDb::open_existing_read_only(&db_path).unwrap();
    let first = root.join("first.jsonl");
    let second = root.join("second.jsonl");

    let first_manifest = db.write_fast_training_feature_jsonl(FUTURE_PATH_LABEL_VERSION, &first).unwrap();
    let second_manifest = db.write_fast_training_feature_jsonl(FUTURE_PATH_LABEL_VERSION, &second).unwrap();
    assert_eq!(first_manifest, second_manifest);
    assert_eq!(fs::read(&first).unwrap(), fs::read(&second).unwrap());
    assert_eq!(first_manifest.row_count, 1);
    assert_eq!(first_manifest.min_decision_sequence, 2);
    assert_eq!(first_manifest.max_decision_sequence, 2);
    assert_eq!(first_manifest.sha256.len(), 64);

    assert!(db.write_fast_training_feature_jsonl(FUTURE_PATH_LABEL_VERSION, &first).is_err(), "export must not overwrite an immutable source artifact");

    drop(db);
    cleanup_dir(&root);
}
