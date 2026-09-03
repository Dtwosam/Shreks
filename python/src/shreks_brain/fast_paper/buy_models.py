from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.paper import (
    PaperExecutionResult,
    PaperLedger,
    PaperLedgerUpdate,
    PaperQuoteState,
)
from shreks_brain.risk import FastEntryRiskAssessment

from .models import FastPaperAction, FastPaperActionAssessment


FAST_PAPER_BUY_VERSION = "fl7.2-v1"


class FastPaperBuyOutcome(StrEnum):
    DEFERRED = "DEFERRED"
    ABORTED_QUOTE_UNAVAILABLE = "ABORTED_QUOTE_UNAVAILABLE"
    ABORTED_QUOTE_TOO_LATE = "ABORTED_QUOTE_TOO_LATE"
    ABORTED_PRICE_ABOVE_MAXIMUM = "ABORTED_PRICE_ABOVE_MAXIMUM"
    ABORTED_INSUFFICIENT_CAPACITY = "ABORTED_INSUFFICIENT_CAPACITY"
    RISK_REJECTED = "RISK_REJECTED"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    ABORTED_TOTAL_COST_ABOVE_MAXIMUM = "ABORTED_TOTAL_COST_ABOVE_MAXIMUM"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    FILLED = "FILLED"
    LEDGER_REJECTED = "LEDGER_REJECTED"


class FastPaperBuyError(ValueError):
    """Raised when FL7.2 BUY evidence is contradictory or malformed."""


@dataclass(frozen=True, slots=True)
class FastPaperBuyApproval:
    version: str
    assessment: FastPaperActionAssessment
    mint: str
    quote_mint: str
    state_version: str
    intended_base_quantity: float
    decision_executable_entry_price_quote: float
    maximum_acceptable_entry_price_quote: float
    expected_entry_variable_cost_bps: int
    expected_entry_fixed_cost_quote: float

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_BUY_VERSION:
            raise ValueError("unsupported Fast PAPER BUY version")
        if not isinstance(self.assessment, FastPaperActionAssessment):
            raise ValueError("assessment must be FastPaperActionAssessment")
        if self.assessment.action is not FastPaperAction.BUY:
            raise ValueError("Fast PAPER BUY approval requires BUY assessment")
        for name in ("mint", "quote_mint", "state_version"):
            _require_non_empty_string(name, getattr(self, name))
        _require_positive_finite("intended_base_quantity", self.intended_base_quantity)
        _require_positive_finite(
            "decision_executable_entry_price_quote",
            self.decision_executable_entry_price_quote,
        )
        _require_positive_finite(
            "maximum_acceptable_entry_price_quote",
            self.maximum_acceptable_entry_price_quote,
        )
        if self.decision_executable_entry_price_quote > self.maximum_acceptable_entry_price_quote:
            raise ValueError("BUY approval decision price cannot exceed maximum entry price")
        if (
            isinstance(self.expected_entry_variable_cost_bps, bool)
            or not isinstance(self.expected_entry_variable_cost_bps, int)
            or not 0 <= self.expected_entry_variable_cost_bps <= 40_000
        ):
            raise ValueError("expected_entry_variable_cost_bps must be within [0, 40000]")
        _require_non_negative_finite(
            "expected_entry_fixed_cost_quote",
            self.expected_entry_fixed_cost_quote,
        )

    @property
    def decision_at_unix_ms(self) -> int:
        return self.assessment.as_of_unix_ms

    @property
    def maximum_entry_total_quote(self) -> float:
        rate = 1.0 + self.expected_entry_variable_cost_bps / 10_000.0
        value = (
            self.intended_base_quantity
            * self.maximum_acceptable_entry_price_quote
            * rate
            + self.expected_entry_fixed_cost_quote
        )
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError("maximum entry total quote is invalid")
        return value


@dataclass(frozen=True, slots=True)
class FastPaperBuyQuote:
    provider: str
    mint: str
    quote_mint: str
    observed_at_unix_ms: int
    state: PaperQuoteState
    reference_price_quote: float | None
    execution_price_quote: float | None
    quoted_base_quantity: float | None
    available_base_quantity: float | None
    quote_to_usd_rate: float

    def __post_init__(self) -> None:
        for name in ("provider", "mint", "quote_mint"):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        if not isinstance(self.state, PaperQuoteState):
            raise ValueError("state must be PaperQuoteState")
        for name in (
            "reference_price_quote",
            "execution_price_quote",
            "quoted_base_quantity",
            "available_base_quantity",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_positive_finite(name, value)
        _require_positive_finite("quote_to_usd_rate", self.quote_to_usd_rate)

        if self.state in (
            PaperQuoteState.EXECUTABLE,
            PaperQuoteState.FAILED_AFTER_SUBMISSION,
        ):
            missing = [
                name
                for name in (
                    "reference_price_quote",
                    "execution_price_quote",
                    "quoted_base_quantity",
                    "available_base_quantity",
                )
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(
                    "executable/submitted Fast PAPER quote requires complete price and capacity evidence"
                )


@dataclass(frozen=True, slots=True)
class FastPaperBuyResult:
    version: str
    outcome: FastPaperBuyOutcome
    source_event_id: str
    mint: str
    decision_at_unix_ms: int
    evaluated_at_unix_ms: int
    intended_base_quantity: float
    maximum_entry_total_quote: float
    actual_entry_total_quote: float | None
    risk_assessment: FastEntryRiskAssessment | None
    execution: PaperExecutionResult | None
    ledger_update: PaperLedgerUpdate | None
    next_ledger: PaperLedger

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_BUY_VERSION:
            raise ValueError("unsupported Fast PAPER BUY result version")
        if not isinstance(self.outcome, FastPaperBuyOutcome):
            raise ValueError("outcome must be FastPaperBuyOutcome")
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("decision_at_unix_ms", self.decision_at_unix_ms)
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        if self.evaluated_at_unix_ms < self.decision_at_unix_ms:
            raise ValueError("BUY result evaluation cannot precede decision")
        _require_positive_finite("intended_base_quantity", self.intended_base_quantity)
        _require_positive_finite("maximum_entry_total_quote", self.maximum_entry_total_quote)
        if self.actual_entry_total_quote is not None:
            _require_positive_finite("actual_entry_total_quote", self.actual_entry_total_quote)
        if self.risk_assessment is not None and not isinstance(
            self.risk_assessment, FastEntryRiskAssessment
        ):
            raise ValueError("risk_assessment must be FastEntryRiskAssessment or None")
        if self.execution is not None and not isinstance(self.execution, PaperExecutionResult):
            raise ValueError("execution must be PaperExecutionResult or None")
        if self.ledger_update is not None and not isinstance(self.ledger_update, PaperLedgerUpdate):
            raise ValueError("ledger_update must be PaperLedgerUpdate or None")
        if not isinstance(self.next_ledger, PaperLedger):
            raise ValueError("next_ledger must be PaperLedger")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
    ):
        raise ValueError(f"{name} must be finite and strictly positive")


def _require_non_negative_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")
