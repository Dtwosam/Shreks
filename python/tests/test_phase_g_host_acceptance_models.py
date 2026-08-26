from __future__ import annotations

from dataclasses import replace
import json

import pytest

from shreks_brain.host_acceptance import (
    HOST_ACCEPTANCE_SCHEMA_VERSION,
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
    decode_host_acceptance_record,
    encode_host_acceptance_record,
    fingerprint_host_acceptance_record,
)


_SHA_A = "a" * 64
_SHA_B = "b" * 64
_ZERO_SHA = "0" * 64


def _unit(name: str, *, required: bool = True, status: HostCheckStatus = HostCheckStatus.PASS):
    return SystemdUnitObservation(
        unit_name=name,
        required=required,
        active_state="active",
        sub_state="running" if name.endswith(".service") else "active",
        enabled_state="enabled",
        n_restarts=1,
        exec_main_status=0,
        active_enter_timestamp="Wed 2026-08-26 13:00:00 UTC",
        check_status=status,
    )


def _record(*, unit_status: HostCheckStatus = HostCheckStatus.PASS) -> HostAcceptanceRecord:
    record = HostAcceptanceRecord(
        schema_version=HOST_ACCEPTANCE_SCHEMA_VERSION,
        stage=HostAcceptanceStage.BASELINE,
        captured_at_unix_ms=1_777_000_000_000,
        host_label_sha256=_SHA_A,
        release=ReleaseObservation(
            expected_source_sha="1" * 40,
            resolved_current_path="/opt/shreks/releases/" + "1" * 40,
            current_target_name="1" * 40,
            current_is_managed_symlink=True,
            release_manifest_sha256=_SHA_B,
            check_status=HostCheckStatus.PASS,
        ),
        units=(
            _unit("shreks-observe.service", status=unit_status),
            _unit("shreks-paper-evidence.service"),
            _unit("shreks-paper-campaign.service"),
            _unit("shreks.target"),
            _unit("shreks-telemetry.timer"),
            _unit("shreks-dashboard.service"),
            _unit("shreks-alerts.timer"),
            _unit("shreks-backup.timer"),
        ),
        paper=PaperRecoveryObservation(
            paper_run_id="paper-run-1",
            candidate_version="candidate-v1",
            campaign_manifest_fingerprint_sha256=_SHA_A,
            last_cycle_at_unix_ms=1234,
            ledger_as_of_unix_ms=1234,
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
            updated_at_unix_ms=1200,
            last_command="HALT_NEW_ENTRIES",
            last_source="HOST_CLI",
            state_file_sha256=_SHA_B,
            check_status=HostCheckStatus.PASS,
        ),
        backup=BackupObservation(
            bundle_present=True,
            bundle_path="/var/lib/shreks/backups/bundle-a",
            created_at_unix_ms=1200,
            paper_run_id="paper-run-1",
            campaign_manifest_fingerprint_sha256=_SHA_A,
            manifest_sha256=_SHA_B,
            check_status=HostCheckStatus.PASS,
        ),
        dashboard=DashboardExposureObservation(
            port=8787,
            listeners=("127.0.0.1:8787", "[::1]:8787"),
            loopback_only=True,
            check_status=HostCheckStatus.PASS,
        ),
        protected_paths=(
            ProtectedPathObservation(
                role="paper_campaign_manifest",
                path="/etc/shreks/paper-campaign.json",
                kind=ProtectedPathKind.FILE,
                exists=True,
                symlink=False,
                mode=0o640,
                owner_uid=0,
                group_gid=1001,
                byte_size=111,
                check_status=HostCheckStatus.PASS,
            ),
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
            boot_id="d4a7b1ab-1c84-4a88-a038-f8816cd6f607",
            uptime_seconds=3600.5,
            load_average=(0.1, 0.2, 0.3),
            memory_total_bytes=8_000_000_000,
            memory_available_bytes=6_000_000_000,
            state_filesystem_total_bytes=100_000_000_000,
            state_filesystem_free_bytes=80_000_000_000,
        ),
        overall_status=HostCheckStatus.PASS if unit_status is HostCheckStatus.PASS else unit_status,
        evidence_fingerprint_sha256=_ZERO_SHA,
    )
    return replace(
        record,
        evidence_fingerprint_sha256=fingerprint_host_acceptance_record(record),
    )


def test_host_acceptance_contract_uses_exact_stable_vocabulary():
    assert HOST_ACCEPTANCE_SCHEMA_VERSION == "phase-g-host-acceptance-v1"
    assert tuple(stage.value for stage in HostAcceptanceStage) == (
        "BASELINE",
        "AFTER_PROCESS_RESTART",
        "AFTER_REBOOT",
        "AFTER_RESTORE_DRILL",
    )
    assert tuple(status.value for status in HostCheckStatus) == (
        "PASS",
        "FAIL",
        "UNAVAILABLE",
    )
    assert tuple(kind.value for kind in ProtectedPathKind) == (
        "FILE",
        "DIRECTORY",
        "MISSING",
        "OTHER",
    )


def test_host_acceptance_record_round_trips_canonically_with_verified_fingerprint():
    record = _record()
    payload = encode_host_acceptance_record(record)

    assert payload.endswith("\n")
    assert decode_host_acceptance_record(payload) == record
    assert encode_host_acceptance_record(decode_host_acceptance_record(payload)) == payload
    assert record.evidence_fingerprint_sha256 == fingerprint_host_acceptance_record(record)


def test_record_requires_overall_status_to_match_required_observations():
    with pytest.raises(ValueError, match="overall_status"):
        replace(
            _record(unit_status=HostCheckStatus.FAIL),
            overall_status=HostCheckStatus.PASS,
        )


def test_unavailable_required_observation_keeps_record_unavailable():
    record = _record(unit_status=HostCheckStatus.UNAVAILABLE)
    assert record.overall_status is HostCheckStatus.UNAVAILABLE


def test_duplicate_unit_names_and_protected_roles_are_rejected():
    record = _record()
    with pytest.raises(ValueError, match="unit_name"):
        replace(record, units=record.units + (record.units[0],))
    with pytest.raises(ValueError, match="protected path roles"):
        replace(
            record,
            protected_paths=record.protected_paths + (record.protected_paths[0],),
        )


def test_decoder_rejects_unknown_keys_noncanonical_json_and_bad_fingerprint():
    payload = encode_host_acceptance_record(_record())
    document = json.loads(payload)

    unknown = dict(document)
    unknown["unexpected"] = True
    with pytest.raises(ValueError, match="keys must be exact"):
        decode_host_acceptance_record(json.dumps(unknown, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(ValueError, match="canonical"):
        decode_host_acceptance_record(json.dumps(document, indent=2))

    document["evidence_fingerprint_sha256"] = "f" * 64
    tampered = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    with pytest.raises(ValueError, match="fingerprint"):
        decode_host_acceptance_record(tampered)


def test_models_reject_nonfinite_values_and_malformed_hashes():
    record = _record()
    with pytest.raises(ValueError, match="uptime_seconds"):
        replace(record.resources, uptime_seconds=float("nan"))
    with pytest.raises(ValueError, match="SHA-256"):
        replace(record.release, release_manifest_sha256="ABC")
