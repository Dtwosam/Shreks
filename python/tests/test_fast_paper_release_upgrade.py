from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_release_upgrade as upgrade
from shreks_brain.fast_paper_physical_cutover import HostCommandResult


_SOURCE_SHA = "a" * 40
_TARGET_SHA = "b" * 40
_MANIFEST_FP = "1" * 64
_TARGET_MANIFEST_FP = "2" * 64
_CHAMPION_FP = "3" * 64
_BINDING_FP = "4" * 64
_TARGET_BINDING_FP = "5" * 64
_POLICY_FP = "6" * 64
_TARGET_POLICY_FP = "7" * 64
_CHECKPOINT_FP = "8" * 64
_RUNTIME_FP = "9" * 64
_DECISION_FP = "c" * 64
_HANDOFF_FP = "d" * 64
_AUTH_FP = "e" * 64
_PREFLIGHT_FP = "f" * 64
_BASELINE_FP = "0" * 64


def _paths(tmp_path: Path) -> upgrade.FastPaperReleaseUpgradePaths:
    return upgrade.FastPaperReleaseUpgradePaths(
        releases_dir=(tmp_path / "opt" / "shreks" / "releases").resolve(),
        current_link=(tmp_path / "opt" / "shreks" / "current").resolve(),
        systemd_dir=(tmp_path / "etc" / "systemd" / "system").resolve(),
        authoritative_env_path=(tmp_path / "etc" / "shreks" / "authoritative.env").resolve(),
        runtime_manifest_path=(tmp_path / "etc" / "shreks" / "manifest.json").resolve(),
        service_policy_path=(tmp_path / "etc" / "shreks" / "service.json").resolve(),
        execution_policy_path=(tmp_path / "etc" / "shreks" / "execution.json").resolve(),
        buy_writer_policy_path=(tmp_path / "etc" / "shreks" / "buy.json").resolve(),
        authorization_path=(tmp_path / "etc" / "shreks" / "authorization.json").resolve(),
        receipt_root=(tmp_path / "root" / "receipts").resolve(),
        proc_root=(tmp_path / "proc").resolve(),
    )


def _manifest(source_sha: str, fingerprint: str):
    return SimpleNamespace(
        release_source_sha=source_sha,
        manifest_fingerprint_sha256=fingerprint,
        champion_version="champion-v1",
        champion_fingerprint_sha256=_CHAMPION_FP,
        action_policy=SimpleNamespace(version=7),
    )


def _source(tmp_path: Path):
    release = (tmp_path / "source-release").resolve()
    release.mkdir(parents=True)
    database = (tmp_path / "authoritative.sqlite3").resolve()
    database.write_bytes(b"")
    checkpoint = (tmp_path / "decision.json").resolve()
    checkpoint.write_text("{}\n", encoding="utf-8")
    binding = SimpleNamespace(
        fast_run_id="fast-source-run",
        binding_fingerprint_sha256=_BINDING_FP,
    )
    execution_policy = SimpleNamespace(
        policy_fingerprint_sha256=_POLICY_FP,
    )
    bootstrap = SimpleNamespace(
        execution_bootstrap=SimpleNamespace(
            binding=binding,
            checkpoint=SimpleNamespace(
                payload_sha256=_CHECKPOINT_FP,
            ),
            runtime_state=SimpleNamespace(
                state_fingerprint_sha256=_RUNTIME_FP,
            ),
            execution_policy=execution_policy,
        )
    )
    return upgrade._SourceContext(
        release=release,
        manifest=_manifest(_SOURCE_SHA, _MANIFEST_FP),
        service_policy=object(),
        execution_policy=execution_policy,
        buy_writer_policy=object(),
        environment={"sealed": "source"},
        config=SimpleNamespace(
            decision_config=SimpleNamespace(
                checkpoint_path=checkpoint,
            ),
            execution_config=SimpleNamespace(
                database_path=database,
            ),
        ),
        bootstrap=bootstrap,
        authorization={
            "cutover_preflight_report_fingerprint_sha256": _PREFLIGHT_FP,
            "baseline_receipt_fingerprint_sha256": _BASELINE_FP,
        },
        decision_state=SimpleNamespace(
            state_fingerprint_sha256=_DECISION_FP,
        ),
    )


