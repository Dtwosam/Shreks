from __future__ import annotations

import json
from pathlib import Path
from threading import Event

import pytest

import shreks_brain.observer_campaign.runtime as runtime_module
from shreks_brain.observer_campaign.coordinator import ObserverPaperCampaignCoordinatorRunner
from shreks_brain.observer_campaign.runtime import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_STATUS_SCHEMA_VERSION,
    ObserverPaperCampaignRuntimeError,
    bootstrap_observer_paper_campaign_runtime,
    main,
    preflight_observer_paper_campaign_runtime,
    run_observer_paper_campaign_runtime,
)
from shreks_brain.observer_campaign.runtime_config import ObserverPaperCampaignRuntimeConfig
from shreks_brain.observer_campaign.runtime_manifest import (
    encode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.paper_validation import load_latest_paper_checkpoint

from test_observer_campaign_coordinator_assembly import _seed_two_candidates
from test_observer_campaign_runner import AS_OF, RUN_ID
from test_observer_campaign_runtime_manifest import _manifest


def _runtime_config(tmp_path: Path, *, max_cycles: int | None) -> ObserverPaperCampaignRuntimeConfig:
    database = tmp_path / "observer.sqlite"
    evidence = tmp_path / "e11.json"
    manifest_path = tmp_path / "paper-campaign.json"
    _seed_two_candidates(database)
    manifest_path.write_bytes(encode_observer_paper_campaign_runtime_manifest(_manifest()))
    return ObserverPaperCampaignRuntimeConfig(
        observer_database_path=database.resolve(),
        evidence_path=evidence.resolve(),
        manifest_path=manifest_path.resolve(),
        cycle_interval_seconds=0.001,
        max_cycles=max_cycles,
    )


def test_bootstrap_decodes_manifest_constructs_exact_sealed_runner_and_restores_state(
    tmp_path: Path,
) -> None:
    config = _runtime_config(tmp_path, max_cycles=1)

    bootstrap = bootstrap_observer_paper_campaign_runtime(config)

    assert type(bootstrap.runner) is ObserverPaperCampaignCoordinatorRunner
    assert bootstrap.manifest == _manifest()
    assert bootstrap.restored_state == _manifest().initial_state


def test_runtime_uses_one_timestamp_once_per_iteration_and_stops_at_finite_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _runtime_config(tmp_path, max_cycles=2)
    timestamps = iter((AS_OF, AS_OF + 1))
    clock_calls = 0
    run_calls: list[tuple[int, int]] = []
    real_run_cycle = ObserverPaperCampaignCoordinatorRunner.run_cycle

    def clock() -> int:
        nonlocal clock_calls
        clock_calls += 1
        return next(timestamps)

    def recording_run_cycle(self, as_of_unix_ms: int, created_at_unix_ms: int):
        run_calls.append((as_of_unix_ms, created_at_unix_ms))
        return real_run_cycle(self, as_of_unix_ms, created_at_unix_ms)

    monkeypatch.setattr(
        ObserverPaperCampaignCoordinatorRunner,
        "run_cycle",
        recording_run_cycle,
    )
    statuses: list[str] = []

    completed = run_observer_paper_campaign_runtime(
        config,
        clock_unix_ms=clock,
        status_sink=statuses.append,
    )

    assert completed == 2
    assert clock_calls == 2
    assert run_calls == [(AS_OF, AS_OF), (AS_OF + 1, AS_OF + 1)]
    checkpoint = load_latest_paper_checkpoint(config.observer_database_path, RUN_ID)
    assert checkpoint is not None and checkpoint.sequence == 2
    assert len(statuses) == 2


def test_restart_bootstrap_restores_durable_checkpoint_before_more_work(tmp_path: Path) -> None:
    config = _runtime_config(tmp_path, max_cycles=1)
    first_bootstrap = bootstrap_observer_paper_campaign_runtime(config)
    first_result = first_bootstrap.runner.run_cycle(AS_OF, AS_OF)

    restarted = bootstrap_observer_paper_campaign_runtime(config)

    assert restarted.restored_state == first_result.next_state
    checkpoint = load_latest_paper_checkpoint(config.observer_database_path, RUN_ID)
    assert checkpoint is not None and checkpoint.state == restarted.restored_state


def test_preexisting_stop_request_performs_no_cycle_or_checkpoint(tmp_path: Path) -> None:
    config = _runtime_config(tmp_path, max_cycles=None)
    stop_event = Event()
    stop_event.set()

    completed = run_observer_paper_campaign_runtime(
        config,
        stop_event=stop_event,
        clock_unix_ms=lambda: AS_OF,
        status_sink=lambda _line: pytest.fail("stopped runtime must not emit cycle status"),
    )

    assert completed == 0
    assert load_latest_paper_checkpoint(config.observer_database_path, RUN_ID) is None


def test_status_output_is_exact_paper_runtime_evidence_metadata_without_secrets(
    tmp_path: Path,
) -> None:
    config = _runtime_config(tmp_path, max_cycles=1)
    statuses: list[str] = []

    completed = run_observer_paper_campaign_runtime(
        config,
        clock_unix_ms=lambda: AS_OF,
        status_sink=statuses.append,
    )

    assert completed == 1
    assert len(statuses) == 1
    status = json.loads(statuses[0])
    assert set(status) == {
        "schema_version",
        "mode",
        "paper_run_id",
        "candidate_version",
        "manifest_fingerprint_sha256",
        "completed_cycles",
        "cycle_as_of_unix_ms",
        "state_as_of_unix_ms",
        "evaluated_trade_count",
        "global_risk_halt",
    }
    assert status["schema_version"] == OBSERVER_PAPER_CAMPAIGN_RUNTIME_STATUS_SCHEMA_VERSION
    assert status["mode"] == "PAPER"
    assert status["paper_run_id"] == RUN_ID
    assert status["completed_cycles"] == 1
    assert status["cycle_as_of_unix_ms"] == AS_OF
    assert status["state_as_of_unix_ms"] == AS_OF
    assert "key" not in statuses[0].lower()
    assert "secret" not in statuses[0].lower()
    assert "helius" not in statuses[0].lower()
    assert "jupiter" not in statuses[0].lower()


def test_manifest_and_bootstrap_failures_propagate_fail_closed(tmp_path: Path) -> None:
    config = _runtime_config(tmp_path, max_cycles=1)
    config.manifest_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ObserverPaperCampaignRuntimeError, match="manifest"):
        bootstrap_observer_paper_campaign_runtime(config)


