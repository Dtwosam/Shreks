from __future__ import annotations

from dataclasses import asdict, fields
import hashlib
import json
from typing import Any

from .models import (
    BackupObservation,
    DashboardExposureObservation,
    HOST_ACCEPTANCE_SCHEMA_VERSION,
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


_ZERO_SHA256 = "0" * 64


def fingerprint_host_acceptance_record(record: HostAcceptanceRecord) -> str:
    if type(record) is not HostAcceptanceRecord:
        raise ValueError("record must be an exact HostAcceptanceRecord")
    document = asdict(record)
    document["evidence_fingerprint_sha256"] = _ZERO_SHA256
    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def encode_host_acceptance_record(record: HostAcceptanceRecord) -> str:
    if type(record) is not HostAcceptanceRecord:
        raise ValueError("record must be an exact HostAcceptanceRecord")
    expected = fingerprint_host_acceptance_record(record)
    if record.evidence_fingerprint_sha256 != expected:
        raise ValueError("host acceptance evidence fingerprint does not match record")
    return json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def decode_host_acceptance_record(payload: str | bytes) -> HostAcceptanceRecord:
    if type(payload) is bytes:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("host acceptance payload must be UTF-8") from error
    elif type(payload) is str:
        text = payload
    else:
        raise ValueError("host acceptance payload must be exact str or bytes")

    try:
        raw = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("host acceptance payload must be valid finite JSON") from error

    obj = _exact_object(raw, HostAcceptanceRecord)
    record = HostAcceptanceRecord(
        schema_version=obj["schema_version"],
        stage=_enum_value("stage", obj["stage"], HostAcceptanceStage),
        captured_at_unix_ms=obj["captured_at_unix_ms"],
        host_label_sha256=obj["host_label_sha256"],
        release=_decode_release(obj["release"]),
        units=_decode_units(obj["units"]),
        paper=_decode_paper(obj["paper"]),
        risk_control=_decode_risk(obj["risk_control"]),
        backup=_decode_backup(obj["backup"]),
        dashboard=_decode_dashboard(obj["dashboard"]),
        protected_paths=_decode_protected_paths(obj["protected_paths"]),
        resources=_decode_resources(obj["resources"]),
        overall_status=_enum_value(
            "overall_status", obj["overall_status"], HostCheckStatus
        ),
        evidence_fingerprint_sha256=obj["evidence_fingerprint_sha256"],
    )
    if record.schema_version != HOST_ACCEPTANCE_SCHEMA_VERSION:
        raise ValueError("unsupported host acceptance schema version")
    if record.evidence_fingerprint_sha256 != fingerprint_host_acceptance_record(record):
        raise ValueError("host acceptance evidence fingerprint does not match record")
    if encode_host_acceptance_record(record) != text:
        raise ValueError("host acceptance payload must use canonical encoding")
    return record


def _decode_release(value: object) -> ReleaseObservation:
    obj = _exact_object(value, ReleaseObservation)
    return ReleaseObservation(
        expected_source_sha=obj["expected_source_sha"],
        resolved_current_path=obj["resolved_current_path"],
        current_target_name=obj["current_target_name"],
        current_is_managed_symlink=obj["current_is_managed_symlink"],
        release_manifest_sha256=obj["release_manifest_sha256"],
        check_status=_enum_value(
            "release.check_status", obj["check_status"], HostCheckStatus
        ),
    )


def _decode_units(value: object) -> tuple[SystemdUnitObservation, ...]:
    if type(value) is not list:
        raise ValueError("units must be an exact JSON array")
    result = []
    for item in value:
        obj = _exact_object(item, SystemdUnitObservation)
        result.append(
            SystemdUnitObservation(
                unit_name=obj["unit_name"],
                required=obj["required"],
                active_state=obj["active_state"],
                sub_state=obj["sub_state"],
                enabled_state=obj["enabled_state"],
                n_restarts=obj["n_restarts"],
                exec_main_status=obj["exec_main_status"],
                active_enter_timestamp=obj["active_enter_timestamp"],
                check_status=_enum_value(
                    "unit.check_status", obj["check_status"], HostCheckStatus
                ),
            )
        )
    return tuple(result)


def _decode_paper(value: object) -> PaperRecoveryObservation:
    obj = _exact_object(value, PaperRecoveryObservation)
    return PaperRecoveryObservation(
        paper_run_id=obj["paper_run_id"],
        candidate_version=obj["candidate_version"],
        campaign_manifest_fingerprint_sha256=obj[
            "campaign_manifest_fingerprint_sha256"
        ],
        last_cycle_at_unix_ms=obj["last_cycle_at_unix_ms"],
        ledger_as_of_unix_ms=obj["ledger_as_of_unix_ms"],
        ledger_entry_count=obj["ledger_entry_count"],
        processed_intent_keys=_string_tuple(
            "paper.processed_intent_keys", obj["processed_intent_keys"]
        ),
        managed_position_ids=_string_tuple(
            "paper.managed_position_ids", obj["managed_position_ids"]
        ),
        preflight_status=_enum_value(
            "paper.preflight_status", obj["preflight_status"], HostCheckStatus
        ),
    )


def _decode_risk(value: object) -> RiskControlObservation:
    obj = _exact_object(value, RiskControlObservation)
    return RiskControlObservation(
        schema_version=obj["schema_version"],
        revision=obj["revision"],
        halt_new_entries=obj["halt_new_entries"],
        kill_switch_active=obj["kill_switch_active"],
        updated_at_unix_ms=obj["updated_at_unix_ms"],
        last_command=obj["last_command"],
        last_source=obj["last_source"],
        state_file_sha256=obj["state_file_sha256"],
        check_status=_enum_value(
            "risk_control.check_status", obj["check_status"], HostCheckStatus
        ),
    )


def _decode_backup(value: object) -> BackupObservation:
    obj = _exact_object(value, BackupObservation)
    return BackupObservation(
        bundle_present=obj["bundle_present"],
        bundle_path=obj["bundle_path"],
        created_at_unix_ms=obj["created_at_unix_ms"],
        paper_run_id=obj["paper_run_id"],
        campaign_manifest_fingerprint_sha256=obj[
            "campaign_manifest_fingerprint_sha256"
        ],
        manifest_sha256=obj["manifest_sha256"],
        check_status=_enum_value(
            "backup.check_status", obj["check_status"], HostCheckStatus
        ),
    )


def _decode_dashboard(value: object) -> DashboardExposureObservation:
    obj = _exact_object(value, DashboardExposureObservation)
    return DashboardExposureObservation(
        port=obj["port"],
        listeners=_string_tuple("dashboard.listeners", obj["listeners"]),
        loopback_only=obj["loopback_only"],
        check_status=_enum_value(
            "dashboard.check_status", obj["check_status"], HostCheckStatus
        ),
    )


def _decode_protected_paths(value: object) -> tuple[ProtectedPathObservation, ...]:
    if type(value) is not list:
        raise ValueError("protected_paths must be an exact JSON array")
    result = []
    for item in value:
        obj = _exact_object(item, ProtectedPathObservation)
        result.append(
            ProtectedPathObservation(
                role=obj["role"],
                path=obj["path"],
                kind=_enum_value("protected_path.kind", obj["kind"], ProtectedPathKind),
                exists=obj["exists"],
                symlink=obj["symlink"],
                mode=obj["mode"],
                owner_uid=obj["owner_uid"],
                group_gid=obj["group_gid"],
                byte_size=obj["byte_size"],
                check_status=_enum_value(
                    "protected_path.check_status",
                    obj["check_status"],
                    HostCheckStatus,
                ),
            )
        )
    return tuple(result)


def _decode_resources(value: object) -> HostResourceObservation:
    obj = _exact_object(value, HostResourceObservation)
    load = obj["load_average"]
    if load is not None:
        if type(load) is not list or len(load) != 3:
            raise ValueError("resources.load_average must be a three-value JSON array or null")
        load_value = tuple(load)
    else:
        load_value = None
    return HostResourceObservation(
        boot_id=obj["boot_id"],
        uptime_seconds=obj["uptime_seconds"],
        load_average=load_value,
        memory_total_bytes=obj["memory_total_bytes"],
        memory_available_bytes=obj["memory_available_bytes"],
        state_filesystem_total_bytes=obj["state_filesystem_total_bytes"],
        state_filesystem_free_bytes=obj["state_filesystem_free_bytes"],
    )


def _exact_object(value: object, expected_type: type) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{expected_type.__name__} JSON value must be an exact object")
    expected = {item.name for item in fields(expected_type)}
    if set(value) != expected:
        raise ValueError(f"{expected_type.__name__} JSON keys must be exact")
    return value


def _enum_value(name: str, value: object, enum_type: type):
    if type(value) is not str:
        raise ValueError(f"{name} must be an exact string")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError(f"unsupported {name}") from error


def _string_tuple(name: str, value: object) -> tuple[str, ...]:
    if type(value) is not list or not all(type(item) is str for item in value):
        raise ValueError(f"{name} must be an exact JSON string array")
    return tuple(value)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
