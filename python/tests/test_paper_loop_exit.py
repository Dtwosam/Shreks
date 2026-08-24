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
OPEN_FILL_AT = 1_002_000
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
    return PaperLoopPolicy("loop-v1-test", 300)


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


def _features(as_of: int, price: float) -> FeatureVector:
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


def _context(as_of: int, *, global_halt: bool = False) -> ExitExecutionContext:
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


def _observation(state, as_of: int, price: float, *, global_halt: bool = False):
    return PaperExitObservation(
        state.managed_positions[0].position_id,
        _features(as_of, price),
        _context(as_of, global_halt=global_halt),
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
        reference_price_usd=(execution_price if reference_price is None else reference_price),
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
    paper_policy = _paper_policy(latency_ms=latency_ms, max_quote_lag_ms=max_quote_lag_ms)
    ledger = create_paper_ledger(10_000.0, OPEN_INTENT_AT)
    intent = _buy_intent()
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=OPEN_FILL_AT,
            processed_intent_keys=frozenset(),
            quote=_quote(OPEN_FILL_AT),
        ),
        paper_policy,
    )
    assert execution.state is PaperExecutionState.FILLED
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    position = next(p for p in update.ledger.positions if p.state is PaperPositionState.OPEN)
    policy = _exit_policy()
    managed = ManagedPaperPosition(
        position.position_id,
        policy,
        create_exit_state(position, policy),
    )
    return create_paper_loop_state(
        update.ledger,
        _loop_policy(),
        paper_policy,
        managed_positions=(managed,),
    )


def _cycle(state, as_of: int, *, observation=None, quote=None):
    return run_paper_cycle(
        state,
        PaperCycleInput(
            as_of,
            (),
            () if observation is None else (observation,),
            () if quote is None else (quote,),
        ),
    )


def _open_position(state):
    return next(p for p in state.ledger.positions if p.state is PaperPositionState.OPEN)


def _create_pending_reduce(state):
    result = _cycle(state, EXIT_AT, observation=_observation(state, EXIT_AT, 1.20))
    pending = result.next_state.managed_positions[0].pending_exit
    assert pending is not None
    assert pending.action is DecisionAction.REDUCE
    return result, pending


def test_missing_observation_without_pending_does_not_invent_hold() -> None:
    state = _open_state()
    result = _cycle(state, EXIT_AT)
    assert len(result.exit_results) == 1
    item = result.exit_results[0]
    assert item.exit_assessment is None
    assert item.intent is None
    assert item.reason is PaperLoopReasonCode.EXIT_OBSERVATION_MISSING
    assert result.next_state.managed_positions[0].pending_exit is None


def test_hold_updates_exit_state_and_marks_from_usable_price() -> None:
    state = _open_state()
    result = _cycle(state, EXIT_AT, observation=_observation(state, EXIT_AT, 1.10))
    item = result.exit_results[0]
    assert item.exit_assessment is not None
    assert item.exit_assessment.action is DecisionAction.HOLD
    assert item.reason is PaperLoopReasonCode.EXIT_HOLD
    assert item.mark_ledger_update is not None
    assert _open_position(result.next_state).last_mark_price_usd == pytest.approx(1.10)


def test_reduce_without_quote_persists_original_decision() -> None:
    state = _open_state()
    result, pending = _create_pending_reduce(state)
    item = result.exit_results[0]
    assert item.reason is PaperLoopReasonCode.EXIT_QUOTE_MISSING
    assert item.intent is None
    assert pending.as_of_unix_ms == EXIT_AT


def test_pending_reduce_survives_hold_and_rebuilds_notional_from_later_quote() -> None:
    state = _open_state()
    first, pending = _create_pending_reduce(state)
    second_at = EXIT_AT + 1_000
    second = _cycle(
        first.next_state,
        second_at,
        observation=_observation(first.next_state, second_at, 1.10),
        quote=_quote(second_at, execution_price=0.90),
    )
    item = second.exit_results[0]
    assert item.exit_assessment is not None and item.exit_assessment.action is DecisionAction.HOLD
    assert item.intent is not None
    assert item.intent.as_of_unix_ms == EXIT_AT
    assert item.intent.requested_notional_usd == pytest.approx(pending.target_quantity * 0.90)
    assert item.execution is not None and item.execution.fill is not None
    assert item.execution.fill.quantity <= pending.target_quantity + 1e-12


