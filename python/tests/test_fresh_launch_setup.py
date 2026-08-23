from dataclasses import replace

import pytest

from shreks_brain.features import FeatureVector
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups.fresh_launch import assess_fresh_launch
from shreks_brain.setups.models import (
    FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
    FRESH_LAUNCH_SETUP_NAME,
    FreshLaunchPolicy,
    FreshLaunchReasonCode,
    SetupState,
)


AS_OF = 2_000_000


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


def ready_vector(**overrides) -> FeatureVector:
    values = {
        "schema_version": "b2-v1",
        "as_of_unix_ms": AS_OF,
        "source_observed_at_unix_ms": AS_OF - 10_000,
        "source_age_ms": 10_000,
        "safety_policy_version": "safety-v1",
        "safety_decision": SafetyDecision.PASS,
        "token_age_seconds": 300.0,
        "price_usd": 1.0,
        "liquidity_usd": 100_000.0,
        "liquidity_change_5m_pct": 10.0,
        "exit_price_impact_pct": 2.0,
        "volume_m5_usd": 20_000.0,
        "volume_h1_usd": 100_000.0,
        "volume_velocity_ratio": 2.4,
        "tx_count_m5": 100,
        "tx_count_h1": 500,
        "buy_fraction_m5": 0.75,
        "buy_fraction_h1": 0.60,
        "buy_sell_ratio_m5": 3.0,
        "buy_sell_ratio_h1": 1.5,
        "buy_pressure_acceleration": 0.15,
        "return_1m_pct": 4.0,
        "return_5m_pct": 20.0,
        "return_15m_pct": 30.0,
        "momentum_acceleration_1m_vs_5m": 0.0,
        "distance_from_local_high_pct": -5.0,
        "range_position_pct": 85.0,
        "safety_soft_finding_count": 0,
        "safety_liquidity_weak": False,
        "safety_holder_concentration_elevated": False,
        "safety_creator_concentration_elevated": False,
        "safety_exit_price_impact_elevated": False,
        "missing_features": (),
    }
    values.update(overrides)
    return FeatureVector(**values)


def codes(assessment):
    return tuple(finding.code for finding in assessment.findings)


def test_all_confirmations_pass_is_ready():
    result = assess_fresh_launch(ready_vector(), policy())

    assert result.setup_name == FRESH_LAUNCH_SETUP_NAME
    assert result.policy_version == "fresh-v1-test"
    assert result.feature_schema_version == "b2-v1"
    assert result.as_of_unix_ms == AS_OF
    assert result.state is SetupState.READY
    assert result.confirmations_passed == 9
    assert result.confirmations_required == FRESH_LAUNCH_CONFIRMATIONS_REQUIRED
    assert result.confirmation_score == 100.0
    assert codes(result) == (FreshLaunchReasonCode.ALL_CONFIRMATIONS_PASSED,)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"safety_decision": SafetyDecision.REJECT}, FreshLaunchReasonCode.SAFETY_NOT_PASS),
        ({"token_age_seconds": 901.0}, FreshLaunchReasonCode.SETUP_WINDOW_EXPIRED),
        ({"source_age_ms": 30_001}, FreshLaunchReasonCode.SOURCE_DATA_TOO_OLD),
        ({"liquidity_usd": 49_999.0}, FreshLaunchReasonCode.LIQUIDITY_BELOW_MINIMUM),
        ({"exit_price_impact_pct": 5.01}, FreshLaunchReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH),
        ({"return_5m_pct": 80.01}, FreshLaunchReasonCode.MOVE_TOO_EXTENDED),
    ],
)
def test_each_hard_gate_blocks_independently(changes, expected):
    result = assess_fresh_launch(ready_vector(**changes), policy())

    assert result.state is SetupState.BLOCKED
    assert expected in codes(result)
    assert result.confirmations_passed == 9
    assert result.confirmation_score == 100.0
    assert FreshLaunchReasonCode.ALL_CONFIRMATIONS_PASSED not in codes(result)


