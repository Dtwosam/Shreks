from dataclasses import replace

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.exits.engine import (
    acknowledge_exit_fill,
    assess_exit,
    create_exit_state,
)
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


def _features(price_usd=1.20):
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=AS_OF,
        source_observed_at_unix_ms=AS_OF - 100,
        source_age_ms=100,
        safety_policy_version="safety-test",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=100.0,
        price_usd=price_usd,
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


def _context():
    return ExitExecutionContext(
        as_of_unix_ms=AS_OF,
        observed_at_unix_ms=AS_OF - 100,
        route_state=ExitRouteState.AVAILABLE,
        available_exit_notional_usd=1_000.0,
        expected_exit_price_impact_pct=2.0,
        price_impact_notional_usd=500.0,
        wallet_distribution_detected=False,
        global_halt_active=False,
    )


def _policy():
    return ExitPolicy(
        version="exit-v1",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(TakeProfitLevel("tp1", 20.0, 0.5),),
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


def _take_profit_decision(position=None):
    position = position or _position()
    policy = _policy()
    state = create_exit_state(position, policy)
    decision = assess_exit(position, _features(), _context(), state, policy)
    assert decision.action is DecisionAction.REDUCE
    assert decision.primary_reason is ExitReasonCode.TAKE_PROFIT_TRIGGERED
    assert decision.target_quantity == 250.0
    return policy, decision


def _reduced(position, quantity, *, updated_at=AS_OF + 1):
    if quantity == 0.0:
        return replace(
            position,
            state=PaperPositionState.CLOSED,
            quantity=0.0,
            open_cost_basis_usd=0.0,
            unrealized_pnl_usd=0.0,
            updated_at_unix_ms=updated_at,
            closed_at_unix_ms=updated_at,
            last_mark_price_usd=None,
            last_mark_at_unix_ms=None,
            sell_fill_count=position.sell_fill_count + 1,
        )
    fraction = quantity / position.quantity
    return replace(
        position,
        quantity=quantity,
        open_cost_basis_usd=position.open_cost_basis_usd * fraction,
        updated_at_unix_ms=updated_at,
        sell_fill_count=position.sell_fill_count + 1,
    )


def test_hold_and_non_take_profit_decisions_never_complete_take_profit_levels():
    position = _position()
    policy = _policy()
    state = create_exit_state(position, policy)
    hold = assess_exit(position, _features(price_usd=1.10), _context(), state, policy)
    assert hold.action is DecisionAction.HOLD
    assert acknowledge_exit_fill(hold.next_state, hold, position, position) == hold.next_state

    hard_stop = assess_exit(position, _features(price_usd=0.90), _context(), state, policy)
    assert hard_stop.primary_reason is ExitReasonCode.HARD_STOP_TRIGGERED
    closed = _reduced(position, 0.0)
    assert acknowledge_exit_fill(hard_stop.next_state, hard_stop, position, closed) == hard_stop.next_state


def test_acknowledgement_rejects_identity_policy_and_quantity_contradictions():
    position = _position()
    _, decision = _take_profit_decision(position)
    state = decision.next_state
    after = _reduced(position, 250.0)

    with pytest.raises(ValueError, match="state"):
        acknowledge_exit_fill(replace(state, position_id="other"), decision, position, after)
    with pytest.raises(ValueError, match="policy"):
        acknowledge_exit_fill(replace(state, policy_version="other"), decision, position, after)
    with pytest.raises(ValueError, match="before"):
        acknowledge_exit_fill(
            state,
            decision,
            replace(position, position_id="other"),
            after,
        )
    with pytest.raises(ValueError, match="after"):
        acknowledge_exit_fill(
            state,
            decision,
            position,
            replace(after, position_id="other"),
        )
    with pytest.raises(ValueError, match="mint"):
        acknowledge_exit_fill(
            state,
            decision,
            position,
            replace(after, mint="OtherMint"),
        )

    increased = replace(
        position,
        quantity=501.0,
        open_cost_basis_usd=502.503,
        updated_at_unix_ms=AS_OF + 1,
        buy_fill_count=2,
    )
    with pytest.raises(ValueError, match="increase"):
        acknowledge_exit_fill(state, decision, position, increased)


def test_failed_or_partial_below_target_fill_keeps_level_incomplete():
    position = _position()
    _, decision = _take_profit_decision(position)

    no_fill = acknowledge_exit_fill(
        decision.next_state,
        decision,
        position,
        position,
    )
    assert no_fill.completed_take_profit_levels == frozenset()

    partial = _reduced(position, 300.0)  # actual reduction 200 < target 250
    partial_state = acknowledge_exit_fill(
        decision.next_state,
        decision,
        position,
        partial,
    )
    assert partial_state.completed_take_profit_levels == frozenset()


def test_exact_or_larger_booked_reduction_completes_level_and_is_idempotent():
    position = _position()
    _, decision = _take_profit_decision(position)
    original_high_water = decision.next_state.high_water_price_usd
    original_high_water_at = decision.next_state.high_water_at_unix_ms

    exact = _reduced(position, 250.0)
    completed = acknowledge_exit_fill(
        decision.next_state,
        decision,
        position,
        exact,
    )
    assert completed.completed_take_profit_levels == frozenset({"tp1"})
    assert decision.next_state.completed_take_profit_levels == frozenset()
    assert completed.high_water_price_usd == original_high_water
    assert completed.high_water_at_unix_ms == original_high_water_at

    repeated = acknowledge_exit_fill(completed, decision, position, exact)
    assert repeated == completed

    beyond = _reduced(position, 200.0)  # actual reduction 300 > target 250
    beyond_completed = acknowledge_exit_fill(
        decision.next_state,
        decision,
        position,
        beyond,
    )
    assert beyond_completed.completed_take_profit_levels == frozenset({"tp1"})


def test_full_close_completes_take_profit_level_from_authoritative_c3_quantity():
    position = _position()
    _, decision = _take_profit_decision(position)
    closed = _reduced(position, 0.0)

    completed = acknowledge_exit_fill(
        decision.next_state,
        decision,
        position,
        closed,
    )
    assert completed.completed_take_profit_levels == frozenset({"tp1"})
