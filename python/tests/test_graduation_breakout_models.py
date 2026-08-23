from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.setups.models import (
    GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED,
    GRADUATION_BREAKOUT_SETUP_NAME,
    GraduationBreakoutAssessment,
    GraduationBreakoutFinding,
    GraduationBreakoutPolicy,
    GraduationBreakoutReasonCode,
    GraduationContext,
    SetupState,
)


def context(**overrides) -> GraduationContext:
    values = {
        "event_type": "pump_graduation",
        "provider": "helius",
        "mint": "mint-a",
        "quote_mint": "So11111111111111111111111111111111111111112",
        "from_venue": "pump_fun_bonding_curve",
        "to_venue": "pump_swap",
        "pool_address": "pool-a",
        "signature": "sig-a",
        "slot": 2**64 - 1,
        "detected_at_unix_ms": 1_000_000,
        "occurred_at_unix_ms": 999_000,
    }
    values.update(overrides)
    return GraduationContext(**values)


def policy(**overrides) -> GraduationBreakoutPolicy:
    values = {
        "version": "graduation-v1-test",
        "min_seconds_since_graduation": 30.0,
        "max_seconds_since_graduation": 900.0,
        "max_source_age_ms": 30_000,
        "min_liquidity_usd": 50_000.0,
        "max_exit_price_impact_pct": 5.0,
        "min_tx_count_m5": 50,
        "min_volume_velocity_ratio": 1.2,
        "min_buy_fraction_m5": 0.60,
        "min_buy_pressure_acceleration": 0.05,
        "min_return_1m_pct": 1.0,
        "max_return_1m_pct": 40.0,
        "min_liquidity_change_5m_pct": 0.0,
        "min_distance_from_local_high_pct": -15.0,
        "min_range_position_pct": 60.0,
    }
    values.update(overrides)
    return GraduationBreakoutPolicy(**values)


def assessment(**overrides) -> GraduationBreakoutAssessment:
    values = {
        "setup_name": GRADUATION_BREAKOUT_SETUP_NAME,
        "policy_version": "graduation-v1-test",
        "feature_schema_version": "b2-v1",
        "as_of_unix_ms": 1_060_000,
        "graduation_mint": "mint-a",
        "graduation_detected_at_unix_ms": 1_000_000,
        "seconds_since_graduation": 60.0,
        "state": SetupState.WATCH,
        "confirmation_score": 50.0,
        "confirmations_passed": 4,
        "confirmations_required": GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED,
        "findings": (
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.RETURN_1M_BELOW_MINIMUM,
                message="return below threshold",
                observed_value=0.5,
                threshold_value=1.0,
            ),
        ),
    }
    values.update(overrides)
    return GraduationBreakoutAssessment(**values)


def test_stable_graduation_breakout_contract_values():
    assert GRADUATION_BREAKOUT_SETUP_NAME == "graduation_breakout"
    assert GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED == 8
    assert GraduationBreakoutReasonCode.GRADUATION_NOT_VERIFIED.value == (
        "GRADUATION_NOT_VERIFIED"
    )
    assert GraduationBreakoutReasonCode.GRADUATION_AFTER_AS_OF.value == (
        "GRADUATION_AFTER_AS_OF"
    )
    assert GraduationBreakoutReasonCode.MOVE_TOO_EXTENDED.value == "MOVE_TOO_EXTENDED"
    assert GraduationBreakoutReasonCode.ALL_CONFIRMATIONS_PASSED.value == (
        "ALL_CONFIRMATIONS_PASSED"
    )


def test_graduation_reason_code_order_is_stable():
    assert [code.value for code in GraduationBreakoutReasonCode] == [
        "SAFETY_NOT_PASS",
        "GRADUATION_NOT_VERIFIED",
        "GRADUATION_EVENT_NOT_PUMP",
        "GRADUATION_VENUE_TRANSITION_INVALID",
        "GRADUATION_AFTER_AS_OF",
        "POST_GRADUATION_WINDOW_EXPIRED",
        "SOURCE_DATA_TOO_OLD",
        "LIQUIDITY_BELOW_MINIMUM",
        "EXIT_PRICE_IMPACT_TOO_HIGH",
        "MOVE_TOO_EXTENDED",
        "GRADUATION_TOO_RECENT",
        "LIQUIDITY_UNKNOWN",
        "EXIT_PRICE_IMPACT_UNKNOWN",
        "TX_COUNT_M5_UNKNOWN",
        "TX_COUNT_M5_BELOW_MINIMUM",
        "VOLUME_VELOCITY_UNKNOWN",
        "VOLUME_VELOCITY_BELOW_MINIMUM",
        "BUY_FRACTION_M5_UNKNOWN",
        "BUY_FRACTION_M5_BELOW_MINIMUM",
        "BUY_PRESSURE_ACCELERATION_UNKNOWN",
        "BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM",
        "RETURN_1M_UNKNOWN",
        "RETURN_1M_BELOW_MINIMUM",
        "LIQUIDITY_CHANGE_5M_UNKNOWN",
        "LIQUIDITY_CHANGE_5M_BELOW_MINIMUM",
        "DISTANCE_FROM_LOCAL_HIGH_UNKNOWN",
        "TOO_FAR_BELOW_LOCAL_HIGH",
        "RANGE_POSITION_UNKNOWN",
        "RANGE_POSITION_BELOW_MINIMUM",
        "ALL_CONFIRMATIONS_PASSED",
    ]


