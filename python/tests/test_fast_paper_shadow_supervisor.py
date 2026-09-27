from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_supervisor as supervisor
from shreks_brain.fast_paper_runtime.shadow_service import (
    FastPaperShadowServiceConfig,
)
from shreks_brain.fast_paper_runtime.shadow_service_coordinator import (
    FastPaperShadowServiceCoordinatorResult,
)
from shreks_brain.fast_paper_runtime.shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionConfig,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNIT = _REPO_ROOT / "deploy" / "systemd" / "shreks-fast-paper-shadow.service"
_ENV_EXAMPLE = (
    _REPO_ROOT
    / "deploy"
    / "systemd"
    / "shreks-fast-paper-shadow.env.example"
)


def _buy_writer_policy(tmp_path: Path | None = None):
    root = Path("/tmp") if tmp_path is None else tmp_path
    return SimpleNamespace(
        market_read_policy=object(),
        regime_read_policy=object(),
        regime_policy=object(),
        safety_policy=object(),
        safety_probe_identity=object(),
        execution_economics_policies=(object(),),
        operator_risk_control_path=(root / "operator-control.json").resolve(),
        entry_authority_binary_path=(root / "shreks-fast-entry-authority").resolve(),
        day_started_at_unix_ms=0,
        data_healthy=True,
        execution_healthy=True,
        global_risk_halt=False,
    )


@pytest.fixture(autouse=True)
def _default_source_publishers(monkeypatch):
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_skip_source_publisher_cycle",
        lambda *_args, **_kwargs: 0,
        raising=False,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_buy_authority_writer_cycle",
        lambda *_args, **_kwargs: 0,
        raising=False,
    )
    monkeypatch.setattr(
        supervisor,
        "read_fast_paper_shadow_buy_writer_policy",
        lambda _path: _buy_writer_policy(),
        raising=False,
    )
    monkeypatch.setattr(
        supervisor,
        "verify_fast_paper_shadow_buy_writer_policy_bindings",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_buy_source_publisher_cycle",
        lambda *_args, **_kwargs: 0,
        raising=False,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_open_source_publisher_cycle",
        lambda *_args, **_kwargs: 0,
        raising=False,
    )


def _decision_config(tmp_path: Path):
    return FastPaperShadowServiceConfig(
        manifest_path=(tmp_path / "manifest.json").resolve(),
        policy_path=(tmp_path / "service-policy.json").resolve(),
        evidence_directory=(tmp_path / "decision").resolve(),
        cycle_interval_seconds=2.0,
        maximum_decisions=8,
    )


def _execution_config(tmp_path: Path):
    return FastPaperShadowServiceExecutionConfig(
        execution_policy_path=(tmp_path / "execution-policy.json").resolve(),
        source_directory=(tmp_path / "execution-sources").resolve(),
        ledger_database_path=(tmp_path / "ledger.sqlite3").resolve(),
        run_id="shadow-run-1",
    )


def _config(tmp_path: Path):
    return supervisor.FastPaperShadowSupervisorConfig(
        decision_config=_decision_config(tmp_path),
        execution_config=_execution_config(tmp_path),
        buy_authority_source_directory=(tmp_path / "buy-authority-sources").resolve(),
        quote_usd_source_directory=(tmp_path / "quote-usd-sources").resolve(),
        reduction_source_directory=(tmp_path / "reduction-sources").resolve(),
        pending_buy_retry_source_directory=(
            tmp_path / "retry-sources"
        ).resolve(),
        buy_writer_policy_path=(tmp_path / "buy-writer-policy.json").resolve(),
    )


def _decision_bootstrap():
    return SimpleNamespace(
        policy=SimpleNamespace(),
        manifest=SimpleNamespace(
            manifest_fingerprint_sha256="a" * 64,
            champion_version="champion-v1",
            champion_fingerprint_sha256="b" * 64,
            action_policy=SimpleNamespace(version=7),
        ),
        state=SimpleNamespace(
            cursor=SimpleNamespace(decision_sequence=4),
        ),
    )


def _execution_bootstrap():
    return SimpleNamespace(
        checkpoint=SimpleNamespace(sequence=9),
        runtime_state=SimpleNamespace(
            last_processed_source_sequence=4,
            pending_buy=None,
            market_positions=(),
        ),
    )


