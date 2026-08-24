from dataclasses import replace

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.exits import (
    ExitExecutionContext,
    ExitPolicy,
    ExitReasonCode,
    ExitRouteState,
    TakeProfitLevel,
    create_exit_state,
)
from shreks_brain.features import FeatureVector
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedgerUpdateState,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
)
from shreks_brain.paper_loop.engine import create_paper_loop_state, run_paper_cycle
from shreks_brain.paper_loop.models import (
    ManagedPaperPosition,
    PaperCycleInput,
    PaperExitObservation,
    PaperLoopPolicy,
    PaperLoopReasonCode,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision


OPEN_INTENT_AT = 1_000_000
OPEN_FILL_AT = 1_001_000
EXIT_AT = 1_010_000
MINT = "Mint111"


def _paper_policy(*, latency_ms: int = 1_000, max_quote_lag_ms: int = 5_000) -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-v1-test",
        assumed_latency_ms=latency_ms,
        max_quote_lag_ms=max_quote_lag_ms,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.10,
    )


def _loop_policy() -> PaperLoopPolicy:
    return PaperLoopPolicy(version="loop-v1-test", exit_max_slippage_bps=300)


def _exit_policy() -> ExitPolicy:
    return ExitPolicy(
        version="exit-v1-test",
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


def _features(as_of: int, *, price: float) -> FeatureVector:
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=as_of,
        source_age_ms=0,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=600.0,
        price_usd=price,
        liquidity_usd=100_000.0,
        liquidity_change_5m_pct=0.0,
        exit_price_impact_pct=1.0,
        volume_m5_usd=20_000.0,
        volume_h1_usd=100_000.0,
        volume_velocity_ratio=1.0,
        tx_count_m5=100,
        tx_count_h1=500,
        buy_fraction_m5=0.55,
        buy_fraction_h1=0.55,
        buy_sell_ratio_m5=1.2,
        buy_sell_ratio_h1=1.2,
        buy_pressure_acceleration=0.0,
        return_1m_pct=0.0,
        return_5m_pct=0.0,
        return_15m_pct=0.0,
        momentum_acceleration_1m_vs_5m=0.0,
        distance_from_local_high_pct=-2.0,
        range_position_pct=70.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )


def _exit_context(as_of: int, *, global_halt: bool = False) -> ExitExecutionContext:
    return ExitExecutionContext(
        as_of_unix_ms=as_of,
        observed_at_unix_ms=as_of,
        route_state=ExitRouteState.AVAILABLE,
        available_exit_notional_usd=None,
        expected_exit_price_impact_pct=None,
        price_impact_notional_usd=None,
        wallet_distribution_detected=None,
        global_halt_active=global_halt,
    )


def _observation(
    state,
    as_of: int,
    *,
    price: float,
    global_halt: bool = False,
) -> PaperExitObservation:
    return PaperExitObservation(
        position_id=state.managed_positions[0].position_id,
        features=_features(as_of, price=price),
        execution_context=_exit_context(as_of, global_halt=global_halt),
    )


def _quote(
    observed_at: int,
    *,
    execution_price: float | None = 1.0,
    reference_price: float | None = None,
    quoted_notional: float | None = 10_000.0,
    available_notional: float | None = 10_000.0,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
) -> PaperQuote:
    return PaperQuote(
        provider="paper-test",
        mint=MINT,
        observed_at_unix_ms=observed_at,
        state=state,
        reference_price_usd=(
            execution_price if reference_price is None else reference_price
        ),
        execution_price_usd=execution_price,
        quoted_notional_usd=quoted_notional,
        available_notional_usd=available_notional,
    )


def _buy_intent() -> TradeIntent:
    return TradeIntent(
        mint=MINT,
        side=TradeSide.BUY,
        requested_notional_usd=500.0,
        max_slippage_bps=300,
        strategy_name="fresh_launch_continuation",
        strategy_version="fresh-v1-test",
        score_policy_version="score-v1-test",
        decision_policy_version="decision-v1-test",
        risk_policy_version="risk-v1-test",
        reason="ENTRY_APPROVED",
        idempotency_key="entry-key",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=OPEN_INTENT_AT,
    )


