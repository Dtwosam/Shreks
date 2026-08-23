from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.setups.models import (
    FIRST_PULLBACK_CONFIRMATIONS_REQUIRED,
    FIRST_PULLBACK_SETUP_NAME,
    FirstPullbackAssessment,
    FirstPullbackFinding,
    FirstPullbackPolicy,
    FirstPullbackReasonCode,
    PullbackContext,
    SetupState,
)


def context(**overrides) -> PullbackContext:
    values = {
        "impulse_started_at_unix_ms": 1_000_000,
        "peak_at_unix_ms": 1_120_000,
        "trough_at_unix_ms": 1_240_000,
        "impulse_start_price_usd": 1.0,
        "peak_price_usd": 1.5,
        "trough_price_usd": 1.2,
        "peak_liquidity_usd": 100_000.0,
        "trough_liquidity_usd": 80_000.0,
        "trough_buy_fraction_m5": 0.40,
        "sample_count": 8,
    }
    values.update(overrides)
    return PullbackContext(**values)


def policy(**overrides) -> FirstPullbackPolicy:
    values = {
        "version": "pullback-v1-test",
        "min_seconds_since_trough": 15.0,
        "max_seconds_since_trough": 600.0,
        "max_source_age_ms": 30_000,
        "min_structure_samples": 5,
        "min_initial_impulse_pct": 20.0,
        "min_pullback_depth_pct": 8.0,
        "max_pullback_depth_pct": 35.0,
        "min_recovery_from_trough_pct": 5.0,
        "min_current_vs_peak_pct": -10.0,
        "max_current_vs_peak_pct": 10.0,
        "min_liquidity_retention_pct": 70.0,
        "min_liquidity_usd": 50_000.0,
        "max_exit_price_impact_pct": 5.0,
        "min_tx_count_m5": 50,
        "min_volume_velocity_ratio": 1.2,
        "min_buy_fraction_m5": 0.60,
        "min_buy_fraction_improvement": 0.10,
        "min_buy_pressure_acceleration": 0.05,
        "min_return_1m_pct": 1.0,
        "max_return_1m_pct": 30.0,
    }
    values.update(overrides)
    return FirstPullbackPolicy(**values)


def assessment(**overrides) -> FirstPullbackAssessment:
    values = {
        "setup_name": FIRST_PULLBACK_SETUP_NAME,
        "policy_version": "pullback-v1-test",
        "feature_schema_version": "b2-v1",
        "as_of_unix_ms": 1_300_000,
        "state": SetupState.WATCH,
        "seconds_since_trough": 60.0,
        "impulse_return_pct": 50.0,
        "pullback_depth_pct": 20.0,
        "recovery_from_trough_pct": 10.0,
        "current_vs_peak_pct": -4.0,
        "liquidity_retention_pct": 80.0,
        "buy_fraction_improvement": 0.20,
        "confirmation_score": 8 / 9 * 100,
        "confirmations_passed": 8,
        "confirmations_required": FIRST_PULLBACK_CONFIRMATIONS_REQUIRED,
        "findings": (
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.RETURN_1M_BELOW_MINIMUM,
                message="one-minute return is below threshold",
                observed_value=0.5,
                threshold_value=1.0,
            ),
        ),
    }
    values.update(overrides)
    return FirstPullbackAssessment(**values)


def test_stable_first_pullback_contract_values():
    assert FIRST_PULLBACK_SETUP_NAME == "first_pullback"
    assert FIRST_PULLBACK_CONFIRMATIONS_REQUIRED == 9
    assert FirstPullbackReasonCode.PULLBACK_NOT_OBSERVED.value == "PULLBACK_NOT_OBSERVED"
    assert FirstPullbackReasonCode.PULLBACK_LOW_BROKEN.value == "PULLBACK_LOW_BROKEN"
    assert FirstPullbackReasonCode.ALL_CONFIRMATIONS_PASSED.value == (
        "ALL_CONFIRMATIONS_PASSED"
    )


