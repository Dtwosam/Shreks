import math

import pytest

from shreks_brain.safety import (
    SafetyAssessment,
    SafetyDecision,
    SafetyFinding,
    SafetyReasonCode,
    SafetySeverity,
)
from shreks_brain.features.engine import build_feature_vector
from shreks_brain.features.models import FeatureInputs, MarketFeaturePoint


AS_OF = 2_000_000


def safety(
    *,
    decision: SafetyDecision = SafetyDecision.PASS,
    findings: tuple[SafetyFinding, ...] = (),
) -> SafetyAssessment:
    return SafetyAssessment(
        decision=decision,
        policy_version="safety-v1",
        as_of_unix_ms=AS_OF,
        findings=findings,
    )


def point(
    observed_at_unix_ms: int,
    *,
    price_usd: float | None,
    liquidity_usd: float | None,
    volume_m5_usd: float | None = None,
    volume_h1_usd: float | None = None,
    buys_m5: int | None = None,
    sells_m5: int | None = None,
    buys_h1: int | None = None,
    sells_h1: int | None = None,
) -> MarketFeaturePoint:
    return MarketFeaturePoint(
        observed_at_unix_ms=observed_at_unix_ms,
        price_usd=price_usd,
        liquidity_usd=liquidity_usd,
        volume_m5_usd=volume_m5_usd,
        volume_h1_usd=volume_h1_usd,
        buys_m5=buys_m5,
        sells_m5=sells_m5,
        buys_h1=buys_h1,
        sells_h1=sells_h1,
    )


def clean_inputs(*, safety_assessment: SafetyAssessment | None = None, **overrides) -> FeatureInputs:
    values = {
        "as_of_unix_ms": AS_OF,
        "current": point(
            AS_OF - 10_000,
            price_usd=1.20,
            liquidity_usd=120_000.0,
            volume_m5_usd=24_000.0,
            volume_h1_usd=120_000.0,
            buys_m5=80,
            sells_m5=20,
            buys_h1=600,
            sells_h1=400,
        ),
        "one_minute_ago": point(
            AS_OF - 60_000,
            price_usd=1.00,
            liquidity_usd=110_000.0,
        ),
        "five_minutes_ago": point(
            AS_OF - 300_000,
            price_usd=0.80,
            liquidity_usd=100_000.0,
        ),
        "fifteen_minutes_ago": point(
            AS_OF - 900_000,
            price_usd=0.60,
            liquidity_usd=80_000.0,
        ),
        "pair_created_at_unix_ms": AS_OF - 600_000,
        "local_high_price_usd": 1.50,
        "local_low_price_usd": 0.60,
        "exit_price_impact_pct": 3.0,
        "safety": safety_assessment or safety(),
    }
    values.update(overrides)
    return FeatureInputs(**values)


def soft(code: SafetyReasonCode) -> SafetyFinding:
    return SafetyFinding(
        code=code,
        severity=SafetySeverity.SOFT,
        message=code.value,
    )


def test_builds_exact_clean_feature_vector():
    assessment = safety(
        findings=(
            soft(SafetyReasonCode.LIQUIDITY_WEAK),
            soft(SafetyReasonCode.CREATOR_CONCENTRATION_ELEVATED),
        )
    )
    vector = build_feature_vector(clean_inputs(safety_assessment=assessment))

    assert vector.schema_version == "b2-v1"
    assert vector.as_of_unix_ms == AS_OF
    assert vector.source_observed_at_unix_ms == AS_OF - 10_000
    assert vector.source_age_ms == 10_000
    assert vector.safety_policy_version == "safety-v1"
    assert vector.safety_decision is SafetyDecision.PASS

    assert vector.token_age_seconds == 600.0
    assert vector.price_usd == 1.20
    assert vector.liquidity_usd == 120_000.0
    assert vector.liquidity_change_5m_pct == pytest.approx(20.0)
    assert vector.exit_price_impact_pct == 3.0

    assert vector.volume_m5_usd == 24_000.0
    assert vector.volume_h1_usd == 120_000.0
    assert vector.volume_velocity_ratio == pytest.approx(2.4)
    assert vector.tx_count_m5 == 100
    assert vector.tx_count_h1 == 1_000

    assert vector.buy_fraction_m5 == pytest.approx(0.8)
    assert vector.buy_fraction_h1 == pytest.approx(0.6)
    assert vector.buy_sell_ratio_m5 == pytest.approx(4.0)
    assert vector.buy_sell_ratio_h1 == pytest.approx(1.5)
    assert vector.buy_pressure_acceleration == pytest.approx(0.2)

    assert vector.return_1m_pct == pytest.approx(20.0)
    assert vector.return_5m_pct == pytest.approx(50.0)
    assert vector.return_15m_pct == pytest.approx(100.0)
    assert vector.momentum_acceleration_1m_vs_5m == pytest.approx(10.0)

    assert vector.distance_from_local_high_pct == pytest.approx(-20.0)
    assert vector.range_position_pct == pytest.approx(66.66666666666667)

    assert vector.safety_soft_finding_count == 2
    assert vector.safety_liquidity_weak is True
    assert vector.safety_holder_concentration_elevated is False
    assert vector.safety_creator_concentration_elevated is True
    assert vector.safety_exit_price_impact_elevated is False
    assert vector.missing_features == ()


