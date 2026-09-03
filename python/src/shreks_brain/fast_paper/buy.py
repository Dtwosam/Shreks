from __future__ import annotations

import math

from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerUpdateState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    execute_paper_intent,
)
from shreks_brain.risk import (
    FastEntryRiskRequest,
    RiskContext,
    RiskPolicy,
    RiskState,
    assess_fast_entry_risk,
)
from shreks_brain.runtime import RuntimeMode

from .buy_models import (
    FAST_PAPER_BUY_VERSION,
    FastPaperBuyApproval,
    FastPaperBuyError,
    FastPaperBuyOutcome,
    FastPaperBuyQuote,
    FastPaperBuyResult,
)


_ARITH_REL_TOL = 1e-12
_ARITH_ABS_TOL = 1e-9


def execute_fast_paper_buy(
    ledger: PaperLedger,
    approval: FastPaperBuyApproval,
    risk_context: RiskContext,
    risk_policy: RiskPolicy,
    fill_policy: PaperFillPolicy,
    *,
    evaluated_at_unix_ms: int,
    quote: FastPaperBuyQuote | None,
) -> FastPaperBuyResult:
    """Attempt one exact-size FL7.2 PAPER BUY without any LIVE authority."""

    if not isinstance(ledger, PaperLedger):
        raise ValueError("ledger must be PaperLedger")
    if not isinstance(approval, FastPaperBuyApproval):
        raise ValueError("approval must be FastPaperBuyApproval")
    if not isinstance(risk_context, RiskContext):
        raise ValueError("risk_context must be RiskContext")
    if not isinstance(risk_policy, RiskPolicy):
        raise ValueError("risk_policy must be RiskPolicy")
    if not isinstance(fill_policy, PaperFillPolicy):
        raise ValueError("fill_policy must be PaperFillPolicy")
    if isinstance(evaluated_at_unix_ms, bool) or not isinstance(evaluated_at_unix_ms, int):
        raise ValueError("evaluated_at_unix_ms must be an integer")
    if evaluated_at_unix_ms < approval.decision_at_unix_ms:
        raise FastPaperBuyError("BUY evaluation cannot precede the Fast Lane decision")
    if risk_context.as_of_unix_ms != evaluated_at_unix_ms:
        raise FastPaperBuyError("risk context timestamp must match BUY evaluation time")
    if quote is not None and not isinstance(quote, FastPaperBuyQuote):
        raise ValueError("quote must be FastPaperBuyQuote or None")

    maximum_total = approval.maximum_entry_total_quote
    eligible_at = approval.decision_at_unix_ms + fill_policy.assumed_latency_ms
    deadline = eligible_at + fill_policy.max_quote_lag_ms

    if quote is not None:
        _validate_quote_identity_and_time(approval, quote, evaluated_at_unix_ms)

    if evaluated_at_unix_ms < eligible_at:
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.DEFERRED,
            maximum_total,
        )

    if quote is None:
        outcome = (
            FastPaperBuyOutcome.DEFERRED
            if evaluated_at_unix_ms <= deadline
            else FastPaperBuyOutcome.ABORTED_QUOTE_UNAVAILABLE
        )
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            outcome,
            maximum_total,
        )

    if quote.observed_at_unix_ms < eligible_at:
        outcome = (
            FastPaperBuyOutcome.DEFERRED
            if evaluated_at_unix_ms <= deadline
            else FastPaperBuyOutcome.ABORTED_QUOTE_UNAVAILABLE
        )
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            outcome,
            maximum_total,
        )

    if quote.observed_at_unix_ms > deadline:
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.ABORTED_QUOTE_TOO_LATE,
            maximum_total,
        )

    if quote.state is PaperQuoteState.UNAVAILABLE:
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.ABORTED_QUOTE_UNAVAILABLE,
            maximum_total,
        )

    reference_price_quote = quote.reference_price_quote
    execution_price_quote = quote.execution_price_quote
    quoted_base_quantity = quote.quoted_base_quantity
    available_base_quantity = quote.available_base_quantity
    if (
        reference_price_quote is None
        or execution_price_quote is None
        or quoted_base_quantity is None
        or available_base_quantity is None
    ):
        raise FastPaperBuyError("executable/submitted quote lacks complete price or capacity evidence")

    if _strictly_greater(
        execution_price_quote,
        approval.maximum_acceptable_entry_price_quote,
    ):
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.ABORTED_PRICE_ABOVE_MAXIMUM,
            maximum_total,
        )

    if _strictly_less(quoted_base_quantity, approval.intended_base_quantity) or _strictly_less(
        available_base_quantity,
        approval.intended_base_quantity,
    ):
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.ABORTED_INSUFFICIENT_CAPACITY,
            maximum_total,
        )

    execution_price_usd = execution_price_quote * quote.quote_to_usd_rate
    reference_price_usd = reference_price_quote * quote.quote_to_usd_rate
    requested_notional_usd = approval.intended_base_quantity * execution_price_usd
    for name, value in (
        ("execution_price_usd", execution_price_usd),
        ("reference_price_usd", reference_price_usd),
        ("requested_notional_usd", requested_notional_usd),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise FastPaperBuyError(f"{name} is invalid after quote-to-USD conversion")

    risk_request = FastEntryRiskRequest(
        mint=approval.mint,
        source_event_id=approval.assessment.source_event_id,
        decision_at_unix_ms=approval.decision_at_unix_ms,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        strategy_name=approval.assessment.strategy_family,
        strategy_version=approval.assessment.strategy_version,
        action_assessment_version=approval.assessment.version,
        state_version=approval.state_version,
        requested_notional_usd=requested_notional_usd,
    )
    risk = assess_fast_entry_risk(
        risk_request,
        risk_context,
        risk_policy,
        RuntimeMode.PAPER,
    )
    if risk.state is RiskState.REJECTED:
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.RISK_REJECTED,
            maximum_total,
            risk_assessment=risk,
        )

    intent = risk.intent
    if intent is None:
        raise FastPaperBuyError("approved Fast Lane risk did not produce TradeIntent")
    if intent.idempotency_key in ledger.processed_intent_keys:
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.ALREADY_PROCESSED,
            maximum_total,
            risk_assessment=risk,
        )

    paper_quote = PaperQuote(
        provider=quote.provider,
        mint=approval.mint,
        observed_at_unix_ms=quote.observed_at_unix_ms,
        state=quote.state,
        reference_price_usd=reference_price_usd,
        execution_price_usd=execution_price_usd,
        quoted_notional_usd=quoted_base_quantity * execution_price_usd,
        available_notional_usd=available_base_quantity * execution_price_usd,
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
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.DEFERRED,
            maximum_total,
            risk_assessment=risk,
            execution=execution,
        )

    if execution.state is PaperExecutionState.PARTIAL:
        raise FastPaperBuyError(
            "FL7.2 requires exact full-size entry; unexpected partial fill fails closed"
        )

    if execution.state is PaperExecutionState.FAILED:
        ledger_update = apply_paper_execution(ledger, intent, execution)
        outcome = (
            FastPaperBuyOutcome.EXECUTION_FAILED
            if ledger_update.state is PaperLedgerUpdateState.APPLIED
            else FastPaperBuyOutcome.LEDGER_REJECTED
        )
        return _result(
            ledger_update.ledger if ledger_update.state is PaperLedgerUpdateState.APPLIED else ledger,
            approval,
            evaluated_at_unix_ms,
            outcome,
            maximum_total,
            risk_assessment=risk,
            execution=execution,
            ledger_update=ledger_update,
        )

    fill = execution.fill
    if fill is None:
        raise FastPaperBuyError("FILLED execution must carry fill evidence")
    if not math.isclose(
        fill.quantity,
        approval.intended_base_quantity,
        rel_tol=_ARITH_REL_TOL,
        abs_tol=_ARITH_ABS_TOL,
    ):
        raise FastPaperBuyError("PAPER fill quantity does not equal Rust-assessed base quantity")

    actual_total_quote = (
        fill.filled_notional_usd + execution.explicit_cost_usd
    ) / quote.quote_to_usd_rate
    if not math.isfinite(actual_total_quote) or actual_total_quote <= 0.0:
        raise FastPaperBuyError("actual entry total quote is invalid")

    if _strictly_greater(actual_total_quote, maximum_total):
        return _result(
            ledger,
            approval,
            evaluated_at_unix_ms,
            FastPaperBuyOutcome.ABORTED_TOTAL_COST_ABOVE_MAXIMUM,
            maximum_total,
            actual_entry_total_quote=actual_total_quote,
            risk_assessment=risk,
            execution=execution,
        )

    ledger_update = apply_paper_execution(ledger, intent, execution)
    if ledger_update.state is PaperLedgerUpdateState.APPLIED:
        outcome = FastPaperBuyOutcome.FILLED
        next_ledger = ledger_update.ledger
    else:
        outcome = FastPaperBuyOutcome.LEDGER_REJECTED
        next_ledger = ledger
    return _result(
        next_ledger,
        approval,
        evaluated_at_unix_ms,
        outcome,
        maximum_total,
        actual_entry_total_quote=actual_total_quote,
        risk_assessment=risk,
        execution=execution,
        ledger_update=ledger_update,
    )