def _target(tmp_path: Path):
    release = (tmp_path / "target-release").resolve()
    release.mkdir(parents=True)
    return upgrade._TargetContext(
        release=release,
        identity=upgrade._ReleaseIdentity(
            source_sha=_TARGET_SHA,
            platform="x86_64-unknown-linux-gnu",
            wheel_path=release / "wheel.whl",
        ),
        manifest=_manifest(_TARGET_SHA, _TARGET_MANIFEST_FP),
        execution_policy=SimpleNamespace(
            policy_fingerprint_sha256=_TARGET_POLICY_FP,
        ),
        buy_writer_policy=object(),
        environment={"sealed": "target"},
        fast_run_id=f"fast-release-{_TARGET_SHA}",
        unit_payload=b"fast-unit\n",
        commissioning_fingerprint_sha256="a" * 64,
    )


def _handoff(target):
    binding = SimpleNamespace(
        fast_run_id=target.fast_run_id,
        binding_fingerprint_sha256=_TARGET_BINDING_FP,
    )
    checkpoint = SimpleNamespace(payload_sha256=_CHECKPOINT_FP)
    runtime = SimpleNamespace(state_fingerprint_sha256=_RUNTIME_FP)
    decision = SimpleNamespace(state_fingerprint_sha256=_DECISION_FP)
    return SimpleNamespace(
        handoff=SimpleNamespace(
            handoff_fingerprint_sha256=_HANDOFF_FP,
        ),
        binding=binding,
        checkpoint=checkpoint,
        runtime_state=runtime,
        decision_state=decision,
    )


def _systemd_state(*, running: bool, pid: int = 111):
    return SimpleNamespace(
        active_state="active" if running else "inactive",
        sub_state="running" if running else "dead",
        main_pid=pid if running else 0,
        n_restarts=0,
        exec_main_status=0,
        invocation_id="1" * 32 if running else "",
        fragment_path="/etc/systemd/system/shreks-paper-campaign.service",
        working_directory="/opt/shreks/current",
        user="shreks",
        group="shreks",
        private_network="yes",
    )


class Runner:
    def __init__(self, events: list[str]):
        self.events = events
        self.paper_running = True

    def __call__(self, command: tuple[str, ...]) -> HostCommandResult:
        self.events.append("cmd:" + " ".join(command))
        if command == ("systemctl", "stop", upgrade._UNIT):
            self.paper_running = False
        if command == ("systemctl", "start", upgrade._TARGET):
            self.paper_running = True
        return HostCommandResult(0, "", "")


def _patch_happy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    events: list[str],
):
    source = _source(tmp_path)
    target = _target(tmp_path)
    handoff = _handoff(target)
    runner = Runner(events)
    loads = {"count": 0}

    def load_source(*_args, **_kwargs):
        loads["count"] += 1
        events.append(f"load-source:{loads['count']}")
        return source

    monkeypatch.setattr(upgrade, "_require_root", lambda: None)
    monkeypatch.setattr(upgrade, "_load_source_context", load_source)
    monkeypatch.setattr(
        upgrade,
        "_prepare_target_context",
        lambda *_args, **_kwargs: target,
    )
    monkeypatch.setattr(
        upgrade,
        "_require_no_receipt",
        lambda *_args, **_kwargs: events.append("receipt-preflight"),
    )
    monkeypatch.setattr(
        upgrade,
        "_read_systemd_state",
        lambda supplied: _systemd_state(
            running=supplied.paper_running,
            pid=222 if supplied.paper_running else 0,
        ),
    )
    monkeypatch.setattr(
        upgrade,
        "_verify_fast_process",
        lambda *_args, **_kwargs: events.append("verify-process"),
    )

    def capture(*_args, **_kwargs):
        assert runner.paper_running is False
        assert loads["count"] >= 2
        events.append("capture-backup-post-stop")
        metadata = SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o100640)
        return SimpleNamespace(
            current_release=source.release,
            control_payloads={},
            control_stats={},
            unit_payloads={},
            authorization_payload=b"source-auth\n",
            authorization_stat=metadata,
        )

    monkeypatch.setattr(upgrade, "_capture_backup", capture)
    monkeypatch.setattr(
        upgrade,
        "_replace_authorization_with_upgrade_marker",
        lambda *_args, **_kwargs: events.append("guard"),
    )
    monkeypatch.setattr(
        upgrade,
        "initialize_fast_paper_authoritative_release_handoff",
        lambda *_args, **_kwargs: (
            events.append("handoff") or handoff
        ),
    )
    monkeypatch.setattr(
        upgrade,
        "build_fast_paper_cutover_authorization",
        lambda **_kwargs: {
            "authorization_fingerprint_sha256": _AUTH_FP,
        },
    )
    monkeypatch.setattr(
        upgrade,
        "_target_control_payloads",
        lambda *_args, **_kwargs: {
            "authorization": b"target-auth\n",
        },
    )
    monkeypatch.setattr(
        upgrade,
        "_stop_non_paper_runtime",
        lambda _runner: events.append("stop-non-paper"),
    )
    monkeypatch.setattr(
        upgrade,
        "_install_target_controls",
        lambda *_args, **_kwargs: events.append("install-controls"),
    )
    monkeypatch.setattr(
        upgrade,
        "_install_target_units",
        lambda *_args, **_kwargs: events.append("install-units"),
    )
    monkeypatch.setattr(
        upgrade,
        "_atomic_switch",
        lambda *_args, **_kwargs: events.append("switch-current"),
    )
    target_config = object()
    monkeypatch.setattr(
        upgrade,
        "validate_fast_paper_authoritative_cutover_environment",
        lambda *_args, **_kwargs: target_config,
    )
    target_bootstrap = SimpleNamespace(
        execution_bootstrap=SimpleNamespace(
            binding=handoff.binding,
            checkpoint=handoff.checkpoint,
            runtime_state=handoff.runtime_state,
        ),
        decision_bootstrap=SimpleNamespace(
            state=handoff.decision_state,
        ),
    )
    monkeypatch.setattr(
        upgrade,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: target_bootstrap,
    )
    monkeypatch.setattr(
        upgrade,
        "verify_fast_paper_cutover_authorization",
        lambda *_args, **_kwargs: events.append("verify-target-auth"),
    )
    monkeypatch.setattr(
        upgrade,
        "_replace_file_atomically",
        lambda *_args, **_kwargs: events.append("install-valid-auth"),
    )
    monkeypatch.setattr(
        upgrade,
        "_wait_running",
        lambda *_args, **_kwargs: _systemd_state(running=True, pid=222),
    )
    monkeypatch.setattr(
        upgrade,
        "_require_other_services_active",
        lambda _runner: events.append("verify-other-services"),
    )
    monkeypatch.setattr(
        upgrade,
        "_read_authoritative_statuses",
        lambda *_args, **_kwargs: ({"completed_cycles": 1}, {"completed_cycles": 2}),
    )
    monkeypatch.setattr(
        upgrade,
        "_require_status_advancement",
        lambda *_args, **_kwargs: events.append("verify-status"),
    )
    monkeypatch.setattr(
        upgrade,
        "_write_receipt_no_replace",
        lambda *_args, **_kwargs: events.append("write-receipt"),
    )
    return source, target, handoff, runner


