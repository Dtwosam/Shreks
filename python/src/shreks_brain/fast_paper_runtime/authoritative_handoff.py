from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Mapping

from shreks_brain.fast_paper import create_fast_paper_loop_state
from shreks_brain.paper import PaperLedger, PaperPositionState
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    FAST_PAPER_CHECKPOINT_SCHEMA_VERSION,
    FAST_PAPER_RUNTIME_STATE_VERSION,
    FastPaperCheckpointRecord,
    FastPaperRuntimeState,
    PaperCheckpointRecord,
    decode_fast_paper_checkpoint,
    decode_paper_checkpoint,
    encode_fast_paper_checkpoint,
    encode_paper_checkpoint,
    load_latest_fast_paper_checkpoint,
    load_latest_paper_checkpoint,
    validate_fast_paper_accounting,
    validate_paper_accounting,
)

from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest
from .shadow_execution_input import FastPaperShadowExecutionPolicy
from .authoritative_runtime_state import (
    _ensure_authoritative_runtime_state_table,
    _insert_runtime_state_row,
    _runtime_state_row,
    build_fast_paper_authoritative_runtime_state,
    decode_fast_paper_authoritative_runtime_state,
    load_latest_fast_paper_authoritative_runtime_state,
)


FAST_PAPER_AUTHORITATIVE_BINDING_SCHEMA_NAME = (
    "shreks.fast_paper_authoritative_binding"
)
FAST_PAPER_AUTHORITATIVE_BINDING_SCHEMA_VERSION = 1

_BINDING_TABLE = "fast_paper_authoritative_bindings"
_CHECKPOINT_TABLE = "paper_loop_checkpoints"

_BINDING_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "fast_run_id",
        "legacy_run_id",
        "legacy_checkpoint_sequence",
        "legacy_checkpoint_payload_sha256",
        "legacy_runtime_manifest_fingerprint_sha256",
        "release_source_sha",
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "execution_policy_fingerprint_sha256",
        "risk_policy_version",
        "fill_policy_version",
        "position_action_policy_version",
        "database_path",
        "binding_fingerprint_sha256",
    }
)


class FastPaperAuthoritativeHandoffError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeBinding:
    schema_name: str
    schema_version: int
    fast_run_id: str
    legacy_run_id: str
    legacy_checkpoint_sequence: int
    legacy_checkpoint_payload_sha256: str
    legacy_runtime_manifest_fingerprint_sha256: str
    release_source_sha: str
    manifest_fingerprint_sha256: str
    champion_version: str
    champion_fingerprint_sha256: str
    action_policy_version: int
    execution_policy_fingerprint_sha256: str
    risk_policy_version: str
    fill_policy_version: str
    position_action_policy_version: str
    database_path: str
    binding_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_AUTHORITATIVE_BINDING_SCHEMA_NAME:
            raise ValueError("authoritative binding schema_name is incompatible")
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_AUTHORITATIVE_BINDING_SCHEMA_VERSION
        ):
            raise ValueError(
                "authoritative binding schema_version is incompatible"
            )
        for name in (
            "fast_run_id",
            "legacy_run_id",
            "champion_version",
            "risk_policy_version",
            "fill_policy_version",
            "position_action_policy_version",
            "database_path",
        ):
            _require_text(name, getattr(self, name))
        if self.fast_run_id == self.legacy_run_id:
            raise ValueError(
                "Fast and legacy run IDs must use different checkpoint namespaces"
            )
        _require_non_negative_int(
            "legacy_checkpoint_sequence",
            self.legacy_checkpoint_sequence,
        )
        _require_sha256(
            "legacy_checkpoint_payload_sha256",
            self.legacy_checkpoint_payload_sha256,
        )
        _require_sha256(
            "legacy_runtime_manifest_fingerprint_sha256",
            self.legacy_runtime_manifest_fingerprint_sha256,
        )
        _require_source_sha("release_source_sha", self.release_source_sha)
        for name in (
            "manifest_fingerprint_sha256",
            "champion_fingerprint_sha256",
            "execution_policy_fingerprint_sha256",
            "binding_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _require_positive_int(
            "action_policy_version",
            self.action_policy_version,
        )
        if not Path(self.database_path).is_absolute():
            raise ValueError("database_path must be absolute")
        if _binding_fingerprint(self) != self.binding_fingerprint_sha256:
            raise ValueError(
                "authoritative binding fingerprint mismatch"
            )


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeHandoffResult:
    binding: FastPaperAuthoritativeBinding
    checkpoint: FastPaperCheckpointRecord

    def __post_init__(self) -> None:
        if type(self.binding) is not FastPaperAuthoritativeBinding:
            raise ValueError(
                "binding must be exact FastPaperAuthoritativeBinding"
            )
        if type(self.checkpoint) is not FastPaperCheckpointRecord:
            raise ValueError(
                "checkpoint must be exact FastPaperCheckpointRecord"
            )
        if self.checkpoint.run_id != self.binding.fast_run_id:
            raise ValueError(
                "handoff checkpoint run_id must match authoritative binding"
            )


