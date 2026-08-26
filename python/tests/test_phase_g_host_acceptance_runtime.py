from __future__ import annotations

from dataclasses import replace
import io
from pathlib import Path
import stat

import pytest

from shreks_brain.host_acceptance import (
    HOST_ACCEPTANCE_SCHEMA_VERSION,
    PHASE_G_REQUIRED_UNITS,
    BackupObservation,
    DashboardExposureObservation,
    HostAcceptanceRecord,
    HostAcceptanceStage,
    HostCheckStatus,
    HostResourceObservation,
    PaperRecoveryObservation,
    ReleaseObservation,
    RiskControlObservation,
    SystemdUnitObservation,
    decode_host_acceptance_record,
    fingerprint_host_acceptance_record,
)
from shreks_brain.host_acceptance.compare import (
    HostContinuityVerdict,
    decode_host_continuity_assessment,
)
from shreks_brain.host_acceptance.runtime import (
    build_host_acceptance_parser,
    run_host_acceptance_cli,
)


_ZERO = "0" * 64
_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _unit(name: str) -> SystemdUnitObservation:
    return SystemdUnitObservation(
        unit_name=name,
        required=True,
        active_state="active",
        sub_state="waiting" if name.endswith(".timer") else "running",
        enabled_state="enabled",
        n_restarts=0,
        exec_main_status=0,
        active_enter_timestamp="Wed 2026-08-26 13:00:00 UTC",
        check_status=HostCheckStatus.PASS,
    )


def _record(stage: HostAcceptanceStage, *, boot_id: str, status: HostCheckStatus = HostCheckStatus.PASS) -> HostAcceptanceRecord:
    units = tuple(_unit(name) for name in PHASE_G_REQUIRED_UNITS)
    if status is not HostCheckStatus.PASS:
        units = (replace(units[0], check_status=status),) + units[1:]
    record = HostAcceptanceRecord(
        schema_version=HOST_ACCEPTANCE_SCHEMA_VERSION,
        stage=stage,
        captured_at_unix_ms=1_800_000_000_000,
        host_label_sha256=_SHA_A,
        release=ReleaseObservation(
            expected_source_sha="1" * 40,
            resolved_current_path="/opt/shreks/releases/" + "1" * 40,
            current_target_name="1" * 40,
            current_is_managed_symlink=True,
            release_manifest_sha256=_SHA_B,
            check_status=HostCheckStatus.PASS,
        ),
        units=units,
        paper=PaperRecoveryObservation(
            paper_run_id="paper-run-1",
            candidate_version="candidate-v1",
            campaign_manifest_fingerprint_sha256=_SHA_A,
            last_cycle_at_unix_ms=100,
            ledger_as_of_unix_ms=100,
            ledger_entry_count=2,
            processed_intent_keys=("intent-a", "intent-b"),
            managed_position_ids=("position-a",),
            preflight_status=HostCheckStatus.PASS,
        ),
        risk_control=RiskControlObservation(
            schema_version="g7-operator-risk-control-v1",
            revision=3,
            halt_new_entries=True,
            kill_switch_active=False,
            updated_at_unix_ms=90,
            last_command="HALT_NEW_ENTRIES",
            last_source="HOST_CLI",
            state_file_sha256=_SHA_B,
            check_status=HostCheckStatus.PASS,
        ),
        backup=BackupObservation(
            bundle_present=True,
            bundle_path="/var/lib/shreks/backups/bundle-a",
            created_at_unix_ms=90,
            paper_run_id="paper-run-1",
            campaign_manifest_fingerprint_sha256=_SHA_A,
            manifest_sha256=_SHA_B,
            check_status=HostCheckStatus.PASS,
        ),
        dashboard=DashboardExposureObservation(
            port=8787,
            listeners=("127.0.0.1:8787",),
            loopback_only=True,
            check_status=HostCheckStatus.PASS,
        ),
        protected_paths=(),
        resources=HostResourceObservation(
            boot_id=boot_id,
            uptime_seconds=100.0,
            load_average=(0.1, 0.2, 0.3),
            memory_total_bytes=8_000_000,
            memory_available_bytes=6_000_000,
            state_filesystem_total_bytes=100_000_000,
            state_filesystem_free_bytes=80_000_000,
        ),
        overall_status=status,
        evidence_fingerprint_sha256=_ZERO,
    )
    return replace(record, evidence_fingerprint_sha256=fingerprint_host_acceptance_record(record))