def _validate_quote_identity_and_time(
    approval: FastPaperBuyApproval,
    quote: FastPaperBuyQuote,
    evaluated_at_unix_ms: int,
) -> None:
    if quote.mint != approval.mint:
        raise FastPaperBuyError("quote mint does not match Fast PAPER BUY approval")
    if quote.quote_mint != approval.quote_mint:
        raise FastPaperBuyError("quote mint currency does not match Fast PAPER BUY approval")
    if quote.observed_at_unix_ms > evaluated_at_unix_ms:
        raise FastPaperBuyError("quote timestamp is after BUY evaluation time")


def _strictly_greater(actual: float, limit: float) -> bool:
    return actual > limit and not math.isclose(
        actual,
        limit,
        rel_tol=_ARITH_REL_TOL,
        abs_tol=_ARITH_ABS_TOL,
    )


def _strictly_less(actual: float, minimum: float) -> bool:
    return actual < minimum and not math.isclose(
        actual,
        minimum,
        rel_tol=_ARITH_REL_TOL,
        abs_tol=_ARITH_ABS_TOL,
    )


def _result(
    next_ledger: PaperLedger,
    approval: FastPaperBuyApproval,
    evaluated_at_unix_ms: int,
    outcome: FastPaperBuyOutcome,
    maximum_entry_total_quote: float,
    *,
    actual_entry_total_quote: float | None = None,
    risk_assessment=None,
    execution=None,
    ledger_update=None,
) -> FastPaperBuyResult:
    return FastPaperBuyResult(
        version=FAST_PAPER_BUY_VERSION,
        outcome=outcome,
        source_event_id=approval.assessment.source_event_id,
        mint=approval.mint,
        decision_at_unix_ms=approval.decision_at_unix_ms,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        intended_base_quantity=approval.intended_base_quantity,
        maximum_entry_total_quote=maximum_entry_total_quote,
        actual_entry_total_quote=actual_entry_total_quote,
        risk_assessment=risk_assessment,
        execution=execution,
        ledger_update=ledger_update,
        next_ledger=next_ledger,
    )
