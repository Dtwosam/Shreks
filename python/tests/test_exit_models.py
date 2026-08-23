from dataclasses import fields, replace
import math

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.exits.models import (
    ExitAssessment,
    ExitExecutionContext,
    ExitFinding,
    ExitPolicy,
    ExitReasonCode,
    ExitRouteState,
    ExitState,
    TakeProfitLevel,
)


def _level(**overrides):
    values = dict(
        name="tp1",
        trigger_return_pct=20.0,
        reduce_fraction_of_current_quantity=0.5,
    )
    values.update(overrides)
    return TakeProfitLevel(**values)


def _policy(**overrides):
    values = dict(
        version="exit-test-v1",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(
            _level(),
            _level(name="tp2", trigger_return_pct=40.0, reduce_fraction_of_current_quantity=1.0),
        ),
        trailing_activation_return_pct=15.0,
        trailing_stop_drawdown_pct=8.0,
        max_hold_seconds=1_800,
        flow_exit_max_buy_fraction_m5=0.40,
        flow_exit_max_buy_pressure_acceleration=-0.10,
        momentum_exit_max_return_1m_pct=-5.0,
        momentum_exit_max_return_5m_pct=-8.0,
        min_liquidity_usd=10_000.0,
        max_exit_price_impact_pct=8.0,
        min_exit_capacity_fraction=0.50,
        wallet_distribution_enabled=True,
    )
    values.update(overrides)
    return ExitPolicy(**values)


def _context(**overrides):
    values = dict(
        as_of_unix_ms=1_001_000,
        observed_at_unix_ms=1_000_900,
        route_state=ExitRouteState.AVAILABLE,
        available_exit_notional_usd=1_000.0,
        expected_exit_price_impact_pct=2.0,
        price_impact_notional_usd=500.0,
        wallet_distribution_detected=None,
        global_halt_active=False,
    )
    values.update(overrides)
    return ExitExecutionContext(**values)


def _state(**overrides):
    values = dict(
        policy_version="exit-test-v1",
        position_id="position-1",
        mint="Mint111",
        initialized_at_unix_ms=1_000_000,
        last_evaluated_at_unix_ms=1_000_500,
        high_water_price_usd=1.20,
        high_water_at_unix_ms=1_000_400,
        completed_take_profit_levels=frozenset(),
    )
    values.update(overrides)
    return ExitState(**values)


def _assessment(**overrides):
    state = _state(last_evaluated_at_unix_ms=1_001_000)
    finding = ExitFinding(
        code=ExitReasonCode.NO_EXIT_TRIGGERED,
        message="no exit trigger",
        primary=True,
    )
    values = dict(
        policy_version="exit-test-v1",
        feature_schema_version="b2-v1",
        position_id="position-1",
        mint="Mint111",
        as_of_unix_ms=1_001_000,
        action=DecisionAction.HOLD,
        primary_reason=ExitReasonCode.NO_EXIT_TRIGGERED,
        target_reduction_fraction=0.0,
        target_quantity=0.0,
        position_age_seconds=1.0,
        current_price_usd=1.10,
        current_market_value_usd=550.0,
        price_return_pct=10.0,
        drawdown_from_high_water_pct=-8.3333333333,
        exit_capacity_fraction=1.0,
        triggered_take_profit_level=None,
        next_state=state,
        findings=(finding,),
    )
    values.update(overrides)
    return ExitAssessment(**values)


def test_exit_route_state_and_reason_code_order_are_stable():
    assert [value.value for value in ExitRouteState] == [
        "AVAILABLE",
        "UNAVAILABLE",
        "UNKNOWN",
    ]
    assert [value.value for value in ExitReasonCode] == [
        "FEATURE_SCHEMA_MISMATCH",
        "POSITION_NOT_OPEN",
        "STATE_POSITION_MISMATCH",
        "STATE_MINT_MISMATCH",
        "STATE_POLICY_MISMATCH",
        "AS_OF_MISMATCH",
        "CONTEXT_BEFORE_POSITION",
        "STATE_AFTER_AS_OF",
        "GLOBAL_HALT_EXIT",
        "MAX_HOLD_EXIT",
        "MARKET_SOURCE_AFTER_AS_OF",
        "MARKET_SOURCE_TOO_OLD",
        "EXECUTION_EVIDENCE_AFTER_AS_OF",
        "EXECUTION_EVIDENCE_TOO_OLD",
        "CURRENT_PRICE_UNAVAILABLE",
        "LIQUIDITY_ROUTE_UNAVAILABLE",
        "LIQUIDITY_BELOW_MINIMUM",
        "EXIT_PRICE_IMPACT_TOO_HIGH",
        "EXIT_CAPACITY_TOO_LOW",
        "HARD_STOP_TRIGGERED",
        "TRAILING_STOP_TRIGGERED",
        "WALLET_DISTRIBUTION_TRIGGERED",
        "FLOW_DETERIORATION_TRIGGERED",
        "MOMENTUM_DETERIORATION_TRIGGERED",
        "TAKE_PROFIT_TRIGGERED",
        "NO_EXIT_TRIGGERED",
    ]
    assert DecisionAction.HOLD.value == "HOLD"
    assert DecisionAction.REDUCE.value == "REDUCE"
    assert DecisionAction.EXIT.value == "EXIT"