def build_fast_paper_authoritative_binding(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    legacy_checkpoint: PaperCheckpointRecord,
    *,
    legacy_runtime_manifest_fingerprint_sha256: str,
    fast_run_id: str,
    database_path: str | Path,
) -> FastPaperAuthoritativeBinding:
    _require_manifest_and_policy(manifest, execution_policy)
    _require_legacy_checkpoint(legacy_checkpoint)
    _require_sha256(
        "legacy_runtime_manifest_fingerprint_sha256",
        legacy_runtime_manifest_fingerprint_sha256,
    )
    _require_text("fast_run_id", fast_run_id)
    if fast_run_id == legacy_checkpoint.run_id:
        raise FastPaperAuthoritativeHandoffError(
            "Fast and legacy run IDs must use different checkpoint namespaces"
        )
    database = _authoritative_database_path(manifest, database_path)

    values: dict[str, object] = {
        "schema_name": FAST_PAPER_AUTHORITATIVE_BINDING_SCHEMA_NAME,
        "schema_version": FAST_PAPER_AUTHORITATIVE_BINDING_SCHEMA_VERSION,
        "fast_run_id": fast_run_id,
        "legacy_run_id": legacy_checkpoint.run_id,
        "legacy_checkpoint_sequence": legacy_checkpoint.sequence,
        "legacy_checkpoint_payload_sha256": legacy_checkpoint.payload_sha256,
        "legacy_runtime_manifest_fingerprint_sha256": (
            legacy_runtime_manifest_fingerprint_sha256
        ),
        "release_source_sha": manifest.release_source_sha,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": manifest.action_policy.version,
        "execution_policy_fingerprint_sha256": (
            execution_policy.policy_fingerprint_sha256
        ),
        "risk_policy_version": manifest.risk_policy_version,
        "fill_policy_version": manifest.fill_policy_version,
        "position_action_policy_version": (
            manifest.position_action_policy_version
        ),
        "database_path": str(database),
    }
    fingerprint = hashlib.sha256(
        _canonical(values).encode("utf-8")
    ).hexdigest()
    try:
        return FastPaperAuthoritativeBinding(
            **values,
            binding_fingerprint_sha256=fingerprint,
        )
    except (TypeError, ValueError) as exc:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER binding is invalid"
        ) from exc


def build_initial_fast_paper_authoritative_state(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    legacy_checkpoint: PaperCheckpointRecord,
) -> FastPaperRuntimeState:
    _require_manifest_and_policy(manifest, execution_policy)
    _require_legacy_checkpoint(legacy_checkpoint)
    source = legacy_checkpoint.state

    open_positions = tuple(
        position
        for position in source.ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    if open_positions:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative handoff requires a flat legacy ledger with zero OPEN positions"
        )
    if source.pending_entry is not None:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative handoff requires no legacy pending entry"
        )
    if any(
        managed.pending_exit is not None
        for managed in source.managed_positions
    ):
        raise FastPaperAuthoritativeHandoffError(
            "authoritative handoff requires no legacy pending exit"
        )
    if source.managed_positions:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative handoff flat ledger cannot retain managed positions"
        )

    legacy_accounting = validate_paper_accounting(source)
    if legacy_accounting.status is not AccountingValidationStatus.RECONCILED:
        raise FastPaperAuthoritativeHandoffError(
            "legacy PAPER accounting must be RECONCILED before handoff"
        )

    ledger: PaperLedger = source.ledger
    state = FastPaperRuntimeState(
        version=FAST_PAPER_RUNTIME_STATE_VERSION,
        as_of_unix_ms=source.last_cycle_at_unix_ms,
        event_loop_state=create_fast_paper_loop_state(),
        ledger=ledger,
        fill_policy=execution_policy.fill_policy,
        position_action_policy=execution_policy.position_action_policy,
        pending_buy=None,
        position_action_states=(),
    )
    fast_accounting = validate_fast_paper_accounting(state)
    if fast_accounting.status is not AccountingValidationStatus.RECONCILED:
        raise FastPaperAuthoritativeHandoffError(
            "initial Fast PAPER accounting is not RECONCILED"
        )
    if fast_accounting != legacy_accounting:
        raise FastPaperAuthoritativeHandoffError(
            "Fast PAPER handoff accounting differs from legacy source accounting"
        )
    return state