@pytest.mark.parametrize("decision", [SafetyDecision.REJECT, SafetyDecision.INCOMPLETE])
def test_non_pass_safety_still_produces_features_for_research(decision):
    vector = build_feature_vector(clean_inputs(safety_assessment=safety(decision=decision)))

    assert vector.safety_decision is decision
    assert vector.price_usd == 1.20
    assert vector.return_5m_pct == pytest.approx(50.0)


def test_zero_denominators_stay_unknown_instead_of_infinite_or_zero_filled():
    current = point(
        AS_OF - 10_000,
        price_usd=1.0,
        liquidity_usd=100_000.0,
        volume_m5_usd=20_000.0,
        volume_h1_usd=0.0,
        buys_m5=10,
        sells_m5=0,
        buys_h1=0,
        sells_h1=0,
    )
    five_minutes_ago = point(
        AS_OF - 300_000,
        price_usd=0.0,
        liquidity_usd=0.0,
    )

    vector = build_feature_vector(
        clean_inputs(
            current=current,
            five_minutes_ago=five_minutes_ago,
            local_high_price_usd=1.0,
            local_low_price_usd=1.0,
        )
    )

    assert vector.return_5m_pct is None
    assert vector.liquidity_change_5m_pct is None
    assert vector.volume_velocity_ratio is None
    assert vector.buy_sell_ratio_m5 is None
    assert vector.buy_fraction_m5 == 1.0
    assert vector.buy_fraction_h1 is None
    assert vector.buy_pressure_acceleration is None
    assert vector.range_position_pct is None
    assert math.isfinite(vector.distance_from_local_high_pct)


def test_missing_data_is_none_and_reported_in_canonical_order():
    current = point(
        AS_OF - 10_000,
        price_usd=None,
        liquidity_usd=None,
        volume_m5_usd=None,
        volume_h1_usd=None,
        buys_m5=None,
        sells_m5=None,
        buys_h1=None,
        sells_h1=None,
    )
    vector = build_feature_vector(
        clean_inputs(
            current=current,
            one_minute_ago=None,
            five_minutes_ago=None,
            fifteen_minutes_ago=None,
            pair_created_at_unix_ms=None,
            local_high_price_usd=None,
            local_low_price_usd=None,
            exit_price_impact_pct=None,
        )
    )

    assert vector.price_usd is None
    assert vector.liquidity_usd is None
    assert vector.tx_count_m5 is None
    assert vector.buy_fraction_m5 is None
    assert vector.return_1m_pct is None
    assert vector.range_position_pct is None

    assert vector.missing_features == (
        "token_age_seconds",
        "price_usd",
        "liquidity_usd",
        "liquidity_change_5m_pct",
        "exit_price_impact_pct",
        "volume_m5_usd",
        "volume_h1_usd",
        "volume_velocity_ratio",
        "tx_count_m5",
        "tx_count_h1",
        "buy_fraction_m5",
        "buy_fraction_h1",
        "buy_sell_ratio_m5",
        "buy_sell_ratio_h1",
        "buy_pressure_acceleration",
        "return_1m_pct",
        "return_5m_pct",
        "return_15m_pct",
        "momentum_acceleration_1m_vs_5m",
        "distance_from_local_high_pct",
        "range_position_pct",
    )


def test_all_soft_safety_flags_are_projected_by_reason_code():
    assessment = safety(
        findings=(
            soft(SafetyReasonCode.LIQUIDITY_WEAK),
            soft(SafetyReasonCode.HOLDER_CONCENTRATION_ELEVATED),
            soft(SafetyReasonCode.CREATOR_CONCENTRATION_ELEVATED),
            soft(SafetyReasonCode.EXIT_PRICE_IMPACT_ELEVATED),
        )
    )

    vector = build_feature_vector(clean_inputs(safety_assessment=assessment))

    assert vector.safety_soft_finding_count == 4
    assert vector.safety_liquidity_weak
    assert vector.safety_holder_concentration_elevated
    assert vector.safety_creator_concentration_elevated
    assert vector.safety_exit_price_impact_elevated


def test_repeated_builds_are_identical():
    bundle = clean_inputs()
    assert build_feature_vector(bundle) == build_feature_vector(bundle)
