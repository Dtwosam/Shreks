from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math

from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerUpdate,
    PaperLedgerUpdateState,
    PaperPosition,
    PaperPositionMark,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    execute_paper_intent,
    mark_paper_position,
)
from shreks_brain.risk import (
    FAST_LANE_SCORE_POLICY_SENTINEL,
    TradeIntent,
    TradeSide,
)
from shreks_brain.runtime import RuntimeMode

from .models import FastPaperAction
from .position_models import (
    FAST_PAPER_EXIT_RISK_POLICY_SENTINEL,
    FAST_PAPER_POSITION_ACTION_VERSION,
    FastPaperPositionActionApproval,
    FastPaperPositionActionError,
    FastPaperPositionActionPolicy,
    FastPaperPositionActionResult,
    FastPaperPositionActionState,
    FastPaperPositionOutcome,
    FastPaperPositionQuote,
)


_EXIT_KEY_VERSION = "fl7.4-exit-v1"
_REL_TOL = 1e-12
_ABS_TOL = 1e-9


def create_fast_paper_position_action_state(
    position_id: str,
    as_of_unix_ms: int,
) -> FastPaperPositionActionState:
    """Create one deterministic in-memory FL7.4 position-action state."""

    return FastPaperPositionActionState(
        version=FAST_PAPER_POSITION_ACTION_VERSION,
        position_id=position_id,
        pending_exit=None,
        last_assessment_at_unix_ms=as_of_unix_ms,
    )


