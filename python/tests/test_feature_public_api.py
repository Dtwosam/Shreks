from dataclasses import fields

from shreks_brain.safety import SafetyAssessment, SafetyDecision
from shreks_brain.features import (
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
    build_feature_vector,
)


def test_public_api_builds_feature_vector_without_internal_imports():
    as_of = 2_000_000
    safety = SafetyAssessment(
        decision=SafetyDecision.PASS,
        policy_version="safety-v1",
        as_of_unix_ms=as_of,
        findings=(),
    )
    current = MarketFeaturePoint(
        observed_at_unix_ms=as_of - 10_000,
        price_usd=1.0,
        liquidity_usd=100_000.0,
        volume_m5_usd=10_000.0,
        volume_h1_usd=100_000.0,
        buys_m5=10,
        sells_m5=5,
        buys_h1=100,
        sells_h1=50,
    )
    bundle = FeatureInputs(
        as_of_unix_ms=as_of,
        current=current,
        one_minute_ago=None,
        five_minutes_ago=None,
        fifteen_minutes_ago=None,
        pair_created_at_unix_ms=as_of - 500_000,
        local_high_price_usd=1.1,
        local_low_price_usd=0.9,
        exit_price_impact_pct=1.0,
        safety=safety,
    )

    vector = build_feature_vector(bundle)

    assert isinstance(vector, FeatureVector)
    assert vector.schema_version == "b2-v1"
    assert vector.safety_decision is SafetyDecision.PASS
    assert vector.price_usd == 1.0


def test_public_schema_constants_and_lookahead_boundary_are_stable():
    assert FEATURE_SCHEMA_VERSION == "b2-v1"
    assert (ANCHOR_1M_MIN_AGE_MS, ANCHOR_1M_MAX_AGE_MS) == (60_000, 90_000)
    assert (ANCHOR_5M_MIN_AGE_MS, ANCHOR_5M_MAX_AGE_MS) == (300_000, 360_000)
    assert (ANCHOR_15M_MIN_AGE_MS, ANCHOR_15M_MAX_AGE_MS) == (900_000, 1_020_000)

    names = {field.name for field in fields(FeatureInputs)}
    assert "future_return_pct" not in names
    assert "mfe_pct" not in names
    assert "mae_pct" not in names
