from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_execution_cycle as execution_cycle
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowServiceExecutionBootstrap,
    bootstrap_fast_paper_shadow_service_execution,
    build_fast_paper_shadow_runtime_state,
    run_fast_paper_shadow_service_execution_cycle,
)

from test_fast_paper_shadow_service_execution_bootstrap import (
    _durable_fixture,
)


def _decision(manifest, *, sequence: int, fingerprint: str):
    return SimpleNamespace(
        release_source_sha=manifest.release_source_sha,
        manifest_fingerprint_sha256=manifest.manifest_fingerprint_sha256,
        champion_fingerprint_sha256=manifest.champion_fingerprint_sha256,
        source_sequence=sequence,
        source_event_id=f"event-{sequence}",
        evidence_fingerprint_sha256=fingerprint,
    )


def _evidence_file(directory: Path, sequence: int, suffix: str) -> Path:
    path = directory / f"shadow-{sequence:020d}-{suffix}.json"
    path.write_text("{}\n", encoding="utf-8")
    return path


def _bootstrap(tmp_path: Path):
    manifest, _policy, _binding, _checkpoint, _runtime, config = (
        _durable_fixture(tmp_path)
    )
    bootstrap = bootstrap_fast_paper_shadow_service_execution(
        manifest,
        config,
    )
    decision_directory = tmp_path / "decision-evidence"
    decision_directory.mkdir()
    return manifest, bootstrap, decision_directory


def test_execution_cycle_returns_zero_when_no_decision_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    monkeypatch.setattr(
        execution_cycle,
        "consume_fast_paper_shadow_service_execution_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "empty decision population must not execute"
        ),
    )

    assert (
        run_fast_paper_shadow_service_execution_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            committed_at_unix_ms=60_000,
        )
        == 0
    )


def test_execution_cycle_waits_for_oldest_missing_source_without_leapfrog(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    first_path = _evidence_file(decision_directory, 1, "a")
    second_path = _evidence_file(decision_directory, 2, "b")
    first = _decision(manifest, sequence=1, fingerprint="a" * 64)
    second = _decision(manifest, sequence=2, fingerprint="b" * 64)

    def read(path):
        if Path(path) == first_path:
            return first
        if Path(path) == second_path:
            return second
        raise AssertionError(path)

    monkeypatch.setattr(
        execution_cycle,
        "read_fast_paper_shadow_decision_evidence",
        read,
    )
    (bootstrap.source_directory / f"{second.evidence_fingerprint_sha256}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        execution_cycle,
        "consume_fast_paper_shadow_service_execution_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "later source authority must not leapfrog the oldest pending decision"
        ),
    )

    assert (
        run_fast_paper_shadow_service_execution_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            committed_at_unix_ms=60_000,
        )
        == 0
    )


def test_execution_cycle_consumes_exact_oldest_available_source_once(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    first_path = _evidence_file(decision_directory, 1, "a")
    _evidence_file(decision_directory, 2, "b")
    first = _decision(manifest, sequence=1, fingerprint="a" * 64)
    second = _decision(manifest, sequence=2, fingerprint="b" * 64)
    (bootstrap.source_directory / f"{first.evidence_fingerprint_sha256}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (bootstrap.source_directory / f"{second.evidence_fingerprint_sha256}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        execution_cycle,
        "read_fast_paper_shadow_decision_evidence",
        lambda path: (
            first if Path(path) == first_path else second
        ),
    )
    captured: dict[str, object] = {}

    def consume(
        manifest_arg,
        binding,
        execution_policy,
        decision_evidence,
        *,
        source_directory,
        committed_at_unix_ms,
    ):
        captured.update(
            manifest=manifest_arg,
            binding=binding,
            execution_policy=execution_policy,
            decision=decision_evidence,
            source_directory=source_directory,
            committed_at_unix_ms=committed_at_unix_ms,
        )
        return object()

    monkeypatch.setattr(
        execution_cycle,
        "consume_fast_paper_shadow_service_execution_source_record",
        consume,
    )

    assert (
        run_fast_paper_shadow_service_execution_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            committed_at_unix_ms=60_000,
        )
        == 1
    )
    assert captured["manifest"] is manifest
    assert captured["binding"] == bootstrap.binding
    assert captured["execution_policy"] == bootstrap.execution_policy
    assert captured["decision"] is first
    assert captured["source_directory"] == bootstrap.source_directory
    assert captured["committed_at_unix_ms"] == 60_000


