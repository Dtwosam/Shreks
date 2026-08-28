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
fn production_uses_one_realtime_failover_source_and_the_durable_writer() {
    for required in [
        "PumpRealtimeFailoverStream",
        "PumpRealtimeLogStreamConfig",
        "build_pump_realtime_configs",
        "PumpRealtimeLogStreamConfig::helius",
        "PumpRealtimeLogStreamConfig::alchemy",
        "forward_pump_realtime_signals",
        "Observer::run_pump_realtime_writer",
        "PUMP_REALTIME_CHANNEL_CAPACITY",
    ] {
        assert!(
            OBSERVE_SOURCE.contains(required),
            "production observer must wire the Pump realtime evidence path: {required}"
        );
    }

    assert_eq!(
        OBSERVE_SOURCE
            .matches("PumpRealtimeFailoverStream::new")
            .count(),
        1,
        "production must create exactly one ordered Pump realtime failover source"
    );

    let start = OBSERVE_SOURCE
        .find("fn build_pump_realtime_configs")
        .expect("realtime config builder must exist");
    let end = OBSERVE_SOURCE[start..]
        .find("fn build_lifecycle_observer")
        .map(|offset| start + offset)
        .expect("lifecycle builder must follow realtime config builder");
    let builder = &OBSERVE_SOURCE[start..end];
    let helius = builder
        .find("PumpRealtimeLogStreamConfig::helius")
        .expect("Helius realtime config must be present");
    let alchemy = builder
        .find("PumpRealtimeLogStreamConfig::alchemy")
        .expect("Alchemy realtime config must be present");
    assert!(
        helius < alchemy,
        "Helius must remain primary and Alchemy must be the ordered fallback"
    );

    for forbidden in [
        "PumpLogStream::new",
        "PumpLogStreamConfig::helius",
        "forward_pump_signals",
        "with_pump_signal_receiver",
    ] {
        assert!(
            !OBSERVE_SOURCE.contains(forbidden),
            "production must not retain the lifecycle-only Pump websocket path: {forbidden}"
        );
    }
}

#[test]
fn realtime_writer_termination_is_fail_closed_and_supervised() {
    for required in [
        "run_observation_with_realtime",
        "writer_result = &mut writer",
        "Pump realtime writer stopped unexpectedly",
        "forwarder.abort()",
    ] {
        assert!(
            OBSERVE_SOURCE.contains(required),
            "production must supervise realtime durability fail-closed: {required}"
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