def _open_state(*, latency_ms: int = 1_000, max_quote_lag_ms: int = 5_000):
    paper_policy = _paper_policy(
        latency_ms=latency_ms,
        max_quote_lag_ms=max_quote_lag_ms,
    )
    ledger = create_paper_ledger(10_000.0, OPEN_INTENT_AT)
    intent = _buy_intent()
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=OPEN_FILL_AT,
            processed_intent_keys=frozenset(),
            quote=_quote(OPEN_FILL_AT, execution_price=1.0),
        ),
        paper_policy,
    )
    assert execution.state is PaperExecutionState.FILLED
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    position = next(
        position
        for position in update.ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    exit_policy = _exit_policy()
    managed = ManagedPaperPosition(
        position_id=position.position_id,
        exit_policy=exit_policy,
        exit_state=create_exit_state(position, exit_policy),
    )
    return create_paper_loop_state(
        update.ledger,
        _loop_policy(),
        paper_policy,
        managed_positions=(managed,),
    )


def _cycle(state, as_of: int, *, observation=None, quote=None):
    observations = () if observation is None else (observation,)
    quotes = () if quote is None else (quote,)
    return run_paper_cycle(
        state,
        PaperCycleInput(
            as_of_unix_ms=as_of,
            entry_candidates=(),
            exit_observations=observations,
            quotes=quotes,
        ),
    )


def _position(state):
    return next(
        position
        for position in state.ledger.positions
        if position.state is PaperPositionState.OPEN
    )


def test_missing_exit_observation_without_pending_does_not_invent_hold() -> None:
    state = _open_state()
    result = _cycle(state, EXIT_AT)
    assert len(result.exit_results) == 1
    item = result.exit_results[0]
    assert item.exit_assessment is None
    assert item.intent is None
    assert item.reason is PaperLoopReasonCode.EXIT_OBSERVATION_MISSING
    assert result.next_state.managed_positions[0].exit_state is state.managed_positions[0].exit_state
    assert result.next_state.managed_positions[0].pending_exit is None


def test_hold_updates_exit_state_and_marks_from_usable_price() -> None:
    state = _open_state()
    result = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.10),
    )
    item = result.exit_results[0]
    assert item.exit_assessment is not None
    assert item.exit_assessment.action is DecisionAction.HOLD
    assert item.reason is PaperLoopReasonCode.EXIT_HOLD
    assert item.mark_ledger_update is not None
    assert result.next_state.managed_positions[0].pending_exit is None
    assert _position(result.next_state).last_mark_price_usd == pytest.approx(1.10)


def test_reduce_without_quote_persists_original_exit_decision() -> None:
    state = _open_state()
    result = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    item = result.exit_results[0]
    assert item.exit_assessment is not None
    assert item.exit_assessment.action is DecisionAction.REDUCE
    assert item.intent is None
    assert item.reason is PaperLoopReasonCode.EXIT_QUOTE_MISSING
    pending = result.next_state.managed_positions[0].pending_exit
    assert pending is item.exit_assessment
    assert pending.as_of_unix_ms == EXIT_AT


def test_pending_reduce_survives_next_hold_and_uses_original_latency_clock() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    pending = first.next_state.managed_positions[0].pending_exit
    assert pending is not None

    second_at = EXIT_AT + 1_000
    second = _cycle(
        first.next_state,
        second_at,
        observation=_observation(first.next_state, second_at, price=1.10),
        quote=_quote(second_at, execution_price=0.90),
    )
    item = second.exit_results[0]
    assert item.exit_assessment is not None
    assert item.exit_assessment.action is DecisionAction.HOLD
    assert item.intent is not None
    assert item.intent.as_of_unix_ms == EXIT_AT
    assert item.intent.requested_notional_usd == pytest.approx(
        pending.target_quantity * 0.90
    )
    assert item.execution is not None
    assert item.execution.fill is not None
    assert item.execution.fill.quantity <= pending.target_quantity + 1e-12


def test_quote_before_original_latency_keeps_pending_and_builds_no_sell() -> None:
    state = _open_state(latency_ms=2_000)
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    quote_at = EXIT_AT + 1_999
    second = _cycle(
        first.next_state,
        quote_at,
        observation=_observation(first.next_state, quote_at, price=1.10),
        quote=_quote(quote_at, execution_price=0.95),
    )
    item = second.exit_results[0]
    assert item.intent is None
    assert item.execution is None
    assert item.reason is PaperLoopReasonCode.EXIT_QUOTE_BEFORE_LATENCY
    assert second.next_state.managed_positions[0].pending_exit is not None
    assert second.next_state.managed_positions[0].pending_exit.as_of_unix_ms == EXIT_AT


