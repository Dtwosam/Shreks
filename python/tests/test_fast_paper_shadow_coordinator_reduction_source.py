from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_coordinator as coordinator
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime.persisted_quotes import (
    FastPaperShadowReductionRead,
)

from test_fast_paper_shadow_service_coordinator import (
    _decision_bootstrap,
    _decision_config,
    _execution_bootstrap,
    _execution_config,
)


def _open_execution_bootstrap():
    return _execution_bootstrap(
        None,
        market_positions=(
            SimpleNamespace(
                market_key="pump_fun_bonding_curve:Mint111:Quote111",
            ),
        ),
    )


def test_coordinator_reads_exact_open_reduction_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap()
    execution_bootstrap = _open_execution_bootstrap()
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    record = SimpleNamespace(
        venue="pump_fun_bonding_curve",
        mint="Mint111",
        quote_mint="Quote111",
    )
    position = FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=0.75,
    )
    monkeypatch.setattr(
        coordinator,
        "fast_paper_shadow_decision_position",
        lambda *_args: position,
    )
    reads = (
        FastPaperShadowReductionRead(
            target_exposure_fraction=0.25,
            input_amount_raw=10_000_000,
        ),
    )
    source_directory = tmp_path / "reduction-sources"
    source_directory.mkdir()
    captured: dict[str, object] = {}

    def read_source(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        market_key,
        directory,
    ):
        captured.update(
            manifest=manifest,
            binding=binding,
            checkpoint=checkpoint,
            runtime_state=runtime_state,
            market_key=market_key,
            directory=directory,
        )
        return SimpleNamespace(reduction_reads=reads)

    monkeypatch.setattr(
        coordinator,
        "read_fast_paper_shadow_reduction_source_record",
        read_source,
    )
    updated = SimpleNamespace(
        manifest=decision_bootstrap.manifest,
        policy=decision_bootstrap.policy,
        state=SimpleNamespace(
            cursor=SimpleNamespace(decision_sequence=1),
        ),
    )

    def run_decision(
        _bootstrap,
        _config,
        *,
        clock_unix_ms,
        position_resolver,
        reduction_read_resolver,
    ):
        resolved_position = position_resolver(record)
        assert resolved_position == position
        assert reduction_read_resolver(record, resolved_position) == reads
        return updated, 1

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        run_decision,
    )

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        reduction_source_directory=source_directory,
        committed_at_unix_ms=20_000,
    )

    assert result.decisions_produced == 1
    assert captured["manifest"] is decision_bootstrap.manifest
    assert captured["binding"] is execution_bootstrap.binding
    assert captured["checkpoint"] is execution_bootstrap.checkpoint
    assert captured["runtime_state"] is execution_bootstrap.runtime_state
    assert (
        captured["market_key"]
        == "pump_fun_bonding_curve:Mint111:Quote111"
    )
    assert captured["directory"] == source_directory.resolve()


def test_coordinator_flat_posture_does_not_read_reduction_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap()
    execution_bootstrap = _execution_bootstrap(None)
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    monkeypatch.setattr(
        coordinator,
        "fast_paper_shadow_decision_position",
        lambda *_args: FastCampaignDecisionPosition(kind="FLAT"),
    )
    source_directory = tmp_path / "reduction-sources"
    source_directory.mkdir()
    monkeypatch.setattr(
        coordinator,
        "read_fast_paper_shadow_reduction_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "FLAT posture must not read reduction source authority"
        ),
    )
    updated = SimpleNamespace(
        manifest=decision_bootstrap.manifest,
        policy=decision_bootstrap.policy,
        state=SimpleNamespace(
            cursor=SimpleNamespace(decision_sequence=1),
        ),
    )

    def run_decision(
        _bootstrap,
        _config,
        *,
        clock_unix_ms,
        position_resolver,
        reduction_read_resolver,
    ):
        record = SimpleNamespace(
            venue="pump_fun_bonding_curve",
            mint="Mint111",
            quote_mint="Quote111",
        )
        position = position_resolver(record)
        assert position.kind == "FLAT"
        assert reduction_read_resolver(record, position) == ()
        return updated, 1

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        run_decision,
    )

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        reduction_source_directory=source_directory,
        committed_at_unix_ms=20_000,
    )
    assert result.decisions_produced == 1


def test_coordinator_rejects_dual_reduction_authority(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "reduction-sources"
    source_directory.mkdir()
    with pytest.raises(ValueError, match="either|both|reduction"):
        coordinator.run_fast_paper_shadow_service_coordinated_cycle(
            _decision_bootstrap(),
            _decision_config(tmp_path),
            _execution_config(tmp_path),
            reduction_read_resolver=lambda *_args: (),
            reduction_source_directory=source_directory,
            committed_at_unix_ms=20_000,
        )


def test_coordinator_execution_catchup_never_reads_reduction_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    before = _execution_bootstrap(None)
    after = _execution_bootstrap(1)
    bootstraps = iter((before, after))
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: next(bootstraps),
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_execution_cycle",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        coordinator,
        "read_fast_paper_shadow_reduction_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "execution catch-up must not read reduction source authority"
        ),
    )
    source_directory = tmp_path / "reduction-sources"
    source_directory.mkdir()

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        reduction_source_directory=source_directory,
        committed_at_unix_ms=20_000,
    )
    assert result.decisions_produced == 0
    assert result.executions_committed == 1


def test_coordinator_reduction_source_is_read_only() -> None:
    payload = Path(coordinator.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "build_fast_paper_shadow_reduction_source_record",
        "write_fast_paper_shadow_reduction_source_record",
        "FastPaperShadowReductionRead(",
        "decimal_quantity_to_raw",
        "input_amount_raw=",
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in payload
