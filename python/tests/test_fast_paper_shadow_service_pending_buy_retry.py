from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_execution as service_execution
from shreks_brain.fast_paper_runtime import (
    run_fast_paper_shadow_service_pending_buy_retry,
)


def _fixtures() -> SimpleNamespace:
    return SimpleNamespace(
        manifest=object(),
        binding=object(),
        execution_policy=object(),
        retry=object(),
        checkpoint=SimpleNamespace(
            sequence=9,
            payload_sha256="a" * 64,
        ),
        runtime_state=SimpleNamespace(
            state_fingerprint_sha256="b" * 64,
        ),
        transition=SimpleNamespace(replayed=False),
        commit_result=object(),
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

    def retry(
        manifest,
        execution_policy,
        binding,
        checkpoint,
        runtime_state,
        retry_input,
    ):
        captured.update(
            retry_manifest=manifest,
            retry_execution_policy=execution_policy,
            retry_binding=binding,
            retry_checkpoint=checkpoint,
            retry_runtime_state=runtime_state,
            retry_input=retry_input,
        )
        return values.transition

    monkeypatch.setattr(
        service_execution,
        "retry_fast_paper_shadow_pending_buy",
        retry,
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


def test_shadow_service_pending_buy_retry_executes_exact_retry_and_commits(
    monkeypatch,
) -> None:
    values = _fixtures()
    captured = _install_happy_path(monkeypatch, values)

    result = run_fast_paper_shadow_service_pending_buy_retry(
        values.manifest,
        values.binding,
        values.execution_policy,
        values.retry,
        committed_at_unix_ms=25_000,
    )

    assert result is values.commit_result
    assert captured["checkpoint_manifest"] is values.manifest
    assert captured["runtime_manifest"] is values.manifest
    assert captured["retry_manifest"] is values.manifest
    assert captured["retry_execution_policy"] is values.execution_policy
    assert captured["retry_binding"] is values.binding
    assert captured["retry_checkpoint"] is values.checkpoint
    assert captured["retry_runtime_state"] is values.runtime_state
    assert captured["retry_input"] is values.retry
    assert captured["commit_checkpoint"] is values.checkpoint
    assert captured["commit_runtime_state"] is values.runtime_state
    assert captured["commit_transition"] is values.transition
    assert captured["commit_sequence"] == 10
    assert captured["commit_created_at_unix_ms"] == 25_000


@pytest.mark.parametrize(
    ("missing_name", "checkpoint", "runtime_state"),
    (
        ("checkpoint", None, SimpleNamespace(state_fingerprint_sha256="b" * 64)),
        (
            "runtime state",
            SimpleNamespace(sequence=9, payload_sha256="a" * 64),
            None,
        ),
    ),
)
def test_shadow_service_pending_buy_retry_requires_exact_durable_pair_before_retry(
    monkeypatch,
    missing_name: str,
    checkpoint: object,
    runtime_state: object,
) -> None:
    values = _fixtures()
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
        "retry_fast_paper_shadow_pending_buy",
        lambda *_args, **_kwargs: pytest.fail(
            "missing durable pair must fail before retry"
        ),
        raising=False,
    )

    with pytest.raises(ValueError, match=missing_name):
        run_fast_paper_shadow_service_pending_buy_retry(
            values.manifest,
            values.binding,
            values.execution_policy,
            values.retry,
            committed_at_unix_ms=25_000,
        )


def test_shadow_service_pending_buy_retry_failure_never_commits(
    monkeypatch,
) -> None:
    values = _fixtures()
    _install_happy_path(monkeypatch, values)
    monkeypatch.setattr(
        service_execution,
        "retry_fast_paper_shadow_pending_buy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("retry facts are stale")
        ),
    )
    monkeypatch.setattr(
        service_execution,
        "commit_fast_paper_shadow_transition_atomically",
        lambda *_args, **_kwargs: pytest.fail(
            "failed retry must not reach atomic commit"
        ),
    )

    with pytest.raises(ValueError, match="stale"):
        run_fast_paper_shadow_service_pending_buy_retry(
            values.manifest,
            values.binding,
            values.execution_policy,
            values.retry,
            committed_at_unix_ms=25_000,
        )


def test_shadow_service_pending_buy_retry_has_no_new_authority_dependencies() -> None:
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
