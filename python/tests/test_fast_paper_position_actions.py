from __future__ import annotations

from dataclasses import replace
import math

import pytest

from shreks_brain.fast_paper import (
    FAST_PAPER_EXIT_RISK_POLICY_SENTINEL,
    FAST_PAPER_POSITION_ACTION_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperPositionActionApproval,
    FastPaperPositionActionError,
    FastPaperPositionActionPolicy,
    FastPaperPositionActionResult,
    FastPaperPositionActionState,
    FastPaperPositionOutcome,
    FastPaperPositionQuote,
    apply_fast_paper_position_action,
    create_fast_paper_position_action_state,
)
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerUpdateState,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
)
from shreks_brain.risk import FAST_LANE_SCORE_POLICY_SENTINEL, TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


QUOTE_MINT = "quote-a"


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-v1",
        assumed_latency_ms=100,
        max_quote_lag_ms=2_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
    )


def _action_policy() -> FastPaperPositionActionPolicy:
    return FastPaperPositionActionPolicy(version="fl7.4-policy-v1", max_slippage_bps=500)


def _open_ledger() -> PaperLedger:
    ledger = create_paper_ledger(10_000.0, 1_000)
    intent = TradeIntent(
        mint="mint-a",
        side=TradeSide.BUY,
        requested_notional_usd=1_000.0,
        max_slippage_bps=500,
        strategy_name="impulse-scalp",
        strategy_version="1",
        score_policy_version=FAST_LANE_SCORE_POLICY_SENTINEL,
        decision_policy_version="assessment-v1",
        risk_policy_version="risk-v1",
        reason="test-open",
        idempotency_key="open-mint-a",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=1_000,
    )
    quote = PaperQuote(
        provider="test",
        mint="mint-a",
        observed_at_unix_ms=1_100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=10.0,
        execution_price_usd=10.0,
        quoted_notional_usd=1_000.0,
        available_notional_usd=1_000.0,
    )
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=1_100,
            processed_intent_keys=ledger.processed_intent_keys,
            quote=quote,
        ),
        _fill_policy(),
    )
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    return update.ledger


def _open_position(ledger: PaperLedger):
    positions = tuple(
        position for position in ledger.positions if position.state is PaperPositionState.OPEN
    )
    assert len(positions) == 1
    return positions[0]


def _assessment(
    action: FastPaperAction,
    *,
    as_of_unix_ms: int = 1_200,
    source_event_id: str | None = None,
    reasons: tuple[str, ...] | None = None,
) -> FastPaperActionAssessment:
    if source_event_id is None:
        source_event_id = f"event-{action.value.lower()}-{as_of_unix_ms}"
    if reasons is None:
        reasons = (f"{action.value.lower()}_conditions_met",)
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=source_event_id,
        market_key="pump:mint-a:quote-a",
        source_sequence=as_of_unix_ms,
        as_of_unix_ms=as_of_unix_ms,
        strategy_family="longer-runner",
        strategy_version="1",
        action=action,
        reasons=reasons,
    )


def _approval(
    ledger: PaperLedger,
    action: FastPaperAction,
    *,
    target_base_quantity: float | None,
    as_of_unix_ms: int = 1_200,
    source_event_id: str | None = None,
) -> FastPaperPositionActionApproval:
    position = _open_position(ledger)
    return FastPaperPositionActionApproval(
        version=FAST_PAPER_POSITION_ACTION_VERSION,
        assessment=_assessment(
            action,
            as_of_unix_ms=as_of_unix_ms,
            source_event_id=source_event_id,
        ),
        position_id=position.position_id,
        mint=position.mint,
        quote_mint=QUOTE_MINT,
        state_version="fast-state-v1",
        target_base_quantity=target_base_quantity,
    )


def _state(ledger: PaperLedger) -> FastPaperPositionActionState:
    position = _open_position(ledger)
    return create_fast_paper_position_action_state(
        position.position_id,
        ledger.as_of_unix_ms,
    )


