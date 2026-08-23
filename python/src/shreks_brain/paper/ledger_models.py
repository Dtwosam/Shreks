from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.paper.models import PaperExecutionReasonCode, PaperExecutionState
from shreks_brain.risk import TradeSide


_ACCOUNTING_REL_TOL = 1e-12
_ACCOUNTING_ABS_TOL = 1e-9


class PaperPositionState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PaperLedgerUpdateState(StrEnum):
    NOOP = "NOOP"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"


class PaperLedgerReasonCode(StrEnum):
    INTENT_MODE_NOT_PAPER = "INTENT_MODE_NOT_PAPER"
    INTENT_RESULT_KEY_MISMATCH = "INTENT_RESULT_KEY_MISMATCH"
    INTENT_RESULT_MINT_MISMATCH = "INTENT_RESULT_MINT_MISMATCH"
    INTENT_RESULT_SIDE_MISMATCH = "INTENT_RESULT_SIDE_MISMATCH"
    INTENT_RESULT_NOTIONAL_MISMATCH = "INTENT_RESULT_NOTIONAL_MISMATCH"
    EXECUTION_REASON_STATE_MISMATCH = "EXECUTION_REASON_STATE_MISMATCH"
    DUPLICATE_TERMINAL_INTENT = "DUPLICATE_TERMINAL_INTENT"
    EXECUTION_TIME_BEFORE_LEDGER = "EXECUTION_TIME_BEFORE_LEDGER"
    EXECUTION_DEFERRED_NOOP = "EXECUTION_DEFERRED_NOOP"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    SELL_WITHOUT_OPEN_POSITION = "SELL_WITHOUT_OPEN_POSITION"
    SELL_QUANTITY_EXCEEDS_POSITION = "SELL_QUANTITY_EXCEEDS_POSITION"
    FAILED_EXECUTION_BOOKED = "FAILED_EXECUTION_BOOKED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_INCREASED = "POSITION_INCREASED"
    POSITION_REDUCED = "POSITION_REDUCED"
    POSITION_CLOSED = "POSITION_CLOSED"
    MARK_TIME_BEFORE_LEDGER = "MARK_TIME_BEFORE_LEDGER"
    MARK_POSITION_NOT_FOUND = "MARK_POSITION_NOT_FOUND"
    MARK_MINT_MISMATCH = "MARK_MINT_MISMATCH"
    MARK_POSITION_CLOSED = "MARK_POSITION_CLOSED"
    POSITION_MARKED = "POSITION_MARKED"


