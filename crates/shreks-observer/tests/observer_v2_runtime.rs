const OBSERVE_SOURCE: &str = include_str!("../src/bin/shreks-observe.rs");

#[test]
fn observe_binary_runs_v2_sampler_and_does_not_duplicate_public_discovery() {
    for required in [
        "HighResolutionSampler",
        "SamplerProvider",
        "SamplingPolicy::default_v1",
        "DexScreenerProvider",
        "MeteoraProvider",
        "restore_registry",
        "run_until_shutdown",
        "Observer::new",
        "HeliusProvider",
    ] {
        assert!(
            OBSERVE_SOURCE.contains(required),
            "shreks-observe must include Observer V2 runtime surface: {required}"
        );
    }

    assert!(
        !OBSERVE_SOURCE.contains("build_free_observer"),
        "legacy observer must not duplicate public discovery once V2 owns it"
    );
}

#[test]
fn lifecycle_observer_has_pump_only_market_evidence_without_v2_duplication() {
    let start = OBSERVE_SOURCE
        .find("fn build_lifecycle_observer")
        .expect("lifecycle observer builder must exist");
    let end = OBSERVE_SOURCE[start..]
        .find("fn build_high_resolution_sampler")
        .map(|offset| start + offset)
        .expect("V2 sampler builder must follow lifecycle observer builder");
    let builder = &OBSERVE_SOURCE[start..end];

    assert!(
        builder.contains("DexScreenerProvider::new()"),
        "verified Pump launches require DEX Screener market evidence in the lifecycle observer"
    );
    assert!(
        builder.contains("with_pump_market_provider"),
        "verified Pump launches must use the dedicated Pump-only market path"
    );
    assert!(
        !builder.contains("with_discovery_provider"),
        "lifecycle observer must not duplicate V2 public discovery"
    );
    assert!(
        !builder.contains(".with_market_provider"),
        "lifecycle observer must not attach a general market provider that duplicates V2 outcome sampling"
    );
}

#[test]
fn observe_v2_runtime_remains_observe_only() {
    for forbidden in [
        "TradeIntent",
        "QuoteProvider",
        "RuntimeMode::Live",
        "sign_transaction",
        "send_transaction",
        "submit_transaction",
    ] {
        assert!(
            !OBSERVE_SOURCE.contains(forbidden),
            "observe-only runtime unexpectedly contains forbidden authority: {forbidden}"
        );
    }
}
