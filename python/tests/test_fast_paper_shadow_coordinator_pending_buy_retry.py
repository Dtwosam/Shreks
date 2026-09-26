from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_coordinator as coordinator

from test_fast_paper_shadow_service_coordinator import (
    _decision_bootstrap,
    _decision_config,
    _execution_config,
)


def _execution_bootstrap(
    *,
    checkpoint_sequence: int,
    execution_sequence: int | None,
    pending_buy,
):
    return SimpleNamespace(
        binding=object(),
        execution_policy=object(),
        checkpoint=SimpleNamespace(sequence=checkpoint_sequence),
        source_directory=Path("/tmp/execution-sources"),
        runtime_state=SimpleNamespace(
            last_processed_source_sequence=execution_sequence,
            pending_buy=pending_buy,
            market_positions=(),
        ),
    )


def test_coordinator_pending_buy_retry_commits_before_new_decision(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    before = _execution_bootstrap(
        checkpoint_sequence=7,
        execution_sequence=1,
        pending_buy=object(),
    )
    after = _execution_bootstrap(
        checkpoint_sequence=8,
        execution_sequence=1,
        pending_buy=None,
    )
    bootstraps = iter((before, after))
    retry_input = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: next(bootstraps),
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "pending BUY retry must block new decision production"
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "read_fast_paper_shadow_reduction_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "pending BUY retry must not touch reduction source authority"
        ),
    )

    def retry_service(
        manifest,
        binding,
        execution_policy,
        supplied_retry,
        *,
        committed_at_unix_ms,
    ):
        captured.update(
            manifest=manifest,
            binding=binding,
            execution_policy=execution_policy,
            retry=supplied_retry,
            committed_at_unix_ms=committed_at_unix_ms,
        )
        return object()

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_pending_buy_retry",
        retry_service,
        raising=False,
    )

    def retry_resolver(execution_bootstrap):
        captured["resolver_bootstrap"] = execution_bootstrap
        return retry_input

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        pending_buy_retry_resolver=retry_resolver,
        reduction_source_directory=tmp_path / "missing-and-irrelevant",
        committed_at_unix_ms=25_000,
    )

    assert result.decision_bootstrap is decision_bootstrap
    assert result.execution_bootstrap is after
    assert result.decisions_produced == 0
    assert result.executions_committed == 1
    assert captured["resolver_bootstrap"] is before
    assert captured["manifest"] is decision_bootstrap.manifest
    assert captured["binding"] is before.binding
    assert captured["execution_policy"] is before.execution_policy
    assert captured["retry"] is retry_input
    assert captured["committed_at_unix_ms"] == 25_000


def test_coordinator_pending_buy_retry_missing_facts_is_backpressure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    execution_bootstrap = _execution_bootstrap(
        checkpoint_sequence=7,
        execution_sequence=1,
        pending_buy=object(),
    )
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_pending_buy_retry",
        lambda *_args, **_kwargs: pytest.fail(
            "missing retry facts must not invoke the retry transaction"
        ),
        raising=False,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "pending BUY backpressure must block decision production"
        ),
    )

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        pending_buy_retry_resolver=lambda _bootstrap: None,
        committed_at_unix_ms=25_000,
    )

    assert result.decision_bootstrap is decision_bootstrap
    assert result.execution_bootstrap is execution_bootstrap
    assert result.decisions_produced == 0
    assert result.executions_committed == 0


def test_coordinator_pending_buy_without_retry_resolver_still_fails_closed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    execution_bootstrap = _execution_bootstrap(
        checkpoint_sequence=7,
        execution_sequence=1,
        pending_buy=object(),
    )
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )

    with pytest.raises(ValueError, match="pending BUY|retry"):
        coordinator.run_fast_paper_shadow_service_coordinated_cycle(
            decision_bootstrap,
            _decision_config(tmp_path),
            _execution_config(tmp_path),
            committed_at_unix_ms=25_000,
        )


@pytest.mark.parametrize(
    ("after_checkpoint_sequence", "after_execution_sequence", "match"),
    (
        (7, 1, "checkpoint|advance"),
        (9, 1, "checkpoint|advance"),
        (8, 2, "cursor|execution"),
    ),
)
def test_coordinator_pending_buy_retry_requires_exact_durable_progress(
    monkeypatch,
    tmp_path: Path,
    after_checkpoint_sequence: int,
    after_execution_sequence: int,
    match: str,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    before = _execution_bootstrap(
        checkpoint_sequence=7,
        execution_sequence=1,
        pending_buy=object(),
    )
    after = _execution_bootstrap(
        checkpoint_sequence=after_checkpoint_sequence,
        execution_sequence=after_execution_sequence,
        pending_buy=None,
    )
    bootstraps = iter((before, after))

    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: next(bootstraps),
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_pending_buy_retry",
        lambda *_args, **_kwargs: object(),
        raising=False,
    )

    with pytest.raises(ValueError, match=match):
        coordinator.run_fast_paper_shadow_service_coordinated_cycle(
            decision_bootstrap,
            _decision_config(tmp_path),
            _execution_config(tmp_path),
            pending_buy_retry_resolver=lambda _bootstrap: object(),
            committed_at_unix_ms=25_000,
        )


def test_coordinator_pending_buy_retry_source_has_orchestration_authority_only() -> None:
    source = Path(coordinator.__file__).read_text(encoding="utf-8")
    assert "run_fast_paper_shadow_service_pending_buy_retry" in source

    for forbidden in (
        "retry_fast_paper_shadow_pending_buy(",
        "FastPaperShadowPendingBuyRetryInput(",
        "RiskContext(",
        "FastPaperShadowQuoteUsdEvidence(",
        "FastPaperShadowQuoteEvidence(",
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