def test_preflight_valid_initial_state_is_read_only_and_emits_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _runtime_config(tmp_path, max_cycles=None)
    monkeypatch.setattr(
        ObserverPaperCampaignCoordinatorRunner,
        "run_cycle",
        lambda *_args, **_kwargs: pytest.fail("preflight must not run a cycle"),
    )
    monkeypatch.setattr(
        ObserverPaperCampaignCoordinatorRunner,
        "evaluated_trades",
        lambda *_args, **_kwargs: pytest.fail("preflight must not normalize evaluated trades"),
    )
    statuses: list[str] = []

    bootstrap = preflight_observer_paper_campaign_runtime(
        config,
        status_sink=statuses.append,
    )

    assert bootstrap.restored_state == _manifest().initial_state
    assert load_latest_paper_checkpoint(config.observer_database_path, RUN_ID) is None
    assert not config.evidence_path.exists()
    assert len(statuses) == 1
    status = json.loads(statuses[0])
    assert set(status) == {
        "schema_version",
        "mode",
        "state",
        "paper_run_id",
        "candidate_version",
        "manifest_fingerprint_sha256",
        "state_as_of_unix_ms",
        "global_risk_halt",
    }
    assert status["schema_version"] == OBSERVER_PAPER_CAMPAIGN_RUNTIME_STATUS_SCHEMA_VERSION
    assert status["mode"] == "PAPER"
    assert status["state"] == "READY"
    assert status["paper_run_id"] == RUN_ID
    assert status["state_as_of_unix_ms"] == _manifest().initial_state.last_cycle_at_unix_ms
    assert "secret" not in statuses[0].lower()
    assert "key" not in statuses[0].lower()


