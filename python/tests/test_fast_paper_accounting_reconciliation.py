from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from shreks_brain.fast_paper import (
    FAST_PAPER_BUY_VERSION,
    FAST_PAPER_POSITION_ACTION_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperBuyApproval,
    FastPaperBuyOutcome,
    FastPaperBuyQuote,
    FastPaperMaterialUpdate,
    FastPaperPositionActionApproval,
    FastPaperPositionActionPolicy,
    FastPaperPositionOutcome,
    FastPaperPositionQuote,
    apply_fast_paper_position_action,
    create_fast_paper_loop_state,
    create_fast_paper_position_action_state,
    execute_fast_paper_buy,
    run_fast_paper_event,
)
from shreks_brain.paper import (
    PaperExecutionState,
    PaperFillPolicy,
    PaperPositionState,
    PaperQuoteState,
    create_paper_ledger,
)
from shreks_brain.paper_validation import (
    FAST_PAPER_RUNTIME_STATE_VERSION,
    AccountingValidationStatus,
    FastPaperRuntimeState,
    load_latest_fast_paper_checkpoint,
    save_fast_paper_checkpoint,
    validate_fast_paper_accounting,
    validate_fast_paper_restart_equivalence,
    validate_paper_ledger,
)
from shreks_brain.risk import RiskContext, RiskPolicy


T0 = 6_000_000
MARKET_KEY = "pump:mint-a:quote-a"
QUOTE_MINT = "quote-a"
CHECKPOINT_DDL = """
CREATE TABLE paper_loop_checkpoints (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    checkpoint_schema_version TEXT NOT NULL,
    state_as_of_unix_ms INTEGER NOT NULL CHECK (state_as_of_unix_ms >= 0),
    created_at_unix_ms INTEGER NOT NULL CHECK (created_at_unix_ms >= 0),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
);
CREATE INDEX idx_paper_loop_checkpoints_run_latest
    ON paper_loop_checkpoints (run_id, sequence DESC);
"""


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="fl7.5-fill-v1",
        assumed_latency_ms=100,
        max_quote_lag_ms=2_000,
        swap_fee_bps=50,
        network_fee_usd=0.05,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
    )


def _position_policy() -> FastPaperPositionActionPolicy:
    return FastPaperPositionActionPolicy(
        version="fl7.5-position-v1",
        max_slippage_bps=600,
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-fl7.5-v1",
        required_decision_policy_version="assessment-v1",
        required_feature_schema_version="state-v1",
        target_position_notional_usd=500.0,
        max_notional_per_position_usd=500.0,
        max_capital_fraction_per_position=1.0,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=5_000.0,
        max_daily_realized_loss_usd=5_000.0,
        max_rolling_drawdown_pct=100.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=0,
        min_liquidity_usd=0.0,
        max_expected_price_impact_pct=100.0,
        max_slippage_bps=1_000,
        max_market_data_age_ms=2_000,
    )


def _risk_context(at: int, *, open_positions: int = 0) -> RiskContext:
    return RiskContext(
        as_of_unix_ms=at,
        trading_capital_usd=20_000.0,
        open_position_count=open_positions,
        aggregate_open_risk_usd=0.0,
        daily_realized_pnl_usd=0.0,
        rolling_drawdown_pct=0.0,
        consecutive_losses=0,
        last_loss_at_unix_ms=None,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=0.0,
        price_impact_notional_usd=10_000.0,
        market_data_age_ms=0,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _assessment(
    action: FastPaperAction,
    *,
    event_id: str,
    sequence: int,
    at: int,
) -> FastPaperActionAssessment:
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=event_id,
        market_key=MARKET_KEY,
        source_sequence=sequence,
        as_of_unix_ms=at,
        strategy_family="impulse-scalp" if action is FastPaperAction.BUY else "longer-runner",
        strategy_version="1",
        action=action,
        reasons=(f"{action.value.lower()}_conditions_met",),
    )


def _record(loop_state, assessment: FastPaperActionAssessment):
    update = FastPaperMaterialUpdate(
        source_event_id=assessment.source_event_id,
        market_key=assessment.market_key,
        source_sequence=assessment.source_sequence,
        as_of_unix_ms=assessment.as_of_unix_ms,
        state_version="state-v1",
        is_material=True,
        material_reason="fl7.5-integration",
    )
    return run_fast_paper_event(
        loop_state,
        update,
        lambda _update: assessment,
    ).next_state


def _buy_approval(assessment: FastPaperActionAssessment) -> FastPaperBuyApproval:
    return FastPaperBuyApproval(
        version=FAST_PAPER_BUY_VERSION,
        assessment=assessment,
        mint="mint-a",
        quote_mint=QUOTE_MINT,
        state_version="state-v1",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.10,
    )