def _quote(
    *,
    observed_at_unix_ms: int = 1_300,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
    reference_price_quote: float | None = 5.0,
    execution_price_quote: float | None = 5.0,
    quoted_base_quantity: float | None = 200.0,
    available_base_quantity: float | None = 200.0,
    quote_to_usd_rate: float = 2.0,
    mint: str = "mint-a",
    quote_mint: str = QUOTE_MINT,
) -> FastPaperPositionQuote:
    return FastPaperPositionQuote(
        provider="fast-quote",
        mint=mint,
        quote_mint=quote_mint,
        observed_at_unix_ms=observed_at_unix_ms,
        state=state,
        reference_price_quote=reference_price_quote,
        execution_price_quote=execution_price_quote,
        quoted_base_quantity=quoted_base_quantity,
        available_base_quantity=available_base_quantity,
        quote_to_usd_rate=quote_to_usd_rate,
    )


def _apply(
    ledger: PaperLedger,
    state: FastPaperPositionActionState,
    approval: FastPaperPositionActionApproval,
    *,
    quote: FastPaperPositionQuote | None,
    evaluated_at_unix_ms: int,
) -> FastPaperPositionActionResult:
    return apply_fast_paper_position_action(
        state=state,
        approval=approval,
        ledger=ledger,
        quote=quote,
        fill_policy=_fill_policy(),
        policy=_action_policy(),
        evaluated_at_unix_ms=evaluated_at_unix_ms,
    )


def test_fl7_4_public_versions_are_stable() -> None:
    assert FAST_PAPER_POSITION_ACTION_VERSION == "fl7.4-v1"
    assert FAST_PAPER_EXIT_RISK_POLICY_SENTINEL == "not-applicable:fast-lane-exit"


def test_only_hold_reduce_sell_are_valid_position_actions() -> None:
    ledger = _open_ledger()
    position = _open_position(ledger)
    for action in (FastPaperAction.BUY, FastPaperAction.SKIP):
        with pytest.raises(ValueError, match="HOLD|REDUCE|SELL"):
            FastPaperPositionActionApproval(
                version=FAST_PAPER_POSITION_ACTION_VERSION,
                assessment=_assessment(action),
                position_id=position.position_id,
                mint=position.mint,
                quote_mint=QUOTE_MINT,
                state_version="fast-state-v1",
                target_base_quantity=None,
            )


def test_action_specific_quantity_contract_rejects_fabricated_or_invalid_targets() -> None:
    ledger = _open_ledger()
    position = _open_position(ledger)

    with pytest.raises(ValueError, match="HOLD"):
        _approval(ledger, FastPaperAction.HOLD, target_base_quantity=1.0)

    for action in (FastPaperAction.REDUCE, FastPaperAction.SELL):
        for value in (None, 0.0, -1.0, math.nan, math.inf):
            with pytest.raises(ValueError, match="target_base_quantity"):
                FastPaperPositionActionApproval(
                    version=FAST_PAPER_POSITION_ACTION_VERSION,
                    assessment=_assessment(action),
                    position_id=position.position_id,
                    mint=position.mint,
                    quote_mint=QUOTE_MINT,
                    state_version="fast-state-v1",
                    target_base_quantity=value,
                )


def test_hold_without_mark_evidence_is_true_noop() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.HOLD, target_base_quantity=None)
    result = _apply(ledger, _state(ledger), approval, quote=None, evaluated_at_unix_ms=1_200)

    assert result.outcome is FastPaperPositionOutcome.HOLD
    assert result.intent is None
    assert result.execution is None
    assert result.execution_ledger_update is None
    assert result.mark_ledger_update is None
    assert result.next_ledger == ledger
    assert result.next_state.pending_exit is None


def test_hold_can_mark_position_without_changing_cash_or_journal() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.HOLD, target_base_quantity=None)
    result = _apply(
        ledger,
        _state(ledger),
        approval,
        quote=_quote(observed_at_unix_ms=1_200, reference_price_quote=6.0),
        evaluated_at_unix_ms=1_200,
    )

    assert result.outcome is FastPaperPositionOutcome.HOLD_MARKED
    assert result.intent is None
    assert result.execution is None
    assert result.execution_ledger_update is None
    assert result.mark_ledger_update is not None
    assert result.mark_ledger_update.state is PaperLedgerUpdateState.APPLIED
    assert result.next_ledger.cash_balance_usd == pytest.approx(ledger.cash_balance_usd)
    assert len(result.next_ledger.entries) == len(ledger.entries)
    marked = _open_position(result.next_ledger)
    assert marked.last_mark_price_usd == pytest.approx(12.0)
    assert marked.last_mark_at_unix_ms == 1_200


