from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.host_acceptance import (
    HostAcceptanceStage,
    HostCheckStatus,
    HostResourceObservation,
    ProtectedPathKind,
)
from shreks_brain.host_acceptance.collector import (
    HostAcceptanceCaptureConfig,
    HostCommandResult,
    ProtectedPathRequirement,
    collect_host_acceptance_record,
)


_SOURCE_SHA = "1" * 40
_CAMPAIGN_SHA = "a" * 64


def _resource_observation() -> HostResourceObservation:
    return HostResourceObservation(
        boot_id="13a576c1-3b0b-4ed2-a173-cd2f46fa8371",
        uptime_seconds=123.5,
        load_average=(0.1, 0.2, 0.3),
        memory_total_bytes=8_000_000,
        memory_available_bytes=6_000_000,
        state_filesystem_total_bytes=100_000_000,
        state_filesystem_free_bytes=80_000_000,
    )


def _build_config(tmp_path: Path, *, expected_sha: str = _SOURCE_SHA) -> tuple[HostAcceptanceCaptureConfig, dict[str, Path]]:
    managed = tmp_path / "releases"
    release = managed / _SOURCE_SHA
    release.mkdir(parents=True)
    (release / "RELEASE_MANIFEST.json").write_text("sealed-release-manifest\n")
    current = tmp_path / "current"
    current.symlink_to(release, target_is_directory=True)

    observer_db = tmp_path / "shreks.db"
    observer_db.write_bytes(b"sqlite-fixture")
    e11 = tmp_path / "e11.json"
    e11.write_text("{}\n")
    campaign = tmp_path / "paper-campaign.json"
    campaign.write_text("{}\n")
    risk = tmp_path / "risk-control.json"
    risk.write_text('{"schema":"g7"}\n')

    backup_root = tmp_path / "backups"
    older = backup_root / "001-older"
    newer = backup_root / "002-newer"
    older.mkdir(parents=True)
    newer.mkdir()
    (older / "manifest.json").write_text("old-manifest\n")
    (newer / "manifest.json").write_text("new-manifest\n")

    dashboard_password = tmp_path / "dashboard-password"
    dashboard_password.write_text("DO-NOT-READ-DASHBOARD-SECRET")
    dashboard_password.chmod(0o640)
    telegram_token = tmp_path / "telegram-bot-token"
    telegram_token.write_text("DO-NOT-READ-TELEGRAM-SECRET")
    telegram_token.chmod(0o640)

    protected = (
        ProtectedPathRequirement(
            role="dashboard_password",
            path=dashboard_password,
            expected_kind=ProtectedPathKind.FILE,
            expected_mode=0o640,
            secret=True,
        ),
        ProtectedPathRequirement(
            role="telegram_bot_token",
            path=telegram_token,
            expected_kind=ProtectedPathKind.FILE,
            expected_mode=0o640,
            secret=True,
        ),
        ProtectedPathRequirement(
            role="campaign_manifest",
            path=campaign,
            expected_kind=ProtectedPathKind.FILE,
            expected_mode=None,
            secret=False,
        ),
    )

    config = HostAcceptanceCaptureConfig(
        stage=HostAcceptanceStage.BASELINE,
        host_label="shreks-prod-eu-1",
        expected_release_sha=expected_sha,
        observer_database_path=observer_db,
        evidence_path=e11,
        campaign_manifest_path=campaign,
        risk_control_path=risk,
        backup_root=backup_root,
        dashboard_port=8787,
        paper_cycle_interval_seconds=1.0,
        current_release_path=current,
        managed_releases_path=managed,
        state_filesystem_path=tmp_path,
        protected_paths=protected,
    )
    return config, {
        "release": release,
        "risk": risk,
        "newer": newer,
        "dashboard_password": dashboard_password,
        "telegram_token": telegram_token,
    }


def _command_runner(commands: list[tuple[str, ...]], *, public_dashboard: bool = False):
    def run(command: tuple[str, ...]) -> HostCommandResult:
        commands.append(command)
        assert type(command) is tuple
        assert command
        assert command[0] in ("systemctl", "ss")
        forbidden = {"start", "stop", "restart", "enable", "disable", "reboot", "poweroff", "kill"}
        assert not forbidden.intersection(command)

        if command[0] == "systemctl" and command[1] == "show":
            unit = command[2]
            sub = "waiting" if unit.endswith(".timer") else "running"
            if unit == "shreks.target":
                sub = "active"
            return HostCommandResult(
                returncode=0,
                stdout=(
                    "ActiveState=active\n"
                    f"SubState={sub}\n"
                    "NRestarts=1\n"
                    "ExecMainStatus=0\n"
                    "ActiveEnterTimestamp=Wed 2026-08-26 13:00:00 UTC\n"
                ),
            )
        if command[0] == "systemctl" and command[1] == "is-enabled":
            unit = command[2]
            enabled = unit in {
                "shreks.target",
                "shreks-telemetry.timer",
                "shreks-dashboard.service",
                "shreks-alerts.timer",
                "shreks-backup.timer",
            }
            return HostCommandResult(returncode=0 if enabled else 1, stdout="enabled\n" if enabled else "disabled\n")
        if command == ("ss", "-ltnH"):
            local = "0.0.0.0:8787" if public_dashboard else "127.0.0.1:8787"
            return HostCommandResult(
                returncode=0,
                stdout=(
                    f"LISTEN 0 128 {local} 0.0.0.0:*\n"
                    "LISTEN 0 128 [::1]:8787 [::]:*\n"
                ),
            )
        raise AssertionError(f"unexpected command: {command!r}")

    return run