def initialize_fast_paper_authoritative_handoff(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    legacy_checkpoint: PaperCheckpointRecord,
    *,
    legacy_runtime_manifest_fingerprint_sha256: str,
    fast_run_id: str,
    database_path: str | Path,
    created_at_unix_ms: int,
) -> FastPaperAuthoritativeHandoffResult:
    _require_non_negative_int(
        "created_at_unix_ms",
        created_at_unix_ms,
    )
    binding = build_fast_paper_authoritative_binding(
        manifest,
        execution_policy,
        legacy_checkpoint,
        legacy_runtime_manifest_fingerprint_sha256=(
            legacy_runtime_manifest_fingerprint_sha256
        ),
        fast_run_id=fast_run_id,
        database_path=database_path,
    )
    state = build_initial_fast_paper_authoritative_state(
        manifest,
        execution_policy,
        legacy_checkpoint,
    )
    if created_at_unix_ms < state.as_of_unix_ms:
        raise FastPaperAuthoritativeHandoffError(
            "handoff creation time cannot precede initial Fast PAPER state"
        )

    checkpoint_payload = encode_fast_paper_checkpoint(
        fast_run_id,
        0,
        state,
        created_at_unix_ms,
    )
    checkpoint = decode_fast_paper_checkpoint(checkpoint_payload)
    checkpoint_json = checkpoint_payload.decode("utf-8")
    binding_json = _canonical(_binding_document(binding))
    runtime_state = build_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
        execution_policy_fingerprint_sha256=(
            execution_policy.policy_fingerprint_sha256
        ),
    )
    expected_runtime_row = _runtime_state_row(
        runtime_state,
        created_at_unix_ms=created_at_unix_ms,
    )

    database = Path(binding.database_path)
    connection = _connect(database)
    idempotent = False
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_checkpoint_table(connection)
        _require_exact_latest_legacy_checkpoint(
            connection,
            legacy_checkpoint,
        )
        _ensure_binding_table(connection)
        _ensure_authoritative_runtime_state_table(connection)

        existing_binding = connection.execute(
            f"""
            SELECT binding_fingerprint_sha256, binding_json
            FROM {_BINDING_TABLE}
            WHERE fast_run_id = ?
            """,
            (fast_run_id,),
        ).fetchone()
        existing_checkpoints = connection.execute(
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
            ORDER BY sequence ASC
            """,
            (fast_run_id,),
        ).fetchall()
        existing_runtime_states = connection.execute(
            """
            SELECT
                paper_checkpoint_sequence,
                paper_checkpoint_payload_sha256,
                state_schema_version,
                created_at_unix_ms,
                payload_sha256,
                payload_json
            FROM fast_paper_authoritative_runtime_states
            WHERE fast_run_id = ?
            ORDER BY paper_checkpoint_sequence ASC
            """,
            (fast_run_id,),
        ).fetchall()

        expected_binding = (
            binding.binding_fingerprint_sha256,
            binding_json,
        )
        expected_checkpoint = (
            checkpoint.sequence,
            checkpoint.checkpoint_schema_version,
            checkpoint.state_as_of_unix_ms,
            checkpoint.created_at_unix_ms,
            checkpoint.payload_sha256,
            checkpoint_json,
        )
        if (
            existing_binding is not None
            or existing_checkpoints
            or existing_runtime_states
        ):
            if (
                existing_binding == expected_binding
                and existing_checkpoints == [expected_checkpoint]
                and existing_runtime_states == [expected_runtime_row]
            ):
                connection.rollback()
                idempotent = True
            else:
                connection.rollback()
                raise FastPaperAuthoritativeHandoffError(
                    "Fast PAPER authoritative target namespace collision"
                )
        else:
            connection.execute(
                f"""
                INSERT INTO {_BINDING_TABLE}(
                    fast_run_id,
                    binding_fingerprint_sha256,
                    binding_json
                ) VALUES (?, ?, ?)
                """,
                (
                    fast_run_id,
                    binding.binding_fingerprint_sha256,
                    binding_json,
                ),
            )
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
                    checkpoint_json,
                ),
            )
            _insert_runtime_state_row(
                connection,
                binding,
                runtime_state,
                created_at_unix_ms=created_at_unix_ms,
            )
            connection.commit()
    except FastPaperAuthoritativeHandoffError:
        if connection.in_transaction:
            connection.rollback()
        raise
    except (sqlite3.Error, UnicodeError, ValueError) as exc:
        if connection.in_transaction:
            connection.rollback()
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER handoff persistence failed"
        ) from exc
    finally:
        connection.close()

    restored_binding = load_fast_paper_authoritative_binding(
        manifest,
        fast_run_id=fast_run_id,
        database_path=database,
    )
    restored_checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        manifest,
        restored_binding,
    )
    if restored_binding != binding:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding readback mismatch"
        )
    if restored_checkpoint != checkpoint:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER checkpoint readback mismatch"
        )
    restored_runtime_state = (
        load_latest_fast_paper_authoritative_runtime_state(
            manifest,
            restored_binding,
        )
    )
    if restored_runtime_state != runtime_state:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER runtime-state readback mismatch"
        )
    if idempotent and (
        restored_checkpoint.sequence != 0
        or restored_checkpoint.payload_sha256 != checkpoint.payload_sha256
    ):
        raise FastPaperAuthoritativeHandoffError(
            "idempotent authoritative handoff readback changed"
        )
    return FastPaperAuthoritativeHandoffResult(
        binding=restored_binding,
        checkpoint=restored_checkpoint,
    )


def reseed_pristine_fast_paper_authoritative_handoff(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    legacy_checkpoint: PaperCheckpointRecord,
    *,
    legacy_runtime_manifest_fingerprint_sha256: str,
    fast_run_id: str,
    database_path: str | Path,
    created_at_unix_ms: int,
) -> FastPaperAuthoritativeHandoffResult:
    """Atomically reseed an untouched Fast namespace from the final legacy checkpoint."""

    _require_non_negative_int(
        "created_at_unix_ms",
        created_at_unix_ms,
    )
    desired_binding = build_fast_paper_authoritative_binding(
        manifest,
        execution_policy,
        legacy_checkpoint,
        legacy_runtime_manifest_fingerprint_sha256=(
            legacy_runtime_manifest_fingerprint_sha256
        ),
        fast_run_id=fast_run_id,
        database_path=database_path,
    )
    desired_state = build_initial_fast_paper_authoritative_state(
        manifest,
        execution_policy,
        legacy_checkpoint,
    )
    if created_at_unix_ms < desired_state.as_of_unix_ms:
        raise FastPaperAuthoritativeHandoffError(
            "handoff reseed time cannot precede final legacy state"
        )
    desired_checkpoint_payload = encode_fast_paper_checkpoint(
        fast_run_id,
        0,
        desired_state,
        created_at_unix_ms,
    )
    desired_checkpoint = decode_fast_paper_checkpoint(
        desired_checkpoint_payload
    )
    desired_checkpoint_json = desired_checkpoint_payload.decode("utf-8")
    desired_binding_json = _canonical(
        _binding_document(desired_binding)
    )
    desired_runtime_state = build_fast_paper_authoritative_runtime_state(
        manifest,
        desired_binding,
        desired_checkpoint,
        market_positions=(),
        execution_policy_fingerprint_sha256=(
            execution_policy.policy_fingerprint_sha256
        ),
    )
    desired_runtime_row = _runtime_state_row(
        desired_runtime_state,
        created_at_unix_ms=created_at_unix_ms,
    )
    desired_binding_row = (
        desired_binding.binding_fingerprint_sha256,
        desired_binding_json,
    )
    desired_checkpoint_row = (
        desired_checkpoint.sequence,
        desired_checkpoint.checkpoint_schema_version,
        desired_checkpoint.state_as_of_unix_ms,
        desired_checkpoint.created_at_unix_ms,
        desired_checkpoint.payload_sha256,
        desired_checkpoint_json,
    )

    database = Path(desired_binding.database_path)
    connection = _connect(database)
    idempotent = False
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_checkpoint_table(connection)
        _ensure_binding_table(connection)
        _ensure_authoritative_runtime_state_table(connection)
        _require_exact_latest_legacy_checkpoint(
            connection,
            legacy_checkpoint,
        )

        binding_row = connection.execute(
            f"""
            SELECT binding_fingerprint_sha256, binding_json
            FROM {_BINDING_TABLE}
            WHERE fast_run_id = ?
            """,
            (fast_run_id,),
        ).fetchone()
        checkpoint_rows = connection.execute(
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
            ORDER BY sequence ASC
            """,
            (fast_run_id,),
        ).fetchall()
        runtime_rows = connection.execute(
            """
            SELECT
                paper_checkpoint_sequence,
                paper_checkpoint_payload_sha256,
                state_schema_version,
                created_at_unix_ms,
                payload_sha256,
                payload_json
            FROM fast_paper_authoritative_runtime_states
            WHERE fast_run_id = ?
            ORDER BY paper_checkpoint_sequence ASC
            """,
            (fast_run_id,),
        ).fetchall()

        if (
            binding_row is None
            or len(checkpoint_rows) != 1
            or len(runtime_rows) != 1
        ):
            raise FastPaperAuthoritativeHandoffError(
                "Fast PAPER authoritative namespace is not exactly pristine"
            )

        existing_binding_fingerprint, existing_binding_json = binding_row
        if (
            not isinstance(existing_binding_fingerprint, str)
            or not isinstance(existing_binding_json, str)
        ):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative binding row is malformed"
            )
        existing_binding = _decode_binding(existing_binding_json)
        if (
            existing_binding.binding_fingerprint_sha256
            != existing_binding_fingerprint
        ):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative binding row fingerprint mismatch"
            )
        _require_binding_manifest(manifest, existing_binding)
        if (
            existing_binding.fast_run_id != fast_run_id
            or existing_binding.legacy_run_id != legacy_checkpoint.run_id
            or existing_binding.execution_policy_fingerprint_sha256
            != execution_policy.policy_fingerprint_sha256
            or existing_binding.legacy_runtime_manifest_fingerprint_sha256
            != legacy_runtime_manifest_fingerprint_sha256
        ):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative binding identity is incompatible with final reseed"
            )

        old_legacy_row = connection.execute(
            f"""
            SELECT
                sequence,
                checkpoint_schema_version,
                state_as_of_unix_ms,
                created_at_unix_ms,
                payload_sha256,
                payload_json
            FROM {_CHECKPOINT_TABLE}
            WHERE run_id = ? AND sequence = ?
            """,
            (
                existing_binding.legacy_run_id,
                existing_binding.legacy_checkpoint_sequence,
            ),
        ).fetchone()
        if old_legacy_row is None:
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative handoff source checkpoint is missing"
            )
        old_payload = old_legacy_row[5]
        if not isinstance(old_payload, str):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative handoff source payload is malformed"
            )
        old_legacy_checkpoint = decode_paper_checkpoint(
            old_payload.encode("utf-8")
        )
        expected_old_legacy_row = (
            old_legacy_checkpoint.sequence,
            old_legacy_checkpoint.checkpoint_schema_version,
            old_legacy_checkpoint.state_as_of_unix_ms,
            old_legacy_checkpoint.created_at_unix_ms,
            old_legacy_checkpoint.payload_sha256,
            old_payload,
        )
        if (
            old_legacy_row != expected_old_legacy_row
            or old_legacy_checkpoint.run_id
            != existing_binding.legacy_run_id
            or old_legacy_checkpoint.payload_sha256
            != existing_binding.legacy_checkpoint_payload_sha256
        ):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative handoff source checkpoint is not authentic"
            )

        checkpoint_row = checkpoint_rows[0]
        checkpoint_payload = checkpoint_row[5]
        if not isinstance(checkpoint_payload, str):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative checkpoint payload is malformed"
            )
        existing_checkpoint = decode_fast_paper_checkpoint(
            checkpoint_payload.encode("utf-8")
        )
        expected_checkpoint_row = (
            existing_checkpoint.sequence,
            existing_checkpoint.checkpoint_schema_version,
            existing_checkpoint.state_as_of_unix_ms,
            existing_checkpoint.created_at_unix_ms,
            existing_checkpoint.payload_sha256,
            checkpoint_payload,
        )
        if (
            checkpoint_row != expected_checkpoint_row
            or existing_checkpoint.run_id != fast_run_id
            or existing_checkpoint.sequence != 0
            or existing_checkpoint.state
            != build_initial_fast_paper_authoritative_state(
                manifest,
                execution_policy,
                old_legacy_checkpoint,
            )
        ):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative checkpoint is not an untouched handoff"
            )

        runtime_row = runtime_rows[0]
        runtime_payload = runtime_row[5]
        if not isinstance(runtime_payload, str):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative runtime-state payload is malformed"
            )
        existing_runtime_state = (
            decode_fast_paper_authoritative_runtime_state(
                runtime_payload
            )
        )
        if (
            runtime_row
            != _runtime_state_row(
                existing_runtime_state,
                created_at_unix_ms=runtime_row[3],
            )
            or existing_runtime_state
            != build_fast_paper_authoritative_runtime_state(
                manifest,
                existing_binding,
                existing_checkpoint,
                market_positions=(),
                execution_policy_fingerprint_sha256=(
                    execution_policy.policy_fingerprint_sha256
                ),
            )
        ):
            raise FastPaperAuthoritativeHandoffError(
                "existing authoritative runtime state is not pristine"
            )

        if (
            binding_row == desired_binding_row
            and checkpoint_row == desired_checkpoint_row
            and runtime_row == desired_runtime_row
        ):
            connection.rollback()
            idempotent = True
        else:
            connection.execute(
                """
                DELETE FROM fast_paper_authoritative_runtime_states
                WHERE fast_run_id = ?
                """,
                (fast_run_id,),
            )
            connection.execute(
                f"""
                DELETE FROM {_CHECKPOINT_TABLE}
                WHERE run_id = ?
                """,
                (fast_run_id,),
            )
            connection.execute(
                f"""
                DELETE FROM {_BINDING_TABLE}
                WHERE fast_run_id = ?
                """,
                (fast_run_id,),
            )
            connection.execute(
                f"""
                INSERT INTO {_BINDING_TABLE}(
                    fast_run_id,
                    binding_fingerprint_sha256,
                    binding_json
                ) VALUES (?, ?, ?)
                """,
                (
                    fast_run_id,
                    desired_binding.binding_fingerprint_sha256,
                    desired_binding_json,
                ),
            )
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
                    desired_checkpoint.run_id,
                    desired_checkpoint.sequence,
                    desired_checkpoint.checkpoint_schema_version,
                    desired_checkpoint.state_as_of_unix_ms,
                    desired_checkpoint.created_at_unix_ms,
                    desired_checkpoint.payload_sha256,
                    desired_checkpoint_json,
                ),
            )
            _insert_runtime_state_row(
                connection,
                desired_binding,
                desired_runtime_state,
                created_at_unix_ms=created_at_unix_ms,
            )
            _require_exact_latest_legacy_checkpoint(
                connection,
                legacy_checkpoint,
            )
            connection.commit()
    except FastPaperAuthoritativeHandoffError:
        if connection.in_transaction:
            connection.rollback()
        raise
    except (sqlite3.Error, UnicodeError, ValueError) as exc:
        if connection.in_transaction:
            connection.rollback()
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER pristine reseed failed"
        ) from exc
    finally:
        connection.close()

    restored_binding = load_fast_paper_authoritative_binding(
        manifest,
        fast_run_id=fast_run_id,
        database_path=database,
    )
    restored_checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        manifest,
        restored_binding,
    )
    restored_runtime_state = (
        load_latest_fast_paper_authoritative_runtime_state(
            manifest,
            restored_binding,
        )
    )
    if (
        restored_binding != desired_binding
        or restored_checkpoint != desired_checkpoint
        or restored_runtime_state != desired_runtime_state
    ):
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER pristine reseed readback mismatch"
        )
    if idempotent and (
        restored_binding.binding_fingerprint_sha256
        != desired_binding.binding_fingerprint_sha256
    ):
        raise FastPaperAuthoritativeHandoffError(
            "idempotent authoritative reseed identity changed"
        )
    return FastPaperAuthoritativeHandoffResult(
        binding=restored_binding,
        checkpoint=restored_checkpoint,
    )


