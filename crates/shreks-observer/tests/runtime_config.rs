use std::time::Duration;

use shreks_core::ProviderId;
use shreks_observer::{free_observe_provider_plan, ObserverRuntimeConfig};

#[test]
fn runtime_defaults_are_safe_and_observe_only() {
    let config = ObserverRuntimeConfig::from_lookup(|_| None).unwrap();

    assert_eq!(config.db_path.to_string_lossy(), "data/shreks.db");
    assert_eq!(config.cycle_interval, Duration::from_secs(30));

    let plan = free_observe_provider_plan(&config.providers);
    assert_eq!(plan.discovery, vec![ProviderId::DexScreener]);
    assert_eq!(
        plan.market,
        vec![ProviderId::DexScreener, ProviderId::Meteora]
    );
    assert!(plan.chain.is_empty());
    assert!(plan.transactions.is_empty());
    assert!(plan.realtime.is_empty());
    assert!(
        !plan.all_providers().contains(&ProviderId::Jupiter),
        "Jupiter must not be part of the observe-only runtime"
    );
}

#[test]
fn helius_is_enabled_for_chain_pump_verification_and_realtime_only_with_non_blank_key() {
    let without_key = ObserverRuntimeConfig::from_lookup(|name| match name {
        "HELIUS_API_KEY" => Some("   ".to_owned()),
        _ => None,
    })
    .unwrap();
    let without_key_plan = free_observe_provider_plan(&without_key.providers);
    assert!(without_key_plan.chain.is_empty());
    assert!(without_key_plan.transactions.is_empty());
    assert!(without_key_plan.realtime.is_empty());

    let with_key = ObserverRuntimeConfig::from_lookup(|name| match name {
        "HELIUS_API_KEY" => Some("fixture-helius-key".to_owned()),
        _ => None,
    })
    .unwrap();
    let with_key_plan = free_observe_provider_plan(&with_key.providers);
    assert_eq!(with_key_plan.chain, vec![ProviderId::Helius]);
    assert_eq!(with_key_plan.transactions, vec![ProviderId::Helius]);
    assert_eq!(with_key_plan.realtime, vec![ProviderId::Helius]);
    assert_eq!(
        with_key_plan
            .all_providers()
            .iter()
            .filter(|provider| **provider == ProviderId::Helius)
            .count(),
        1,
        "Helius should be deduplicated across chain, transaction, and realtime roles"
    );
}

#[test]
fn runtime_accepts_explicit_db_path_and_cycle_interval() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "SHREKS_DB_PATH" => Some("tmp/observe.sqlite".to_owned()),
        "SHREKS_OBSERVER_INTERVAL_SECONDS" => Some("7".to_owned()),
        _ => None,
    })
    .unwrap();

    assert_eq!(config.db_path.to_string_lossy(), "tmp/observe.sqlite");
    assert_eq!(config.cycle_interval, Duration::from_secs(7));
}

#[test]
fn runtime_rejects_zero_or_malformed_cycle_interval() {
    for invalid in ["0", "abc", "-1"] {
        let result = ObserverRuntimeConfig::from_lookup(|name| match name {
            "SHREKS_OBSERVER_INTERVAL_SECONDS" => Some(invalid.to_owned()),
            _ => None,
        });
        assert!(result.is_err(), "interval {invalid:?} should be rejected");
    }
}
