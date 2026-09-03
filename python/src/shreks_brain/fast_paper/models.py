from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


FAST_PAPER_EVENT_LOOP_VERSION = "fl7.1-v1"


class FastPaperAction(StrEnum):
    BUY = "BUY"
    SKIP = "SKIP"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"


class FastPaperEventOutcome(StrEnum):
    ASSESSED = "ASSESSED"
    IGNORED_NON_MATERIAL = "IGNORED_NON_MATERIAL"
    REPLAYED = "REPLAYED"


class FastPaperLoopError(ValueError):
    """Base error for deterministic FL7.1 event application failures."""


class FastPaperLoopConflictError(FastPaperLoopError):
    """Raised when one stable event identity is replayed with different content."""


class FastPaperLoopOrderError(FastPaperLoopError):
    """Raised when a new per-market update regresses canonical order or time."""


class FastPaperAssessmentMismatchError(FastPaperLoopError):
    """Raised when a returned assessment does not belong to the triggering update."""


@dataclass(frozen=True, slots=True)
class FastPaperMaterialUpdate:
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    state_version: str
    is_material: bool
    material_reason: str | None

    def __post_init__(self) -> None:
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_non_empty_string("market_key", self.market_key)
        _require_non_negative_int("source_sequence", self.source_sequence)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_empty_string("state_version", self.state_version)
        _require_bool("is_material", self.is_material)
        if self.is_material:
            if self.material_reason is None:
                raise ValueError("material update requires material_reason")
            _require_non_empty_string("material_reason", self.material_reason)
        elif self.material_reason is not None:
            raise ValueError("non-material update must not carry material_reason")


@dataclass(frozen=True, slots=True)
class FastPaperActionAssessment:
    version: str
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    strategy_family: str
    strategy_version: str
    action: FastPaperAction
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_non_empty_string("market_key", self.market_key)
        _require_non_negative_int("source_sequence", self.source_sequence)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_empty_string("strategy_family", self.strategy_family)
        _require_non_empty_string("strategy_version", self.strategy_version)
        if not isinstance(self.action, FastPaperAction):
            raise ValueError("action must be a FastPaperAction")
        if not isinstance(self.reasons, tuple) or not self.reasons:
            raise ValueError("reasons must be a non-empty tuple")
        for reason in self.reasons:
            _require_non_empty_string("reason", reason)


@dataclass(frozen=True, slots=True)
class FastPaperMarketCursor:
    market_key: str
    last_source_sequence: int
    last_as_of_unix_ms: int

    def __post_init__(self) -> None:
        _require_non_empty_string("market_key", self.market_key)
        _require_non_negative_int("last_source_sequence", self.last_source_sequence)
        _require_non_negative_int("last_as_of_unix_ms", self.last_as_of_unix_ms)


@dataclass(frozen=True, slots=True)
class FastPaperEventRecord:
    source_event_id: str
    update_fingerprint: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    is_material: bool
    assessment: FastPaperActionAssessment | None

    def __post_init__(self) -> None:
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_sha256_hex("update_fingerprint", self.update_fingerprint)
        _require_non_empty_string("market_key", self.market_key)
        _require_non_negative_int("source_sequence", self.source_sequence)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_bool("is_material", self.is_material)
        if self.is_material:
            if not isinstance(self.assessment, FastPaperActionAssessment):
                raise ValueError("material record requires FastPaperActionAssessment")
        elif self.assessment is not None:
            raise ValueError("non-material record must not carry assessment")


@dataclass(frozen=True, slots=True)
class FastPaperLoopState:
    version: str
    market_cursors: tuple[FastPaperMarketCursor, ...]
    records: tuple[FastPaperEventRecord, ...]

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_EVENT_LOOP_VERSION:
            raise ValueError("unsupported fast PAPER event-loop version")
        if not isinstance(self.market_cursors, tuple):
            raise ValueError("market_cursors must be a tuple")
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        for cursor in self.market_cursors:
            if not isinstance(cursor, FastPaperMarketCursor):
                raise ValueError("market_cursors must contain FastPaperMarketCursor values")
        for record in self.records:
            if not isinstance(record, FastPaperEventRecord):
                raise ValueError("records must contain FastPaperEventRecord values")

        cursor_keys = tuple(cursor.market_key for cursor in self.market_cursors)
        if len(cursor_keys) != len(set(cursor_keys)):
            raise ValueError("market cursor keys must be unique")
        record_ids = tuple(record.source_event_id for record in self.records)
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("event record IDs must be unique")

        cursors_by_market = {cursor.market_key: cursor for cursor in self.market_cursors}
        latest_by_market: dict[str, tuple[int, int]] = {}
        for record in self.records:
            previous = latest_by_market.get(record.market_key)
            point = (record.source_sequence, record.as_of_unix_ms)
            if previous is None or record.source_sequence > previous[0]:
                latest_by_market[record.market_key] = point

        for market_key, (sequence, as_of) in latest_by_market.items():
            cursor = cursors_by_market.get(market_key)
            if cursor is None:
                raise ValueError("recorded market requires a matching cursor")
            if cursor.last_source_sequence < sequence:
                raise ValueError("market cursor cannot precede latest record sequence")
            if cursor.last_as_of_unix_ms < as_of:
                raise ValueError("market cursor cannot precede latest record timestamp")


@dataclass(frozen=True, slots=True)
class FastPaperEventResult:
    outcome: FastPaperEventOutcome
    source_event_id: str
    assessment: FastPaperActionAssessment | None
    next_state: FastPaperLoopState

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, FastPaperEventOutcome):
            raise ValueError("outcome must be a FastPaperEventOutcome")
        _require_non_empty_string("source_event_id", self.source_event_id)
        if self.assessment is not None and not isinstance(
            self.assessment, FastPaperActionAssessment
        ):
            raise ValueError("assessment must be FastPaperActionAssessment or None")
        if not isinstance(self.next_state, FastPaperLoopState):
            raise ValueError("next_state must be FastPaperLoopState")
        if self.outcome is FastPaperEventOutcome.ASSESSED and self.assessment is None:
            raise ValueError("ASSESSED result requires assessment")
        if self.outcome is FastPaperEventOutcome.IGNORED_NON_MATERIAL and self.assessment is not None:
            raise ValueError("IGNORED_NON_MATERIAL result cannot carry assessment")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a bool")


def _require_sha256_hex(name: str, value: object) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a 64-character SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be hexadecimal") from exc
