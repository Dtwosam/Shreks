from __future__ import annotations

import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_shadow_physical_commission as physical


_SHA = "a" * 40
_UID = 1001
_GID = 1001
_UNIT = "shreks-fast-paper-shadow.service"


def _layout(tmp_path: Path) -> physical.FastPaperShadowPhysicalCommissionPaths:
    release = tmp_path / "opt" / "shreks" / "releases" / _SHA
    runtime = release / ".venv" / "bin" / "python"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime.chmod(0o755)

    current = tmp_path / "opt" / "shreks" / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(release)

    unit_parent = tmp_path / "etc" / "systemd" / "system"
    unit_parent.mkdir(parents=True)
    unit = unit_parent / _UNIT
    unit.write_text("[Service]\nPrivateNetwork=true\n", encoding="utf-8")
    unit.chmod(0o644)

    config_parent = tmp_path / "etc" / "shreks"
    config_parent.mkdir(parents=True)
    config = config_parent / "fast-paper-shadow.env"
    config.write_text("placeholder\n", encoding="utf-8")

    target = unit_parent / "shreks.target"
    target.write_text("[Unit]\nDescription=core\n", encoding="utf-8")

    shadow = tmp_path / "var" / "lib" / "shreks" / "fast-paper-shadow"
    shadow.mkdir(parents=True)
    shadow.chmod(0o700)

    proc = tmp_path / "proc"
    proc.mkdir()
    root_private = tmp_path / "root"
    root_private.mkdir()

    return physical.FastPaperShadowPhysicalCommissionPaths(
        current_link=current,
        unit_destination=unit,
        config_destination=config,
        target_path=target,
        shadow_root=shadow,
        commissioning_root=root_private
        / "shreks-fast-paper-shadow-commissioning",
        proc_root=proc,
    )


