from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.authoritative_handoff as handoff
from shreks_brain.paper_loop import PendingPaperEntry
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    load_latest_fast_paper_checkpoint,
    load_latest_paper_checkpoint,
    save_paper_checkpoint,
    validate_fast_paper_accounting,
    validate_fast_paper_restart_equivalence,
    validate_paper_accounting,
)

from test_fast_paper_shadow_execution_input import _execution_policy
from test_fast_paper_shadow_restart_orchestration import _manifest
from test_observer_campaign_runner import _state as _legacy_flat_state
from test_paper_loop_exit import (
    _buy_intent,
    _create_pending_reduce,
    _exit_policy,
    _open_state,
)


_LEGACY_RUN_ID = "legacy-paper-run"
_FAST_RUN_ID = "fast-paper-run"
_LEGACY_MANIFEST_FP = "9" * 64


def _create_checkpoint_table(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_loop_checkpoints (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence >= 0),
                checkpoint_schema_version TEXT NOT NULL,
                state_as_of_unix_ms INTEGER NOT NULL CHECK (state_as_of_unix_ms >= 0),
                created_at_unix_ms INTEGER NOT NULL CHECK (created_at_unix_ms >= 0),
                payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence)
            );
            CREATE INDEX idx_paper_loop_checkpoints_run_latest
                ON paper_loop_checkpoints (run_id, sequence DESC);
            """
        )


def _legacy_checkpoint(
    tmp_path: Path,
    *,
    state=None,
    sequence: int = 7,
):
    manifest = _manifest(tmp_path)
    database = Path(manifest.observer_database_path)
    _create_checkpoint_table(database)
    legacy_state = _legacy_flat_state() if state is None else state
    checkpoint = save_paper_checkpoint(
        database,
        _LEGACY_RUN_ID,
        sequence,
        legacy_state,
        legacy_state.last_cycle_at_unix_ms,
    )
    return manifest, database, checkpoint


def _initialize(
    manifest,
    database: Path,
    source,
    *,
    fast_run_id: str = _FAST_RUN_ID,
):
    return handoff.initialize_fast_paper_authoritative_handoff(
        manifest,
        _execution_policy(manifest),
        source,
        legacy_runtime_manifest_fingerprint_sha256=_LEGACY_MANIFEST_FP,
        fast_run_id=fast_run_id,
        database_path=database,
        created_at_unix_ms=source.state.last_cycle_at_unix_ms,
    )


def test_flat_latest_legacy_checkpoint_seeds_exact_fast_ledger(
    tmp_path: Path,
) -> None:
    manifest, database, source = _legacy_checkpoint(tmp_path)
    policy = _execution_policy(manifest)

    result = handoff.initialize_fast_paper_authoritative_handoff(
        manifest,
        policy,
        source,
        legacy_runtime_manifest_fingerprint_sha256=_LEGACY_MANIFEST_FP,
        fast_run_id=_FAST_RUN_ID,
        database_path=database,
        created_at_unix_ms=source.state.last_cycle_at_unix_ms,
    )

    binding = result.binding
    checkpoint = result.checkpoint
    assert binding.schema_name == "shreks.fast_paper_authoritative_binding"
    assert binding.schema_version == 1
    assert binding.fast_run_id == _FAST_RUN_ID
    assert binding.legacy_run_id == _LEGACY_RUN_ID
    assert binding.legacy_checkpoint_sequence == source.sequence
    assert binding.legacy_checkpoint_payload_sha256 == source.payload_sha256
    assert (
        binding.legacy_runtime_manifest_fingerprint_sha256
        == _LEGACY_MANIFEST_FP
    )
    assert binding.release_source_sha == manifest.release_source_sha
    assert (
        binding.manifest_fingerprint_sha256
        == manifest.manifest_fingerprint_sha256
    )
    assert binding.champion_version == manifest.champion_version
    assert (
        binding.champion_fingerprint_sha256
        == manifest.champion_fingerprint_sha256
    )
    assert binding.action_policy_version == manifest.action_policy.version
    assert (
        binding.execution_policy_fingerprint_sha256
        == policy.policy_fingerprint_sha256
    )
    assert binding.risk_policy_version == manifest.risk_policy_version
    assert binding.fill_policy_version == manifest.fill_policy_version
    assert (
        binding.position_action_policy_version
        == manifest.position_action_policy_version
    )
    assert binding.database_path == str(database.resolve())

    assert checkpoint.run_id == _FAST_RUN_ID
    assert checkpoint.sequence == 0
    assert checkpoint.state.ledger == source.state.ledger
    assert checkpoint.state.as_of_unix_ms == source.state.last_cycle_at_unix_ms
    assert checkpoint.state.event_loop_state.records == ()
    assert checkpoint.state.event_loop_state.market_cursors == ()
    assert checkpoint.state.fill_policy == policy.fill_policy
    assert (
        checkpoint.state.position_action_policy
        == policy.position_action_policy
    )
    assert checkpoint.state.pending_buy is None
    assert checkpoint.state.position_action_states == ()

    legacy_accounting = validate_paper_accounting(source.state)
    fast_accounting = validate_fast_paper_accounting(checkpoint.state)
    assert legacy_accounting.status is AccountingValidationStatus.RECONCILED
    assert fast_accounting == legacy_accounting

    restored_source = load_latest_paper_checkpoint(
        database,
        _LEGACY_RUN_ID,
    )
    assert restored_source == source
    restored_fast = load_latest_fast_paper_checkpoint(
        database,
        _FAST_RUN_ID,
    )
    assert restored_fast == checkpoint
    assert validate_fast_paper_restart_equivalence(
        checkpoint.state,
        restored_fast.state,
    ).equivalent


def test_exact_repeat_is_idempotent(
    tmp_path: Path,
) -> None:
    manifest, database, source = _legacy_checkpoint(tmp_path)

    first = _initialize(manifest, database, source)
    second = _initialize(manifest, database, source)

    assert second == first
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM paper_loop_checkpoints
            WHERE run_id = ?
            """,
            (_FAST_RUN_ID,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_bindings
            WHERE fast_run_id = ?
            """,
            (_FAST_RUN_ID,),
        ).fetchone() == (1,)


def test_stale_legacy_checkpoint_is_rejected(
    tmp_path: Path,
) -> None:
    manifest, database, source = _legacy_checkpoint(tmp_path)
    save_paper_checkpoint(
        database,
        _LEGACY_RUN_ID,
        source.sequence + 1,
        source.state,
        source.state.last_cycle_at_unix_ms,
    )

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="latest|stale",
    ):
        _initialize(manifest, database, source)


def test_open_legacy_position_is_rejected(
    tmp_path: Path,
) -> None:
    state = _open_state(latency_ms=0)
    manifest, database, source = _legacy_checkpoint(
        tmp_path,
        state=state,
    )

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="OPEN|flat",
    ):
        _initialize(manifest, database, source)


def test_pending_legacy_entry_is_rejected(
    tmp_path: Path,
) -> None:
    state = replace(
        _legacy_flat_state(),
        pending_entry=PendingPaperEntry(
            intent=_buy_intent(),
            exit_policy=_exit_policy(),
        ),
    )
    manifest, database, source = _legacy_checkpoint(
        tmp_path,
        state=state,
    )

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="pending entry",
    ):
        _initialize(manifest, database, source)


def test_pending_legacy_exit_is_rejected(
    tmp_path: Path,
) -> None:
    pending_state = _create_pending_reduce(
        _open_state(latency_ms=0)
    )[0].next_state
    assert pending_state.managed_positions[0].pending_exit is not None
    manifest, database, source = _legacy_checkpoint(
        tmp_path,
        state=pending_state,
    )

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="pending exit|flat",
    ):
        _initialize(manifest, database, source)


def test_non_reconciled_source_accounting_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, database, source = _legacy_checkpoint(tmp_path)
    monkeypatch.setattr(
        handoff,
        "validate_paper_accounting",
        lambda _state: SimpleNamespace(
            status=AccountingValidationStatus.INVALID
        ),
    )

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="accounting",
    ):
        _initialize(manifest, database, source)


def test_database_must_be_exact_manifest_authoritative_observer_root(
    tmp_path: Path,
) -> None:
    manifest, _database, source = _legacy_checkpoint(tmp_path)
    substitute = tmp_path / "substitute.sqlite3"
    _create_checkpoint_table(substitute)
    save_paper_checkpoint(
        substitute,
        _LEGACY_RUN_ID,
        source.sequence,
        source.state,
        source.created_at_unix_ms,
    )

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="authoritative|observer",
    ):
        handoff.initialize_fast_paper_authoritative_handoff(
            manifest,
            _execution_policy(manifest),
            source,
            legacy_runtime_manifest_fingerprint_sha256=(
                _LEGACY_MANIFEST_FP
            ),
            fast_run_id=_FAST_RUN_ID,
            database_path=substitute,
            created_at_unix_ms=source.state.last_cycle_at_unix_ms,
        )


def test_fast_and_legacy_run_ids_must_differ(
    tmp_path: Path,
) -> None:
    manifest, database, source = _legacy_checkpoint(tmp_path)

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="run_id|run ID|namespace",
    ):
        _initialize(
            manifest,
            database,
            source,
            fast_run_id=_LEGACY_RUN_ID,
        )


def test_target_checkpoint_namespace_collision_is_rejected(
    tmp_path: Path,
) -> None:
    manifest, database, source = _legacy_checkpoint(tmp_path)
    save_paper_checkpoint(
        database,
        _FAST_RUN_ID,
        0,
        source.state,
        source.created_at_unix_ms,
    )

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="namespace|collision|schema",
    ):
        _initialize(manifest, database, source)


def test_binding_tamper_fails_closed_before_checkpoint_load(
    tmp_path: Path,
) -> None:
    manifest, database, source = _legacy_checkpoint(tmp_path)
    result = _initialize(manifest, database, source)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE fast_paper_authoritative_bindings
            SET binding_fingerprint_sha256 = ?
            WHERE fast_run_id = ?
            """,
            ("0" * 64, _FAST_RUN_ID),
        )
        connection.commit()

    with pytest.raises(
        handoff.FastPaperAuthoritativeHandoffError,
        match="binding|fingerprint",
    ):
        handoff.load_latest_fast_paper_authoritative_checkpoint(
            manifest,
            result.binding,
        )