def test_activation_orders_guard_handoff_controls_authorization_and_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    source, target, _handoff_value, runner = _patch_happy(
        monkeypatch,
        tmp_path,
        events,
    )

    receipt = upgrade.activate_fast_paper_release_upgrade(
        target.release,
        paths=_paths(tmp_path),
        runtime_executable=source.release / ".venv" / "bin" / "python",
        observation_seconds=5,
        command_runner=runner,
        sleeper=lambda _seconds: None,
        clock_unix_ms=lambda: 123_456,
    )

    assert receipt["state"] == "FAST_PAPER_RELEASE_UPGRADE_ACTIVE"
    assert receipt["target_release_source_sha"] == _TARGET_SHA
    assert receipt["signing_submission_authority"] == "NOT_GRANTED"
    assert receipt["live_authority"] == "DISABLED"

    def at(value: str) -> int:
        return events.index(value)

    stop = events.index(f"cmd:systemctl stop {upgrade._UNIT}")
    start = events.index(f"cmd:systemctl start {upgrade._TARGET}")
    assert stop < at("load-source:2") < at("capture-backup-post-stop")
    assert at("capture-backup-post-stop") < at("guard") < at("handoff")
    assert at("handoff") < at("install-controls") < at("install-units")
    assert at("install-units") < at("switch-current")
    assert at("switch-current") < at("verify-target-auth")
    assert at("verify-target-auth") < at("install-valid-auth") < start


def test_pre_start_failure_restores_source_fast_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    source, target, _handoff_value, runner = _patch_happy(
        monkeypatch,
        tmp_path,
        events,
    )
    monkeypatch.setattr(
        upgrade,
        "_install_target_controls",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("control rotation failed")
        ),
    )
    monkeypatch.setattr(
        upgrade,
        "_restore_source_before_target_start",
        lambda *_args, **_kwargs: events.append("restore-source"),
    )
    monkeypatch.setattr(
        upgrade,
        "_revoke_authorization_for_manual_recovery",
        lambda *_args, **_kwargs: events.append("revoke"),
    )

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="source Fast release restored",
    ):
        upgrade.activate_fast_paper_release_upgrade(
            target.release,
            paths=_paths(tmp_path),
            runtime_executable=source.release / ".venv" / "bin" / "python",
            observation_seconds=5,
            command_runner=runner,
            sleeper=lambda _seconds: None,
            clock_unix_ms=lambda: 123_456,
        )

    assert "restore-source" in events
    assert "revoke" not in events
    assert f"cmd:systemctl start {upgrade._TARGET}" not in events


