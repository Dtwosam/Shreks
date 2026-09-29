from __future__ import annotations

import json
import os
import sqlite3
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
_FINAL_RUN_ID = "fast-final-run-1"
_ROOT_MANAGER_PROOF_FP = "9" * 64


def failure_marker_is_fail_closed(document: dict[str, object]) -> bool:
    return (
        document.get("production_paper_cutover")
        == "STOPPED_MANUAL_RECOVERY"
        and document.get("signing_submission_authority")
        == "NOT_GRANTED"
        and document.get("live_authority") == "DISABLED"
    )


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
            run_id="fast-provisional-run-1",
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


def _bootstrap(run_id: str = _FINAL_RUN_ID):
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
                fast_run_id=run_id,
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
        "_require_final_run_namespace_unused",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        cutover,
        "_initialize_final_legacy_handoff",
        lambda supplied_config, **_kwargs: (
            supplied_config,
            _bootstrap(),
        ),
    )
    monkeypatch.setattr(
        cutover,
        "_verify_release_manager_installation_proof",
        lambda *_args, **_kwargs: {
            "proof_fingerprint_sha256": _ROOT_MANAGER_PROOF_FP,
        },
    )


def test_final_fast_run_namespace_must_be_unused_across_all_authoritative_tables(
    tmp_path: Path,
) -> None:
    database = tmp_path / "observer.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE fast_paper_authoritative_bindings (
                fast_run_id TEXT PRIMARY KEY
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE paper_loop_checkpoints (
                run_id TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE fast_paper_authoritative_runtime_states (
                fast_run_id TEXT NOT NULL
            )
            """
        )
        connection.commit()
    config = SimpleNamespace(
        execution_config=SimpleNamespace(database_path=database)
    )

    cutover._require_final_run_namespace_unused(config, _FINAL_RUN_ID)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO paper_loop_checkpoints(run_id) VALUES (?)",
            (_FINAL_RUN_ID,),
        )
        connection.commit()

    with pytest.raises(
        cutover.FastPaperPhysicalCutoverError,
        match="already used",
    ):
        cutover._require_final_run_namespace_unused(
            config,
            _FINAL_RUN_ID,
        )


def test_final_handoff_initializes_fresh_run_and_retargets_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "authoritative.env"
    config_path.write_text("provisional\n", encoding="utf-8")
    database = tmp_path / "observer.sqlite3"
    database.write_bytes(b"db")
    provisional_config = SimpleNamespace(
        execution_config=SimpleNamespace(database_path=database),
    )
    manifest = SimpleNamespace()
    execution_policy = SimpleNamespace()
    provisional_bootstrap = SimpleNamespace(
        decision_bootstrap=SimpleNamespace(manifest=manifest),
        execution_bootstrap=SimpleNamespace(
            binding=SimpleNamespace(fast_run_id="fast-provisional-run-1"),
            execution_policy=execution_policy,
        ),
    )
    final_binding = SimpleNamespace(fast_run_id=_FINAL_RUN_ID)
    final_checkpoint = SimpleNamespace(sequence=0)
    final_bootstrap = SimpleNamespace(
        execution_bootstrap=SimpleNamespace(
            binding=final_binding,
            checkpoint=final_checkpoint,
        )
    )
    final_config = SimpleNamespace(
        execution_config=SimpleNamespace(
            database_path=database,
            run_id=_FINAL_RUN_ID,
        )
    )
    legacy_manifest = SimpleNamespace(
        paper_run_id="legacy-run-1",
        manifest_fingerprint_sha256="8" * 64,
    )
    legacy_checkpoint = SimpleNamespace(sequence=99)
    calls = {"bootstrap": 0}

    def bootstrap(config):
        calls["bootstrap"] += 1
        return (
            provisional_bootstrap
            if config is provisional_config
            else final_bootstrap
        )

    monkeypatch.setattr(
        cutover,
        "bootstrap_fast_paper_authoritative_runtime",
        bootstrap,
    )
    monkeypatch.setattr(
        cutover,
        "decode_observer_paper_campaign_runtime_manifest",
        lambda _payload: legacy_manifest,
    )
    monkeypatch.setattr(
        cutover,
        "load_latest_paper_checkpoint",
        lambda database_path, run_id: (
            legacy_checkpoint
            if Path(database_path) == database
            and run_id == "legacy-run-1"
            else None
        ),
    )
    observed = {}

    def initialize(*args, **kwargs):
        observed["initialize_args"] = args
        observed["initialize_kwargs"] = kwargs
        return SimpleNamespace(
            binding=final_binding,
            checkpoint=final_checkpoint,
        )

    monkeypatch.setattr(
        cutover,
        "initialize_fast_paper_authoritative_handoff",
        initialize,
    )
    monkeypatch.setattr(
        cutover,
        "read_fast_paper_authoritative_cutover_environment",
        lambda _path: {
            "SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID": (
                "fast-provisional-run-1"
            )
        },
    )
    monkeypatch.setattr(
        cutover,
        "validate_fast_paper_authoritative_cutover_environment",
        lambda environment, supplied_manifest, authoritative_database_path: (
            final_config
            if environment[
                "SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID"
            ]
            == _FINAL_RUN_ID
            and supplied_manifest is manifest
            and Path(authoritative_database_path) == database
            else pytest.fail("final environment binding drift")
        ),
    )
    monkeypatch.setattr(
        cutover,
        "encode_fast_paper_authoritative_cutover_environment",
        lambda environment: (
            f"run_id={environment['SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID']}\n"
        ),
    )
    monkeypatch.setattr(
        cutover,
        "_read_regular_no_follow",
        lambda path, label: (
            (b"legacy-manifest\n", os.stat(config_path))
            if "legacy" in label
            else (config_path.read_bytes(), os.stat(config_path))
        ),
    )

    def replace_file(path, payload, **metadata):
        observed["config_path"] = path
        observed["config_payload"] = payload
        observed["config_metadata"] = metadata

    monkeypatch.setattr(cutover, "_replace_file_atomically", replace_file)

    restored_config, restored_bootstrap = (
        cutover._initialize_final_legacy_handoff(
            provisional_config,
            final_fast_run_id=_FINAL_RUN_ID,
            authoritative_config_path=config_path,
            legacy_runtime_manifest_path=tmp_path / "legacy.json",
            legacy_observer_database_path=database,
            created_at_unix_ms=123_456,
        )
    )

    assert restored_config is final_config
    assert restored_bootstrap is final_bootstrap
    assert observed["initialize_args"][2] is legacy_checkpoint
    assert observed["initialize_kwargs"]["fast_run_id"] == _FINAL_RUN_ID
    assert observed["config_path"] == config_path
    assert observed["config_payload"] == (
        f"run_id={_FINAL_RUN_ID}\n".encode("utf-8")
    )
    assert calls["bootstrap"] == 2


def test_final_handoff_rejects_different_legacy_database_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "authoritative.env"
    config_path.write_text("provisional\n", encoding="utf-8")
    authoritative_database = tmp_path / "authoritative.sqlite3"
    authoritative_database.write_bytes(b"authoritative")
    other_database = tmp_path / "other.sqlite3"
    other_database.write_bytes(b"other")
    provisional_config = SimpleNamespace(
        execution_config=SimpleNamespace(
            database_path=authoritative_database,
        ),
    )
    provisional_bootstrap = SimpleNamespace(
        decision_bootstrap=SimpleNamespace(manifest=SimpleNamespace()),
        execution_bootstrap=SimpleNamespace(
            binding=SimpleNamespace(
                fast_run_id="fast-provisional-run-1"
            ),
            execution_policy=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(
        cutover,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: provisional_bootstrap,
    )
    monkeypatch.setattr(
        cutover,
        "decode_observer_paper_campaign_runtime_manifest",
        lambda _payload: SimpleNamespace(
            paper_run_id="legacy-run-1",
            manifest_fingerprint_sha256="8" * 64,
        ),
    )
    monkeypatch.setattr(
        cutover,
        "_read_regular_no_follow",
        lambda _path, _label: (
            b"legacy-manifest\n",
            os.stat(config_path),
        ),
    )
    monkeypatch.setattr(
        cutover,
        "initialize_fast_paper_authoritative_handoff",
        lambda *_args, **_kwargs: pytest.fail(
            "handoff must not initialize from a different database"
        ),
    )

    with pytest.raises(
        cutover.FastPaperPhysicalCutoverError,
        match="handoff initialization",
    ):
        cutover._initialize_final_legacy_handoff(
            provisional_config,
            final_fast_run_id=_FINAL_RUN_ID,
            authoritative_config_path=config_path,
            legacy_runtime_manifest_path=tmp_path / "legacy.json",
            legacy_observer_database_path=other_database,
            created_at_unix_ms=123_456,
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
            "fast_run_id": "fast-provisional-run-1",
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
        release_manager_installation_proof_path=(
            tmp_path / "release-manager-proof.json"
        ),
        final_fast_run_id=_FINAL_RUN_ID,
        paths=paths,
        runtime_executable=paths.current_link / ".venv" / "bin" / "python",
        command_runner=runner,
    )

    assert receipt["state"] == "READY_FOR_PROTECTED_PAPER_CUTOVER"
    assert receipt["production_paper_cutover"] == "NOT_GRANTED"
    assert (
        receipt[
            "release_manager_installation_proof_fingerprint_sha256"
        ]
        == _ROOT_MANAGER_PROOF_FP
    )
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
        lambda **_kwargs: {
            "state": "READY_FOR_PROTECTED_PAPER_CUTOVER",
            "release_manager_installation_proof_fingerprint_sha256": (
                _ROOT_MANAGER_PROOF_FP
            ),
        },
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
        release_manager_installation_proof_path=(
            tmp_path / "release-manager-proof.json"
        ),
        final_fast_run_id=_FINAL_RUN_ID,
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
    assert (
        receipt[
            "release_manager_installation_proof_fingerprint_sha256"
        ]
        == _ROOT_MANAGER_PROOF_FP
    )
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
        lambda **_kwargs: {
            "state": "READY_FOR_PROTECTED_PAPER_CUTOVER",
            "release_manager_installation_proof_fingerprint_sha256": (
                _ROOT_MANAGER_PROOF_FP
            ),
        },
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
            final_fast_run_id=_FINAL_RUN_ID,
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
        lambda **_kwargs: {
            "state": "READY_FOR_PROTECTED_PAPER_CUTOVER",
            "release_manager_installation_proof_fingerprint_sha256": (
                _ROOT_MANAGER_PROOF_FP
            ),
        },
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
            final_fast_run_id=_FINAL_RUN_ID,
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
    assert paths.active_unit_destination.read_bytes() == b"fast-unit\n"
    assert paths.cutover_authorization_path.is_file()
    revocation = json.loads(
        paths.cutover_authorization_path.read_text(encoding="utf-8")
    )
    assert revocation["state"] == "REVOKED_MANUAL_RECOVERY"
    assert (
        revocation["production_paper_cutover"]
        == "STOPPED_MANUAL_RECOVERY"
    )
    assert revocation["live_authority"] == "DISABLED"
    assert paths.failure_receipt.is_file()
    failure = json.loads(paths.failure_receipt.read_text(encoding="utf-8"))
    assert failure["state"] == "MANUAL_RECOVERY_REQUIRED"
    assert failure["legacy_service_restarted"] is False
    assert failure["fast_unit_retained"] is True


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
        lambda **_kwargs: {
            "state": "READY_FOR_PROTECTED_PAPER_CUTOVER",
            "release_manager_installation_proof_fingerprint_sha256": (
                _ROOT_MANAGER_PROOF_FP
            ),
        },
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
            final_fast_run_id=_FINAL_RUN_ID,
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
    assert paths.active_unit_destination.read_bytes() == b"fast-unit\n"
    assert paths.cutover_authorization_path.is_file()
    revocation = json.loads(
        paths.cutover_authorization_path.read_text(encoding="utf-8")
    )
    assert revocation["state"] == "REVOKED_MANUAL_RECOVERY"
    assert failure_marker_is_fail_closed(revocation)
    failure = json.loads(paths.failure_receipt.read_text(encoding="utf-8"))
    assert failure["state"] == "MANUAL_RECOVERY_REQUIRED"
    assert failure["authoritative_state_changed"] is False
    assert failure["legacy_service_restarted"] is False
    assert failure["fast_unit_retained"] is True


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