def test_supervisor_loads_existing_configs_and_source_directories(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision = _decision_config(tmp_path)
    execution = _execution_config(tmp_path)
    buy_authority = (tmp_path / "buy-authority-sources").resolve()
    quote_usd = (tmp_path / "quote-usd-sources").resolve()
    reduction = (tmp_path / "reduction-sources").resolve()
    retry = (tmp_path / "retry-sources").resolve()
    buy_writer_policy = (tmp_path / "buy-writer-policy.json").resolve()
    env = {
        "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY": str(buy_authority),
        "SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY": str(quote_usd),
        "SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY": str(reduction),
        "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY": str(retry),
        "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH": str(buy_writer_policy),
    }
    captured: dict[str, object] = {}

    def load_decision(supplied):
        captured["decision_env"] = supplied
        return decision

    def load_execution(supplied):
        captured["execution_env"] = supplied
        return execution

    monkeypatch.setattr(
        supervisor,
        "load_fast_paper_shadow_service_config",
        load_decision,
    )
    monkeypatch.setattr(
        supervisor,
        "load_fast_paper_shadow_service_execution_config",
        load_execution,
    )

    config = supervisor.load_fast_paper_shadow_supervisor_config(env)

    assert config.decision_config is decision
    assert config.execution_config is execution
    assert config.buy_authority_source_directory == buy_authority
    assert config.quote_usd_source_directory == quote_usd
    assert config.reduction_source_directory == reduction
    assert config.pending_buy_retry_source_directory == retry
    assert config.buy_writer_policy_path == buy_writer_policy
    assert captured["decision_env"] == env
    assert captured["execution_env"] == env


def test_supervisor_preflight_authenticates_both_bootstraps_without_cycle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for name in ("decision", "execution-sources", "buy-authority-sources", "quote-usd-sources", "reduction-sources", "retry-sources"):
        (tmp_path / name).mkdir()
    config = _config(tmp_path)
    decision = _decision_bootstrap()
    execution = _execution_bootstrap()
    captured: dict[str, object] = {}

    def bootstrap_decision(supplied):
        captured["decision_config"] = supplied
        return decision

    monkeypatch.setattr(
        supervisor,
        "bootstrap_fast_paper_shadow_service",
        bootstrap_decision,
    )
    monkeypatch.setattr(
        supervisor,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda manifest, supplied: (
            captured.update(manifest=manifest, execution_config=supplied)
            or execution
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_service_coordinated_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "preflight must not run a coordinated cycle"
        ),
    )

    bootstrap = supervisor.bootstrap_fast_paper_shadow_supervisor(config)

    assert bootstrap.decision_bootstrap is decision
    assert bootstrap.execution_bootstrap is execution
    assert captured["decision_config"] is config.decision_config
    assert captured["manifest"] is decision.manifest
    assert captured["execution_config"] is config.execution_config


def test_supervisor_cycle_calls_coordinator_once_with_durable_sources(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for name in ("decision", "execution-sources", "buy-authority-sources", "quote-usd-sources", "reduction-sources", "retry-sources"):
        (tmp_path / name).mkdir()
    config = _config(tmp_path)
    before = supervisor.FastPaperShadowSupervisorBootstrap(
        decision_bootstrap=_decision_bootstrap(),
        execution_bootstrap=_execution_bootstrap(),
        buy_writer_policy=_buy_writer_policy(tmp_path),
    )
    after_decision = _decision_bootstrap()
    after_execution = _execution_bootstrap()
    captured: dict[str, object] = {}

    def coordinated(
        decision_bootstrap,
        decision_config,
        execution_config,
        *,
        clock_unix_ms,
        reduction_source_directory,
        pending_buy_retry_source_directory,
        committed_at_unix_ms,
    ):
        captured.update(
            decision_bootstrap=decision_bootstrap,
            decision_config=decision_config,
            execution_config=execution_config,
            reduction_source_directory=reduction_source_directory,
            pending_buy_retry_source_directory=pending_buy_retry_source_directory,
            committed_at_unix_ms=committed_at_unix_ms,
            decision_clock=clock_unix_ms(),
        )
        return FastPaperShadowServiceCoordinatorResult(
            decision_bootstrap=after_decision,
            execution_bootstrap=after_execution,
            decisions_produced=1,
            executions_committed=0,
        )

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_service_coordinated_cycle",
        coordinated,
    )

    updated, produced, committed = (
        supervisor.run_fast_paper_shadow_supervisor_cycle(
            before,
            config,
            clock_unix_ms=lambda: 25_000,
        )
    )

    assert updated.decision_bootstrap is after_decision
    assert updated.execution_bootstrap is after_execution
    assert produced == 1
    assert committed == 0
    assert captured["decision_bootstrap"] is before.decision_bootstrap
    assert captured["decision_config"] is config.decision_config
    assert captured["execution_config"] is config.execution_config
    assert captured["reduction_source_directory"] == (
        config.reduction_source_directory
    )
    assert captured["pending_buy_retry_source_directory"] == (
        config.pending_buy_retry_source_directory
    )
    assert captured["committed_at_unix_ms"] == 25_000
    assert captured["decision_clock"] == 25_000


def test_supervisor_status_reports_decision_and_execution_progress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for name in ("decision", "execution-sources", "buy-authority-sources", "quote-usd-sources", "reduction-sources", "retry-sources"):
        (tmp_path / name).mkdir()
    config = _config(tmp_path)
    bootstrap = supervisor.FastPaperShadowSupervisorBootstrap(
        decision_bootstrap=_decision_bootstrap(),
        execution_bootstrap=_execution_bootstrap(),
        buy_writer_policy=_buy_writer_policy(tmp_path),
    )
    monkeypatch.setattr(
        supervisor,
        "bootstrap_fast_paper_shadow_supervisor",
        lambda _config: bootstrap,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_supervisor_cycle",
        lambda current, _config, *, clock_unix_ms: (current, 1, 0),
    )

    class OneCycle:
        def is_set(self):
            return False

        def wait(self, _seconds):
            return True

    lines: list[str] = []
    totals = supervisor.run_fast_paper_shadow_supervisor(
        config,
        stop_event=OneCycle(),
        clock_unix_ms=lambda: 25_000,
        status_sink=lines.append,
    )

    assert totals == (1, 0)
    assert len(lines) == 1
    document = json.loads(lines[0])
    assert document["mode"] == "PAPER_SHADOW_COORDINATED"
    assert document["state"] == "RUNNING"
    assert document["completed_cycles"] == 1
    assert document["decisions_produced"] == 1
    assert document["executions_committed"] == 0
    assert document["decision_cursor_sequence"] == 4
    assert document["execution_cursor_sequence"] == 4
    assert document["paper_checkpoint_sequence"] == 9


def test_supervisor_source_has_orchestration_authority_only() -> None:
    payload = Path(supervisor.__file__).read_text(encoding="utf-8")
    for required in (
        "load_fast_paper_shadow_service_config",
        "load_fast_paper_shadow_service_execution_config",
        "bootstrap_fast_paper_shadow_service",
        "bootstrap_fast_paper_shadow_service_execution",
        "run_fast_paper_shadow_service_coordinated_cycle",
    ):
        assert required in payload

    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "execute_fast_paper_shadow_decision(",
        "retry_fast_paper_shadow_pending_buy(",
        "build_fast_paper_shadow_reduction_source_record",
        "write_fast_paper_shadow_reduction_source_record",
        "build_fast_paper_shadow_pending_buy_retry_source_record",
        "write_fast_paper_shadow_pending_buy_retry_source_record",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in payload


def test_systemd_runs_coordinated_supervisor_and_packages_complete_env_example() -> None:
    unit = _UNIT.read_text(encoding="utf-8")
    assert (
        "ExecStartPre=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.fast_paper_runtime.shadow_supervisor --preflight"
    ) in unit
    assert (
        "ExecStart=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.fast_paper_runtime.shadow_supervisor"
    ) in unit
    assert "PrivateNetwork=true" in unit
    assert "ReadWritePaths=/var/lib/shreks/fast-paper-shadow" in unit
    assert "shreks-paper-campaign.service" not in unit
    assert "WantedBy=shreks.target" not in unit
    assert "PartOf=shreks.target" not in unit

    payload = _ENV_EXAMPLE.read_text(encoding="utf-8")
    for name in (
        "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH",
        "SHREKS_FAST_PAPER_SHADOW_SERVICE_POLICY_PATH",
        "SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY",
        "SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH",
        "SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY",
        "SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH",
        "SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID",
        "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY",
        "SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY",
        "SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY",
        "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY",
        "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH",
    ):
        assert f"{name}=" in payload



def test_supervisor_publishes_skip_source_before_coordinator(
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
    config = _config(tmp_path)
    before = supervisor.FastPaperShadowSupervisorBootstrap(
        decision_bootstrap=_decision_bootstrap(),
        execution_bootstrap=_execution_bootstrap(),
        buy_writer_policy=_buy_writer_policy(tmp_path),
    )
    order: list[str] = []

    def publish(
        manifest,
        execution_bootstrap,
        *,
        decision_evidence_directory,
    ):
        order.append("publish")
        assert manifest is before.decision_bootstrap.manifest
        assert execution_bootstrap is before.execution_bootstrap
        assert (
            decision_evidence_directory
            == config.decision_config.evidence_directory
        )
        return 1

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_skip_source_publisher_cycle",
        publish,
        raising=False,
    )

    result = FastPaperShadowServiceCoordinatorResult(
        decision_bootstrap=before.decision_bootstrap,
        execution_bootstrap=before.execution_bootstrap,
        decisions_produced=0,
        executions_committed=1,
    )

    def coordinated(*_args, **_kwargs):
        order.append("coordinate")
        return result

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_service_coordinated_cycle",
        coordinated,
    )

    updated, produced, committed = (
        supervisor.run_fast_paper_shadow_supervisor_cycle(
            before,
            config,
            clock_unix_ms=lambda: 25_000,
        )
    )

    assert order == ["publish", "coordinate"]
    assert updated.execution_bootstrap is before.execution_bootstrap
    assert produced == 0
    assert committed == 1


def test_supervisor_only_orchestrates_skip_source_publication() -> None:
    payload = Path(supervisor.__file__).read_text(encoding="utf-8")
    assert "run_fast_paper_shadow_skip_source_publisher_cycle" in payload
    for forbidden in (
        "FastPaperShadowExecutionInput(",
        "produce_fast_paper_shadow_execution_input_source_record(",
        "write_fast_paper_shadow_execution_input_source_record(",
    ):
        assert forbidden not in payload