def test_first_pullback_reason_code_order_is_stable():
    assert [code.value for code in FirstPullbackReasonCode] == [
        "SAFETY_NOT_PASS",
        "PULLBACK_AFTER_AS_OF",
        "PULLBACK_AFTER_MARKET_SOURCE",
        "PULLBACK_WINDOW_EXPIRED",
        "INITIAL_IMPULSE_TOO_WEAK",
        "PULLBACK_TOO_DEEP",
        "PULLBACK_LOW_BROKEN",
        "BREAKOUT_TOO_EXTENDED",
        "SOURCE_DATA_TOO_OLD",
        "LIQUIDITY_BELOW_MINIMUM",
        "EXIT_PRICE_IMPACT_TOO_HIGH",
        "MOVE_TOO_EXTENDED",
        "PULLBACK_NOT_OBSERVED",
        "INSUFFICIENT_STRUCTURE_SAMPLES",
        "PULLBACK_TOO_RECENT",
        "PULLBACK_NOT_DEEP_ENOUGH",
        "CURRENT_PRICE_UNKNOWN",
        "LIQUIDITY_UNKNOWN",
        "EXIT_PRICE_IMPACT_UNKNOWN",
        "LIQUIDITY_RETENTION_UNKNOWN",
        "TROUGH_BUY_FRACTION_UNKNOWN",
        "TX_COUNT_M5_UNKNOWN",
        "TX_COUNT_M5_BELOW_MINIMUM",
        "VOLUME_VELOCITY_UNKNOWN",
        "VOLUME_VELOCITY_BELOW_MINIMUM",
        "BUY_FRACTION_M5_UNKNOWN",
        "BUY_FRACTION_M5_BELOW_MINIMUM",
        "BUY_FRACTION_IMPROVEMENT_UNKNOWN",
        "BUY_FRACTION_IMPROVEMENT_BELOW_MINIMUM",
        "BUY_PRESSURE_ACCELERATION_UNKNOWN",
        "BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM",
        "RETURN_1M_UNKNOWN",
        "RETURN_1M_BELOW_MINIMUM",
        "RECOVERY_FROM_TROUGH_UNKNOWN",
        "RECOVERY_FROM_TROUGH_BELOW_MINIMUM",
        "CURRENT_VS_PEAK_UNKNOWN",
        "CURRENT_VS_PEAK_BELOW_MINIMUM",
        "LIQUIDITY_RETENTION_BELOW_MINIMUM",
        "ALL_CONFIRMATIONS_PASSED",
    ]


@pytest.mark.parametrize(
    "field",
    ["impulse_started_at_unix_ms", "peak_at_unix_ms", "trough_at_unix_ms"],
)
@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_context_timestamps_are_non_negative_integers(field, value):
    with pytest.raises(ValueError):
        context(**{field: value})


@pytest.mark.parametrize(
    "overrides",
    [
        {"peak_at_unix_ms": 1_000_000},
        {"peak_at_unix_ms": 999_999},
        {"trough_at_unix_ms": 1_120_000},
        {"trough_at_unix_ms": 1_119_999},
    ],
)
def test_context_requires_strict_start_peak_trough_chronology(overrides):
    with pytest.raises(ValueError):
        context(**overrides)


@pytest.mark.parametrize(
    "field",
    ["impulse_start_price_usd", "peak_price_usd", "trough_price_usd"],
)
@pytest.mark.parametrize("value", [0.0, -1.0, math.nan, math.inf, -math.inf, True, "1"])
def test_context_prices_are_finite_and_positive(field, value):
    with pytest.raises(ValueError):
        context(**{field: value})


def test_peak_must_not_be_below_impulse_start():
    with pytest.raises(ValueError):
        context(impulse_start_price_usd=1.5, peak_price_usd=1.49)


def test_peak_must_be_strictly_above_trough():
    with pytest.raises(ValueError):
        context(peak_price_usd=1.5, trough_price_usd=1.5)
    with pytest.raises(ValueError):
        context(peak_price_usd=1.5, trough_price_usd=1.6)


@pytest.mark.parametrize("field", ["peak_liquidity_usd", "trough_liquidity_usd"])
@pytest.mark.parametrize("value", [-0.01, math.nan, math.inf, -math.inf, True, "1"])
def test_optional_context_liquidity_is_finite_non_negative(field, value):
    with pytest.raises(ValueError):
        context(**{field: value})


def test_optional_context_liquidity_can_be_missing_or_zero():
    assert context(peak_liquidity_usd=None).peak_liquidity_usd is None
    assert context(trough_liquidity_usd=None).trough_liquidity_usd is None
    assert context(peak_liquidity_usd=0.0).peak_liquidity_usd == 0.0


@pytest.mark.parametrize("value", [-0.01, 1.01, math.nan, math.inf, True, "0.5"])
def test_trough_buy_fraction_is_bounded_when_present(value):
    with pytest.raises(ValueError):
        context(trough_buy_fraction_m5=value)


def test_trough_buy_fraction_can_be_missing():
    assert context(trough_buy_fraction_m5=None).trough_buy_fraction_m5 is None


@pytest.mark.parametrize("value", [-1, 0, 1, 2, 2.5, True])
def test_context_requires_at_least_three_integer_samples(value):
    with pytest.raises(ValueError):
        context(sample_count=value)


def test_context_accepts_exactly_three_samples():
    assert context(sample_count=3).sample_count == 3


def test_context_policy_finding_and_assessment_are_frozen():
    ctx = context()
    configured = policy()
    finding = FirstPullbackFinding(
        code=FirstPullbackReasonCode.PULLBACK_TOO_RECENT,
        message="too recent",
    )
    result = assessment(findings=(finding,))

    with pytest.raises(FrozenInstanceError):
        ctx.peak_price_usd = 2.0
    with pytest.raises(FrozenInstanceError):
        configured.min_liquidity_usd = 1.0
    with pytest.raises(FrozenInstanceError):
        finding.message = "other"
    with pytest.raises(FrozenInstanceError):
        result.state = SetupState.READY


@pytest.mark.parametrize("version", ["", "   ", None])
def test_policy_version_is_non_empty(version):
    with pytest.raises(ValueError):
        policy(version=version)


