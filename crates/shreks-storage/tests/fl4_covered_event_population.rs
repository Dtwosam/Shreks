use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FuturePathCompleteness,
    FuturePathCoverage, FuturePathDecision, ProviderId, VenueId,
    DEFAULT_FUTURE_PATH_HORIZONS_MS, FUTURE_PATH_LABEL_VERSION,
};
use shreks_storage::{
    populate_fast_future_path_labels, FastCoveredFuturePathPopulationRequest,
    PumpTradeEvidenceWrite, ShreksDb, FAST_COVERED_FUTURE_PATH_POPULATION_SCHEMA_NAME,
    FAST_COVERED_FUTURE_PATH_POPULATION_SCHEMA_VERSION,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-fl4-population";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fl4-covered-population-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw_trade(signature: &str, source_observed_at: i64, price_quote: f64) -> PumpTradeEvidenceWrite {
    let sol_amount_raw = (2.0 * price_quote * 1_000_000_000.0).round() as u64;
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 55,
        observed_at_unix_ms: source_observed_at,
        mint: MINT.to_owned(),
        quote_mint: WSOL.to_owned(),
        user: "wallet-fl4-population".to_owned(),
        is_buy: true,
        token_amount_raw: 2_000_000,
        sol_amount_raw,
        quote_amount_raw: sol_amount_raw,
        timestamp_unix_seconds: 1,
        virtual_sol_reserves_raw: 10_000_000_000,
        virtual_token_reserves_raw: 20_000_000_000,
        real_sol_reserves_raw: 5_000_000_000,
        real_token_reserves_raw: 10_000_000_000,
        virtual_quote_reserves_raw: 10_000_000_000,
        real_quote_reserves_raw: 5_000_000_000,
        ix_name: "buy".to_owned(),
    }
}

fn event(signature: &str, sequence: u64, observed_at: i64, price_quote: f64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, 0).unwrap(),
        sequence,
        ProviderId::SolanaPublic,
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Buy,
        Some("wallet-fl4-population".to_owned()),
        55,
        1_000,
        observed_at,
        2.0,
        2.0 * price_quote,
        price_quote,
    )
    .unwrap()
}

fn seed_event(db: &ShreksDb, signature: &str, sequence: u64, observed_at: i64, price: f64) {
    let source_observed_at = observed_at - 50;
    assert!(db
        .record_pump_trade_evidence(&raw_trade(signature, source_observed_at, price))
        .unwrap());
    assert!(db
        .record_fast_event(
            &event(signature, sequence, observed_at, price),
            source_observed_at,
            6,
            9,
        )
        .unwrap());
}

fn historical_coverage(db: &ShreksDb) -> (u64, u64) {
    let first = db
        .begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            1,
            900,
            54,
            "coverage-start",
        )
        .unwrap();
    let first = db
        .extend_fast_realtime_coverage_session(
            first.session_id,
            ProviderId::SolanaPublic,
            1,
            1_700,
            56,
            "coverage-end",
        )
        .unwrap();
    let latest = db
        .begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            2,
            1_800,
            57,
            "coverage-next",
        )
        .unwrap();
    (first.session_id, latest.session_id)
}

fn request(session_id: u64, maximum_decisions: u64) -> FastCoveredFuturePathPopulationRequest {
    FastCoveredFuturePathPopulationRequest {
        coverage_session_id: session_id,
        from_observed_at_unix_ms: 1_000,
        through_observed_at_unix_ms: 1_250,
        maximum_decisions,
    }
}

