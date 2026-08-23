from __future__ import annotations

import math

from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode

from .models import (
    PaperExecutionContext,
    PaperExecutionFinding,
    PaperExecutionReasonCode,
    PaperExecutionResult,
    PaperExecutionState,
    PaperFill,
    PaperFillPolicy,
    PaperQuoteState,
)


_SLIPPAGE_REL_TOL = 1e-12
_SLIPPAGE_ABS_TOL = 1e-9


def execute_paper_intent(
    intent: TradeIntent,
    context: PaperExecutionContext,
    policy: PaperFillPolicy,
) -> PaperExecutionResult:
    """Deterministically simulate one point-in-time paper execution attempt."""

    if intent.execution_mode is not RuntimeMode.PAPER:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.INTENT_MODE_NOT_PAPER,
        )

    if intent.idempotency_key in context.processed_intent_keys:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.DUPLICATE_INTENT,
        )

    if context.evaluated_at_unix_ms < intent.as_of_unix_ms:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.EVALUATION_BEFORE_INTENT,
        )

    quote = context.quote
    if quote is not None and quote.observed_at_unix_ms > context.evaluated_at_unix_ms:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.QUOTE_AFTER_EVALUATION,
            quote_timestamp=quote.observed_at_unix_ms,
        )

    if quote is not None and quote.mint != intent.mint:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.QUOTE_MINT_MISMATCH,
            quote_timestamp=quote.observed_at_unix_ms,
        )

    eligible_at_unix_ms = intent.as_of_unix_ms + policy.assumed_latency_ms
    deadline_unix_ms = eligible_at_unix_ms + policy.max_quote_lag_ms

    if context.evaluated_at_unix_ms < eligible_at_unix_ms:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.DEFERRED,
            PaperExecutionReasonCode.LATENCY_PENDING,
            quote_timestamp=quote.observed_at_unix_ms if quote is not None else None,
        )

    if quote is None:
        if context.evaluated_at_unix_ms <= deadline_unix_ms:
            return _terminal(
                intent,
                context,
                policy,
                PaperExecutionState.DEFERRED,
                PaperExecutionReasonCode.QUOTE_PENDING,
            )
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.QUOTE_WINDOW_EXPIRED,
        )

    if quote.observed_at_unix_ms < eligible_at_unix_ms:
        if context.evaluated_at_unix_ms <= deadline_unix_ms:
            return _terminal(
                intent,
                context,
                policy,
                PaperExecutionState.DEFERRED,
                PaperExecutionReasonCode.QUOTE_BEFORE_LATENCY,
                quote_timestamp=quote.observed_at_unix_ms,
            )
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.QUOTE_WINDOW_EXPIRED,
            quote_timestamp=quote.observed_at_unix_ms,
        )

    if quote.observed_at_unix_ms > deadline_unix_ms:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.QUOTE_TOO_LATE,
            quote_timestamp=quote.observed_at_unix_ms,
        )

    if quote.state is PaperQuoteState.UNAVAILABLE:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.ROUTE_UNAVAILABLE,
            quote_timestamp=quote.observed_at_unix_ms,
        )

    if quote.state is PaperQuoteState.FAILED_AFTER_SUBMISSION:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.SIMULATED_SUBMISSION_FAILED,
            quote_timestamp=quote.observed_at_unix_ms,
            network_fee_usd=policy.network_fee_usd,
            net_cash_flow_usd=-policy.network_fee_usd,
        )

    if quote.reference_price_usd is None:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.REFERENCE_PRICE_UNKNOWN,
            quote_timestamp=quote.observed_at_unix_ms,
        )
    if quote.execution_price_usd is None:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.EXECUTION_PRICE_UNKNOWN,
            quote_timestamp=quote.observed_at_unix_ms,
        )
    if quote.quoted_notional_usd is None:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.QUOTED_NOTIONAL_UNKNOWN,
            quote_timestamp=quote.observed_at_unix_ms,
        )
    if quote.available_notional_usd is None:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.AVAILABLE_NOTIONAL_UNKNOWN,
            quote_timestamp=quote.observed_at_unix_ms,
        )

    fill_notional_usd = min(
        intent.requested_notional_usd,
        quote.quoted_notional_usd,
        quote.available_notional_usd,
    )
    if fill_notional_usd <= 0.0:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.NO_EXECUTABLE_NOTIONAL,
            quote_timestamp=quote.observed_at_unix_ms,
        )

    is_partial = fill_notional_usd < intent.requested_notional_usd
    if is_partial and not policy.allow_partial_fills:
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.PARTIAL_FILL_DISABLED,
            quote_timestamp=quote.observed_at_unix_ms,
        )
    if is_partial:
        fill_fraction = fill_notional_usd / intent.requested_notional_usd
        if fill_fraction < policy.min_partial_fill_fraction:
            return _terminal(
                intent,
                context,
                policy,
                PaperExecutionState.FAILED,
                PaperExecutionReasonCode.PARTIAL_FILL_TOO_SMALL,
                quote_timestamp=quote.observed_at_unix_ms,
            )

    if intent.side is TradeSide.BUY:
        signed_slippage_bps = (
            quote.execution_price_usd / quote.reference_price_usd - 1.0
        ) * 10_000.0
    else:
        signed_slippage_bps = (
            1.0 - quote.execution_price_usd / quote.reference_price_usd
        ) * 10_000.0

    if signed_slippage_bps > intent.max_slippage_bps and not math.isclose(
        signed_slippage_bps,
        float(intent.max_slippage_bps),
        rel_tol=_SLIPPAGE_REL_TOL,
        abs_tol=_SLIPPAGE_ABS_TOL,
    ):
        return _terminal(
            intent,
            context,
            policy,
            PaperExecutionState.FAILED,
            PaperExecutionReasonCode.SLIPPAGE_EXCEEDS_INTENT,
            quote_timestamp=quote.observed_at_unix_ms,
        )

    quantity = fill_notional_usd / quote.execution_price_usd
    if intent.side is TradeSide.BUY:
        signed_slippage_usd = quantity * (
            quote.execution_price_usd - quote.reference_price_usd
        )
    else:
        signed_slippage_usd = quantity * (
            quote.reference_price_usd - quote.execution_price_usd
        )

    swap_fee_usd = fill_notional_usd * policy.swap_fee_bps / 10_000.0
    network_fee_usd = policy.network_fee_usd
    explicit_cost_usd = swap_fee_usd + network_fee_usd
    if intent.side is TradeSide.BUY:
        net_cash_flow_usd = -(fill_notional_usd + explicit_cost_usd)
    else:
        net_cash_flow_usd = fill_notional_usd - explicit_cost_usd

    state = PaperExecutionState.PARTIAL if is_partial else PaperExecutionState.FILLED
    code = (
        PaperExecutionReasonCode.FILL_PARTIAL
        if is_partial
        else PaperExecutionReasonCode.FILL_COMPLETE
    )
    unfilled_notional_usd = intent.requested_notional_usd - fill_notional_usd
    fill = PaperFill(
        intent_idempotency_key=intent.idempotency_key,
        mint=intent.mint,
        side=intent.side,
        state=state,
        requested_notional_usd=intent.requested_notional_usd,
        filled_notional_usd=fill_notional_usd,
        unfilled_notional_usd=unfilled_notional_usd,
        quantity=quantity,
        reference_price_usd=quote.reference_price_usd,
        execution_price_usd=quote.execution_price_usd,
        signed_slippage_bps=signed_slippage_bps,
        signed_slippage_usd=signed_slippage_usd,
        swap_fee_usd=swap_fee_usd,
        network_fee_usd=network_fee_usd,
        explicit_cost_usd=explicit_cost_usd,
        net_cash_flow_usd=net_cash_flow_usd,
        quote_provider=quote.provider,
        executed_at_unix_ms=quote.observed_at_unix_ms,
    )
    return PaperExecutionResult(
        policy_version=policy.version,
        intent_idempotency_key=intent.idempotency_key,
        mint=intent.mint,
        side=intent.side,
        state=state,
        requested_notional_usd=intent.requested_notional_usd,
        evaluated_at_unix_ms=context.evaluated_at_unix_ms,
        quote_observed_at_unix_ms=quote.observed_at_unix_ms,
        swap_fee_usd=swap_fee_usd,
        network_fee_usd=network_fee_usd,
        explicit_cost_usd=explicit_cost_usd,
        net_cash_flow_usd=net_cash_flow_usd,
        findings=(PaperExecutionFinding(code=code, message=_message(code)),),
        fill=fill,
    )


def _terminal(
    intent: TradeIntent,
    context: PaperExecutionContext,
    policy: PaperFillPolicy,
    state: PaperExecutionState,
    code: PaperExecutionReasonCode,
    *,
    quote_timestamp: int | None = None,
    network_fee_usd: float = 0.0,
    net_cash_flow_usd: float = 0.0,
) -> PaperExecutionResult:
    return PaperExecutionResult(
        policy_version=policy.version,
        intent_idempotency_key=intent.idempotency_key,
        mint=intent.mint,
        side=intent.side,
        state=state,
        requested_notional_usd=intent.requested_notional_usd,
        evaluated_at_unix_ms=context.evaluated_at_unix_ms,
        quote_observed_at_unix_ms=quote_timestamp,
        swap_fee_usd=0.0,
        network_fee_usd=network_fee_usd,
        explicit_cost_usd=network_fee_usd,
        net_cash_flow_usd=net_cash_flow_usd,
        findings=(PaperExecutionFinding(code=code, message=_message(code)),),
        fill=None,
    )


def _message(code: PaperExecutionReasonCode) -> str:
    return code.value.replace("_", " ").lower()
