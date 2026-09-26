from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_execution as service_execution
from shreks_brain.fast_paper_runtime import (
    consume_fast_paper_shadow_service_execution_source_record,
)


def _values() -> SimpleNamespace:
    decision_evidence = object()
    authenticated_input = object()
    manifest = object()
    binding = object()
    execution_policy = object()
    checkpoint = SimpleNamespace(
        sequence=11,
        payload_sha256="a" * 64,
    )
    runtime_state = SimpleNamespace(
        state_fingerprint_sha256="b" * 64,
    )
    record = SimpleNamespace(
        execution_input=authenticated_input,
    )
    transition = SimpleNamespace(replayed=False)
    commit_result = object()
    return SimpleNamespace(
        decision_evidence=decision_evidence,
        authenticated_input=authenticated_input,
        manifest=manifest,
        binding=binding,
        execution_policy=execution_policy,
        checkpoint=checkpoint,
        runtime_state=runtime_state,
        record=record,
        transition=transition,
        commit_result=commit_result,
    )


def _install_happy_path(monkeypatch, values: SimpleNamespace) -> dict[str, object]:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        service_execution,
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        lambda manifest, binding: (
            captured.update(
                checkpoint_manifest=manifest,
                checkpoint_binding=binding,
            )
            or values.checkpoint
        ),
    )
    monkeypatch.setattr(
        service_execution,
        "load_latest_fast_paper_shadow_runtime_state",
        lambda manifest, binding: (
            captured.update(
                runtime_manifest=manifest,
                runtime_binding=binding,
            )
            or values.runtime_state
        ),
    )

    def read(
        manifest,
        execution_policy,
        decision_evidence,
        directory,
        *,
        paper_checkpoint_sequence,
        paper_checkpoint_payload_sha256,
        shadow_runtime_state_fingerprint_sha256,
    ):
        captured.update(
            read_manifest=manifest,
            read_execution_policy=execution_policy,
            read_decision_evidence=decision_evidence,
            read_directory=directory,
            read_checkpoint_sequence=paper_checkpoint_sequence,
            read_checkpoint_sha=paper_checkpoint_payload_sha256,
            read_runtime_sha=shadow_runtime_state_fingerprint_sha256,
        )
        return values.record

    monkeypatch.setattr(
        service_execution,
        "read_fast_paper_shadow_execution_input_source_record",
        read,
    )

    def execute(
        manifest,
        execution_policy,
        binding,
        checkpoint,
        runtime_state,
        source,
    ):
        captured.update(
            execute_manifest=manifest,
            execute_execution_policy=execution_policy,
            execute_binding=binding,
            execute_checkpoint=checkpoint,
            execute_runtime_state=runtime_state,
            executed_source=source,
        )
        return values.transition

    monkeypatch.setattr(
        service_execution,
        "execute_fast_paper_shadow_decision",
        execute,
    )

    def commit(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        transition,
        *,
        sequence,
        created_at_unix_ms,
    ):
        captured.update(
            commit_manifest=manifest,
            commit_binding=binding,
            commit_checkpoint=checkpoint,
            commit_runtime_state=runtime_state,
            commit_transition=transition,
            commit_sequence=sequence,
            commit_created_at_unix_ms=created_at_unix_ms,
        )
        return values.commit_result

    monkeypatch.setattr(
        service_execution,
        "commit_fast_paper_shadow_transition_atomically",
        commit,
    )
    monkeypatch.setattr(
        service_execution,
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "consumer must not produce execution source authority"
        ),
    )
    monkeypatch.setattr(
        service_execution,
        "write_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "consumer must not write execution source authority"
        ),
    )
    return captured


