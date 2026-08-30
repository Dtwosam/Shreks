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
        "production must create exactly one bounded ordered realtime failover source"
    );
    assert!(
        !OBSERVE_SOURCE.contains("PUMP_AMM_PROGRAM_ID"),
        "production runtime must never restore the global PumpSwap AMM subscription"
    );
}

#[test]
fn bounded_realtime_provider_order_remains_helius_chainstack_alchemy() {
    let start = OBSERVE_SOURCE
        .find("fn build_pump_realtime_configs")
        .expect("bounded realtime config builder must exist");
    let end = OBSERVE_SOURCE[start..]
        .find("fn build_lifecycle_observer")
        .map(|offset| start + offset)
        .expect("lifecycle builder must follow realtime config builder");
    let builder = &OBSERVE_SOURCE[start..end];

    let helius = builder
        .find("BoundedPumpRealtimeLogStreamConfig::helius")
        .expect("Helius bounded realtime config must be present");
    let chainstack = builder
        .find("BoundedPumpRealtimeLogStreamConfig::chainstack")
        .expect("Chainstack bounded realtime config must be present");
    let alchemy = builder
        .find("BoundedPumpRealtimeLogStreamConfig::alchemy")
        .expect("Alchemy bounded realtime config must be present");

    assert!(
        helius < chainstack && chainstack < alchemy,
        "bounded production provider order must remain Helius -> Chainstack -> Alchemy"
    );
}
