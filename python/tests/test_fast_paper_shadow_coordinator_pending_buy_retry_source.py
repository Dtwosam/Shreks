from __future__ import annotations

import hashlib
import json
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
            state_fingerprint_sha256="b" * 64,
            last_processed_source_sequence=execution_sequence,
            pending_buy=pending_buy,
            market_positions=(),
        ),
    )


def _pending():
    return SimpleNamespace(
        source_event_id="pending-event-1",
        market_key="pump_fun_bonding_curve:Mint111:Quote111",
        mint="Mint111",
        target_exposure_fraction=0.5,
    )


def _current_source_path(
    directory: Path,
    *,
    runtime_fingerprint: str = "b" * 64,
    source_event_id: str = "pending-event-1",
) -> Path:
    raw = json.dumps(
        {
            "pending_source_event_id": source_event_id,
            "runtime_state_fingerprint_sha256": runtime_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return directory / f"{hashlib.sha256(raw).hexdigest()}.json"


def test_coordinator_reads_exact_pending_buy_retry_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    before = _execution_bootstrap(
        checkpoint_sequence=7,
        execution_sequence=1,
        pending_buy=_pending(),
    )
    after = _execution_bootstrap(
        checkpoint_sequence=8,
        execution_sequence=1,
        pending_buy=None,
    )
    bootstraps = iter((before, after))
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: next(bootstraps),
    )

    source_directory = tmp_path / "retry-sources"
    source_directory.mkdir()
    _current_source_path(source_directory).write_text("{}\n", encoding="utf-8")

    retry_input = object()
    captured: dict[str, object] = {}

    def read_source(
        manifest,
        binding,
        execution_policy,
        checkpoint,
        runtime_state,
        directory,
    ):
        captured.update(
            reader_manifest=manifest,
            reader_binding=binding,
            reader_policy=execution_policy,
            reader_checkpoint=checkpoint,
            reader_runtime=runtime_state,
            reader_directory=directory,
        )
        return SimpleNamespace(retry_input=retry_input)

    monkeypatch.setattr(
        coordinator,
        "read_fast_paper_shadow_pending_buy_retry_source_record",
        read_source,
        raising=False,
    )

    def retry_service(
        manifest,
        binding,
        execution_policy,
        retry,
        *,
        committed_at_unix_ms,
    ):
        captured.update(
            service_manifest=manifest,
            service_binding=binding,
            service_policy=execution_policy,
            service_retry=retry,
            committed_at_unix_ms=committed_at_unix_ms,
        )
        return object()

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_pending_buy_retry",
        retry_service,
    )
    monkeypatch.setattr(
        coordinator,
        "read_fast_paper_shadow_reduction_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "pending BUY retry must not touch reduction source authority"
        ),
    )

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        pending_buy_retry_source_directory=source_directory,
        reduction_source_directory=tmp_path / "missing-and-irrelevant",
        committed_at_unix_ms=25_000,
    )

    assert result.decision_bootstrap is decision_bootstrap
    assert result.execution_bootstrap is after
    assert result.decisions_produced == 0
    assert result.executions_committed == 1
    assert captured["reader_manifest"] is decision_bootstrap.manifest
    assert captured["reader_binding"] is before.binding
    assert captured["reader_policy"] is before.execution_policy
    assert captured["reader_checkpoint"] is before.checkpoint
    assert captured["reader_runtime"] is before.runtime_state
    assert captured["reader_directory"] == source_directory.resolve()
    assert captured["service_manifest"] is decision_bootstrap.manifest
    assert captured["service_binding"] is before.binding
    assert captured["service_policy"] is before.execution_policy
    assert captured["service_retry"] is retry_input
    assert captured["committed_at_unix_ms"] == 25_000


def test_coordinator_missing_current_retry_source_is_backpressure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    execution_bootstrap = _execution_bootstrap(
        checkpoint_sequence=7,
        execution_sequence=1,
        pending_buy=_pending(),
    )
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    monkeypatch.setattr(
        coordinator,
        "read_fast_paper_shadow_pending_buy_retry_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "missing exact source must be backpressure before strict read"
        ),
        raising=False,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_pending_buy_retry",
        lambda *_args, **_kwargs: pytest.fail(
            "missing retry source must not invoke retry transaction"
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "pending BUY backpressure must block new decisions"
        ),
    )

    source_directory = tmp_path / "retry-sources"
    source_directory.mkdir()

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        pending_buy_retry_source_directory=source_directory,
        committed_at_unix_ms=25_000,
    )

    assert result.decision_bootstrap is decision_bootstrap
    assert result.execution_bootstrap is execution_bootstrap
    assert result.decisions_produced == 0
    assert result.executions_committed == 0


def test_coordinator_rejects_dual_pending_buy_retry_authority(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "retry-sources"
    source_directory.mkdir()

    with pytest.raises(ValueError, match="either|both|retry"):
        coordinator.run_fast_paper_shadow_service_coordinated_cycle(
            _decision_bootstrap(1),
            _decision_config(tmp_path),
            _execution_config(tmp_path),
            pending_buy_retry_resolver=lambda _bootstrap: None,
            pending_buy_retry_source_directory=source_directory,
            committed_at_unix_ms=25_000,
        )


def test_coordinator_without_pending_buy_does_not_touch_retry_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap()
    execution_bootstrap = _execution_bootstrap(
        checkpoint_sequence=7,
        execution_sequence=None,
        pending_buy=None,
    )
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    monkeypatch.setattr(
        coordinator,
        "read_fast_paper_shadow_pending_buy_retry_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "no pending BUY must not read retry source"
        ),
        raising=False,
    )

    updated = SimpleNamespace(
        manifest=decision_bootstrap.manifest,
        policy=decision_bootstrap.policy,
        state=SimpleNamespace(
            cursor=SimpleNamespace(decision_sequence=1),
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: (updated, 1),
    )

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        pending_buy_retry_source_directory=tmp_path / "missing-and-irrelevant",
        committed_at_unix_ms=25_000,
    )

    assert result.decisions_produced == 1


def test_coordinator_pending_buy_retry_source_is_read_only() -> None:
    payload = Path(coordinator.__file__).read_text(encoding="utf-8")
    assert "read_fast_paper_shadow_pending_buy_retry_source_record" in payload

    for forbidden in (
        "build_fast_paper_shadow_pending_buy_retry_source_record",
        "write_fast_paper_shadow_pending_buy_retry_source_record",
        "FastPaperShadowPendingBuyRetryInput(",
        "derive_paper_risk_accounting_facts",
        "retry_fast_paper_shadow_pending_buy(",
        "RiskContext(",
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in payload
