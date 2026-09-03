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
from shreks_brain.risk import TradeIntent

from .models import FastPaperAction, FastPaperActionAssessment


FAST_PAPER_POSITION_ACTION_VERSION = "fl7.4-v1"
FAST_PAPER_EXIT_RISK_POLICY_SENTINEL = "not-applicable:fast-lane-exit"


class FastPaperPositionActionError(ValueError):
    """Raised when FL7.4 position-action evidence is contradictory or malformed."""


class FastPaperPositionOutcome(StrEnum):
    HOLD = "HOLD"
    HOLD_MARKED = "HOLD_MARKED"
    DEFERRED = "DEFERRED"
    ABORTED_QUOTE_UNAVAILABLE = "ABORTED_QUOTE_UNAVAILABLE"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    REDUCED = "REDUCED"
    SOLD = "SOLD"
    LEDGER_REJECTED = "LEDGER_REJECTED"


@dataclass(frozen=True, slots=True)
class FastPaperPositionActionPolicy:
    version: str
    max_slippage_bps: int

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_bps("max_slippage_bps", self.max_slippage_bps)


@dataclass(frozen=True, slots=True)
class FastPaperPositionActionApproval:
    version: str
    assessment: FastPaperActionAssessment
    position_id: str
    mint: str
    quote_mint: str
    state_version: str
    target_base_quantity: float | None

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_POSITION_ACTION_VERSION:
            raise ValueError("unsupported Fast PAPER position-action version")
        if not isinstance(self.assessment, FastPaperActionAssessment):
            raise ValueError("assessment must be FastPaperActionAssessment")
        if self.assessment.action not in (
            FastPaperAction.HOLD,
            FastPaperAction.REDUCE,
            FastPaperAction.SELL,
        ):
            raise ValueError("Fast PAPER position action must be HOLD, REDUCE, or SELL")
        for name in ("position_id", "mint", "quote_mint", "state_version"):
            _require_non_empty_string(name, getattr(self, name))

        if self.assessment.action is FastPaperAction.HOLD:
            if self.target_base_quantity is not None:
                raise ValueError("HOLD must not carry target_base_quantity")
            return
        if self.target_base_quantity is None:
            raise ValueError("target_base_quantity is required for REDUCE/SELL")
        _require_positive_finite("target_base_quantity", self.target_base_quantity)


@dataclass(frozen=True, slots=True)
class FastPaperPositionQuote:
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
            missing = tuple(
                name
                for name in (
                    "reference_price_quote",
                    "execution_price_quote",
                    "quoted_base_quantity",
                    "available_base_quantity",
                )
                if getattr(self, name) is None
            )
            if missing:
                raise ValueError(
                    "executable/submitted Fast PAPER position quote requires complete price and capacity evidence"
                )


@dataclass(frozen=True, slots=True)
class FastPaperPositionActionState:
    version: str
    position_id: str
    pending_exit: FastPaperPositionActionApproval | None
    last_assessment_at_unix_ms: int

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_POSITION_ACTION_VERSION:
            raise ValueError("unsupported Fast PAPER position-action state version")
        _require_non_empty_string("position_id", self.position_id)
        _require_non_negative_int(
            "last_assessment_at_unix_ms", self.last_assessment_at_unix_ms
        )
        if self.pending_exit is None:
            return
        if not isinstance(self.pending_exit, FastPaperPositionActionApproval):
            raise ValueError("pending_exit must be FastPaperPositionActionApproval or None")
        if self.pending_exit.position_id != self.position_id:
            raise ValueError("pending_exit position_id must match state")
        if self.pending_exit.assessment.action not in (
            FastPaperAction.REDUCE,
            FastPaperAction.SELL,
        ):
            raise ValueError("pending_exit must be REDUCE or SELL")
        if self.pending_exit.assessment.as_of_unix_ms > self.last_assessment_at_unix_ms:
            raise ValueError("pending_exit cannot be later than state assessment clock")


@dataclass(frozen=True, slots=True)
class FastPaperPositionActionResult:
    version: str
    outcome: FastPaperPositionOutcome
    position_id: str
    mint: str
    evaluated_at_unix_ms: int
    applied_assessment: FastPaperActionAssessment
    active_exit: FastPaperPositionActionApproval | None
    intent: TradeIntent | None
    execution: PaperExecutionResult | None
    execution_ledger_update: PaperLedgerUpdate | None
    mark_ledger_update: PaperLedgerUpdate | None
    next_ledger: PaperLedger
    next_state: FastPaperPositionActionState

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_POSITION_ACTION_VERSION:
            raise ValueError("unsupported Fast PAPER position-action result version")
        if not isinstance(self.outcome, FastPaperPositionOutcome):
            raise ValueError("outcome must be FastPaperPositionOutcome")
        _require_non_empty_string("position_id", self.position_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        if not isinstance(self.applied_assessment, FastPaperActionAssessment):
            raise ValueError("applied_assessment must be FastPaperActionAssessment")
        if self.active_exit is not None and not isinstance(
            self.active_exit, FastPaperPositionActionApproval
        ):
            raise ValueError("active_exit must be FastPaperPositionActionApproval or None")
        if self.intent is not None and not isinstance(self.intent, TradeIntent):
            raise ValueError("intent must be TradeIntent or None")
        if self.execution is not None and not isinstance(self.execution, PaperExecutionResult):
            raise ValueError("execution must be PaperExecutionResult or None")
        for name in ("execution_ledger_update", "mark_ledger_update"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, PaperLedgerUpdate):
                raise ValueError(f"{name} must be PaperLedgerUpdate or None")
        if not isinstance(self.next_ledger, PaperLedger):
            raise ValueError("next_ledger must be PaperLedger")
        if not isinstance(self.next_state, FastPaperPositionActionState):
            raise ValueError("next_state must be FastPaperPositionActionState")
        if self.next_state.position_id != self.position_id:
            raise ValueError("next_state position_id must match result")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bps(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError(f"{name} must be an integer within [0, 10000]")


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
    ):
        raise ValueError(f"{name} must be finite and strictly positive")
