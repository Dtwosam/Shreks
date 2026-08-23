from __future__ import annotations

from dataclasses import replace
import hashlib
import math

from shreks_brain.paper.ledger_models import (
    PaperLedger,
    PaperLedgerEntry,
    PaperLedgerFinding,
    PaperLedgerReasonCode,
    PaperLedgerUpdate,
    PaperLedgerUpdateState,
    PaperPosition,
    PaperPositionMark,
    PaperPositionState,
)
from shreks_brain.paper.models import (
    PaperExecutionReasonCode,
    PaperExecutionResult,
    PaperExecutionState,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


_ACCOUNTING_REL_TOL = 1e-12
_ACCOUNTING_ABS_TOL = 1e-9
_POSITION_ID_VERSION = "c3-position-v1"

_DEFERRED_REASONS = frozenset(
    {
        PaperExecutionReasonCode.LATENCY_PENDING,
        PaperExecutionReasonCode.QUOTE_PENDING,
        PaperExecutionReasonCode.QUOTE_BEFORE_LATENCY,
    }
)
_FILL_REASONS = frozenset(
    {
        PaperExecutionReasonCode.FILL_PARTIAL,
        PaperExecutionReasonCode.FILL_COMPLETE,
    }
)


def create_paper_ledger(starting_cash_usd: float, as_of_unix_ms: int) -> PaperLedger:
    """Create an empty authoritative paper ledger with caller-supplied capital."""

    return PaperLedger(
        starting_cash_usd=starting_cash_usd,
        cash_balance_usd=starting_cash_usd,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=0.0,
        accumulated_costs_usd=0.0,
        as_of_unix_ms=as_of_unix_ms,
        positions=(),
        entries=(),
        processed_intent_keys=frozenset(),
    )


def apply_paper_execution(
    ledger: PaperLedger,
    intent: TradeIntent,
    execution: PaperExecutionResult,
) -> PaperLedgerUpdate:
    """Book one C1 execution result into immutable paper accounting state."""

    if intent.execution_mode is not RuntimeMode.PAPER:
        return _rejected(ledger, PaperLedgerReasonCode.INTENT_MODE_NOT_PAPER)
    if intent.idempotency_key != execution.intent_idempotency_key:
        return _rejected(ledger, PaperLedgerReasonCode.INTENT_RESULT_KEY_MISMATCH)
    if intent.mint != execution.mint:
        return _rejected(ledger, PaperLedgerReasonCode.INTENT_RESULT_MINT_MISMATCH)
    if intent.side is not execution.side:
        return _rejected(ledger, PaperLedgerReasonCode.INTENT_RESULT_SIDE_MISMATCH)
    if not _close(intent.requested_notional_usd, execution.requested_notional_usd):
        return _rejected(ledger, PaperLedgerReasonCode.INTENT_RESULT_NOTIONAL_MISMATCH)
    if not _execution_reason_matches_state(execution):
        return _rejected(ledger, PaperLedgerReasonCode.EXECUTION_REASON_STATE_MISMATCH)
    if intent.idempotency_key in ledger.processed_intent_keys:
        return _rejected(ledger, PaperLedgerReasonCode.DUPLICATE_TERMINAL_INTENT)
    if execution.evaluated_at_unix_ms < ledger.as_of_unix_ms:
        return _rejected(ledger, PaperLedgerReasonCode.EXECUTION_TIME_BEFORE_LEDGER)
    if execution.state is PaperExecutionState.DEFERRED:
        return _noop(ledger, PaperLedgerReasonCode.EXECUTION_DEFERRED_NOOP)

    proposed_cash = ledger.cash_balance_usd + execution.net_cash_flow_usd
    if proposed_cash < 0.0 and not _close(proposed_cash, 0.0):
        return _rejected(ledger, PaperLedgerReasonCode.INSUFFICIENT_CASH)
    if _close(proposed_cash, 0.0):
        proposed_cash = 0.0

    open_index, open_position = _find_open_position(ledger, intent.mint)

    if execution.state is PaperExecutionState.FAILED:
        return _book_failed(
            ledger,
            intent,
            execution,
            proposed_cash,
            open_index,
            open_position,
        )

    fill = execution.fill
    if fill is None:
        return _rejected(ledger, PaperLedgerReasonCode.EXECUTION_REASON_STATE_MISMATCH)

    if intent.side is TradeSide.BUY:
        return _book_buy(
            ledger,
            intent,
            execution,
            proposed_cash,
            open_index,
            open_position,
        )

    if open_position is None or open_index is None:
        return _rejected(ledger, PaperLedgerReasonCode.SELL_WITHOUT_OPEN_POSITION)
    if fill.quantity > open_position.quantity and not _close(
        fill.quantity, open_position.quantity
    ):
        return _rejected(ledger, PaperLedgerReasonCode.SELL_QUANTITY_EXCEEDS_POSITION)
    return _book_sell(
        ledger,
        intent,
        execution,
        proposed_cash,
        open_index,
        open_position,
    )


def _book_failed(
    ledger: PaperLedger,
    intent: TradeIntent,
    execution: PaperExecutionResult,
    proposed_cash: float,
    open_index: int | None,
    open_position: PaperPosition | None,
) -> PaperLedgerUpdate:
    realized_delta = execution.net_cash_flow_usd
    position_id = open_position.position_id if open_position is not None else None
    positions = ledger.positions

    if open_position is not None and open_index is not None and (
        not _close(realized_delta, 0.0) or not _close(execution.explicit_cost_usd, 0.0)
    ):
        changed = replace(
            open_position,
            realized_pnl_usd=open_position.realized_pnl_usd + realized_delta,
            accumulated_costs_usd=(
                open_position.accumulated_costs_usd + execution.explicit_cost_usd
            ),
            updated_at_unix_ms=execution.evaluated_at_unix_ms,
        )
        positions = _replace_position(positions, open_index, changed)

    entry = _entry(
        ledger,
        intent,
        execution,
        PaperLedgerReasonCode.FAILED_EXECUTION_BOOKED,
        position_id=position_id,
        realized_pnl_delta_usd=realized_delta,
    )
    new_ledger = _ledger_after_entry(
        ledger,
        execution,
        positions,
        entry,
        proposed_cash,
        realized_delta,
    )
    return _applied(
        new_ledger,
        PaperLedgerReasonCode.FAILED_EXECUTION_BOOKED,
        position_id,
        execution.net_cash_flow_usd,
        realized_delta,
        execution.explicit_cost_usd,
    )


def _book_buy(
    ledger: PaperLedger,
    intent: TradeIntent,
    execution: PaperExecutionResult,
    proposed_cash: float,
    open_index: int | None,
    open_position: PaperPosition | None,
) -> PaperLedgerUpdate:
    fill = execution.fill
    assert fill is not None

    if open_position is None or open_index is None:
        position_id = _position_id(intent.mint, intent.idempotency_key)
        position = PaperPosition(
            position_id=position_id,
            mint=intent.mint,
            state=PaperPositionState.OPEN,
            quantity=fill.quantity,
            weighted_entry_price_usd=fill.execution_price_usd,
            open_cost_basis_usd=(
                fill.filled_notional_usd + execution.explicit_cost_usd
            ),
            realized_pnl_usd=0.0,
            unrealized_pnl_usd=None,
            accumulated_costs_usd=execution.explicit_cost_usd,
            opened_at_unix_ms=execution.evaluated_at_unix_ms,
            updated_at_unix_ms=execution.evaluated_at_unix_ms,
            closed_at_unix_ms=None,
            last_mark_price_usd=None,
            last_mark_at_unix_ms=None,
            buy_fill_count=1,
            sell_fill_count=0,
        )
        positions = ledger.positions + (position,)
        reason = PaperLedgerReasonCode.POSITION_OPENED
    else:
        position_id = open_position.position_id
        total_quantity = open_position.quantity + fill.quantity
        weighted_entry = (
            open_position.quantity * open_position.weighted_entry_price_usd
            + fill.filled_notional_usd
        ) / total_quantity
        position = replace(
            open_position,
            quantity=total_quantity,
            weighted_entry_price_usd=weighted_entry,
            open_cost_basis_usd=(
                open_position.open_cost_basis_usd
                + fill.filled_notional_usd
                + execution.explicit_cost_usd
            ),
            accumulated_costs_usd=(
                open_position.accumulated_costs_usd + execution.explicit_cost_usd
            ),
            unrealized_pnl_usd=None,
            updated_at_unix_ms=execution.evaluated_at_unix_ms,
            last_mark_price_usd=None,
            last_mark_at_unix_ms=None,
            buy_fill_count=open_position.buy_fill_count + 1,
        )
        positions = _replace_position(ledger.positions, open_index, position)
        reason = PaperLedgerReasonCode.POSITION_INCREASED

    entry = _entry(
        ledger,
        intent,
        execution,
        reason,
        position_id=position_id,
        realized_pnl_delta_usd=0.0,
    )
    new_ledger = _ledger_after_entry(
        ledger,
        execution,
        positions,
        entry,
        proposed_cash,
        0.0,
    )
    return _applied(
        new_ledger,
        reason,
        position_id,
        execution.net_cash_flow_usd,
        0.0,
        execution.explicit_cost_usd,
    )


def _book_sell(
    ledger: PaperLedger,
    intent: TradeIntent,
    execution: PaperExecutionResult,
    proposed_cash: float,
    open_index: int,
    open_position: PaperPosition,
) -> PaperLedgerUpdate:
    fill = execution.fill
    assert fill is not None

    closes = _close(fill.quantity, open_position.quantity)
    fraction = 1.0 if closes else fill.quantity / open_position.quantity
    released_basis = open_position.open_cost_basis_usd * fraction
    realized_delta = execution.net_cash_flow_usd - released_basis

    if closes:
        position = replace(
            open_position,
            state=PaperPositionState.CLOSED,
            quantity=0.0,
            open_cost_basis_usd=0.0,
            realized_pnl_usd=open_position.realized_pnl_usd + realized_delta,
            unrealized_pnl_usd=0.0,
            accumulated_costs_usd=(
                open_position.accumulated_costs_usd + execution.explicit_cost_usd
            ),
            updated_at_unix_ms=execution.evaluated_at_unix_ms,
            closed_at_unix_ms=execution.evaluated_at_unix_ms,
            last_mark_price_usd=None,
            last_mark_at_unix_ms=None,
            sell_fill_count=open_position.sell_fill_count + 1,
        )
        reason = PaperLedgerReasonCode.POSITION_CLOSED
    else:
        remaining_quantity = open_position.quantity - fill.quantity
        remaining_basis = open_position.open_cost_basis_usd - released_basis
        if _close(remaining_basis, 0.0):
            remaining_basis = 0.0
        position = replace(
            open_position,
            quantity=remaining_quantity,
            open_cost_basis_usd=remaining_basis,
            realized_pnl_usd=open_position.realized_pnl_usd + realized_delta,
            unrealized_pnl_usd=None,
            accumulated_costs_usd=(
                open_position.accumulated_costs_usd + execution.explicit_cost_usd
            ),
            updated_at_unix_ms=execution.evaluated_at_unix_ms,
            last_mark_price_usd=None,
            last_mark_at_unix_ms=None,
            sell_fill_count=open_position.sell_fill_count + 1,
        )
        reason = PaperLedgerReasonCode.POSITION_REDUCED

    positions = _replace_position(ledger.positions, open_index, position)
    entry = _entry(
        ledger,
        intent,
        execution,
        reason,
        position_id=open_position.position_id,
        realized_pnl_delta_usd=realized_delta,
    )
    new_ledger = _ledger_after_entry(
        ledger,
        execution,
        positions,
        entry,
        proposed_cash,
        realized_delta,
    )
    return _applied(
        new_ledger,
        reason,
        open_position.position_id,
        execution.net_cash_flow_usd,
        realized_delta,
        execution.explicit_cost_usd,
    )


def _ledger_after_entry(
    ledger: PaperLedger,
    execution: PaperExecutionResult,
    positions: tuple[PaperPosition, ...],
    entry: PaperLedgerEntry,
    cash_balance_usd: float,
    realized_delta: float,
) -> PaperLedger:
    entries = ledger.entries + (entry,)
    return PaperLedger(
        starting_cash_usd=ledger.starting_cash_usd,
        cash_balance_usd=cash_balance_usd,
        realized_pnl_usd=ledger.realized_pnl_usd + realized_delta,
        unrealized_pnl_usd=_aggregate_unrealized(positions),
        accumulated_costs_usd=(
            ledger.accumulated_costs_usd + execution.explicit_cost_usd
        ),
        as_of_unix_ms=execution.evaluated_at_unix_ms,
        positions=positions,
        entries=entries,
        processed_intent_keys=(
            ledger.processed_intent_keys | frozenset({execution.intent_idempotency_key})
        ),
    )


def _entry(
    ledger: PaperLedger,
    intent: TradeIntent,
    execution: PaperExecutionResult,
    ledger_reason: PaperLedgerReasonCode,
    *,
    position_id: str | None,
    realized_pnl_delta_usd: float,
) -> PaperLedgerEntry:
    fill = execution.fill
    return PaperLedgerEntry(
        sequence=len(ledger.entries) + 1,
        intent_idempotency_key=intent.idempotency_key,
        position_id=position_id,
        mint=intent.mint,
        side=intent.side,
        execution_state=execution.state,
        paper_execution_reason_code=execution.findings[0].code,
        ledger_reason_code=ledger_reason,
        strategy_name=intent.strategy_name,
        strategy_version=intent.strategy_version,
        score_policy_version=intent.score_policy_version,
        decision_policy_version=intent.decision_policy_version,
        risk_policy_version=intent.risk_policy_version,
        paper_policy_version=execution.policy_version,
        booked_at_unix_ms=execution.evaluated_at_unix_ms,
        filled_quantity=fill.quantity if fill is not None else 0.0,
        filled_notional_usd=fill.filled_notional_usd if fill is not None else 0.0,
        cash_flow_usd=execution.net_cash_flow_usd,
        explicit_cost_usd=execution.explicit_cost_usd,
        realized_pnl_delta_usd=realized_pnl_delta_usd,
    )


def _execution_reason_matches_state(execution: PaperExecutionResult) -> bool:
    reason = execution.findings[0].code
    if execution.state is PaperExecutionState.DEFERRED:
        return reason in _DEFERRED_REASONS
    if execution.state is PaperExecutionState.PARTIAL:
        return reason is PaperExecutionReasonCode.FILL_PARTIAL
    if execution.state is PaperExecutionState.FILLED:
        return reason is PaperExecutionReasonCode.FILL_COMPLETE
    return reason not in _DEFERRED_REASONS and reason not in _FILL_REASONS


def _find_open_position(
    ledger: PaperLedger,
    mint: str,
) -> tuple[int | None, PaperPosition | None]:
    for index, position in enumerate(ledger.positions):
        if position.mint == mint and position.state is PaperPositionState.OPEN:
            return index, position
    return None, None


def _replace_position(
    positions: tuple[PaperPosition, ...],
    index: int,
    position: PaperPosition,
) -> tuple[PaperPosition, ...]:
    return positions[:index] + (position,) + positions[index + 1 :]


def _aggregate_unrealized(positions: tuple[PaperPosition, ...]) -> float | None:
    open_positions = tuple(
        position for position in positions if position.state is PaperPositionState.OPEN
    )
    if not open_positions:
        return 0.0
    if any(position.unrealized_pnl_usd is None for position in open_positions):
        return None
    return sum(position.unrealized_pnl_usd or 0.0 for position in open_positions)


def _position_id(mint: str, first_buy_intent_key: str) -> str:
    payload = f"{_POSITION_ID_VERSION}|{mint}|{first_buy_intent_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _rejected(ledger: PaperLedger, code: PaperLedgerReasonCode) -> PaperLedgerUpdate:
    return PaperLedgerUpdate(
        state=PaperLedgerUpdateState.REJECTED,
        ledger=ledger,
        position_id=None,
        cash_delta_usd=0.0,
        realized_pnl_delta_usd=0.0,
        cost_delta_usd=0.0,
        findings=(PaperLedgerFinding(code, _message(code)),),
    )


def _noop(ledger: PaperLedger, code: PaperLedgerReasonCode) -> PaperLedgerUpdate:
    return PaperLedgerUpdate(
        state=PaperLedgerUpdateState.NOOP,
        ledger=ledger,
        position_id=None,
        cash_delta_usd=0.0,
        realized_pnl_delta_usd=0.0,
        cost_delta_usd=0.0,
        findings=(PaperLedgerFinding(code, _message(code)),),
    )


def _applied(
    ledger: PaperLedger,
    code: PaperLedgerReasonCode,
    position_id: str | None,
    cash_delta_usd: float,
    realized_pnl_delta_usd: float,
    cost_delta_usd: float,
) -> PaperLedgerUpdate:
    return PaperLedgerUpdate(
        state=PaperLedgerUpdateState.APPLIED,
        ledger=ledger,
        position_id=position_id,
        cash_delta_usd=cash_delta_usd,
        realized_pnl_delta_usd=realized_pnl_delta_usd,
        cost_delta_usd=cost_delta_usd,
        findings=(PaperLedgerFinding(code, _message(code)),),
    )


def _message(code: PaperLedgerReasonCode) -> str:
    return code.value.replace("_", " ").lower()


def _close(left: float, right: float) -> bool:
    return math.isclose(
        left,
        right,
        rel_tol=_ACCOUNTING_REL_TOL,
        abs_tol=_ACCOUNTING_ABS_TOL,
    )