def apply_fast_paper_position_action(
    *,
    state: FastPaperPositionActionState,
    approval: FastPaperPositionActionApproval,
    ledger: PaperLedger,
    quote: FastPaperPositionQuote | None,
    fill_policy: PaperFillPolicy,
    policy: FastPaperPositionActionPolicy,
    evaluated_at_unix_ms: int,
) -> FastPaperPositionActionResult:
    """Apply one fresh Fast Lane open-position assessment in PAPER only.

    The function preserves base-quantity authority and delegates all fill and
    accounting semantics to the existing PAPER execution and ledger engines.
    """

    if not isinstance(state, FastPaperPositionActionState):
        raise FastPaperPositionActionError(
            "state must be FastPaperPositionActionState"
        )
    if not isinstance(approval, FastPaperPositionActionApproval):
        raise FastPaperPositionActionError(
            "approval must be FastPaperPositionActionApproval"
        )
    if not isinstance(ledger, PaperLedger):
        raise FastPaperPositionActionError("ledger must be PaperLedger")
    if quote is not None and not isinstance(quote, FastPaperPositionQuote):
        raise FastPaperPositionActionError(
            "quote must be FastPaperPositionQuote or None"
        )
    if not isinstance(fill_policy, PaperFillPolicy):
        raise FastPaperPositionActionError("fill_policy must be PaperFillPolicy")
    if not isinstance(policy, FastPaperPositionActionPolicy):
        raise FastPaperPositionActionError(
            "policy must be FastPaperPositionActionPolicy"
        )
    _require_non_negative_int("evaluated_at_unix_ms", evaluated_at_unix_ms)

    if state.position_id != approval.position_id:
        raise FastPaperPositionActionError(
            "approval position does not match position-action state"
        )
    position = _require_open_position(ledger, approval.position_id)
    if position.mint != approval.mint:
        raise FastPaperPositionActionError(
            "approval mint does not match authoritative position mint"
        )
    if approval.assessment.as_of_unix_ms < state.last_assessment_at_unix_ms:
        raise FastPaperPositionActionError(
            "assessment timestamp regresses position-action state"
        )
    if evaluated_at_unix_ms < approval.assessment.as_of_unix_ms:
        raise FastPaperPositionActionError(
            "evaluation timestamp precedes fresh assessment timestamp"
        )
    if evaluated_at_unix_ms < ledger.as_of_unix_ms:
        raise FastPaperPositionActionError(
            "evaluation timestamp precedes authoritative ledger time"
        )

    _validate_fresh_quantity_authority(position, approval)
    if quote is not None:
        _validate_quote_identity_and_time(
            quote,
            approval,
            position,
            evaluated_at_unix_ms,
        )

    active_exit = _reconcile_pending_exit(state.pending_exit, approval)
    next_state = FastPaperPositionActionState(
        version=FAST_PAPER_POSITION_ACTION_VERSION,
        position_id=state.position_id,
        pending_exit=active_exit,
        last_assessment_at_unix_ms=approval.assessment.as_of_unix_ms,
    )

    if active_exit is None:
        return _hold_result(
            approval=approval,
            ledger=ledger,
            quote=quote,
            next_state=next_state,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )

    if quote is None:
        return _result(
            outcome=FastPaperPositionOutcome.DEFERRED,
            approval=approval,
            active_exit=active_exit,
            intent=None,
            execution=None,
            execution_update=None,
            mark_update=None,
            ledger=ledger,
            state=next_state,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )

    eligible_at_unix_ms = (
        active_exit.assessment.as_of_unix_ms + fill_policy.assumed_latency_ms
    )
    if quote.observed_at_unix_ms < eligible_at_unix_ms:
        return _result(
            outcome=FastPaperPositionOutcome.DEFERRED,
            approval=approval,
            active_exit=active_exit,
            intent=None,
            execution=None,
            execution_update=None,
            mark_update=None,
            ledger=ledger,
            state=next_state,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )

    if quote.state is PaperQuoteState.UNAVAILABLE:
        return _result(
            outcome=FastPaperPositionOutcome.ABORTED_QUOTE_UNAVAILABLE,
            approval=approval,
            active_exit=active_exit,
            intent=None,
            execution=None,
            execution_update=None,
            mark_update=None,
            ledger=ledger,
            state=next_state,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )

    current_position = _require_open_position(ledger, active_exit.position_id)
    target = active_exit.target_base_quantity
    assert target is not None
    attempt_quantity = min(target, current_position.quantity)
    if not math.isfinite(attempt_quantity) or attempt_quantity <= 0.0:
        raise FastPaperPositionActionError(
            "authorized exit has no positive remaining base quantity"
        )

    paper_quote, requested_notional_usd = _adapt_quote(
        quote,
        attempt_quantity,
    )
    intent = _build_exit_intent(
        active_exit,
        current_position,
        requested_notional_usd,
        policy,
    )

    if intent.idempotency_key in ledger.processed_intent_keys:
        replay_state = replace(next_state, pending_exit=None)
        return _result(
            outcome=FastPaperPositionOutcome.ALREADY_PROCESSED,
            approval=approval,
            active_exit=active_exit,
            intent=intent,
            execution=None,
            execution_update=None,
            mark_update=None,
            ledger=ledger,
            state=replay_state,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )

    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=evaluated_at_unix_ms,
            processed_intent_keys=ledger.processed_intent_keys,
            quote=paper_quote,
        ),
        fill_policy,
    )

    if execution.state is PaperExecutionState.DEFERRED:
        return _result(
            outcome=FastPaperPositionOutcome.DEFERRED,
            approval=approval,
            active_exit=active_exit,
            intent=intent,
            execution=execution,
            execution_update=None,
            mark_update=None,
            ledger=ledger,
            state=next_state,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )

    execution_update = apply_paper_execution(ledger, intent, execution)
    terminal_state = replace(next_state, pending_exit=None)
    next_ledger = execution_update.ledger

    if execution_update.state is PaperLedgerUpdateState.REJECTED:
        outcome = FastPaperPositionOutcome.LEDGER_REJECTED
    elif execution.state is PaperExecutionState.FAILED:
        if execution.findings[0].code is PaperExecutionReasonCode.DUPLICATE_INTENT:
            outcome = FastPaperPositionOutcome.ALREADY_PROCESSED
        else:
            outcome = FastPaperPositionOutcome.EXECUTION_FAILED
    else:
        after = _find_position(next_ledger, current_position.position_id)
        if after is None:
            raise FastPaperPositionActionError(
                "authoritative ledger lost position after applied exit"
            )
        outcome = (
            FastPaperPositionOutcome.SOLD
            if after.state is PaperPositionState.CLOSED
            else FastPaperPositionOutcome.REDUCED
        )

    return _result(
        outcome=outcome,
        approval=approval,
        active_exit=active_exit,
        intent=intent,
        execution=execution,
        execution_update=execution_update,
        mark_update=None,
        ledger=next_ledger,
        state=terminal_state,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
    )


