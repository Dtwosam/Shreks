from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_physical_cutover as cutover


_SHA = "a" * 40
_COMMISSIONING_FP = "b" * 64
_REPORT_FP = "c" * 64
_BASELINE_FP = "d" * 64
_MANIFEST_FP = "e" * 64
_CHAMPION_FP = "f" * 64
_BINDING_FP = "1" * 64
_POLICY_FP = "2" * 64


def _paths(tmp_path: Path) -> cutover.FastPaperPhysicalCutoverPaths:
    release = tmp_path / _SHA
    (release / ".venv" / "bin").mkdir(parents=True)
    python = release / ".venv" / "bin" / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    (release / "deploy" / "systemd").mkdir(parents=True)
    (release / "deploy" / "systemd" / cutover._UNIT).write_bytes(
        b"legacy-unit\n"
    )
    current = tmp_path / "current"
    current.symlink_to(release)

    systemd = tmp_path / "systemd"
    systemd.mkdir()
    active = systemd / cutover._UNIT
    active.write_bytes(b"legacy-unit\n")
    active.chmod(0o644)

    etc = tmp_path / "etc"
    etc.mkdir()
    config = etc / "fast-paper-authoritative.env"
    config.write_text("sealed\n", encoding="utf-8")

    proc = tmp_path / "proc"
    proc.mkdir()
    return cutover.FastPaperPhysicalCutoverPaths(
        current_link=current,
        active_unit_destination=active,
        authoritative_config_path=config,
        cutover_authorization_path=etc / "cutover-authorization.json",
        commissioning_root=tmp_path / "receipts",
        proc_root=proc,
    )


def _config(tmp_path: Path):
    root = tmp_path / "authoritative"
    roots = {}
    for name in (
        "decision",
        "execution",
        "buy",
        "usd",
        "reduction",
        "retry",
    ):
        value = root / name
        value.mkdir(parents=True, exist_ok=True)
        roots[name] = value
    checkpoint = roots["decision"] / "runtime-state.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    return SimpleNamespace(
        decision_config=SimpleNamespace(
            evidence_directory=roots["decision"],
            checkpoint_path=checkpoint,
        ),
        execution_config=SimpleNamespace(
            source_directory=roots["execution"],
        ),
        buy_authority_source_directory=roots["buy"],
        quote_usd_source_directory=roots["usd"],
        reduction_source_directory=roots["reduction"],
        pending_buy_retry_source_directory=roots["retry"],
    )


def _snapshot(
    config,
    *,
    checkpoint_sequence: int = 0,
    decision_sequence: int | None = 42,
    processed_sequence: int | None = None,
) -> cutover.DurableAuthoritativeSnapshot:
    return cutover.DurableAuthoritativeSnapshot(
        decision_state_fingerprint_sha256="3" * 64,
        decision_cursor_sequence=decision_sequence,
        decision_members=(config.decision_config.checkpoint_path.name,),
        paper_checkpoint_sequence=checkpoint_sequence,
        paper_checkpoint_payload_sha256="4" * 64,
        runtime_state_fingerprint_sha256="5" * 64,
        last_processed_source_sequence=processed_sequence,
        last_processed_source_event_id=(
            None if processed_sequence is None else "event"
        ),
        pending_buy=False,
        market_position_ids=(),
        source_members=(
            ("execution", ()),
            ("buy", ()),
            ("quote_usd", ()),
            ("reduction", ()),
            ("retry", ()),
        ),
    )