def test_quote_before_original_latency_keeps_pending_and_builds_no_sell() -> None:
    state = _open_state(latency_ms=2_000)
    first, _ = _create_pending_reduce(state)
    quote_at = EXIT_AT + 1_999
    second = _cycle(
        first.next_state,
        quote_at,
        observation=_observation(first.next_state, quote_at, 1.10),
        quote=_quote(quote_at, execution_price=0.95),
    )
    item = second.exit_results[0]
    assert item.reason is PaperLoopReasonCode.EXIT_QUOTE_BEFORE_LATENCY
    assert item.intent is None
    assert second.next_state.managed_positions[0].pending_exit.as_of_unix_ms == EXIT_AT


@pytest.mark.parametrize(
    ("quote", "reason"),
    (
        (_quote(EXIT_AT + 501, execution_price=None, quoted_notional=None, available_notional=None), PaperLoopReasonCode.EXIT_QUOTE_AFTER_CYCLE),
        (_quote(EXIT_AT + 1_000, execution_price=None), PaperLoopReasonCode.EXIT_EXECUTION_PRICE_UNAVAILABLE),
    ),
)
def test_future_or_unpriced_quote_cannot_fabricate_sell(quote: PaperQuote, reason: PaperLoopReasonCode) -> None:
    state = _open_state()
    first, _ = _create_pending_reduce(state)
    cycle_at = EXIT_AT + (500 if reason is PaperLoopReasonCode.EXIT_QUOTE_AFTER_CYCLE else 1_000)
    second = _cycle(
        first.next_state,
        cycle_at,
        observation=_observation(first.next_state, cycle_at, 1.10),
        quote=quote,
    )
    item = second.exit_results[0]
    assert item.reason is reason
    assert item.intent is None
    assert second.next_state.managed_positions[0].pending_exit is not None


def test_quote_limited_partial_sell_books_actual_quantity_and_does_not_complete_tp() -> None:
    state = _open_state()
    first, pending = _create_pending_reduce(state)
    eligible = EXIT_AT + 1_000
    before_qty = _open_position(first.next_state).quantity
    second = _cycle(
        first.next_state,
        eligible,
        observation=_observation(first.next_state, eligible, 1.20),
        quote=_quote(eligible, quoted_notional=100.0),
    )
    item = second.exit_results[0]
    assert item.execution is not None and item.execution.state is PaperExecutionState.PARTIAL
    assert item.execution.fill is not None and item.execution.fill.quantity == pytest.approx(100.0)
    assert item.execution.fill.quantity < pending.target_quantity
    assert _open_position(second.next_state).quantity == pytest.approx(before_qty - 100.0)
    assert "tp1" not in second.next_state.managed_positions[0].exit_state.completed_take_profit_levels
    assert second.next_state.managed_positions[0].pending_exit is None


def test_exact_tp_target_completes_only_after_c3_booking() -> None:
    state = _open_state()
    first, pending = _create_pending_reduce(state)
    assert "tp1" not in first.next_state.managed_positions[0].exit_state.completed_take_profit_levels
    eligible = EXIT_AT + 1_000
    second = _cycle(
        first.next_state,
        eligible,
        observation=_observation(first.next_state, eligible, 1.20),
        quote=_quote(eligible),
    )
    item = second.exit_results[0]
    assert item.execution_ledger_update is not None
    assert item.execution_ledger_update.state is PaperLedgerUpdateState.APPLIED
    assert item.execution.fill.quantity == pytest.approx(pending.target_quantity)
    assert "tp1" in second.next_state.managed_positions[0].exit_state.completed_take_profit_levels


