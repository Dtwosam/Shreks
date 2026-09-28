from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Mapping

from shreks_brain.paper_validation import (
    FastPaperCheckpointRecord,
    decode_fast_paper_checkpoint,
    encode_fast_paper_checkpoint,
    load_latest_paper_checkpoint,
)

from .authoritative_handoff import (
    FastPaperAuthoritativeBinding,
    FastPaperAuthoritativeHandoffError,
    _BINDING_TABLE,
    _CHECKPOINT_TABLE,
    _binding_document,
    _canonical,
    _connect,
    _ensure_binding_table,
    _require_checkpoint_table,
    build_fast_paper_authoritative_binding,
    load_fast_paper_authoritative_binding,
    load_latest_fast_paper_authoritative_checkpoint,
)
from .authoritative_runtime_state import (
    FastPaperAuthoritativeRuntimeState,
    _ensure_authoritative_runtime_state_table,
    _insert_runtime_state_row,
    _runtime_state_row,
    build_fast_paper_authoritative_runtime_state,
    load_latest_fast_paper_authoritative_runtime_state,
)
from .codec import (
    build_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
)
from .models import (
    FastPaperRuntimeManifest,
    FastPaperRuntimeState,
)
from .shadow_execution_input import FastPaperShadowExecutionPolicy


FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_SCHEMA_NAME = (
    "shreks.fast_paper_authoritative_release_handoff"
)
FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_SCHEMA_VERSION = 1
FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_TABLE = (
    "fast_paper_authoritative_release_handoffs"
)