class FakeRunner:
    def __init__(self, paths):
        self.paths = paths
        self.mode = "legacy"
        self.pid = 1001
        self.invocation = "1" * 32
        self.nrestarts = 0
        self.commands = []
        self.journal_enabled = True
        self._make_proc(self.pid, cutover._LEGACY_MODULE)

    def _make_proc(self, pid: int, module: str) -> None:
        root = self.paths.proc_root / str(pid)
        root.mkdir(parents=True, exist_ok=True)
        cwd = root / "cwd"
        cwd.unlink(missing_ok=True)
        cwd.symlink_to(self.paths.current_link.resolve())
        (root / "cmdline").write_bytes(
            (
                str(self.paths.current_link / ".venv" / "bin" / "python")
                + "\0-m\0"
                + module
                + "\0"
            ).encode("utf-8")
        )

    def __call__(self, command):
        command = tuple(command)
        self.commands.append(command)
        if command == cutover._SHOW_COMMAND:
            active = self.mode in ("legacy", "fast")
            private = "yes" if self.mode == "fast" else "no"
            return cutover.HostCommandResult(
                0,
                (
                    f"ActiveState={'active' if active else 'inactive'}\n"
                    f"SubState={'running' if active else 'dead'}\n"
                    f"MainPID={self.pid if active else 0}\n"
                    f"NRestarts={self.nrestarts}\n"
                    "ExecMainStatus=0\n"
                    f"InvocationID={self.invocation if active else ''}\n"
                    f"FragmentPath={self.paths.active_unit_destination}\n"
                    "WorkingDirectory=/opt/shreks/current\n"
                    "User=shreks\n"
                    "Group=shreks\n"
                    f"PrivateNetwork={private}\n"
                ),
                "",
            )
        if command == cutover._SHADOW_SHOW_COMMAND:
            return cutover.HostCommandResult(
                0,
                "ActiveState=inactive\nSubState=dead\nMainPID=0\n",
                "",
            )
        if command == ("systemctl", "stop", cutover._UNIT):
            self.mode = "stopped"
            self.pid = 0
            self.invocation = ""
            return cutover.HostCommandResult(0, "", "")
        if command == ("systemctl", "daemon-reload"):
            return cutover.HostCommandResult(0, "", "")
        if command == ("systemctl", "start", cutover._UNIT):
            payload = self.paths.active_unit_destination.read_bytes()
            if payload == b"fast-unit\n":
                self.mode = "fast"
                self.pid = 2002
                self.invocation = "2" * 32
                self._make_proc(self.pid, cutover._FAST_MODULE)
            else:
                self.mode = "legacy"
                self.pid = 3003
                self.invocation = "3" * 32
                self._make_proc(self.pid, cutover._LEGACY_MODULE)
            return cutover.HostCommandResult(0, "", "")
        if command[:3] == ("journalctl", "-u", cutover._UNIT):
            if not self.journal_enabled:
                return cutover.HostCommandResult(0, "", "")
            rows = []
            for cycle in (1, 2):
                rows.append(
                    json.dumps(
                        {
                            "schema_name": cutover._STATUS_SCHEMA,
                            "schema_version": 1,
                            "mode": "PAPER_AUTHORITATIVE_FAST",
                            "state": "RUNNING",
                            "production_paper_cutover": "GRANTED_AND_ACTIVE",
                            "service_control_authority": "NOT_GRANTED",
                            "signing_submission_authority": "NOT_GRANTED",
                            "live": "DISABLED",
                            "manifest_fingerprint_sha256": _MANIFEST_FP,
                            "champion_version": "champion-v1",
                            "champion_fingerprint_sha256": _CHAMPION_FP,
                            "action_policy_version": 7,
                            "completed_cycles": cycle,
                            "decisions_produced": cycle,
                            "executions_committed": cycle - 1,
                            "decision_cursor_sequence": 42 + cycle,
                            "execution_cursor_sequence": (
                                None if cycle == 1 else 43
                            ),
                            "paper_checkpoint_sequence": cycle - 1,
                            "pending_buy": False,
                            "open_market_positions": 0,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            return cutover.HostCommandResult(0, "\n".join(rows) + "\n", "")
        raise AssertionError(f"unexpected command: {command}")


def _bootstrap():
    manifest = SimpleNamespace(
        release_source_sha=_SHA,
        manifest_fingerprint_sha256=_MANIFEST_FP,
        champion_version="champion-v1",
        champion_fingerprint_sha256=_CHAMPION_FP,
        action_policy=SimpleNamespace(version=7),
    )
    return SimpleNamespace(
        decision_bootstrap=SimpleNamespace(manifest=manifest),
        execution_bootstrap=SimpleNamespace(
            binding=SimpleNamespace(
                fast_run_id="fast-run-1",
                binding_fingerprint_sha256=_BINDING_FP,
            ),
            execution_policy=SimpleNamespace(
                policy_fingerprint_sha256=_POLICY_FP
            ),
        ),
    )


def _patch_common(monkeypatch, paths, config):
    monkeypatch.setattr(cutover, "_require_root", lambda: None)
    monkeypatch.setattr(
        cutover,
        "_service_identity",
        lambda: (os.geteuid(), os.getegid()),
    )
    monkeypatch.setattr(cutover.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(cutover, "_require_safe_root_parent", lambda _path: None)
    monkeypatch.setattr(
        cutover,
        "_candidate_unit_from_wheel",
        lambda *_args, **_kwargs: (b"fast-unit\n", _COMMISSIONING_FP),
    )
    monkeypatch.setattr(
        cutover,
        "_load_authoritative_config",
        lambda _path: config,
    )
    monkeypatch.setattr(
        cutover,
        "_refresh_final_legacy_handoff",
        lambda *_args, **_kwargs: _bootstrap(),
    )


def test_physical_preflight_requires_legacy_active_shadow_quiescent_and_pristine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    config = _config(tmp_path)
    runner = FakeRunner(paths)
    _patch_common(monkeypatch, paths, config)
    monkeypatch.setattr(
        cutover,
        "preflight_fast_paper_authoritative_host",
        lambda **_kwargs: {
            "state": "READY_FOR_PROTECTED_PAPER_CUTOVER_REVIEW",
            "release_source_sha": _SHA,
            "fast_run_id": "fast-run-1",
            "baseline_receipt_fingerprint_sha256": _BASELINE_FP,
        },
    )
    monkeypatch.setattr(
        cutover,
        "_capture_authoritative_snapshot",
        lambda _config: _snapshot(config),
    )
    monkeypatch.setattr(
        cutover,
        "_require_root_unit_metadata",
        lambda _stat: None,
    )

    receipt = cutover.preflight_fast_paper_physical_cutover(
        expected_release_source_sha=_SHA,
        authoritative_release_wheel_path=tmp_path / "wheel.whl",
        release_platform="x86_64-unknown-linux-gnu",
        baseline_receipt_path=tmp_path / "baseline.json",
        paths=paths,
        runtime_executable=paths.current_link / ".venv" / "bin" / "python",
        command_runner=runner,
    )

    assert receipt["state"] == "READY_FOR_PROTECTED_PAPER_CUTOVER"
    assert receipt["production_paper_cutover"] == "NOT_GRANTED"
    assert runner.mode == "legacy"


def test_activation_stops_legacy_runs_final_preflight_then_starts_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    config = _config(tmp_path)
    runner = FakeRunner(paths)
    before = _snapshot(config)
    after = _snapshot(
        config,
        checkpoint_sequence=1,
        decision_sequence=43,
        processed_sequence=43,
    )
    snapshots = iter((before, after))
    _patch_common(monkeypatch, paths, config)
    monkeypatch.setattr(
        cutover,
        "preflight_fast_paper_physical_cutover",
        lambda **_kwargs: {"state": "READY_FOR_PROTECTED_PAPER_CUTOVER"},
    )
    observed = {}

    def final_preflight(**_kwargs):
        observed["mode_at_final_preflight"] = runner.mode
        return {
            "decision": "CUTOVER_PREFLIGHT_READY",
            "report_fingerprint_sha256": _REPORT_FP,
        }

    monkeypatch.setattr(
        cutover,
        "assess_fast_paper_cutover_preflight",
        final_preflight,
    )
    monkeypatch.setattr(
        cutover,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: _bootstrap(),
    )
    monkeypatch.setattr(
        cutover,
        "read_fast_paper_authoritative_cutover_baseline_receipt",
        lambda _path: {"receipt_fingerprint_sha256": _BASELINE_FP},
    )
    monkeypatch.setattr(
        cutover,
        "_capture_authoritative_snapshot",
        lambda _config: next(snapshots),
    )

    receipt = cutover.activate_fast_paper_physical_cutover(
        expected_release_source_sha=_SHA,
        authoritative_release_wheel_path=tmp_path / "wheel.whl",
        release_platform="x86_64-unknown-linux-gnu",
        baseline_receipt_path=tmp_path / "baseline.json",
        fast_manifest_path=tmp_path / "manifest.json",
        champion_registry_path=tmp_path / "registry.json",
        shadow_restart_receipt_path=tmp_path / "restart.json",
        shadow_ledger_database_path=tmp_path / "shadow.sqlite3",
        legacy_runtime_manifest_path=tmp_path / "legacy.json",
        legacy_observer_database_path=tmp_path / "observer.sqlite3",
        observation_seconds=5,
        paths=paths,
        runtime_executable=paths.current_link / ".venv" / "bin" / "python",
        command_runner=runner,
        sleeper=lambda _seconds: None,
        clock_unix_ms=lambda: 123_456,
    )

    assert observed["mode_at_final_preflight"] == "stopped"
    assert receipt["state"] == "PRODUCTION_PAPER_CUTOVER_ACTIVE"
    assert receipt["production_paper_cutover"] == "ACTIVE"
    assert receipt["authoritative_paper_runtime"] == "FAST_LANE_LEARNED_ACTIVE"
    assert receipt["live_authority"] == "DISABLED"
    assert runner.mode == "fast"
    assert paths.active_unit_destination.read_bytes() == b"fast-unit\n"
    assert paths.cutover_authorization_path.is_file()
    assert paths.success_receipt.is_file()
    assert runner.commands.count(("systemctl", "stop", cutover._UNIT)) == 1
    assert runner.commands.count(("systemctl", "daemon-reload")) == 1
    assert runner.commands.count(("systemctl", "start", cutover._UNIT)) == 1


def test_final_preflight_failure_restores_legacy_when_state_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    config = _config(tmp_path)
    runner = FakeRunner(paths)
    before = _snapshot(config)
    _patch_common(monkeypatch, paths, config)
    monkeypatch.setattr(
        cutover,
        "preflight_fast_paper_physical_cutover",
        lambda **_kwargs: {"state": "READY_FOR_PROTECTED_PAPER_CUTOVER"},
    )
    monkeypatch.setattr(
        cutover,
        "assess_fast_paper_cutover_preflight",
        lambda **_kwargs: {
            "decision": "CUTOVER_PREFLIGHT_NOT_READY",
            "report_fingerprint_sha256": _REPORT_FP,
        },
    )
    monkeypatch.setattr(
        cutover,
        "_capture_authoritative_snapshot",
        lambda _config: before,
    )

    with pytest.raises(
        cutover.FastPaperPhysicalCutoverError,
        match="legacy PAPER authority restored",
    ):
        cutover.activate_fast_paper_physical_cutover(
            expected_release_source_sha=_SHA,
            authoritative_release_wheel_path=tmp_path / "wheel.whl",
            release_platform="x86_64-unknown-linux-gnu",
            baseline_receipt_path=tmp_path / "baseline.json",
            fast_manifest_path=tmp_path / "manifest.json",
            champion_registry_path=tmp_path / "registry.json",
            shadow_restart_receipt_path=tmp_path / "restart.json",
            shadow_ledger_database_path=tmp_path / "shadow.sqlite3",
            legacy_runtime_manifest_path=tmp_path / "legacy.json",
            legacy_observer_database_path=tmp_path / "observer.sqlite3",
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link / ".venv" / "bin" / "python",
            command_runner=runner,
            sleeper=lambda _seconds: None,
        )

    assert runner.mode == "legacy"
    assert paths.active_unit_destination.read_bytes() == b"legacy-unit\n"
    assert not paths.cutover_authorization_path.exists()


def test_post_start_failure_never_restores_legacy_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    config = _config(tmp_path)
    runner = FakeRunner(paths)
    runner.journal_enabled = False
    before = _snapshot(config)
    changed = _snapshot(
        config,
        checkpoint_sequence=1,
        decision_sequence=43,
        processed_sequence=43,
    )
    snapshots = iter((before, changed))
    _patch_common(monkeypatch, paths, config)
    monkeypatch.setattr(
        cutover,
        "preflight_fast_paper_physical_cutover",
        lambda **_kwargs: {"state": "READY_FOR_PROTECTED_PAPER_CUTOVER"},
    )
    monkeypatch.setattr(
        cutover,
        "assess_fast_paper_cutover_preflight",
        lambda **_kwargs: {
            "decision": "CUTOVER_PREFLIGHT_READY",
            "report_fingerprint_sha256": _REPORT_FP,
        },
    )
    monkeypatch.setattr(
        cutover,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: _bootstrap(),
    )
    monkeypatch.setattr(
        cutover,
        "read_fast_paper_authoritative_cutover_baseline_receipt",
        lambda _path: {"receipt_fingerprint_sha256": _BASELINE_FP},
    )
    monkeypatch.setattr(
        cutover,
        "_capture_authoritative_snapshot",
        lambda _config: next(snapshots),
    )

    with pytest.raises(
        cutover.FastPaperPhysicalCutoverError,
        match="legacy score authority is not restored",
    ):
        cutover.activate_fast_paper_physical_cutover(
            expected_release_source_sha=_SHA,
            authoritative_release_wheel_path=tmp_path / "wheel.whl",
            release_platform="x86_64-unknown-linux-gnu",
            baseline_receipt_path=tmp_path / "baseline.json",
            fast_manifest_path=tmp_path / "manifest.json",
            champion_registry_path=tmp_path / "registry.json",
            shadow_restart_receipt_path=tmp_path / "restart.json",
            shadow_ledger_database_path=tmp_path / "shadow.sqlite3",
            legacy_runtime_manifest_path=tmp_path / "legacy.json",
            legacy_observer_database_path=tmp_path / "observer.sqlite3",
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link / ".venv" / "bin" / "python",
            command_runner=runner,
            sleeper=lambda _seconds: None,
            clock_unix_ms=lambda: 123_456,
        )

    assert runner.mode == "stopped"
    assert paths.active_unit_destination.read_bytes() == b"legacy-unit\n"
    assert not paths.cutover_authorization_path.exists()
    assert paths.failure_receipt.is_file()
    failure = json.loads(paths.failure_receipt.read_text(encoding="utf-8"))
    assert failure["state"] == "MANUAL_RECOVERY_REQUIRED"
    assert failure["legacy_service_restarted"] is False


def test_post_start_failure_with_unchanged_state_still_never_restores_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    config = _config(tmp_path)
    runner = FakeRunner(paths)
    runner.journal_enabled = False
    pristine = _snapshot(config)
    snapshots = iter((pristine, pristine))
    _patch_common(monkeypatch, paths, config)
    monkeypatch.setattr(
        cutover,
        "preflight_fast_paper_physical_cutover",
        lambda **_kwargs: {"state": "READY_FOR_PROTECTED_PAPER_CUTOVER"},
    )
    monkeypatch.setattr(
        cutover,
        "assess_fast_paper_cutover_preflight",
        lambda **_kwargs: {
            "decision": "CUTOVER_PREFLIGHT_READY",
            "report_fingerprint_sha256": _REPORT_FP,
        },
    )
    monkeypatch.setattr(
        cutover,
        "read_fast_paper_authoritative_cutover_baseline_receipt",
        lambda _path: {"receipt_fingerprint_sha256": _BASELINE_FP},
    )
    monkeypatch.setattr(
        cutover,
        "_capture_authoritative_snapshot",
        lambda _config: next(snapshots),
    )

    with pytest.raises(
        cutover.FastPaperPhysicalCutoverError,
        match="legacy score authority is not restored",
    ):
        cutover.activate_fast_paper_physical_cutover(
            expected_release_source_sha=_SHA,
            authoritative_release_wheel_path=tmp_path / "wheel.whl",
            release_platform="x86_64-unknown-linux-gnu",
            baseline_receipt_path=tmp_path / "baseline.json",
            fast_manifest_path=tmp_path / "manifest.json",
            champion_registry_path=tmp_path / "registry.json",
            shadow_restart_receipt_path=tmp_path / "restart.json",
            shadow_ledger_database_path=tmp_path / "shadow.sqlite3",
            legacy_runtime_manifest_path=tmp_path / "legacy.json",
            legacy_observer_database_path=tmp_path / "observer.sqlite3",
            observation_seconds=5,
            paths=paths,
            runtime_executable=paths.current_link / ".venv" / "bin" / "python",
            command_runner=runner,
            sleeper=lambda _seconds: None,
            clock_unix_ms=lambda: 123_456,
        )

    assert runner.mode == "stopped"
    assert paths.active_unit_destination.read_bytes() == b"legacy-unit\n"
    assert not paths.cutover_authorization_path.exists()
    failure = json.loads(paths.failure_receipt.read_text(encoding="utf-8"))
    assert failure["state"] == "MANUAL_RECOVERY_REQUIRED"
    assert failure["authoritative_state_changed"] is False
    assert failure["legacy_service_restarted"] is False


def test_default_command_runner_rejects_unreviewed_service_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cutover.subprocess,
        "run",
        lambda command, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    for forbidden in (
        ("systemctl", "restart", cutover._UNIT),
        ("systemctl", "enable", cutover._UNIT),
        ("systemctl", "disable", cutover._UNIT),
        ("systemctl", "start", "other.service"),
        ("systemctl", "stop", cutover._SHADOW_UNIT),
    ):
        with pytest.raises(
            cutover.FastPaperPhysicalCutoverError,
            match="allowlist",
        ):
            cutover._default_command_runner(forbidden)
