from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
import os
import sqlite3

from shreks_brain.exits import ExitPolicy, ExitState
from shreks_brain.fast_paper import (
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperBuyApproval,
    FastPaperEventRecord,
    FastPaperLoopState,
    FastPaperMarketCursor,
    FastPaperPositionActionApproval,
    FastPaperPositionActionPolicy,
    FastPaperPositionActionState,
    FastPaperProtectiveExitPolicy,
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
from shreks_brain.risk import TradeSide

from .accounting import validate_paper_ledger
from .fast_models import (
    FAST_PAPER_CHECKPOINT_SCHEMA_VERSION,
    FastPaperCheckpointError,
    FastPaperCheckpointRecord,
    FastPaperRestartValidationReport,
    FastPaperRuntimeState,
)
from .models import AccountingValidationReport, AccountingValidationStatus
from .protected_models import (
    FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION,
    FastPaperProtectedCheckpointRecord,
    FastPaperProtectedRuntimeState,
)


_TABLE_NAME = "paper_loop_checkpoints"


_DATACLASS_TYPES = (
    PaperLedger,
    PaperLedgerEntry,
    PaperPosition,
    PaperFillPolicy,
    FastPaperActionAssessment,
    FastPaperMarketCursor,
    FastPaperEventRecord,
    FastPaperLoopState,
    FastPaperBuyApproval,
    FastPaperPositionActionPolicy,
    FastPaperPositionActionApproval,
    FastPaperPositionActionState,
    FastPaperRuntimeState,
    ExitPolicy,
    ExitState,
    FastPaperProtectiveExitPolicy,
    FastPaperProtectedRuntimeState,
)
_DATACLASS_BY_NAME = {item.__name__: item for item in _DATACLASS_TYPES}
_DATACLASS_NAME_BY_TYPE = {item: item.__name__ for item in _DATACLASS_TYPES}

_ENUM_TYPES = (
    PaperPositionState,
    PaperLedgerReasonCode,
    PaperExecutionState,
    PaperExecutionReasonCode,
    TradeSide,
    FastPaperAction,
)
_ENUM_BY_NAME = {item.__name__: item for item in _ENUM_TYPES}
_ENUM_NAME_BY_TYPE = {item: item.__name__ for item in _ENUM_TYPES}


def validate_fast_paper_accounting(
    state: FastPaperRuntimeState,
) -> AccountingValidationReport:
    """Reconcile the authoritative C3 ledger inside one validated Fast PAPER runtime."""

    if not isinstance(state, FastPaperRuntimeState):
        raise ValueError("state must be a FastPaperRuntimeState")
    return validate_paper_ledger(state.ledger)


def encode_fast_paper_checkpoint(
    run_id: str,
    sequence: int,
    state: FastPaperRuntimeState,
    created_at_unix_ms: int,
) -> bytes:
    _require_non_empty_string("run_id", run_id)
    _require_non_negative_int("sequence", sequence)
    if not isinstance(state, FastPaperRuntimeState):
        raise FastPaperCheckpointError("state must be a FastPaperRuntimeState")
    _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
    if created_at_unix_ms < state.as_of_unix_ms:
        raise FastPaperCheckpointError(
            "created_at_unix_ms must not precede Fast PAPER runtime state"
        )

    envelope = {
        "checkpoint_schema_version": FAST_PAPER_CHECKPOINT_SCHEMA_VERSION,
        "run_id": run_id,
        "sequence": sequence,
        "created_at_unix_ms": created_at_unix_ms,
        "state_as_of_unix_ms": state.as_of_unix_ms,
        "state": _encode_value(state),
    }
    return _canonical_json(envelope)


def decode_fast_paper_checkpoint(
    payload: bytes | str,
    *,
    expected_sha256: str | None = None,
) -> FastPaperCheckpointRecord:
    raw = _payload_bytes(payload)
    payload_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        _require_sha256("expected_sha256", expected_sha256)
        if payload_sha256 != expected_sha256:
            raise FastPaperCheckpointError("Fast PAPER checkpoint checksum mismatch")

    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FastPaperCheckpointError(
            "Fast PAPER checkpoint payload is not valid UTF-8 JSON"
        ) from error
    if not isinstance(envelope, dict):
        raise FastPaperCheckpointError("Fast PAPER checkpoint envelope must be an object")
    expected_keys = {
        "checkpoint_schema_version",
        "run_id",
        "sequence",
        "created_at_unix_ms",
        "state_as_of_unix_ms",
        "state",
    }
    if set(envelope) != expected_keys:
        raise FastPaperCheckpointError("Fast PAPER checkpoint envelope is malformed")
    if envelope["checkpoint_schema_version"] != FAST_PAPER_CHECKPOINT_SCHEMA_VERSION:
        raise FastPaperCheckpointError("unsupported Fast PAPER checkpoint schema version")

    run_id = envelope["run_id"]
    sequence = envelope["sequence"]
    created_at_unix_ms = envelope["created_at_unix_ms"]
    state_as_of_unix_ms = envelope["state_as_of_unix_ms"]
    _require_non_empty_string("run_id", run_id)
    _require_non_negative_int("sequence", sequence)
    _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
    _require_non_negative_int("state_as_of_unix_ms", state_as_of_unix_ms)

    state = _decode_value(envelope["state"])
    if not isinstance(state, FastPaperRuntimeState):
        raise FastPaperCheckpointError(
            "Fast PAPER checkpoint state must decode to FastPaperRuntimeState"
        )
    if state.as_of_unix_ms != state_as_of_unix_ms:
        raise FastPaperCheckpointError("Fast PAPER checkpoint state timestamp mismatch")
    if created_at_unix_ms < state_as_of_unix_ms:
        raise FastPaperCheckpointError("Fast PAPER checkpoint creation time precedes state")

    canonical = encode_fast_paper_checkpoint(
        run_id,
        sequence,
        state,
        created_at_unix_ms,
    )
    if canonical != raw:
        raise FastPaperCheckpointError("Fast PAPER checkpoint payload is not canonical")

    try:
        return FastPaperCheckpointRecord(
            run_id=run_id,
            sequence=sequence,
            checkpoint_schema_version=FAST_PAPER_CHECKPOINT_SCHEMA_VERSION,
            state_as_of_unix_ms=state_as_of_unix_ms,
            created_at_unix_ms=created_at_unix_ms,
            payload_sha256=payload_sha256,
            state=state,
        )
    except ValueError as error:
        raise FastPaperCheckpointError(str(error)) from error


def save_fast_paper_checkpoint(
    database_path: str | os.PathLike[str],
    run_id: str,
    sequence: int,
    state: FastPaperRuntimeState,
    created_at_unix_ms: int,
) -> FastPaperCheckpointRecord:
    payload = encode_fast_paper_checkpoint(
        run_id,
        sequence,
        state,
        created_at_unix_ms,
    )
    record = decode_fast_paper_checkpoint(payload)
    payload_json = payload.decode("utf-8")

    connection = _connect(database_path)
    try:
        _require_checkpoint_table(connection)
        connection.execute("BEGIN IMMEDIATE")
        _require_fast_schema_namespace(connection, run_id)

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
            raise FastPaperCheckpointError(
                "Fast PAPER checkpoint sequence collision with different state or metadata"
            )

        latest_sequence = connection.execute(
            f"SELECT MAX(sequence) FROM {_TABLE_NAME} WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        if latest_sequence is not None and sequence < latest_sequence:
            connection.rollback()
            raise FastPaperCheckpointError(
                "Fast PAPER checkpoint sequence must be monotonic for a run"
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
    except FastPaperCheckpointError:
        _rollback_if_needed(connection)
        raise
    except sqlite3.Error as error:
        _rollback_if_needed(connection)
        raise FastPaperCheckpointError(
            f"Fast PAPER checkpoint storage error: {error}"
        ) from error
    finally:
        connection.close()


def load_latest_fast_paper_checkpoint(
    database_path: str | os.PathLike[str],
    run_id: str,
) -> FastPaperCheckpointRecord | None:
    _require_non_empty_string("run_id", run_id)
    connection = _connect(database_path)
    try:
        _require_checkpoint_table(connection)
        _require_fast_schema_namespace(connection, run_id)
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
    except FastPaperCheckpointError:
        raise
    except sqlite3.Error as error:
        raise FastPaperCheckpointError(
            f"Fast PAPER checkpoint storage error: {error}"
        ) from error
    finally:
        connection.close()

    if row is None:
        return None
    payload_json = row[6]
    if not isinstance(payload_json, str):
        raise FastPaperCheckpointError("Fast PAPER checkpoint payload_json is not text")
    record = decode_fast_paper_checkpoint(
        payload_json.encode("utf-8"),
        expected_sha256=row[5],
    )
    if not _stored_row_matches_record(row, record, payload_json):
        raise FastPaperCheckpointError("Fast PAPER checkpoint row/envelope metadata mismatch")
    return record


def validate_fast_paper_restart_equivalence(
    expected: FastPaperRuntimeState,
    restored: FastPaperRuntimeState,
) -> FastPaperRestartValidationReport:
    if not isinstance(expected, FastPaperRuntimeState) or not isinstance(
        restored, FastPaperRuntimeState
    ):
        raise FastPaperCheckpointError(
            "Fast PAPER restart validation requires FastPaperRuntimeState values"
        )

    expected_fingerprint = _state_fingerprint(expected)
    restored_fingerprint = _state_fingerprint(restored)
    expected_accounting = validate_fast_paper_accounting(expected)
    restored_accounting = validate_fast_paper_accounting(restored)

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

    return FastPaperRestartValidationReport(
        equivalent=not differences,
        expected_state_sha256=expected_fingerprint,
        restored_state_sha256=restored_fingerprint,
        expected_accounting=expected_accounting,
        restored_accounting=restored_accounting,
        differences=tuple(differences),
    )


def encode_fast_paper_protected_checkpoint(
    run_id: str,
    sequence: int,
    state: FastPaperProtectedRuntimeState,
    created_at_unix_ms: int,
) -> bytes:
    _require_non_empty_string("run_id", run_id)
    _require_non_negative_int("sequence", sequence)
    if not isinstance(state, FastPaperProtectedRuntimeState):
        raise FastPaperCheckpointError(
            "state must be a FastPaperProtectedRuntimeState"
        )
    _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
    state_time = state.base_runtime_state.as_of_unix_ms
    if created_at_unix_ms < state_time:
        raise FastPaperCheckpointError(
            "created_at_unix_ms must not precede Fast PAPER protected runtime state"
        )

    envelope = {
        "checkpoint_schema_version": FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION,
        "run_id": run_id,
        "sequence": sequence,
        "created_at_unix_ms": created_at_unix_ms,
        "state_as_of_unix_ms": state_time,
        "state": _encode_value(state),
    }
    return _canonical_json(envelope)


def decode_fast_paper_protected_checkpoint(
    payload: bytes | str,
    *,
    expected_sha256: str | None = None,
) -> FastPaperProtectedCheckpointRecord:
    raw = _payload_bytes(payload)
    payload_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        _require_sha256("expected_sha256", expected_sha256)
        if payload_sha256 != expected_sha256:
            raise FastPaperCheckpointError(
                "Fast PAPER protected checkpoint checksum mismatch"
            )

    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint payload is not valid UTF-8 JSON"
        ) from error
    if not isinstance(envelope, dict):
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint envelope must be an object"
        )
    expected_keys = {
        "checkpoint_schema_version",
        "run_id",
        "sequence",
        "created_at_unix_ms",
        "state_as_of_unix_ms",
        "state",
    }
    if set(envelope) != expected_keys:
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint envelope is malformed"
        )
    if (
        envelope["checkpoint_schema_version"]
        != FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION
    ):
        raise FastPaperCheckpointError(
            "unsupported Fast PAPER protected checkpoint schema version"
        )

    run_id = envelope["run_id"]
    sequence = envelope["sequence"]
    created_at_unix_ms = envelope["created_at_unix_ms"]
    state_as_of_unix_ms = envelope["state_as_of_unix_ms"]
    _require_non_empty_string("run_id", run_id)
    _require_non_negative_int("sequence", sequence)
    _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
    _require_non_negative_int("state_as_of_unix_ms", state_as_of_unix_ms)

    state = _decode_value(envelope["state"])
    if not isinstance(state, FastPaperProtectedRuntimeState):
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint state must decode to FastPaperProtectedRuntimeState"
        )
    if state.base_runtime_state.as_of_unix_ms != state_as_of_unix_ms:
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint state timestamp mismatch"
        )
    if created_at_unix_ms < state_as_of_unix_ms:
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint creation time precedes state"
        )

    canonical = encode_fast_paper_protected_checkpoint(
        run_id,
        sequence,
        state,
        created_at_unix_ms,
    )
    if canonical != raw:
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint payload is not canonical"
        )

    try:
        return FastPaperProtectedCheckpointRecord(
            run_id=run_id,
            sequence=sequence,
            checkpoint_schema_version=FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION,
            state_as_of_unix_ms=state_as_of_unix_ms,
            created_at_unix_ms=created_at_unix_ms,
            payload_sha256=payload_sha256,
            state=state,
        )
    except ValueError as error:
        raise FastPaperCheckpointError(str(error)) from error


