use std::collections::HashMap;

use shreks_providers::config::ProviderConfig;

#[test]
fn missing_optional_keys_disable_only_keyed_providers() {
    let config = ProviderConfig::from_lookup(|_| None);

    assert!(!config.helius_enabled());
    assert!(!config.alchemy_enabled());
    assert!(!config.jupiter_enabled());
    assert!(config.dexscreener_enabled);
    assert!(config.meteora_enabled);
}

#[test]
fn runtime_keys_enable_keyed_providers_without_becoming_debug_output() {
    let values = HashMap::from([
        ("HELIUS_API_KEY", "helius-secret"),
        ("ALCHEMY_API_KEY", "alchemy-secret"),
        ("JUPITER_API_KEY", "jupiter-secret"),
    ]);
    let config = ProviderConfig::from_lookup(|name| values.get(name).map(|value| value.to_string()));

    assert!(config.helius_enabled());
    assert!(config.alchemy_enabled());
    assert!(config.jupiter_enabled());
    assert_eq!(config.alchemy_api_key(), Some("alchemy-secret"));
    let debug = format!("{config:?}");
    assert!(!debug.contains("helius-secret"));
    assert!(!debug.contains("alchemy-secret"));
    assert!(!debug.contains("jupiter-secret"));
}

#[test]
fn blank_keys_are_treated_as_missing() {
    let values = HashMap::from([
        ("HELIUS_API_KEY", "   "),
        ("ALCHEMY_API_KEY", "\t"),
        ("JUPITER_API_KEY", ""),
    ]);
    let config = ProviderConfig::from_lookup(|name| values.get(name).map(|value| value.to_string()));
    assert!(!config.helius_enabled());
    assert!(!config.alchemy_enabled());
    assert!(!config.jupiter_enabled());
}

#[test]
fn default_budgets_stay_within_known_free_limits() {
    let config = ProviderConfig::from_lookup(|_| None);

    assert!(config.helius_rpc_rps > 0);
    assert!(config.helius_rpc_rps <= 10);

    assert!(config.jupiter_general_rps > 0);
    assert!(config.jupiter_general_rps <= 1);

    // DEX Screener token-pair endpoints document 300 requests/minute = 5 RPS.
    assert!(config.dexscreener_market_rps > 0);
    assert!(config.dexscreener_market_rps <= 5);

    // Meteora's public docs do not currently publish a hard ceiling Shreks
    // relies on, so V1 intentionally starts at a conservative one RPS.
    assert_eq!(config.meteora_market_rps, 1);
}

#[test]
fn config_has_no_paid_fallback_switch() {
    let config = ProviderConfig::from_lookup(|_| None);
    let debug = format!("{config:?}").to_ascii_lowercase();
    assert!(!debug.contains("paid"));
    assert!(!debug.contains("fallback"));
}
