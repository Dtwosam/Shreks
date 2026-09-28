from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    FastPaperCheckpointRecord,
    FastPaperRuntimeState,
    decode_fast_paper_checkpoint,
    encode_fast_paper_checkpoint,
    validate_fast_paper_accounting,
)

from .authoritative_handoff import (
    FastPaperAuthoritativeBinding,
    load_fast_paper_authoritative_binding,
    load_latest_fast_paper_authoritative_checkpoint,
)
from .authoritative_runtime_state import (
    FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE,
    FastPaperAuthoritativeMarketPosition,
    FastPaperAuthoritativeRuntimeState,
    _insert_runtime_state_row as _runtime_insert,
    build_fast_paper_authoritative_runtime_state,
    encode_fast_paper_authoritative_runtime_state,
    load_latest_fast_paper_authoritative_runtime_state,
)
from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest


FAST_PAPER_AUTHORITATIVE_COMMIT_VERSION = (
    "fast-paper-authoritative-commit-v1"
)
_BINDING_TABLE = "fast_paper_authoritative_bindings"
_CHECKPOINT_TABLE = "paper_loop_checkpoints"


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeTransition:
    next_paper_state: FastPaperRuntimeState
    next_market_positions: tuple[
        FastPaperAuthoritativeMarketPosition,
        ...,
    ]
    execution_policy_fingerprint_sha256: str
    last_processed_source_sequence: int | None
    last_processed_source_event_id: str | None
    last_processed_decision_evidence_fingerprint_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.next_paper_state) is not FastPaperRuntimeState:
            raise ValueError(
                "next_paper_state must be exact FastPaperRuntimeState"
            )
        if (
            not isinstance(self.next_market_positions, tuple)
            or not all(
                type(value) is FastPaperAuthoritativeMarketPosition
                for value in self.next_market_positions
            )
        ):
            raise ValueError(
                "next_market_positions must contain exact FastPaperAuthoritativeMarketPosition values"
            )
        _require_sha256(
            "execution_policy_fingerprint_sha256",
            self.execution_policy_fingerprint_sha256,
        )
        identity = (
            self.last_processed_source_sequence,
            self.last_processed_source_event_id,
            self.last_processed_decision_evidence_fingerprint_sha256,
        )
        if any(value is None for value in identity):
            if any(value is not None for value in identity):
                raise ValueError(
                    "last processed learned identity fields must be all present or all absent"
                )
        else:
            _require_positive_int(
                "last_processed_source_sequence",
                self.last_processed_source_sequence,
            )
            _require_text(
                "last_processed_source_event_id",
                self.last_processed_source_event_id,
            )
            _require_sha256(
                "last_processed_decision_evidence_fingerprint_sha256",
                self.last_processed_decision_evidence_fingerprint_sha256,
            )


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeCommitResult:
    version: str
    checkpoint: FastPaperCheckpointRecord
    runtime_state: FastPaperAuthoritativeRuntimeState

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_AUTHORITATIVE_COMMIT_VERSION:
            raise ValueError(
                "unsupported authoritative Fast PAPER commit version"
            )
        if type(self.checkpoint) is not FastPaperCheckpointRecord:
            raise ValueError(
                "checkpoint must be exact FastPaperCheckpointRecord"
            )
        if (
            type(self.runtime_state)
            is not FastPaperAuthoritativeRuntimeState
        ):
            raise ValueError(
                "runtime_state must be exact FastPaperAuthoritativeRuntimeState"
            )
        if (
            self.runtime_state.paper_checkpoint_sequence
            != self.checkpoint.sequence
            or self.runtime_state.paper_checkpoint_payload_sha256
            != self.checkpoint.payload_sha256
        ):
            raise ValueError(
                "authoritative commit result checkpoint/runtime pair is torn"
            )


def commit_fast_paper_authoritative_transition_atomically(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
    current_checkpoint: FastPaperCheckpointRecord,
    current_runtime_state: FastPaperAuthoritativeRuntimeState,
    transition: FastPaperAuthoritativeTransition,
    *,
    sequence: int,
    created_at_unix_ms: int,
) -> FastPaperAuthoritativeCommitResult:
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
    _require_identity_transition(
        current_runtime_state,
        transition,
    )

    checkpoint_payload = encode_fast_paper_checkpoint(
        binding.fast_run_id,
        sequence,
        transition.next_paper_state,
        created_at_unix_ms,
    )
    checkpoint = decode_fast_paper_checkpoint(checkpoint_payload)
    runtime_state = build_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=transition.next_market_positions,
        execution_policy_fingerprint_sha256=(
            transition.execution_policy_fingerprint_sha256
        ),
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

    database = Path(binding.database_path)
    connection = _connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_storage_tables(connection)
        _require_binding_row(connection, binding)
        _require_current_checkpoint_row(
            connection,
            current_checkpoint,
        )
        _require_current_runtime_row(
            connection,
            binding,
            current_runtime_state,
        )
        _require_target_sequence_free(
            connection,
            binding.fast_run_id,
            sequence,
        )
        _insert_checkpoint_row(
            connection,
            checkpoint,
            checkpoint_payload.decode("utf-8"),
        )
        _insert_runtime_state_row(
            connection,
            binding,
            runtime_state,
            created_at_unix_ms=created_at_unix_ms,
        )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()

    restored_checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        manifest,
        binding,
    )
    restored_runtime = load_latest_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
    )
    if restored_checkpoint != checkpoint:
        raise ValueError(
            "authoritative Fast PAPER checkpoint readback mismatch"
        )
    if restored_runtime != runtime_state:
        raise ValueError(
            "authoritative Fast PAPER runtime readback mismatch"
        )
    return FastPaperAuthoritativeCommitResult(
        version=FAST_PAPER_AUTHORITATIVE_COMMIT_VERSION,
        checkpoint=restored_checkpoint,
        runtime_state=restored_runtime,
    )


