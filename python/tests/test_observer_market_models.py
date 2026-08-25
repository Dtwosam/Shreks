import math

import pytest

from shreks_brain.observer_market.models import (
    OBSERVER_MARKET_SCHEMA_VERSION,
    ObservedMarketWindow,
    ObserverCandidateIdentity,
    ObserverMarketReadPolicy,
    ObserverMarketSnapshot,
)


def _policy(**changes):
    values = {
        "version": "e13-policy-v1",
        "source_priority": ("dexscreener", "meteora"),
        "max_current_age_ms": 20_000,
        "local_range_lookback_ms": 300_000,
    }
    values.update(changes)
    return ObserverMarketReadPolicy(**values)


def _candidate(**changes):
    values = {
        "candidate_id": 7,
        "mint": "Mint111",
        "pair_address": "Pair111",
        "discovery_source": "pump",
        "discovered_at_unix_ms": 1_000,
        "venue": "pump_fun",
    }
    values.update(changes)
    return ObserverCandidateIdentity(**values)


def _snapshot(**changes):
    values = {
        "row_id": 11,
        "candidate_id": 7,
        "observed_at_unix_ms": 1_000_000,
        "source": "dexscreener",
        "source_observed_at_unix_ms": 999_500,
        "venue": "raydium",
        "pair_address": "Pair111",
        "price_usd": 0.25,
        "liquidity_usd": 50_000.0,
        "volume_m5_usd": 4_000.0,
        "volume_h1_usd": 30_000.0,
        "buys_m5": 40,
        "sells_m5": 20,
        "buys_h1": 300,
        "sells_h1": 150,
        "pair_created_at_unix_ms": 500_000,
    }
    values.update(changes)
    return ObserverMarketSnapshot(**values)


def _window(**changes):
    current = _snapshot()
    candidate = _candidate()
    values = {
        "schema_version": OBSERVER_MARKET_SCHEMA_VERSION,
        "policy_version": "e13-policy-v1",
        "candidate": candidate,
        "as_of_unix_ms": 1_005_000,
        "selected_source": current.source,
        "selected_pair_address": current.pair_address,
        "current": current,
        "one_minute_ago": None,
        "five_minutes_ago": None,
        "fifteen_minutes_ago": None,
        "pair_created_at_unix_ms": current.pair_created_at_unix_ms,
        "local_high_price_usd": 0.30,
        "local_low_price_usd": 0.20,
    }
    values.update(changes)
    return ObservedMarketWindow(**values)


def test_schema_and_valid_models_are_immutable():
    assert OBSERVER_MARKET_SCHEMA_VERSION == "e13-observer-market-v1"
    policy = _policy()
    candidate = _candidate()
    snapshot = _snapshot()
    window = _window()

    assert policy.source_priority == ("dexscreener", "meteora")
    assert candidate.candidate_id == 7
    assert snapshot.price_usd == 0.25
    assert window.current is snapshot or window.current == snapshot

    with pytest.raises((AttributeError, TypeError)):
        policy.version = "changed"


def test_policy_rejects_invalid_or_ambiguous_configuration():
    invalid = (
        {"version": ""},
        {"source_priority": ()},
        {"source_priority": ("dexscreener", "dexscreener")},
        {"source_priority": ("",)},
        {"max_current_age_ms": -1},
        {"local_range_lookback_ms": 0},
    )
    for changes in invalid:
        with pytest.raises(ValueError):
            _policy(**changes)


def test_candidate_identity_rejects_invalid_values_but_allows_storage_empty_pair_sentinel():
    invalid = (
        {"candidate_id": 0},
        {"mint": ""},
        {"discovery_source": ""},
        {"discovered_at_unix_ms": -1},
        {"venue": ""},
    )
    for changes in invalid:
        with pytest.raises(ValueError):
            _candidate(**changes)

    assert _candidate(pair_address="").pair_address == ""


def test_snapshot_rejects_invalid_persisted_market_values_but_allows_empty_pair_sentinel():
    invalid = (
        {"row_id": 0},
        {"candidate_id": 0},
        {"observed_at_unix_ms": -1},
        {"source": ""},
        {"source_observed_at_unix_ms": -1},
        {"price_usd": -0.01},
        {"price_usd": math.nan},
        {"liquidity_usd": -1.0},
        {"volume_m5_usd": math.inf},
        {"buys_m5": -1},
        {"sells_h1": -1},
        {"pair_created_at_unix_ms": -1},
    )
    for changes in invalid:
        with pytest.raises(ValueError):
            _snapshot(**changes)

    assert _snapshot(pair_address="").pair_address == ""


def test_snapshot_rejects_source_time_after_observation_and_pair_creation_after_observation():
    with pytest.raises(ValueError, match="source_observed_at"):
        _snapshot(source_observed_at_unix_ms=1_000_001)
    with pytest.raises(ValueError, match="pair_created_at"):
        _snapshot(pair_created_at_unix_ms=1_000_001)


def test_window_rejects_wrong_schema_or_attribution():
    invalid = (
        {"schema_version": "wrong"},
        {"policy_version": ""},
        {"selected_source": "meteora"},
        {"selected_pair_address": "OtherPair"},
        {"current": _snapshot(candidate_id=8)},
        {"current": _snapshot(observed_at_unix_ms=1_006_000)},
        {"pair_created_at_unix_ms": 1_006_000},
        {"local_high_price_usd": 0.10, "local_low_price_usd": 0.20},
    )
    for changes in invalid:
        with pytest.raises(ValueError):
            _window(**changes)


def test_window_rejects_anchor_from_different_candidate_source_pair_or_future():
    invalid_anchors = (
        _snapshot(
            row_id=12,
            candidate_id=8,
            observed_at_unix_ms=940_000,
            source_observed_at_unix_ms=939_500,
        ),
        _snapshot(
            row_id=12,
            source="meteora",
            observed_at_unix_ms=940_000,
            source_observed_at_unix_ms=939_500,
        ),
        _snapshot(
            row_id=12,
            pair_address="OtherPair",
            observed_at_unix_ms=940_000,
            source_observed_at_unix_ms=939_500,
        ),
        _snapshot(row_id=12, observed_at_unix_ms=1_006_000),
    )
    for anchor in invalid_anchors:
        with pytest.raises(ValueError):
            _window(one_minute_ago=anchor)


def test_window_allows_nullable_market_fields_missing_anchors_and_empty_pair_path():
    current = _snapshot(
        source_observed_at_unix_ms=None,
        pair_address="",
        price_usd=None,
        liquidity_usd=None,
        volume_m5_usd=None,
        volume_h1_usd=None,
        buys_m5=None,
        sells_m5=None,
        buys_h1=None,
        sells_h1=None,
        pair_created_at_unix_ms=None,
    )
    window = _window(
        candidate=_candidate(pair_address=""),
        current=current,
        selected_pair_address="",
        pair_created_at_unix_ms=None,
        local_high_price_usd=None,
        local_low_price_usd=None,
    )
    assert window.one_minute_ago is None
    assert window.local_high_price_usd is None