def test_shadow_service_source_consumer_authenticates_executes_and_commits(
    monkeypatch,
    tmp_path: Path,
) -> None:
    values = _values()
    captured = _install_happy_path(monkeypatch, values)
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()

    result = consume_fast_paper_shadow_service_execution_source_record(
        values.manifest,
        values.binding,
        values.execution_policy,
        values.decision_evidence,
        source_directory=source_directory,
        committed_at_unix_ms=2_000,
    )

    assert result is values.commit_result
    assert captured["checkpoint_manifest"] is values.manifest
    assert captured["runtime_manifest"] is values.manifest
    assert captured["read_decision_evidence"] is values.decision_evidence
    assert captured["read_directory"] == source_directory
    assert captured["read_checkpoint_sequence"] == 11
    assert captured["read_checkpoint_sha"] == "a" * 64
    assert captured["read_runtime_sha"] == "b" * 64
    assert captured["executed_source"] is values.authenticated_input
    assert captured["commit_checkpoint"] is values.checkpoint
    assert captured["commit_runtime_state"] is values.runtime_state
    assert captured["commit_transition"] is values.transition
    assert captured["commit_sequence"] == 12
    assert captured["commit_created_at_unix_ms"] == 2_000


@pytest.mark.parametrize(
    ("missing_name", "checkpoint", "runtime_state"),
    (
        ("checkpoint", None, SimpleNamespace(state_fingerprint_sha256="b" * 64)),
        (
            "runtime state",
            SimpleNamespace(sequence=11, payload_sha256="a" * 64),
            None,
        ),
    ),
)
def test_shadow_service_source_consumer_requires_durable_pair_before_read(
    monkeypatch,
    tmp_path: Path,
    missing_name: str,
    checkpoint: object,
    runtime_state: object,
) -> None:
    values = _values()
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()
    monkeypatch.setattr(
        service_execution,
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        lambda *_args: checkpoint,
    )
    monkeypatch.setattr(
        service_execution,
        "load_latest_fast_paper_shadow_runtime_state",
        lambda *_args: runtime_state,
    )
    monkeypatch.setattr(
        service_execution,
        "read_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "missing durable pair must fail before source read"
        ),
    )

    with pytest.raises(ValueError, match=missing_name):
        consume_fast_paper_shadow_service_execution_source_record(
            values.manifest,
            values.binding,
            values.execution_policy,
            values.decision_evidence,
            source_directory=source_directory,
            committed_at_unix_ms=2_000,
        )


def test_shadow_service_source_consumer_never_executes_when_source_read_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    values = _values()
    _install_happy_path(monkeypatch, values)
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()
    monkeypatch.setattr(
        service_execution,
        "read_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("stale source authority")
        ),
    )
    monkeypatch.setattr(
        service_execution,
        "execute_fast_paper_shadow_decision",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid source authority must not execute"
        ),
    )

    with pytest.raises(ValueError, match="stale source authority"):
        consume_fast_paper_shadow_service_execution_source_record(
            values.manifest,
            values.binding,
            values.execution_policy,
            values.decision_evidence,
            source_directory=source_directory,
            committed_at_unix_ms=2_000,
        )


def test_shadow_service_source_consumer_rejects_replay_before_commit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    values = _values()
    _install_happy_path(monkeypatch, values)
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()
    monkeypatch.setattr(
        service_execution,
        "execute_fast_paper_shadow_decision",
        lambda *_args, **_kwargs: SimpleNamespace(replayed=True),
    )
    monkeypatch.setattr(
        service_execution,
        "commit_fast_paper_shadow_transition_atomically",
        lambda *_args, **_kwargs: pytest.fail(
            "replayed transition must not create another checkpoint"
        ),
    )

    with pytest.raises(ValueError, match="replay"):
        consume_fast_paper_shadow_service_execution_source_record(
            values.manifest,
            values.binding,
            values.execution_policy,
            values.decision_evidence,
            source_directory=source_directory,
            committed_at_unix_ms=2_000,
        )


def test_shadow_service_source_consumer_has_no_new_authority_dependencies() -> None:
    source = Path(service_execution.__file__).read_text(encoding="utf-8")
    forbidden = (
        "shreks_brain.scoring",
        "score_candidate",
        "shreks_brain.decision",
        "decide_entry",
        "requests",
        "httpx",
        "urllib",
        "sqlite3",
        "RuntimeMode.LIVE",
    )
    for marker in forbidden:
        assert marker not in source
