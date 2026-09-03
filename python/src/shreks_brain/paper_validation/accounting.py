from __future__ import annotations

import math

from shreks_brain.paper import PaperExecutionState, PaperLedger, PaperPositionState
from shreks_brain.paper_loop import PaperLoopState
from shreks_brain.risk import TradeSide

from .models import (
    AccountingFinding,
    AccountingFindingCode,
    AccountingValidationReport,
    AccountingValidationStatus,
)


_REL_TOL = 1e-12
_ABS_TOL = 1e-9


def validate_paper_accounting(state: PaperLoopState) -> AccountingValidationReport:
    """Independently reconcile immutable C3/C5 paper accounting without mutation."""

    if not isinstance(state, PaperLoopState):
        raise ValueError("state must be a PaperLoopState")
    return validate_paper_ledger(state.ledger)


def validate_paper_ledger(ledger: PaperLedger) -> AccountingValidationReport:
    """Independently reconcile one authoritative C3 PAPER ledger without mutation."""

    if not isinstance(ledger, PaperLedger):
        raise ValueError("ledger must be a PaperLedger")

    findings: list[AccountingFinding] = []

    actual_sequences = tuple(entry.sequence for entry in ledger.entries)
    expected_sequences = tuple(range(1, len(ledger.entries) + 1))
    if actual_sequences != expected_sequences:
        findings.append(
            _finding(
                AccountingFindingCode.JOURNAL_SEQUENCE_MISMATCH,
                "journal sequence values do not reconcile from 1",
            )
        )

    journal_keys = frozenset(entry.intent_idempotency_key for entry in ledger.entries)
    if ledger.processed_intent_keys != journal_keys:
        findings.append(
            _finding(
                AccountingFindingCode.PROCESSED_INTENT_KEYS_MISMATCH,
                "processed intent keys do not equal terminal journal keys",
            )
        )

    expected_cash = ledger.starting_cash_usd + sum(
        entry.cash_flow_usd for entry in ledger.entries
    )
    if not _close(ledger.cash_balance_usd, expected_cash):
        findings.append(
            _finding(
                AccountingFindingCode.CASH_BALANCE_MISMATCH,
                "cash balance does not reconcile to starting cash plus journal cash flows",
                observed=ledger.cash_balance_usd,
                expected=expected_cash,
            )
        )

    expected_realized = sum(entry.realized_pnl_delta_usd for entry in ledger.entries)
    if not _close(ledger.realized_pnl_usd, expected_realized):
        findings.append(
            _finding(
                AccountingFindingCode.REALIZED_PNL_MISMATCH,
                "realized PnL does not reconcile to journal deltas",
                observed=ledger.realized_pnl_usd,
                expected=expected_realized,
            )
        )

    expected_costs = sum(entry.explicit_cost_usd for entry in ledger.entries)
    if not _close(ledger.accumulated_costs_usd, expected_costs):
        findings.append(
            _finding(
                AccountingFindingCode.ACCUMULATED_COSTS_MISMATCH,
                "accumulated costs do not reconcile to journal explicit costs",
                observed=ledger.accumulated_costs_usd,
                expected=expected_costs,
            )
        )

    running_quantity: dict[str, float] = {}
    partial_reduction_count = 0
    terminal_failure_count = 0
    for entry in ledger.entries:
        if entry.execution_state is PaperExecutionState.FAILED:
            terminal_failure_count += 1
        if entry.position_id is None or entry.filled_quantity <= 0.0:
            continue
        current = running_quantity.get(entry.position_id, 0.0)
        if entry.side is TradeSide.BUY:
            current += entry.filled_quantity
        else:
            current -= entry.filled_quantity
            if current > _ABS_TOL:
                partial_reduction_count += 1
        running_quantity[entry.position_id] = current

    open_positions = tuple(
        position for position in ledger.positions if position.state is PaperPositionState.OPEN
    )
    closed_positions = tuple(
        position for position in ledger.positions if position.state is PaperPositionState.CLOSED
    )

    for position in ledger.positions:
        linked = tuple(
            entry for entry in ledger.entries if entry.position_id == position.position_id
        )
        linked_realized = sum(entry.realized_pnl_delta_usd for entry in linked)
        if not _close(position.realized_pnl_usd, linked_realized):
            findings.append(
                _finding(
                    AccountingFindingCode.POSITION_REALIZED_PNL_MISMATCH,
                    "position realized PnL does not reconcile to linked journal deltas",
                    position.position_id,
                    position.realized_pnl_usd,
                    linked_realized,
                )
            )
        linked_costs = sum(entry.explicit_cost_usd for entry in linked)
        if not _close(position.accumulated_costs_usd, linked_costs):
            findings.append(
                _finding(
                    AccountingFindingCode.POSITION_ACCUMULATED_COSTS_MISMATCH,
                    "position accumulated costs do not reconcile to linked journal costs",
                    position.position_id,
                    position.accumulated_costs_usd,
                    linked_costs,
                )
            )
        expected_quantity = running_quantity.get(position.position_id, 0.0)
        if not _close(position.quantity, expected_quantity):
            findings.append(
                _finding(
                    AccountingFindingCode.POSITION_QUANTITY_MISMATCH,
                    "position quantity does not reconcile to linked BUY minus SELL fills",
                    position.position_id,
                    position.quantity,
                    expected_quantity,
                )
            )
        if position.state is PaperPositionState.OPEN and position.last_mark_price_usd is not None:
            expected_position_unrealized = (
                position.quantity * position.last_mark_price_usd - position.open_cost_basis_usd
            )
            if position.unrealized_pnl_usd is None or not _close(
                position.unrealized_pnl_usd, expected_position_unrealized
            ):
                findings.append(
                    _finding(
                        AccountingFindingCode.POSITION_UNREALIZED_PNL_MISMATCH,
                        "position unrealized PnL does not reconcile to mark minus open cost basis",
                        position.position_id,
                        position.unrealized_pnl_usd,
                        expected_position_unrealized,
                    )
                )

    if not open_positions:
        expected_unrealized: float | None = 0.0
    elif any(position.last_mark_price_usd is None for position in open_positions):
        expected_unrealized = None
    else:
        expected_unrealized = sum(
            position.quantity * (position.last_mark_price_usd or 0.0)
            - position.open_cost_basis_usd
            for position in open_positions
        )

    if expected_unrealized is None:
        if ledger.unrealized_pnl_usd is not None:
            findings.append(
                _finding(
                    AccountingFindingCode.UNREALIZED_PNL_MISMATCH,
                    "portfolio unrealized PnL must remain unknown while an OPEN position is unmarked",
                    observed=ledger.unrealized_pnl_usd,
                )
            )
        for position in open_positions:
            if position.last_mark_price_usd is None:
                findings.append(
                    _finding(
                        AccountingFindingCode.UNMARKED_OPEN_POSITION,
                        "OPEN position lacks current mark evidence for portfolio equity",
                        position.position_id,
                    )
                )
        open_market_value = None
        equity = None
        net_pnl = None
        expected_net_pnl = None
    else:
        if ledger.unrealized_pnl_usd is None or not _close(
            ledger.unrealized_pnl_usd, expected_unrealized
        ):
            findings.append(
                _finding(
                    AccountingFindingCode.UNREALIZED_PNL_MISMATCH,
                    "portfolio unrealized PnL does not reconcile to OPEN positions",
                    observed=ledger.unrealized_pnl_usd,
                    expected=expected_unrealized,
                )
            )
        open_market_value = sum(
            position.quantity * (position.last_mark_price_usd or 0.0)
            for position in open_positions
        )
        equity = ledger.cash_balance_usd + open_market_value
        net_pnl = equity - ledger.starting_cash_usd
        expected_net_pnl = expected_realized + expected_unrealized
        if not _close(net_pnl, expected_net_pnl):
            findings.append(
                _finding(
                    AccountingFindingCode.EQUITY_PNL_MISMATCH,
                    "marked portfolio equity PnL does not reconcile to realized plus unrealized PnL",
                    observed=net_pnl,
                    expected=expected_net_pnl,
                )
            )

    invalid_findings = tuple(
        finding
        for finding in findings
        if finding.code is not AccountingFindingCode.UNMARKED_OPEN_POSITION
    )
    if invalid_findings:
        status = AccountingValidationStatus.INVALID
    elif findings:
        status = AccountingValidationStatus.INCOMPLETE
    else:
        status = AccountingValidationStatus.RECONCILED

    winning = sum(position.realized_pnl_usd > _ABS_TOL for position in closed_positions)
    losing = sum(position.realized_pnl_usd < -_ABS_TOL for position in closed_positions)
    flat = len(closed_positions) - winning - losing

    return AccountingValidationReport(
        status=status,
        as_of_unix_ms=ledger.as_of_unix_ms,
        starting_cash_usd=ledger.starting_cash_usd,
        cash_balance_usd=ledger.cash_balance_usd,
        expected_cash_balance_usd=expected_cash,
        realized_pnl_usd=ledger.realized_pnl_usd,
        expected_realized_pnl_usd=expected_realized,
        unrealized_pnl_usd=ledger.unrealized_pnl_usd,
        expected_unrealized_pnl_usd=expected_unrealized,
        accumulated_costs_usd=ledger.accumulated_costs_usd,
        expected_accumulated_costs_usd=expected_costs,
        open_market_value_usd=open_market_value,
        equity_usd=equity,
        net_pnl_usd=net_pnl,
        expected_net_pnl_usd=expected_net_pnl,
        journal_entry_count=len(ledger.entries),
        terminal_failure_count=terminal_failure_count,
        lifecycle_count=len(ledger.positions),
        open_position_count=len(open_positions),
        closed_position_count=len(closed_positions),
        partial_reduction_count=partial_reduction_count,
        winning_closed_count=winning,
        losing_closed_count=losing,
        flat_closed_count=flat,
        findings=tuple(findings),
    )


def _finding(
    code: AccountingFindingCode,
    message: str,
    position_id: str | None = None,
    observed: float | int | None = None,
    expected: float | int | None = None,
) -> AccountingFinding:
    return AccountingFinding(code, message, position_id, observed, expected)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)
