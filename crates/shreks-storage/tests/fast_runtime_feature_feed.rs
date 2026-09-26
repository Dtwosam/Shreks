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
use shreks_storage::{
    FastRuntimeFeatureCursor, PumpTradeEvidenceWrite, ShreksDb,
    FAST_RUNTIME_FEATURE_BATCH_SCHEMA_NAME, FAST_RUNTIME_FEATURE_BATCH_SCHEMA_VERSION,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-runtime-feed";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-runtime-feed-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw_trade(signature: &str, observed_at: i64, price: f64) -> PumpTradeEvidenceWrite {
    let sol_raw = (2.0 * price * 1_000_000_000.0).round() as u64;
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 77,
        observed_at_unix_ms: observed_at - 20,
        mint: MINT.to_owned(),
        quote_mint: WSOL.to_owned(),
        user: format!("wallet-{signature}"),
        is_buy: true,
        token_amount_raw: 2_000_000,
        sol_amount_raw: sol_raw,
        quote_amount_raw: 0,
        timestamp_unix_seconds: (observed_at - 20) / 1_000,
        virtual_sol_reserves_raw: 10_000_000_000 + sol_raw,
        virtual_token_reserves_raw: 20_000_000_000 + 2_000_000,
        real_sol_reserves_raw: 5_000_000_000 + sol_raw,
        real_token_reserves_raw: 11_000_000_000,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: "buy".to_owned(),
    }
}

fn event(signature: &str, sequence: u64, observed_at: i64, price: f64) -> FastEvent {
    let source_observed_at = observed_at - 20;
    FastEvent::new(
        FastEventId::new(signature, 0).unwrap(),
        sequence,
        ProviderId::Helius,
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Buy,
        Some(format!("wallet-{signature}")),
        77,
        (source_observed_at / 1_000) * 1_000,
        observed_at,
        2.0,
        2.0 * price,
        price,
    )
    .unwrap()
}

fn store_event(db: &ShreksDb, signature: &str, sequence: u64, at: i64, price: f64) {
    db.record_pump_trade_evidence(&raw_trade(signature, at, price))
        .unwrap();
    db.record_fast_event(&event(signature, sequence, at, price), at - 20, 6, 9)
        .unwrap();
}

fn complete_label() -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms: 250,
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
    }
}

#[test]
fn runtime_feed_reads_unlabeled_events_in_bounded_cursor_order() {
    let root = unique_test_dir("unlabeled");
    fs::create_dir_all(&root).unwrap();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    store_event(&db, "event-a", 1, 1_000, 0.050);
    store_event(&db, "event-b", 2, 1_100, 0.055);
    drop(db);

    let db = ShreksDb::open_existing_read_only(&db_path).unwrap();
    let first = db.fast_runtime_feature_batch(None, 1).unwrap();
    assert_eq!(first.schema_name, FAST_RUNTIME_FEATURE_BATCH_SCHEMA_NAME);
    assert_eq!(first.schema_version, FAST_RUNTIME_FEATURE_BATCH_SCHEMA_VERSION);
    assert_eq!(first.snapshot_max_sequence, 2);
    assert_eq!(first.records.len(), 1);
    assert_eq!(first.records[0].decision_signature, "event-a");
    assert_eq!(first.records[0].decision_sequence, 1);
    assert_eq!(first.records[0].decision_entry_total_quote, None);

    let cursor = FastRuntimeFeatureCursor {
        decision_sequence: 1,
        decision_signature: "event-a".to_owned(),
        decision_ordinal: 0,
        decision_observed_at_unix_ms: 1_000,
    };
    let second = db.fast_runtime_feature_batch(Some(&cursor), 10).unwrap();
    assert_eq!(second.snapshot_max_sequence, 2);
    assert_eq!(second.records.len(), 1);
    assert_eq!(second.records[0].decision_signature, "event-b");
    assert_eq!(second.records[0].decision_sequence, 2);

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn runtime_feed_cursor_must_authenticate_exact_stored_event() {
    let root = unique_test_dir("cursor");
    fs::create_dir_all(&root).unwrap();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    store_event(&db, "event-a", 1, 1_000, 0.050);
    drop(db);

    let db = ShreksDb::open_existing_read_only(&db_path).unwrap();
    let bad = FastRuntimeFeatureCursor {
        decision_sequence: 1,
        decision_signature: "wrong-signature".to_owned(),
        decision_ordinal: 0,
        decision_observed_at_unix_ms: 1_000,
    };
    let error = db.fast_runtime_feature_batch(Some(&bad), 10).unwrap_err();
    assert!(error.to_string().contains("cursor"));
    drop(db);
    cleanup_dir(&root);
}

#[test]
fn runtime_and_training_paths_share_exact_feature_construction() {
    let root = unique_test_dir("parity");
    fs::create_dir_all(&root).unwrap();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    store_event(&db, "event-a", 1, 1_000, 0.050);

    let decision = FuturePathDecision::new(
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventId::new("event-a", 0).unwrap(),
        1,
        1_000,
        0.050,
    )
    .unwrap();
    db.record_future_path_label(
        &decision,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &complete_label(),
    )
    .unwrap();
    drop(db);

    let db = ShreksDb::open_existing_read_only(&db_path).unwrap();
    let training = db
        .fast_training_feature_records(FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    let runtime = db.fast_runtime_feature_batch(None, 10).unwrap();
    assert_eq!(training, runtime.records);

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn runtime_feed_rejects_zero_batch_limit() {
    let root = unique_test_dir("zero");
    fs::create_dir_all(&root).unwrap();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    drop(db);
    let db = ShreksDb::open_existing_read_only(&db_path).unwrap();
    assert!(db.fast_runtime_feature_batch(None, 0).is_err());
    drop(db);
    cleanup_dir(&root);
}
