from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.setups.models import (
    FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
    FRESH_LAUNCH_SETUP_NAME,
    FreshLaunchAssessment,
    FreshLaunchPolicy,
    FreshLaunchReasonCode,
    SetupFinding,
    SetupState,
)


def policy(**overrides) -> FreshLaunchPolicy:
    values = {
        "version": "fresh-v1-test",
        "min_age_seconds": 60.0,
        "max_age_seconds": 900.0,
        "max_source_age_ms": 30_000,
        "min_liquidity_usd": 50_000.0,
        "max_exit_price_impact_pct": 5.0,
        "max_return_5m_pct": 80.0,
        "min_tx_count_m5": 50,
        "min_volume_velocity_ratio": 1.2,
        "min_buy_fraction_m5": 0.60,
        "min_buy_pressure_acceleration": 0.05,
        "min_return_1m_pct": 1.0,
        "min_return_5m_pct": 5.0,
        "min_liquidity_change_5m_pct": 0.0,
        "min_distance_from_local_high_pct": -15.0,
        "min_range_position_pct": 60.0,
    }
    values.update(overrides)
    return FreshLaunchPolicy(**values)


def test_stable_setup_contract_values():
    assert FRESH_LAUNCH_SETUP_NAME == "fresh_launch_continuation"
    assert FRESH_LAUNCH_CONFIRMATIONS_REQUIRED == 9
    assert [state.value for state in SetupState] == ["BLOCKED", "WATCH", "READY"]
    assert FreshLaunchReasonCode.SAFETY_NOT_PASS.value == "SAFETY_NOT_PASS"
    assert FreshLaunchReasonCode.MOVE_TOO_EXTENDED.value == "MOVE_TOO_EXTENDED"
    assert (
        FreshLaunchReasonCode.ALL_CONFIRMATIONS_PASSED.value
        == "ALL_CONFIRMATIONS_PASSED"
    )


def test_policy_and_assessment_are_frozen():
    configured = policy()
    with pytest.raises(FrozenInstanceError):
        configured.min_liquidity_usd = 1.0

    assessment = FreshLaunchAssessment(
        setup_name=FRESH_LAUNCH_SETUP_NAME,
        policy_version=configured.version,
        feature_schema_version="b2-v1",
        as_of_unix_ms=1_000,
        state=SetupState.WATCH,
        confirmation_score=0.0,
        confirmations_passed=0,
        confirmations_required=FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
        findings=(
            SetupFinding(
                code=FreshLaunchReasonCode.SETUP_TOO_YOUNG,
                message="too young",
            ),
        ),
    )
    with pytest.raises(FrozenInstanceError):
        assessment.state = SetupState.READY


def test_assessment_has_no_trade_or_future_outcome_fields():
    names = {field.name for field in fields(FreshLaunchAssessment)}
    for forbidden in (
        "trade_intent",
        "enter",
        "position_size",
        "future_return_pct",
        "mfe_pct",
        "mae_pct",
        "realized_pnl",
    ):
        assert forbidden not in names


@pytest.mark.parametrize("version", ["", "   ", None])
def test_policy_version_must_be_non_empty(version):
    with pytest.raises(ValueError):
        policy(version=version)


@pytest.mark.parametrize(
    "field",
    [
        "min_age_seconds",
        "max_age_seconds",
        "min_liquidity_usd",
        "max_exit_price_impact_pct",
        "max_return_5m_pct",
        "min_volume_velocity_ratio",
    ],
)
@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf, -math.inf])
def test_non_negative_policy_numbers_are_validated(field, value):
    with pytest.raises(ValueError):
        policy(**{field: value})


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_source_age_must_be_non_negative_integer(value):
    with pytest.raises(ValueError):
        policy(max_source_age_ms=value)


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_tx_count_threshold_must_be_non_negative_integer(value):
    with pytest.raises(ValueError):
        policy(min_tx_count_m5=value)


@pytest.mark.parametrize(
    "field",
    [
        "min_buy_pressure_acceleration",
        "min_return_1m_pct",
        "min_return_5m_pct",
        "min_liquidity_change_5m_pct",
        "min_distance_from_local_high_pct",
    ],
)
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_signed_policy_thresholds_must_still_be_finite(field, value):
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


def test_max_age_must_exceed_min_age():
    with pytest.raises(ValueError):
        policy(max_age_seconds=60.0)
    with pytest.raises(ValueError):
        policy(max_age_seconds=59.0)


def test_max_return_must_not_be_below_minimum_return():
    with pytest.raises(ValueError):
        policy(min_return_5m_pct=20.0, max_return_5m_pct=19.9)
