from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3

from shreks_brain.paper_validation import (
    FastPaperCheckpointRecord,
    decode_fast_paper_checkpoint,
    encode_fast_paper_checkpoint,
)

from .models import FastPaperRuntimeManifest
from .shadow_executor import FastPaperShadowExecutionTransition
from .shadow_ledger import (
    FastPaperShadowLedgerBinding,
    build_fast_paper_shadow_ledger_binding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from .shadow_runtime_state import (
    FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION,
    FastPaperShadowRuntimeState,
    _build_fast_paper_shadow_runtime_state_for_checkpoint,
    _decode_fast_paper_shadow_runtime_state_payload,
    _encode_fast_paper_shadow_runtime_state_payload,
    load_latest_fast_paper_shadow_runtime_state,
)


FAST_PAPER_SHADOW_COMMIT_VERSION = "fl10-fast-paper-shadow-atomic-commit-v1"

_CHECKPOINT_TABLE = "paper_loop_checkpoints"
_BINDING_TABLE = "fast_paper_shadow_ledger_bindings"
_RUNTIME_TABLE = "fast_paper_shadow_runtime_states"


@dataclass(frozen=True, slots=True)
class FastPaperShadowCommitResult:
    version: str
    checkpoint: FastPaperCheckpointRecord
    runtime_state: FastPaperShadowRuntimeState

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_SHADOW_COMMIT_VERSION:
            raise ValueError(
                "unsupported Fast PAPER shadow commit version"
            )
        if type(self.checkpoint) is not FastPaperCheckpointRecord:
            raise ValueError(
                "checkpoint must be exact FastPaperCheckpointRecord"
            )
        if type(self.runtime_state) is not FastPaperShadowRuntimeState:
            raise ValueError(
                "runtime_state must be exact FastPaperShadowRuntimeState"
            )
        if (
            self.runtime_state.paper_checkpoint_sequence
            != self.checkpoint.sequence
            or self.runtime_state.paper_checkpoint_payload_sha256
            != self.checkpoint.payload_sha256
        ):
            raise ValueError(
                "shadow commit result runtime state is torn from checkpoint"
            )


def commit_fast_paper_shadow_transition_atomically(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    current_checkpoint: FastPaperCheckpointRecord,
    current_runtime_state: FastPaperShadowRuntimeState,
    transition: FastPaperShadowExecutionTransition,
    *,
    sequence: int,
    created_at_unix_ms: int,
) -> FastPaperShadowCommitResult:
    _require_inputs(
        manifest,
        binding,
        current_checkpoint,
        current_runtime_state,
        transition,
        sequence=sequence,
        created_at_unix_ms=created_at_unix_ms,
    )
    _require_exact_latest_pair(
        manifest,
        binding,
        current_checkpoint,
        current_runtime_state,
    )

    checkpoint_payload = encode_fast_paper_checkpoint(
        binding.run_id,
        sequence,
        transition.next_paper_state,
        created_at_unix_ms,
    )
    checkpoint = decode_fast_paper_checkpoint(checkpoint_payload)
    runtime_state = _build_fast_paper_shadow_runtime_state_for_checkpoint(
        binding,
        checkpoint,
        market_positions=transition.next_market_positions,
        execution_policy_fingerprint_sha256=(
            transition.execution_policy_fingerprint_sha256
        ),
        pending_buy=transition.next_pending_buy,
        last_processed_source_sequence=(
            transition.last_processed_source_sequence
        ),
        last_processed_source_event_id=(
            transition.last_processed_source_event_id
        ),
        last_processed_decision_evidence_fingerprint_sha256=(
            transition.last_processed_decision_evidence_fingerprint_sha256
        ),
    )
    runtime_payload = _encode_fast_paper_shadow_runtime_state_payload(
        runtime_state
    )
    runtime_payload_sha256 = hashlib.sha256(
        runtime_payload.encode("utf-8")
    ).hexdigest()

    database = _database_path(binding)
    connection = _connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_storage_schema(connection)
        _require_binding_row(connection, binding)
        _require_current_pair_in_transaction(
            connection,
            binding,
            current_checkpoint,
            current_runtime_state,
        )
        _require_target_sequence_free(
            connection,
            binding.run_id,
            sequence,
        )
        _insert_checkpoint_row(
            connection,
            checkpoint,
            checkpoint_payload.decode("utf-8"),
        )
        _insert_shadow_runtime_state_row(
            connection,
            binding,
            runtime_state,
            created_at_unix_ms,
            runtime_payload_sha256,
            runtime_payload,
        )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()

    os.chmod(database, 0o600)
    restored_checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    restored_runtime = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if restored_checkpoint != checkpoint:
        raise ValueError(
            "atomic shadow commit checkpoint read-back mismatch"
        )
    if restored_runtime != runtime_state:
        raise ValueError(
            "atomic shadow commit runtime-state read-back mismatch"
        )

    return FastPaperShadowCommitResult(
        version=FAST_PAPER_SHADOW_COMMIT_VERSION,
        checkpoint=checkpoint,
        runtime_state=runtime_state,
    )


def _require_inputs(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    current_checkpoint: FastPaperCheckpointRecord,
    current_runtime_state: FastPaperShadowRuntimeState,
    transition: FastPaperShadowExecutionTransition,
    *,
    sequence: int,
    created_at_unix_ms: int,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(binding) is not FastPaperShadowLedgerBinding:
        raise ValueError(
            "binding must be exact FastPaperShadowLedgerBinding"
        )
    expected_binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id=binding.run_id,
        database_path=binding.database_path,
    )
    if binding != expected_binding:
        raise ValueError(
            "shadow atomic commit ledger binding does not authenticate against manifest"
        )
    if type(current_checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "current_checkpoint must be exact FastPaperCheckpointRecord"
        )
    if type(current_runtime_state) is not FastPaperShadowRuntimeState:
        raise ValueError(
            "current_runtime_state must be exact FastPaperShadowRuntimeState"
        )
    if type(transition) is not FastPaperShadowExecutionTransition:
        raise ValueError(
            "transition must be exact FastPaperShadowExecutionTransition"
        )
    _require_non_negative_int("sequence", sequence)
    if sequence != current_checkpoint.sequence + 1:
        raise ValueError(
            "shadow atomic commit sequence must be exactly the next checkpoint sequence"
        )
    _require_non_negative_int(
        "created_at_unix_ms",
        created_at_unix_ms,
    )
    if created_at_unix_ms < transition.next_paper_state.as_of_unix_ms:
        raise ValueError(
            "shadow atomic commit creation time cannot precede transition state"
        )
    if current_checkpoint.run_id != binding.run_id:
        raise ValueError(
            "current checkpoint run_id does not match shadow ledger binding"
        )
    if (
        current_runtime_state.paper_checkpoint_sequence
        != current_checkpoint.sequence
        or current_runtime_state.paper_checkpoint_payload_sha256
        != current_checkpoint.payload_sha256
    ):
        raise ValueError(
            "current shadow checkpoint/runtime pair is torn"
        )
    if (
        current_runtime_state.binding_fingerprint_sha256
        != binding.binding_fingerprint_sha256
    ):
        raise ValueError(
            "current shadow runtime binding fingerprint mismatch"
        )
    if (
        transition.execution_policy_fingerprint_sha256
        != current_runtime_state.execution_policy_fingerprint_sha256
    ):
        raise ValueError(
            "shadow atomic commit execution policy fingerprint drift"
        )


def _require_exact_latest_pair(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
) -> None:
    latest_checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    latest_runtime = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if latest_checkpoint != checkpoint:
        raise ValueError(
            "shadow atomic commit requires the exact latest durable checkpoint"
        )
    if latest_runtime != runtime_state:
        raise ValueError(
            "shadow atomic commit requires the exact latest durable runtime state"
        )


def _require_current_pair_in_transaction(
    connection: sqlite3.Connection,
    binding: FastPaperShadowLedgerBinding,
    checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
) -> None:
    checkpoint_row = connection.execute(
        f"""
        SELECT sequence, payload_sha256, payload_json
        FROM {_CHECKPOINT_TABLE}
        WHERE run_id = ?
        ORDER BY sequence DESC
        LIMIT 1
        """,
        (binding.run_id,),
    ).fetchone()
    if checkpoint_row is None:
        raise ValueError(
            "shadow atomic commit durable checkpoint disappeared"
        )
    expected_checkpoint_payload = encode_fast_paper_checkpoint(
        checkpoint.run_id,
        checkpoint.sequence,
        checkpoint.state,
        checkpoint.created_at_unix_ms,
    ).decode("utf-8")
    if checkpoint_row != (
        checkpoint.sequence,
        checkpoint.payload_sha256,
        expected_checkpoint_payload,
    ):
        raise ValueError(
            "shadow atomic commit detected stale durable checkpoint"
        )

    runtime_row = connection.execute(
        f"""
        SELECT
            paper_checkpoint_sequence,
            paper_checkpoint_payload_sha256,
            state_schema_version,
            payload_sha256,
            payload_json
        FROM {_RUNTIME_TABLE}
        WHERE run_id = ?
        ORDER BY paper_checkpoint_sequence DESC
        LIMIT 1
        """,
        (binding.run_id,),
    ).fetchone()
    if runtime_row is None:
        raise ValueError(
            "shadow atomic commit durable runtime state disappeared"
        )
    expected_runtime_payload = (
        _encode_fast_paper_shadow_runtime_state_payload(runtime_state)
    )
    expected_runtime_sha = hashlib.sha256(
        expected_runtime_payload.encode("utf-8")
    ).hexdigest()
    if runtime_row != (
        runtime_state.paper_checkpoint_sequence,
        runtime_state.paper_checkpoint_payload_sha256,
        runtime_state.schema_version,
        expected_runtime_sha,
        expected_runtime_payload,
    ):
        raise ValueError(
            "shadow atomic commit detected stale durable runtime state"
        )
    decoded_runtime = _decode_fast_paper_shadow_runtime_state_payload(
        runtime_row[4]
    )
    if decoded_runtime != runtime_state:
        raise ValueError(
            "shadow atomic commit durable runtime payload changed"
        )


def _require_target_sequence_free(
    connection: sqlite3.Connection,
    run_id: str,
    sequence: int,
) -> None:
    checkpoint_exists = connection.execute(
        f"""
        SELECT 1 FROM {_CHECKPOINT_TABLE}
        WHERE run_id = ? AND sequence = ?
        """,
        (run_id, sequence),
    ).fetchone()
    runtime_exists = connection.execute(
        f"""
        SELECT 1 FROM {_RUNTIME_TABLE}
        WHERE run_id = ? AND paper_checkpoint_sequence = ?
        """,
        (run_id, sequence),
    ).fetchone()
    if checkpoint_exists is not None or runtime_exists is not None:
        raise ValueError(
            "shadow atomic commit target sequence already exists"
        )


def _insert_checkpoint_row(
    connection: sqlite3.Connection,
    checkpoint: FastPaperCheckpointRecord,
    payload_json: str,
) -> None:
    connection.execute(
        f"""
        INSERT INTO {_CHECKPOINT_TABLE}(
            run_id,
            sequence,
            checkpoint_schema_version,
            state_as_of_unix_ms,
            created_at_unix_ms,
            payload_sha256,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            checkpoint.run_id,
            checkpoint.sequence,
            checkpoint.checkpoint_schema_version,
            checkpoint.state_as_of_unix_ms,
            checkpoint.created_at_unix_ms,
            checkpoint.payload_sha256,
            payload_json,
        ),
    )


def _insert_shadow_runtime_state_row(
    connection: sqlite3.Connection,
    binding: FastPaperShadowLedgerBinding,
    runtime_state: FastPaperShadowRuntimeState,
    created_at_unix_ms: int,
    payload_sha256: str,
    payload_json: str,
) -> None:
    connection.execute(
        f"""
        INSERT INTO {_RUNTIME_TABLE}(
            run_id,
            paper_checkpoint_sequence,
            paper_checkpoint_payload_sha256,
            state_schema_version,
            created_at_unix_ms,
            payload_sha256,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            binding.run_id,
            runtime_state.paper_checkpoint_sequence,
            runtime_state.paper_checkpoint_payload_sha256,
            FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION,
            created_at_unix_ms,
            payload_sha256,
            payload_json,
        ),
    )


def _require_binding_row(
    connection: sqlite3.Connection,
    binding: FastPaperShadowLedgerBinding,
) -> None:
    row = connection.execute(
        f"""
        SELECT binding_fingerprint_sha256
        FROM {_BINDING_TABLE}
        WHERE run_id = ?
        """,
        (binding.run_id,),
    ).fetchone()
    if row != (binding.binding_fingerprint_sha256,):
        raise ValueError(
            "shadow atomic commit ledger binding row mismatch"
        )


def _require_storage_schema(connection: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    required = {
        _CHECKPOINT_TABLE,
        _BINDING_TABLE,
        _RUNTIME_TABLE,
    }
    if not required.issubset(tables):
        raise ValueError(
            "shadow atomic commit storage schema is incomplete"
        )


def _database_path(binding: FastPaperShadowLedgerBinding) -> Path:
    path = Path(binding.database_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow atomic commit database must be an existing regular non-symlink file"
        )
    return path


def _connect(database: Path) -> sqlite3.Connection:
    try:
        return sqlite3.connect(database, timeout=5.0)
    except sqlite3.Error as exc:
        raise ValueError(
            "shadow atomic commit database connection failed"
        ) from exc


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )
