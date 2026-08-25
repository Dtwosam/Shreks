from dataclasses import fields
import math

import pytest

from shreks_brain.observer_campaign.models import (
    OBSERVER_PAPER_CAMPAIGN_SCHEMA_VERSION,
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteEvidence,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverPaperRiskEnvironment,
    ObserverRegimeReadPolicy,
)


def _identity(**changes):
    values = {
        "candidate_id": 7,
        "purpose": ObserverPaperQuotePurpose.ENTRY,
        "provider": "jupiter",
        "probe_policy_version": "probe-v2",
        "input_mint": "So11111111111111111111111111111111111111112",
        "output_mint": "Mint111",
        "taker": "Taker111",
        "input_amount": 2**64 - 1,
        "slippage_bps": 75,
    }
    values.update(changes)
    return ObserverPaperQuoteIdentity(**values)


def _evidence(**changes):
    values = {
        "identity": _identity(),
        "output_amount": 500_000_000,
        "minimum_output_amount": 490_000_000,
        "route_available": True,
        "price_impact_pct": "0.25",
        "route_labels": ("Raydium", "Meteora"),
        "quoted_at_unix_ms": 1_000_000,
    }
    values.update(changes)
    return ObserverPaperQuoteEvidence(**values)


def _regime_policy(**changes):
    values = {
        "version": "e15-regime-read-v1",
        "window_ms": 3_600_000,
        "max_snapshot_age_ms": 60_000,
        "source_priority": ("dexscreener", "meteora"),
        "entry_probe_policy_version": "probe-v2",
        "quote_asset_mint": "So11111111111111111111111111111111111111112",
        "entry_input_amount": 1_000_000_000,
        "taker": "Taker111",
        "slippage_bps": 75,
    }
    values.update(changes)
    return ObserverRegimeReadPolicy(**values)


def _risk_environment(**changes):
    values = {
        "trading_capital_usd": 10_000.0,
        "day_started_at_unix_ms": 900_000,
        "data_healthy": True,
        "execution_healthy": True,
        "kill_switch_active": False,
    }
    values.update(changes)
    return ObserverPaperRiskEnvironment(**values)


def test_schema_purpose_vocabulary_and_models_are_immutable():
    assert OBSERVER_PAPER_CAMPAIGN_SCHEMA_VERSION == "e15-observer-paper-v1"
    assert ObserverPaperQuotePurpose.ENTRY.value == "entry"
    assert ObserverPaperQuotePurpose.EXIT.value == "exit"

    asset = ObserverPaperQuoteAsset(
        mint="So11111111111111111111111111111111111111112",
        decimals=9,
        usd_per_token=150.0,
    )
    identity = _identity()
    evidence = _evidence()
    policy = _regime_policy()
    environment = _risk_environment()

    assert asset.decimals == 9
    assert identity.input_amount == 2**64 - 1
    assert evidence.identity is identity or evidence.identity == identity
    assert policy.source_priority == ("dexscreener", "meteora")
    assert environment.data_healthy is True

    with pytest.raises((AttributeError, TypeError)):
        asset.decimals = 6


def test_quote_asset_requires_exact_mint_decimal_range_and_positive_finite_usd_value():
    invalid = (
        {"mint": "", "decimals": 9, "usd_per_token": 150.0},
        {"mint": "Mint", "decimals": -1, "usd_per_token": 150.0},
        {"mint": "Mint", "decimals": 256, "usd_per_token": 150.0},
        {"mint": "Mint", "decimals": True, "usd_per_token": 150.0},
        {"mint": "Mint", "decimals": 9, "usd_per_token": 0.0},
        {"mint": "Mint", "decimals": 9, "usd_per_token": math.nan},
        {"mint": "Mint", "decimals": 9, "usd_per_token": math.inf},
    )
    for values in invalid:
        with pytest.raises(ValueError):
            ObserverPaperQuoteAsset(**values)


def test_quote_identity_requires_exact_purpose_request_attribution_and_u64_amount():
    invalid = (
        {"candidate_id": 0},
        {"purpose": "entry"},
        {"provider": ""},
        {"probe_policy_version": ""},
        {"input_mint": ""},
        {"output_mint": ""},
        {"output_mint": "So11111111111111111111111111111111111111112"},
        {"taker": ""},
        {"input_amount": 0},
        {"input_amount": 2**64},
        {"slippage_bps": -1},
        {"slippage_bps": 10_001},
    )
    for changes in invalid:
        with pytest.raises(ValueError):
            _identity(**changes)


def test_quote_evidence_rejects_malformed_raw_route_and_price_impact_values():
    invalid = (
        {"output_amount": -1},
        {"output_amount": 2**64},
        {"minimum_output_amount": -1},
        {"minimum_output_amount": 500_000_001},
        {"route_available": 1},
        {"route_available": True, "output_amount": 0},
        {"route_available": True, "route_labels": ()},
        {"price_impact_pct": ""},
        {"price_impact_pct": "NaN"},
        {"price_impact_pct": "-0.1"},
        {"route_labels": ("",)},
        {"quoted_at_unix_ms": -1},
    )
    for changes in invalid:
        with pytest.raises(ValueError):
            _evidence(**changes)

    unavailable = _evidence(
        output_amount=0,
        minimum_output_amount=0,
        route_available=False,
        price_impact_pct=None,
        route_labels=(),
    )
    assert unavailable.route_available is False


def test_regime_read_policy_is_versioned_bounded_and_exactly_attributed():
    invalid = (
        {"version": ""},
        {"window_ms": 0},
        {"max_snapshot_age_ms": -1},
        {"source_priority": ()},
        {"source_priority": ("dexscreener", "dexscreener")},
        {"source_priority": ("",)},
        {"entry_probe_policy_version": ""},
        {"quote_asset_mint": ""},
        {"entry_input_amount": 0},
        {"entry_input_amount": 2**64},
        {"taker": ""},
        {"slippage_bps": 10_001},
    )
    for changes in invalid:
        with pytest.raises(ValueError):
            _regime_policy(**changes)


def test_risk_environment_has_no_optimistic_defaults_and_requires_explicit_health_facts():
    invalid = (
        {"trading_capital_usd": 0.0},
        {"trading_capital_usd": math.inf},
        {"day_started_at_unix_ms": -1},
        {"data_healthy": 1},
        {"execution_healthy": None},
        {"kill_switch_active": 0},
    )
    for changes in invalid:
        with pytest.raises(ValueError):
            _risk_environment(**changes)

    field_names = tuple(field.name for field in fields(ObserverPaperRiskEnvironment))
    assert field_names == (
        "trading_capital_usd",
        "day_started_at_unix_ms",
        "data_healthy",
        "execution_healthy",
        "kill_switch_active",
    )


def test_e15_models_carry_no_execution_or_promotion_authority_fields():
    forbidden = {
        "private_key",
        "secret_key",
        "signed_transaction",
        "transaction_instructions",
        "submit",
        "live_mode",
        "promote",
        "registry_mutation",
    }
    for model in (
        ObserverPaperQuoteAsset,
        ObserverPaperQuoteIdentity,
        ObserverPaperQuoteEvidence,
        ObserverRegimeReadPolicy,
        ObserverPaperRiskEnvironment,
    ):
        names = {field.name.lower() for field in fields(model)}
        assert names.isdisjoint(forbidden)