def load_fast_paper_authoritative_binding(
    manifest: FastPaperRuntimeManifest,
    *,
    fast_run_id: str,
    database_path: str | Path,
) -> FastPaperAuthoritativeBinding:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise FastPaperAuthoritativeHandoffError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    try:
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise FastPaperAuthoritativeHandoffError(
            "Fast PAPER runtime manifest authentication failed"
        ) from exc
    _require_text("fast_run_id", fast_run_id)
    database = _authoritative_database_path(manifest, database_path)
    connection = _connect(database)
    try:
        row = connection.execute(
            f"""
            SELECT binding_fingerprint_sha256, binding_json
            FROM {_BINDING_TABLE}
            WHERE fast_run_id = ?
            """,
            (fast_run_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding table is missing or unreadable"
        ) from exc
    finally:
        connection.close()
    if row is None:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER binding is missing"
        )
    fingerprint, payload = row
    _require_sha256(
        "stored binding fingerprint",
        fingerprint,
    )
    if not isinstance(payload, str):
        raise FastPaperAuthoritativeHandoffError(
            "stored authoritative binding payload must be text"
        )
    binding = _decode_binding(payload)
    if binding.binding_fingerprint_sha256 != fingerprint:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding row fingerprint mismatch"
        )
    if binding.fast_run_id != fast_run_id:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding run_id mismatch"
        )
    _require_binding_manifest(manifest, binding)
    return binding


