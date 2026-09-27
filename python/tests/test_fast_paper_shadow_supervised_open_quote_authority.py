from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service as service
import shreks_brain.fast_paper_runtime.shadow_service_coordinator as coordinator
import shreks_brain.fast_paper_runtime.shadow_supervisor as supervisor
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime.persisted_quotes import (
    FastPaperShadowReductionRead,
)
from shreks_brain.fast_paper_runtime.shadow_service_coordinator import (
    FastPaperShadowServiceCoordinatorResult,
)

from test_fast_paper_shadow_coordinator_reduction_source import (
    _open_execution_bootstrap,
)
from test_fast_paper_shadow_service_coordinator import (
    _decision_bootstrap as _coordinator_decision_bootstrap,
    _decision_config,
    _execution_config,
)
from test_fast_paper_shadow_service_reduction_reads import (
    _fixture as _service_fixture,
)
from test_fast_paper_shadow_supervisor import (
    _buy_writer_policy,
    _config as _supervisor_config,
    _decision_bootstrap as _supervisor_decision_bootstrap,
    _execution_bootstrap as _supervisor_execution_bootstrap,
)


def _read(target: float = 0.25, amount: int = 10_000_000):
    return FastPaperShadowReductionRead(
        target_exposure_fraction=target,
        input_amount_raw=amount,
    )


def test_service_open_posture_uses_explicit_dynamic_full_exit_raw(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, _record, captured = _service_fixture(
        monkeypatch,
        tmp_path,
    )
    position = FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=0.75,
    )
    reads = (_read(),)
    calls: list[object] = []

    service.run_fast_paper_shadow_service_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: 1_050,
        position_resolver=lambda _record: position,
        exit_input_amount_resolver=lambda record, supplied_position: (
            calls.append((record, supplied_position)) or 20_000_000
        ),
        reduction_read_resolver=lambda *_args: reads,
    )

    assert len(calls) == 1
    assert calls[0][1] == position
    assert captured["read_policy"].exit_input_amount_raw == 20_000_000
    assert captured["read_policy"].reduction_reads == reads


def test_service_flat_posture_never_calls_dynamic_full_exit_resolver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, _record, captured = _service_fixture(
        monkeypatch,
        tmp_path,
    )

    service.run_fast_paper_shadow_service_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: 1_050,
        position_resolver=lambda _record: FastCampaignDecisionPosition(
            kind="FLAT"
        ),
        exit_input_amount_resolver=lambda *_args: pytest.fail(
            "FLAT posture must not request dynamic full-exit authority"
        ),
    )

    assert (
        captured["read_policy"].exit_input_amount_raw
        == bootstrap.policy.exit_input_amount_raw
    )


def test_coordinator_consumes_v2_full_exit_and_reduction_reads_from_same_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _coordinator_decision_bootstrap()
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
    reads = (_read(),)
    source = SimpleNamespace(
        exit_input_amount_raw=20_000_000,
        reduction_reads=reads,
    )
    source_directory = tmp_path / "reduction-sources"
    source_directory.mkdir()
    reads_seen = 0

    def read_source(*_args, **_kwargs):
        nonlocal reads_seen
        reads_seen += 1
        return source

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
        exit_input_amount_resolver,
    ):
        resolved = position_resolver(record)
        assert resolved == position
        assert exit_input_amount_resolver(record, resolved) == 20_000_000
        assert reduction_read_resolver(record, resolved) == reads
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
    assert reads_seen == 1


def test_supervisor_runs_open_quote_writer_before_open_publisher_and_coordinator(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for name in (
        "decision",
        "execution-sources",
        "buy-authority-sources",
        "quote-usd-sources",
        "reduction-sources",
        "retry-sources",
    ):
        (tmp_path / name).mkdir()
    config = _supervisor_config(tmp_path)
    before = supervisor.FastPaperShadowSupervisorBootstrap(
        decision_bootstrap=_supervisor_decision_bootstrap(),
        execution_bootstrap=_supervisor_execution_bootstrap(),
        buy_writer_policy=_buy_writer_policy(tmp_path),
    )
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_skip_source_publisher_cycle",
        lambda *_args, **_kwargs: events.append(("skip", None)) or 0,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_buy_authority_writer_cycle",
        lambda *_args, **_kwargs: events.append(("buy-writer", None)) or 0,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_buy_source_publisher_cycle",
        lambda *_args, **_kwargs: events.append(("buy", None)) or 0,
    )

    def open_writer(
        decision_bootstrap,
        execution_bootstrap,
        *,
        reduction_source_directory,
        clock_unix_ms,
    ):
        events.append(
            (
                "open-writer",
                (
                    decision_bootstrap,
                    execution_bootstrap,
                    reduction_source_directory,
                    clock_unix_ms(),
                ),
            )
        )
        return 1

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_open_quote_writer_cycle",
        open_writer,
        raising=False,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_open_source_publisher_cycle",
        lambda *_args, **_kwargs: events.append(("open", None)) or 0,
    )

    def coordinated(decision_bootstrap, *_args, **_kwargs):
        events.append(("coordinator", None))
        return FastPaperShadowServiceCoordinatorResult(
            decision_bootstrap=decision_bootstrap,
            execution_bootstrap=before.execution_bootstrap,
            decisions_produced=0,
            executions_committed=0,
        )

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_service_coordinated_cycle",
        coordinated,
    )

    supervisor.run_fast_paper_shadow_supervisor_cycle(
        before,
        config,
        clock_unix_ms=lambda: 25_000,
    )

    assert [name for name, _value in events] == [
        "skip",
        "buy-writer",
        "buy",
        "open-writer",
        "open",
        "coordinator",
    ]
    writer_args = events[3][1]
    assert writer_args[0] is before.decision_bootstrap
    assert writer_args[1] is before.execution_bootstrap
    assert writer_args[2] == config.reduction_source_directory
    assert writer_args[3] == 25_000


def test_supervised_open_quote_authority_has_no_float_to_raw_or_live_path() -> None:
    service_source = Path(service.__file__).read_text(encoding="utf-8")
    coordinator_source = Path(coordinator.__file__).read_text(encoding="utf-8")
    supervisor_source = Path(supervisor.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "decimal_quantity_to_raw",
        "float_to_raw",
        "int(position.quantity",
        "round(position.quantity",
        "shreks_brain.scoring",
        "score_candidate",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in service_source
        assert forbidden not in coordinator_source
        assert forbidden not in supervisor_source