class FastPaperAuthoritativeReleaseHandoffError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeReleaseHandoff:
    schema_name: str
    schema_version: int
    source_run_id: str
    source_release_source_sha: str
    source_manifest_fingerprint_sha256: str
    source_binding_fingerprint_sha256: str
    source_checkpoint_sequence: int
    source_checkpoint_payload_sha256: str
    source_runtime_state_fingerprint_sha256: str
    source_decision_state_fingerprint_sha256: str
    target_run_id: str
    target_release_source_sha: str
    target_manifest_fingerprint_sha256: str
    target_binding_fingerprint_sha256: str
    target_checkpoint_sequence: int
    target_checkpoint_payload_sha256: str
    target_runtime_state_fingerprint_sha256: str
    target_decision_state_fingerprint_sha256: str
    created_at_unix_ms: int
    handoff_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_SCHEMA_NAME
        ):
            raise ValueError(
                "release handoff schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_SCHEMA_VERSION
        ):
            raise ValueError(
                "release handoff schema_version is incompatible"
            )
        for name in ("source_run_id", "target_run_id"):
            _require_text(name, getattr(self, name))
        if self.source_run_id == self.target_run_id:
            raise ValueError(
                "release handoff source and target run IDs must differ"
            )
        for name in (
            "source_release_source_sha",
            "target_release_source_sha",
        ):
            _require_source_sha(name, getattr(self, name))
        if (
            self.source_release_source_sha
            == self.target_release_source_sha
        ):
            raise ValueError(
                "release handoff requires a distinct target release"
            )
        for name in (
            "source_manifest_fingerprint_sha256",
            "source_binding_fingerprint_sha256",
            "source_checkpoint_payload_sha256",
            "source_runtime_state_fingerprint_sha256",
            "source_decision_state_fingerprint_sha256",
            "target_manifest_fingerprint_sha256",
            "target_binding_fingerprint_sha256",
            "target_checkpoint_payload_sha256",
            "target_runtime_state_fingerprint_sha256",
            "target_decision_state_fingerprint_sha256",
            "handoff_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _require_non_negative_int(
            "source_checkpoint_sequence",
            self.source_checkpoint_sequence,
        )
        if self.target_checkpoint_sequence != 0:
            raise ValueError(
                "release handoff target checkpoint sequence must be zero"
            )
        _require_non_negative_int(
            "created_at_unix_ms",
            self.created_at_unix_ms,
        )
        if (
            _handoff_fingerprint(self)
            != self.handoff_fingerprint_sha256
        ):
            raise ValueError(
                "release handoff fingerprint mismatch"
            )


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeReleaseHandoffResult:
    handoff: FastPaperAuthoritativeReleaseHandoff
    binding: FastPaperAuthoritativeBinding
    checkpoint: FastPaperCheckpointRecord
    runtime_state: FastPaperAuthoritativeRuntimeState
    decision_state: FastPaperRuntimeState

    def __post_init__(self) -> None:
        if (
            type(self.handoff)
            is not FastPaperAuthoritativeReleaseHandoff
        ):
            raise ValueError(
                "handoff must be exact FastPaperAuthoritativeReleaseHandoff"
            )
        if type(self.binding) is not FastPaperAuthoritativeBinding:
            raise ValueError(
                "binding must be exact FastPaperAuthoritativeBinding"
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
        if type(self.decision_state) is not FastPaperRuntimeState:
            raise ValueError(
                "decision_state must be exact FastPaperRuntimeState"
            )
        if (
            self.binding.fast_run_id != self.handoff.target_run_id
            or self.checkpoint.run_id != self.handoff.target_run_id
        ):
            raise ValueError(
                "release handoff result target run identity mismatch"
            )


def initialize_fast_paper_authoritative_release_handoff(
    source_manifest: FastPaperRuntimeManifest,
    target_manifest: FastPaperRuntimeManifest,
    source_binding: FastPaperAuthoritativeBinding,
    target_execution_policy: FastPaperShadowExecutionPolicy,
    source_decision_state: FastPaperRuntimeState,
    *,
    target_fast_run_id: str,
    database_path: str | Path,
    created_at_unix_ms: int,
) -> FastPaperAuthoritativeReleaseHandoffResult:
    """Append one release-bound Fast successor namespace without economic action."""

    _require_inputs(
        source_manifest,
        target_manifest,
        source_binding,
        target_execution_policy,
        source_decision_state,
        target_fast_run_id=target_fast_run_id,
        created_at_unix_ms=created_at_unix_ms,
    )
    _require_release_compatibility(
        source_manifest,
        target_manifest,
    )

    persisted_source_binding = load_fast_paper_authoritative_binding(
        source_manifest,
        fast_run_id=source_binding.fast_run_id,
        database_path=database_path,
    )
    if persisted_source_binding != source_binding:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source authoritative binding changed"
        )
    source_checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        source_manifest,
        source_binding,
    )
    source_runtime_state = (
        load_latest_fast_paper_authoritative_runtime_state(
            source_manifest,
            source_binding,
        )
    )
    _require_quiescent_learned_boundary(
        source_checkpoint,
        source_runtime_state,
        source_decision_state,
    )
    if created_at_unix_ms < source_checkpoint.state_as_of_unix_ms:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff creation time cannot precede source PAPER state"
        )

    legacy_checkpoint = load_latest_paper_checkpoint(
        database_path,
        source_binding.legacy_run_id,
    )
    if (
        legacy_checkpoint is None
        or legacy_checkpoint.sequence
        != source_binding.legacy_checkpoint_sequence
        or legacy_checkpoint.payload_sha256
        != source_binding.legacy_checkpoint_payload_sha256
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "original legacy handoff checkpoint is no longer the exact latest source"
        )

    target_binding = build_fast_paper_authoritative_binding(
        target_manifest,
        target_execution_policy,
        legacy_checkpoint,
        legacy_runtime_manifest_fingerprint_sha256=(
            source_binding.legacy_runtime_manifest_fingerprint_sha256
        ),
        fast_run_id=target_fast_run_id,
        database_path=database_path,
    )
    target_checkpoint_payload = encode_fast_paper_checkpoint(
        target_fast_run_id,
        0,
        source_checkpoint.state,
        created_at_unix_ms,
    )
    target_checkpoint = decode_fast_paper_checkpoint(
        target_checkpoint_payload
    )
    target_runtime_state = build_fast_paper_authoritative_runtime_state(
        target_manifest,
        target_binding,
        target_checkpoint,
        market_positions=source_runtime_state.market_positions,
        execution_policy_fingerprint_sha256=(
            target_execution_policy.policy_fingerprint_sha256
        ),
        last_processed_source_sequence=(
            source_runtime_state.last_processed_source_sequence
        ),
        last_processed_source_event_id=(
            source_runtime_state.last_processed_source_event_id
        ),
        last_processed_decision_evidence_fingerprint_sha256=(
            source_runtime_state
            .last_processed_decision_evidence_fingerprint_sha256
        ),
    )
    target_decision_state = build_fast_paper_runtime_state(
        target_manifest,
        cursor=source_decision_state.cursor,
    )
    handoff = _build_handoff(
        source_manifest=source_manifest,
        source_binding=source_binding,
        source_checkpoint=source_checkpoint,
        source_runtime_state=source_runtime_state,
        source_decision_state=source_decision_state,
        target_manifest=target_manifest,
        target_binding=target_binding,
        target_checkpoint=target_checkpoint,
        target_runtime_state=target_runtime_state,
        target_decision_state=target_decision_state,
        created_at_unix_ms=created_at_unix_ms,
    )

    database = Path(target_binding.database_path)
    connection = _connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_checkpoint_table(connection)
        _ensure_binding_table(connection)
        _ensure_authoritative_runtime_state_table(connection)
        _ensure_release_handoff_table(connection)

        _require_source_rows_unchanged(
            connection,
            source_binding,
            source_checkpoint,
            source_runtime_state,
        )

        expected_binding = (
            target_binding.binding_fingerprint_sha256,
            _canonical(_binding_document(target_binding)),
        )
        expected_checkpoint = (
            target_checkpoint.sequence,
            target_checkpoint.checkpoint_schema_version,
            target_checkpoint.state_as_of_unix_ms,
            target_checkpoint.created_at_unix_ms,
            target_checkpoint.payload_sha256,
            target_checkpoint_payload.decode("utf-8"),
        )
        expected_runtime = _runtime_state_row(
            target_runtime_state,
            created_at_unix_ms=created_at_unix_ms,
        )
        expected_handoff = _handoff_row(handoff)

        existing_binding = connection.execute(
            f"""
            SELECT binding_fingerprint_sha256, binding_json
            FROM {_BINDING_TABLE}
            WHERE fast_run_id = ?
            """,
            (target_fast_run_id,),
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
            (target_fast_run_id,),
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
            (target_fast_run_id,),
        ).fetchall()
        existing_handoff = connection.execute(
            f"""
            SELECT
                source_run_id,
                target_run_id,
                created_at_unix_ms,
                handoff_fingerprint_sha256,
                payload_json
            FROM {FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_TABLE}
            WHERE target_run_id = ?
            """,
            (target_fast_run_id,),
        ).fetchone()

        occupied = (
            existing_binding is not None
            or bool(existing_checkpoints)
            or bool(existing_runtime_states)
            or existing_handoff is not None
        )
        if occupied:
            if (
                existing_binding == expected_binding
                and existing_checkpoints == [expected_checkpoint]
                and existing_runtime_states == [expected_runtime]
                and existing_handoff == expected_handoff
            ):
                connection.rollback()
            else:
                connection.rollback()
                raise FastPaperAuthoritativeReleaseHandoffError(
                    "target Fast release namespace collision"
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
                    target_fast_run_id,
                    target_binding.binding_fingerprint_sha256,
                    expected_binding[1],
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
                    target_checkpoint.run_id,
                    target_checkpoint.sequence,
                    target_checkpoint.checkpoint_schema_version,
                    target_checkpoint.state_as_of_unix_ms,
                    target_checkpoint.created_at_unix_ms,
                    target_checkpoint.payload_sha256,
                    expected_checkpoint[5],
                ),
            )
            _insert_runtime_state_row(
                connection,
                target_binding,
                target_runtime_state,
                created_at_unix_ms=created_at_unix_ms,
            )
            connection.execute(
                f"""
                INSERT INTO {FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_TABLE}(
                    source_run_id,
                    target_run_id,
                    created_at_unix_ms,
                    handoff_fingerprint_sha256,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                expected_handoff,
            )
            _require_source_rows_unchanged(
                connection,
                source_binding,
                source_checkpoint,
                source_runtime_state,
            )
            connection.commit()
    except FastPaperAuthoritativeReleaseHandoffError:
        if connection.in_transaction:
            connection.rollback()
        raise
    except (
        FastPaperAuthoritativeHandoffError,
        sqlite3.Error,
        TypeError,
        ValueError,
    ) as exc:
        if connection.in_transaction:
            connection.rollback()
        raise FastPaperAuthoritativeReleaseHandoffError(
            "Fast PAPER release handoff persistence failed"
        ) from exc
    finally:
        connection.close()

    restored_binding = load_fast_paper_authoritative_binding(
        target_manifest,
        fast_run_id=target_fast_run_id,
        database_path=database,
    )
    restored_checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        target_manifest,
        restored_binding,
    )
    restored_runtime_state = (
        load_latest_fast_paper_authoritative_runtime_state(
            target_manifest,
            restored_binding,
        )
    )
    restored_handoff = load_fast_paper_authoritative_release_handoff(
        database,
        target_fast_run_id=target_fast_run_id,
    )
    if (
        restored_binding != target_binding
        or restored_checkpoint != target_checkpoint
        or restored_runtime_state != target_runtime_state
        or restored_handoff != handoff
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "Fast PAPER release handoff readback mismatch"
        )
    return FastPaperAuthoritativeReleaseHandoffResult(
        handoff=restored_handoff,
        binding=restored_binding,
        checkpoint=restored_checkpoint,
        runtime_state=restored_runtime_state,
        decision_state=target_decision_state,
    )


def load_fast_paper_authoritative_release_handoff(
    database_path: str | Path,
    *,
    target_fast_run_id: str,
) -> FastPaperAuthoritativeReleaseHandoff:
    _require_text("target_fast_run_id", target_fast_run_id)
    database = Path(database_path).expanduser()
    if database.is_symlink() or not database.is_file():
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff database must be an existing regular non-symlink file"
        )
    connection = _connect(database)
    try:
        row = connection.execute(
            f"""
            SELECT handoff_fingerprint_sha256, payload_json
            FROM {FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_TABLE}
            WHERE target_run_id = ?
            """,
            (target_fast_run_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff table is missing or unreadable"
        ) from exc
    finally:
        connection.close()
    if row is None:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff record is missing"
        )
    fingerprint, payload = row
    _require_sha256("stored handoff fingerprint", fingerprint)
    if not isinstance(payload, str):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "stored release handoff payload must be text"
        )
    handoff = _decode_handoff(payload)
    if handoff.handoff_fingerprint_sha256 != fingerprint:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff row fingerprint mismatch"
        )
    return handoff


def _require_inputs(
    source_manifest: FastPaperRuntimeManifest,
    target_manifest: FastPaperRuntimeManifest,
    source_binding: FastPaperAuthoritativeBinding,
    target_execution_policy: FastPaperShadowExecutionPolicy,
    source_decision_state: FastPaperRuntimeState,
    *,
    target_fast_run_id: str,
    created_at_unix_ms: int,
) -> None:
    for label, manifest in (
        ("source", source_manifest),
        ("target", target_manifest),
    ):
        if type(manifest) is not FastPaperRuntimeManifest:
            raise FastPaperAuthoritativeReleaseHandoffError(
                f"{label} manifest must be exact FastPaperRuntimeManifest"
            )
        try:
            verify_fast_paper_runtime_bindings(manifest)
        except Exception as exc:
            raise FastPaperAuthoritativeReleaseHandoffError(
                f"{label} Fast PAPER manifest authentication failed"
            ) from exc
    if type(source_binding) is not FastPaperAuthoritativeBinding:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source binding must be exact FastPaperAuthoritativeBinding"
        )
    if type(target_execution_policy) is not FastPaperShadowExecutionPolicy:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "target execution policy must be exact FastPaperShadowExecutionPolicy"
        )
    if type(source_decision_state) is not FastPaperRuntimeState:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source decision state must be exact FastPaperRuntimeState"
        )
    expected_source_decision_state = build_fast_paper_runtime_state(
        source_manifest,
        cursor=source_decision_state.cursor,
    )
    if source_decision_state != expected_source_decision_state:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source decision state does not authenticate against source manifest"
        )
    _require_text("target_fast_run_id", target_fast_run_id)
    if target_fast_run_id in (
        source_binding.fast_run_id,
        source_binding.legacy_run_id,
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "target Fast run ID must be a fresh checkpoint namespace"
        )
    _require_non_negative_int(
        "created_at_unix_ms",
        created_at_unix_ms,
    )


def _require_release_compatibility(
    source: FastPaperRuntimeManifest,
    target: FastPaperRuntimeManifest,
) -> None:
    if source.release_source_sha == target.release_source_sha:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "Fast PAPER release handoff requires a distinct target release"
        )
    exact = (
        "champion_version",
        "champion_fingerprint_sha256",
        "champion_file_sha256",
        "decision_binary_sha256",
        "feature_feed_binary_sha256",
        "action_policy",
        "feature_schema_version",
        "state_version",
        "fast_paper_event_loop_version",
        "risk_policy_version",
        "fill_policy_version",
        "position_action_policy_version",
        "strategy_family",
        "strategy_version",
        "assessment_version",
        "paper_evidence_path",
        "checkpoint_path",
        "quote_provider",
        "quote_mint",
        "quote_decimals",
        "route_evidence_version",
    )
    for name in exact:
        if getattr(source, name) != getattr(target, name):
            raise FastPaperAuthoritativeReleaseHandoffError(
                f"Fast PAPER release handoff forbids {name} drift"
            )
    source_db = Path(source.observer_database_path).expanduser()
    target_db = Path(target.observer_database_path).expanduser()
    if (
        source_db.is_symlink()
        or target_db.is_symlink()
        or not source_db.is_file()
        or not target_db.is_file()
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "Fast PAPER release handoff database must be a regular non-symlink file"
        )
    try:
        if not source_db.samefile(target_db):
            raise FastPaperAuthoritativeReleaseHandoffError(
                "Fast PAPER release handoff observer database changed"
            )
    except OSError as exc:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "Fast PAPER release handoff database identity cannot be resolved"
        ) from exc


def _require_quiescent_learned_boundary(
    checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperAuthoritativeRuntimeState,
    decision_state: FastPaperRuntimeState,
) -> None:
    if checkpoint.state.pending_buy is not None:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "Fast PAPER release handoff requires pending BUY resolution"
        )
    decision_sequence = (
        None
        if decision_state.cursor is None
        else decision_state.cursor.decision_sequence
    )
    execution_sequence = runtime_state.last_processed_source_sequence
    if decision_sequence != execution_sequence:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "Fast PAPER release handoff requires equal decision and execution cursors"
        )


def _build_handoff(
    *,
    source_manifest: FastPaperRuntimeManifest,
    source_binding: FastPaperAuthoritativeBinding,
    source_checkpoint: FastPaperCheckpointRecord,
    source_runtime_state: FastPaperAuthoritativeRuntimeState,
    source_decision_state: FastPaperRuntimeState,
    target_manifest: FastPaperRuntimeManifest,
    target_binding: FastPaperAuthoritativeBinding,
    target_checkpoint: FastPaperCheckpointRecord,
    target_runtime_state: FastPaperAuthoritativeRuntimeState,
    target_decision_state: FastPaperRuntimeState,
    created_at_unix_ms: int,
) -> FastPaperAuthoritativeReleaseHandoff:
    values: dict[str, object] = {
        "schema_name": (
            FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_SCHEMA_NAME
        ),
        "schema_version": (
            FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_SCHEMA_VERSION
        ),
        "source_run_id": source_binding.fast_run_id,
        "source_release_source_sha": source_manifest.release_source_sha,
        "source_manifest_fingerprint_sha256": (
            source_manifest.manifest_fingerprint_sha256
        ),
        "source_binding_fingerprint_sha256": (
            source_binding.binding_fingerprint_sha256
        ),
        "source_checkpoint_sequence": source_checkpoint.sequence,
        "source_checkpoint_payload_sha256": (
            source_checkpoint.payload_sha256
        ),
        "source_runtime_state_fingerprint_sha256": (
            source_runtime_state.state_fingerprint_sha256
        ),
        "source_decision_state_fingerprint_sha256": (
            source_decision_state.state_fingerprint_sha256
        ),
        "target_run_id": target_binding.fast_run_id,
        "target_release_source_sha": target_manifest.release_source_sha,
        "target_manifest_fingerprint_sha256": (
            target_manifest.manifest_fingerprint_sha256
        ),
        "target_binding_fingerprint_sha256": (
            target_binding.binding_fingerprint_sha256
        ),
        "target_checkpoint_sequence": target_checkpoint.sequence,
        "target_checkpoint_payload_sha256": (
            target_checkpoint.payload_sha256
        ),
        "target_runtime_state_fingerprint_sha256": (
            target_runtime_state.state_fingerprint_sha256
        ),
        "target_decision_state_fingerprint_sha256": (
            target_decision_state.state_fingerprint_sha256
        ),
        "created_at_unix_ms": created_at_unix_ms,
    }
    fingerprint = hashlib.sha256(
        _canonical(values).encode("utf-8")
    ).hexdigest()
    return FastPaperAuthoritativeReleaseHandoff(
        **values,
        handoff_fingerprint_sha256=fingerprint,
    )


def _require_source_rows_unchanged(
    connection: sqlite3.Connection,
    binding: FastPaperAuthoritativeBinding,
    checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperAuthoritativeRuntimeState,
) -> None:
    stored_binding = connection.execute(
        f"""
        SELECT binding_fingerprint_sha256, binding_json
        FROM {_BINDING_TABLE}
        WHERE fast_run_id = ?
        """,
        (binding.fast_run_id,),
    ).fetchone()
    if stored_binding != (
        binding.binding_fingerprint_sha256,
        _canonical(_binding_document(binding)),
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source authoritative binding changed during release handoff"
        )
    stored_checkpoint = connection.execute(
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
        (binding.fast_run_id,),
    ).fetchone()
    expected_checkpoint_payload = encode_fast_paper_checkpoint(
        checkpoint.run_id,
        checkpoint.sequence,
        checkpoint.state,
        checkpoint.created_at_unix_ms,
    ).decode("utf-8")
    expected_checkpoint = (
        checkpoint.sequence,
        checkpoint.checkpoint_schema_version,
        checkpoint.state_as_of_unix_ms,
        checkpoint.created_at_unix_ms,
        checkpoint.payload_sha256,
        expected_checkpoint_payload,
    )
    if stored_checkpoint != expected_checkpoint:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source authoritative checkpoint changed during release handoff"
        )
    stored_runtime = connection.execute(
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
        ORDER BY paper_checkpoint_sequence DESC
        LIMIT 1
        """,
        (binding.fast_run_id,),
    ).fetchone()
    if stored_runtime is None:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source authoritative runtime state disappeared during release handoff"
        )
    if (
        stored_runtime[0] != runtime_state.paper_checkpoint_sequence
        or stored_runtime[1]
        != runtime_state.paper_checkpoint_payload_sha256
        or stored_runtime[5] is None
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source authoritative runtime state changed during release handoff"
        )
    if (
        hashlib.sha256(str(stored_runtime[5]).encode("utf-8")).hexdigest()
        != stored_runtime[4]
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source authoritative runtime row checksum changed during release handoff"
        )
    if runtime_state.state_fingerprint_sha256 not in str(stored_runtime[5]):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "source authoritative runtime payload changed during release handoff"
        )