def load_latest_fast_paper_authoritative_checkpoint(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
) -> FastPaperCheckpointRecord:
    if type(binding) is not FastPaperAuthoritativeBinding:
        raise FastPaperAuthoritativeHandoffError(
            "binding must be exact FastPaperAuthoritativeBinding"
        )
    _require_binding_manifest(manifest, binding)
    persisted = load_fast_paper_authoritative_binding(
        manifest,
        fast_run_id=binding.fast_run_id,
        database_path=binding.database_path,
    )
    if persisted != binding:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding content changed"
        )
    try:
        checkpoint = load_latest_fast_paper_checkpoint(
            binding.database_path,
            binding.fast_run_id,
        )
    except Exception as exc:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER checkpoint load failed"
        ) from exc
    if checkpoint is None:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative Fast PAPER checkpoint is missing"
        )
    if checkpoint.state.fill_policy.version != binding.fill_policy_version:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative checkpoint fill policy version drift"
        )
    if (
        checkpoint.state.position_action_policy.version
        != binding.position_action_policy_version
    ):
        raise FastPaperAuthoritativeHandoffError(
            "authoritative checkpoint position-action policy version drift"
        )
    return checkpoint


def _require_manifest_and_policy(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise FastPaperAuthoritativeHandoffError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    try:
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise FastPaperAuthoritativeHandoffError(
            "Fast PAPER runtime manifest authentication failed"
        ) from exc
    if type(execution_policy) is not FastPaperShadowExecutionPolicy:
        raise FastPaperAuthoritativeHandoffError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    if (
        execution_policy.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
        or execution_policy.risk_policy.version
        != manifest.risk_policy_version
        or execution_policy.fill_policy.version
        != manifest.fill_policy_version
        or execution_policy.position_action_policy.version
        != manifest.position_action_policy_version
    ):
        raise FastPaperAuthoritativeHandoffError(
            "execution policy does not match Fast PAPER runtime manifest"
        )


def _require_legacy_checkpoint(
    checkpoint: PaperCheckpointRecord,
) -> None:
    if type(checkpoint) is not PaperCheckpointRecord:
        raise FastPaperAuthoritativeHandoffError(
            "legacy_checkpoint must be exact PaperCheckpointRecord"
        )
    _require_text("legacy run_id", checkpoint.run_id)
    _require_non_negative_int(
        "legacy checkpoint sequence",
        checkpoint.sequence,
    )
    _require_sha256(
        "legacy checkpoint payload SHA-256",
        checkpoint.payload_sha256,
    )


def _require_binding_manifest(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
) -> None:
    try:
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise FastPaperAuthoritativeHandoffError(
            "Fast PAPER runtime manifest authentication failed"
        ) from exc
    database = _authoritative_database_path(
        manifest,
        binding.database_path,
    )
    expected = {
        "release_source_sha": manifest.release_source_sha,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": manifest.action_policy.version,
        "risk_policy_version": manifest.risk_policy_version,
        "fill_policy_version": manifest.fill_policy_version,
        "position_action_policy_version": (
            manifest.position_action_policy_version
        ),
        "database_path": str(database),
    }
    for name, value in expected.items():
        if getattr(binding, name) != value:
            raise FastPaperAuthoritativeHandoffError(
                f"authoritative binding {name} does not match runtime manifest"
            )


def _authoritative_database_path(
    manifest: FastPaperRuntimeManifest,
    value: str | Path,
) -> Path:
    if not isinstance(value, (str, Path)):
        raise FastPaperAuthoritativeHandoffError(
            "authoritative database path must be explicit"
        )
    if isinstance(value, str) and not value.strip():
        raise FastPaperAuthoritativeHandoffError(
            "authoritative database path must be explicit"
        )
    raw = Path(value).expanduser()
    expected = Path(manifest.observer_database_path).expanduser()
    if raw.is_symlink() or expected.is_symlink():
        raise FastPaperAuthoritativeHandoffError(
            "authoritative observer database must not be a symlink"
        )
    if not raw.is_file() or not expected.is_file():
        raise FastPaperAuthoritativeHandoffError(
            "authoritative observer database must be an existing regular file"
        )
    try:
        if not raw.samefile(expected):
            raise FastPaperAuthoritativeHandoffError(
                "database path is not the manifest authoritative observer database"
            )
        return expected.resolve(strict=True)
    except OSError as exc:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative observer database identity cannot be resolved"
        ) from exc


