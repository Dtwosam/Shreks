from dataclasses import replace
import math

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.exits.engine import assess_exit, create_exit_state
from shreks_brain.exits.models import (
    ExitExecutionContext,
    ExitPolicy,
    ExitReasonCode,
    ExitRouteState,
    TakeProfitLevel,
)
from shreks_brain.features import FeatureVector
from shreks_brain.paper import PaperPosition, PaperPositionState
from shreks_brain.safety import SafetyDecision


AS_OF = 1_010_000


def _position(**overrides):
    values = dict(
        position_id="position-1",
        mint="Mint111",
        state=PaperPositionState.OPEN,
        quantity=500.0,
        weighted_entry_price_usd=1.0,
        open_cost_basis_usd=501.5,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=None,
        accumulated_costs_usd=1.5,
        opened_at_unix_ms=1_000_000,
        updated_at_unix_ms=1_000_000,
        closed_at_unix_ms=None,
        last_mark_price_usd=None,
        last_mark_at_unix_ms=None,
        buy_fill_count=1,
        sell_fill_count=0,
    )
    values.update(overrides)
    return PaperPosition(**values)


def _features(**overrides):
    values = dict(
        schema_version="b2-v1",
        as_of_unix_ms=AS_OF,
        source_observed_at_unix_ms=AS_OF - 100,
        source_age_ms=100,
        safety_policy_version="safety-test",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=100.0,
        price_usd=1.10,
        liquidity_usd=20_000.0,
        liquidity_change_5m_pct=1.0,
        exit_price_impact_pct=1.0,
        volume_m5_usd=10_000.0,
        volume_h1_usd=50_000.0,
        volume_velocity_ratio=2.0,
        tx_count_m5=100,
        tx_count_h1=500,
        buy_fraction_m5=0.60,
        buy_fraction_h1=0.55,
        buy_sell_ratio_m5=1.5,
        buy_sell_ratio_h1=1.2,
        buy_pressure_acceleration=0.10,
        return_1m_pct=2.0,
        return_5m_pct=5.0,
        return_15m_pct=10.0,
        momentum_acceleration_1m_vs_5m=1.0,
        distance_from_local_high_pct=-5.0,
        range_position_pct=0.80,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )
    values.update(overrides)
    return FeatureVector(**values)


def _context(**overrides):
    values = dict(
        as_of_unix_ms=AS_OF,
        observed_at_unix_ms=AS_OF - 100,
        route_state=ExitRouteState.AVAILABLE,
        available_exit_notional_usd=1_000.0,
        expected_exit_price_impact_pct=2.0,
        price_impact_notional_usd=500.0,
        wallet_distribution_detected=False,
        global_halt_active=False,
    )
    values.update(overrides)
    return ExitExecutionContext(**values)