@dataclass(frozen=True, slots=True)
class PaperPositionMark:
    position_id: str
    mint: str
    observed_at_unix_ms: int
    mark_price_usd: float

    def __post_init__(self) -> None:
        _require_non_empty_string("position_id", self.position_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_positive_finite("mark_price_usd", self.mark_price_usd)


@dataclass(frozen=True, slots=True)
class PaperPosition:
    position_id: str
    mint: str
    state: PaperPositionState
    quantity: float
    weighted_entry_price_usd: float
    open_cost_basis_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float | None
    accumulated_costs_usd: float
    opened_at_unix_ms: int
    updated_at_unix_ms: int
    closed_at_unix_ms: int | None
    last_mark_price_usd: float | None
    last_mark_at_unix_ms: int | None
    buy_fill_count: int
    sell_fill_count: int

    def __post_init__(self) -> None:
        _require_non_empty_string("position_id", self.position_id)
        _require_non_empty_string("mint", self.mint)
        if not isinstance(self.state, PaperPositionState):
            raise ValueError("state must be a PaperPositionState")
        _require_non_negative_finite("quantity", self.quantity)
        _require_positive_finite("weighted_entry_price_usd", self.weighted_entry_price_usd)
        _require_non_negative_finite("open_cost_basis_usd", self.open_cost_basis_usd)
        _require_finite("realized_pnl_usd", self.realized_pnl_usd)
        if self.unrealized_pnl_usd is not None:
            _require_finite("unrealized_pnl_usd", self.unrealized_pnl_usd)
        _require_non_negative_finite("accumulated_costs_usd", self.accumulated_costs_usd)
        _require_non_negative_int("opened_at_unix_ms", self.opened_at_unix_ms)
        _require_non_negative_int("updated_at_unix_ms", self.updated_at_unix_ms)
        if self.updated_at_unix_ms < self.opened_at_unix_ms:
            raise ValueError("updated_at_unix_ms must not precede opened_at_unix_ms")
        if self.closed_at_unix_ms is not None:
            _require_non_negative_int("closed_at_unix_ms", self.closed_at_unix_ms)
            if self.closed_at_unix_ms < self.opened_at_unix_ms:
                raise ValueError("closed_at_unix_ms must not precede opened_at_unix_ms")
            if self.closed_at_unix_ms > self.updated_at_unix_ms:
                raise ValueError("closed_at_unix_ms must not exceed updated_at_unix_ms")
        _require_positive_int("buy_fill_count", self.buy_fill_count)
        _require_non_negative_int("sell_fill_count", self.sell_fill_count)

        mark_price_present = self.last_mark_price_usd is not None
        mark_time_present = self.last_mark_at_unix_ms is not None
        if mark_price_present != mark_time_present:
            raise ValueError("last_mark_price_usd and last_mark_at_unix_ms must be paired")
        if mark_price_present:
            _require_positive_finite("last_mark_price_usd", self.last_mark_price_usd)
            _require_non_negative_int("last_mark_at_unix_ms", self.last_mark_at_unix_ms)
            assert self.last_mark_at_unix_ms is not None
            if self.last_mark_at_unix_ms < self.opened_at_unix_ms:
                raise ValueError("last_mark_at_unix_ms must not precede opened_at_unix_ms")
            if self.last_mark_at_unix_ms > self.updated_at_unix_ms:
                raise ValueError("last_mark_at_unix_ms must not exceed updated_at_unix_ms")

        if self.state is PaperPositionState.OPEN:
            if self.quantity <= 0.0:
                raise ValueError("OPEN position requires strictly positive quantity")
            if self.open_cost_basis_usd <= 0.0:
                raise ValueError("OPEN position requires strictly positive open_cost_basis_usd")
            if self.closed_at_unix_ms is not None:
                raise ValueError("OPEN position cannot have closed_at_unix_ms")
            if not mark_price_present:
                if self.unrealized_pnl_usd is not None:
                    raise ValueError("unrealized_pnl_usd requires current last_mark evidence")
            else:
                if self.unrealized_pnl_usd is None:
                    raise ValueError("unrealized_pnl_usd is required with current last_mark evidence")
                assert self.last_mark_price_usd is not None
                expected = self.quantity * self.last_mark_price_usd - self.open_cost_basis_usd
                _require_close("unrealized_pnl_usd", self.unrealized_pnl_usd, expected)
            return

        if self.closed_at_unix_ms is None:
            raise ValueError("closed_at_unix_ms is required for CLOSED position")
        if not _is_zero(self.quantity):
            raise ValueError("CLOSED position requires zero quantity")
        if not _is_zero(self.open_cost_basis_usd):
            raise ValueError("CLOSED position requires zero open_cost_basis_usd")
        if self.unrealized_pnl_usd is None or not _is_zero(self.unrealized_pnl_usd):
            raise ValueError("CLOSED position requires unrealized_pnl_usd equal to zero")


@dataclass(frozen=True, slots=True)
class PaperLedgerEntry:
    sequence: int
    intent_idempotency_key: str
    position_id: str | None
    mint: str
    side: TradeSide
    execution_state: PaperExecutionState
    paper_execution_reason_code: PaperExecutionReasonCode
    ledger_reason_code: PaperLedgerReasonCode
    strategy_name: str
    strategy_version: str
    score_policy_version: str
    decision_policy_version: str
    risk_policy_version: str
    paper_policy_version: str
    booked_at_unix_ms: int
    filled_quantity: float
    filled_notional_usd: float
    cash_flow_usd: float
    explicit_cost_usd: float
    realized_pnl_delta_usd: float

    def __post_init__(self) -> None:
        _require_positive_int("sequence", self.sequence)
        _require_non_empty_string("intent_idempotency_key", self.intent_idempotency_key)
        if self.position_id is not None:
            _require_non_empty_string("position_id", self.position_id)
        _require_non_empty_string("mint", self.mint)
        if not isinstance(self.side, TradeSide):
            raise ValueError("side must be a TradeSide")
        if self.execution_state not in (
            PaperExecutionState.FAILED,
            PaperExecutionState.PARTIAL,
            PaperExecutionState.FILLED,
        ):
            raise ValueError("execution_state must be terminal FAILED/PARTIAL/FILLED")
        if not isinstance(self.paper_execution_reason_code, PaperExecutionReasonCode):
            raise ValueError("paper_execution_reason_code must be a PaperExecutionReasonCode")
        if not isinstance(self.ledger_reason_code, PaperLedgerReasonCode):
            raise ValueError("ledger_reason_code must be a PaperLedgerReasonCode")
        for name in (
            "strategy_name",
            "strategy_version",
            "score_policy_version",
            "decision_policy_version",
            "risk_policy_version",
            "paper_policy_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("booked_at_unix_ms", self.booked_at_unix_ms)
        _require_non_negative_finite("filled_quantity", self.filled_quantity)
        _require_non_negative_finite("filled_notional_usd", self.filled_notional_usd)
        _require_finite("cash_flow_usd", self.cash_flow_usd)
        _require_non_negative_finite("explicit_cost_usd", self.explicit_cost_usd)
        _require_finite("realized_pnl_delta_usd", self.realized_pnl_delta_usd)

        if self.execution_state is PaperExecutionState.FAILED:
            if not _is_zero(self.filled_quantity) or not _is_zero(self.filled_notional_usd):
                raise ValueError("FAILED entry requires zero filled quantity/notional")
        elif self.filled_quantity <= 0.0 or self.filled_notional_usd <= 0.0:
            raise ValueError("PARTIAL/FILLED entry requires positive filled quantity/notional")


@dataclass(frozen=True, slots=True)
class PaperLedger:
    starting_cash_usd: float
    cash_balance_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float | None
    accumulated_costs_usd: float
    as_of_unix_ms: int
    positions: tuple[PaperPosition, ...]
    entries: tuple[PaperLedgerEntry, ...]
    processed_intent_keys: frozenset[str]

    def __post_init__(self) -> None:
        _require_non_negative_finite("starting_cash_usd", self.starting_cash_usd)
        _require_non_negative_finite("cash_balance_usd", self.cash_balance_usd)
        _require_finite("realized_pnl_usd", self.realized_pnl_usd)
        if self.unrealized_pnl_usd is not None:
            _require_finite("unrealized_pnl_usd", self.unrealized_pnl_usd)
        _require_non_negative_finite("accumulated_costs_usd", self.accumulated_costs_usd)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.positions, tuple) or not all(
            isinstance(position, PaperPosition) for position in self.positions
        ):
            raise ValueError("positions must be a tuple of PaperPosition values")
        if not isinstance(self.entries, tuple) or not all(
            isinstance(entry, PaperLedgerEntry) for entry in self.entries
        ):
            raise ValueError("entries must be a tuple of PaperLedgerEntry values")
        if not isinstance(self.processed_intent_keys, frozenset) or not all(
            isinstance(key, str) and key.strip() for key in self.processed_intent_keys
        ):
            raise ValueError("processed_intent_keys must be a frozenset of non-empty strings")

        position_ids = tuple(position.position_id for position in self.positions)
        if len(position_ids) != len(set(position_ids)):
            raise ValueError("position_id values must be unique")
        open_mints = tuple(
            position.mint
            for position in self.positions
            if position.state is PaperPositionState.OPEN
        )
        if len(open_mints) != len(set(open_mints)):
            raise ValueError("at most one OPEN position may exist per mint")

        expected_sequences = tuple(range(1, len(self.entries) + 1))
        actual_sequences = tuple(entry.sequence for entry in self.entries)
        if actual_sequences != expected_sequences:
            raise ValueError("journal sequence values must be contiguous from 1")
        intent_keys = tuple(entry.intent_idempotency_key for entry in self.entries)
        if len(intent_keys) != len(set(intent_keys)):
            raise ValueError("journal intent idempotency keys must be unique")
        if self.processed_intent_keys != frozenset(intent_keys):
            raise ValueError("processed_intent_keys must equal terminal journal intent keys")

        expected_cash = self.starting_cash_usd + sum(
            entry.cash_flow_usd for entry in self.entries
        )
        _require_close("cash_balance_usd", self.cash_balance_usd, expected_cash)
        expected_realized = sum(entry.realized_pnl_delta_usd for entry in self.entries)
        _require_close("realized_pnl_usd", self.realized_pnl_usd, expected_realized)
        expected_costs = sum(entry.explicit_cost_usd for entry in self.entries)
        _require_close("accumulated_costs_usd", self.accumulated_costs_usd, expected_costs)

        for position in self.positions:
            linked = tuple(
                entry for entry in self.entries if entry.position_id == position.position_id
            )
            linked_realized = sum(entry.realized_pnl_delta_usd for entry in linked)
            if not math.isclose(
                position.realized_pnl_usd,
                linked_realized,
                rel_tol=_ACCOUNTING_REL_TOL,
                abs_tol=_ACCOUNTING_ABS_TOL,
            ):
                raise ValueError("position realized_pnl_usd must equal linked journal deltas")
            linked_costs = sum(entry.explicit_cost_usd for entry in linked)
            if not math.isclose(
                position.accumulated_costs_usd,
                linked_costs,
                rel_tol=_ACCOUNTING_REL_TOL,
                abs_tol=_ACCOUNTING_ABS_TOL,
            ):
                raise ValueError("position accumulated_costs_usd must equal linked journal costs")

        for entry in self.entries:
            if entry.booked_at_unix_ms > self.as_of_unix_ms:
                raise ValueError("as_of_unix_ms must not precede journal bookings")
        for position in self.positions:
            if position.updated_at_unix_ms > self.as_of_unix_ms:
                raise ValueError("as_of_unix_ms must not precede position updates")

        open_positions = tuple(
            position
            for position in self.positions
            if position.state is PaperPositionState.OPEN
        )
        if not open_positions:
            if self.unrealized_pnl_usd is None or not _is_zero(self.unrealized_pnl_usd):
                raise ValueError("unrealized_pnl_usd must be zero with no OPEN positions")
        elif any(position.unrealized_pnl_usd is None for position in open_positions):
            if self.unrealized_pnl_usd is not None:
                raise ValueError("unrealized_pnl_usd must be None when any OPEN position is unmarked")
        else:
            expected_unrealized = sum(
                position.unrealized_pnl_usd or 0.0 for position in open_positions
            )
            if self.unrealized_pnl_usd is None:
                raise ValueError("unrealized_pnl_usd is required when all OPEN positions are marked")
            _require_close("unrealized_pnl_usd", self.unrealized_pnl_usd, expected_unrealized)


@dataclass(frozen=True, slots=True)
class PaperLedgerFinding:
    code: PaperLedgerReasonCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, PaperLedgerReasonCode):
            raise ValueError("code must be a PaperLedgerReasonCode")
        _require_non_empty_string("message", self.message)