def test_post_start_failure_never_restores_source_and_revokes_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    source, target, _handoff_value, runner = _patch_happy(
        monkeypatch,
        tmp_path,
        events,
    )
    monkeypatch.setattr(
        upgrade,
        "_read_authoritative_statuses",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("no stable statuses")
        ),
    )
    monkeypatch.setattr(
        upgrade,
        "_restore_source_before_target_start",
        lambda *_args, **_kwargs: events.append("restore-source"),
    )
    monkeypatch.setattr(
        upgrade,
        "_stop_all_runtime_best_effort",
        lambda _runner: events.append("stop-all"),
    )
    monkeypatch.setattr(
        upgrade,
        "_revoke_authorization_for_manual_recovery",
        lambda *_args, **_kwargs: events.append("revoke"),
    )

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="manual recovery required",
    ):
        upgrade.activate_fast_paper_release_upgrade(
            target.release,
            paths=_paths(tmp_path),
            runtime_executable=source.release / ".venv" / "bin" / "python",
            observation_seconds=5,
            command_runner=runner,
            sleeper=lambda _seconds: None,
            clock_unix_ms=lambda: 123_456,
        )

    assert f"cmd:systemctl start {upgrade._TARGET}" in events
    assert "stop-all" in events
    assert "revoke" in events
    assert "restore-source" not in events


def test_target_preparation_failure_occurs_before_service_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    source = _source(tmp_path)
    runner = Runner(events)
    monkeypatch.setattr(upgrade, "_require_root", lambda: None)
    monkeypatch.setattr(
        upgrade,
        "_load_source_context",
        lambda *_args, **_kwargs: source,
    )
    monkeypatch.setattr(
        upgrade,
        "_prepare_target_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            upgrade.FastPaperReleaseUpgradeError(
                "target release changes Fast trading semantics"
            )
        ),
    )

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="trading semantics",
    ):
        upgrade.activate_fast_paper_release_upgrade(
            tmp_path / "candidate",
            paths=_paths(tmp_path),
            command_runner=runner,
        )

    assert events == []


def test_fresh_target_run_id_skips_immutable_prior_attempts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE fast_paper_authoritative_bindings(
                fast_run_id TEXT PRIMARY KEY
            );
            CREATE TABLE paper_loop_checkpoints(
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL
            );
            CREATE TABLE fast_paper_authoritative_runtime_states(
                fast_run_id TEXT NOT NULL
            );
            CREATE TABLE fast_paper_authoritative_release_handoffs(
                target_run_id TEXT PRIMARY KEY
            );
            """
        )
        base = f"fast-release-{_TARGET_SHA}"
        connection.execute(
            "INSERT INTO fast_paper_authoritative_release_handoffs(target_run_id) VALUES (?)",
            (base,),
        )
        connection.execute(
            "INSERT INTO fast_paper_authoritative_bindings(fast_run_id) VALUES (?)",
            (base + ".2",),
        )

    assert upgrade._fresh_target_run_id(
        database,
        _TARGET_SHA,
    ) == f"fast-release-{_TARGET_SHA}.3"


def test_default_command_runner_rejects_unreviewed_service_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda command, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        ),
    )
    for forbidden in (
        ("systemctl", "restart", upgrade._UNIT),
        ("systemctl", "enable", upgrade._UNIT),
        ("systemctl", "disable", upgrade._UNIT),
        ("systemctl", "start", upgrade._UNIT),
        ("systemctl", "start", "other.service"),
    ):
        with pytest.raises(
            upgrade.FastPaperReleaseUpgradeError,
            match="allowlist",
        ):
            upgrade._default_command_runner(forbidden)


def test_release_upgrade_source_has_no_scoring_signing_or_live_authority() -> None:
    source = Path(upgrade.__file__).read_text(encoding="utf-8")

    for required in (
        "initialize_fast_paper_authoritative_release_handoff",
        "UPGRADE_IN_PROGRESS",
        "build_fast_paper_cutover_authorization",
        "FAST_PAPER_RELEASE_UPGRADE_ACTIVE",
        "signing_submission_authority",
        "live_authority",
    ):
        assert required in source

    for forbidden in (
        "score_candidate",
        "decide_entry",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "LIVE_ENABLED",
        "shreks_brain.observer_campaign.runtime",
        "systemctl restart",
        "systemctl enable",
        "systemctl disable",
    ):
        assert forbidden not in source
