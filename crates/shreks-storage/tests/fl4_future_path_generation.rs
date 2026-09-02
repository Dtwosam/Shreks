use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FuturePathCompleteness,
    FuturePathCoverage, FuturePathDecision, ProviderId, VenueId,
};
use shreks_storage::{EvidenceWriteOutcome, PumpTradeEvidenceWrite, ShreksDb, StorageError};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fl4-generation-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn market() -> FastMarketKey {
    FastMarketKey::new("mint-fl4-generation", WSOL, VenueId::PumpFunBondingCurve).unwrap()
}

fn raw_trade(
    signature: &str,
    observed_at_unix_ms: i64,
    timestamp_unix_seconds: i64,
    sol_amount_raw: u64,
) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 77,
        observed_at_unix_ms,
        mint: market().mint,
        quote_mint: WSOL.to_owned(),
        user: "wallet-fl4-generation".to_owned(),
        is_buy: true,
        token_amount_raw: 2_000_000,
        sol_amount_raw,
        quote_amount_raw: 0,
        timestamp_unix_seconds,
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
    source: &PumpTradeEvidenceWrite,
    sequence: u64,
    observed_at_unix_ms: i64,
) -> FastEvent {
    let base_quantity = source.token_amount_raw as f64 / 1_000_000.0;
    let quote_quantity = source.sol_amount_raw as f64 / 1_000_000_000.0;
    FastEvent::new(
        FastEventId::new(source.signature.clone(), source.ordinal).unwrap(),
        sequence,
        source.provider,
        market(),
        FastEventKind::Buy,
        Some(source.user.clone()),
        source.slot,
        source.timestamp_unix_seconds * 1_000,
        observed_at_unix_ms,
        base_quantity,
        quote_quantity,
        quote_quantity / base_quantity,
    )
    .unwrap()
}

fn persist_event(
    db: &ShreksDb,
    source: &PumpTradeEvidenceWrite,
    sequence: u64,
    canonical_observed_at_unix_ms: i64,
) {
    assert!(db.record_pump_trade_evidence(source).unwrap());
    assert!(db
        .record_fast_event(
            &canonical_event(source, sequence, canonical_observed_at_unix_ms),
            source.observed_at_unix_ms,
            6,
            9,
        )
        .unwrap());
}

fn decision() -> FuturePathDecision {
    FuturePathDecision::new(
        market(),
        FastEventId::new("decision-fl4-generation", 0).unwrap(),
        1,
        1_000,
        0.05,
    )
    .unwrap()
}

#[test]
fn canonical_future_observations_use_observation_clock_and_exact_boundary() {
    let root = unique_test_dir("boundary");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let decision_source = raw_trade("decision-fl4-generation", 900, 1, 100_000_000);
    let late_arrival = raw_trade("late-fl4-generation", 1_050, 0, 80_000_000);
    let exact_boundary = raw_trade("boundary-fl4-generation", 1_150, 1, 120_000_000);
    let outside = raw_trade("outside-fl4-generation", 1_200, 1, 200_000_000);

    persist_event(&db, &decision_source, 1, 1_000);
    // This event occurred at 0ms, before the decision, but was not canonically
    // observable until 1_100ms. FL4 must treat it as future information.
    persist_event(&db, &late_arrival, 2, 1_100);
    persist_event(&db, &exact_boundary, 3, 1_250);
    persist_event(&db, &outside, 4, 1_251);

    let observations = db
        .future_path_observations_for_decision(&decision(), 1_250)
        .unwrap();
    assert_eq!(observations.len(), 2);
    assert_eq!(observations[0].event.id.signature, "late-fl4-generation");
    assert_eq!(observations[0].event.occurred_at_unix_ms, 0);
    assert_eq!(observations[0].event.observed_at_unix_ms, 1_100);
    assert_eq!(observations[1].event.id.signature, "boundary-fl4-generation");
    assert_eq!(observations[1].event.observed_at_unix_ms, 1_250);
    assert_eq!(observations[0].route_available, None);
    assert_eq!(observations[0].exit_capacity_base, None);
    assert_eq!(observations[0].executable_exit_net_quote, None);

    let labels = db
        .generate_future_path_labels_for_decision(
            &decision(),
            FuturePathCoverage::new(1_250, true).unwrap(),
            &[100, 250],
        )
        .unwrap();
    assert_eq!(labels.len(), 2);
    assert_eq!(labels[0].completeness, FuturePathCompleteness::Complete);
    assert_eq!(labels[0].event_count, 1);
    assert!((labels[0].endpoint_return_bps.unwrap() - -2_000.0).abs() < 1e-9);
    assert_eq!(labels[1].event_count, 2);
    assert_eq!(
        labels[1].endpoint_event_id.as_ref().unwrap().signature,
        "boundary-fl4-generation"
    );
    assert!((labels[1].endpoint_return_bps.unwrap() - 2_000.0).abs() < 1e-9);
    assert!((labels[1].mfe_bps.unwrap() - 2_000.0).abs() < 1e-9);
    assert!((labels[1].mae_bps.unwrap() - -2_000.0).abs() < 1e-9);

    cleanup_dir(&root);
}

#[test]
fn canonical_conflict_quarantine_blocks_future_path_generation() {
    let root = unique_test_dir("quarantine");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let decision_source = raw_trade("decision-fl4-generation", 900, 1, 100_000_000);
    let future_source = raw_trade("future-fl4-conflict", 1_050, 1, 120_000_000);
    persist_event(&db, &decision_source, 1, 1_000);
    persist_event(&db, &future_source, 2, 1_100);

    let mut conflicting_source = future_source.clone();
    conflicting_source.sol_amount_raw = 130_000_000;
    let outcome = db
        .record_pump_trade_evidence_or_quarantine(&conflicting_source)
        .unwrap();
    assert_eq!(outcome, EvidenceWriteOutcome::QuarantinedConflict);

    let error = db
        .future_path_observations_for_decision(&decision(), 1_250)
        .unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));

    cleanup_dir(&root);
}
