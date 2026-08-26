from __future__ import annotations

from dataclasses import replace
import fcntl
import json
import os
from pathlib import Path
from typing import Any

from .models import (
    G7_OPERATOR_RISK_CONTROL_SCHEMA_VERSION,
    OperatorRiskControlCommand,
    OperatorRiskControlSource,
    OperatorRiskControlState,
)


_STATE_KEYS = frozenset(
    {
        "schema_version",
        "revision",
        "halt_new_entries",
        "kill_switch_active",
        "updated_at_unix_ms",
        "last_command",
        "last_source",
        "last_reason",
    }
)
_MIN_HOST_RESET_REASON_CHARS = 8


class RiskControlStateError(ValueError):
    """Raised when durable operator risk-control state cannot be trusted."""


class RiskControlCommandError(ValueError):
    """Raised when an operator risk-control command is unsafe or malformed."""


class RiskControlConflictError(RiskControlCommandError):
    """Raised when expected revision does not match durable state."""


def encode_operator_risk_control_state(state: OperatorRiskControlState) -> bytes:
    if type(state) is not OperatorRiskControlState:
        raise RiskControlStateError("state must be an exact OperatorRiskControlState")
    document = {
        "schema_version": state.schema_version,
        "revision": state.revision,
        "halt_new_entries": state.halt_new_entries,
        "kill_switch_active": state.kill_switch_active,
        "updated_at_unix_ms": state.updated_at_unix_ms,
        "last_command": state.last_command.value,
        "last_source": state.last_source.value,
        "last_reason": state.last_reason,
    }
    try:
        return (
            json.dumps(
                document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RiskControlStateError("operator risk-control state cannot be encoded") from error


def decode_operator_risk_control_state(payload: bytes | str) -> OperatorRiskControlState:
    if type(payload) is bytes:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RiskControlStateError("operator risk-control state must be UTF-8") from error
    elif type(payload) is str:
        text = payload
    else:
        raise RiskControlStateError("operator risk-control payload must be exact bytes or str")

    try:
        raw = json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise RiskControlStateError("operator risk-control state must be finite JSON") from error
    document = _exact_dict(raw)
    try:
        state = OperatorRiskControlState(
            schema_version=_exact_string(document["schema_version"], "schema_version"),
            revision=_non_negative_int(document["revision"], "revision"),
            halt_new_entries=_exact_bool(document["halt_new_entries"], "halt_new_entries"),
            kill_switch_active=_exact_bool(document["kill_switch_active"], "kill_switch_active"),
            updated_at_unix_ms=_non_negative_int(
                document["updated_at_unix_ms"], "updated_at_unix_ms"
            ),
            last_command=OperatorRiskControlCommand(
                _exact_string(document["last_command"], "last_command")
            ),
            last_source=OperatorRiskControlSource(
                _exact_string(document["last_source"], "last_source")
            ),
            last_reason=_exact_string(document["last_reason"], "last_reason"),
        )
    except (TypeError, ValueError) as error:
        raise RiskControlStateError("operator risk-control state values are invalid") from error

    if encode_operator_risk_control_state(state).decode("utf-8") != text:
        raise RiskControlStateError("operator risk-control state must use canonical encoding")
    return state


def load_operator_risk_control_state(path: Path) -> OperatorRiskControlState:
    output = _require_path(path)
    if output.is_symlink():
        raise RiskControlStateError("operator risk-control state path must not be a symlink")
    try:
        if not output.exists():
            raise RiskControlStateError("operator risk-control state is unavailable")
        if not output.is_file():
            raise RiskControlStateError("operator risk-control state path must be a regular file")
        payload = output.read_bytes()
    except RiskControlStateError:
        raise
    except OSError as error:
        raise RiskControlStateError("operator risk-control state is unavailable") from error
    return decode_operator_risk_control_state(payload)


def write_operator_risk_control_state(
    path: Path,
    state: OperatorRiskControlState,
) -> None:
    output = _require_path(path)
    if type(state) is not OperatorRiskControlState:
        raise RiskControlStateError("state must be an exact OperatorRiskControlState")
    _atomic_write(output, encode_operator_risk_control_state(state))


def initialize_operator_risk_control_state(
    path: Path,
    *,
    observed_at_unix_ms: int,
) -> OperatorRiskControlState:
    output = _require_path(path)
    observed_at = _command_timestamp(observed_at_unix_ms)
    with _exclusive_lock(output):
        if output.is_symlink():
            raise RiskControlStateError("operator risk-control state path must not be a symlink")
        if output.exists():
            raise RiskControlStateError("operator risk-control state already exists")
        state = OperatorRiskControlState(
            schema_version=G7_OPERATOR_RISK_CONTROL_SCHEMA_VERSION,
            revision=0,
            halt_new_entries=False,
            kill_switch_active=False,
            updated_at_unix_ms=observed_at,
            last_command=OperatorRiskControlCommand.INITIALIZE,
            last_source=OperatorRiskControlSource.HOST_CLI,
            last_reason="initialized operator risk control",
        )
        _atomic_write(output, encode_operator_risk_control_state(state))
        return state


def apply_operator_risk_control_command(
    path: Path,
    command: OperatorRiskControlCommand,
    *,
    expected_revision: int,
    observed_at_unix_ms: int,
    source: OperatorRiskControlSource,
    reason: str,
) -> OperatorRiskControlState:
    output = _require_path(path)
    if type(command) is not OperatorRiskControlCommand:
        raise RiskControlCommandError("command must be an exact OperatorRiskControlCommand")
    if command is OperatorRiskControlCommand.INITIALIZE:
        raise RiskControlCommandError("INITIALIZE must use the initialization authority")
    if type(source) is not OperatorRiskControlSource:
        raise RiskControlCommandError("source must be an exact OperatorRiskControlSource")
    expected = _expected_revision(expected_revision)
    observed_at = _command_timestamp(observed_at_unix_ms)
    command_reason = _command_reason(reason, command=command, source=source)
    if source is OperatorRiskControlSource.DASHBOARD and command in (
        OperatorRiskControlCommand.CLEAR_ENTRY_HALT,
        OperatorRiskControlCommand.RESET_KILL_SWITCH,
    ):
        raise RiskControlCommandError("clear/reset commands are host-only")

    with _exclusive_lock(output):
        state = load_operator_risk_control_state(output)
        if state.revision != expected:
            raise RiskControlConflictError("operator risk-control revision conflict")
        if observed_at < state.updated_at_unix_ms:
            raise RiskControlCommandError("command timestamp precedes current state")

        if command is OperatorRiskControlCommand.HALT_NEW_ENTRIES:
            next_state = replace(
                state,
                revision=state.revision + 1,
                halt_new_entries=True,
                updated_at_unix_ms=observed_at,
                last_command=command,
                last_source=source,
                last_reason=command_reason,
            )
        elif command is OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH:
            next_state = replace(
                state,
                revision=state.revision + 1,
                halt_new_entries=True,
                kill_switch_active=True,
                updated_at_unix_ms=observed_at,
                last_command=command,
                last_source=source,
                last_reason=command_reason,
            )
        elif command is OperatorRiskControlCommand.RESET_KILL_SWITCH:
            if source is not OperatorRiskControlSource.HOST_CLI:
                raise RiskControlCommandError("reset kill switch is host-only")
            if not state.kill_switch_active:
                raise RiskControlCommandError("kill switch is not active")
            next_state = replace(
                state,
                revision=state.revision + 1,
                halt_new_entries=True,
                kill_switch_active=False,
                updated_at_unix_ms=observed_at,
                last_command=command,
                last_source=source,
                last_reason=command_reason,
            )
        elif command is OperatorRiskControlCommand.CLEAR_ENTRY_HALT:
            if source is not OperatorRiskControlSource.HOST_CLI:
                raise RiskControlCommandError("clear entry halt is host-only")
            if state.kill_switch_active:
                raise RiskControlCommandError("kill switch must be reset before clearing entry halt")
            if not state.halt_new_entries:
                raise RiskControlCommandError("entry halt is not active")
            next_state = replace(
                state,
                revision=state.revision + 1,
                halt_new_entries=False,
                updated_at_unix_ms=observed_at,
                last_command=command,
                last_source=source,
                last_reason=command_reason,
            )
        else:
            raise RiskControlCommandError("unsupported operator risk-control command")

        _atomic_write(output, encode_operator_risk_control_state(next_state))
        return next_state


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise RiskControlStateError("operator risk-control state path must not be a symlink")
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise RiskControlStateError("operator risk-control parent directory is unavailable")
    temporary = path.with_name(path.name + ".tmp")
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(parent)
    except (OSError, TypeError, ValueError) as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RiskControlStateError("operator risk-control state write failed") from error


class _exclusive_lock:
    def __init__(self, state_path: Path) -> None:
        self._path = state_path.with_name(state_path.name + ".lock")
        self._descriptor: int | None = None

    def __enter__(self) -> None:
        if self._path.is_symlink():
            raise RiskControlStateError("operator risk-control lock path must not be a symlink")
        parent = self._path.parent
        if not parent.exists() or not parent.is_dir():
            raise RiskControlStateError("operator risk-control parent directory is unavailable")
        try:
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self._path, flags, 0o600)
            os.chmod(self._path, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            self._descriptor = descriptor
        except OSError as error:
            raise RiskControlStateError("operator risk-control lock is unavailable") from error
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        descriptor = self._descriptor
        self._descriptor = None
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        return False


def _require_path(path: object) -> Path:
    if not isinstance(path, Path) or not path.name:
        raise RiskControlStateError("operator risk-control path must name a file")
    return path


def _exact_dict(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _STATE_KEYS:
        raise RiskControlStateError("operator risk-control JSON keys must be exact")
    return value


def _exact_string(value: object, label: str) -> str:
    if type(value) is not str:
        raise RiskControlStateError(f"{label} must be an exact string")
    return value


def _exact_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise RiskControlStateError(f"{label} must be an exact bool")
    return value


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise RiskControlStateError(f"{label} must be a non-negative integer")
    return value


def _expected_revision(value: object) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise RiskControlCommandError("expected revision must be a non-negative integer")
    return value


def _command_timestamp(value: object) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise RiskControlCommandError("command timestamp must be a non-negative integer")
    return value


def _command_reason(
    value: object,
    *,
    command: OperatorRiskControlCommand,
    source: OperatorRiskControlSource,
) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > 512
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RiskControlCommandError("command reason must be bounded printable text")
    if (
        source is OperatorRiskControlSource.HOST_CLI
        and command
        in (
            OperatorRiskControlCommand.CLEAR_ENTRY_HALT,
            OperatorRiskControlCommand.RESET_KILL_SWITCH,
        )
        and len(value) < _MIN_HOST_RESET_REASON_CHARS
    ):
        raise RiskControlCommandError("host reset reason is too short")
    return value


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite JSON constants are forbidden")


def _fsync_directory(path: Path) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