def _buy_quote(at: int) -> FastPaperBuyQuote:
    return FastPaperBuyQuote(
        provider="fl7.5-fixture",
        mint="mint-a",
        quote_mint=QUOTE_MINT,
        observed_at_unix_ms=at,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=10.0,
        execution_price_quote=10.1,
        quoted_base_quantity=10.0,
        available_base_quantity=10.0,
        quote_to_usd_rate=1.0,
    )


def _position_quote(
    at: int,
    *,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
    reference_price: float = 11.0,
    execution_price: float = 10.95,
    quoted_base: float = 100.0,
    available_base: float = 100.0,
) -> FastPaperPositionQuote:
    return FastPaperPositionQuote(
        provider="fl7.5-fixture",
        mint="mint-a",
        quote_mint=QUOTE_MINT,
        observed_at_unix_ms=at,
        state=state,
        reference_price_quote=reference_price,
        execution_price_quote=execution_price,
        quoted_base_quantity=quoted_base,
        available_base_quantity=available_base,
        quote_to_usd_rate=1.0,
    )


def _open_position(ledger):
    values = tuple(
        position for position in ledger.positions if position.state is PaperPositionState.OPEN
    )
    assert len(values) == 1
    return values[0]


def _open_fast_position():
    fill_policy = _fill_policy()
    loop_state = create_fast_paper_loop_state()
    buy_assessment = _assessment(
        FastPaperAction.BUY,
        event_id="event-buy",
        sequence=1,
        at=T0 + 100,
    )
    loop_state = _record(loop_state, buy_assessment)
    approval = _buy_approval(buy_assessment)
    ledger = create_paper_ledger(20_000.0, T0)
    result = execute_fast_paper_buy(
        ledger,
        approval,
        _risk_context(T0 + 200),
        _risk_policy(),
        fill_policy,
        evaluated_at_unix_ms=T0 + 200,
        quote=_buy_quote(T0 + 200),
    )
    assert result.outcome is FastPaperBuyOutcome.FILLED
    assert result.execution is not None
    assert result.execution.state is PaperExecutionState.FILLED
    position = _open_position(result.next_ledger)
    action_state = create_fast_paper_position_action_state(
        position.position_id,
        result.next_ledger.as_of_unix_ms,
    )
    return loop_state, result.next_ledger, action_state, fill_policy


def _exit_approval(
    ledger,
    assessment: FastPaperActionAssessment,
    target: float,
) -> FastPaperPositionActionApproval:
    position = _open_position(ledger)
    return FastPaperPositionActionApproval(
        version=FAST_PAPER_POSITION_ACTION_VERSION,
        assessment=assessment,
        position_id=position.position_id,
        mint=position.mint,
        quote_mint=QUOTE_MINT,
        state_version="state-v1",
        target_base_quantity=target,
    )


def _apply_exit(*, state, approval, ledger, quote, fill_policy, evaluated_at):
    return apply_fast_paper_position_action(
        state=state,
        approval=approval,
        ledger=ledger,
        quote=quote,
        fill_policy=fill_policy,
        policy=_position_policy(),
        evaluated_at_unix_ms=evaluated_at,
    )


def _runtime(loop_state, ledger, action_states, fill_policy, *, at, pending_buy=None):
    return FastPaperRuntimeState(
        version=FAST_PAPER_RUNTIME_STATE_VERSION,
        as_of_unix_ms=at,
        event_loop_state=loop_state,
        ledger=ledger,
        fill_policy=fill_policy,
        position_action_policy=_position_policy(),
        pending_buy=pending_buy,
        position_action_states=tuple(action_states),
    )


