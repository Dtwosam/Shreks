use shreks_core::ProviderId;
use shreks_providers::bounded_pump_realtime::BoundedPumpRealtimeLogStreamConfig;

#[test]
fn solana_public_realtime_constructor_is_bounded_and_redacts_official_endpoint() {
    let config = BoundedPumpRealtimeLogStreamConfig::solana_public()
        .expect("official Solana public websocket configuration must be valid");

    let debug = format!("{config:?}");
    assert!(debug.contains("SolanaPublic"));
    assert!(debug.contains("<redacted>"));
    assert!(!debug.contains("api.mainnet.solana.com"));
}

#[test]
fn solana_public_identity_is_allowed_through_local_bounded_stream_harness() {
    let config = BoundedPumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::SolanaPublic,
        "ws://127.0.0.1:9",
    )
    .expect("Solana public provider identity must be valid for the bounded realtime engine");

    let debug = format!("{config:?}");
    assert!(debug.contains("SolanaPublic"));
    assert!(!debug.contains("127.0.0.1:9"));
}
