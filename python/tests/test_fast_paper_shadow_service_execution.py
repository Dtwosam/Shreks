from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_execution as service_execution
from shreks_brain.fast_paper_runtime import (
    run_fast_paper_shadow_service_execution,
)


def _fixtures() -> SimpleNamespace:
    decision = object()
    supplied_execution_input = SimpleNamespace(decision_evidence=decision)
    authenticated_execution_input = object()
    manifest = object()
    binding = object()
    execution_policy = object()
    checkpoint = SimpleNamespace(
        sequence=7,
        payload_sha256="a" * 64,
    )
    runtime_state = SimpleNamespace(
        state_fingerprint_sha256="b" * 64,
    )
    record = SimpleNamespace(
        execution_input=authenticated_execution_input,
    )
    transition = SimpleNamespace(replayed=False)
    commit_result = object()
    return SimpleNamespace(
        decision=decision,
        supplied_execution_input=supplied_execution_input,
        authenticated_execution_input=authenticated_execution_input,
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

    def produce(
        manifest,
        binding,
        execution_policy,
        checkpoint,
        runtime_state,
        source,
        *,
        source_observed_at_unix_ms,
        risk_day_started_at_unix_ms,
    ):
        captured.update(
            producer_manifest=manifest,
            producer_binding=binding,
            producer_execution_policy=execution_policy,
            producer_checkpoint=checkpoint,
            producer_runtime_state=runtime_state,
            producer_source=source,
            source_observed_at_unix_ms=source_observed_at_unix_ms,
            risk_day_started_at_unix_ms=risk_day_started_at_unix_ms,
        )
        return values.record

    monkeypatch.setattr(
        service_execution,
        "produce_fast_paper_shadow_execution_input_source_record",
        produce,
    )

    def write(record, directory):
        captured.update(
            written_record=record,
            written_directory=directory,
        )
        return Path(directory) / "record.json"

    monkeypatch.setattr(
        service_execution,
        "write_fast_paper_shadow_execution_input_source_record",
        write,
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
    return captured


def test_shadow_service_execution_binds_source_executes_readback_and_commits(
    monkeypatch,
    tmp_path: Path,
) -> None:
    values = _fixtures()
    captured = _install_happy_path(monkeypatch, values)
    source_directory = tmp_path / "execution-inputs"
    source_directory.mkdir()

    result = run_fast_paper_shadow_service_execution(
        values.manifest,
        values.binding,
        values.execution_policy,
        values.supplied_execution_input,
        source_directory=source_directory,
        source_observed_at_unix_ms=1_000,
        risk_day_started_at_unix_ms=0,
        committed_at_unix_ms=1_100,
    )

    assert result is values.commit_result
    assert captured["checkpoint_manifest"] is values.manifest
    assert captured["checkpoint_binding"] is values.binding
    assert captured["runtime_manifest"] is values.manifest
    assert captured["runtime_binding"] is values.binding
    assert captured["producer_checkpoint"] is values.checkpoint
    assert captured["producer_runtime_state"] is values.runtime_state
    assert captured["producer_source"] is values.supplied_execution_input
    assert captured["source_observed_at_unix_ms"] == 1_000
    assert captured["risk_day_started_at_unix_ms"] == 0
    assert captured["written_record"] is values.record
    assert captured["written_directory"] == source_directory
    assert captured["read_decision_evidence"] is values.decision
    assert captured["read_checkpoint_sequence"] == 7
    assert captured["read_checkpoint_sha"] == "a" * 64
    assert captured["read_runtime_sha"] == "b" * 64
    assert captured["executed_source"] is values.authenticated_execution_input
    assert captured["commit_checkpoint"] is values.checkpoint
    assert captured["commit_runtime_state"] is values.runtime_state
    assert captured["commit_transition"] is values.transition
    assert captured["commit_sequence"] == 8
    assert captured["commit_created_at_unix_ms"] == 1_100


def test_shadow_service_execution_recovers_write_once_source_before_commit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    values = _fixtures()
    captured = _install_happy_path(monkeypatch, values)
    source_directory = tmp_path / "execution-inputs"
    source_directory.mkdir()

    def already_written(record, directory):
        captured.update(
            written_record=record,
            written_directory=directory,
        )
        raise FileExistsError("already staged")

    monkeypatch.setattr(
        service_execution,
        "write_fast_paper_shadow_execution_input_source_record",
        already_written,
    )

    result = run_fast_paper_shadow_service_execution(
        values.manifest,
        values.binding,
        values.execution_policy,
        values.supplied_execution_input,
        source_directory=source_directory,
        source_observed_at_unix_ms=1_000,
        risk_day_started_at_unix_ms=0,
        committed_at_unix_ms=1_100,
    )

    assert result is values.commit_result
    assert captured["executed_source"] is values.authenticated_execution_input
    assert captured["commit_sequence"] == 8


@pytest.mark.parametrize(
    ("missing_name", "checkpoint", "runtime_state"),
    (
        ("checkpoint", None, SimpleNamespace(state_fingerprint_sha256="b" * 64)),
        (
            "runtime state",
            SimpleNamespace(sequence=7, payload_sha256="a" * 64),
            None,
        ),
    ),
)
def test_shadow_service_execution_requires_exact_durable_pair_before_production(
    monkeypatch,
    tmp_path: Path,
    missing_name: str,
    checkpoint: object,
    runtime_state: object,
) -> None:
    values = _fixtures()
    source_directory = tmp_path / "execution-inputs"
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
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "missing durable pair must fail before source production"
        ),
    )

    with pytest.raises(ValueError, match=missing_name):
        run_fast_paper_shadow_service_execution(
            values.manifest,
            values.binding,
            values.execution_policy,
            values.supplied_execution_input,
            source_directory=source_directory,
            source_observed_at_unix_ms=1_000,
            risk_day_started_at_unix_ms=0,
            committed_at_unix_ms=1_100,
        )