def save_fast_paper_protected_checkpoint(
    database_path: str | os.PathLike[str],
    run_id: str,
    sequence: int,
    state: FastPaperProtectedRuntimeState,
    created_at_unix_ms: int,
) -> FastPaperProtectedCheckpointRecord:
    payload = encode_fast_paper_protected_checkpoint(
        run_id,
        sequence,
        state,
        created_at_unix_ms,
    )
    record = decode_fast_paper_protected_checkpoint(payload)
    payload_json = payload.decode("utf-8")

    connection = _connect(database_path)
    try:
        _require_checkpoint_table(connection)
        connection.execute("BEGIN IMMEDIATE")
        _require_protected_schema_namespace(connection, run_id)

        existing = connection.execute(
            f"""SELECT run_id, sequence, checkpoint_schema_version,
                       state_as_of_unix_ms, created_at_unix_ms,
                       payload_sha256, payload_json
                FROM {_TABLE_NAME}
                WHERE run_id = ? AND sequence = ?""",
            (run_id, sequence),
        ).fetchone()
        if existing is not None:
            if _stored_row_matches_protected_record(existing, record, payload_json):
                connection.rollback()
                return record
            connection.rollback()
            raise FastPaperCheckpointError(
                "Fast PAPER protected checkpoint sequence collision with different state or metadata"
            )

        latest_sequence = connection.execute(
            f"SELECT MAX(sequence) FROM {_TABLE_NAME} WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        if latest_sequence is not None and sequence < latest_sequence:
            connection.rollback()
            raise FastPaperCheckpointError(
                "Fast PAPER protected checkpoint sequence must be monotonic for a run"
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
    except FastPaperCheckpointError:
        _rollback_if_needed(connection)
        raise
    except sqlite3.Error as error:
        _rollback_if_needed(connection)
        raise FastPaperCheckpointError(
            f"Fast PAPER protected checkpoint storage error: {error}"
        ) from error
    finally:
        connection.close()


def load_latest_fast_paper_protected_checkpoint(
    database_path: str | os.PathLike[str],
    run_id: str,
) -> FastPaperProtectedCheckpointRecord | None:
    _require_non_empty_string("run_id", run_id)
    connection = _connect(database_path)
    try:
        _require_checkpoint_table(connection)
        _require_protected_schema_namespace(connection, run_id)
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
    except FastPaperCheckpointError:
        raise
    except sqlite3.Error as error:
        raise FastPaperCheckpointError(
            f"Fast PAPER protected checkpoint storage error: {error}"
        ) from error
    finally:
        connection.close()

    if row is None:
        return None
    payload_json = row[6]
    if not isinstance(payload_json, str):
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint payload_json is not text"
        )
    record = decode_fast_paper_protected_checkpoint(
        payload_json.encode("utf-8"),
        expected_sha256=row[5],
    )
    if not _stored_row_matches_protected_record(row, record, payload_json):
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint row/envelope metadata mismatch"
        )
    return record