def _hold_result(
    *,
    approval: FastPaperPositionActionApproval,
    ledger: PaperLedger,
    quote: FastPaperPositionQuote | None,
    next_state: FastPaperPositionActionState,
    evaluated_at_unix_ms: int,
) -> FastPaperPositionActionResult:
    mark_update: PaperLedgerUpdate | None = None
    next_ledger = ledger
    outcome = FastPaperPositionOutcome.HOLD

    if (
        quote is not None
        and quote.reference_price_quote is not None
        and quote.observed_at_unix_ms >= ledger.as_of_unix_ms
    ):
        mark_price_usd = _positive_product(
            quote.reference_price_quote,
            quote.quote_to_usd_rate,
            "reference mark price USD",
        )
        update = mark_paper_position(
            ledger,
            PaperPositionMark(
                position_id=approval.position_id,
                mint=approval.mint,
                observed_at_unix_ms=quote.observed_at_unix_ms,
                mark_price_usd=mark_price_usd,
            ),
        )
        if update.state is PaperLedgerUpdateState.APPLIED:
            mark_update = update
            next_ledger = update.ledger
            outcome = FastPaperPositionOutcome.HOLD_MARKED

    return _result(
        outcome=outcome,
        approval=approval,
        active_exit=None,
        intent=None,
        execution=None,
        execution_update=None,
        mark_update=mark_update,
        ledger=next_ledger,
        state=next_state,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
    )


def _validate_fresh_quantity_authority(
    position: PaperPosition,
    approval: FastPaperPositionActionApproval,
) -> None:
    action = approval.assessment.action
    if action is FastPaperAction.HOLD:
        return
    target = approval.target_base_quantity
    assert target is not None
    if action is FastPaperAction.REDUCE:
        if target > position.quantity or math.isclose(
            target,
            position.quantity,
            rel_tol=_REL_TOL,
            abs_tol=_ABS_TOL,
        ):
            raise FastPaperPositionActionError(
                "REDUCE target must be strictly below authoritative OPEN position quantity"
            )
        return
    if action is FastPaperAction.SELL and not math.isclose(
        target,
        position.quantity,
        rel_tol=_REL_TOL,
        abs_tol=_ABS_TOL,
    ):
        raise FastPaperPositionActionError(
            "SELL target must equal authoritative full OPEN position quantity"
        )


def _reconcile_pending_exit(
    pending: FastPaperPositionActionApproval | None,
    fresh: FastPaperPositionActionApproval,
) -> FastPaperPositionActionApproval | None:
    if pending is None:
        return None if fresh.assessment.action is FastPaperAction.HOLD else fresh
    if pending.assessment.action is FastPaperAction.SELL:
        return pending
    if fresh.assessment.action is FastPaperAction.SELL:
        return fresh
    return pending


def _validate_quote_identity_and_time(
    quote: FastPaperPositionQuote,
    approval: FastPaperPositionActionApproval,
    position: PaperPosition,
    evaluated_at_unix_ms: int,
) -> None:
    if quote.mint != position.mint:
        raise FastPaperPositionActionError(
            "quote mint does not match authoritative position mint"
        )
    if quote.quote_mint != approval.quote_mint:
        raise FastPaperPositionActionError(
            "quote mint pair does not match approval quote mint"
        )
    if quote.observed_at_unix_ms > evaluated_at_unix_ms:
        raise FastPaperPositionActionError(
            "future quote cannot be consumed by position action"
        )