def _ensure_release_handoff_table(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS
            {FAST_PAPER_AUTHORITATIVE_RELEASE_HANDOFF_TABLE} (
                source_run_id TEXT NOT NULL,
                target_run_id TEXT NOT NULL PRIMARY KEY,
                created_at_unix_ms INTEGER NOT NULL
                    CHECK (created_at_unix_ms >= 0),
                handoff_fingerprint_sha256 TEXT NOT NULL
                    CHECK (length(handoff_fingerprint_sha256) = 64),
                payload_json TEXT NOT NULL
            )
        """
    )


def _handoff_row(
    handoff: FastPaperAuthoritativeReleaseHandoff,
) -> tuple[object, ...]:
    return (
        handoff.source_run_id,
        handoff.target_run_id,
        handoff.created_at_unix_ms,
        handoff.handoff_fingerprint_sha256,
        _canonical(_handoff_document(handoff)),
    )


def _handoff_document(
    handoff: FastPaperAuthoritativeReleaseHandoff,
) -> dict[str, object]:
    return {
        "schema_name": handoff.schema_name,
        "schema_version": handoff.schema_version,
        "source_run_id": handoff.source_run_id,
        "source_release_source_sha": handoff.source_release_source_sha,
        "source_manifest_fingerprint_sha256": (
            handoff.source_manifest_fingerprint_sha256
        ),
        "source_binding_fingerprint_sha256": (
            handoff.source_binding_fingerprint_sha256
        ),
        "source_checkpoint_sequence": handoff.source_checkpoint_sequence,
        "source_checkpoint_payload_sha256": (
            handoff.source_checkpoint_payload_sha256
        ),
        "source_runtime_state_fingerprint_sha256": (
            handoff.source_runtime_state_fingerprint_sha256
        ),
        "source_decision_state_fingerprint_sha256": (
            handoff.source_decision_state_fingerprint_sha256
        ),
        "target_run_id": handoff.target_run_id,
        "target_release_source_sha": handoff.target_release_source_sha,
        "target_manifest_fingerprint_sha256": (
            handoff.target_manifest_fingerprint_sha256
        ),
        "target_binding_fingerprint_sha256": (
            handoff.target_binding_fingerprint_sha256
        ),
        "target_checkpoint_sequence": handoff.target_checkpoint_sequence,
        "target_checkpoint_payload_sha256": (
            handoff.target_checkpoint_payload_sha256
        ),
        "target_runtime_state_fingerprint_sha256": (
            handoff.target_runtime_state_fingerprint_sha256
        ),
        "target_decision_state_fingerprint_sha256": (
            handoff.target_decision_state_fingerprint_sha256
        ),
        "created_at_unix_ms": handoff.created_at_unix_ms,
        "handoff_fingerprint_sha256": handoff.handoff_fingerprint_sha256,
    }


def _handoff_fingerprint(
    handoff: FastPaperAuthoritativeReleaseHandoff,
) -> str:
    material = _handoff_document_unchecked(handoff)
    material.pop("handoff_fingerprint_sha256")
    return hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()


def _handoff_document_unchecked(
    handoff: FastPaperAuthoritativeReleaseHandoff,
) -> dict[str, object]:
    return {
        "schema_name": handoff.schema_name,
        "schema_version": handoff.schema_version,
        "source_run_id": handoff.source_run_id,
        "source_release_source_sha": handoff.source_release_source_sha,
        "source_manifest_fingerprint_sha256": (
            handoff.source_manifest_fingerprint_sha256
        ),
        "source_binding_fingerprint_sha256": (
            handoff.source_binding_fingerprint_sha256
        ),
        "source_checkpoint_sequence": handoff.source_checkpoint_sequence,
        "source_checkpoint_payload_sha256": (
            handoff.source_checkpoint_payload_sha256
        ),
        "source_runtime_state_fingerprint_sha256": (
            handoff.source_runtime_state_fingerprint_sha256
        ),
        "source_decision_state_fingerprint_sha256": (
            handoff.source_decision_state_fingerprint_sha256
        ),
        "target_run_id": handoff.target_run_id,
        "target_release_source_sha": handoff.target_release_source_sha,
        "target_manifest_fingerprint_sha256": (
            handoff.target_manifest_fingerprint_sha256
        ),
        "target_binding_fingerprint_sha256": (
            handoff.target_binding_fingerprint_sha256
        ),
        "target_checkpoint_sequence": handoff.target_checkpoint_sequence,
        "target_checkpoint_payload_sha256": (
            handoff.target_checkpoint_payload_sha256
        ),
        "target_runtime_state_fingerprint_sha256": (
            handoff.target_runtime_state_fingerprint_sha256
        ),
        "target_decision_state_fingerprint_sha256": (
            handoff.target_decision_state_fingerprint_sha256
        ),
        "created_at_unix_ms": handoff.created_at_unix_ms,
        "handoff_fingerprint_sha256": (
            handoff.handoff_fingerprint_sha256
        ),
    }


def _decode_handoff(
    payload: str,
) -> FastPaperAuthoritativeReleaseHandoff:
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff JSON is invalid"
        ) from exc
    if not isinstance(document, dict):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff must be a JSON object"
        )
    if payload != _canonical(document):
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff must use canonical JSON"
        )
    try:
        return FastPaperAuthoritativeReleaseHandoff(**document)
    except (TypeError, ValueError) as exc:
        raise FastPaperAuthoritativeReleaseHandoffError(
            "release handoff content is incompatible"
        ) from exc


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
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            f"{name} must be non-empty trimmed text"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            f"{name} must be a non-negative integer"
        )


def _require_source_sha(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            f"{name} must be exactly 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FastPaperAuthoritativeReleaseHandoffError(
            f"{name} must be lowercase SHA-256 hex"
        )