def _require_exact_latest_legacy_checkpoint(
    connection: sqlite3.Connection,
    checkpoint: PaperCheckpointRecord,
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
    if row is None:
        raise FastPaperAuthoritativeHandoffError(
            "legacy source checkpoint is missing"
        )
    expected_payload = encode_paper_checkpoint(
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
        raise FastPaperAuthoritativeHandoffError(
            "legacy source checkpoint is stale or no longer the exact latest checkpoint"
        )


def _ensure_binding_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_BINDING_TABLE} (
            fast_run_id TEXT PRIMARY KEY,
            binding_fingerprint_sha256 TEXT NOT NULL
                CHECK (length(binding_fingerprint_sha256) = 64),
            binding_json TEXT NOT NULL
        )
        """
    )


def _require_checkpoint_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (_CHECKPOINT_TABLE,),
    ).fetchone()
    if row is None:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative database is missing paper_loop_checkpoints"
        )


def _binding_document(
    binding: FastPaperAuthoritativeBinding,
) -> dict[str, object]:
    document = {
        "schema_name": binding.schema_name,
        "schema_version": binding.schema_version,
        "fast_run_id": binding.fast_run_id,
        "legacy_run_id": binding.legacy_run_id,
        "legacy_checkpoint_sequence": binding.legacy_checkpoint_sequence,
        "legacy_checkpoint_payload_sha256": (
            binding.legacy_checkpoint_payload_sha256
        ),
        "legacy_runtime_manifest_fingerprint_sha256": (
            binding.legacy_runtime_manifest_fingerprint_sha256
        ),
        "release_source_sha": binding.release_source_sha,
        "manifest_fingerprint_sha256": (
            binding.manifest_fingerprint_sha256
        ),
        "champion_version": binding.champion_version,
        "champion_fingerprint_sha256": (
            binding.champion_fingerprint_sha256
        ),
        "action_policy_version": binding.action_policy_version,
        "execution_policy_fingerprint_sha256": (
            binding.execution_policy_fingerprint_sha256
        ),
        "risk_policy_version": binding.risk_policy_version,
        "fill_policy_version": binding.fill_policy_version,
        "position_action_policy_version": (
            binding.position_action_policy_version
        ),
        "database_path": binding.database_path,
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
    }
    if frozenset(document) != _BINDING_FIELDS:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding document field set is incomplete"
        )
    return document


def _binding_fingerprint(
    binding: FastPaperAuthoritativeBinding,
) -> str:
    material = _binding_document_unchecked(binding)
    material.pop("binding_fingerprint_sha256")
    return hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()


def _binding_document_unchecked(
    binding: FastPaperAuthoritativeBinding,
) -> dict[str, object]:
    return {
        "schema_name": binding.schema_name,
        "schema_version": binding.schema_version,
        "fast_run_id": binding.fast_run_id,
        "legacy_run_id": binding.legacy_run_id,
        "legacy_checkpoint_sequence": binding.legacy_checkpoint_sequence,
        "legacy_checkpoint_payload_sha256": (
            binding.legacy_checkpoint_payload_sha256
        ),
        "legacy_runtime_manifest_fingerprint_sha256": (
            binding.legacy_runtime_manifest_fingerprint_sha256
        ),
        "release_source_sha": binding.release_source_sha,
        "manifest_fingerprint_sha256": (
            binding.manifest_fingerprint_sha256
        ),
        "champion_version": binding.champion_version,
        "champion_fingerprint_sha256": (
            binding.champion_fingerprint_sha256
        ),
        "action_policy_version": binding.action_policy_version,
        "execution_policy_fingerprint_sha256": (
            binding.execution_policy_fingerprint_sha256
        ),
        "risk_policy_version": binding.risk_policy_version,
        "fill_policy_version": binding.fill_policy_version,
        "position_action_policy_version": (
            binding.position_action_policy_version
        ),
        "database_path": binding.database_path,
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
    }


def _decode_binding(payload: str) -> FastPaperAuthoritativeBinding:
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding JSON is invalid"
        ) from exc
    if not isinstance(document, dict):
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding must be a JSON object"
        )
    if frozenset(document) != _BINDING_FIELDS:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding has unknown or missing fields"
        )
    if payload != _canonical(document):
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding must use canonical JSON"
        )
    try:
        return FastPaperAuthoritativeBinding(**document)
    except (TypeError, ValueError) as exc:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative binding content is incompatible"
        ) from exc


def _connect(database: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(database, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except sqlite3.Error as exc:
        raise FastPaperAuthoritativeHandoffError(
            "authoritative database connection failed"
        ) from exc


def _canonical(value: Mapping[str, object] | object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FastPaperAuthoritativeHandoffError(
            f"{name} must be non-empty trimmed text"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperAuthoritativeHandoffError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FastPaperAuthoritativeHandoffError(
            f"{name} must be a positive integer"
        )


def _require_source_sha(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FastPaperAuthoritativeHandoffError(
            f"{name} must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FastPaperAuthoritativeHandoffError(
            f"{name} must be lowercase SHA-256 hex"
        )
