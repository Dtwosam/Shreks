from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


G7_OPERATOR_RISK_CONTROL_SCHEMA_VERSION = "g7-operator-risk-control-v1"
_MAX_REASON_CHARS = 512


class OperatorRiskControlCommand(StrEnum):
    INITIALIZE = "INITIALIZE"
    HALT_NEW_ENTRIES = "HALT_NEW_ENTRIES"
    EMERGENCY_KILL_SWITCH = "EMERGENCY_KILL_SWITCH"
    CLEAR_ENTRY_HALT = "CLEAR_ENTRY_HALT"
    RESET_KILL_SWITCH = "RESET_KILL_SWITCH"


class OperatorRiskControlSource(StrEnum):
    HOST_CLI = "HOST_CLI"
    DASHBOARD = "DASHBOARD"


@dataclass(frozen=True, slots=True)
class OperatorRiskControlState:
    schema_version: str
    revision: int
    halt_new_entries: bool
    kill_switch_active: bool
    updated_at_unix_ms: int
    last_command: OperatorRiskControlCommand
    last_source: OperatorRiskControlSource
    last_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != G7_OPERATOR_RISK_CONTROL_SCHEMA_VERSION:
            raise ValueError("unsupported operator risk-control schema version")
        _require_non_negative_int("revision", self.revision)
        _require_bool("halt_new_entries", self.halt_new_entries)
        _require_bool("kill_switch_active", self.kill_switch_active)
        if self.kill_switch_active and not self.halt_new_entries:
            raise ValueError("kill switch requires entry halt")
        _require_non_negative_int("updated_at_unix_ms", self.updated_at_unix_ms)
        if type(self.last_command) is not OperatorRiskControlCommand:
            raise ValueError("last_command must be an exact OperatorRiskControlCommand")
        if type(self.last_source) is not OperatorRiskControlSource:
            raise ValueError("last_source must be an exact OperatorRiskControlSource")
        _require_reason(self.last_reason)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be an exact bool")


def _require_reason(value: object) -> None:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > _MAX_REASON_CHARS
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("last_reason must be bounded printable text")
