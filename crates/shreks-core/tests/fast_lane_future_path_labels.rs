use shreks_core::{
    label_future_paths, FastEvent, FastEventId, FastEventKind, FastMarketKey, FuturePathCompleteness,
    FuturePathCoverage, FuturePathDecision, FuturePathObservation, ProviderId, VenueId,
    FUTURE_PATH_LABEL_VERSION,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn market() -> FastMarketKey {
    FastMarketKey::new("mint-fl4", WSOL, VenueId::PumpFunBondingCurve).unwrap()
}

fn event(sequence: u64, ordinal: u32, occurred_at: i64, observed_at: i64, price: f64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(format!("sig-{sequence}"), ordinal).unwrap(),
        sequence,
        ProviderId::SolanaPublic,
        market(),
        FastEventKind::Buy,
        Some(format!("actor-{sequence}")),
        10_000 + sequence,
        occurred_at,
        observed_at,
        1.0,
        price,
        price,
    )
    .unwrap()
}

#[test]
fn labels_use_canonical_observation_clock_and_exact_horizon_boundaries() {
    let decision = FuturePathDecision::new(
        market(),
        FastEventId::new("decision-sig", 0).unwrap(),
        10,
        1_000,
        10.0,
    )
    .unwrap()
    .with_entry_total_quote(10.5)
    .unwrap();

    let observations = vec![
        // Occurred before the decision but became knowable only after it.
        FuturePathObservation::from_event(event(11, 0, 900, 1_100, 12.0))
            .with_route_available(true)
            .with_exit_capacity_base(8.0)
            .unwrap()
            .with_executable_exit_net_quote(11.0)
            .unwrap(),
        FuturePathObservation::from_event(event(12, 0, 1_200, 1_250, 8.0))
            .with_route_available(false)
            .with_exit_capacity_base(6.0)
            .unwrap()
            .with_executable_exit_net_quote(8.4)
            .unwrap(),
        FuturePathObservation::from_event(event(13, 0, 1_300, 1_500, 11.0))
            .with_route_available(true)
            .with_exit_capacity_base(7.0)
            .unwrap()
            .with_executable_exit_net_quote(11.55)
            .unwrap(),
        // Strictly outside the 500ms horizon.
        FuturePathObservation::from_event(event(14, 0, 1_400, 1_501, 20.0)),
    ];

    let labels = label_future_paths(
        &decision,
        &observations,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &[250, 500],
    )
    .unwrap();

    assert_eq!(labels.len(), 2);

    let h250 = &labels[0];
    assert_eq!(h250.version, FUTURE_PATH_LABEL_VERSION);
    assert_eq!(h250.horizon_ms, 250);
    assert_eq!(h250.completeness, FuturePathCompleteness::Complete);
    assert_eq!(h250.event_count, 2);
    assert!(!h250.no_trade_events);
    assert_eq!(h250.endpoint_event_id.as_ref().unwrap().signature, "sig-12");
    assert_eq!(h250.endpoint_observed_at_unix_ms, Some(1_250));
    assert!((h250.endpoint_return_bps.unwrap() - -2_000.0).abs() < 1e-9);
    assert!((h250.mfe_bps.unwrap() - 2_000.0).abs() < 1e-9);
    assert!((h250.mae_bps.unwrap() - -2_000.0).abs() < 1e-9);
    assert_eq!(h250.time_to_peak_ms, Some(100));
    assert_eq!(h250.time_to_trough_ms, Some(250));
    assert_eq!(h250.reversal_occurred, Some(true));
    assert_eq!(h250.first_reversal_after_ms, Some(250));
    assert_eq!(h250.min_exit_capacity_base, Some(6.0));
    assert_eq!(h250.endpoint_exit_capacity_base, Some(6.0));
    assert_eq!(h250.route_unavailability_observed, Some(true));
    assert!((h250.best_cost_adjusted_return_bps.unwrap() - (11.0 / 10.5 - 1.0) * 10_000.0).abs() < 1e-9);
    assert!((h250.endpoint_cost_adjusted_return_bps.unwrap() - (8.4 / 10.5 - 1.0) * 10_000.0).abs() < 1e-9);

    let h500 = &labels[1];
    assert_eq!(h500.event_count, 3);
    assert_eq!(h500.endpoint_event_id.as_ref().unwrap().signature, "sig-13");
    assert_eq!(h500.endpoint_observed_at_unix_ms, Some(1_500));
    assert!((h500.endpoint_return_bps.unwrap() - 1_000.0).abs() < 1e-9);
    assert_eq!(h500.endpoint_exit_capacity_base, Some(7.0));
    assert!((h500.best_cost_adjusted_return_bps.unwrap() - 1_000.0).abs() < 1e-9);
}

#[test]
fn complete_no_trade_and_incomplete_capture_are_not_conflated() {
    let decision = FuturePathDecision::new(
        market(),
        FastEventId::new("decision-empty", 0).unwrap(),
        20,
        5_000,
        2.0,
    )
    .unwrap();

    let complete = label_future_paths(
        &decision,
        &[],
        FuturePathCoverage::new(5_500, true).unwrap(),
        &[250, 500],
    )
    .unwrap();
    assert_eq!(complete[0].completeness, FuturePathCompleteness::Complete);
    assert!(complete[0].no_trade_events);
    assert_eq!(complete[0].endpoint_return_bps, None);
    assert_eq!(complete[1].completeness, FuturePathCompleteness::Complete);
    assert!(complete[1].no_trade_events);

    let incomplete = label_future_paths(
        &decision,
        &[],
        FuturePathCoverage::new(5_500, false).unwrap(),
        &[250, 500],
    )
    .unwrap();
    assert_eq!(incomplete[0].completeness, FuturePathCompleteness::Incomplete);
    assert!(!incomplete[0].no_trade_events);
    assert_eq!(incomplete[0].event_count, 0);
    assert_eq!(incomplete[0].endpoint_return_bps, None);
}

#[test]
fn malformed_future_inputs_fail_closed() {
    let decision = FuturePathDecision::new(
        market(),
        FastEventId::new("decision-invalid", 0).unwrap(),
        30,
        10_000,
        1.0,
    )
    .unwrap();

    let non_monotonic = vec![
        FuturePathObservation::from_event(event(32, 0, 10_010, 10_010, 1.1)),
        FuturePathObservation::from_event(event(31, 0, 10_020, 10_020, 1.2)),
    ];
    assert!(label_future_paths(
        &decision,
        &non_monotonic,
        FuturePathCoverage::new(11_000, true).unwrap(),
        &[250]
    )
    .is_err());

    assert!(label_future_paths(
        &decision,
        &[],
        FuturePathCoverage::new(11_000, true).unwrap(),
        &[500, 250]
    )
    .is_err());

    let wrong_market_event = FastEvent::new(
        FastEventId::new("wrong-market", 0).unwrap(),
        31,
        ProviderId::SolanaPublic,
        FastMarketKey::new("other-mint", WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Sell,
        None,
        99,
        10_100,
        10_100,
        1.0,
        1.0,
        1.0,
    )
    .unwrap();
    assert!(label_future_paths(
        &decision,
        &[FuturePathObservation::from_event(wrong_market_event)],
        FuturePathCoverage::new(11_000, true).unwrap(),
        &[250]
    )
    .is_err());
}