def test_future_quote_is_not_consumed_and_pending_survives() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    cycle_at = EXIT_AT + 500
    future = _quote(cycle_at + 1, execution_price=None, quoted_notional=None, available_notional=None)
    second = _cycle(
        first.next_state,
        cycle_at,
        observation=_observation(first.next_state, cycle_at, price=1.10),
        quote=future,
    )
    item = second.exit_results[0]
    assert item.reason is PaperLoopReasonCode.EXIT_QUOTE_AFTER_CYCLE
    assert item.intent is None
    assert second.next_state.managed_positions[0].pending_exit is not None


def test_missing_execution_price_does_not_fabricate_sell_notional() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    eligible_at = EXIT_AT + 1_000
    second = _cycle(
        first.next_state,
        eligible_at,
        observation=_observation(first.next_state, eligible_at, price=1.10),
        quote=_quote(
            eligible_at,
            execution_price=None,
            reference_price=None,
            quoted_notional=10_000.0,
            available_notional=10_000.0,
        ),
    )
    item = second.exit_results[0]
    assert item.reason is PaperLoopReasonCode.EXIT_EXECUTION_PRICE_UNAVAILABLE
    assert item.intent is None
    assert item.execution is None
    assert second.next_state.managed_positions[0].pending_exit is not None


def test_quote_size_limit_books_only_actual_partial_quantity_and_does_not_complete_tp() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    pending = first.next_state.managed_positions[0].pending_exit
    assert pending is not None
    eligible_at = EXIT_AT + 1_000
    before_qty = _position(first.next_state).quantity
    second = _cycle(
        first.next_state,
        eligible_at,
        observation=_observation(first.next_state, eligible_at, price=1.20),
        quote=_quote(
            eligible_at,
            execution_price=1.0,
            quoted_notional=100.0,
            available_notional=10_000.0,
        ),
    )
    item = second.exit_results[0]
    assert item.execution is not None
    assert item.execution.state is PaperExecutionState.PARTIAL
    assert item.execution.fill is not None
    assert item.execution.fill.quantity == pytest.approx(100.0)
    assert item.execution.fill.quantity < pending.target_quantity
    assert _position(second.next_state).quantity == pytest.approx(before_qty - 100.0)
    assert "tp1" not in second.next_state.managed_positions[0].exit_state.completed_take_profit_levels
    assert second.next_state.managed_positions[0].pending_exit is None


def test_exact_tp_target_completes_only_after_c3_booking() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    pending = first.next_state.managed_positions[0].pending_exit
    assert pending is not None
    assert "tp1" not in first.next_state.managed_positions[0].exit_state.completed_take_profit_levels

    eligible_at = EXIT_AT + 1_000
    second = _cycle(
        first.next_state,
        eligible_at,
        observation=_observation(first.next_state, eligible_at, price=1.20),
        quote=_quote(eligible_at, execution_price=1.0),
    )
    item = second.exit_results[0]
    assert item.execution_ledger_update is not None
    assert item.execution_ledger_update.state is PaperLedgerUpdateState.APPLIED
    assert item.execution is not None and item.execution.fill is not None
    assert item.execution.fill.quantity == pytest.approx(pending.target_quantity)
    assert "tp1" in second.next_state.managed_positions[0].exit_state.completed_take_profit_levels


def test_newer_full_exit_supersedes_pending_reduce_without_backdating() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    assert first.next_state.managed_positions[0].pending_exit is not None
    assert first.next_state.managed_positions[0].pending_exit.action is DecisionAction.REDUCE

    emergency_at = EXIT_AT + 500
    second = _cycle(
        first.next_state,
        emergency_at,
        observation=_observation(
            first.next_state,
            emergency_at,
            price=1.10,
            global_halt=True,
        ),
    )
    pending = second.next_state.managed_positions[0].pending_exit
    assert pending is not None
    assert pending.action is DecisionAction.EXIT
    assert pending.primary_reason is ExitReasonCode.GLOBAL_HALT_EXIT
    assert pending.as_of_unix_ms == emergency_at

    eligible_at = emergency_at + 1_000
    third = _cycle(
        second.next_state,
        eligible_at,
        observation=_observation(second.next_state, eligible_at, price=1.10),
        quote=_quote(eligible_at, execution_price=1.0),
    )
    item = third.exit_results[0]
    assert item.intent is not None
    assert item.intent.as_of_unix_ms == emergency_at
    assert item.intent.reason == ExitReasonCode.GLOBAL_HALT_EXIT.value
    assert not third.next_state.managed_positions
    assert all(position.state is PaperPositionState.CLOSED for position in third.next_state.ledger.positions)