def _patch_sealed_sources(monkeypatch: pytest.MonkeyPatch, paths: dict[str, Path]) -> None:
    import shreks_brain.host_acceptance.collector as collector

    ledger = SimpleNamespace(
        as_of_unix_ms=1_250,
        entries=(SimpleNamespace(), SimpleNamespace()),
        processed_intent_keys=frozenset({"intent-b", "intent-a"}),
        positions=(SimpleNamespace(position_id="position-a", state=SimpleNamespace(value="OPEN")),),
    )
    restored_state = SimpleNamespace(
        last_cycle_at_unix_ms=1_300,
        ledger=ledger,
        managed_positions=(SimpleNamespace(position_id="position-a"),),
    )
    manifest = SimpleNamespace(
        paper_run_id="paper-run-1",
        candidate=SimpleNamespace(candidate_version="candidate-v1"),
        manifest_fingerprint_sha256=_CAMPAIGN_SHA,
    )
    monkeypatch.setattr(
        collector,
        "preflight_observer_paper_campaign_runtime",
        lambda _config, status_sink=None: SimpleNamespace(
            manifest=manifest,
            restored_state=restored_state,
        ),
    )
    monkeypatch.setattr(
        collector,
        "load_operator_risk_control_state",
        lambda _path: SimpleNamespace(
            schema_version="g7-operator-risk-control-v1",
            revision=4,
            halt_new_entries=True,
            kill_switch_active=False,
            updated_at_unix_ms=1_200,
            last_command=SimpleNamespace(value="HALT_NEW_ENTRIES"),
            last_source=SimpleNamespace(value="HOST_CLI"),
        ),
    )

    def verify_bundle(path: Path):
        assert path in (paths["newer"], paths["newer"].parent / "001-older")
        if path.name == "002-newer":
            return SimpleNamespace(
                created_at_unix_ms=1_250,
                paper_run_id="paper-run-1",
                campaign_manifest_fingerprint_sha256=_CAMPAIGN_SHA,
            )
        return SimpleNamespace(
            created_at_unix_ms=1_100,
            paper_run_id="paper-run-1",
            campaign_manifest_fingerprint_sha256=_CAMPAIGN_SHA,
        )

    monkeypatch.setattr(collector, "verify_backup_bundle", verify_bundle)


def test_collector_builds_passing_record_from_sealed_read_only_sources(tmp_path, monkeypatch):
    config, paths = _build_config(tmp_path)
    _patch_sealed_sources(monkeypatch, paths)
    commands: list[tuple[str, ...]] = []

    record = collect_host_acceptance_record(
        config,
        command_runner=_command_runner(commands),
        clock_unix_ms=lambda: 1_777_000_000_000,
        resource_reader=lambda _path: _resource_observation(),
    )

    assert record.overall_status is HostCheckStatus.PASS
    assert record.release.current_target_name == _SOURCE_SHA
    assert record.release.release_manifest_sha256 == hashlib.sha256(
        (paths["release"] / "RELEASE_MANIFEST.json").read_bytes()
    ).hexdigest()
    assert record.paper.processed_intent_keys == ("intent-a", "intent-b")
    assert record.paper.managed_position_ids == ("position-a",)
    assert record.risk_control.last_command == "HALT_NEW_ENTRIES"
    assert record.risk_control.last_source == "HOST_CLI"
    assert record.backup.bundle_path == str(paths["newer"])
    assert record.dashboard.listeners == ("127.0.0.1:8787", "[::1]:8787")
    assert len(record.units) == 8
    assert any(command[:2] == ("systemctl", "show") for command in commands)
    assert any(command[:2] == ("systemctl", "is-enabled") for command in commands)
    assert ("ss", "-ltnH") in commands


def test_collector_marks_release_mismatch_and_public_dashboard_as_fail(tmp_path, monkeypatch):
    config, paths = _build_config(tmp_path, expected_sha="2" * 40)
    _patch_sealed_sources(monkeypatch, paths)

    record = collect_host_acceptance_record(
        config,
        command_runner=_command_runner([], public_dashboard=True),
        clock_unix_ms=lambda: 1_777_000_000_000,
        resource_reader=lambda _path: _resource_observation(),
    )

    assert record.release.check_status is HostCheckStatus.FAIL
    assert record.dashboard.check_status is HostCheckStatus.FAIL
    assert record.dashboard.loopback_only is False
    assert record.overall_status is HostCheckStatus.FAIL


def test_secret_protected_paths_are_stat_only(tmp_path, monkeypatch):
    config, paths = _build_config(tmp_path)
    _patch_sealed_sources(monkeypatch, paths)
    secret_paths = {paths["dashboard_password"].resolve(), paths["telegram_token"].resolve()}
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    original_open = Path.open

    def reject_secret_read_bytes(path: Path):
        if path.resolve() in secret_paths:
            raise AssertionError("secret file content must never be read")
        return original_read_bytes(path)

    def reject_secret_read_text(path: Path, *args, **kwargs):
        if path.resolve() in secret_paths:
            raise AssertionError("secret file content must never be read")
        return original_read_text(path, *args, **kwargs)

    def reject_secret_open(path: Path, *args, **kwargs):
        if path.resolve() in secret_paths:
            raise AssertionError("secret file content must never be opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", reject_secret_read_bytes)
    monkeypatch.setattr(Path, "read_text", reject_secret_read_text)
    monkeypatch.setattr(Path, "open", reject_secret_open)

    record = collect_host_acceptance_record(
        config,
        command_runner=_command_runner([]),
        clock_unix_ms=lambda: 1_777_000_000_000,
        resource_reader=lambda _path: _resource_observation(),
    )

    secret_roles = {item.role for item in record.protected_paths if item.role.endswith(("password", "token"))}
    assert secret_roles == {"dashboard_password", "telegram_bot_token"}
    assert record.overall_status is HostCheckStatus.PASS