def test_reduce_requires_explicit_strictly_partial_authority() -> None:
    ledger = _open_ledger()
    position = _open_position(ledger)

    for target in (position.quantity, position.quantity + 1.0):
        approval = _approval(
            ledger,
            FastPaperAction.REDUCE,
            target_base_quantity=target,
        )
        with pytest.raises(FastPaperPositionActionError, match="REDUCE"):
            _apply(ledger, _state(ledger), approval, quote=None, evaluated_at_unix_ms=1_200)


def test_sell_requires_explicit_full_position_authority() -> None:
    ledger = _open_ledger()
    position = _open_position(ledger)

    approval = _approval(
        ledger,
        FastPaperAction.SELL,
        target_base_quantity=position.quantity - 1.0,
    )
    with pytest.raises(FastPaperPositionActionError, match="SELL"):
        _apply(ledger, _state(ledger), approval, quote=None, evaluated_at_unix_ms=1_200)


def test_missing_quote_defers_and_preserves_quantity_authority() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    result = _apply(ledger, _state(ledger), approval, quote=None, evaluated_at_unix_ms=1_200)

    assert result.outcome is FastPaperPositionOutcome.DEFERRED
    assert result.intent is None
    assert result.execution is None
    assert result.next_ledger == ledger
    assert result.next_state.pending_exit == approval
    assert result.next_state.last_assessment_at_unix_ms == 1_200


def test_future_quote_fails_closed_before_execution() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    with pytest.raises(FastPaperPositionActionError, match="future quote"):
        _apply(
            ledger,
            _state(ledger),
            approval,
            quote=_quote(observed_at_unix_ms=1_301),
            evaluated_at_unix_ms=1_300,
        )


def test_pre_latency_quote_defers_without_resetting_original_action_time() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    first = _apply(
        ledger,
        _state(ledger),
        approval,
        quote=_quote(observed_at_unix_ms=1_250),
        evaluated_at_unix_ms=1_250,
    )
    assert first.outcome is FastPaperPositionOutcome.DEFERRED
    assert first.next_state.pending_exit == approval

    hold = _approval(
        ledger,
        FastPaperAction.HOLD,
        target_base_quantity=None,
        as_of_unix_ms=1_275,
    )
    second = _apply(
        ledger,
        first.next_state,
        hold,
        quote=_quote(observed_at_unix_ms=1_300),
        evaluated_at_unix_ms=1_300,
    )
    assert second.next_state.last_assessment_at_unix_ms == 1_275
    assert second.active_exit == approval
    assert second.intent is not None
    assert second.intent.as_of_unix_ms == 1_200


def test_eligible_reduce_uses_exact_current_quote_for_quantity_safe_paper_sell() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    result = _apply(
        ledger,
        _state(ledger),
        approval,
        quote=_quote(observed_at_unix_ms=1_300),
        evaluated_at_unix_ms=1_300,
    )

    assert result.intent is not None
    assert result.intent.execution_mode is RuntimeMode.PAPER
    assert result.intent.side is TradeSide.SELL
    assert result.intent.as_of_unix_ms == 1_200
    assert result.intent.score_policy_version == FAST_LANE_SCORE_POLICY_SENTINEL
    assert result.intent.risk_policy_version == FAST_PAPER_EXIT_RISK_POLICY_SENTINEL
    assert result.intent.requested_notional_usd == pytest.approx(25.0 * 5.0 * 2.0)
    assert result.execution is not None
    assert result.execution.fill is not None
    assert result.execution.fill.quantity <= 25.0 + 1e-9


