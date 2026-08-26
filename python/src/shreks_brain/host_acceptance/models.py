from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


HOST_ACCEPTANCE_SCHEMA_VERSION = "phase-g-host-acceptance-v1"

PHASE_G_REQUIRED_UNITS = (
    "shreks-observe.service",
    "shreks-paper-evidence.service",
    "shreks-paper-campaign.service",
    "shreks.target",
    "shreks-telemetry.timer",
    "shreks-dashboard.service",
    "shreks-alerts.timer",
    "shreks-backup.timer",
)


class HostAcceptanceStage(StrEnum):
    BASELINE = "BASELINE"
    AFTER_PROCESS_RESTART = "AFTER_PROCESS_RESTART"
    AFTER_REBOOT = "AFTER_REBOOT"
    AFTER_RESTORE_DRILL = "AFTER_RESTORE_DRILL"


class HostCheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class ProtectedPathKind(StrEnum):
    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    MISSING = "MISSING"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class SystemdUnitObservation:
    unit_name: str
    required: bool
    active_state: str
    sub_state: str
    enabled_state: str
    n_restarts: int
    exec_main_status: int
    active_enter_timestamp: str
    check_status: HostCheckStatus

    def __post_init__(self) -> None:
        _require_text("unit_name", self.unit_name)
        _require_bool("required", self.required)
        _require_text("active_state", self.active_state)
        _require_text("sub_state", self.sub_state)
        _require_text("enabled_state", self.enabled_state)
        _require_non_negative_int("n_restarts", self.n_restarts)
        _require_non_negative_int("exec_main_status", self.exec_main_status)
        _require_text("active_enter_timestamp", self.active_enter_timestamp)
        _require_status("check_status", self.check_status)


@dataclass(frozen=True, slots=True)
class PaperRecoveryObservation:
    paper_run_id: str
    candidate_version: str
    campaign_manifest_fingerprint_sha256: str
    last_cycle_at_unix_ms: int
    ledger_as_of_unix_ms: int
    ledger_entry_count: int
    processed_intent_keys: tuple[str, ...]
    managed_position_ids: tuple[str, ...]
    preflight_status: HostCheckStatus

    def __post_init__(self) -> None:
        _require_text("paper_run_id", self.paper_run_id)
        _require_text("candidate_version", self.candidate_version)
        _require_sha256(
            "campaign_manifest_fingerprint_sha256",
            self.campaign_manifest_fingerprint_sha256,
        )
        _require_non_negative_int("last_cycle_at_unix_ms", self.last_cycle_at_unix_ms)
        _require_non_negative_int("ledger_as_of_unix_ms", self.ledger_as_of_unix_ms)
        _require_non_negative_int("ledger_entry_count", self.ledger_entry_count)
        _require_sorted_unique_text_tuple("processed_intent_keys", self.processed_intent_keys)
        _require_sorted_unique_text_tuple("managed_position_ids", self.managed_position_ids)
        _require_status("preflight_status", self.preflight_status)


@dataclass(frozen=True, slots=True)
class RiskControlObservation:
    schema_version: str
    revision: int
    halt_new_entries: bool
    kill_switch_active: bool
    updated_at_unix_ms: int
    last_command: str
    last_source: str
    state_file_sha256: str
    check_status: HostCheckStatus

    def __post_init__(self) -> None:
        _require_text("schema_version", self.schema_version)
        _require_non_negative_int("revision", self.revision)
        _require_bool("halt_new_entries", self.halt_new_entries)
        _require_bool("kill_switch_active", self.kill_switch_active)
        if self.kill_switch_active and not self.halt_new_entries:
            raise ValueError("kill_switch_active requires halt_new_entries")
        _require_non_negative_int("updated_at_unix_ms", self.updated_at_unix_ms)
        _require_text("last_command", self.last_command)
        _require_text("last_source", self.last_source)
        _require_sha256("state_file_sha256", self.state_file_sha256)
        _require_status("check_status", self.check_status)


@dataclass(frozen=True, slots=True)
class ReleaseObservation:
    expected_source_sha: str
    resolved_current_path: str
    current_target_name: str
    current_is_managed_symlink: bool
    release_manifest_sha256: str | None
    check_status: HostCheckStatus

    def __post_init__(self) -> None:
        _require_source_sha("expected_source_sha", self.expected_source_sha)
        _require_text("resolved_current_path", self.resolved_current_path)
        _require_text("current_target_name", self.current_target_name)
        _require_bool("current_is_managed_symlink", self.current_is_managed_symlink)
        if self.release_manifest_sha256 is not None:
            _require_sha256("release_manifest_sha256", self.release_manifest_sha256)
        _require_status("check_status", self.check_status)


