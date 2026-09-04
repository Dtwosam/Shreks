from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math

from shreks_brain.observer_market.models import ObservedMarketWindow
from shreks_brain.paper import (
    PaperQuote,
    PaperQuoteState,
    derive_paper_risk_accounting_facts,
)
from shreks_brain.paper_loop import PaperLoopState
from shreks_brain.risk import RiskContext

from .models import (
    ObserverPaperQuoteEvidence,
    ObserverPaperQuotePurpose,
    ObserverPaperRiskEnvironment,
)


class ObserverPaperRiskContextError(ValueError):
    """Raised when paper-loop risk facts cannot be derived without guessing."""


def build_observer_risk_context(
    state: PaperLoopState,
    window: ObservedMarketWindow,
    entry_quote: tuple[ObserverPaperQuoteEvidence, PaperQuote] | None,
    environment: ObserverPaperRiskEnvironment,
) -> RiskContext:
    if type(state) is not PaperLoopState:
        raise ObserverPaperRiskContextError("state must be a PaperLoopState")
    if type(window) is not ObservedMarketWindow:
        raise ObserverPaperRiskContextError("window must be an ObservedMarketWindow")
    if type(environment) is not ObserverPaperRiskEnvironment:
        raise ObserverPaperRiskContextError(
            "environment must be an ObserverPaperRiskEnvironment"
        )
    if window.as_of_unix_ms < state.last_cycle_at_unix_ms:
        raise ObserverPaperRiskContextError(
            "risk as_of cannot precede current paper-loop state"
        )
    if environment.day_started_at_unix_ms > window.as_of_unix_ms:
        raise ObserverPaperRiskContextError("day start cannot be in the future")

    ledger = state.ledger
    accounting = derive_paper_risk_accounting_facts(
        ledger,
        day_started_at_unix_ms=environment.day_started_at_unix_ms,
    )

    current = window.current
    market_age = window.as_of_unix_ms - current.observed_at_unix_ms
    if market_age < 0:
        raise ObserverPaperRiskContextError("market evidence cannot be from the future")

    expected_price_impact: float | None = None
    price_impact_notional: float | None = None
    if entry_quote is not None:
        evidence, paper_quote = _validate_entry_quote_pair(window, entry_quote)
        if evidence.route_available and paper_quote.state is PaperQuoteState.EXECUTABLE:
            expected_price_impact = _optional_decimal_float(
                evidence.price_impact_pct,
                "entry price impact",
            )
            price_impact_notional = paper_quote.quoted_notional_usd

    active_keys = (
        frozenset({state.pending_entry.intent.idempotency_key})
        if state.pending_entry is not None
        else frozenset()
    )

    return RiskContext(
        as_of_unix_ms=window.as_of_unix_ms,
        trading_capital_usd=environment.trading_capital_usd,
        open_position_count=accounting.open_position_count,
        aggregate_open_risk_usd=accounting.aggregate_open_risk_usd,
        daily_realized_pnl_usd=accounting.daily_realized_pnl_usd,
        rolling_drawdown_pct=accounting.rolling_drawdown_pct,
        consecutive_losses=accounting.consecutive_losses,
        last_loss_at_unix_ms=accounting.last_loss_at_unix_ms,
        liquidity_usd=current.liquidity_usd,
        expected_price_impact_pct=expected_price_impact,
        price_impact_notional_usd=price_impact_notional,
        market_data_age_ms=market_age,
        data_healthy=environment.data_healthy,
        execution_healthy=environment.execution_healthy,
        kill_switch_active=environment.kill_switch_active,
        active_intent_keys=active_keys,
    )


def _validate_entry_quote_pair(
    window: ObservedMarketWindow,
    entry_quote: tuple[ObserverPaperQuoteEvidence, PaperQuote],
) -> tuple[ObserverPaperQuoteEvidence, PaperQuote]:
    if not isinstance(entry_quote, tuple) or len(entry_quote) != 2:
        raise ObserverPaperRiskContextError(
            "entry_quote must pair raw evidence with its reconstructed PaperQuote"
        )
    evidence, paper_quote = entry_quote
    if type(evidence) is not ObserverPaperQuoteEvidence or type(paper_quote) is not PaperQuote:
        raise ObserverPaperRiskContextError(
            "entry_quote must pair ObserverPaperQuoteEvidence and PaperQuote"
        )
    identity = evidence.identity
    if identity.purpose is not ObserverPaperQuotePurpose.ENTRY:
        raise ObserverPaperRiskContextError("risk entry quote must have ENTRY purpose")
    if identity.candidate_id != window.candidate.candidate_id:
        raise ObserverPaperRiskContextError("entry quote candidate attribution mismatch")
    if identity.output_mint != window.candidate.mint or paper_quote.mint != window.candidate.mint:
        raise ObserverPaperRiskContextError("entry quote mint attribution mismatch")
    if evidence.quoted_at_unix_ms != paper_quote.observed_at_unix_ms:
        raise ObserverPaperRiskContextError("entry quote timestamps are contradictory")
    if evidence.quoted_at_unix_ms > window.as_of_unix_ms:
        raise ObserverPaperRiskContextError("entry quote evidence cannot be from the future")
    if evidence.identity.provider != paper_quote.provider:
        raise ObserverPaperRiskContextError("entry quote provider attribution mismatch")
    if evidence.route_available:
        if paper_quote.state is not PaperQuoteState.EXECUTABLE:
            raise ObserverPaperRiskContextError(
                "route-available entry evidence requires an executable PaperQuote"
            )
    elif paper_quote.state is not PaperQuoteState.UNAVAILABLE:
        raise ObserverPaperRiskContextError(
            "route-unavailable entry evidence requires an unavailable PaperQuote"
        )
    return evidence, paper_quote



def _optional_decimal_float(value: str | None, name: str) -> float | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ObserverPaperRiskContextError(f"{name} is malformed") from error
    converted = float(parsed)
    if not parsed.is_finite() or not math.isfinite(converted) or converted < 0:
        raise ObserverPaperRiskContextError(f"{name} must be finite and non-negative")
    return converted