def test_binding_is_deterministic_and_manifest_policy_bound(
    tmp_path: Path,
) -> None:
    manifest, database, source = _legacy_checkpoint(tmp_path)
    policy = _execution_policy(manifest)

    first = handoff.build_fast_paper_authoritative_binding(
        manifest,
        policy,
        source,
        legacy_runtime_manifest_fingerprint_sha256=_LEGACY_MANIFEST_FP,
        fast_run_id=_FAST_RUN_ID,
        database_path=database,
    )
    second = handoff.build_fast_paper_authoritative_binding(
        manifest,
        policy,
        source,
        legacy_runtime_manifest_fingerprint_sha256=_LEGACY_MANIFEST_FP,
        fast_run_id=_FAST_RUN_ID,
        database_path=database,
    )

    assert first == second
    assert len(first.binding_fingerprint_sha256) == 64


def test_authoritative_handoff_source_has_state_authority_only() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "authoritative_handoff.py"
    ).read_text(encoding="utf-8")

    for required in (
        "PaperLedger",
        "FastPaperRuntimeState",
        "encode_fast_paper_checkpoint",
        "load_latest_paper_checkpoint",
        "validate_paper_accounting",
        "validate_fast_paper_accounting",
        "BEGIN IMMEDIATE",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "run_paper_cycle",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "commit_fast_paper_shadow_transition_atomically",
        "initialize_fast_paper_shadow_ledger_database",
        "systemctl",
        "subprocess",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "LIVE_ENABLED",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in source