def _make_proc(paths, pid: int, *, cpu_ticks: int = 100, rss_kib: int = 4096):
    release = paths.current_link.resolve()
    pid_root = paths.proc_root / str(pid)
    pid_root.mkdir(parents=True, exist_ok=True)
    (pid_root / "cwd").symlink_to(release)
    (pid_root / "cmdline").write_bytes(
        (
            str(paths.current_link / ".venv" / "bin" / "python")
            + "\0-m\0shreks_brain.fast_paper_runtime.shadow_supervisor\0"
        ).encode("utf-8")
    )
    fields = ["0"] * 50
    fields[11] = str(cpu_ticks // 2)
    fields[12] = str(cpu_ticks - cpu_ticks // 2)
    (pid_root / "stat").write_text(
        f"{pid} (python) S " + " ".join(fields) + "\n",
        encoding="utf-8",
    )
    (pid_root / "status").write_text(
        f"Name:\tpython\nVmRSS:\t{rss_kib} kB\n",
        encoding="utf-8",
    )
    (pid_root / "net").mkdir()
    (pid_root / "net" / "dev").write_text(
        "Inter-|   Receive                                                |  Transmit\n"
        " face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n"
        "    lo: 100 1 0 0 0 0 0 0 200 1 0 0 0 0 0 0\n",
        encoding="utf-8",
    )


def _status(cycle: int, *, decisions: int = 0, executions: int = 0) -> str:
    return json.dumps(
        {
            "schema_name": "shreks.fast_paper_shadow_supervisor_status",
            "schema_version": 1,
            "mode": "PAPER_SHADOW_COORDINATED",
            "state": "RUNNING",
            "manifest_fingerprint_sha256": "b" * 64,
            "champion_version": "champion-v1",
            "champion_fingerprint_sha256": "c" * 64,
            "action_policy_version": 1,
            "completed_cycles": cycle,
            "decisions_produced": decisions,
            "executions_committed": executions,
            "decision_cursor_sequence": None,
            "execution_cursor_sequence": None,
            "paper_checkpoint_sequence": 0,
            "pending_buy": False,
            "open_market_positions": 0,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class FakeRunner:
    def __init__(self, paths):
        self.paths = paths
        self.commands: list[tuple[str, ...]] = []
        self.active = False
        self.pid = 0
        self.nrestarts = 0
        self.invocation = "0" * 32
        self.enabled = "static"
        self.journal = _status(1) + "\n" + _status(4) + "\n"

    def __call__(self, command: tuple[str, ...]):
        self.commands.append(command)
        if command == ("systemctl", "daemon-reload"):
            return physical.HostCommandResult(0, "", "")
        if command == ("systemctl", "start", _UNIT):
            assert not self.active
            self.active = True
            self.pid = 4321
            self.invocation = "1" * 32
            _make_proc(self.paths, self.pid)
            return physical.HostCommandResult(0, "", "")
        if command == ("systemctl", "restart", _UNIT):
            assert self.active
            self.pid = 4322
            self.invocation = "2" * 32
            _make_proc(self.paths, self.pid, cpu_ticks=120, rss_kib=4200)
            return physical.HostCommandResult(0, "", "")
        if command == ("systemctl", "is-enabled", _UNIT):
            return physical.HostCommandResult(
                0 if self.enabled == "static" else 1,
                self.enabled + "\n",
                "",
            )
        if command[:3] == ("systemctl", "show", _UNIT):
            active = "active" if self.active else "inactive"
            sub = "running" if self.active else "dead"
            stdout = (
                f"ActiveState={active}\n"
                f"SubState={sub}\n"
                f"MainPID={self.pid}\n"
                f"NRestarts={self.nrestarts}\n"
                "ExecMainStatus=0\n"
                f"InvocationID={self.invocation}\n"
                f"FragmentPath={self.paths.unit_destination}\n"
                "WorkingDirectory=/opt/shreks/current\n"
                "User=shreks\n"
                "Group=shreks\n"
                "PrivateNetwork=yes\n"
            )
            return physical.HostCommandResult(0, stdout, "")
        if command[:4] == ("journalctl", "-u", _UNIT, "--since"):
            return physical.HostCommandResult(0, self.journal, "")
        raise AssertionError(f"unexpected command: {command}")


def _patch_preflight(monkeypatch, paths):
    monkeypatch.setattr(physical.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        physical,
        "_resolve_service_identity",
        lambda: (_UID, _GID),
    )
    monkeypatch.setattr(
        physical,
        "preflight_fast_paper_shadow_host",
        lambda **_kwargs: {
            "state": "READY_FOR_DORMANT_SYSTEMD_LOAD_REVIEW",
            "release_source_sha": _SHA,
            "live_authority": "DISABLED",
        },
    )


def test_commissioning_receipts_must_stay_outside_service_write_tree(
    tmp_path: Path,
) -> None:
    release = tmp_path / "release"
    release.mkdir()
    current = tmp_path / "current"
    current.symlink_to(release)
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    with pytest.raises(
        ValueError,
        match="outside the service-writable shadow tree",
    ):
        physical.FastPaperShadowPhysicalCommissionPaths(
            current_link=current,
            unit_destination=tmp_path / "unit",
            config_destination=tmp_path / "env",
            target_path=tmp_path / "target",
            shadow_root=shadow,
            commissioning_root=shadow / "commissioning",
            proc_root=tmp_path / "proc",
        )


def test_default_command_runner_rejects_enable_stop_and_foreign_units(
    monkeypatch,
) -> None:
    called = []

    def fake_run(command, **kwargs):
        called.append(tuple(command))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(physical.subprocess, "run", fake_run)

    physical._default_command_runner(("systemctl", "daemon-reload"))
    physical._default_command_runner(("systemctl", "start", _UNIT))
    physical._default_command_runner(("systemctl", "restart", _UNIT))

    for forbidden in (
        ("systemctl", "enable", _UNIT),
        ("systemctl", "disable", _UNIT),
        ("systemctl", "stop", _UNIT),
        ("systemctl", "start", "shreks-paper-campaign.service"),
    ):
        with pytest.raises(
            physical.FastPaperShadowPhysicalCommissionError,
            match="allowlist",
        ):
            physical._default_command_runner(forbidden)

    assert called == [
        ("systemctl", "daemon-reload"),
        ("systemctl", "start", _UNIT),
        ("systemctl", "restart", _UNIT),
    ]


def test_activation_is_detached_one_start_and_writes_private_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _layout(tmp_path)
    _patch_preflight(monkeypatch, paths)
    runner = FakeRunner(paths)

    receipt = physical.activate_fast_paper_shadow(
        expected_release_source_sha=_SHA,
        observation_seconds=5,
        paths=paths,
        runtime_executable=paths.current_link / ".venv" / "bin" / "python",
        command_runner=runner,
        clock_unix_ms=lambda: 1_000_000,
        sleeper=lambda _seconds: None,
    )

    assert receipt["state"] == "ACTIVE_DETACHED_OBSERVED"
    assert receipt["shadow_runtime"] == "ACTIVE_DETACHED"
    assert receipt["production_paper_cutover"] == "NOT_GRANTED"
    assert receipt["live_authority"] == "DISABLED"
    assert receipt["completed_cycles_delta"] == 3
    assert receipt["main_pid"] == 4321
    assert receipt["unit_file_state"] == "static"
    assert receipt["private_network_non_loopback_interfaces"] == []

    assert runner.commands.count(("systemctl", "daemon-reload")) == 1
    assert runner.commands.count(("systemctl", "start", _UNIT)) == 1
    assert not any(
        command[:2] in (
            ("systemctl", "enable"),
            ("systemctl", "disable"),
            ("systemctl", "stop"),
        )
        for command in runner.commands
    )

    stored = paths.activation_receipt
    assert stored.is_file()
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert stat.S_IMODE(paths.commissioning_root.stat().st_mode) == 0o700
    assert json.loads(stored.read_text(encoding="utf-8")) == receipt

    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="activation receipt",
    ):
        physical.activate_fast_paper_shadow(
            expected_release_source_sha=_SHA,
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link
            / ".venv"
            / "bin"
            / "python",
            command_runner=runner,
            clock_unix_ms=lambda: 1_100_000,
            sleeper=lambda _seconds: None,
        )


def test_activation_rejects_enabled_or_already_active_unit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _layout(tmp_path)
    _patch_preflight(monkeypatch, paths)

    enabled = FakeRunner(paths)
    enabled.enabled = "enabled"
    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="enabled",
    ):
        physical.activate_fast_paper_shadow(
            expected_release_source_sha=_SHA,
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link
            / ".venv"
            / "bin"
            / "python",
            command_runner=enabled,
            sleeper=lambda _seconds: None,
        )
    assert ("systemctl", "start", _UNIT) not in enabled.commands

    active = FakeRunner(paths)
    active.active = True
    active.pid = 999
    active.invocation = "f" * 32
    _make_proc(paths, 999)
    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="inactive",
    ):
        physical.activate_fast_paper_shadow(
            expected_release_source_sha=_SHA,
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link
            / ".venv"
            / "bin"
            / "python",
            command_runner=active,
            sleeper=lambda _seconds: None,
        )
    assert ("systemctl", "start", _UNIT) not in active.commands


def test_observation_rejects_process_restart_churn_and_bad_network(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _layout(tmp_path)
    _patch_preflight(monkeypatch, paths)
    runner = FakeRunner(paths)
    runner.active = True
    runner.pid = 4321
    runner.invocation = "1" * 32
    _make_proc(paths, runner.pid)

    calls = 0

    def sleeper(_seconds):
        nonlocal calls
        calls += 1
        if calls == 1:
            runner.pid = 4322
            runner.nrestarts = 1
            runner.invocation = "2" * 32
            _make_proc(paths, 4322)

    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="stable|restart|PID",
    ):
        physical.observe_fast_paper_shadow(
            expected_release_source_sha=_SHA,
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link
            / ".venv"
            / "bin"
            / "python",
            command_runner=runner,
            sleeper=sleeper,
        )

    runner = FakeRunner(paths)
    runner.active = True
    runner.pid = 5000
    runner.invocation = "3" * 32
    _make_proc(paths, 5000)
    net = paths.proc_root / "5000" / "net" / "dev"
    net.write_text(
        net.read_text(encoding="utf-8")
        + "  eth0: 1 1 0 0 0 0 0 0 2 1 0 0 0 0 0 0\n",
        encoding="utf-8",
    )
    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="network",
    ):
        physical.observe_fast_paper_shadow(
            expected_release_source_sha=_SHA,
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link
            / ".venv"
            / "bin"
            / "python",
            command_runner=runner,
            sleeper=lambda _seconds: None,
        )


