from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.paper_loop import PaperLoopState


_CHECKPOINT_SCHEMA_VERSION = "c6-paper-state-v1"


class AccountingValidationStatus(StrEnum):
    RECONCILED = "RECONCILED"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


class AccountingFindingCode(StrEnum):
    JOURNAL_SEQUENCE_MISMATCH = "JOURNAL_SEQUENCE_MISMATCH"
    PROCESSED_INTENT_KEYS_MISMATCH = "PROCESSED_INTENT_KEYS_MISMATCH"
    CASH_BALANCE_MISMATCH = "CASH_BALANCE_MISMATCH"
    REALIZED_PNL_MISMATCH = "REALIZED_PNL_MISMATCH"
    ACCUMULATED_COSTS_MISMATCH = "ACCUMULATED_COSTS_MISMATCH"
    POSITION_REALIZED_PNL_MISMATCH = "POSITION_REALIZED_PNL_MISMATCH"
    POSITION_ACCUMULATED_COSTS_MISMATCH = "POSITION_ACCUMULATED_COSTS_MISMATCH"
    POSITION_QUANTITY_MISMATCH = "POSITION_QUANTITY_MISMATCH"
    POSITION_UNREALIZED_PNL_MISMATCH = "POSITION_UNREALIZED_PNL_MISMATCH"
    UNREALIZED_PNL_MISMATCH = "UNREALIZED_PNL_MISMATCH"
    UNMARKED_OPEN_POSITION = "UNMARKED_OPEN_POSITION"
    EQUITY_PNL_MISMATCH = "EQUITY_PNL_MISMATCH"


@dataclass(frozen=True, slots=True)
class AccountingFinding:
    code: AccountingFindingCode
    message: str
    position_id: str | None = None
    observed_value: float | int | None = None
    expected_value: float | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, AccountingFindingCode):
            raise ValueError("code must be an AccountingFindingCode")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be a non-empty string")
        if self.position_id is not None and (
            not isinstance(self.position_id, str) or not self.position_id.strip()
        ):
            raise ValueError("position_id must be a non-empty string or None")
        for name in ("observed_value", "expected_value"):
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name} must be numeric or None")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError(f"{name} must be finite")


@dataclass(frozen=True, slots=True)
class AccountingValidationReport:
    status: AccountingValidationStatus
    as_of_unix_ms: int
    starting_cash_usd: float
    cash_balance_usd: float
    expected_cash_balance_usd: float
    realized_pnl_usd: float
    expected_realized_pnl_usd: float
    unrealized_pnl_usd: float | None
    expected_unrealized_pnl_usd: float | None
    accumulated_costs_usd: float
    expected_accumulated_costs_usd: float
    open_market_value_usd: float | None
    equity_usd: float | None
    net_pnl_usd: float | None
    expected_net_pnl_usd: float | None
    journal_entry_count: int
    terminal_failure_count: int
    lifecycle_count: int
    open_position_count: int
    closed_position_count: int
    partial_reduction_count: int
    winning_closed_count: int
    losing_closed_count: int
    flat_closed_count: int
    findings: tuple[AccountingFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, AccountingValidationStatus):
            raise ValueError("status must be an AccountingValidationStatus")
        if (
            isinstance(self.as_of_unix_ms, bool)
            or not isinstance(self.as_of_unix_ms, int)
            or self.as_of_unix_ms < 0
        ):
            raise ValueError("as_of_unix_ms must be a non-negative integer")
        for name in (
            "starting_cash_usd",
            "cash_balance_usd",
            "expected_cash_balance_usd",
            "realized_pnl_usd",
            "expected_realized_pnl_usd",
            "accumulated_costs_usd",
            "expected_accumulated_costs_usd",
        ):
            _require_finite(name, getattr(self, name))
        for name in (
            "unrealized_pnl_usd",
            "expected_unrealized_pnl_usd",
            "open_market_value_usd",
            "equity_usd",
            "net_pnl_usd",
            "expected_net_pnl_usd",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_finite(name, value)
        for name in (
            "journal_entry_count",
            "terminal_failure_count",
            "lifecycle_count",
            "open_position_count",
            "closed_position_count",
            "partial_reduction_count",
            "winning_closed_count",
            "losing_closed_count",
            "flat_closed_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, AccountingFinding) for finding in self.findings
        ):
            raise ValueError("findings must be a tuple of AccountingFinding values")
        if self.status is AccountingValidationStatus.RECONCILED and self.findings:
            raise ValueError("RECONCILED report cannot contain findings")
        if self.status is AccountingValidationStatus.INCOMPLETE:
            if not self.findings or any(
                finding.code is not AccountingFindingCode.UNMARKED_OPEN_POSITION
                for finding in self.findings
            ):
                raise ValueError("INCOMPLETE report requires only unmarked-position findings")
        if self.status is AccountingValidationStatus.INVALID and not self.findings:
            raise ValueError("INVALID report requires findings")


@dataclass(frozen=True, slots=True)
class PaperCheckpointRecord:
    run_id: str
    sequence: int
    checkpoint_schema_version: str
    state_as_of_unix_ms: int
    created_at_unix_ms: int
    payload_sha256: str
    state: PaperLoopState

    def __post_init__(self) -> None:
        _require_non_empty_string("run_id", self.run_id)
        _require_non_negative_int("sequence", self.sequence)
        if self.checkpoint_schema_version != _CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("unsupported checkpoint_schema_version")
        _require_non_negative_int("state_as_of_unix_ms", self.state_as_of_unix_ms)
        _require_non_negative_int("created_at_unix_ms", self.created_at_unix_ms)
        if self.created_at_unix_ms < self.state_as_of_unix_ms:
            raise ValueError("created_at_unix_ms must not precede state_as_of_unix_ms")
        if (
            not isinstance(self.payload_sha256, str)
            or len(self.payload_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.payload_sha256)
        ):
            raise ValueError("payload_sha256 must be a lowercase SHA-256 hex digest")
        if not isinstance(self.state, PaperLoopState):
            raise ValueError("state must be a PaperLoopState")
        if self.state.last_cycle_at_unix_ms != self.state_as_of_unix_ms:
            raise ValueError("state_as_of_unix_ms must equal state last-cycle time")


@dataclass(frozen=True, slots=True)
class RestartValidationReport:
    equivalent: bool
    expected_state_sha256: str
    restored_state_sha256: str
    expected_accounting: AccountingValidationReport
    restored_accounting: AccountingValidationReport
    differences: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.equivalent, bool):
            raise ValueError("equivalent must be a boolean")
        for name in ("expected_state_sha256", "restored_state_sha256"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        if not isinstance(self.expected_accounting, AccountingValidationReport):
            raise ValueError("expected_accounting must be an AccountingValidationReport")
        if not isinstance(self.restored_accounting, AccountingValidationReport):
            raise ValueError("restored_accounting must be an AccountingValidationReport")
        if not isinstance(self.differences, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.differences
        ):
            raise ValueError("differences must be a tuple of non-empty strings")
        if self.equivalent != (not self.differences):
            raise ValueError("equivalent must match whether differences are empty")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