def test_partial_capacity_never_fills_more_than_authorized_reduce_quantity() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    result = _apply(
        ledger,
        _state(ledger),
        approval,
        quote=_quote(
            observed_at_unix_ms=1_300,
            quoted_base_quantity=10.0,
            available_base_quantity=10.0,
        ),
        evaluated_at_unix_ms=1_300,
    )

    assert result.execution is not None
    assert result.execution.state is PaperExecutionState.PARTIAL
    assert result.execution.fill is not None
    assert result.execution.fill.quantity == pytest.approx(10.0)
    assert result.execution.fill.quantity < approval.target_base_quantity
    assert result.outcome is FastPaperPositionOutcome.REDUCED


def test_successful_reduce_uses_authoritative_c3_accounting() -> None:
    ledger = _open_ledger()
    before = _open_position(ledger)
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    result = _apply(
        ledger,
        _state(ledger),
        approval,
        quote=_quote(observed_at_unix_ms=1_300),
        evaluated_at_unix_ms=1_300,
    )

    assert result.outcome is FastPaperPositionOutcome.REDUCED
    assert result.execution_ledger_update is not None
    assert result.execution_ledger_update.state is PaperLedgerUpdateState.APPLIED
    after = _open_position(result.next_ledger)
    assert after.quantity == pytest.approx(before.quantity - 25.0)
    assert after.open_cost_basis_usd < before.open_cost_basis_usd
    assert after.sell_fill_count == before.sell_fill_count + 1
    assert result.next_ledger.cash_balance_usd > ledger.cash_balance_usd
    assert result.next_ledger.accumulated_costs_usd > ledger.accumulated_costs_usd
    assert result.next_state.pending_exit is None


def test_successful_sell_closes_authoritative_position() -> None:
    ledger = _open_ledger()
    position = _open_position(ledger)
    approval = _approval(
        ledger,
        FastPaperAction.SELL,
        target_base_quantity=position.quantity,
    )
    result = _apply(
        ledger,
        _state(ledger),
        approval,
        quote=_quote(observed_at_unix_ms=1_300),
        evaluated_at_unix_ms=1_300,
    )

    assert result.outcome is FastPaperPositionOutcome.SOLD
    closed = next(item for item in result.next_ledger.positions if item.position_id == position.position_id)
    assert closed.state is PaperPositionState.CLOSED
    assert closed.quantity == pytest.approx(0.0)
    assert result.next_state.pending_exit is None


def test_pending_reduce_is_promoted_by_newer_full_sell() -> None:
    ledger = _open_ledger()
    position = _open_position(ledger)
    reduce = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    first = _apply(ledger, _state(ledger), reduce, quote=None, evaluated_at_unix_ms=1_200)

    sell = _approval(
        ledger,
        FastPaperAction.SELL,
        target_base_quantity=position.quantity,
        as_of_unix_ms=1_250,
    )
    second = _apply(
        ledger,
        first.next_state,
        sell,
        quote=None,
        evaluated_at_unix_ms=1_250,
    )

    assert second.next_state.pending_exit == sell
    assert second.next_state.pending_exit.assessment.as_of_unix_ms == 1_250


def test_pending_sell_cannot_be_cancelled_by_newer_hold_or_reduce() -> None:
    ledger = _open_ledger()
    position = _open_position(ledger)
    sell = _approval(
        ledger,
        FastPaperAction.SELL,
        target_base_quantity=position.quantity,
    )
    first = _apply(ledger, _state(ledger), sell, quote=None, evaluated_at_unix_ms=1_200)

    for fresh in (
        _approval(
            ledger,
            FastPaperAction.HOLD,
            target_base_quantity=None,
            as_of_unix_ms=1_250,
        ),
        _approval(
            ledger,
            FastPaperAction.REDUCE,
            target_base_quantity=10.0,
            as_of_unix_ms=1_300,
        ),
    ):
        result = _apply(
            ledger,
            first.next_state,
            fresh,
            quote=None,
            evaluated_at_unix_ms=fresh.assessment.as_of_unix_ms,
        )
        assert result.next_state.pending_exit == sell
        first = result


def test_pending_reduce_latency_is_not_reset_by_newer_hold_or_reduce() -> None:
    ledger = _open_ledger()
    original = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    first = _apply(ledger, _state(ledger), original, quote=None, evaluated_at_unix_ms=1_200)

    newer = _approval(
        ledger,
        FastPaperAction.REDUCE,
        target_base_quantity=10.0,
        as_of_unix_ms=1_250,
    )
    second = _apply(
        ledger,
        first.next_state,
        newer,
        quote=None,
        evaluated_at_unix_ms=1_250,
    )
    assert second.next_state.pending_exit == original
    assert second.next_state.pending_exit.assessment.as_of_unix_ms == 1_200
    assert second.next_state.last_assessment_at_unix_ms == 1_250