def _headroom_telemetry(count: int = 25) -> dict[str, object]:
    return {
        "manifest_fingerprint_sha256": "b" * 64,
        "champion_version": "champion-v1",
        "champion_fingerprint_sha256": "c" * 64,
        "action_policy_version": 1,
        "decision_evidence_count": count,
        "decision_evidence_rate_per_second": float(count) / 5.0,
        "event_to_evaluation_lag_ms": {
            "p50": 4.0,
            "p95": 12.0,
            "p99": 15.0,
            "max": 18.0,
        },
        "decision_latency_ms": {
            "p50": 0.1,
            "p95": 0.3,
            "p99": 0.4,
            "max": 0.5,
        },
        "telemetry_fingerprint_sha256": "d" * 64,
    }


def _advance_proc_resources(paths, pid: int) -> None:
    pid_root = paths.proc_root / str(pid)
    fields = ["0"] * 50
    fields[10] = "250"
    fields[11] = "300"
    (pid_root / "stat").write_text(
        f"{pid} (python) S " + " ".join(fields) + "\n",
        encoding="utf-8",
    )
    (pid_root / "status").write_text(
        "Name:\tpython\nVmRSS:\t8192 kB\n",
        encoding="utf-8",
    )
    (pid_root / "net" / "dev").write_text(
        "Inter-|   Receive                                                |  Transmit\n"
        " face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n"
        "    lo: 1100 1 0 0 0 0 0 0 2200 1 0 0 0 0 0 0\n",
        encoding="utf-8",
    )
    (paths.shadow_root / "burst-evidence.bin").write_bytes(b"x" * 500)