#[test]
fn covered_population_labels_every_canonical_event_in_the_explicit_window() {
    let root = unique_test_dir("population");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let (historical_session, _) = historical_coverage(&db);

    seed_event(&db, "decision-a", 1, 1_000, 0.05);
    seed_event(&db, "decision-b", 2, 1_250, 0.06);
    seed_event(&db, "future-c", 3, 1_600, 0.07);

    let report = populate_fast_future_path_labels(&db, &request(historical_session, 2)).unwrap();

    assert_eq!(
        report.schema_name,
        FAST_COVERED_FUTURE_PATH_POPULATION_SCHEMA_NAME
    );
    assert_eq!(
        report.schema_version,
        FAST_COVERED_FUTURE_PATH_POPULATION_SCHEMA_VERSION
    );
    assert_eq!(report.future_path_label_version, FUTURE_PATH_LABEL_VERSION);
    assert_eq!(report.coverage_session_id, historical_session);
    assert_eq!(report.coverage_provider, "solana_public");
    assert_eq!(report.from_observed_at_unix_ms, 1_000);
    assert_eq!(report.through_observed_at_unix_ms, 1_250);
    assert_eq!(report.coverage_complete_through_unix_ms, 1_700);
    assert_eq!(report.decision_count, 2);
    assert_eq!(report.inserted_label_count, 24);
    assert_eq!(report.already_existing_label_count, 0);
    assert_eq!(report.min_decision_sequence, 1);
    assert_eq!(report.max_decision_sequence, 2);
    assert_eq!(
        report.horizons_ms,
        DEFAULT_FUTURE_PATH_HORIZONS_MS.to_vec()
    );

    let first = db
        .future_path_labels_for_decision("decision-a", 0, FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    assert_eq!(first.len(), DEFAULT_FUTURE_PATH_HORIZONS_MS.len());
    assert!(first.iter().all(|row| row.decision.entry_total_quote.is_none()));
    assert!(first.iter().all(|row| row.coverage.contiguous));
    assert!(first
        .iter()
        .all(|row| row.coverage.complete_through_unix_ms == 1_700));
    assert_eq!(first[0].label.horizon_ms, 250);
    assert_eq!(first[0].label.completeness, FuturePathCompleteness::Complete);
    assert_eq!(first[1].label.horizon_ms, 500);
    assert_eq!(first[1].label.completeness, FuturePathCompleteness::Complete);
    assert_eq!(first[2].label.horizon_ms, 1_000);
    assert_eq!(first[2].label.completeness, FuturePathCompleteness::Incomplete);
    assert!(first.iter().all(|row| row.label.min_exit_capacity_base.is_none()));
    assert!(first
        .iter()
        .all(|row| row.label.route_unavailability_observed.is_none()));
    assert!(first
        .iter()
        .all(|row| row.label.endpoint_cost_adjusted_return_bps.is_none()));

    let second = db
        .future_path_labels_for_decision("decision-b", 0, FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    assert_eq!(second[0].label.completeness, FuturePathCompleteness::Complete);
    assert_eq!(second[1].label.completeness, FuturePathCompleteness::Incomplete);

    let rerun = populate_fast_future_path_labels(&db, &request(historical_session, 2)).unwrap();
    assert_eq!(rerun.decision_count, 2);
    assert_eq!(rerun.inserted_label_count, 0);
    assert_eq!(rerun.already_existing_label_count, 24);

    cleanup_dir(&root);
}

#[test]
fn covered_population_rejects_latest_mutable_session() {
    let root = unique_test_dir("latest");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let (_, latest_session) = historical_coverage(&db);
    seed_event(&db, "decision-a", 1, 1_000, 0.05);

    let error = populate_fast_future_path_labels(&db, &request(latest_session, 2)).unwrap_err();
    assert!(error.to_string().contains("latest"));
    assert!(db
        .future_path_labels_for_decision("decision-a", 0, FUTURE_PATH_LABEL_VERSION)
        .unwrap()
        .is_empty());

    cleanup_dir(&root);
}

#[test]
fn covered_population_rejects_window_outside_session_or_above_explicit_cap() {
    let root = unique_test_dir("bounds");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let (historical_session, _) = historical_coverage(&db);
    seed_event(&db, "decision-a", 1, 1_000, 0.05);
    seed_event(&db, "decision-b", 2, 1_250, 0.06);

    let outside = FastCoveredFuturePathPopulationRequest {
        coverage_session_id: historical_session,
        from_observed_at_unix_ms: 800,
        through_observed_at_unix_ms: 1_250,
        maximum_decisions: 2,
    };
    let error = populate_fast_future_path_labels(&db, &outside).unwrap_err();
    assert!(error.to_string().contains("coverage session"));

    let error = populate_fast_future_path_labels(&db, &request(historical_session, 1)).unwrap_err();
    assert!(error.to_string().contains("maximum"));
    for signature in ["decision-a", "decision-b"] {
        assert!(db
            .future_path_labels_for_decision(signature, 0, FUTURE_PATH_LABEL_VERSION)
            .unwrap()
            .is_empty());
    }

    cleanup_dir(&root);
}

#[test]
fn covered_population_rejects_empty_window_before_writing() {
    let root = unique_test_dir("empty");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let (historical_session, _) = historical_coverage(&db);

    let error = populate_fast_future_path_labels(&db, &request(historical_session, 1)).unwrap_err();
    assert!(error.to_string().contains("no canonical FastEvents"));

    cleanup_dir(&root);
}

#[test]
fn covered_population_rolls_back_the_entire_invocation_on_label_conflict() {
    let root = unique_test_dir("rollback");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let (historical_session, _) = historical_coverage(&db);

    seed_event(&db, "decision-a", 1, 1_000, 0.05);
    seed_event(&db, "decision-b", 2, 1_250, 0.06);
    seed_event(&db, "future-c", 3, 1_600, 0.07);

    let decision_b = FuturePathDecision::new(
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventId::new("decision-b", 0).unwrap(),
        2,
        1_250,
        0.06,
    )
    .unwrap();
    let older_coverage = FuturePathCoverage::new(1_600, true).unwrap();
    let conflicting = db
        .generate_future_path_labels_for_decision(&decision_b, older_coverage, &[250])
        .unwrap();
    assert_eq!(conflicting.len(), 1);
    assert!(db
        .record_future_path_label(&decision_b, older_coverage, &conflicting[0])
        .unwrap());

    let error =
        populate_fast_future_path_labels(&db, &request(historical_session, 2)).unwrap_err();
    assert!(error.to_string().contains("conflicting future-path label"));

    assert!(
        db.future_path_labels_for_decision("decision-a", 0, FUTURE_PATH_LABEL_VERSION)
            .unwrap()
            .is_empty(),
        "first-decision inserts from the failed invocation must roll back"
    );
    let preserved = db
        .future_path_labels_for_decision("decision-b", 0, FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    assert_eq!(preserved.len(), 1);
    assert_eq!(preserved[0].coverage, older_coverage);
    assert_eq!(preserved[0].label.horizon_ms, 250);

    cleanup_dir(&root);
}
