from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.safety import SafetyAssessment, SafetyDecision
from shreks_brain.features.models import (
    ANCHOR_1M_MAX_AGE_MS,
    ANCHOR_1M_MIN_AGE_MS,
    ANCHOR_5M_MAX_AGE_MS,
    ANCHOR_5M_MIN_AGE_MS,
    ANCHOR_15M_MAX_AGE_MS,
    ANCHOR_15M_MIN_AGE_MS,
    FEATURE_SCHEMA_VERSION,
    FeatureInputs,
    FeatureVector,
    MarketFeaturePoint,
)


AS_OF = 2_000_000


def clean_safety(*, as_of_unix_ms: int = AS_OF) -> SafetyAssessment:
    return SafetyAssessment(
        decision=SafetyDecision.PASS,
        policy_version="safety-v1",
        as_of_unix_ms=as_of_unix_ms,
        findings=(),
    )


def point(*, observed_at_unix_ms: int = AS_OF - 10_000, **overrides) -> MarketFeaturePoint:
    values = {
        "observed_at_unix_ms": observed_at_unix_ms,
        "price_usd": 1.0,
        "liquidity_usd": 100_000.0,
        "volume_m5_usd": 10_000.0,
        "volume_h1_usd": 100_000.0,
        "buys_m5": 10,
        "sells_m5": 5,
        "buys_h1": 100,
        "sells_h1": 50,
    }
    values.update(overrides)
    return MarketFeaturePoint(**values)


def inputs(**overrides) -> FeatureInputs:
    values = {
        "as_of_unix_ms": AS_OF,
        "current": point(),
        "one_minute_ago": None,
        "five_minutes_ago": None,
        "fifteen_minutes_ago": None,
        "pair_created_at_unix_ms": AS_OF - 500_000,
        "local_high_price_usd": 1.2,
        "local_low_price_usd": 0.8,
        "exit_price_impact_pct": 2.5,
        "safety": clean_safety(),
    }
    values.update(overrides)
    return FeatureInputs(**values)


def test_schema_and_anchor_contract_is_stable():
    assert FEATURE_SCHEMA_VERSION == "b2-v1"
    assert (ANCHOR_1M_MIN_AGE_MS, ANCHOR_1M_MAX_AGE_MS) == (60_000, 90_000)
    assert (ANCHOR_5M_MIN_AGE_MS, ANCHOR_5M_MAX_AGE_MS) == (300_000, 360_000)
    assert (ANCHOR_15M_MIN_AGE_MS, ANCHOR_15M_MAX_AGE_MS) == (900_000, 1_020_000)


def test_feature_inputs_exclude_future_outcome_fields():
    names = {field.name for field in fields(FeatureInputs)}
    for forbidden in (
        "future_return_pct",
        "return_pct",
        "mfe_pct",
        "mae_pct",
        "realized_pnl",
        "trade_result",
    ):
        assert forbidden not in names


def test_market_feature_point_is_frozen():
    market = point()
    with pytest.raises(FrozenInstanceError):
        market.price_usd = 2.0


def test_feature_inputs_and_vector_are_frozen():
    bundle = inputs()
    with pytest.raises(FrozenInstanceError):
        bundle.as_of_unix_ms = AS_OF + 1

    vector = FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=AS_OF,
        source_observed_at_unix_ms=AS_OF - 10_000,
        source_age_ms=10_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=500.0,
        price_usd=1.0,
        liquidity_usd=100_000.0,
        liquidity_change_5m_pct=None,
        exit_price_impact_pct=2.5,
        volume_m5_usd=10_000.0,
        volume_h1_usd=100_000.0,
        volume_velocity_ratio=1.2,
        tx_count_m5=15,
        tx_count_h1=150,
        buy_fraction_m5=2 / 3,
        buy_fraction_h1=2 / 3,
        buy_sell_ratio_m5=2.0,
        buy_sell_ratio_h1=2.0,
        buy_pressure_acceleration=0.0,
        return_1m_pct=None,
        return_5m_pct=None,
        return_15m_pct=None,
        momentum_acceleration_1m_vs_5m=None,
        distance_from_local_high_pct=-16.666666666666664,
        range_position_pct=50.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=("liquidity_change_5m_pct",),
    )
    with pytest.raises(FrozenInstanceError):
        vector.price_usd = 3.0


@pytest.mark.parametrize("field", ["price_usd", "liquidity_usd", "volume_m5_usd", "volume_h1_usd"])
@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf, -math.inf])
def test_market_money_values_must_be_finite_and_non_negative(field, value):
    with pytest.raises(ValueError):
        point(**{field: value})


@pytest.mark.parametrize("field", ["buys_m5", "sells_m5", "buys_h1", "sells_h1"])
@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_market_counts_must_be_non_negative_integers(field, value):
    with pytest.raises(ValueError):
        point(**{field: value})


def test_current_point_cannot_be_future_dated():
    with pytest.raises(ValueError):
        inputs(current=point(observed_at_unix_ms=AS_OF + 1))


@pytest.mark.parametrize(
    ("field", "age_ms"),
    [
        ("one_minute_ago", 60_000),
        ("one_minute_ago", 90_000),
        ("five_minutes_ago", 300_000),
        ("five_minutes_ago", 360_000),
        ("fifteen_minutes_ago", 900_000),
        ("fifteen_minutes_ago", 1_020_000),
    ],
)
def test_anchor_timing_band_boundaries_are_accepted(field, age_ms):
    bundle = inputs(**{field: point(observed_at_unix_ms=AS_OF - age_ms)})
    assert getattr(bundle, field).observed_at_unix_ms == AS_OF - age_ms


@pytest.mark.parametrize(
    ("field", "age_ms"),
    [
        ("one_minute_ago", 59_999),
        ("one_minute_ago", 90_001),
        ("five_minutes_ago", 299_999),
        ("five_minutes_ago", 360_001),
        ("fifteen_minutes_ago", 899_999),
        ("fifteen_minutes_ago", 1_020_001),
    ],
)
def test_anchor_outside_versioned_timing_band_is_rejected(field, age_ms):
    with pytest.raises(ValueError):
        inputs(**{field: point(observed_at_unix_ms=AS_OF - age_ms)})


def test_pair_creation_must_not_follow_current_observation():
    with pytest.raises(ValueError):
        inputs(pair_created_at_unix_ms=point().observed_at_unix_ms + 1)


@pytest.mark.parametrize("field", ["local_high_price_usd", "local_low_price_usd"])
@pytest.mark.parametrize("value", [0.0, -1.0, math.nan, math.inf])
def test_known_local_extrema_must_be_positive_and_finite(field, value):
    with pytest.raises(ValueError):
        inputs(**{field: value})


def test_local_high_cannot_be_below_local_low():
    with pytest.raises(ValueError):
        inputs(local_high_price_usd=0.9, local_low_price_usd=1.0)


@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf])
def test_exit_price_impact_must_be_finite_and_non_negative(value):
    with pytest.raises(ValueError):
        inputs(exit_price_impact_pct=value)


def test_safety_assessment_must_match_feature_timestamp_exactly():
    with pytest.raises(ValueError):
        inputs(safety=clean_safety(as_of_unix_ms=AS_OF - 1))

    with pytest.raises(ValueError):
        inputs(safety=clean_safety(as_of_unix_ms=AS_OF + 1))