def test_host_capacity_reads_cpu_memory_and_filesystem(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _layout(tmp_path)
    (paths.proc_root / "meminfo").write_text(
        "MemTotal:       16384 kB\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(physical.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(
        physical.os,
        "statvfs",
        lambda _path: SimpleNamespace(
            f_frsize=4096,
            f_bsize=4096,
            f_blocks=1000,
            f_bavail=250,
        ),
    )

    capacity = physical._read_host_capacity(paths)

    assert capacity == physical.HostCapacitySnapshot(
        logical_cpu_count=4,
        memory_total_bytes=16384 * 1024,
        storage_capacity_bytes=4096 * 1000,
        storage_available_bytes=4096 * 250,
    )


def test_headroom_telemetry_uses_exact_runtime_evidence_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _layout(tmp_path)
    evidence_directory = tmp_path / "decisions"
    evidence_directory.mkdir()
    monkeypatch.setattr(
        physical,
        "read_fast_paper_shadow_host_environment",
        lambda _path: {"loaded": "yes"},
    )
    monkeypatch.setattr(
        physical,
        "validate_fast_paper_shadow_production_environment",
        lambda _env: SimpleNamespace(
            supervisor_config=SimpleNamespace(
                decision_config=SimpleNamespace(
                    evidence_directory=evidence_directory
                )
            )
        ),
    )
    captured = {}

    def collect(**kwargs):
        captured.update(kwargs)
        return _headroom_telemetry()

    monkeypatch.setattr(
        physical,
        "collect_fast_paper_shadow_decision_telemetry",
        collect,
    )

    result = physical._collect_headroom_decision_telemetry(
        paths,
        expected_sha=_SHA,
        since_unix_ms=1_000,
        until_unix_ms=6_000,
    )

    assert result["decision_evidence_count"] == 25
    assert captured == {
        "evidence_directory": evidence_directory,
        "expected_release_sha": _SHA,
        "since_unix_ms": 1_000,
        "until_unix_ms": 6_000,
    }


def test_resource_headroom_rejects_identity_drift_and_invalid_minimum() -> None:
    observation = {
        "manifest_fingerprint_sha256": "b" * 64,
        "champion_version": "champion-v1",
        "champion_fingerprint_sha256": "c" * 64,
        "action_policy_version": 1,
    }
    telemetry = {
        **_headroom_telemetry(),
        "champion_version": "other-champion",
    }

    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="identity",
    ):
        physical._require_headroom_identity(observation, telemetry)

    for value in (0, -1, True):
        with pytest.raises(
            physical.FastPaperShadowPhysicalCommissionError,
            match="positive integer",
        ):
            physical._validate_minimum_decisions(value)