def _require_inputs(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
    current_checkpoint: FastPaperCheckpointRecord,
    current_runtime_state: FastPaperAuthoritativeRuntimeState,
    transition: FastPaperAuthoritativeTransition,
    *,
    sequence: int,
    created_at_unix_ms: int,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    verify_fast_paper_runtime_bindings(manifest)
    if type(binding) is not FastPaperAuthoritativeBinding:
        raise ValueError(
            "binding must be exact FastPaperAuthoritativeBinding"
        )
    persisted_binding = load_fast_paper_authoritative_binding(
        manifest,
        fast_run_id=binding.fast_run_id,
        database_path=binding.database_path,
    )
    if persisted_binding != binding:
        raise ValueError(
            "authoritative binding content changed"
        )
    if type(current_checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "current_checkpoint must be exact FastPaperCheckpointRecord"
        )
    if (
        type(current_runtime_state)
        is not FastPaperAuthoritativeRuntimeState
    ):
        raise ValueError(
            "current_runtime_state must be exact FastPaperAuthoritativeRuntimeState"
        )
    if type(transition) is not FastPaperAuthoritativeTransition:
        raise ValueError(
            "transition must be exact FastPaperAuthoritativeTransition"
        )
    _require_non_negative_int("sequence", sequence)
    if sequence != current_checkpoint.sequence + 1:
        raise ValueError(
            "authoritative commit sequence must be exactly current checkpoint sequence + 1"
        )
    _require_non_negative_int(
        "created_at_unix_ms",
        created_at_unix_ms,
    )
    if created_at_unix_ms < transition.next_paper_state.as_of_unix_ms:
        raise ValueError(
            "authoritative commit time cannot precede next PAPER state"
        )
    if (
        transition.next_paper_state.as_of_unix_ms
        < current_checkpoint.state.as_of_unix_ms
    ):
        raise ValueError(
            "authoritative PAPER state time cannot regress"
        )
    if current_checkpoint.run_id != binding.fast_run_id:
        raise ValueError(
            "current checkpoint run_id does not match authoritative binding"
        )
    if (
        current_runtime_state.paper_checkpoint_sequence
        != current_checkpoint.sequence
        or current_runtime_state.paper_checkpoint_payload_sha256
        != current_checkpoint.payload_sha256
    ):
        raise ValueError(
            "current authoritative checkpoint/runtime pair is torn"
        )
    if (
        current_runtime_state.binding_fingerprint_sha256
        != binding.binding_fingerprint_sha256
    ):
        raise ValueError(
            "current authoritative runtime binding fingerprint mismatch"
        )
    if (
        current_runtime_state.execution_policy_fingerprint_sha256
        != binding.execution_policy_fingerprint_sha256
        or transition.execution_policy_fingerprint_sha256
        != binding.execution_policy_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative execution policy fingerprint drift"
        )
    if (
        transition.next_paper_state.fill_policy.version
        != binding.fill_policy_version
    ):
        raise ValueError(
            "authoritative Fast PAPER fill policy version drift"
        )
    if (
        transition.next_paper_state.position_action_policy.version
        != binding.position_action_policy_version
    ):
        raise ValueError(
            "authoritative Fast PAPER position-action policy version drift"
        )
    accounting = validate_fast_paper_accounting(
        transition.next_paper_state
    )
    if accounting.status is AccountingValidationStatus.INVALID:
        raise ValueError(
            "authoritative Fast PAPER next state accounting is INVALID"
        )


def _require_exact_latest_pair(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
    checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperAuthoritativeRuntimeState,
) -> None:
    latest_checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        manifest,
        binding,
    )
    latest_runtime = load_latest_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
    )
    if latest_checkpoint != checkpoint:
        raise ValueError(
            "authoritative commit requires the exact latest durable checkpoint"
        )
    if latest_runtime != runtime_state:
        raise ValueError(
            "authoritative commit requires the exact latest durable runtime state"
        )