def test_take_profit_level_requires_interpretable_positive_trigger_and_fraction():
    assert _level().reduce_fraction_of_current_quantity == 0.5
    for overrides in (
        {"name": ""},
        {"trigger_return_pct": 0.0},
        {"trigger_return_pct": -1.0},
        {"reduce_fraction_of_current_quantity": 0.0},
        {"reduce_fraction_of_current_quantity": 1.01},
        {"trigger_return_pct": math.inf},
    ):
        with pytest.raises(ValueError):
            _level(**overrides)


def test_exit_policy_has_no_defaults_and_requires_consistent_optional_rules():
    with pytest.raises(TypeError):
        ExitPolicy()

    assert _policy(take_profit_levels=()).take_profit_levels == ()

    for overrides in (
        {"version": ""},
        {"required_feature_schema_version": ""},
        {"max_market_data_age_ms": -1},
        {"max_execution_evidence_age_ms": -1},
        {"hard_stop_loss_pct": 0.0},
        {"trailing_activation_return_pct": None},
        {"trailing_stop_drawdown_pct": None},
        {"flow_exit_max_buy_fraction_m5": None},
        {"flow_exit_max_buy_pressure_acceleration": None},
        {"momentum_exit_max_return_1m_pct": None},
        {"momentum_exit_max_return_5m_pct": None},
        {"min_liquidity_usd": -1.0},
        {"max_exit_price_impact_pct": -1.0},
        {"min_exit_capacity_fraction": 0.0},
        {"min_exit_capacity_fraction": 1.01},
        {"wallet_distribution_enabled": 1},
    ):
        with pytest.raises(ValueError):
            _policy(**overrides)


def test_take_profit_levels_must_be_unique_and_strictly_increasing():
    with pytest.raises(ValueError, match="unique"):
        _policy(take_profit_levels=(_level(), _level()))
    with pytest.raises(ValueError, match="increasing"):
        _policy(
            take_profit_levels=(
                _level(name="later", trigger_return_pct=40.0),
                _level(name="earlier", trigger_return_pct=20.0),
            )
        )
    with pytest.raises(ValueError, match="increasing"):
        _policy(
            take_profit_levels=(
                _level(name="a", trigger_return_pct=20.0),
                _level(name="b", trigger_return_pct=20.0),
            )
        )


def test_execution_context_keeps_unknown_evidence_unknown_and_pairs_impact_size():
    unknown = _context(
        route_state=ExitRouteState.UNKNOWN,
        available_exit_notional_usd=None,
        expected_exit_price_impact_pct=None,
        price_impact_notional_usd=None,
        wallet_distribution_detected=None,
    )
    assert unknown.available_exit_notional_usd is None
    assert unknown.expected_exit_price_impact_pct is None
    assert unknown.wallet_distribution_detected is None

    for overrides in (
        {"expected_exit_price_impact_pct": 2.0, "price_impact_notional_usd": None},
        {"expected_exit_price_impact_pct": None, "price_impact_notional_usd": 500.0},
        {"available_exit_notional_usd": -1.0},
        {"expected_exit_price_impact_pct": -1.0},
        {"price_impact_notional_usd": 0.0},
        {"wallet_distribution_detected": "yes"},
        {"global_halt_active": 1},
    ):
        with pytest.raises(ValueError):
            _context(**overrides)


def test_exit_state_validates_policy_identity_chronology_high_water_and_levels():
    assert _state().completed_take_profit_levels == frozenset()

    for overrides in (
        {"policy_version": ""},
        {"position_id": ""},
        {"mint": ""},
        {"initialized_at_unix_ms": -1},
        {"last_evaluated_at_unix_ms": 999_999},
        {"high_water_price_usd": 0.0},
        {"high_water_at_unix_ms": 999_999},
        {"high_water_at_unix_ms": 1_000_501},
        {"completed_take_profit_levels": {"tp1"}},
        {"completed_take_profit_levels": frozenset({""})},
    ):
        with pytest.raises(ValueError):
            _state(**overrides)