def test_resource_headroom_requires_activity_and_records_capacity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _layout(tmp_path)
    _patch_preflight(monkeypatch, paths)
    runner = FakeRunner(paths)

    physical.activate_fast_paper_shadow(
        expected_release_source_sha=_SHA,
        observation_seconds=5,
        paths=paths,
        runtime_executable=paths.current_link / ".venv" / "bin" / "python",
        command_runner=runner,
        clock_unix_ms=lambda: 1_000_000,
        sleeper=lambda _seconds: None,
    )

    captured = {}

    def telemetry(_paths, *, expected_sha, since_unix_ms, until_unix_ms):
        captured.update(
            expected_sha=expected_sha,
            since_unix_ms=since_unix_ms,
            until_unix_ms=until_unix_ms,
        )
        return _headroom_telemetry()

    monkeypatch.setattr(
        physical,
        "_collect_headroom_decision_telemetry",
        telemetry,
    )
    monkeypatch.setattr(
        physical,
        "_read_host_capacity",
        lambda _paths: physical.HostCapacitySnapshot(
            logical_cpu_count=4,
            memory_total_bytes=16 * 1024**3,
            storage_capacity_bytes=100 * 1024**3,
            storage_available_bytes=80 * 1024**3,
        ),
    )
    monkeypatch.setattr(physical.os, "sysconf", lambda _name: 100)

    starts_before = runner.commands.count(("systemctl", "start", _UNIT))
    restarts_before = runner.commands.count(("systemctl", "restart", _UNIT))

    receipt = physical.measure_fast_paper_shadow_resource_headroom(
        expected_release_source_sha=_SHA,
        observation_seconds=5,
        minimum_decisions=10,
        paths=paths,
        runtime_executable=paths.current_link / ".venv" / "bin" / "python",
        command_runner=runner,
        clock_unix_ms=lambda: 2_000_000,
        sleeper=lambda _seconds: _advance_proc_resources(paths, runner.pid),
    )

    assert receipt["state"] == "RESOURCE_HEADROOM_MEASURED"
    assert receipt["minimum_decision_evidence_count"] == 10
    assert receipt["decision_evidence_count"] == 25
    assert receipt["decision_evidence_rate_per_second"] == pytest.approx(5.0)
    assert receipt["cpu_percent"] == pytest.approx(100.0)
    assert receipt["cpu_host_utilization_pct"] == pytest.approx(25.0)
    assert receipt["cpu_host_headroom_pct"] == pytest.approx(75.0)
    assert receipt["logical_cpu_count"] == 4
    assert receipt["rss_bytes_peak"] == 8192 * 1024
    assert receipt["shadow_storage_growth_bytes_per_second"] == pytest.approx(
        100.0
    )
    assert receipt["private_network_rx_bytes_per_second"] == pytest.approx(
        200.0
    )
    assert receipt["private_network_tx_bytes_per_second"] == pytest.approx(
        400.0
    )
    assert receipt["completed_cycles_per_second"] == pytest.approx(0.6)
    assert receipt["production_paper_cutover"] == "NOT_GRANTED"
    assert receipt["live_authority"] == "DISABLED"
    assert captured == {
        "expected_sha": _SHA,
        "since_unix_ms": 2_000_000,
        "until_unix_ms": 2_005_000,
    }
    assert runner.commands.count(("systemctl", "start", _UNIT)) == starts_before
    assert runner.commands.count(("systemctl", "restart", _UNIT)) == restarts_before
    assert paths.headroom_receipt.is_file()
    assert stat.S_IMODE(paths.headroom_receipt.stat().st_mode) == 0o600