@dataclass(frozen=True, slots=True)
class ProtectedPathObservation:
    role: str
    path: str
    kind: ProtectedPathKind
    exists: bool
    symlink: bool
    mode: int | None
    owner_uid: int | None
    group_gid: int | None
    byte_size: int | None
    check_status: HostCheckStatus

    def __post_init__(self) -> None:
        _require_text("role", self.role)
        _require_text("path", self.path)
        if type(self.kind) is not ProtectedPathKind:
            raise ValueError("kind must be an exact ProtectedPathKind")
        _require_bool("exists", self.exists)
        _require_bool("symlink", self.symlink)
        _require_optional_non_negative_int("mode", self.mode)
        if self.mode is not None and self.mode > 0o7777:
            raise ValueError("mode must be a valid numeric permission mode")
        _require_optional_non_negative_int("owner_uid", self.owner_uid)
        _require_optional_non_negative_int("group_gid", self.group_gid)
        _require_optional_non_negative_int("byte_size", self.byte_size)
        _require_status("check_status", self.check_status)

        if self.kind is ProtectedPathKind.MISSING:
            if self.exists:
                raise ValueError("MISSING protected path cannot exist")
            if any(
                value is not None
                for value in (self.mode, self.owner_uid, self.group_gid, self.byte_size)
            ):
                raise ValueError("MISSING protected path cannot carry stat metadata")
        elif not self.exists:
            raise ValueError("non-MISSING protected path must exist")

        if self.kind is ProtectedPathKind.DIRECTORY and self.byte_size is not None:
            raise ValueError("DIRECTORY protected path cannot carry file byte_size")


@dataclass(frozen=True, slots=True)
class DashboardExposureObservation:
    port: int
    listeners: tuple[str, ...]
    loopback_only: bool
    check_status: HostCheckStatus

    def __post_init__(self) -> None:
        if isinstance(self.port, bool) or type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("port must be an integer from 1 through 65535")
        _require_sorted_unique_text_tuple("listeners", self.listeners)
        _require_bool("loopback_only", self.loopback_only)
        _require_status("check_status", self.check_status)
        if self.check_status is HostCheckStatus.PASS and (
            not self.listeners or not self.loopback_only
        ):
            raise ValueError("PASS dashboard exposure requires loopback-only listeners")


@dataclass(frozen=True, slots=True)
class BackupObservation:
    bundle_present: bool
    bundle_path: str | None
    created_at_unix_ms: int | None
    paper_run_id: str | None
    campaign_manifest_fingerprint_sha256: str | None
    manifest_sha256: str | None
    check_status: HostCheckStatus

    def __post_init__(self) -> None:
        _require_bool("bundle_present", self.bundle_present)
        _require_optional_non_negative_int("created_at_unix_ms", self.created_at_unix_ms)
        if self.bundle_path is not None:
            _require_text("bundle_path", self.bundle_path)
        if self.paper_run_id is not None:
            _require_text("paper_run_id", self.paper_run_id)
        if self.campaign_manifest_fingerprint_sha256 is not None:
            _require_sha256(
                "campaign_manifest_fingerprint_sha256",
                self.campaign_manifest_fingerprint_sha256,
            )
        if self.manifest_sha256 is not None:
            _require_sha256("manifest_sha256", self.manifest_sha256)
        _require_status("check_status", self.check_status)

        details = (
            self.bundle_path,
            self.created_at_unix_ms,
            self.paper_run_id,
            self.campaign_manifest_fingerprint_sha256,
            self.manifest_sha256,
        )
        if self.bundle_present and any(value is None for value in details):
            raise ValueError("present backup bundle requires complete verified metadata")
        if not self.bundle_present and any(value is not None for value in details):
            raise ValueError("absent backup bundle cannot carry bundle metadata")
        if self.check_status is HostCheckStatus.PASS and not self.bundle_present:
            raise ValueError("PASS backup observation requires a verified bundle")


@dataclass(frozen=True, slots=True)
class HostResourceObservation:
    boot_id: str
    uptime_seconds: float | None
    load_average: tuple[float, float, float] | None
    memory_total_bytes: int | None
    memory_available_bytes: int | None
    state_filesystem_total_bytes: int | None
    state_filesystem_free_bytes: int | None

    def __post_init__(self) -> None:
        _require_text("boot_id", self.boot_id)
        _require_optional_non_negative_finite("uptime_seconds", self.uptime_seconds)
        if self.load_average is not None:
            if type(self.load_average) is not tuple or len(self.load_average) != 3:
                raise ValueError("load_average must be a three-value tuple or None")
            for value in self.load_average:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise ValueError("load_average values must be non-negative finite numbers")
        for name in (
            "memory_total_bytes",
            "memory_available_bytes",
            "state_filesystem_total_bytes",
            "state_filesystem_free_bytes",
        ):
            _require_optional_non_negative_int(name, getattr(self, name))
        if (
            self.memory_total_bytes is not None
            and self.memory_available_bytes is not None
            and self.memory_available_bytes > self.memory_total_bytes
        ):
            raise ValueError("memory_available_bytes cannot exceed memory_total_bytes")
        if (
            self.state_filesystem_total_bytes is not None
            and self.state_filesystem_free_bytes is not None
            and self.state_filesystem_free_bytes > self.state_filesystem_total_bytes
        ):
            raise ValueError(
                "state_filesystem_free_bytes cannot exceed state_filesystem_total_bytes"
            )