def test_exit_finding_requires_reason_message_and_boolean_primary():
    finding = ExitFinding(
        code=ExitReasonCode.HARD_STOP_TRIGGERED,
        message="hard stop",
        primary=True,
        observed_value=-10.0,
        threshold_value=-10.0,
    )
    assert finding.primary is True

    with pytest.raises(ValueError):
        replace(finding, primary=1)
    with pytest.raises(ValueError):
        replace(finding, observed_value=math.inf)
    with pytest.raises(ValueError):
        replace(finding, threshold_value=math.nan)


def test_hold_reduce_exit_target_invariants_are_exact():
    _assessment()

    reduce = _assessment(
        action=DecisionAction.REDUCE,
        primary_reason=ExitReasonCode.TAKE_PROFIT_TRIGGERED,
        target_reduction_fraction=0.5,
        target_quantity=250.0,
        triggered_take_profit_level="tp1",
        findings=(
            ExitFinding(
                ExitReasonCode.TAKE_PROFIT_TRIGGERED,
                "take profit",
                primary=True,
            ),
        ),
    )
    assert reduce.target_reduction_fraction == 0.5

    exit_assessment = _assessment(
        action=DecisionAction.EXIT,
        primary_reason=ExitReasonCode.HARD_STOP_TRIGGERED,
        target_reduction_fraction=1.0,
        target_quantity=500.0,
        findings=(
            ExitFinding(
                ExitReasonCode.HARD_STOP_TRIGGERED,
                "hard stop",
                primary=True,
            ),
        ),
    )
    assert exit_assessment.target_reduction_fraction == 1.0

    for overrides in (
        {"action": DecisionAction.ENTER},
        {"target_reduction_fraction": 0.1},
        {"target_quantity": 1.0},
    ):
        with pytest.raises(ValueError):
            _assessment(**overrides)

    with pytest.raises(ValueError):
        replace(reduce, target_reduction_fraction=1.0)
    with pytest.raises(ValueError):
        replace(exit_assessment, target_reduction_fraction=0.5)


def test_exit_assessment_requires_one_primary_finding_matching_primary_reason():
    secondary = ExitFinding(
        ExitReasonCode.FLOW_DETERIORATION_TRIGGERED,
        "flow weak",
        primary=False,
    )
    valid = replace(_assessment(), findings=_assessment().findings + (secondary,))
    assert len(valid.findings) == 2

    with pytest.raises(ValueError, match="primary"):
        replace(_assessment(), findings=(secondary,))
    with pytest.raises(ValueError, match="primary"):
        replace(
            _assessment(),
            findings=(
                _assessment().findings[0],
                replace(_assessment().findings[0], code=ExitReasonCode.HARD_STOP_TRIGGERED),
            ),
        )
    with pytest.raises(ValueError, match="primary_reason"):
        replace(
            _assessment(),
            primary_reason=ExitReasonCode.HARD_STOP_TRIGGERED,
        )


def test_exit_assessment_metrics_preserve_unknowns_and_ranges():
    unknown = _assessment(
        current_price_usd=None,
        current_market_value_usd=None,
        price_return_pct=None,
        drawdown_from_high_water_pct=None,
        exit_capacity_fraction=None,
    )
    assert unknown.current_price_usd is None
    assert unknown.exit_capacity_fraction is None

    for overrides in (
        {"position_age_seconds": -1.0},
        {"current_price_usd": 0.0},
        {"current_market_value_usd": -1.0},
        {"price_return_pct": math.inf},
        {"drawdown_from_high_water_pct": math.nan},
        {"exit_capacity_fraction": -0.01},
        {"exit_capacity_fraction": 1.01},
        {"triggered_take_profit_level": ""},
    ):
        with pytest.raises(ValueError):
            _assessment(**overrides)


def test_public_c4_models_contain_no_execution_or_live_authority():
    public_models = (
        TakeProfitLevel,
        ExitPolicy,
        ExitExecutionContext,
        ExitState,
        ExitFinding,
        ExitAssessment,
    )
    forbidden = (
        "trade_intent",
        "fill",
        "signature",
        "signer",
        "private_key",
        "secret",
        "transaction",
        "live_execution",
        "provider",
        "sqlite",
    )
    for model in public_models:
        field_names = " ".join(field.name for field in fields(model)).lower()
        assert not any(fragment in field_names for fragment in forbidden)
