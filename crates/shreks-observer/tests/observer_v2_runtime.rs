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
        "legacy observer must not duplicate public discovery/market calls once V2 owns them"
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
