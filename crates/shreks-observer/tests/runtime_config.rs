use std::time::Duration;

use shreks_core::ProviderId;
use shreks_observer::{free_observe_provider_plan, ObserverRuntimeConfig};

fn bounded_value(name: &str) -> Option<String> {
    match name {
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
        _ => None,
    }
}

#[test]
fn public_realtime_requires_explicit_positive_pumpswap_tracking_bounds_without_paid_credentials() {
    let missing_age = match ObserverRuntimeConfig::from_lookup(|_| None) {
        Ok(_) => panic!("public realtime must fail closed without an explicit tracking age"),
        Err(error) => error,
    };
    assert!(
        missing_age
            .to_string()
            .contains("SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS")
    );

    let missing_count = match ObserverRuntimeConfig::from_lookup(|name| match name {
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        _ => None,
    }) {
        Ok(_) => panic!("public realtime must fail closed without an explicit pool cap"),
        Err(error) => error,
    };
    assert!(
        missing_count
            .to_string()
            .contains("SHREKS_PUMPSWAP_MAX_TRACKED_POOLS")
    );

    for (name, invalid) in [
        ("SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS", "0"),
        ("SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS", "-1"),
        ("SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS", "nope"),
        ("SHREKS_PUMPSWAP_MAX_TRACKED_POOLS", "0"),
        ("SHREKS_PUMPSWAP_MAX_TRACKED_POOLS", "-1"),
        ("SHREKS_PUMPSWAP_MAX_TRACKED_POOLS", "nope"),
    ] {
        let error = match ObserverRuntimeConfig::from_lookup(|key| match key {
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
        }) {
            Ok(_) => panic!("invalid public realtime scope bound must fail closed"),
            Err(error) => error,
        };
        assert!(error.to_string().contains(name), "invalid {name}={invalid}: {error}");
    }
}

#[test]
fn runtime_defaults_use_public_solana_for_all_broad_chain_roles() {
    let config = ObserverRuntimeConfig::from_lookup(bounded_value).unwrap();

    assert_eq!(config.db_path.to_string_lossy(), "data/shreks.db");
    assert_eq!(config.cycle_interval, Duration::from_secs(30));
    assert_eq!(
        config.pumpswap_tracking_max_age,
        Some(Duration::from_secs(900))
    );
    assert_eq!(config.pumpswap_max_tracked_pools, Some(64));

    let plan = free_observe_provider_plan(&config.providers);
    assert_eq!(plan.discovery, vec![ProviderId::DexScreener]);
    assert_eq!(
        plan.market,
        vec![ProviderId::DexScreener, ProviderId::Meteora]
    );
    assert_eq!(plan.chain, vec![ProviderId::SolanaPublic]);
    assert_eq!(plan.transactions, vec![ProviderId::SolanaPublic]);
    assert_eq!(plan.realtime, vec![ProviderId::SolanaPublic]);
    assert!(
        !plan.all_providers().contains(&ProviderId::Jupiter),
        "Jupiter must not be part of the observe-only runtime"
    );
}

#[test]
fn paid_provider_credentials_are_inert_for_broad_observe_plan() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "HELIUS_API_KEY" => Some("fixture-helius-key".to_owned()),
        "CHAINSTACK_SOLANA_WSS_URL" => {
            Some("wss://solana-mainnet.core.chainstack.com/fixture-chainstack-key".to_owned())
        }
        "ALCHEMY_API_KEY" => Some("fixture-alchemy-key".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
        _ => None,
    })
    .expect("paid credentials must not impose broad-observer request-budget requirements");

    let plan = free_observe_provider_plan(&config.providers);
    assert_eq!(plan.chain, vec![ProviderId::SolanaPublic]);
    assert_eq!(plan.transactions, vec![ProviderId::SolanaPublic]);
    assert_eq!(plan.realtime, vec![ProviderId::SolanaPublic]);
    for paid in [ProviderId::Helius, ProviderId::Chainstack, ProviderId::Alchemy] {
        assert!(
            !plan.all_providers().contains(&paid),
            "paid provider {paid} must not re-enter broad FL1 capture"
        );
    }
}

#[test]
fn valid_public_realtime_scope_bounds_are_exposed_exactly() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("901".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("37".to_owned()),
        _ => None,
    })
    .unwrap();

    assert_eq!(config.pumpswap_tracking_max_age, Some(Duration::from_secs(901)));
    assert_eq!(config.pumpswap_max_tracked_pools, Some(37));
}

#[test]
fn runtime_accepts_explicit_db_path_and_cycle_interval() {
    let config = ObserverRuntimeConfig::from_lookup(|name| match name {
        "SHREKS_DB_PATH" => Some("tmp/observe.sqlite".to_owned()),
        "SHREKS_OBSERVER_INTERVAL_SECONDS" => Some("7".to_owned()),
        "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
        "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
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
            "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS" => Some("900".to_owned()),
            "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS" => Some("64".to_owned()),
            _ => None,
        });
        assert!(result.is_err(), "interval {invalid:?} should be rejected");
    }
}