def validate_fast_paper_protected_restart_equivalence(
    expected: FastPaperProtectedRuntimeState,
    restored: FastPaperProtectedRuntimeState,
) -> FastPaperRestartValidationReport:
    if not isinstance(expected, FastPaperProtectedRuntimeState) or not isinstance(
        restored,
        FastPaperProtectedRuntimeState,
    ):
        raise FastPaperCheckpointError(
            "Fast PAPER protected restart validation requires FastPaperProtectedRuntimeState values"
        )

    expected_fingerprint = _protected_state_fingerprint(expected)
    restored_fingerprint = _protected_state_fingerprint(restored)
    expected_accounting = validate_paper_ledger(expected.base_runtime_state.ledger)
    restored_accounting = validate_paper_ledger(restored.base_runtime_state.ledger)

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

    return FastPaperRestartValidationReport(
        equivalent=not differences,
        expected_state_sha256=expected_fingerprint,
        restored_state_sha256=restored_fingerprint,
        expected_accounting=expected_accounting,
        restored_accounting=restored_accounting,
        differences=tuple(differences),
    )


def _state_fingerprint(state: FastPaperRuntimeState) -> str:
    return hashlib.sha256(_canonical_json(_encode_value(state))).hexdigest()


def _protected_state_fingerprint(state: FastPaperProtectedRuntimeState) -> str:
    return hashlib.sha256(_canonical_json(_encode_value(state))).hexdigest()