def test_context_accepts_full_width_slot_and_optional_block_time():
    value = context(slot=2**64 - 1, occurred_at_unix_ms=None)
    assert value.slot == 2**64 - 1
    assert value.occurred_at_unix_ms is None


@pytest.mark.parametrize(
    "field",
    [
        "event_type",
        "provider",
        "mint",
        "quote_mint",
        "from_venue",
        "to_venue",
        "pool_address",
        "signature",
    ],
)
@pytest.mark.parametrize("value", ["", "   ", None])
def test_context_identity_fields_must_be_non_empty_strings(field, value):
    with pytest.raises(ValueError):
        context(**{field: value})


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_context_slot_must_be_non_negative_integer(value):
    with pytest.raises(ValueError):
        context(slot=value)


@pytest.mark.parametrize("field", ["detected_at_unix_ms", "occurred_at_unix_ms"])
@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_context_timestamps_must_be_non_negative_integers(field, value):
    with pytest.raises(ValueError):
        context(**{field: value})


def test_context_policy_finding_and_assessment_are_frozen():
    ctx = context()
    configured = policy()
    finding = GraduationBreakoutFinding(
        code=GraduationBreakoutReasonCode.GRADUATION_TOO_RECENT,
        message="too recent",
    )
    result = assessment(findings=(finding,))

    with pytest.raises(FrozenInstanceError):
        ctx.mint = "other"
    with pytest.raises(FrozenInstanceError):
        configured.min_liquidity_usd = 1.0
    with pytest.raises(FrozenInstanceError):
        finding.message = "other"
    with pytest.raises(FrozenInstanceError):
        result.state = SetupState.READY


@pytest.mark.parametrize("version", ["", "   ", None])
def test_policy_version_must_be_non_empty(version):
    with pytest.raises(ValueError):
        policy(version=version)


@pytest.mark.parametrize(
    "field",
    [
        "min_seconds_since_graduation",
        "max_seconds_since_graduation",
        "min_liquidity_usd",
        "max_exit_price_impact_pct",
        "min_volume_velocity_ratio",
    ],
)
@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf, -math.inf])
def test_non_negative_policy_numbers_are_validated(field, value):
    with pytest.raises(ValueError):
        policy(**{field: value})


@pytest.mark.parametrize("field", ["max_source_age_ms", "min_tx_count_m5"])
@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_integer_policy_fields_are_validated(field, value):
    with pytest.raises(ValueError):
        policy(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "min_buy_pressure_acceleration",
        "min_return_1m_pct",
        "max_return_1m_pct",
        "min_liquidity_change_5m_pct",
        "min_distance_from_local_high_pct",
    ],
)
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_signed_policy_thresholds_must_be_finite(field, value):
    with pytest.raises(ValueError):
        policy(**{field: value})


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_buy_fraction_threshold_is_within_unit_interval(value):
    with pytest.raises(ValueError):
        policy(min_buy_fraction_m5=value)


@pytest.mark.parametrize("value", [-0.01, 100.01])
def test_range_position_threshold_is_percentage(value):
    with pytest.raises(ValueError):
        policy(min_range_position_pct=value)


def test_distance_from_high_threshold_must_not_be_positive():
    with pytest.raises(ValueError):
        policy(min_distance_from_local_high_pct=0.01)


def test_max_graduation_age_must_exceed_minimum():
    with pytest.raises(ValueError):
        policy(max_seconds_since_graduation=30.0)
    with pytest.raises(ValueError):
        policy(max_seconds_since_graduation=29.9)


def test_max_return_must_not_be_below_minimum_return():
    with pytest.raises(ValueError):
        policy(min_return_1m_pct=20.0, max_return_1m_pct=19.9)


@pytest.mark.parametrize("setup_name", ["", "fresh_launch_continuation", "other"])
def test_assessment_requires_exact_setup_name(setup_name):
    with pytest.raises(ValueError):
        assessment(setup_name=setup_name)


@pytest.mark.parametrize("field", ["policy_version", "feature_schema_version"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_assessment_versions_must_be_non_empty(field, value):
    with pytest.raises(ValueError):
        assessment(**{field: value})


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_assessment_as_of_must_be_non_negative_integer(value):
    with pytest.raises(ValueError):
        assessment(as_of_unix_ms=value)


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_optional_assessment_graduation_timestamp_is_validated(value):
    with pytest.raises(ValueError):
        assessment(graduation_detected_at_unix_ms=value)


def test_assessment_allows_missing_graduation_audit_fields():
    result = assessment(
        graduation_mint=None,
        graduation_detected_at_unix_ms=None,
        seconds_since_graduation=None,
    )
    assert result.graduation_mint is None
    assert result.graduation_detected_at_unix_ms is None
    assert result.seconds_since_graduation is None


@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf, -math.inf, True, "1"])
def test_optional_seconds_since_graduation_must_be_finite_non_negative(value):
    with pytest.raises(ValueError):
        assessment(seconds_since_graduation=value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"confirmations_passed": -1},
        {"confirmations_required": 0},
        {"confirmations_required": -1},
        {"confirmations_passed": 9, "confirmations_required": 8},
        {"confirmation_score": -0.1},
        {"confirmation_score": 100.1},
        {"confirmation_score": math.nan},
    ],
)
def test_assessment_confirmation_fields_are_validated(overrides):
    with pytest.raises(ValueError):
        assessment(**overrides)


def test_assessment_has_no_execution_or_future_outcome_fields():
    names = {field.name for field in fields(GraduationBreakoutAssessment)}
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