def _adapt_quote(
    quote: FastPaperPositionQuote,
    attempt_quantity: float,
) -> tuple[PaperQuote, float]:
    assert quote.reference_price_quote is not None
    assert quote.execution_price_quote is not None
    assert quote.quoted_base_quantity is not None
    assert quote.available_base_quantity is not None

    reference_price_usd = _positive_product(
        quote.reference_price_quote,
        quote.quote_to_usd_rate,
        "reference price USD",
    )
    execution_price_usd = _positive_product(
        quote.execution_price_quote,
        quote.quote_to_usd_rate,
        "execution price USD",
    )
    requested_notional_usd = _positive_product(
        attempt_quantity,
        execution_price_usd,
        "requested SELL notional USD",
    )
    quoted_notional_usd = _positive_product(
        quote.quoted_base_quantity,
        execution_price_usd,
        "quoted notional USD",
    )
    available_notional_usd = _positive_product(
        quote.available_base_quantity,
        execution_price_usd,
        "available notional USD",
    )
    return (
        PaperQuote(
            provider=quote.provider,
            mint=quote.mint,
            observed_at_unix_ms=quote.observed_at_unix_ms,
            state=quote.state,
            reference_price_usd=reference_price_usd,
            execution_price_usd=execution_price_usd,
            quoted_notional_usd=quoted_notional_usd,
            available_notional_usd=available_notional_usd,
        ),
        requested_notional_usd,
    )


def _build_exit_intent(
    approval: FastPaperPositionActionApproval,
    position: PaperPosition,
    requested_notional_usd: float,
    policy: FastPaperPositionActionPolicy,
) -> TradeIntent:
    return TradeIntent(
        mint=position.mint,
        side=TradeSide.SELL,
        requested_notional_usd=requested_notional_usd,
        max_slippage_bps=policy.max_slippage_bps,
        strategy_name=approval.assessment.strategy_family,
        strategy_version=approval.assessment.strategy_version,
        score_policy_version=FAST_LANE_SCORE_POLICY_SENTINEL,
        decision_policy_version=approval.assessment.version,
        risk_policy_version=FAST_PAPER_EXIT_RISK_POLICY_SENTINEL,
        reason=approval.assessment.reasons[0],
        idempotency_key=_exit_idempotency_key(approval),
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=approval.assessment.as_of_unix_ms,
    )


def _exit_idempotency_key(approval: FastPaperPositionActionApproval) -> str:
    target = approval.target_base_quantity
    assert target is not None
    payload = json.dumps(
        [
            _EXIT_KEY_VERSION,
            approval.position_id,
            approval.assessment.source_event_id,
            approval.assessment.version,
            approval.assessment.strategy_family,
            approval.assessment.strategy_version,
            approval.assessment.as_of_unix_ms,
            approval.assessment.action.value,
            list(approval.assessment.reasons),
            float(target).hex(),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_open_position(ledger: PaperLedger, position_id: str) -> PaperPosition:
    position = _find_position(ledger, position_id)
    if position is None:
        raise FastPaperPositionActionError(
            "authoritative position was not found for position_id"
        )
    if position.state is not PaperPositionState.OPEN:
        raise FastPaperPositionActionError(
            "Fast PAPER position action requires authoritative OPEN position"
        )
    return position


def _find_position(ledger: PaperLedger, position_id: str) -> PaperPosition | None:
    for position in ledger.positions:
        if position.position_id == position_id:
            return position
    return None


def _positive_product(left: float, right: float, name: str) -> float:
    value = left * right
    if not math.isfinite(value) or value <= 0.0:
        raise FastPaperPositionActionError(f"{name} must be finite and positive")
    return value


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperPositionActionError(
            f"{name} must be a non-negative integer"
        )


def _result(
    *,
    outcome: FastPaperPositionOutcome,
    approval: FastPaperPositionActionApproval,
    active_exit: FastPaperPositionActionApproval | None,
    intent: TradeIntent | None,
    execution,
    execution_update,
    mark_update,
    ledger: PaperLedger,
    state: FastPaperPositionActionState,
    evaluated_at_unix_ms: int,
) -> FastPaperPositionActionResult:
    return FastPaperPositionActionResult(
        version=FAST_PAPER_POSITION_ACTION_VERSION,
        outcome=outcome,
        position_id=approval.position_id,
        mint=approval.mint,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        applied_assessment=approval.assessment,
        active_exit=active_exit,
        intent=intent,
        execution=execution,
        execution_ledger_update=execution_update,
        mark_ledger_update=mark_update,
        next_ledger=ledger,
        next_state=state,
    )