@dataclass(frozen=True, slots=True)
class HostAcceptanceRecord:
    schema_version: str
    stage: HostAcceptanceStage
    captured_at_unix_ms: int
    host_label_sha256: str
    release: ReleaseObservation
    units: tuple[SystemdUnitObservation, ...]
    paper: PaperRecoveryObservation
    risk_control: RiskControlObservation
    backup: BackupObservation
    dashboard: DashboardExposureObservation
    protected_paths: tuple[ProtectedPathObservation, ...]
    resources: HostResourceObservation
    overall_status: HostCheckStatus
    evidence_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != HOST_ACCEPTANCE_SCHEMA_VERSION:
            raise ValueError("unsupported host acceptance schema version")
        if type(self.stage) is not HostAcceptanceStage:
            raise ValueError("stage must be an exact HostAcceptanceStage")
        _require_non_negative_int("captured_at_unix_ms", self.captured_at_unix_ms)
        _require_sha256("host_label_sha256", self.host_label_sha256)
        if type(self.release) is not ReleaseObservation:
            raise ValueError("release must be an exact ReleaseObservation")
        if type(self.units) is not tuple or any(
            type(item) is not SystemdUnitObservation for item in self.units
        ):
            raise ValueError("units must be a tuple of exact SystemdUnitObservation values")
        unit_names = tuple(item.unit_name for item in self.units)
        if len(unit_names) != len(set(unit_names)):
            raise ValueError("unit_name values must be unique")
        if unit_names != PHASE_G_REQUIRED_UNITS:
            raise ValueError("units must use exact Phase G required unit ordering")
        if any(item.required is not True for item in self.units):
            raise ValueError("every Phase G host acceptance unit must be required")
        if type(self.paper) is not PaperRecoveryObservation:
            raise ValueError("paper must be an exact PaperRecoveryObservation")
        if type(self.risk_control) is not RiskControlObservation:
            raise ValueError("risk_control must be an exact RiskControlObservation")
        if type(self.backup) is not BackupObservation:
            raise ValueError("backup must be an exact BackupObservation")
        if type(self.dashboard) is not DashboardExposureObservation:
            raise ValueError("dashboard must be an exact DashboardExposureObservation")
        if type(self.protected_paths) is not tuple or any(
            type(item) is not ProtectedPathObservation for item in self.protected_paths
        ):
            raise ValueError(
                "protected_paths must be a tuple of exact ProtectedPathObservation values"
            )
        roles = tuple(item.role for item in self.protected_paths)
        if len(roles) != len(set(roles)):
            raise ValueError("protected path roles must be unique")
        if type(self.resources) is not HostResourceObservation:
            raise ValueError("resources must be an exact HostResourceObservation")
        _require_status("overall_status", self.overall_status)
        _require_sha256("evidence_fingerprint_sha256", self.evidence_fingerprint_sha256)

        expected = _overall_status(self)
        if self.overall_status is not expected:
            raise ValueError(
                f"overall_status must match required observations: expected {expected.value}"
            )


def _overall_status(record: HostAcceptanceRecord) -> HostCheckStatus:
    statuses = [record.release.check_status]
    statuses.extend(item.check_status for item in record.units if item.required)
    statuses.extend(
        (
            record.paper.preflight_status,
            record.risk_control.check_status,
            record.backup.check_status,
            record.dashboard.check_status,
        )
    )
    statuses.extend(item.check_status for item in record.protected_paths)
    if any(status is HostCheckStatus.FAIL for status in statuses):
        return HostCheckStatus.FAIL
    if any(status is HostCheckStatus.UNAVAILABLE for status in statuses):
        return HostCheckStatus.UNAVAILABLE
    return HostCheckStatus.PASS


def _require_text(name: str, value: object) -> None:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{name} must be non-empty trimmed text")


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be an exact bool")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_non_negative_int(name: str, value: object) -> None:
    if value is not None:
        _require_non_negative_int(name, value)


def _require_optional_non_negative_finite(name: str, value: object) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be a non-negative finite number or None")


def _require_status(name: str, value: object) -> None:
    if type(value) is not HostCheckStatus:
        raise ValueError(f"{name} must be an exact HostCheckStatus")


def _require_sha256(name: str, value: object) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex string")


def _require_source_sha(name: str, value: object) -> None:
    if (
        type(value) is not str
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase 40-character source SHA")


def _require_sorted_unique_text_tuple(name: str, value: object) -> None:
    if type(value) is not tuple:
        raise ValueError(f"{name} must be an exact tuple")
    for item in value:
        _require_text(name, item)
    if tuple(sorted(set(value))) != value:
        raise ValueError(f"{name} must contain sorted unique text values")