def test_resource_headroom_refuses_window_without_required_activity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _layout(tmp_path)
    _patch_preflight(monkeypatch, paths)
    runner = FakeRunner(paths)

    physical.activate_fast_paper_shadow(
        expected_release_source_sha=_SHA,
        observation_seconds=5,
        paths=paths,
        runtime_executable=paths.current_link / ".venv" / "bin" / "python",
        command_runner=runner,
        sleeper=lambda _seconds: None,
    )
    monkeypatch.setattr(
        physical,
        "_collect_headroom_decision_telemetry",
        lambda *_args, **_kwargs: _headroom_telemetry(count=2),
    )

    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="required decision evidence",
    ):
        physical.measure_fast_paper_shadow_resource_headroom(
            expected_release_source_sha=_SHA,
            observation_seconds=5,
            minimum_decisions=10,
            paths=paths,
            runtime_executable=paths.current_link
            / ".venv"
            / "bin"
            / "python",
            command_runner=runner,
            clock_unix_ms=lambda: 2_000_000,
            sleeper=lambda _seconds: None,
        )

    assert not paths.headroom_receipt.exists()


def test_journal_parser_requires_canonical_advancing_supervisor_status() -> None:
    parsed = physical.parse_supervisor_status_journal(
        _status(2, decisions=1) + "\n" + _status(5, decisions=2) + "\n"
    )
    assert [item["completed_cycles"] for item in parsed] == [2, 5]

    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="advance",
    ):
        physical._require_status_advancement((parsed[0], parsed[0]))

    bad = _status(1) + "\nnot-json\n" + _status(2)
    assert len(physical.parse_supervisor_status_journal(bad)) == 2


def test_journal_advancement_uses_latest_cycle_segment_after_restart() -> None:
    statuses = physical.parse_supervisor_status_journal(
        _status(12)
        + "\n"
        + _status(13)
        + "\n"
        + _status(1)
        + "\n"
        + _status(3)
        + "\n"
    )
    first, last = physical._require_status_advancement(statuses)
    assert first["completed_cycles"] == 1
    assert last["completed_cycles"] == 3


def test_restart_proof_requires_activation_receipt_and_monotonic_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _layout(tmp_path)
    _patch_preflight(monkeypatch, paths)
    runner = FakeRunner(paths)
    runner.active = True
    runner.pid = 4321
    runner.invocation = "1" * 32
    _make_proc(paths, 4321)

    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="activation receipt",
    ):
        physical.prove_fast_paper_shadow_restart(
            expected_release_source_sha=_SHA,
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link
            / ".venv"
            / "bin"
            / "python",
            command_runner=runner,
            sleeper=lambda _seconds: None,
        )

    physical._write_receipt_no_replace(
        paths.activation_receipt,
        physical._finalize_receipt(
            {
                "schema_name": "shreks.fast_paper_shadow_physical_activation",
                "schema_version": 1,
                "state": "ACTIVE_DETACHED_OBSERVED",
                "release_source_sha": _SHA,
            }
        ),
    )

    snapshots = iter(
        (
            physical.DurableShadowSnapshot(
                manifest_fingerprint_sha256="b" * 64,
                run_id="shadow-run-1",
                binding_fingerprint_sha256="c" * 64,
                checkpoint_sequence=4,
                checkpoint_payload_sha256="d" * 64,
                runtime_state_fingerprint_sha256="e" * 64,
                last_processed_source_sequence=9,
                last_processed_source_event_id="event-9",
                pending_buy_fingerprint_sha256=None,
                market_position_ids=("position-1",),
            ),
            physical.DurableShadowSnapshot(
                manifest_fingerprint_sha256="b" * 64,
                run_id="shadow-run-1",
                binding_fingerprint_sha256="c" * 64,
                checkpoint_sequence=5,
                checkpoint_payload_sha256="1" * 64,
                runtime_state_fingerprint_sha256="2" * 64,
                last_processed_source_sequence=10,
                last_processed_source_event_id="event-10",
                pending_buy_fingerprint_sha256=None,
                market_position_ids=("position-1",),
            ),
        )
    )
    monkeypatch.setattr(
        physical,
        "_capture_durable_shadow_snapshot",
        lambda *_args, **_kwargs: next(snapshots),
    )

    receipt = physical.prove_fast_paper_shadow_restart(
        expected_release_source_sha=_SHA,
        observation_seconds=5,
        paths=paths,
        runtime_executable=paths.current_link / ".venv" / "bin" / "python",
        command_runner=runner,
        sleeper=lambda _seconds: None,
    )
    assert receipt["state"] == "RESTART_RECONSTRUCTION_PROVEN"
    assert receipt["pre_restart_main_pid"] == 4321
    assert receipt["post_restart_main_pid"] == 4322
    assert receipt["automatic_restart_delta"] == 0
    assert runner.commands.count(("systemctl", "restart", _UNIT)) == 1
    assert paths.restart_receipt.is_file()


