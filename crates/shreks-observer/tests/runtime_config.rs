use std::time::Duration;

use shreks_core::ProviderId;
use shreks_observer::{free_observe_provider_plan, ObserverRuntimeConfig};

#[test]
fn runtime_defaults_are_safe_and_observe_only() {
    let config = ObserverRuntimeConfig::from_lookup(|_| None).unwrap();

    assert_eq!(config.db_path.to_string_lossy(), "data/shreks.db");
    assert_eq!(config.cycle_interval, Duration::from_secs(30));
    assert_eq!(config.pumpswap_tracking_max_age, None);
    assert_eq!(config.pumpswap_max_tracked_pools, None);

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
        "SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS" => Some("500".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
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
fn helius_http_request_ceiling_is_required_only_when_helius_is_enabled() {
    let missing = match ObserverRuntimeConfig::from_lookup(|name| match name {
        "HELIUS_API_KEY" => Some("fixture-helius-key".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
        _ => None,
    }) {
        Ok(_) => panic!("Helius observer runtime must not start without an HTTP request ceiling"),
        Err(error) => error,
    };
    assert!(
        missing
            .to_string()
            .contains("SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS")
    );

    for invalid in ["0", "-1", "nope"] {
        let error = match ObserverRuntimeConfig::from_lookup(|name| match name {
            "HELIUS_API_KEY" => Some("fixture-helius-key".to_owned()),
            "SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS" => Some(invalid.to_owned()),
            "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
            "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
            _ => None,
        }) {
            Ok(_) => panic!("invalid Helius request ceiling must fail closed"),
            Err(error) => error,
        };
        assert!(
            error
                .to_string()
                .contains("SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS"),
            "invalid {invalid}: {error}"
        );
    }

    let bounded = ObserverRuntimeConfig::from_lookup(|name| match name {
        "HELIUS_API_KEY" => Some("fixture-helius-key".to_owned()),
        "SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS" => Some("123".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
        _ => None,
    })
    .unwrap();
    assert_eq!(
        bounded.providers.observer_helius_max_requests_per_process,
        Some(123)
    );

    let helius_free = ObserverRuntimeConfig::from_lookup(|_| None)
        .expect("Helius-free observe mode must not require a Helius ceiling");
    assert_eq!(
        helius_free.providers.observer_helius_max_requests_per_process,
        None
    );
}

#[test]
fn realtime_requires_explicit_positive_pumpswap_tracking_bounds() {
    for missing in [
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS",
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS",
    ] {
        let result = ObserverRuntimeConfig::from_lookup(|name| match name {
            "CHAINSTACK_SOLANA_WSS_URL" => Some("wss://fixture-chainstack.invalid/key".to_owned()),
            "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS"
                if missing != "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" =>
            {
                Some("900".to_owned())
            }
            "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS"
                if missing != "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" =>
            {
                Some("64".to_owned())
            }
            _ => None,
        });
        let error = result.expect_err("realtime must fail closed without both scope bounds");
        assert!(error.to_string().contains(missing), "missing {missing}: {error}");
    }

    for (name, invalid) in [
        ("SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS", "0"),
        ("SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS", "-1"),
        ("SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS", "nope"),
        ("SHREKS_PUMPSWAP_MAX_TRACKED_POOLS", "0"),
        ("SHREKS_PUMPSWAP_MAX_TRACKED_POOLS", "-1"),
        ("SHREKS_PUMPSWAP_MAX_TRACKED_POOLS", "nope"),
    ] {
        let result = ObserverRuntimeConfig::from_lookup(|key| match key {
            "CHAINSTACK_SOLANA_WSS_URL" => Some("wss://fixture-chainstack.invalid/key".to_owned()),
            "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some(
                if name == "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" {
                    invalid
                } else {
                    "900"
                }
                .to_owned(),
            ),
            "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some(
                if name == "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" {
                    invalid
                } else {
                    "64"
                }
                .to_owned(),
            ),
            _ => None,
        });
        let error = result.expect_err("invalid realtime scope bound must fail closed");
        assert!(error.to_string().contains(name), "invalid {name}={invalid}: {error}");
    }
}

#[test]
fn valid_realtime_scope_bounds_are_exposed_exactly() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "CHAINSTACK_SOLANA_WSS_URL" => Some("wss://fixture-chainstack.invalid/key".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("901".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("37".to_owned()),
        _ => None,
    })
    .unwrap();

    assert_eq!(config.pumpswap_tracking_max_age, Some(Duration::from_secs(901)));
    assert_eq!(config.pumpswap_max_tracked_pools, Some(37));
}

#[test]
fn chainstack_adds_readonly_chain_truth_and_owns_transaction_verification_when_configured() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "HELIUS_API_KEY" => Some("fixture-helius-key".to_owned()),
        "SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS" => Some("500".to_owned()),
        "CHAINSTACK_SOLANA_WSS_URL" => {
            Some("wss://solana-mainnet.core.chainstack.com/fixture-chainstack-key".to_owned())
        }
        "ALCHEMY_API_KEY" => Some("fixture-alchemy-key".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
        _ => None,
    })
    .unwrap();

    let plan = free_observe_provider_plan(&config.providers);
    assert_eq!(
        plan.chain,
        vec![ProviderId::Helius, ProviderId::Chainstack],
        "Helius and Chainstack may independently persist read-only mint truth"
    );
    assert_eq!(
        plan.transactions,
        vec![ProviderId::Chainstack],
        "the current observer consumes only its first transaction adapter, so Chainstack is selected explicitly to keep fallback provenance truthful while Helius quota is exhausted"
    );
    assert_eq!(
        plan.realtime,
        vec![
            ProviderId::Helius,
            ProviderId::Chainstack,
            ProviderId::Alchemy,
        ],
        "Helius remains primary realtime, Chainstack is the proven fallback, and Alchemy stays tertiary"
    );
    assert!(!plan.chain.contains(&ProviderId::Alchemy));
    assert!(!plan.transactions.contains(&ProviderId::Helius));
    assert!(!plan.transactions.contains(&ProviderId::Alchemy));
}

