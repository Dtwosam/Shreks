from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


G6_ALERT_STATE_SCHEMA_VERSION = "g6-alert-state-v1"
_MAX_EVENT_ID_CHARS = 256
_MAX_TITLE_CHARS = 512
_MAX_LINE_CHARS = 1024
_MAX_EVENT_TEXT_CHARS = 3500
_ALLOWED_PROOF_DECISIONS = frozenset(
    {"SUFFICIENT", "INSUFFICIENT_EVIDENCE", "FAILED"}
)


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertCode(StrEnum):
    CORE_RUNTIME_STOPPED = "CORE_RUNTIME_STOPPED"
    SYSTEMD_HEALTH_UNAVAILABLE = "SYSTEMD_HEALTH_UNAVAILABLE"
    TELEMETRY_SOURCE_UNAVAILABLE = "TELEMETRY_SOURCE_UNAVAILABLE"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    PROVIDER_FAILURE_PERSISTENT = "PROVIDER_FAILURE_PERSISTENT"
    CHECKPOINT_UNAVAILABLE = "CHECKPOINT_UNAVAILABLE"
    PAPER_SOURCE_UNAVAILABLE = "PAPER_SOURCE_UNAVAILABLE"
    ACCOUNTING_NOT_RECONCILED = "ACCOUNTING_NOT_RECONCILED"
    GLOBAL_RISK_HALT_ACTIVE = "GLOBAL_RISK_HALT_ACTIVE"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    EXECUTION_DEGRADED = "EXECUTION_DEGRADED"
    PAPER_PROOF_SUFFICIENT = "PAPER_PROOF_SUFFICIENT"
    CHALLENGER_PROOF_FAILED = "CHALLENGER_PROOF_FAILED"
    ALERTING_STARTED = "ALERTING_STARTED"


@dataclass(frozen=True, slots=True)
class AlertEvent:
    event_id: str
    code: AlertCode
    severity: AlertSeverity
    observed_at_unix_ms: int
    title: str
    lines: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_bounded_text("event_id", self.event_id, _MAX_EVENT_ID_CHARS)
        if type(self.code) is not AlertCode:
            raise ValueError("code must be an exact AlertCode")
        if type(self.severity) is not AlertSeverity:
            raise ValueError("severity must be an exact AlertSeverity")
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_bounded_text("title", self.title, _MAX_TITLE_CHARS)
        if not isinstance(self.lines, tuple):
            raise ValueError("lines must be a tuple")
        total = len(self.title)
        for line in self.lines:
            _require_bounded_text("line", line, _MAX_LINE_CHARS)
            total += len(line)
        if total > _MAX_EVENT_TEXT_CHARS:
            raise ValueError("alert event text is too large")


@dataclass(frozen=True, slots=True)
class AlertState:
    schema_version: str
    initialized: bool
    highest_ledger_sequence: int
    last_proof_decision: str | None
    active_condition_keys: tuple[str, ...]
    pending_events: tuple[AlertEvent, ...]
    last_observed_at_unix_ms: int | None

    def __post_init__(self) -> None:
        if self.schema_version != G6_ALERT_STATE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {G6_ALERT_STATE_SCHEMA_VERSION}"
            )
        if type(self.initialized) is not bool:
            raise ValueError("initialized must be an exact bool")
        _require_non_negative_int(
            "highest_ledger_sequence", self.highest_ledger_sequence
        )
        if self.last_proof_decision is not None:
            if self.last_proof_decision not in _ALLOWED_PROOF_DECISIONS:
                raise ValueError("last_proof_decision is unsupported")
        if not isinstance(self.active_condition_keys, tuple):
            raise ValueError("active_condition_keys must be a tuple")
        for key in self.active_condition_keys:
            _require_bounded_text("active condition key", key, _MAX_EVENT_ID_CHARS)
        if self.active_condition_keys != tuple(sorted(self.active_condition_keys)):
            raise ValueError("active_condition_keys must be sorted")
        if len(self.active_condition_keys) != len(set(self.active_condition_keys)):
            raise ValueError("active_condition_keys must be unique")
        if not isinstance(self.pending_events, tuple) or not all(
            type(event) is AlertEvent for event in self.pending_events
        ):
            raise ValueError("pending_events must contain exact AlertEvent values")
        event_ids = tuple(event.event_id for event in self.pending_events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("pending event IDs must be unique")
        if self.last_observed_at_unix_ms is not None:
            _require_non_negative_int(
                "last_observed_at_unix_ms", self.last_observed_at_unix_ms
            )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bounded_text(name: str, value: object, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{name} must be bounded printable text")