def test_restart_snapshot_regression_fails_closed() -> None:
    before = physical.DurableShadowSnapshot(
        manifest_fingerprint_sha256="a" * 64,
        run_id="run",
        binding_fingerprint_sha256="b" * 64,
        checkpoint_sequence=5,
        checkpoint_payload_sha256="c" * 64,
        runtime_state_fingerprint_sha256="d" * 64,
        last_processed_source_sequence=10,
        last_processed_source_event_id="event-10",
        pending_buy_fingerprint_sha256=None,
        market_position_ids=(),
    )
    after = physical.DurableShadowSnapshot(
        manifest_fingerprint_sha256="a" * 64,
        run_id="run",
        binding_fingerprint_sha256="b" * 64,
        checkpoint_sequence=4,
        checkpoint_payload_sha256="e" * 64,
        runtime_state_fingerprint_sha256="f" * 64,
        last_processed_source_sequence=9,
        last_processed_source_event_id="event-9",
        pending_buy_fingerprint_sha256=None,
        market_position_ids=(),
    )
    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="regress",
    ):
        physical._verify_restart_monotonicity(before, after)


def test_restart_pending_buy_change_requires_durable_advancement() -> None:
    before = physical.DurableShadowSnapshot(
        manifest_fingerprint_sha256="a" * 64,
        run_id="run",
        binding_fingerprint_sha256="b" * 64,
        checkpoint_sequence=5,
        checkpoint_payload_sha256="c" * 64,
        runtime_state_fingerprint_sha256="d" * 64,
        last_processed_source_sequence=10,
        last_processed_source_event_id="event-10",
        pending_buy_fingerprint_sha256="e" * 64,
        market_position_ids=(),
    )
    invalid = physical.DurableShadowSnapshot(
        manifest_fingerprint_sha256="a" * 64,
        run_id="run",
        binding_fingerprint_sha256="b" * 64,
        checkpoint_sequence=5,
        checkpoint_payload_sha256="c" * 64,
        runtime_state_fingerprint_sha256="f" * 64,
        last_processed_source_sequence=10,
        last_processed_source_event_id="event-10",
        pending_buy_fingerprint_sha256=None,
        market_position_ids=(),
    )
    with pytest.raises(
        physical.FastPaperShadowPhysicalCommissionError,
        match="pending BUY identity changed without durable advancement",
    ):
        physical._verify_restart_monotonicity(before, invalid)

    advanced = physical.DurableShadowSnapshot(
        manifest_fingerprint_sha256="a" * 64,
        run_id="run",
        binding_fingerprint_sha256="b" * 64,
        checkpoint_sequence=6,
        checkpoint_payload_sha256="1" * 64,
        runtime_state_fingerprint_sha256="2" * 64,
        last_processed_source_sequence=10,
        last_processed_source_event_id="event-10",
        pending_buy_fingerprint_sha256=None,
        market_position_ids=("position-1",),
    )
    physical._verify_restart_monotonicity(before, advanced)


def test_cli_packaging_and_authority_boundary() -> None:
    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(encoding="utf-8")
    target = (repo / "deploy" / "systemd" / "shreks.target").read_text(
        encoding="utf-8"
    )
    release_manager = (
        repo / "deploy" / "release" / "release_manager.py"
    ).read_text(encoding="utf-8")
    source = Path(physical.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-physical-commission = '
        '"shreks_brain.fast_paper_shadow_physical_commission:main"'
    ) in pyproject
    assert _UNIT not in target
    assert _UNIT not in release_manager

    for forbidden in (
        '"enable"',
        '"disable"',
        '"stop"',
        "shreks-paper-campaign.service",
        "shreks.target start",
        "score_candidate",
        "shreks_brain.scoring",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