#[test]
fn chainstack_can_supply_readonly_rpc_and_realtime_without_helius() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "CHAINSTACK_SOLANA_WSS_URL" => {
            Some("wss://solana-mainnet.core.chainstack.com/fixture-chainstack-key".to_owned())
        }
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
        _ => None,
    })
    .unwrap();

    let plan = free_observe_provider_plan(&config.providers);
    assert_eq!(plan.chain, vec![ProviderId::Chainstack]);
    assert_eq!(plan.transactions, vec![ProviderId::Chainstack]);
    assert_eq!(plan.realtime, vec![ProviderId::Chainstack]);
}

#[test]
fn alchemy_is_realtime_only_and_ordered_after_helius_when_both_keys_exist() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "HELIUS_API_KEY" => Some("fixture-helius-key".to_owned()),
        "SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS" => Some("500".to_owned()),
        "ALCHEMY_API_KEY" => Some("fixture-alchemy-key".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
        _ => None,
    })
    .unwrap();

    let plan = free_observe_provider_plan(&config.providers);
    assert_eq!(plan.chain, vec![ProviderId::Helius]);
    assert_eq!(plan.transactions, vec![ProviderId::Helius]);
    assert_eq!(
        plan.realtime,
        vec![ProviderId::Helius, ProviderId::Alchemy],
        "Helius remains primary and Alchemy is the realtime fallback when Chainstack is absent"
    );
    assert!(!plan.chain.contains(&ProviderId::Alchemy));
    assert!(!plan.transactions.contains(&ProviderId::Alchemy));
}

#[test]
fn alchemy_can_provide_realtime_without_helius_chain_authority() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "ALCHEMY_API_KEY" => Some("fixture-alchemy-key".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
        _ => None,
    })
    .unwrap();

    let plan = free_observe_provider_plan(&config.providers);
    assert!(plan.chain.is_empty());
    assert!(plan.transactions.is_empty());
    assert_eq!(plan.realtime, vec![ProviderId::Alchemy]);
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
