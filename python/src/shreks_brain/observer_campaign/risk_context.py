from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math

from shreks_brain.observer_market.models import ObservedMarketWindow
from shreks_brain.paper import PaperPositionState, PaperQuote, PaperQuoteState
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
    open_positions = tuple(
        position
        for position in ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    aggregate_open_risk = sum(
        position.open_cost_basis_usd for position in open_positions
    )
    daily_realized = sum(
        item.realized_pnl_delta_usd
        for item in ledger.entries
        if item.booked_at_unix_ms >= environment.day_started_at_unix_ms
    )
    rolling_drawdown = _rolling_drawdown_pct(ledger)
    consecutive_losses, last_loss_at = _loss_streak(ledger.positions)

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
        open_position_count=len(open_positions),
        aggregate_open_risk_usd=aggregate_open_risk,
        daily_realized_pnl_usd=daily_realized,
        rolling_drawdown_pct=rolling_drawdown,
        consecutive_losses=consecutive_losses,
        last_loss_at_unix_ms=last_loss_at,
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


def _rolling_drawdown_pct(ledger) -> float | None:
    open_positions = tuple(
        position
        for position in ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    if any(position.unrealized_pnl_usd is None for position in open_positions):
        return None

    equity = ledger.starting_cash_usd
    points = [equity]
    for item in ledger.entries:
        equity += item.realized_pnl_delta_usd
        points.append(equity)
    current_unrealized = sum(
        position.unrealized_pnl_usd or 0.0 for position in open_positions
    )
    points.append(equity + current_unrealized)

    peak = points[0]
    maximum = 0.0
    for value in points:
        if value > peak:
            peak = value
        if peak <= 0:
            return None
        drawdown = (peak - value) / peak * 100.0
        maximum = max(maximum, drawdown)
    if not math.isfinite(maximum):
        return None
    return maximum


def _loss_streak(positions) -> tuple[int, int | None]:
    closed = sorted(
        (
            position
            for position in positions
            if position.state is PaperPositionState.CLOSED
        ),
        key=lambda position: (
            position.closed_at_unix_ms if position.closed_at_unix_ms is not None else -1,
            position.position_id,
        ),
    )
    streak = 0
    last_loss_at: int | None = None
    for position in reversed(closed):
        if position.realized_pnl_usd >= 0:
            break
        if last_loss_at is None:
            last_loss_at = position.closed_at_unix_ms
        streak += 1
    return streak, last_loss_at


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