def test_execution_cycle_skips_already_processed_decisions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    first_path = _evidence_file(decision_directory, 1, "a")
    second_path = _evidence_file(decision_directory, 2, "b")
    first = _decision(manifest, sequence=1, fingerprint="a" * 64)
    second = _decision(manifest, sequence=2, fingerprint="b" * 64)

    advanced_runtime = build_fast_paper_shadow_runtime_state(
        manifest,
        bootstrap.binding,
        bootstrap.checkpoint,
        market_positions=bootstrap.runtime_state.market_positions,
        execution_policy_fingerprint_sha256=(
            bootstrap.execution_policy.policy_fingerprint_sha256
        ),
        pending_buy=bootstrap.runtime_state.pending_buy,
        last_processed_source_sequence=1,
        last_processed_source_event_id=first.source_event_id,
        last_processed_decision_evidence_fingerprint_sha256=(
            first.evidence_fingerprint_sha256
        ),
    )
    advanced_bootstrap = FastPaperShadowServiceExecutionBootstrap(
        binding=bootstrap.binding,
        execution_policy=bootstrap.execution_policy,
        checkpoint=bootstrap.checkpoint,
        runtime_state=advanced_runtime,
        source_directory=bootstrap.source_directory,
    )
    (bootstrap.source_directory / f"{second.evidence_fingerprint_sha256}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        execution_cycle,
        "read_fast_paper_shadow_decision_evidence",
        lambda path: (
            first if Path(path) == first_path else second
        ),
    )
    consumed: list[object] = []
    monkeypatch.setattr(
        execution_cycle,
        "consume_fast_paper_shadow_service_execution_source_record",
        lambda *_args, **kwargs: consumed.append(
            kwargs.get("decision_evidence")
        ),
    )

    assert (
        run_fast_paper_shadow_service_execution_cycle(
            manifest,
            advanced_bootstrap,
            decision_evidence_directory=decision_directory,
            committed_at_unix_ms=60_000,
        )
        == 1
    )
    assert len(consumed) == 1


def test_execution_cycle_rejects_foreign_decision_before_source_wait(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    path = _evidence_file(decision_directory, 1, "foreign")
    decision = _decision(manifest, sequence=1, fingerprint="c" * 64)
    decision.manifest_fingerprint_sha256 = "d" * 64

    monkeypatch.setattr(
        execution_cycle,
        "read_fast_paper_shadow_decision_evidence",
        lambda source: decision if Path(source) == path else pytest.fail(),
    )
    monkeypatch.setattr(
        execution_cycle,
        "consume_fast_paper_shadow_service_execution_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "foreign decision must fail before execution"
        ),
    )

    with pytest.raises(ValueError, match="manifest"):
        run_fast_paper_shadow_service_execution_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            committed_at_unix_ms=60_000,
        )


def test_execution_cycle_rejects_source_symlink(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    path = _evidence_file(decision_directory, 1, "a")
    decision = _decision(manifest, sequence=1, fingerprint="a" * 64)
    target = tmp_path / "source-target.json"
    target.write_text("{}\n", encoding="utf-8")
    source = bootstrap.source_directory / f"{decision.evidence_fingerprint_sha256}.json"
    source.symlink_to(target)

    monkeypatch.setattr(
        execution_cycle,
        "read_fast_paper_shadow_decision_evidence",
        lambda source_path: decision if Path(source_path) == path else pytest.fail(),
    )
    monkeypatch.setattr(
        execution_cycle,
        "consume_fast_paper_shadow_service_execution_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "source symlink must fail before consumer"
        ),
    )

    with pytest.raises(ValueError, match="source|symlink"):
        run_fast_paper_shadow_service_execution_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            committed_at_unix_ms=60_000,
        )


def test_execution_cycle_source_has_consumer_only_authority() -> None:
    source = Path(execution_cycle.__file__).read_text(encoding="utf-8")
    required = (
        "read_fast_paper_shadow_decision_evidence",
        "consume_fast_paper_shadow_service_execution_source_record",
    )
    for marker in required:
        assert marker in source

    forbidden = (
        "produce_fast_paper_shadow_execution_input_source_record",
        "write_fast_paper_shadow_execution_input_source_record",
        "execute_fast_paper_shadow_decision",
        "commit_fast_paper_shadow_transition_atomically",
        "shreks_brain.scoring",
        "score_candidate",
        "requests",
        "httpx",
        "urllib",
        "sqlite3",
        "RuntimeMode.LIVE",
    )
    for marker in forbidden:
        assert marker not in source
