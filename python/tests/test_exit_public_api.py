from dataclasses import fields, replace
import inspect

import shreks_brain.exits as exits
from shreks_brain.decision import DecisionAction
from shreks_brain.exits import (
    ExitAssessment,
    ExitExecutionContext,
    ExitFinding,
    ExitPolicy,
    ExitReasonCode,
    ExitRouteState,
    ExitState,
    TakeProfitLevel,
    acknowledge_exit_fill,
    assess_exit,
    create_exit_state,
)
from shreks_brain.features import FeatureVector
from shreks_brain.paper import PaperPosition, PaperPositionState
from shreks_brain.safety import SafetyDecision


EXPECTED_EXPORTS = (
    "ExitAssessment",
    "ExitExecutionContext",
    "ExitFinding",
    "ExitPolicy",
    "ExitReasonCode",
    "ExitRouteState",
    "ExitState",
    "TakeProfitLevel",
    "acknowledge_exit_fill",
    "assess_exit",
    "create_exit_state",
)


def _position():
    return PaperPosition(
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


def _features():
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=1_010_000,
        source_observed_at_unix_ms=1_009_900,
        source_age_ms=100,
        safety_policy_version="safety-test",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=100.0,
        price_usd=1.20,
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
        as_of_unix_ms=1_010_000,
        observed_at_unix_ms=1_009_900,
        route_state=ExitRouteState.AVAILABLE,
        available_exit_notional_usd=1_000.0,
        expected_exit_price_impact_pct=2.0,
        price_impact_notional_usd=500.0,
        wallet_distribution_detected=None,
        global_halt_active=False,
    )


def _policy():
    return ExitPolicy(
        version="exit-v1",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=None,
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


def test_public_exit_api_is_exact_and_callable_end_to_end():
    assert exits.__all__ == EXPECTED_EXPORTS
    assert callable(create_exit_state)
    assert callable(assess_exit)
    assert callable(acknowledge_exit_fill)

    position = _position()
    state = create_exit_state(position, _policy())
    decision = assess_exit(position, _features(), _context(), state, _policy())
    assert isinstance(state, ExitState)
    assert isinstance(decision, ExitAssessment)
    assert isinstance(decision.findings[0], ExitFinding)
    assert decision.action is DecisionAction.REDUCE
    assert decision.primary_reason is ExitReasonCode.TAKE_PROFIT_TRIGGERED

    after = replace(
        position,
        quantity=250.0,
        open_cost_basis_usd=250.75,
        updated_at_unix_ms=1_010_001,
        sell_fill_count=1,
    )
    acknowledged = acknowledge_exit_fill(
        decision.next_state,
        decision,
        position,
        after,
    )
    assert acknowledged.completed_take_profit_levels == frozenset({"tp1"})


def test_public_exit_surface_contains_no_execution_or_live_authority():
    forbidden = (
        "trade_intent",
        "quote",
        "fill",
        "signature",
        "signer",
        "private_key",
        "secret",
        "transaction",
        "live_execution",
        "sqlite",
        "provider",
        "persistence",
    )
    models = (
        ExitAssessment,
        ExitExecutionContext,
        ExitFinding,
        ExitPolicy,
        ExitState,
        TakeProfitLevel,
    )
    for model in models:
        names = " ".join(field.name for field in fields(model)).lower()
        assert not any(fragment in names for fragment in forbidden)

    for function in (create_exit_state, assess_exit, acknowledge_exit_fill):
        signature = str(inspect.signature(function)).lower()
        assert not any(fragment in signature for fragment in forbidden)