def _encode_value(value: object) -> object:
    value_type = type(value)
    if isinstance(value, Enum):
        enum_name = _ENUM_NAME_BY_TYPE.get(value_type)
        if enum_name is None:
            raise FastPaperCheckpointError(
                f"unsupported Fast PAPER checkpoint enum type: {value_type.__name__}"
            )
        return {"$enum": enum_name, "value": value.value}

    dataclass_name = _DATACLASS_NAME_BY_TYPE.get(value_type)
    if dataclass_name is not None:
        if not is_dataclass(value):
            raise FastPaperCheckpointError(
                "registered Fast PAPER checkpoint dataclass is malformed"
            )
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
            raise FastPaperCheckpointError("Fast PAPER checkpoint floats must be finite")
        return {"$float": value.hex()}
    if isinstance(value, tuple):
        return {"$tuple": [_encode_value(item) for item in value]}
    if isinstance(value, frozenset):
        encoded = [_encode_value(item) for item in value]
        encoded.sort(key=lambda item: _canonical_json(item))
        return {"$frozenset": encoded}
    raise FastPaperCheckpointError(
        f"unsupported Fast PAPER checkpoint value type: {value_type.__name__}"
    )


def _decode_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise FastPaperCheckpointError(
            "raw JSON floats are not allowed in Fast PAPER checkpoint state"
        )
    if isinstance(value, list):
        raise FastPaperCheckpointError(
            "raw JSON arrays are not allowed in Fast PAPER checkpoint state"
        )
    if not isinstance(value, dict):
        raise FastPaperCheckpointError(
            "Fast PAPER checkpoint value has unsupported JSON type"
        )

    keys = set(value)
    if keys == {"$float"}:
        encoded = value["$float"]
        if not isinstance(encoded, str):
            raise FastPaperCheckpointError("malformed Fast PAPER checkpoint float tag")
        try:
            decoded = float.fromhex(encoded)
        except ValueError as error:
            raise FastPaperCheckpointError(
                "malformed Fast PAPER checkpoint float value"
            ) from error
        if not math.isfinite(decoded):
            raise FastPaperCheckpointError("Fast PAPER checkpoint floats must be finite")
        return decoded

    if keys == {"$tuple"}:
        items = value["$tuple"]
        if not isinstance(items, list):
            raise FastPaperCheckpointError("malformed Fast PAPER checkpoint tuple tag")
        return tuple(_decode_value(item) for item in items)

    if keys == {"$frozenset"}:
        items = value["$frozenset"]
        if not isinstance(items, list):
            raise FastPaperCheckpointError(
                "malformed Fast PAPER checkpoint frozenset tag"
            )
        decoded = tuple(_decode_value(item) for item in items)
        try:
            return frozenset(decoded)
        except TypeError as error:
            raise FastPaperCheckpointError(
                "Fast PAPER checkpoint frozenset contains unhashable value"
            ) from error

    if keys == {"$enum", "value"}:
        enum_name = value["$enum"]
        if not isinstance(enum_name, str) or enum_name not in _ENUM_BY_NAME:
            raise FastPaperCheckpointError("unknown Fast PAPER checkpoint enum type")
        enum_type = _ENUM_BY_NAME[enum_name]
        try:
            return enum_type(value["value"])
        except (TypeError, ValueError) as error:
            raise FastPaperCheckpointError(
                "invalid Fast PAPER checkpoint enum value"
            ) from error

    if keys == {"$type", "fields"}:
        type_name = value["$type"]
        field_values = value["fields"]
        if not isinstance(type_name, str) or type_name not in _DATACLASS_BY_NAME:
            raise FastPaperCheckpointError("unknown Fast PAPER checkpoint dataclass type")
        if not isinstance(field_values, dict):
            raise FastPaperCheckpointError(
                "malformed Fast PAPER checkpoint dataclass fields"
            )
        dataclass_type = _DATACLASS_BY_NAME[type_name]
        expected_fields = {field.name for field in fields(dataclass_type)}
        if set(field_values) != expected_fields:
            raise FastPaperCheckpointError(
                "malformed Fast PAPER checkpoint dataclass field set"
            )
        decoded_fields = {
            name: _decode_value(field_values[name]) for name in expected_fields
        }
        try:
            return dataclass_type(**decoded_fields)
        except (TypeError, ValueError) as error:
            raise FastPaperCheckpointError(
                f"Fast PAPER checkpoint {type_name} invariants rejected restored state: {error}"
            ) from error

    raise FastPaperCheckpointError("Fast PAPER checkpoint value contains malformed type tag")


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
        raise FastPaperCheckpointError(
            "Fast PAPER checkpoint value cannot be canonicalized"
        ) from error