def test_preflight_existing_checkpoint_and_evidence_does_not_advance_or_rewrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _runtime_config(tmp_path, max_cycles=1)
    first = bootstrap_observer_paper_campaign_runtime(config)
    result = first.runner.run_cycle(AS_OF, AS_OF)
    before_checkpoint = load_latest_paper_checkpoint(config.observer_database_path, RUN_ID)
    assert before_checkpoint is not None and before_checkpoint.sequence == 1
    before_evidence = config.evidence_path.read_bytes()

    monkeypatch.setattr(
        ObserverPaperCampaignCoordinatorRunner,
        "run_cycle",
        lambda *_args, **_kwargs: pytest.fail("preflight must not run a cycle"),
    )
    monkeypatch.setattr(
        ObserverPaperCampaignCoordinatorRunner,
        "evaluated_trades",
        lambda *_args, **_kwargs: pytest.fail("preflight must not normalize evaluated trades"),
    )

    restarted = preflight_observer_paper_campaign_runtime(config, status_sink=lambda _line: None)

    after_checkpoint = load_latest_paper_checkpoint(config.observer_database_path, RUN_ID)
    assert after_checkpoint is not None
    assert after_checkpoint.sequence == before_checkpoint.sequence
    assert after_checkpoint.state == result.next_state
    assert restarted.restored_state == result.next_state
    assert config.evidence_path.read_bytes() == before_evidence


def test_preflight_corrupt_evidence_fails_closed_without_advancing_checkpoint(tmp_path: Path) -> None:
    config = _runtime_config(tmp_path, max_cycles=1)
    first = bootstrap_observer_paper_campaign_runtime(config)
    first.runner.run_cycle(AS_OF, AS_OF)
    checkpoint = load_latest_paper_checkpoint(config.observer_database_path, RUN_ID)
    assert checkpoint is not None and checkpoint.sequence == 1
    config.evidence_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ObserverPaperCampaignRuntimeError, match="bootstrap"):
        preflight_observer_paper_campaign_runtime(config, status_sink=lambda _line: None)

    after = load_latest_paper_checkpoint(config.observer_database_path, RUN_ID)
    assert after is not None and after.sequence == checkpoint.sequence


def test_main_preflight_uses_runtime_loader_but_never_enters_cycle_loop(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config = _runtime_config(tmp_path, max_cycles=None)
    monkeypatch.setattr(
        runtime_module,
        "load_observer_paper_campaign_runtime_config",
        lambda: config,
    )
    monkeypatch.setattr(
        runtime_module,
        "run_observer_paper_campaign_runtime",
        lambda *_args, **_kwargs: pytest.fail("--preflight must not enter runtime loop"),
    )

    assert main(["--preflight"]) == 0

    output = capsys.readouterr()
    status = json.loads(output.out.strip())
    assert status["state"] == "READY"
    assert output.err == ""
    assert load_latest_paper_checkpoint(config.observer_database_path, RUN_ID) is None


def test_main_rejects_unknown_arguments_before_loading_runtime_config(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        runtime_module,
        "load_observer_paper_campaign_runtime_config",
        lambda: pytest.fail("unknown arguments must fail before config loading"),
    )

    assert main(["--unknown"]) == 2

    output = capsys.readouterr()
    failure = json.loads(output.err.strip())
    assert failure["state"] == "FAILED"
    assert failure["mode"] == "PAPER"
    assert output.out == ""