def _capture_args(tmp_path: Path, output: Path) -> list[str]:
    absolute = lambda name: str((tmp_path / name).resolve())
    return [
        "capture",
        "--stage", "BASELINE",
        "--host-label", "shreks-free-vps",
        "--expected-release-sha", "1" * 40,
        "--observer-database", absolute("shreks.db"),
        "--evidence", absolute("e11.json"),
        "--campaign-manifest", absolute("paper-campaign.json"),
        "--risk-control", absolute("operator-control.json"),
        "--backup-root", absolute("backups"),
        "--dashboard-port", "8787",
        "--paper-cycle-interval-seconds", "1",
        "--dashboard-password", absolute("dashboard-password"),
        "--telegram-token", absolute("telegram-bot-token"),
        "--output", str(output.resolve()),
    ]


def test_capture_writes_private_canonical_record_and_returns_zero(tmp_path: Path):
    output = tmp_path / "baseline.json"
    stdout = io.StringIO()
    stderr = io.StringIO()
    seen = []

    def collector(config):
        seen.append(config)
        return _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")

    code = run_host_acceptance_cli(
        _capture_args(tmp_path, output),
        collector=collector,
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 0
    assert stderr.getvalue() == ""
    decoded = decode_host_acceptance_record(output.read_text())
    assert decoded.overall_status is HostCheckStatus.PASS
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert seen[0].stage is HostAcceptanceStage.BASELINE
    assert tuple(item.role for item in seen[0].protected_paths) == (
        "dashboard_password",
        "telegram_bot_token",
    )


def test_capture_persists_failed_evidence_but_returns_nonzero(tmp_path: Path):
    output = tmp_path / "failed.json"
    code = run_host_acceptance_cli(
        _capture_args(tmp_path, output),
        collector=lambda _config: _record(
            HostAcceptanceStage.BASELINE,
            boot_id="boot-a",
            status=HostCheckStatus.FAIL,
        ),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert code == 1
    assert decode_host_acceptance_record(output.read_text()).overall_status is HostCheckStatus.FAIL


def test_compare_writes_private_assessment_and_returns_verdict(tmp_path: Path):
    from shreks_brain.host_acceptance import encode_host_acceptance_record

    before = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")
    after = _record(HostAcceptanceStage.AFTER_PROCESS_RESTART, boot_id="boot-a")
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    output = tmp_path / "comparison.json"
    before_path.write_text(encode_host_acceptance_record(before))
    after_path.write_text(encode_host_acceptance_record(after))

    code = run_host_acceptance_cli(
        ["compare", str(before_path.resolve()), str(after_path.resolve()), "--output", str(output.resolve())],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assessment = decode_host_continuity_assessment(output.read_text())
    assert code == 0
    assert assessment.verdict is HostContinuityVerdict.PASS
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_cli_never_echoes_secret_file_contents(tmp_path: Path):
    secret = "SUPER-SECRET-TELEGRAM-TOKEN"
    (tmp_path / "telegram-bot-token").write_text(secret)
    (tmp_path / "dashboard-password").write_text("SUPER-SECRET-DASHBOARD-PASSWORD")
    stdout = io.StringIO()
    stderr = io.StringIO()
    output = tmp_path / "baseline.json"

    run_host_acceptance_cli(
        _capture_args(tmp_path, output),
        collector=lambda _config: _record(HostAcceptanceStage.BASELINE, boot_id="boot-a"),
        stdout=stdout,
        stderr=stderr,
    )
    combined = stdout.getvalue() + stderr.getvalue() + output.read_text()
    assert secret not in combined
    assert "SUPER-SECRET-DASHBOARD-PASSWORD" not in combined


def test_parser_has_no_lifecycle_or_live_subcommands():
    parser = build_host_acceptance_parser()
    for forbidden in ("restart", "reboot", "stop", "start", "enable", "disable", "live", "kill"):
        with pytest.raises(SystemExit):
            parser.parse_args([forbidden])