@pytest.mark.parametrize("decision", [SafetyDecision.REJECT, SafetyDecision.INCOMPLETE])
def test_safety_non_pass_cannot_be_overridden_by_perfect_confirmation(decision):
    result = assess_fresh_launch(ready_vector(safety_decision=decision), policy())

    assert result.state is SetupState.BLOCKED
    assert result.confirmations_passed == 9
    assert codes(result)[0] is FreshLaunchReasonCode.SAFETY_NOT_PASS


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"token_age_seconds": None}, FreshLaunchReasonCode.TOKEN_AGE_UNKNOWN),
        ({"token_age_seconds": 59.99}, FreshLaunchReasonCode.SETUP_TOO_YOUNG),
        ({"liquidity_usd": None}, FreshLaunchReasonCode.LIQUIDITY_UNKNOWN),
        ({"exit_price_impact_pct": None}, FreshLaunchReasonCode.EXIT_PRICE_IMPACT_UNKNOWN),
    ],
)
def test_incomplete_age_or_executability_evidence_stays_watch(changes, expected):
    result = assess_fresh_launch(ready_vector(**changes), policy())

    assert result.state is SetupState.WATCH
    assert expected in codes(result)
    assert result.confirmations_passed == 9
    assert result.confirmation_score == 100.0


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("tx_count_m5", 49, FreshLaunchReasonCode.TX_COUNT_M5_BELOW_MINIMUM),
        ("volume_velocity_ratio", 1.19, FreshLaunchReasonCode.VOLUME_VELOCITY_BELOW_MINIMUM),
        ("buy_fraction_m5", 0.59, FreshLaunchReasonCode.BUY_FRACTION_M5_BELOW_MINIMUM),
        ("buy_pressure_acceleration", 0.04, FreshLaunchReasonCode.BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM),
        ("return_1m_pct", 0.99, FreshLaunchReasonCode.RETURN_1M_BELOW_MINIMUM),
        ("return_5m_pct", 4.99, FreshLaunchReasonCode.RETURN_5M_BELOW_MINIMUM),
        ("liquidity_change_5m_pct", -0.01, FreshLaunchReasonCode.LIQUIDITY_CHANGE_5M_BELOW_MINIMUM),
        ("distance_from_local_high_pct", -15.01, FreshLaunchReasonCode.TOO_FAR_BELOW_LOCAL_HIGH),
        ("range_position_pct", 59.99, FreshLaunchReasonCode.RANGE_POSITION_BELOW_MINIMUM),
    ],
)
def test_each_failed_confirmation_is_watch_and_scores_eight_of_nine(field, value, expected):
    result = assess_fresh_launch(ready_vector(**{field: value}), policy())

    assert result.state is SetupState.WATCH
    assert result.confirmations_passed == 8
    assert result.confirmation_score == pytest.approx((8 / 9) * 100)
    assert expected in codes(result)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("tx_count_m5", FreshLaunchReasonCode.TX_COUNT_M5_UNKNOWN),
        ("volume_velocity_ratio", FreshLaunchReasonCode.VOLUME_VELOCITY_UNKNOWN),
        ("buy_fraction_m5", FreshLaunchReasonCode.BUY_FRACTION_M5_UNKNOWN),
        ("buy_pressure_acceleration", FreshLaunchReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN),
        ("return_1m_pct", FreshLaunchReasonCode.RETURN_1M_UNKNOWN),
        ("return_5m_pct", FreshLaunchReasonCode.RETURN_5M_UNKNOWN),
        ("liquidity_change_5m_pct", FreshLaunchReasonCode.LIQUIDITY_CHANGE_5M_UNKNOWN),
        ("distance_from_local_high_pct", FreshLaunchReasonCode.DISTANCE_FROM_LOCAL_HIGH_UNKNOWN),
        ("range_position_pct", FreshLaunchReasonCode.RANGE_POSITION_UNKNOWN),
    ],
)
def test_each_missing_confirmation_is_watch_and_does_not_pass(field, expected):
    result = assess_fresh_launch(ready_vector(**{field: None}), policy())

    assert result.state is SetupState.WATCH
    assert result.confirmations_passed == 8
    assert result.confirmation_score == pytest.approx((8 / 9) * 100)
    assert expected in codes(result)


def test_equality_at_confirmation_and_hard_gate_thresholds_passes():
    configured = policy()
    vector = ready_vector(
        token_age_seconds=configured.max_age_seconds,
        source_age_ms=configured.max_source_age_ms,
        liquidity_usd=configured.min_liquidity_usd,
        exit_price_impact_pct=configured.max_exit_price_impact_pct,
        tx_count_m5=configured.min_tx_count_m5,
        volume_velocity_ratio=configured.min_volume_velocity_ratio,
        buy_fraction_m5=configured.min_buy_fraction_m5,
        buy_pressure_acceleration=configured.min_buy_pressure_acceleration,
        return_1m_pct=configured.min_return_1m_pct,
        return_5m_pct=configured.min_return_5m_pct,
        liquidity_change_5m_pct=configured.min_liquidity_change_5m_pct,
        distance_from_local_high_pct=configured.min_distance_from_local_high_pct,
        range_position_pct=configured.min_range_position_pct,
    )

    result = assess_fresh_launch(vector, configured)
    assert result.state is SetupState.READY
    assert result.confirmation_score == 100.0


def test_anti_chase_maximum_return_boundary_itself_is_allowed():
    configured = policy()
    result = assess_fresh_launch(
        ready_vector(return_5m_pct=configured.max_return_5m_pct),
        configured,
    )
    assert result.state is SetupState.READY


def test_hard_findings_precede_watch_and_confirmation_findings_deterministically():
    vector = ready_vector(
        safety_decision=SafetyDecision.REJECT,
        token_age_seconds=901.0,
        source_age_ms=30_001,
        liquidity_usd=49_999.0,
        exit_price_impact_pct=5.01,
        return_5m_pct=80.01,
        tx_count_m5=None,
        volume_velocity_ratio=1.0,
    )
    result = assess_fresh_launch(vector, policy())

    assert codes(result)[:8] == (
        FreshLaunchReasonCode.SAFETY_NOT_PASS,
        FreshLaunchReasonCode.SETUP_WINDOW_EXPIRED,
        FreshLaunchReasonCode.SOURCE_DATA_TOO_OLD,
        FreshLaunchReasonCode.LIQUIDITY_BELOW_MINIMUM,
        FreshLaunchReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
        FreshLaunchReasonCode.MOVE_TOO_EXTENDED,
        FreshLaunchReasonCode.TX_COUNT_M5_UNKNOWN,
        FreshLaunchReasonCode.VOLUME_VELOCITY_BELOW_MINIMUM,
    )


def test_repeated_assessments_are_equal():
    vector = ready_vector()
    configured = policy()
    assert assess_fresh_launch(vector, configured) == assess_fresh_launch(vector, configured)