def test_failed_after_submission_books_network_cost_and_clears_pending() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    result = _apply(
        ledger,
        _state(ledger),
        approval,
        quote=_quote(
            observed_at_unix_ms=1_300,
            state=PaperQuoteState.FAILED_AFTER_SUBMISSION,
        ),
        evaluated_at_unix_ms=1_300,
    )

    assert result.outcome is FastPaperPositionOutcome.EXECUTION_FAILED
    assert result.execution is not None
    assert result.execution.state is PaperExecutionState.FAILED
    assert result.execution.findings[0].code is PaperExecutionReasonCode.SIMULATED_SUBMISSION_FAILED
    assert result.execution_ledger_update is not None
    assert result.execution_ledger_update.state is PaperLedgerUpdateState.APPLIED
    assert result.next_ledger.accumulated_costs_usd == pytest.approx(
        ledger.accumulated_costs_usd + _fill_policy().network_fee_usd
    )
    assert result.next_state.pending_exit is None


def test_terminal_replay_is_idempotent_and_never_double_books() -> None:
    ledger = _open_ledger()
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)
    first = _apply(
        ledger,
        _state(ledger),
        approval,
        quote=_quote(observed_at_unix_ms=1_300),
        evaluated_at_unix_ms=1_300,
    )
    entries_after_first = len(first.next_ledger.entries)

    replay = _apply(
        first.next_ledger,
        first.next_state,
        approval,
        quote=_quote(observed_at_unix_ms=1_300),
        evaluated_at_unix_ms=1_300,
    )
    assert replay.outcome is FastPaperPositionOutcome.ALREADY_PROCESSED
    assert len(replay.next_ledger.entries) == entries_after_first
    assert replay.next_ledger == first.next_ledger


def test_identity_time_and_conversion_contradictions_fail_closed() -> None:
    ledger = _open_ledger()
    position = _open_position(ledger)
    approval = _approval(ledger, FastPaperAction.REDUCE, target_base_quantity=25.0)

    wrong_position = replace(approval, position_id="other-position")
    with pytest.raises(FastPaperPositionActionError, match="position"):
        _apply(ledger, _state(ledger), wrong_position, quote=None, evaluated_at_unix_ms=1_200)

    wrong_mint = replace(approval, mint="other-mint")
    with pytest.raises(FastPaperPositionActionError, match="mint"):
        _apply(ledger, _state(ledger), wrong_mint, quote=None, evaluated_at_unix_ms=1_200)

    with pytest.raises(FastPaperPositionActionError, match="quote mint"):
        _apply(
            ledger,
            _state(ledger),
            approval,
            quote=_quote(quote_mint="other-quote"),
            evaluated_at_unix_ms=1_300,
        )

    with pytest.raises(ValueError, match="quote_to_usd_rate"):
        _quote(quote_to_usd_rate=math.nan)

    regressed = _approval(
        ledger,
        FastPaperAction.HOLD,
        target_base_quantity=None,
        as_of_unix_ms=ledger.as_of_unix_ms - 1,
    )
    with pytest.raises(FastPaperPositionActionError, match="timestamp|assessment"):
        _apply(ledger, _state(ledger), regressed, quote=None, evaluated_at_unix_ms=1_200)

    closed_sell = _approval(
        ledger,
        FastPaperAction.SELL,
        target_base_quantity=position.quantity,
    )
    closed_result = _apply(
        ledger,
        _state(ledger),
        closed_sell,
        quote=_quote(observed_at_unix_ms=1_300),
        evaluated_at_unix_ms=1_300,
    )
    with pytest.raises(FastPaperPositionActionError, match="OPEN|closed"):
        _apply(
            closed_result.next_ledger,
            closed_result.next_state,
            closed_sell,
            quote=None,
            evaluated_at_unix_ms=1_400,
        )
