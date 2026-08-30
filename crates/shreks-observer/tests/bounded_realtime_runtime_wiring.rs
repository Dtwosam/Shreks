const OBSERVE_SOURCE: &str = include_str!("../src/bin/shreks-observe.rs");

#[test]
fn production_wires_bounded_realtime_scope_and_supervises_target_publisher() {
    for required in [
        "mod realtime_targets",
        "mod realtime_target_publisher",
        "BoundedPumpRealtimeLogStreamConfig",
        "BoundedPumpRealtimeFailoverStream",
        "refresh_pumpswap_realtime_targets_now",
        "run_pumpswap_realtime_target_publisher",
        "pumpswap_tracking_max_age",
        "pumpswap_max_tracked_pools",
        "target_publisher_result = &mut target_publisher",
        "PumpSwap realtime target publisher stopped unexpectedly",
    ] {
        assert!(
            OBSERVE_SOURCE.contains(required),
            "production bounded realtime runtime is missing: {required}"
        );
    }

    assert_eq!(
        OBSERVE_SOURCE
            .matches("BoundedPumpRealtimeFailoverStream::new")
            .count(),
        1,
        "production must create exactly one bounded realtime source"
    );
    assert!(
        !OBSERVE_SOURCE.contains("PUMP_AMM_PROGRAM_ID"),
        "production runtime must never restore the global PumpSwap AMM subscription"
    );
}

#[test]
fn production_realtime_uses_exactly_one_public_solana_source_without_paid_fallback() {
    let start = OBSERVE_SOURCE
        .find("fn build_pump_realtime_configs")
        .expect("bounded realtime config builder must exist");
    let end = OBSERVE_SOURCE[start..]
        .find("fn build_lifecycle_observer")
        .map(|offset| start + offset)
        .expect("lifecycle builder must follow realtime config builder");
    let builder = &OBSERVE_SOURCE[start..end];

    assert!(
        builder.contains("BoundedPumpRealtimeLogStreamConfig::solana_public()"),
        "broad production realtime must use the official public Solana websocket"
    );
    assert_eq!(
        builder
            .matches("BoundedPumpRealtimeLogStreamConfig::solana_public()")
            .count(),
        1,
        "production must configure exactly one public Solana broad realtime source"
    );
    for forbidden in [
        "BoundedPumpRealtimeLogStreamConfig::helius",
        "BoundedPumpRealtimeLogStreamConfig::chainstack",
        "BoundedPumpRealtimeLogStreamConfig::alchemy",
    ] {
        assert!(
            !builder.contains(forbidden),
            "paid broad realtime fallback must remain disabled: {forbidden}"
        );
    }
}
