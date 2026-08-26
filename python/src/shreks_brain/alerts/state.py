from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import (
    AlertCode,
    AlertEvent,
    AlertSeverity,
    AlertState,
    G6_ALERT_STATE_SCHEMA_VERSION,
)


_STATE_KEYS = frozenset(
    {
        "schema_version",
        "initialized",
        "highest_ledger_sequence",
        "last_proof_decision",
        "active_condition_keys",
        "pending_events",
        "last_observed_at_unix_ms",
    }
)
_EVENT_KEYS = frozenset(
    {"event_id", "code", "severity", "observed_at_unix_ms", "title", "lines"}
)


class AlertStateError(ValueError):
    """Raised when G6 alert state cannot be trusted or persisted safely."""


def encode_alert_state(state: AlertState) -> bytes:
    if type(state) is not AlertState:
        raise AlertStateError("state must be an exact AlertState")
    document = {
        "schema_version": state.schema_version,
        "initialized": state.initialized,
        "highest_ledger_sequence": state.highest_ledger_sequence,
        "last_proof_decision": state.last_proof_decision,
        "active_condition_keys": list(state.active_condition_keys),
        "pending_events": [_event_document(event) for event in state.pending_events],
        "last_observed_at_unix_ms": state.last_observed_at_unix_ms,
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
        raise AlertStateError("alert state cannot be encoded") from error


def decode_alert_state(payload: bytes | str) -> AlertState:
    if type(payload) is bytes:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AlertStateError("alert state must be UTF-8") from error
    elif type(payload) is str:
        text = payload
    else:
        raise AlertStateError("alert state payload must be exact bytes or str")

    try:
        raw = json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise AlertStateError("alert state must be finite JSON") from error
    document = _exact_dict(raw, _STATE_KEYS, "alert state")
    try:
        state = AlertState(
            schema_version=_exact_string(document["schema_version"], "schema_version"),
            initialized=_exact_bool(document["initialized"], "initialized"),
            highest_ledger_sequence=_exact_non_negative_int(
                document["highest_ledger_sequence"], "highest_ledger_sequence"
            ),
            last_proof_decision=_optional_string(
                document["last_proof_decision"], "last_proof_decision"
            ),
            active_condition_keys=_string_tuple(
                document["active_condition_keys"], "active_condition_keys"
            ),
            pending_events=_event_tuple(document["pending_events"]),
            last_observed_at_unix_ms=_optional_non_negative_int(
                document["last_observed_at_unix_ms"], "last_observed_at_unix_ms"
            ),
        )
    except ValueError as error:
        raise AlertStateError("alert state values are invalid") from error
    if encode_alert_state(state).decode("utf-8") != text:
        raise AlertStateError("alert state must use canonical encoding")
    return state


def load_alert_state(path: Path) -> AlertState | None:
    output = _require_path(path)
    if output.is_symlink():
        raise AlertStateError("alert state path must not be a symlink")
    try:
        if not output.exists():
            return None
        if not output.is_file():
            raise AlertStateError("alert state path must be a regular file")
        payload = output.read_bytes()
    except AlertStateError:
        raise
    except OSError as error:
        raise AlertStateError("alert state cannot be read") from error
    try:
        return decode_alert_state(payload)
    except AlertStateError:
        raise


def write_alert_state(path: Path, state: AlertState) -> None:
    output = _require_path(path)
    if type(state) is not AlertState:
        raise AlertStateError("state must be an exact AlertState")
    if output.is_symlink():
        raise AlertStateError("alert state path must not be a symlink")
    parent = output.parent
    if not parent.exists() or not parent.is_dir():
        raise AlertStateError("alert state parent directory is unavailable")
    temporary = output.with_name(output.name + ".tmp")
    payload = encode_alert_state(state)

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
        os.replace(temporary, output)
        os.chmod(output, 0o600)
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
        raise AlertStateError("alert state write failed") from error


def _event_document(event: AlertEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "code": event.code.value,
        "severity": event.severity.value,
        "observed_at_unix_ms": event.observed_at_unix_ms,
        "title": event.title,
        "lines": list(event.lines),
    }


def _event_tuple(value: object) -> tuple[AlertEvent, ...]:
    if type(value) is not list:
        raise AlertStateError("pending_events must be an exact JSON array")
    return tuple(_decode_event(item) for item in value)


def _decode_event(value: object) -> AlertEvent:
    document = _exact_dict(value, _EVENT_KEYS, "alert event")
    try:
        return AlertEvent(
            event_id=_exact_string(document["event_id"], "event_id"),
            code=AlertCode(_exact_string(document["code"], "code")),
            severity=AlertSeverity(_exact_string(document["severity"], "severity")),
            observed_at_unix_ms=_exact_non_negative_int(
                document["observed_at_unix_ms"], "observed_at_unix_ms"
            ),
            title=_exact_string(document["title"], "title"),
            lines=_string_tuple(document["lines"], "lines"),
        )
    except (ValueError, TypeError) as error:
        raise AlertStateError("alert event values are invalid") from error


def _exact_dict(value: object, keys: frozenset[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise AlertStateError(f"{label} JSON keys must be exact")
    return value


def _exact_string(value: object, label: str) -> str:
    if type(value) is not str:
        raise AlertStateError(f"{label} must be an exact string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _exact_string(value, label)


def _exact_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise AlertStateError(f"{label} must be an exact bool")
    return value


def _exact_non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise AlertStateError(f"{label} must be a non-negative integer")
    return value


def _optional_non_negative_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _exact_non_negative_int(value, label)


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not list or not all(type(item) is str for item in value):
        raise AlertStateError(f"{label} must be an exact JSON string array")
    return tuple(value)


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite JSON constants are forbidden")


def _require_path(path: object) -> Path:
    if not isinstance(path, Path):
        raise AlertStateError("alert state path must be a Path")
    if not path.name:
        raise AlertStateError("alert state path must name a file")
    return path


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