def _policy(**overrides):
    values = dict(
        version="exit-v1",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(
            TakeProfitLevel("tp1", 20.0, 0.5),
            TakeProfitLevel("tp2", 40.0, 1.0),
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


def _assess(*, position=None, features=None, context=None, state=None, policy=None):
    position = position or _position()
    features = features or _features()
    context = context or _context()
    policy = policy or _policy()
    state = state or create_exit_state(position, policy)
    return assess_exit(position, features, context, state, policy)


def _primary(result):
    primaries = [finding for finding in result.findings if finding.primary]
    assert len(primaries) == 1
    assert primaries[0].code is result.primary_reason
    return result.primary_reason


def _assert_hold(result, reason):
    assert result.action is DecisionAction.HOLD
    assert _primary(result) is reason
    assert result.target_reduction_fraction == 0.0
    assert result.target_quantity == 0.0


def _assert_exit(result, reason, quantity=500.0):
    assert result.action is DecisionAction.EXIT
    assert _primary(result) is reason
    assert result.target_reduction_fraction == 1.0
    assert math.isclose(result.target_quantity, quantity)


def test_create_exit_state_uses_only_position_evidence_and_requires_open_position():
    position = _position(
        unrealized_pnl_usd=48.5,
        updated_at_unix_ms=1_005_000,
        last_mark_price_usd=1.10,
        last_mark_at_unix_ms=1_005_000,
    )
    state = create_exit_state(position, _policy())
    assert state.policy_version == "exit-v1"
    assert state.position_id == position.position_id
    assert state.mint == position.mint
    assert state.initialized_at_unix_ms == position.opened_at_unix_ms
    assert state.last_evaluated_at_unix_ms == position.updated_at_unix_ms
    assert state.high_water_price_usd == 1.10
    assert state.high_water_at_unix_ms == position.last_mark_at_unix_ms
    assert state.completed_take_profit_levels == frozenset()

    entry_only = create_exit_state(_position(), _policy())
    assert entry_only.high_water_price_usd == 1.0
    assert entry_only.high_water_at_unix_ms == 1_000_000

    closed = _position(
        state=PaperPositionState.CLOSED,
        quantity=0.0,
        open_cost_basis_usd=0.0,
        unrealized_pnl_usd=0.0,
        updated_at_unix_ms=1_005_000,
        closed_at_unix_ms=1_005_000,
    )
    with pytest.raises(ValueError, match="OPEN"):
        create_exit_state(closed, _policy())


def test_structural_precedence_is_fail_closed_and_does_not_invent_exit():
    policy = _policy()
    position = _position()
    state = create_exit_state(position, policy)

    _assert_hold(
        _assess(features=_features(schema_version="other"), state=state),
        ExitReasonCode.FEATURE_SCHEMA_MISMATCH,
    )

    closed = _position(
        state=PaperPositionState.CLOSED,
        quantity=0.0,
        open_cost_basis_usd=0.0,
        unrealized_pnl_usd=0.0,
        updated_at_unix_ms=1_005_000,
        closed_at_unix_ms=1_005_000,
    )
    _assert_hold(
        _assess(position=closed, state=state),
        ExitReasonCode.POSITION_NOT_OPEN,
    )

    _assert_hold(
        _assess(state=replace(state, position_id="other")),
        ExitReasonCode.STATE_POSITION_MISMATCH,
    )
    _assert_hold(
        _assess(state=replace(state, mint="OtherMint")),
        ExitReasonCode.STATE_MINT_MISMATCH,
    )
    _assert_hold(
        _assess(state=replace(state, policy_version="other")),
        ExitReasonCode.STATE_POLICY_MISMATCH,
    )
    _assert_hold(
        _assess(features=_features(as_of_unix_ms=AS_OF - 1), state=state),
        ExitReasonCode.AS_OF_MISMATCH,
    )


def test_chronology_failures_remain_hold_and_position_age_can_be_unknown():
    position = _position()
    policy = _policy()
    state = create_exit_state(position, policy)
    early_as_of = position.opened_at_unix_ms - 1
    result = _assess(
        position=position,
        features=_features(
            as_of_unix_ms=early_as_of,
            source_observed_at_unix_ms=early_as_of,
        ),
        context=_context(
            as_of_unix_ms=early_as_of,
            observed_at_unix_ms=early_as_of,
        ),
        state=state,
        policy=policy,
    )
    _assert_hold(result, ExitReasonCode.CONTEXT_BEFORE_POSITION)
    assert result.position_age_seconds is None

    valid_as_of = position.opened_at_unix_ms + 100
    future_state = replace(
        state,
        last_evaluated_at_unix_ms=valid_as_of + 1,
        high_water_at_unix_ms=valid_as_of + 1,
    )
    result = _assess(
        position=position,
        features=_features(
            as_of_unix_ms=valid_as_of,
            source_observed_at_unix_ms=valid_as_of,
        ),
        context=_context(
            as_of_unix_ms=valid_as_of,
            observed_at_unix_ms=valid_as_of,
        ),
        state=future_state,
        policy=policy,
    )
    _assert_hold(result, ExitReasonCode.STATE_AFTER_AS_OF)


def test_global_halt_and_max_hold_are_price_independent_forced_exits():
    stale_missing = _features(
        price_usd=None,
        source_observed_at_unix_ms=AS_OF - 100_000,
        source_age_ms=100_000,
    )
    global_exit = _assess(
        features=stale_missing,
        context=_context(global_halt_active=True),
    )
    _assert_exit(global_exit, ExitReasonCode.GLOBAL_HALT_EXIT)

    one_second_policy = _policy(max_hold_seconds=10)
    max_hold = _assess(
        features=stale_missing,
        policy=one_second_policy,
        state=create_exit_state(_position(), one_second_policy),
    )
    _assert_exit(max_hold, ExitReasonCode.MAX_HOLD_EXIT)
    assert max_hold.position_age_seconds == 10.0

    both = _assess(
        features=stale_missing,
        context=_context(global_halt_active=True),
        policy=one_second_policy,
        state=create_exit_state(_position(), one_second_policy),
    )
    _assert_exit(both, ExitReasonCode.GLOBAL_HALT_EXIT)
    assert ExitReasonCode.MAX_HOLD_EXIT in {f.code for f in both.findings}


def test_market_and_execution_evidence_quality_hold_without_high_water_advance():
    policy = _policy(max_hold_seconds=None)
    state = replace(
        create_exit_state(_position(), policy),
        high_water_price_usd=1.20,
        high_water_at_unix_ms=1_005_000,
        last_evaluated_at_unix_ms=1_005_000,
    )

    cases = [
        (
            _features(source_observed_at_unix_ms=AS_OF + 1, price_usd=2.0),
            _context(),
            ExitReasonCode.MARKET_SOURCE_AFTER_AS_OF,
        ),
        (
            _features(source_observed_at_unix_ms=AS_OF - 5_001, price_usd=2.0),
            _context(),
            ExitReasonCode.MARKET_SOURCE_TOO_OLD,
        ),
        (
            _features(price_usd=2.0),
            _context(observed_at_unix_ms=AS_OF + 1),
            ExitReasonCode.EXECUTION_EVIDENCE_AFTER_AS_OF,
        ),
        (
            _features(price_usd=2.0),
            _context(observed_at_unix_ms=AS_OF - 5_001),
            ExitReasonCode.EXECUTION_EVIDENCE_TOO_OLD,
        ),
        (
            _features(price_usd=None),
            _context(),
            ExitReasonCode.CURRENT_PRICE_UNAVAILABLE,
        ),
    ]
    for features, context, reason in cases:
        result = _assess(
            features=features,
            context=context,
            state=state,
            policy=policy,
        )
        _assert_hold(result, reason)
        assert result.next_state.high_water_price_usd == 1.20
        assert result.next_state.high_water_at_unix_ms == 1_005_000


def test_liquidity_emergency_precedence_and_equality_boundaries():
    route = _assess(context=_context(route_state=ExitRouteState.UNAVAILABLE))
    _assert_exit(route, ExitReasonCode.LIQUIDITY_ROUTE_UNAVAILABLE)

    liquidity = _assess(features=_features(liquidity_usd=10_000.0))
    _assert_exit(liquidity, ExitReasonCode.LIQUIDITY_BELOW_MINIMUM)

    impact = _assess(
        context=_context(
            expected_exit_price_impact_pct=8.0,
            price_impact_notional_usd=50.0,
        )
    )
    _assert_exit(impact, ExitReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH)

    # Market value is 500 * 1.10 = 550; 275 evidenced notional is exactly 50%.
    capacity = _assess(context=_context(available_exit_notional_usd=275.0))
    _assert_exit(capacity, ExitReasonCode.EXIT_CAPACITY_TOO_LOW)
    assert math.isclose(capacity.exit_capacity_fraction or -1.0, 0.50)

    simultaneous = _assess(
        features=_features(liquidity_usd=9_000.0),
        context=_context(
            route_state=ExitRouteState.UNAVAILABLE,
            expected_exit_price_impact_pct=9.0,
            price_impact_notional_usd=50.0,
            available_exit_notional_usd=100.0,
        ),
    )
    _assert_exit(simultaneous, ExitReasonCode.LIQUIDITY_ROUTE_UNAVAILABLE)
    codes = {finding.code for finding in simultaneous.findings}
    assert ExitReasonCode.LIQUIDITY_BELOW_MINIMUM in codes
    assert ExitReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH in codes
    assert ExitReasonCode.EXIT_CAPACITY_TOO_LOW in codes


def test_hard_stop_equality_and_emergency_precedence_over_profit():
    hard = _assess(features=_features(price_usd=0.90))
    _assert_exit(hard, ExitReasonCode.HARD_STOP_TRIGGERED)
    assert math.isclose(hard.price_return_pct or 0.0, -10.0)

    emergency_profit = _assess(
        features=_features(price_usd=1.50),
        context=_context(route_state=ExitRouteState.UNAVAILABLE),
    )
    _assert_exit(emergency_profit, ExitReasonCode.LIQUIDITY_ROUTE_UNAVAILABLE)
    assert ExitReasonCode.TAKE_PROFIT_TRIGGERED in {
        finding.code for finding in emergency_profit.findings
    }


def test_trailing_requires_activation_and_drawdown_equality_triggers():
    policy = _policy(
        hard_stop_loss_pct=None,
        take_profit_levels=(),
        max_hold_seconds=None,
        flow_exit_max_buy_fraction_m5=None,
        flow_exit_max_buy_pressure_acceleration=None,
        momentum_exit_max_return_1m_pct=None,
        momentum_exit_max_return_5m_pct=None,
        min_liquidity_usd=None,
        max_exit_price_impact_pct=None,
        min_exit_capacity_fraction=None,
        wallet_distribution_enabled=False,
    )
    position = _position()

    inactive_state = replace(
        create_exit_state(position, policy),
        high_water_price_usd=1.149,
        high_water_at_unix_ms=1_005_000,
        last_evaluated_at_unix_ms=1_005_000,
    )
    inactive = _assess(
        position=position,
        features=_features(price_usd=1.05),
        state=inactive_state,
        policy=policy,
    )
    _assert_hold(inactive, ExitReasonCode.NO_EXIT_TRIGGERED)

    activation_state = replace(
        inactive_state,
        high_water_price_usd=1.15,
    )
    activation = _assess(
        position=position,
        features=_features(price_usd=1.15),
        state=activation_state,
        policy=policy,
    )
    _assert_hold(activation, ExitReasonCode.NO_EXIT_TRIGGERED)

    trigger_price = 1.15 * 0.92
    triggered = _assess(
        position=position,
        features=_features(price_usd=trigger_price),
        state=activation.next_state,
        policy=policy,
    )
    _assert_exit(triggered, ExitReasonCode.TRAILING_STOP_TRIGGERED)
    assert math.isclose(triggered.drawdown_from_high_water_pct or 0.0, -8.0)


def test_wallet_flow_and_momentum_require_explicit_complete_evidence():
    wallet = _assess(context=_context(wallet_distribution_detected=True))
    _assert_exit(wallet, ExitReasonCode.WALLET_DISTRIBUTION_TRIGGERED)

    for wallet_value in (None, False):
        result = _assess(context=_context(wallet_distribution_detected=wallet_value))
        _assert_hold(result, ExitReasonCode.NO_EXIT_TRIGGERED)

    disabled = _assess(
        context=_context(wallet_distribution_detected=True),
        policy=_policy(wallet_distribution_enabled=False),
        state=create_exit_state(_position(), _policy(wallet_distribution_enabled=False)),
    )
    _assert_hold(disabled, ExitReasonCode.NO_EXIT_TRIGGERED)

    flow = _assess(
        features=_features(
            buy_fraction_m5=0.40,
            buy_pressure_acceleration=-0.10,
        )
    )
    _assert_exit(flow, ExitReasonCode.FLOW_DETERIORATION_TRIGGERED)
    for features in (
        _features(buy_fraction_m5=None, buy_pressure_acceleration=-0.20),
        _features(buy_fraction_m5=0.30, buy_pressure_acceleration=None),
        _features(buy_fraction_m5=0.50, buy_pressure_acceleration=-0.20),
    ):
        _assert_hold(_assess(features=features), ExitReasonCode.NO_EXIT_TRIGGERED)

    momentum = _assess(
        features=_features(return_1m_pct=-5.0, return_5m_pct=-8.0)
    )
    _assert_exit(momentum, ExitReasonCode.MOMENTUM_DETERIORATION_TRIGGERED)
    for features in (
        _features(return_1m_pct=None, return_5m_pct=-10.0),
        _features(return_1m_pct=-10.0, return_5m_pct=None),
        _features(return_1m_pct=-4.0, return_5m_pct=-10.0),
    ):
        _assert_hold(_assess(features=features), ExitReasonCode.NO_EXIT_TRIGGERED)


def test_take_profit_ladder_is_staged_and_fill_state_controls_completed_levels():
    first = _assess(features=_features(price_usd=1.20))
    assert first.action is DecisionAction.REDUCE
    assert _primary(first) is ExitReasonCode.TAKE_PROFIT_TRIGGERED
    assert first.triggered_take_profit_level == "tp1"
    assert first.target_reduction_fraction == 0.5
    assert first.target_quantity == 250.0

    gapped = _assess(features=_features(price_usd=1.50))
    assert gapped.action is DecisionAction.REDUCE
    assert gapped.triggered_take_profit_level == "tp1"

    completed_state = replace(
        gapped.next_state,
        completed_take_profit_levels=frozenset({"tp1"}),
    )
    second = _assess(
        features=_features(price_usd=1.50),
        state=completed_state,
    )
    _assert_exit(second, ExitReasonCode.TAKE_PROFIT_TRIGGERED)
    assert second.triggered_take_profit_level == "tp2"


def test_high_water_only_increases_on_fresh_price_and_no_exit_case_is_hold():
    policy = _policy(
        hard_stop_loss_pct=None,
        take_profit_levels=(),
        trailing_activation_return_pct=None,
        trailing_stop_drawdown_pct=None,
        max_hold_seconds=None,
        flow_exit_max_buy_fraction_m5=None,
        flow_exit_max_buy_pressure_acceleration=None,
        momentum_exit_max_return_1m_pct=None,
        momentum_exit_max_return_5m_pct=None,
        min_liquidity_usd=None,
        max_exit_price_impact_pct=None,
        min_exit_capacity_fraction=None,
        wallet_distribution_enabled=False,
    )
    position = _position()
    state = create_exit_state(position, policy)
    up = _assess(
        position=position,
        features=_features(price_usd=1.30),
        state=state,
        policy=policy,
    )
    _assert_hold(up, ExitReasonCode.NO_EXIT_TRIGGERED)
    assert up.next_state.high_water_price_usd == 1.30
    assert up.next_state.high_water_at_unix_ms == AS_OF

    later_as_of = AS_OF + 1_000
    down = assess_exit(
        position,
        _features(
            as_of_unix_ms=later_as_of,
            source_observed_at_unix_ms=later_as_of - 100,
            price_usd=1.25,
        ),
        _context(
            as_of_unix_ms=later_as_of,
            observed_at_unix_ms=later_as_of - 100,
        ),
        up.next_state,
        policy,
    )
    _assert_hold(down, ExitReasonCode.NO_EXIT_TRIGGERED)
    assert down.next_state.high_water_price_usd == 1.30
    assert down.next_state.high_water_at_unix_ms == AS_OF


def test_primary_reason_has_lower_priority_trigger_supporting_findings():
    policy = _policy(
        take_profit_levels=(),
        trailing_activation_return_pct=None,
        trailing_stop_drawdown_pct=None,
        max_hold_seconds=None,
        min_liquidity_usd=None,
        max_exit_price_impact_pct=None,
        min_exit_capacity_fraction=None,
    )
    features = _features(
        price_usd=0.90,
        buy_fraction_m5=0.30,
        buy_pressure_acceleration=-0.20,
        return_1m_pct=-10.0,
        return_5m_pct=-12.0,
    )
    context = _context(wallet_distribution_detected=True)
    result = _assess(
        features=features,
        context=context,
        policy=policy,
        state=create_exit_state(_position(), policy),
    )
    _assert_exit(result, ExitReasonCode.HARD_STOP_TRIGGERED)
    codes = [finding.code for finding in result.findings]
    assert codes[0] is ExitReasonCode.HARD_STOP_TRIGGERED
    assert ExitReasonCode.WALLET_DISTRIBUTION_TRIGGERED in codes
    assert ExitReasonCode.FLOW_DETERIORATION_TRIGGERED in codes
    assert ExitReasonCode.MOMENTUM_DETERIORATION_TRIGGERED in codes
    assert sum(finding.primary for finding in result.findings) == 1
