from __future__ import annotations

from dataclasses import replace

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
    ProtectedPathKind,
    ProtectedPathObservation,
    ReleaseObservation,
    RiskControlObservation,
    SystemdUnitObservation,
)
from shreks_brain.host_acceptance.compare import (
    HostContinuityVerdict,
    compare_host_acceptance_records,
    decode_host_continuity_assessment,
    encode_host_continuity_assessment,
)
from shreks_brain.host_acceptance.codec import fingerprint_host_acceptance_record


_SHA_A = "a" * 64
_SHA_B = "b" * 64
_ZERO = "0" * 64


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


def _record(
    stage: HostAcceptanceStage,
    *,
    boot_id: str,
    cycle: int = 100,
    ledger_time: int = 100,
    ledger_count: int = 2,
    intents: tuple[str, ...] = ("intent-a", "intent-b"),
) -> HostAcceptanceRecord:
    record = HostAcceptanceRecord(
        schema_version=HOST_ACCEPTANCE_SCHEMA_VERSION,
        stage=stage,
        captured_at_unix_ms=1_800_000_000_000 + cycle,
        host_label_sha256=_SHA_A,
        release=ReleaseObservation(
            expected_source_sha="1" * 40,
            resolved_current_path="/opt/shreks/releases/" + "1" * 40,
            current_target_name="1" * 40,
            current_is_managed_symlink=True,
            release_manifest_sha256=_SHA_B,
            check_status=HostCheckStatus.PASS,
        ),
        units=tuple(_unit(name) for name in PHASE_G_REQUIRED_UNITS),
        paper=PaperRecoveryObservation(
            paper_run_id="paper-run-1",
            candidate_version="candidate-v1",
            campaign_manifest_fingerprint_sha256=_SHA_A,
            last_cycle_at_unix_ms=cycle,
            ledger_as_of_unix_ms=ledger_time,
            ledger_entry_count=ledger_count,
            processed_intent_keys=intents,
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
        protected_paths=(
            ProtectedPathObservation(
                role="dashboard_password",
                path="/etc/shreks/dashboard-password",
                kind=ProtectedPathKind.FILE,
                exists=True,
                symlink=False,
                mode=0o640,
                owner_uid=0,
                group_gid=1001,
                byte_size=32,
                check_status=HostCheckStatus.PASS,
            ),
        ),
        resources=HostResourceObservation(
            boot_id=boot_id,
            uptime_seconds=100.0,
            load_average=(0.1, 0.2, 0.3),
            memory_total_bytes=8_000_000,
            memory_available_bytes=6_000_000,
            state_filesystem_total_bytes=100_000_000,
            state_filesystem_free_bytes=80_000_000,
        ),
        overall_status=HostCheckStatus.PASS,
        evidence_fingerprint_sha256=_ZERO,
    )
    return replace(record, evidence_fingerprint_sha256=fingerprint_host_acceptance_record(record))


def test_process_restart_requires_same_boot_and_preserves_monotonic_paper_state():
    before = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")
    after = _record(
        HostAcceptanceStage.AFTER_PROCESS_RESTART,
        boot_id="boot-a",
        cycle=110,
        ledger_time=110,
        ledger_count=3,
        intents=("intent-a", "intent-b", "intent-c"),
    )
    assessment = compare_host_acceptance_records(before, after)
    assert assessment.verdict is HostContinuityVerdict.PASS
    assert assessment.findings == ()


def test_reboot_requires_different_boot_id():
    before = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")
    same_boot = _record(HostAcceptanceStage.AFTER_REBOOT, boot_id="boot-a", cycle=101, ledger_time=101)
    assessment = compare_host_acceptance_records(before, same_boot)
    assert assessment.verdict is HostContinuityVerdict.FAIL
    assert any(item.code == "REBOOT_BOOT_ID_UNCHANGED" for item in assessment.findings)


def test_process_restart_rejects_changed_boot_id():
    before = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")
    after = _record(HostAcceptanceStage.AFTER_PROCESS_RESTART, boot_id="boot-b", cycle=101, ledger_time=101)
    assessment = compare_host_acceptance_records(before, after)
    assert assessment.verdict is HostContinuityVerdict.FAIL
    assert any(item.code == "PROCESS_RESTART_BOOT_ID_CHANGED" for item in assessment.findings)


def test_restore_drill_does_not_require_boot_relation_but_preserves_truth():
    before = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")
    after = _record(HostAcceptanceStage.AFTER_RESTORE_DRILL, boot_id="boot-z", cycle=101, ledger_time=101)
    assert compare_host_acceptance_records(before, after).verdict is HostContinuityVerdict.PASS


def test_comparator_catches_lost_ledger_progress_and_processed_intents():
    before = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a", cycle=100, ledger_time=100, ledger_count=3, intents=("a", "b", "c"))
    after = _record(HostAcceptanceStage.AFTER_PROCESS_RESTART, boot_id="boot-a", cycle=99, ledger_time=99, ledger_count=2, intents=("a", "b"))
    assessment = compare_host_acceptance_records(before, after)
    codes = {item.code for item in assessment.findings}
    assert assessment.verdict is HostContinuityVerdict.FAIL
    assert {"PAPER_CYCLE_TIME_REGRESSED", "LEDGER_TIME_REGRESSED", "LEDGER_ENTRY_COUNT_REGRESSED", "PROCESSED_INTENT_LOST"} <= codes


def test_comparator_requires_release_campaign_candidate_and_g7_state_continuity():
    before = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")
    after = _record(HostAcceptanceStage.AFTER_PROCESS_RESTART, boot_id="boot-a", cycle=101, ledger_time=101)
    after = replace(
        after,
        release=replace(after.release, expected_source_sha="2" * 40, current_target_name="2" * 40),
        paper=replace(after.paper, candidate_version="candidate-v2"),
        risk_control=replace(after.risk_control, revision=4, state_file_sha256="c" * 64),
    )
    after = replace(after, evidence_fingerprint_sha256=fingerprint_host_acceptance_record(replace(after, evidence_fingerprint_sha256=_ZERO)))
    assessment = compare_host_acceptance_records(before, after)
    codes = {item.code for item in assessment.findings}
    assert assessment.verdict is HostContinuityVerdict.FAIL
    assert "RELEASE_CHANGED" in codes
    assert "CANDIDATE_VERSION_CHANGED" in codes
    assert "RISK_CONTROL_CHANGED" in codes


def test_both_records_must_pass_and_transition_must_start_at_baseline():
    before = _record(HostAcceptanceStage.AFTER_PROCESS_RESTART, boot_id="boot-a")
    after = _record(HostAcceptanceStage.AFTER_REBOOT, boot_id="boot-b", cycle=101, ledger_time=101)
    assessment = compare_host_acceptance_records(before, after)
    assert assessment.verdict is HostContinuityVerdict.FAIL
    assert any(item.code == "UNEXPECTED_STAGE_TRANSITION" for item in assessment.findings)

    baseline = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")
    failed_unit = replace(baseline.units[0], check_status=HostCheckStatus.FAIL)
    failed_before = replace(baseline, units=(failed_unit,) + baseline.units[1:], overall_status=HostCheckStatus.FAIL)
    failed_before = replace(failed_before, evidence_fingerprint_sha256=fingerprint_host_acceptance_record(replace(failed_before, evidence_fingerprint_sha256=_ZERO)))
    assessment = compare_host_acceptance_records(failed_before, after)
    assert any(item.code == "BEFORE_NOT_PASS" for item in assessment.findings)


def test_assessment_round_trips_canonically_and_has_no_profit_or_live_decision_fields():
    before = _record(HostAcceptanceStage.BASELINE, boot_id="boot-a")
    after = _record(HostAcceptanceStage.AFTER_PROCESS_RESTART, boot_id="boot-a", cycle=101, ledger_time=101)
    assessment = compare_host_acceptance_records(before, after)
    payload = encode_host_continuity_assessment(assessment)
    assert payload.endswith("\n")
    assert decode_host_continuity_assessment(payload) == assessment
    assert encode_host_continuity_assessment(decode_host_continuity_assessment(payload)) == payload
    assert "profit" not in payload.lower()
    assert "live_trading" not in payload.lower()
