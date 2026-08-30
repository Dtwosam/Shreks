const OBSERVE_SOURCE: &str = include_str!("../src/bin/shreks-observe.rs");

fn function_slice<'a>(source: &'a str, start_marker: &str, end_marker: &str) -> &'a str {
    let start = source
        .find(start_marker)
        .unwrap_or_else(|| panic!("missing function marker: {start_marker}"));
    let end = source[start..]
        .find(end_marker)
        .map(|offset| start + offset)
        .unwrap_or_else(|| panic!("missing following marker: {end_marker}"));
    &source[start..end]
}

#[test]
fn broad_realtime_builder_is_solana_public_only_even_when_paid_credentials_exist() {
    let builder = function_slice(
        OBSERVE_SOURCE,
        "fn build_pump_realtime_configs",
        "fn build_lifecycle_observer",
    );

    assert!(builder.contains("BoundedPumpRealtimeLogStreamConfig::solana_public"));
    for forbidden in [
        "BoundedPumpRealtimeLogStreamConfig::helius",
        "BoundedPumpRealtimeLogStreamConfig::chainstack",
        "BoundedPumpRealtimeLogStreamConfig::alchemy",
        "helius_api_key",
        "chainstack_solana_wss_url",
        "alchemy_api_key",
    ] {
        assert!(
            !builder.contains(forbidden),
            "broad realtime must not activate paid provider path: {forbidden}"
        );
    }
}

#[test]
fn lifecycle_chain_and_transaction_verification_are_solana_public_only() {
    let builder = function_slice(
        OBSERVE_SOURCE,
        "fn build_lifecycle_observer",
        "fn build_high_resolution_sampler",
    );

    assert!(builder.contains("StandardSolanaRpcProvider::solana_public"));
    assert!(builder.contains("with_chain_provider"));
    assert!(builder.contains("with_transaction_provider"));
    for forbidden in [
        "HeliusProvider::new",
        "StandardSolanaRpcProvider::chainstack",
        "with_request_budget",
        "observer_helius_max_requests_per_process",
        "helius_api_key",
        "chainstack_solana_wss_url",
    ] {
        assert!(
            !builder.contains(forbidden),
            "broad lifecycle verification must not activate paid provider path: {forbidden}"
        );
    }
}