@dataclass(frozen=True, slots=True)
class PaperLedgerUpdate:
    state: PaperLedgerUpdateState
    ledger: PaperLedger
    position_id: str | None
    cash_delta_usd: float
    realized_pnl_delta_usd: float
    cost_delta_usd: float
    findings: tuple[PaperLedgerFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, PaperLedgerUpdateState):
            raise ValueError("state must be a PaperLedgerUpdateState")
        if not isinstance(self.ledger, PaperLedger):
            raise ValueError("ledger must be a PaperLedger")
        if self.position_id is not None:
            _require_non_empty_string("position_id", self.position_id)
        _require_finite("cash_delta_usd", self.cash_delta_usd)
        _require_finite("realized_pnl_delta_usd", self.realized_pnl_delta_usd)
        _require_finite("cost_delta_usd", self.cost_delta_usd)
        if not isinstance(self.findings, tuple) or len(self.findings) != 1 or not isinstance(
            self.findings[0], PaperLedgerFinding
        ):
            raise ValueError("findings must contain exactly one PaperLedgerFinding")
        if self.state in (PaperLedgerUpdateState.NOOP, PaperLedgerUpdateState.REJECTED):
            if not (
                _is_zero(self.cash_delta_usd)
                and _is_zero(self.realized_pnl_delta_usd)
                and _is_zero(self.cost_delta_usd)
            ):
                raise ValueError("NOOP/REJECTED updates require zero economic deltas")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_positive_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be strictly positive")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_close(name: str, actual: float, expected: float) -> None:
    if not math.isclose(
        actual,
        expected,
        rel_tol=_ACCOUNTING_REL_TOL,
        abs_tol=_ACCOUNTING_ABS_TOL,
    ):
        raise ValueError(f"{name} is inconsistent")


def _is_zero(value: float) -> bool:
    return math.isclose(
        value,
        0.0,
        rel_tol=_ACCOUNTING_REL_TOL,
        abs_tol=_ACCOUNTING_ABS_TOL,
    )