def _migrate(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(CHECKPOINT_DDL)


def test_shared_ledger_validator_matches_fast_runtime_accounting() -> None:
    loop_state, ledger, action_state, fill_policy = _open_fast_position()
    runtime = _runtime(
        loop_state,
        ledger,
        (action_state,),
        fill_policy,
        at=ledger.as_of_unix_ms,
    )

    direct = validate_paper_ledger(ledger)
    fast = validate_fast_paper_accounting(runtime)
    assert direct == fast
    assert direct.status is not AccountingValidationStatus.INVALID


def test_realistic_partial_reductions_failure_restart_and_final_sell_reconcile(tmp_path) -> None:
    loop_state, ledger, action_state, fill_policy = _open_fast_position()

    reduce_one_assessment = _assessment(
        FastPaperAction.REDUCE,
        event_id="event-reduce-1",
        sequence=2,
        at=T0 + 300,
    )
    loop_state = _record(loop_state, reduce_one_assessment)
    reduce_one = _exit_approval(ledger, reduce_one_assessment, 4.0)
    first = _apply_exit(
        state=action_state,
        approval=reduce_one,
        ledger=ledger,
        quote=_position_quote(
            T0 + 400,
            quoted_base=2.5,
            available_base=2.5,
        ),
        fill_policy=fill_policy,
        evaluated_at=T0 + 400,
    )
    assert first.outcome is FastPaperPositionOutcome.REDUCED
    assert first.execution is not None
    assert first.execution.state is PaperExecutionState.PARTIAL
    assert first.execution.fill is not None
    assert first.execution.fill.quantity == pytest.approx(2.5)
    ledger = first.next_ledger
    action_state = first.next_state
    assert _open_position(ledger).quantity == pytest.approx(7.5)

    reduce_two_assessment = _assessment(
        FastPaperAction.REDUCE,
        event_id="event-reduce-2",
        sequence=3,
        at=T0 + 500,
    )
    loop_state = _record(loop_state, reduce_two_assessment)
    reduce_two = _exit_approval(ledger, reduce_two_assessment, 2.0)
    second = _apply_exit(
        state=action_state,
        approval=reduce_two,
        ledger=ledger,
        quote=_position_quote(T0 + 600, execution_price=10.85),
        fill_policy=fill_policy,
        evaluated_at=T0 + 600,
    )
    assert second.outcome is FastPaperPositionOutcome.REDUCED
    assert second.execution is not None
    assert second.execution.state is PaperExecutionState.FILLED
    assert first.intent is not None and second.intent is not None
    assert first.intent.idempotency_key != second.intent.idempotency_key
    ledger = second.next_ledger
    action_state = second.next_state
    assert _open_position(ledger).quantity == pytest.approx(5.5)

    failed_sell_assessment = _assessment(
        FastPaperAction.SELL,
        event_id="event-sell-failed",
        sequence=4,
        at=T0 + 700,
    )
    loop_state = _record(loop_state, failed_sell_assessment)
    failed_sell = _exit_approval(
        ledger,
        failed_sell_assessment,
        _open_position(ledger).quantity,
    )
    failed = _apply_exit(
        state=action_state,
        approval=failed_sell,
        ledger=ledger,
        quote=_position_quote(
            T0 + 800,
            state=PaperQuoteState.FAILED_AFTER_SUBMISSION,
            execution_price=10.8,
        ),
        fill_policy=fill_policy,
        evaluated_at=T0 + 800,
    )
    assert failed.outcome is FastPaperPositionOutcome.EXECUTION_FAILED
    assert failed.execution is not None
    assert failed.execution.state is PaperExecutionState.FAILED
    assert failed.execution.network_fee_usd == pytest.approx(fill_policy.network_fee_usd)
    assert failed.intent is not None
    failed_key = failed.intent.idempotency_key
    ledger = failed.next_ledger
    action_state = failed.next_state
    assert failed_key in ledger.processed_intent_keys
    assert _open_position(ledger).quantity == pytest.approx(5.5)

    before_restart = _runtime(
        loop_state,
        ledger,
        (action_state,),
        fill_policy,
        at=T0 + 800,
    )
    mid_report = validate_fast_paper_accounting(before_restart)
    assert mid_report.status is not AccountingValidationStatus.INVALID
    assert mid_report.partial_reduction_count >= 2
    assert mid_report.terminal_failure_count >= 1
    assert mid_report.accumulated_costs_usd > 0.0

    database = tmp_path / "fl7.5-restart.sqlite3"
    _migrate(database)
    saved = save_fast_paper_checkpoint(
        database,
        "fl7.5-run",
        1,
        before_restart,
        T0 + 850,
    )
    del before_restart

    restored_record = load_latest_fast_paper_checkpoint(database, "fl7.5-run")
    assert restored_record is not None
    restored = restored_record.state
    restart = validate_fast_paper_restart_equivalence(saved.state, restored)
    assert restart.equivalent
    assert failed_key in restored.ledger.processed_intent_keys

    replay = _apply_exit(
        state=restored.position_action_states[0],
        approval=failed_sell,
        ledger=restored.ledger,
        quote=_position_quote(T0 + 860, execution_price=10.75),
        fill_policy=restored.fill_policy,
        evaluated_at=T0 + 860,
    )
    assert replay.outcome is FastPaperPositionOutcome.ALREADY_PROCESSED
    assert len(replay.next_ledger.entries) == len(restored.ledger.entries)

    final_sell_assessment = _assessment(
        FastPaperAction.SELL,
        event_id="event-sell-final",
        sequence=5,
        at=T0 + 900,
    )
    final_loop = _record(restored.event_loop_state, final_sell_assessment)
    final_approval = _exit_approval(
        restored.ledger,
        final_sell_assessment,
        _open_position(restored.ledger).quantity,
    )
    final = _apply_exit(
        state=restored.position_action_states[0],
        approval=final_approval,
        ledger=restored.ledger,
        quote=_position_quote(
            T0 + 1_000,
            reference_price=10.7,
            execution_price=10.6,
        ),
        fill_policy=restored.fill_policy,
        evaluated_at=T0 + 1_000,
    )
    assert final.outcome is FastPaperPositionOutcome.SOLD
    assert all(
        position.state is PaperPositionState.CLOSED
        for position in final.next_ledger.positions
    )

    final_runtime = _runtime(
        final_loop,
        final.next_ledger,
        (),
        restored.fill_policy,
        at=T0 + 1_000,
    )
    report = validate_fast_paper_accounting(final_runtime)
    assert report.status is AccountingValidationStatus.RECONCILED
    assert report.open_position_count == 0
    assert report.closed_position_count == 1
    assert report.partial_reduction_count >= 2
    assert report.terminal_failure_count >= 1
    assert report.accumulated_costs_usd > fill_policy.network_fee_usd
    assert len(final.next_ledger.processed_intent_keys) == len(final.next_ledger.entries)


def test_pending_exit_survives_restart_with_original_timestamp_and_quote_independent_key(tmp_path) -> None:
    loop_state, ledger, action_state, fill_policy = _open_fast_position()
    reduce_assessment = _assessment(
        FastPaperAction.REDUCE,
        event_id="event-reduce-pending",
        sequence=2,
        at=T0 + 300,
    )
    loop_state = _record(loop_state, reduce_assessment)
    approval = _exit_approval(ledger, reduce_assessment, 3.0)

    deferred = _apply_exit(
        state=action_state,
        approval=approval,
        ledger=ledger,
        quote=_position_quote(T0 + 350, execution_price=10.9),
        fill_policy=fill_policy,
        evaluated_at=T0 + 350,
    )
    assert deferred.outcome is FastPaperPositionOutcome.DEFERRED
    assert deferred.next_state.pending_exit == approval
    assert deferred.next_state.pending_exit.assessment.as_of_unix_ms == T0 + 300

    runtime = _runtime(
        loop_state,
        ledger,
        (deferred.next_state,),
        fill_policy,
        at=T0 + 350,
    )
    database = tmp_path / "fl7.5-pending.sqlite3"
    _migrate(database)
    save_fast_paper_checkpoint(database, "pending-run", 1, runtime, T0 + 360)
    restored_record = load_latest_fast_paper_checkpoint(database, "pending-run")
    assert restored_record is not None
    restored = restored_record.state
    restored_state = restored.position_action_states[0]
    assert restored_state.pending_exit == approval

    at_price_a = _apply_exit(
        state=restored_state,
        approval=approval,
        ledger=restored.ledger,
        quote=_position_quote(T0 + 450, execution_price=10.8),
        fill_policy=restored.fill_policy,
        evaluated_at=T0 + 450,
    )
    at_price_b = _apply_exit(
        state=restored_state,
        approval=approval,
        ledger=restored.ledger,
        quote=_position_quote(T0 + 450, execution_price=10.6),
        fill_policy=restored.fill_policy,
        evaluated_at=T0 + 450,
    )
    assert at_price_a.intent is not None and at_price_b.intent is not None
    assert at_price_a.intent.idempotency_key == at_price_b.intent.idempotency_key
    assert at_price_a.intent.as_of_unix_ms == T0 + 300
    assert at_price_b.intent.as_of_unix_ms == T0 + 300
    assert at_price_a.intent.requested_notional_usd != at_price_b.intent.requested_notional_usd


def test_fast_runtime_state_rejects_missing_or_unrecorded_open_position_authority() -> None:
    loop_state, ledger, action_state, fill_policy = _open_fast_position()

    with pytest.raises(ValueError, match="OPEN|position|cover"):
        _runtime(loop_state, ledger, (), fill_policy, at=ledger.as_of_unix_ms)

    reduce_assessment = _assessment(
        FastPaperAction.REDUCE,
        event_id="event-not-recorded",
        sequence=2,
        at=T0 + 300,
    )
    approval = _exit_approval(ledger, reduce_assessment, 2.0)
    pending_state = replace(
        action_state,
        pending_exit=approval,
        last_assessment_at_unix_ms=T0 + 300,
    )
    with pytest.raises(ValueError, match="record|authority|assessment"):
        _runtime(
            loop_state,
            ledger,
            (pending_state,),
            fill_policy,
            at=T0 + 300,
        )

    with pytest.raises(ValueError, match="unique|duplicate"):
        _runtime(
            loop_state,
            ledger,
            (action_state, action_state),
            fill_policy,
            at=ledger.as_of_unix_ms,
        )