def test_newer_full_exit_supersedes_pending_reduce_without_backdating() -> None:
    state = _open_state()
    first, _ = _create_pending_reduce(state)
    emergency_at = EXIT_AT + 500
    second = _cycle(
        first.next_state,
        emergency_at,
        observation=_observation(first.next_state, emergency_at, 1.10, global_halt=True),
    )
    pending = second.next_state.managed_positions[0].pending_exit
    assert pending is not None
    assert pending.action is DecisionAction.EXIT
    assert pending.primary_reason is ExitReasonCode.GLOBAL_HALT_EXIT
    assert pending.as_of_unix_ms == emergency_at

    eligible = emergency_at + 1_000
    third = _cycle(
        second.next_state,
        eligible,
        observation=_observation(second.next_state, eligible, 1.10),
        quote=_quote(eligible),
    )
    item = third.exit_results[0]
    assert item.intent is not None and item.intent.as_of_unix_ms == emergency_at
    assert item.intent.reason == ExitReasonCode.GLOBAL_HALT_EXIT.value
    assert not third.next_state.managed_positions
    assert all(p.state is PaperPositionState.CLOSED for p in third.next_state.ledger.positions)


def test_pending_full_exit_is_not_weakened_and_can_retry_without_new_observation() -> None:
    state = _open_state()
    first = _cycle(
        state,
        EXIT_AT,
        observation=_observation(state, EXIT_AT, 1.10, global_halt=True),
    )
    pending = first.next_state.managed_positions[0].pending_exit
    assert pending is not None and pending.action is DecisionAction.EXIT

    eligible = EXIT_AT + 1_000
    second = _cycle(first.next_state, eligible, quote=_quote(eligible))
    item = second.exit_results[0]
    assert item.exit_assessment is None
    assert item.intent is not None and item.intent.as_of_unix_ms == EXIT_AT
    assert not second.next_state.managed_positions


def test_failed_submission_books_network_cost_clears_pending_and_not_tp() -> None:
    state = _open_state()
    first, _ = _create_pending_reduce(state)
    eligible = EXIT_AT + 1_000
    cash_before = first.next_state.ledger.cash_balance_usd
    second = _cycle(
        first.next_state,
        eligible,
        observation=_observation(first.next_state, eligible, 1.20),
        quote=_quote(eligible, state=PaperQuoteState.FAILED_AFTER_SUBMISSION),
    )
    item = second.exit_results[0]
    assert item.execution is not None and item.execution.state is PaperExecutionState.FAILED
    assert item.execution.findings[0].code is PaperExecutionReasonCode.SIMULATED_SUBMISSION_FAILED
    assert second.next_state.ledger.cash_balance_usd == pytest.approx(
        cash_before - state.paper_fill_policy.network_fee_usd
    )
    assert second.next_state.managed_positions[0].pending_exit is None
    assert "tp1" not in second.next_state.managed_positions[0].exit_state.completed_take_profit_levels


def test_late_quote_is_passed_to_c1_for_quote_too_late_terminal_evidence() -> None:
    state = _open_state(max_quote_lag_ms=2_000)
    first, _ = _create_pending_reduce(state)
    late = EXIT_AT + 3_001
    second = _cycle(
        first.next_state,
        late,
        observation=_observation(first.next_state, late, 1.10),
        quote=_quote(late),
    )
    item = second.exit_results[0]
    assert item.intent is not None
    assert item.execution is not None and item.execution.state is PaperExecutionState.FAILED
    assert item.execution.findings[0].code is PaperExecutionReasonCode.QUOTE_TOO_LATE
    assert second.next_state.managed_positions[0].pending_exit is None


def test_exit_key_is_decision_stable_while_notional_tracks_quote_price_and_metadata() -> None:
    state = _open_state()
    first, pending = _create_pending_reduce(state)
    eligible = EXIT_AT + 1_000

    low = _cycle(first.next_state, eligible, quote=_quote(eligible, execution_price=0.80))
    low_intent = low.exit_results[0].intent
    assert low_intent is not None
    assert low_intent.strategy_name == "fresh_launch_continuation"
    assert low_intent.strategy_version == "fresh-v1-test"
    assert low_intent.score_policy_version == "score-v1-test"
    assert low_intent.decision_policy_version == "decision-v1-test"
    assert low_intent.risk_policy_version == "risk-v1-test"
    assert low_intent.requested_notional_usd == pytest.approx(pending.target_quantity * 0.80)

    high = _cycle(first.next_state, eligible, quote=_quote(eligible, execution_price=1.10))
    high_intent = high.exit_results[0].intent
    assert high_intent is not None
    assert high_intent.requested_notional_usd == pytest.approx(pending.target_quantity * 1.10)
    assert high_intent.idempotency_key == low_intent.idempotency_key