def test_pending_full_exit_is_not_weakened_by_fresh_hold() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.10, global_halt=True),
    )
    pending = first.next_state.managed_positions[0].pending_exit
    assert pending is not None and pending.action is DecisionAction.EXIT

    next_at = EXIT_AT + 500
    second = _cycle(
        first.next_state,
        next_at,
        observation=_observation(first.next_state, next_at, price=1.10),
    )
    retained = second.next_state.managed_positions[0].pending_exit
    assert retained is not None
    assert retained.as_of_unix_ms == EXIT_AT
    assert retained.action is DecisionAction.EXIT


def test_missing_current_observation_can_retry_already_authorized_pending_exit() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    pending = first.next_state.managed_positions[0].pending_exit
    assert pending is not None
    eligible_at = EXIT_AT + 1_000
    second = _cycle(
        first.next_state,
        eligible_at,
        quote=_quote(eligible_at, execution_price=1.0),
    )
    item = second.exit_results[0]
    assert item.exit_assessment is None
    assert item.intent is not None
    assert item.execution is not None
    assert item.execution.fill is not None
    assert item.execution.fill.quantity <= pending.target_quantity + 1e-12


def test_failed_after_submission_books_network_cost_clears_pending_and_does_not_complete_tp() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    eligible_at = EXIT_AT + 1_000
    cash_before = first.next_state.ledger.cash_balance_usd
    second = _cycle(
        first.next_state,
        eligible_at,
        observation=_observation(first.next_state, eligible_at, price=1.20),
        quote=_quote(
            eligible_at,
            execution_price=1.0,
            state=PaperQuoteState.FAILED_AFTER_SUBMISSION,
        ),
    )
    item = second.exit_results[0]
    assert item.execution is not None
    assert item.execution.state is PaperExecutionState.FAILED
    assert item.execution.findings[0].code is PaperExecutionReasonCode.SIMULATED_SUBMISSION_FAILED
    assert second.next_state.ledger.cash_balance_usd == pytest.approx(
        cash_before - state.paper_fill_policy.network_fee_usd
    )
    assert second.next_state.managed_positions[0].pending_exit is None
    assert "tp1" not in second.next_state.managed_positions[0].exit_state.completed_take_profit_levels


def test_late_quote_is_passed_to_c1_for_terminal_quote_too_late_evidence() -> None:
    state = _open_state(max_quote_lag_ms=2_000)
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    late_at = EXIT_AT + 3_001
    second = _cycle(
        first.next_state,
        late_at,
        observation=_observation(first.next_state, late_at, price=1.10),
        quote=_quote(late_at, execution_price=1.0),
    )
    item = second.exit_results[0]
    assert item.intent is not None
    assert item.execution is not None
    assert item.execution.state is PaperExecutionState.FAILED
    assert item.execution.findings[0].code is PaperExecutionReasonCode.QUOTE_TOO_LATE
    assert second.next_state.managed_positions[0].pending_exit is None


def test_exit_intent_reuses_lifecycle_entry_versions_and_key_ignores_quote_price() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, price=1.20),
    )
    pending = first.next_state.managed_positions[0].pending_exit
    assert pending is not None

    eligible_at = EXIT_AT + 1_000
    low_price = _cycle(
        first.next_state,
        eligible_at,
        quote=_quote(eligible_at, execution_price=0.80),
    )
    low_intent = low_price.exit_results[0].intent
    assert low_intent is not None
    assert low_intent.strategy_name == "fresh_launch_continuation"
    assert low_intent.strategy_version == "fresh-v1-test"
    assert low_intent.score_policy_version == "score-v1-test"
    assert low_intent.decision_policy_version == "decision-v1-test"
    assert low_intent.risk_policy_version == "risk-v1-test"
    assert low_intent.requested_notional_usd == pytest.approx(pending.target_quantity * 0.80)

    # Re-evaluate from the same immutable pre-execution state with a different quote.
    high_price = _cycle(
        first.next_state,
        eligible_at,
        quote=_quote(eligible_at, execution_price=1.10),
    )
    high_intent = high_price.exit_results[0].intent
    assert high_intent is not None
    assert high_intent.requested_notional_usd == pytest.approx(pending.target_quantity * 1.10)
    assert high_intent.idempotency_key == low_intent.idempotency_key