def test_shadow_service_execution_requires_exact_source_readback_before_execution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    values = _fixtures()
    _install_happy_path(monkeypatch, values)
    source_directory = tmp_path / "execution-inputs"
    source_directory.mkdir()
    monkeypatch.setattr(
        service_execution,
        "read_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: SimpleNamespace(
            execution_input=object(),
        ),
    )
    monkeypatch.setattr(
        service_execution,
        "execute_fast_paper_shadow_decision",
        lambda *_args, **_kwargs: pytest.fail(
            "mismatched source read-back must not reach execution"
        ),
    )

    with pytest.raises(ValueError, match="read-back mismatch"):
        run_fast_paper_shadow_service_execution(
            values.manifest,
            values.binding,
            values.execution_policy,
            values.supplied_execution_input,
            source_directory=source_directory,
            source_observed_at_unix_ms=1_000,
            risk_day_started_at_unix_ms=0,
            committed_at_unix_ms=1_100,
        )


def test_shadow_service_execution_rejects_replay_before_atomic_commit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    values = _fixtures()
    _install_happy_path(monkeypatch, values)
    source_directory = tmp_path / "execution-inputs"
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
            "replayed decision must not create another durable checkpoint"
        ),
    )

    with pytest.raises(ValueError, match="replay"):
        run_fast_paper_shadow_service_execution(
            values.manifest,
            values.binding,
            values.execution_policy,
            values.supplied_execution_input,
            source_directory=source_directory,
            source_observed_at_unix_ms=1_000,
            risk_day_started_at_unix_ms=0,
            committed_at_unix_ms=1_100,
        )


def test_shadow_service_execution_source_has_no_forbidden_authority_imports() -> None:
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
        "signing",
        "submission",
        "RuntimeMode.LIVE",
    )
    for marker in forbidden:
        assert marker not in source
