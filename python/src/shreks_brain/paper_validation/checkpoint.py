from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any

from shreks_brain.decision import DecisionAction
from shreks_brain.exits import (
    ExitAssessment,
    ExitFinding,
    ExitPolicy,
    ExitReasonCode,
    ExitState,
    TakeProfitLevel,
)
from shreks_brain.paper import (
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerEntry,
    PaperLedgerReasonCode,
    PaperPosition,
    PaperPositionState,
)
from shreks_brain.paper_loop import (
    ManagedPaperPosition,
    PaperLoopPolicy,
    PaperLoopState,
    PendingPaperEntry,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode

from .accounting import validate_paper_accounting
from .models import (
    AccountingValidationStatus,
    PaperCheckpointRecord,
    RestartValidationReport,
)


_CHECKPOINT_SCHEMA_VERSION = "c6-paper-state-v1"
_TABLE_NAME = "paper_loop_checkpoints"


class PaperCheckpointError(ValueError):
    """Raised when a paper checkpoint cannot be safely encoded, stored, or restored."""


_DATACLASS_TYPES = (
    PaperLedger,
    PaperLedgerEntry,
    PaperPosition,
    PaperFillPolicy,
    ExitPolicy,
    TakeProfitLevel,
    ExitState,
    ExitFinding,
    ExitAssessment,
    ManagedPaperPosition,
    PendingPaperEntry,
    PaperLoopPolicy,
    PaperLoopState,
    TradeIntent,
)
_DATACLASS_BY_NAME = {item.__name__: item for item in _DATACLASS_TYPES}
_DATACLASS_NAME_BY_TYPE = {item: item.__name__ for item in _DATACLASS_TYPES}

_ENUM_TYPES = (
    PaperPositionState,
    PaperLedgerReasonCode,
    PaperExecutionState,
    PaperExecutionReasonCode,
    TradeSide,
    RuntimeMode,
    DecisionAction,
    ExitReasonCode,
)
_ENUM_BY_NAME = {item.__name__: item for item in _ENUM_TYPES}
_ENUM_NAME_BY_TYPE = {item: item.__name__ for item in _ENUM_TYPES}


def encode_paper_checkpoint(
    run_id: str,
    sequence: int,
    state: PaperLoopState,
    created_at_unix_ms: int,
) -> bytes:
    _require_non_empty_string("run_id", run_id)
    _require_non_negative_int("sequence", sequence)
    if not isinstance(state, PaperLoopState):
        raise PaperCheckpointError("state must be a PaperLoopState")
    _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
    if created_at_unix_ms < state.last_cycle_at_unix_ms:
        raise PaperCheckpointError(
            "created_at_unix_ms must not precede paper-loop state"
        )

    envelope = {
        "checkpoint_schema_version": _CHECKPOINT_SCHEMA_VERSION,
        "run_id": run_id,
        "sequence": sequence,
        "created_at_unix_ms": created_at_unix_ms,
        "state_as_of_unix_ms": state.last_cycle_at_unix_ms,
        "state": _encode_value(state),
    }
    return _canonical_json(envelope)


def decode_paper_checkpoint(
    payload: bytes | str,
    *,
    expected_sha256: str | None = None,
) -> PaperCheckpointRecord:
    raw = _payload_bytes(payload)
    payload_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        _require_sha256("expected_sha256", expected_sha256)
        if payload_sha256 != expected_sha256:
            raise PaperCheckpointError("checkpoint checksum mismatch")

    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaperCheckpointError("checkpoint payload is not valid UTF-8 JSON") from error
    if not isinstance(envelope, dict):
        raise PaperCheckpointError("checkpoint envelope must be an object")
    expected_keys = {
        "checkpoint_schema_version",
        "run_id",
        "sequence",
        "created_at_unix_ms",
        "state_as_of_unix_ms",
        "state",
    }
    if set(envelope) != expected_keys:
        raise PaperCheckpointError("checkpoint envelope is malformed")
    if envelope["checkpoint_schema_version"] != _CHECKPOINT_SCHEMA_VERSION:
        raise PaperCheckpointError("unsupported checkpoint schema version")

    run_id = envelope["run_id"]
    sequence = envelope["sequence"]
    created_at_unix_ms = envelope["created_at_unix_ms"]
    state_as_of_unix_ms = envelope["state_as_of_unix_ms"]
    _require_non_empty_string("run_id", run_id)
    _require_non_negative_int("sequence", sequence)
    _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
    _require_non_negative_int("state_as_of_unix_ms", state_as_of_unix_ms)

    state = _decode_value(envelope["state"])
    if not isinstance(state, PaperLoopState):
        raise PaperCheckpointError("checkpoint state must decode to PaperLoopState")
    if state.last_cycle_at_unix_ms != state_as_of_unix_ms:
        raise PaperCheckpointError("checkpoint state timestamp metadata mismatch")
    if created_at_unix_ms < state_as_of_unix_ms:
        raise PaperCheckpointError("checkpoint creation time precedes state")

    canonical = encode_paper_checkpoint(
        run_id,
        sequence,
        state,
        created_at_unix_ms,
    )
    if canonical != raw:
        raise PaperCheckpointError("checkpoint payload is not canonical")

    try:
        return PaperCheckpointRecord(
            run_id=run_id,
            sequence=sequence,
            checkpoint_schema_version=_CHECKPOINT_SCHEMA_VERSION,
            state_as_of_unix_ms=state_as_of_unix_ms,
            created_at_unix_ms=created_at_unix_ms,
            payload_sha256=payload_sha256,
            state=state,
        )
    except ValueError as error:
        raise PaperCheckpointError(str(error)) from error


def save_paper_checkpoint(
    database_path: str | os.PathLike[str],
    run_id: str,
    sequence: int,
    state: PaperLoopState,
    created_at_unix_ms: int,
) -> PaperCheckpointRecord:
    payload = encode_paper_checkpoint(run_id, sequence, state, created_at_unix_ms)
    record = decode_paper_checkpoint(payload)
    payload_json = payload.decode("utf-8")

    connection = _connect(database_path)
    try:
        _require_checkpoint_table(connection)
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            f"""SELECT run_id, sequence, checkpoint_schema_version,
                       state_as_of_unix_ms, created_at_unix_ms,
                       payload_sha256, payload_json
                FROM {_TABLE_NAME}
                WHERE run_id = ? AND sequence = ?""",
            (run_id, sequence),
        ).fetchone()
        if existing is not None:
            if _stored_row_matches_record(existing, record, payload_json):
                connection.rollback()
                return record
            connection.rollback()
            raise PaperCheckpointError(
                "checkpoint sequence collision with different state or metadata"
            )

        latest_sequence = connection.execute(
            f"SELECT MAX(sequence) FROM {_TABLE_NAME} WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        if latest_sequence is not None and sequence < latest_sequence:
            connection.rollback()
            raise PaperCheckpointError(
                "checkpoint sequence must be monotonic for a run"
            )

        connection.execute(
            f"""INSERT INTO {_TABLE_NAME} (
                    run_id, sequence, checkpoint_schema_version,
                    state_as_of_unix_ms, created_at_unix_ms,
                    payload_sha256, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.run_id,
                record.sequence,
                record.checkpoint_schema_version,
                record.state_as_of_unix_ms,
                record.created_at_unix_ms,
                record.payload_sha256,
                payload_json,
            ),
        )
        connection.commit()
        return record
    except PaperCheckpointError:
        _rollback_if_needed(connection)
        raise
    except sqlite3.Error as error:
        _rollback_if_needed(connection)
        raise PaperCheckpointError(f"checkpoint storage error: {error}") from error
    finally:
        connection.close()


def load_latest_paper_checkpoint(
    database_path: str | os.PathLike[str],
    run_id: str,
) -> PaperCheckpointRecord | None:
    _require_non_empty_string("run_id", run_id)
    connection = _connect(database_path)
    try:
        _require_checkpoint_table(connection)
        row = connection.execute(
            f"""SELECT run_id, sequence, checkpoint_schema_version,
                       state_as_of_unix_ms, created_at_unix_ms,
                       payload_sha256, payload_json
                FROM {_TABLE_NAME}
                WHERE run_id = ?
                ORDER BY sequence DESC
                LIMIT 1""",
            (run_id,),
        ).fetchone()
    except PaperCheckpointError:
        raise
    except sqlite3.Error as error:
        raise PaperCheckpointError(f"checkpoint storage error: {error}") from error
    finally:
        connection.close()

    if row is None:
        return None
    payload_json = row[6]
    if not isinstance(payload_json, str):
        raise PaperCheckpointError("checkpoint payload_json is not text")
    record = decode_paper_checkpoint(
        payload_json.encode("utf-8"),
        expected_sha256=row[5],
    )
    if not _stored_row_matches_record(row, record, payload_json):
        raise PaperCheckpointError("checkpoint row/envelope metadata mismatch")
    return record


def validate_restart_equivalence(
    expected: PaperLoopState,
    restored: PaperLoopState,
) -> RestartValidationReport:
    if not isinstance(expected, PaperLoopState) or not isinstance(restored, PaperLoopState):
        raise PaperCheckpointError("restart validation requires PaperLoopState values")

    expected_fingerprint = _state_fingerprint(expected)
    restored_fingerprint = _state_fingerprint(restored)
    expected_accounting = validate_paper_accounting(expected)
    restored_accounting = validate_paper_accounting(restored)

    differences: list[str] = []
    if expected != restored:
        differences.append("STATE_MISMATCH")
    if expected_fingerprint != restored_fingerprint:
        differences.append("STATE_FINGERPRINT_MISMATCH")
    if expected_accounting != restored_accounting:
        differences.append("ACCOUNTING_MISMATCH")
    if (
        expected_accounting.status is AccountingValidationStatus.INVALID
        or restored_accounting.status is AccountingValidationStatus.INVALID
    ):
        differences.append("ACCOUNTING_INVALID")

    return RestartValidationReport(
        equivalent=not differences,
        expected_state_sha256=expected_fingerprint,
        restored_state_sha256=restored_fingerprint,
        expected_accounting=expected_accounting,
        restored_accounting=restored_accounting,
        differences=tuple(differences),
    )


def _state_fingerprint(state: PaperLoopState) -> str:
    return hashlib.sha256(_canonical_json(_encode_value(state))).hexdigest()


def _encode_value(value: object) -> object:
    value_type = type(value)
    if isinstance(value, Enum):
        enum_name = _ENUM_NAME_BY_TYPE.get(value_type)
        if enum_name is None:
            raise PaperCheckpointError(
                f"unsupported enum type: {value_type.__name__}"
            )
        return {"$enum": enum_name, "value": value.value}

    dataclass_name = _DATACLASS_NAME_BY_TYPE.get(value_type)
    if dataclass_name is not None:
        if not is_dataclass(value):
            raise PaperCheckpointError("registered dataclass value is malformed")
        return {
            "$type": dataclass_name,
            "fields": {
                field.name: _encode_value(getattr(value, field.name))
                for field in fields(value)
            },
        }

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PaperCheckpointError("checkpoint floats must be finite")
        return {"$float": value.hex()}
    if isinstance(value, tuple):
        return {"$tuple": [_encode_value(item) for item in value]}
    if isinstance(value, frozenset):
        encoded = [_encode_value(item) for item in value]
        encoded.sort(key=lambda item: _canonical_json(item))
        return {"$frozenset": encoded}
    raise PaperCheckpointError(
        f"unsupported checkpoint value type: {value_type.__name__}"
    )


def _decode_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise PaperCheckpointError("raw JSON floats are not allowed in checkpoint state")
    if isinstance(value, list):
        raise PaperCheckpointError("raw JSON arrays are not allowed in checkpoint state")
    if not isinstance(value, dict):
        raise PaperCheckpointError("checkpoint value has unsupported JSON type")

    keys = set(value)
    if keys == {"$float"}:
        encoded = value["$float"]
        if not isinstance(encoded, str):
            raise PaperCheckpointError("malformed checkpoint float tag")
        try:
            decoded = float.fromhex(encoded)
        except ValueError as error:
            raise PaperCheckpointError("malformed checkpoint float value") from error
        if not math.isfinite(decoded):
            raise PaperCheckpointError("checkpoint floats must be finite")
        return decoded

    if keys == {"$tuple"}:
        items = value["$tuple"]
        if not isinstance(items, list):
            raise PaperCheckpointError("malformed checkpoint tuple tag")
        return tuple(_decode_value(item) for item in items)

    if keys == {"$frozenset"}:
        items = value["$frozenset"]
        if not isinstance(items, list):
            raise PaperCheckpointError("malformed checkpoint frozenset tag")
        decoded = tuple(_decode_value(item) for item in items)
        try:
            return frozenset(decoded)
        except TypeError as error:
            raise PaperCheckpointError("frozenset contains unhashable value") from error

    if keys == {"$enum", "value"}:
        enum_name = value["$enum"]
        if not isinstance(enum_name, str) or enum_name not in _ENUM_BY_NAME:
            raise PaperCheckpointError("unknown checkpoint enum type")
        enum_type = _ENUM_BY_NAME[enum_name]
        try:
            return enum_type(value["value"])
        except (TypeError, ValueError) as error:
            raise PaperCheckpointError("invalid checkpoint enum value") from error

    if keys == {"$type", "fields"}:
        type_name = value["$type"]
        field_values = value["fields"]
        if not isinstance(type_name, str) or type_name not in _DATACLASS_BY_NAME:
            raise PaperCheckpointError("unknown checkpoint dataclass type")
        if not isinstance(field_values, dict):
            raise PaperCheckpointError("malformed checkpoint dataclass fields")
        dataclass_type = _DATACLASS_BY_NAME[type_name]
        expected_fields = {field.name for field in fields(dataclass_type)}
        if set(field_values) != expected_fields:
            raise PaperCheckpointError("malformed checkpoint dataclass field set")
        decoded_fields = {
            name: _decode_value(field_values[name]) for name in expected_fields
        }
        try:
            return dataclass_type(**decoded_fields)
        except (TypeError, ValueError) as error:
            raise PaperCheckpointError(
                f"checkpoint {type_name} invariants rejected restored state: {error}"
            ) from error

    raise PaperCheckpointError("checkpoint value contains malformed type tag")


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PaperCheckpointError("checkpoint value cannot be canonicalized") from error


def _payload_bytes(payload: bytes | str) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise PaperCheckpointError("checkpoint payload must be bytes or text")


def _connect(database_path: str | os.PathLike[str]) -> sqlite3.Connection:
    try:
        return sqlite3.connect(Path(database_path))
    except (TypeError, ValueError, sqlite3.Error, OSError) as error:
        raise PaperCheckpointError(f"cannot open checkpoint database: {error}") from error


def _require_checkpoint_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (_TABLE_NAME,),
    ).fetchone()
    if row is None or row[0] != 1:
        raise PaperCheckpointError(
            "paper checkpoint migration is missing from operational database"
        )


def _stored_row_matches_record(
    row: tuple[Any, ...],
    record: PaperCheckpointRecord,
    payload_json: str,
) -> bool:
    return (
        len(row) == 7
        and row[0] == record.run_id
        and row[1] == record.sequence
        and row[2] == record.checkpoint_schema_version
        and row[3] == record.state_as_of_unix_ms
        and row[4] == record.created_at_unix_ms
        and row[5] == record.payload_sha256
        and row[6] == payload_json
    )


def _rollback_if_needed(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PaperCheckpointError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PaperCheckpointError(f"{name} must be a non-negative integer")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PaperCheckpointError(f"{name} must be a lowercase SHA-256 hex digest")