@pytest.mark.parametrize(
    "field",
    [
        "min_seconds_since_trough",
        "max_seconds_since_trough",
        "min_initial_impulse_pct",
        "min_pullback_depth_pct",
        "max_pullback_depth_pct",
        "min_recovery_from_trough_pct",
        "min_liquidity_retention_pct",
        "min_liquidity_usd",
        "max_exit_price_impact_pct",
        "min_volume_velocity_ratio",
    ],
)
@pytest.mark.parametrize("value", [-0.01, math.nan, math.inf, -math.inf])
def test_non_negative_policy_numbers_are_validated(field, value):
    with pytest.raises(ValueError):
        policy(**{field: value})


@pytest.mark.parametrize(
    "field", ["max_source_age_ms", "min_structure_samples", "min_tx_count_m5"]
)
@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_integer_policy_fields_are_validated(field, value):
    with pytest.raises(ValueError):
        policy(**{field: value})


def test_policy_requires_at_least_three_structure_samples():
    with pytest.raises(ValueError):
        policy(min_structure_samples=2)


@pytest.mark.parametrize(
    "field",
    [
        "min_current_vs_peak_pct",
        "max_current_vs_peak_pct",
        "min_buy_fraction_improvement",
        "min_buy_pressure_acceleration",
        "min_return_1m_pct",
        "max_return_1m_pct",
    ],
)
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "1"])
def test_signed_policy_numbers_must_be_finite(field, value):
    with pytest.raises(ValueError):
        policy(**{field: value})


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_policy_buy_fraction_is_bounded(value):
    with pytest.raises(ValueError):
        policy(min_buy_fraction_m5=value)


def test_policy_max_trough_age_must_exceed_minimum():
    with pytest.raises(ValueError):
        policy(max_seconds_since_trough=15.0)
    with pytest.raises(ValueError):
        policy(max_seconds_since_trough=14.9)


def test_policy_pullback_depth_range_is_ordered_and_below_100():
    with pytest.raises(ValueError):
        policy(min_pullback_depth_pct=36.0, max_pullback_depth_pct=35.0)
    with pytest.raises(ValueError):
        policy(max_pullback_depth_pct=100.0)


def test_policy_current_vs_peak_range_is_ordered():
    with pytest.raises(ValueError):
        policy(min_current_vs_peak_pct=11.0, max_current_vs_peak_pct=10.0)


def test_policy_return_range_is_ordered():
    with pytest.raises(ValueError):
        policy(min_return_1m_pct=31.0, max_return_1m_pct=30.0)


@pytest.mark.parametrize("setup_name", ["", "graduation_breakout", "other"])
def test_assessment_requires_exact_setup_name(setup_name):
    with pytest.raises(ValueError):
        assessment(setup_name=setup_name)


@pytest.mark.parametrize("field", ["policy_version", "feature_schema_version"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_assessment_versions_are_non_empty(field, value):
    with pytest.raises(ValueError):
        assessment(**{field: value})


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_assessment_as_of_is_non_negative_integer(value):
    with pytest.raises(ValueError):
        assessment(as_of_unix_ms=value)


@pytest.mark.parametrize(
    "field",
    [
        "seconds_since_trough",
        "impulse_return_pct",
        "pullback_depth_pct",
        "recovery_from_trough_pct",
        "liquidity_retention_pct",
    ],
)
@pytest.mark.parametrize("value", [-0.01, math.nan, math.inf, -math.inf, True, "1"])
def test_non_negative_assessment_metrics_are_validated(field, value):
    with pytest.raises(ValueError):
        assessment(**{field: value})


@pytest.mark.parametrize("field", ["current_vs_peak_pct", "buy_fraction_improvement"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "1"])
def test_signed_assessment_metrics_are_finite(field, value):
    with pytest.raises(ValueError):
        assessment(**{field: value})


def test_assessment_allows_missing_structural_metrics():
    result = assessment(
        seconds_since_trough=None,
        impulse_return_pct=None,
        pullback_depth_pct=None,
        recovery_from_trough_pct=None,
        current_vs_peak_pct=None,
        liquidity_retention_pct=None,
        buy_fraction_improvement=None,
    )
    assert result.seconds_since_trough is None
    assert result.current_vs_peak_pct is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"confirmations_passed": -1},
        {"confirmations_required": 0},
        {"confirmations_passed": 10, "confirmations_required": 9},
        {"confirmation_score": -0.1},
        {"confirmation_score": 100.1},
        {"confirmation_score": math.nan},
    ],
)
def test_assessment_confirmation_fields_are_validated(overrides):
    with pytest.raises(ValueError):
        assessment(**overrides)


def test_assessment_has_no_execution_or_future_outcome_fields():
    names = {field.name for field in fields(FirstPullbackAssessment)}
    for forbidden in (
        "trade_intent",
        "side",
        "notional",
        "position_size",
        "wallet",
        "order",
        "fill",
        "signer",
        "transaction",
        "realized_pnl",
        "future_return_pct",
        "mfe_pct",
        "mae_pct",
    ):
        assert forbidden not in names