def _require_identity_transition(
    current: FastPaperAuthoritativeRuntimeState,
    transition: FastPaperAuthoritativeTransition,
) -> None:
    previous = (
        current.last_processed_source_sequence,
        current.last_processed_source_event_id,
        current.last_processed_decision_evidence_fingerprint_sha256,
    )
    next_identity = (
        transition.last_processed_source_sequence,
        transition.last_processed_source_event_id,
        transition.last_processed_decision_evidence_fingerprint_sha256,
    )
    if previous[0] is None:
        return
    if next_identity[0] is None:
        raise ValueError(
            "authoritative learned source identity cannot be cleared"
        )
    previous_sequence = previous[0]
    next_sequence = next_identity[0]
    assert isinstance(previous_sequence, int)
    assert isinstance(next_sequence, int)
    if next_sequence < previous_sequence:
        raise ValueError(
            "authoritative learned source sequence cannot regress"
        )
    if next_sequence == previous_sequence and next_identity != previous:
        if next_identity[1] != previous[1]:
            raise ValueError(
                "authoritative learned source identity event cannot mutate in place"
            )
        raise ValueError(
            "authoritative learned source identity fingerprint cannot mutate in place"
        )


def _require_storage_tables(
    connection: sqlite3.Connection,
) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    required = {
        _CHECKPOINT_TABLE,
        _BINDING_TABLE,
        FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE,
    }
    if not required.issubset(tables):
        raise ValueError(
            "authoritative Fast PAPER storage schema is incomplete"
        )


def _require_binding_row(
    connection: sqlite3.Connection,
    binding: FastPaperAuthoritativeBinding,
) -> None:
    row = connection.execute(
        f"""
        SELECT binding_fingerprint_sha256
        FROM {_BINDING_TABLE}
        WHERE fast_run_id = ?
        """,
        (binding.fast_run_id,),
    ).fetchone()
    if row != (binding.binding_fingerprint_sha256,):
        raise ValueError(
            "authoritative binding row fingerprint mismatch"
        )


def _require_current_checkpoint_row(
    connection: sqlite3.Connection,
    checkpoint: FastPaperCheckpointRecord,
) -> None:
    row = connection.execute(
        f"""
        SELECT
            sequence,
            checkpoint_schema_version,
            state_as_of_unix_ms,
            created_at_unix_ms,
            payload_sha256,
            payload_json
        FROM {_CHECKPOINT_TABLE}
        WHERE run_id = ?
        ORDER BY sequence DESC
        LIMIT 1
        """,
        (checkpoint.run_id,),
    ).fetchone()
    expected_payload = encode_fast_paper_checkpoint(
        checkpoint.run_id,
        checkpoint.sequence,
        checkpoint.state,
        checkpoint.created_at_unix_ms,
    ).decode("utf-8")
    expected = (
        checkpoint.sequence,
        checkpoint.checkpoint_schema_version,
        checkpoint.state_as_of_unix_ms,
        checkpoint.created_at_unix_ms,
        checkpoint.payload_sha256,
        expected_payload,
    )
    if row != expected:
        raise ValueError(
            "authoritative durable checkpoint changed during commit"
        )


def _require_current_runtime_row(
    connection: sqlite3.Connection,
    binding: FastPaperAuthoritativeBinding,
    state: FastPaperAuthoritativeRuntimeState,
) -> None:
    row = connection.execute(
        f"""
        SELECT
            paper_checkpoint_sequence,
            paper_checkpoint_payload_sha256,
            state_schema_version,
            payload_sha256,
            payload_json
        FROM {FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE}
        WHERE fast_run_id = ?
        ORDER BY paper_checkpoint_sequence DESC
        LIMIT 1
        """,
        (binding.fast_run_id,),
    ).fetchone()
    payload = encode_fast_paper_authoritative_runtime_state(state)
    expected = (
        state.paper_checkpoint_sequence,
        state.paper_checkpoint_payload_sha256,
        state.schema_version,
        __import__("hashlib").sha256(
            payload.encode("utf-8")
        ).hexdigest(),
        payload,
    )
    if row != expected:
        raise ValueError(
            "authoritative durable runtime state changed during commit"
        )


def _require_target_sequence_free(
    connection: sqlite3.Connection,
    fast_run_id: str,
    sequence: int,
) -> None:
    checkpoint_exists = connection.execute(
        f"""
        SELECT 1 FROM {_CHECKPOINT_TABLE}
        WHERE run_id = ? AND sequence = ?
        """,
        (fast_run_id, sequence),
    ).fetchone()
    runtime_exists = connection.execute(
        f"""
        SELECT 1 FROM {FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE}
        WHERE fast_run_id = ? AND paper_checkpoint_sequence = ?
        """,
        (fast_run_id, sequence),
    ).fetchone()
    if checkpoint_exists is not None or runtime_exists is not None:
        raise ValueError(
            "authoritative commit target sequence already exists"
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


def _insert_runtime_state_row(
    connection: sqlite3.Connection,
    binding: FastPaperAuthoritativeBinding,
    state: FastPaperAuthoritativeRuntimeState,
    *,
    created_at_unix_ms: int,
) -> None:
    _runtime_insert(
        connection,
        binding,
        state,
        created_at_unix_ms=created_at_unix_ms,
    )


def _connect(database: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(database, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except sqlite3.Error as exc:
        raise ValueError(
            "authoritative Fast PAPER database connection failed"
        ) from exc


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(
            f"{name} must be non-empty trimmed text"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"{name} must be a positive integer"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            f"{name} must be lowercase SHA-256 hex"
        )