def _payload_bytes(payload: bytes | str) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise FastPaperCheckpointError("Fast PAPER checkpoint payload must be bytes or text")


def _connect(database_path: str | os.PathLike[str]) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(os.fspath(database_path))
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except (OSError, TypeError, sqlite3.Error) as error:
        raise FastPaperCheckpointError(
            f"Fast PAPER checkpoint storage connection error: {error}"
        ) from error


def _require_checkpoint_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (_TABLE_NAME,),
    ).fetchone()
    if row is None:
        raise FastPaperCheckpointError(
            "Fast PAPER checkpoint requires migrated paper_loop_checkpoints table"
        )


def _require_fast_schema_namespace(
    connection: sqlite3.Connection,
    run_id: str,
) -> None:
    versions = tuple(
        row[0]
        for row in connection.execute(
            f"SELECT DISTINCT checkpoint_schema_version FROM {_TABLE_NAME} WHERE run_id = ?",
            (run_id,),
        ).fetchall()
    )
    if any(version != FAST_PAPER_CHECKPOINT_SCHEMA_VERSION for version in versions):
        raise FastPaperCheckpointError(
            "Fast PAPER checkpoint run_id schema namespace conflicts with existing checkpoints"
        )


def _require_protected_schema_namespace(
    connection: sqlite3.Connection,
    run_id: str,
) -> None:
    versions = tuple(
        row[0]
        for row in connection.execute(
            f"SELECT DISTINCT checkpoint_schema_version FROM {_TABLE_NAME} WHERE run_id = ?",
            (run_id,),
        ).fetchall()
    )
    if any(
        version != FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION
        for version in versions
    ):
        raise FastPaperCheckpointError(
            "Fast PAPER protected checkpoint run_id schema namespace conflicts with existing checkpoints"
        )


def _stored_row_matches_record(
    row: tuple[object, ...],
    record: FastPaperCheckpointRecord,
    payload_json: str,
) -> bool:
    return row == (
        record.run_id,
        record.sequence,
        record.checkpoint_schema_version,
        record.state_as_of_unix_ms,
        record.created_at_unix_ms,
        record.payload_sha256,
        payload_json,
    )


def _stored_row_matches_protected_record(
    row: tuple[object, ...],
    record: FastPaperProtectedCheckpointRecord,
    payload_json: str,
) -> bool:
    return row == (
        record.run_id,
        record.sequence,
        record.checkpoint_schema_version,
        record.state_as_of_unix_ms,
        record.created_at_unix_ms,
        record.payload_sha256,
        payload_json,
    )


def _rollback_if_needed(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FastPaperCheckpointError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperCheckpointError(f"{name} must be a non-negative integer")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FastPaperCheckpointError(
            f"{name} must be a lowercase SHA-256 hex digest"
        )
