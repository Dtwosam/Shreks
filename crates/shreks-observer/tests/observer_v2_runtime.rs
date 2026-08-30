const OBSERVE_SOURCE: &str = include_str!("../src/bin/shreks-observe.rs");
const RUNTIME_SOURCE: &str = include_str!("../src/runtime.rs");

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
        "StandardSolanaRpcProvider",
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
fn broad_http_builders_use_public_solana_without_paid_provider_fallback() {
    let runtime_start = RUNTIME_SOURCE
        .find("pub fn build_free_observer")
        .expect("library observer builder must exist");
    let runtime_end = RUNTIME_SOURCE[runtime_start..]
        .find("impl Observer")
        .map(|offset| runtime_start + offset)
        .expect("Observer implementation must follow library builder");
    let runtime_builder = &RUNTIME_SOURCE[runtime_start..runtime_end];

    let binary_start = OBSERVE_SOURCE
        .find("fn build_lifecycle_observer")
        .expect("production lifecycle observer builder must exist");
    let binary_end = OBSERVE_SOURCE[binary_start..]
        .find("fn build_high_resolution_sampler")
        .map(|offset| binary_start + offset)
        .expect("V2 sampler builder must follow lifecycle observer builder");
    let binary_builder = &OBSERVE_SOURCE[binary_start..binary_end];

    for (label, builder) in [
        ("library", runtime_builder),
        ("production", binary_builder),
    ] {
        assert!(
            builder.contains("StandardSolanaRpcProvider::solana_public()"),
            "{label} broad chain/transaction builder must use public Solana"
        );
        for forbidden in [
            "HeliusProvider::new",
            "StandardSolanaRpcProvider::chainstack",
            "observer_helius_max_requests_per_process",
            "with_request_budget",
        ] {
            assert!(
                !builder.contains(forbidden),
                "{label} broad chain/transaction builder must not activate paid provider path: {forbidden}"
            );
        }
    }
}

#[test]
fn production_uses_one_bounded_public_realtime_source_and_the_durable_writer() {
    for required in [
        "BoundedPumpRealtimeFailoverStream",
        "BoundedPumpRealtimeLogStreamConfig",
        "build_pump_realtime_configs",
        "BoundedPumpRealtimeLogStreamConfig::solana_public",
        "refresh_pumpswap_realtime_targets_now",
        "run_pumpswap_realtime_target_publisher",
        "forward_pump_realtime_signals",
        "Observer::run_pump_realtime_writer",
        "PUMP_REALTIME_CHANNEL_CAPACITY",
    ] {
        assert!(
            OBSERVE_SOURCE.contains(required),
            "production observer must wire the bounded Pump realtime evidence path: {required}"
        );
    }

    assert_eq!(
        OBSERVE_SOURCE
            .matches("BoundedPumpRealtimeFailoverStream::new")
            .count(),
        1,
        "production must create exactly one bounded Pump realtime source"
    );

    let start = OBSERVE_SOURCE
        .find("fn build_pump_realtime_configs")
        .expect("realtime config builder must exist");
    let end = OBSERVE_SOURCE[start..]
        .find("fn build_lifecycle_observer")
        .map(|offset| start + offset)
        .expect("lifecycle builder must follow realtime config builder");
    let builder = &OBSERVE_SOURCE[start..end];
    assert!(
        builder.contains("BoundedPumpRealtimeLogStreamConfig::solana_public()"),
        "production broad realtime must be public Solana"
    );
    for forbidden in [
        "BoundedPumpRealtimeLogStreamConfig::helius",
        "BoundedPumpRealtimeLogStreamConfig::chainstack",
        "BoundedPumpRealtimeLogStreamConfig::alchemy",
        "PumpLogStream::new",
        "PumpLogStreamConfig::helius",
        "forward_pump_signals",
        "with_pump_signal_receiver",
        "PUMP_AMM_PROGRAM_ID",
    ] {
        assert!(
            !builder.contains(forbidden),
            "production must not retain a paid or unbounded Pump websocket path: {forbidden}"
        );
    }
}

#[test]
fn realtime_forwarder_writer_and_target_publisher_termination_are_fail_closed_and_supervised() {
    for required in [
        "run_observation_with_realtime",
        "tokio::spawn(forward_pump_realtime_signals(stream, sender))",
        "forwarder_result = &mut forwarder",
        "Pump realtime forwarder stopped unexpectedly",
        "target_publisher_result = &mut target_publisher",
        "PumpSwap realtime target publisher stopped unexpectedly",
        "writer_result = &mut writer",
        "Pump realtime writer stopped unexpectedly",
        "forwarder.abort()",
        "target_publisher.abort()",
    ] {
        assert!(
            OBSERVE_SOURCE.contains(required),
            "production must supervise realtime evidence fail-closed: {required}"
        );
    }

    assert!(
        !OBSERVE_SOURCE.contains("Some(writer.await)"),
        "realtime writer must be monitored during runtime, not only checked at process shutdown"
    );
}

#[test]
fn fast_event_normalizer_is_bounded_periodic_and_fail_closed_supervised() {
    for required in [
        "fast_event_normalizer",
        "normalize_pending_pump_trade_evidence_at",
        "FAST_EVENT_NORMALIZER_BATCH_LIMIT",
        "FAST_EVENT_NORMALIZER_INTERVAL",
        "run_fast_event_normalizer",
        "normalizer_result = &mut normalizer",
        "FastEvent normalizer stopped unexpectedly",
    ] {
        assert!(
            OBSERVE_SOURCE.contains(required),
            "production must supervise canonical FastEvent normalization: {required}"
        );
    }

    assert!(
        OBSERVE_SOURCE.contains("ShreksDb::open(&runtime.db_path)?"),
        "normalizer must use its own restart-safe WAL connection"
    );
    assert!(
        !OBSERVE_SOURCE.contains("spawn_blocking"),
        "bounded normalizer must not create an unbounded blocking-task fanout"
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
