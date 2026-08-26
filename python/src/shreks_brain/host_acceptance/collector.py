from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import hashlib
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

from shreks_brain.backup import verify_backup_bundle
from shreks_brain.observer_campaign.runtime import (
    preflight_observer_paper_campaign_runtime,
)
from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfig,
)
from shreks_brain.risk_control import load_operator_risk_control_state

from .codec import fingerprint_host_acceptance_record
from .models import (
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


_ZERO_SHA256 = "0" * 64
_ENABLED_REQUIRED = frozenset(
    {
        "shreks.target",
        "shreks-telemetry.timer",
        "shreks-dashboard.service",
        "shreks-alerts.timer",
        "shreks-backup.timer",
    }
)
_SHOW_PROPERTIES = (
    "ActiveState",
    "SubState",
    "NRestarts",
    "ExecMainStatus",
    "ActiveEnterTimestamp",
)


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or type(self.returncode) is not int:
            raise ValueError("returncode must be an exact integer")
        if type(self.stdout) is not str:
            raise ValueError("stdout must be an exact string")


@dataclass(frozen=True, slots=True)
class ProtectedPathRequirement:
    role: str
    path: Path
    expected_kind: ProtectedPathKind
    expected_mode: int | None
    secret: bool

    def __post_init__(self) -> None:
        if type(self.role) is not str or not self.role or self.role.strip() != self.role:
            raise ValueError("protected path role must be non-empty trimmed text")
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError("protected path must be an absolute Path")
        if type(self.expected_kind) is not ProtectedPathKind:
            raise ValueError("expected_kind must be an exact ProtectedPathKind")
        if self.expected_mode is not None and (
            isinstance(self.expected_mode, bool)
            or type(self.expected_mode) is not int
            or self.expected_mode < 0
            or self.expected_mode > 0o7777
        ):
            raise ValueError("expected_mode must be a valid numeric mode or None")
        if type(self.secret) is not bool:
            raise ValueError("secret must be an exact bool")


@dataclass(frozen=True, slots=True)
class HostAcceptanceCaptureConfig:
    stage: HostAcceptanceStage
    host_label: str
    expected_release_sha: str
    observer_database_path: Path
    evidence_path: Path
    campaign_manifest_path: Path
    risk_control_path: Path
    backup_root: Path
    dashboard_port: int
    paper_cycle_interval_seconds: float
    current_release_path: Path = Path("/opt/shreks/current")
    managed_releases_path: Path = Path("/opt/shreks/releases")
    state_filesystem_path: Path = Path("/var/lib/shreks")
    protected_paths: tuple[ProtectedPathRequirement, ...] = ()

    def __post_init__(self) -> None:
        if type(self.stage) is not HostAcceptanceStage:
            raise ValueError("stage must be an exact HostAcceptanceStage")
        if type(self.host_label) is not str or not self.host_label or self.host_label.strip() != self.host_label:
            raise ValueError("host_label must be non-empty trimmed text")
        _require_source_sha(self.expected_release_sha)
        for name in (
            "observer_database_path",
            "evidence_path",
            "campaign_manifest_path",
            "risk_control_path",
            "backup_root",
            "current_release_path",
            "managed_releases_path",
            "state_filesystem_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise ValueError(f"{name} must be an absolute Path")
        if isinstance(self.dashboard_port, bool) or type(self.dashboard_port) is not int or not 1 <= self.dashboard_port <= 65535:
            raise ValueError("dashboard_port must be an integer from 1 through 65535")
        if (
            isinstance(self.paper_cycle_interval_seconds, bool)
            or not isinstance(self.paper_cycle_interval_seconds, (int, float))
            or not math.isfinite(self.paper_cycle_interval_seconds)
            or self.paper_cycle_interval_seconds <= 0
        ):
            raise ValueError("paper_cycle_interval_seconds must be positive and finite")
        if type(self.protected_paths) is not tuple or any(
            type(item) is not ProtectedPathRequirement for item in self.protected_paths
        ):
            raise ValueError("protected_paths must contain exact ProtectedPathRequirement values")
        roles = tuple(item.role for item in self.protected_paths)
        if len(roles) != len(set(roles)):
            raise ValueError("protected path requirement roles must be unique")


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]
Clock = Callable[[], int]
ResourceReader = Callable[[Path], HostResourceObservation]


def collect_host_acceptance_record(
    config: HostAcceptanceCaptureConfig,
    *,
    command_runner: CommandRunner | None = None,
    clock_unix_ms: Clock | None = None,
    resource_reader: ResourceReader | None = None,
) -> HostAcceptanceRecord:
    if type(config) is not HostAcceptanceCaptureConfig:
        raise ValueError("config must be an exact HostAcceptanceCaptureConfig")
    runner = _default_command_runner if command_runner is None else command_runner
    clock = _default_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    resource_probe = _default_resource_reader if resource_reader is None else resource_reader

    release = _collect_release(config)
    units = tuple(_collect_unit(unit_name, runner) for unit_name in PHASE_G_REQUIRED_UNITS)
    paper = _collect_paper(config)
    risk_control = _collect_risk_control(config.risk_control_path)
    backup = _collect_backup(config.backup_root)
    dashboard = _collect_dashboard(config.dashboard_port, runner)
    protected_paths = tuple(_collect_protected_path(item) for item in config.protected_paths)
    resources = resource_probe(config.state_filesystem_path)
    if type(resources) is not HostResourceObservation:
        raise ValueError("resource_reader must return an exact HostResourceObservation")

    overall = _combined_status(
        (
            release.check_status,
            *(item.check_status for item in units),
            paper.preflight_status,
            risk_control.check_status,
            backup.check_status,
            dashboard.check_status,
            *(item.check_status for item in protected_paths),
        )
    )
    record = HostAcceptanceRecord(
        schema_version=HOST_ACCEPTANCE_SCHEMA_VERSION,
        stage=config.stage,
        captured_at_unix_ms=clock(),
        host_label_sha256=hashlib.sha256(config.host_label.encode("utf-8")).hexdigest(),
        release=release,
        units=units,
        paper=paper,
        risk_control=risk_control,
        backup=backup,
        dashboard=dashboard,
        protected_paths=protected_paths,
        resources=resources,
        overall_status=overall,
        evidence_fingerprint_sha256=_ZERO_SHA256,
    )
    return replace(
        record,
        evidence_fingerprint_sha256=fingerprint_host_acceptance_record(record),
    )


def _collect_release(config: HostAcceptanceCaptureConfig) -> ReleaseObservation:
    current = config.current_release_path
    resolved = str(current)
    target_name = current.name
    manifest_sha: str | None = None
    valid = False
    try:
        if current.is_symlink():
            target = current.resolve(strict=True)
            resolved = str(target)
            target_name = target.name
            managed = config.managed_releases_path.resolve(strict=True)
            managed_parent = target.parent.resolve(strict=True)
            manifest_path = target / "RELEASE_MANIFEST.json"
            if manifest_path.is_file() and not manifest_path.is_symlink():
                manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            valid = (
                managed_parent == managed
                and target_name == config.expected_release_sha
                and manifest_sha is not None
            )
    except (OSError, RuntimeError, ValueError):
        valid = False
    return ReleaseObservation(
        expected_source_sha=config.expected_release_sha,
        resolved_current_path=resolved,
        current_target_name=target_name,
        current_is_managed_symlink=valid or (
            current.is_symlink() and _is_managed_symlink(current, config.managed_releases_path)
        ),
        release_manifest_sha256=manifest_sha,
        check_status=HostCheckStatus.PASS if valid else HostCheckStatus.FAIL,
    )


def _is_managed_symlink(current: Path, managed: Path) -> bool:
    try:
        target = current.resolve(strict=True)
        return current.is_symlink() and target.parent.resolve(strict=True) == managed.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return False


def _collect_unit(unit_name: str, command_runner: CommandRunner) -> SystemdUnitObservation:
    show = command_runner(
        (
            "systemctl",
            "show",
            unit_name,
            "--property=" + ",".join(_SHOW_PROPERTIES),
            "--no-pager",
        )
    )
    enabled = command_runner(("systemctl", "is-enabled", unit_name))
    fields = _parse_key_values(show.stdout) if show.returncode == 0 else {}
    active_state = fields.get("ActiveState", "unknown")
    sub_state = fields.get("SubState", "unknown")
    n_restarts = _parse_non_negative_int(fields.get("NRestarts"))
    exec_main_status = _parse_non_negative_int(fields.get("ExecMainStatus"))
    active_enter = fields.get("ActiveEnterTimestamp", "unknown") or "unknown"
    enabled_state = enabled.stdout.strip() or "unknown"

    if show.returncode != 0 or n_restarts is None or exec_main_status is None:
        status = HostCheckStatus.UNAVAILABLE
    else:
        active_ok = active_state == "active"
        enabled_ok = True
        if unit_name in _ENABLED_REQUIRED:
            enabled_ok = enabled.returncode == 0 and enabled_state == "enabled"
        status = HostCheckStatus.PASS if active_ok and enabled_ok else HostCheckStatus.FAIL

    return SystemdUnitObservation(
        unit_name=unit_name,
        required=True,
        active_state=active_state,
        sub_state=sub_state,
        enabled_state=enabled_state,
        n_restarts=0 if n_restarts is None else n_restarts,
        exec_main_status=0 if exec_main_status is None else exec_main_status,
        active_enter_timestamp=active_enter,
        check_status=status,
    )


def _collect_paper(config: HostAcceptanceCaptureConfig) -> PaperRecoveryObservation:
    runtime_config = ObserverPaperCampaignRuntimeConfig(
        observer_database_path=config.observer_database_path,
        evidence_path=config.evidence_path,
        manifest_path=config.campaign_manifest_path,
        cycle_interval_seconds=float(config.paper_cycle_interval_seconds),
        max_cycles=None,
        risk_control_path=config.risk_control_path,
    )
    bootstrap = preflight_observer_paper_campaign_runtime(
        runtime_config,
        status_sink=lambda _line: None,
    )
    state = bootstrap.restored_state
    ledger = state.ledger
    position_ids = {item.position_id for item in state.managed_positions}
    for position in ledger.positions:
        if getattr(position.state, "value", None) == "OPEN":
            position_ids.add(position.position_id)
    return PaperRecoveryObservation(
        paper_run_id=bootstrap.manifest.paper_run_id,
        candidate_version=bootstrap.manifest.candidate.candidate_version,
        campaign_manifest_fingerprint_sha256=(
            bootstrap.manifest.manifest_fingerprint_sha256
        ),
        last_cycle_at_unix_ms=state.last_cycle_at_unix_ms,
        ledger_as_of_unix_ms=ledger.as_of_unix_ms,
        ledger_entry_count=len(ledger.entries),
        processed_intent_keys=tuple(sorted(ledger.processed_intent_keys)),
        managed_position_ids=tuple(sorted(position_ids)),
        preflight_status=HostCheckStatus.PASS,
    )


def _collect_risk_control(path: Path) -> RiskControlObservation:
    state = load_operator_risk_control_state(path)
    state_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return RiskControlObservation(
        schema_version=state.schema_version,
        revision=state.revision,
        halt_new_entries=state.halt_new_entries,
        kill_switch_active=state.kill_switch_active,
        updated_at_unix_ms=state.updated_at_unix_ms,
        last_command=state.last_command.value,
        last_source=state.last_source.value,
        state_file_sha256=state_sha,
        check_status=HostCheckStatus.PASS,
    )


def _collect_backup(backup_root: Path) -> BackupObservation:
    candidates: list[tuple[int, Path, object]] = []
    try:
        children = tuple(backup_root.iterdir())
    except OSError:
        children = ()
    for child in children:
        if child.is_symlink() or not child.is_dir():
            continue
        try:
            manifest = verify_backup_bundle(child)
        except Exception:
            continue
        candidates.append((manifest.created_at_unix_ms, child, manifest))
    if not candidates:
        return BackupObservation(
            bundle_present=False,
            bundle_path=None,
            created_at_unix_ms=None,
            paper_run_id=None,
            campaign_manifest_fingerprint_sha256=None,
            manifest_sha256=None,
            check_status=HostCheckStatus.FAIL,
        )
    _, path, manifest = max(candidates, key=lambda item: (item[0], item[1].name))
    manifest_path = path / "manifest.json"
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return BackupObservation(
        bundle_present=True,
        bundle_path=str(path),
        created_at_unix_ms=manifest.created_at_unix_ms,
        paper_run_id=manifest.paper_run_id,
        campaign_manifest_fingerprint_sha256=(
            manifest.campaign_manifest_fingerprint_sha256
        ),
        manifest_sha256=manifest_sha,
        check_status=HostCheckStatus.PASS,
    )


def _collect_dashboard(port: int, command_runner: CommandRunner) -> DashboardExposureObservation:
    result = command_runner(("ss", "-ltnH"))
    if result.returncode != 0:
        return DashboardExposureObservation(
            port=port,
            listeners=(),
            loopback_only=False,
            check_status=HostCheckStatus.UNAVAILABLE,
        )
    listeners = []
    loopback_only = True
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        parsed = _split_listener(local)
        if parsed is None or parsed[1] != port:
            continue
        listeners.append(local)
        if parsed[0] not in ("127.0.0.1", "::1"):
            loopback_only = False
    normalized = tuple(sorted(set(listeners)))
    status = (
        HostCheckStatus.PASS
        if normalized and loopback_only
        else HostCheckStatus.FAIL
    )
    return DashboardExposureObservation(
        port=port,
        listeners=normalized,
        loopback_only=loopback_only if normalized else False,
        check_status=status,
    )


def _split_listener(value: str) -> tuple[str, int] | None:
    try:
        if value.startswith("["):
            end = value.rfind("]:")
            if end <= 0:
                return None
            host = value[1:end]
            port_text = value[end + 2 :]
        else:
            host, separator, port_text = value.rpartition(":")
            if not separator:
                return None
        port = int(port_text, 10)
    except (TypeError, ValueError):
        return None
    return host, port


def _collect_protected_path(
    requirement: ProtectedPathRequirement,
) -> ProtectedPathObservation:
    path = requirement.path
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return ProtectedPathObservation(
            role=requirement.role,
            path=str(path),
            kind=ProtectedPathKind.MISSING,
            exists=False,
            symlink=False,
            mode=None,
            owner_uid=None,
            group_gid=None,
            byte_size=None,
            check_status=HostCheckStatus.FAIL,
        )
    except OSError:
        return ProtectedPathObservation(
            role=requirement.role,
            path=str(path),
            kind=ProtectedPathKind.MISSING,
            exists=False,
            symlink=False,
            mode=None,
            owner_uid=None,
            group_gid=None,
            byte_size=None,
            check_status=HostCheckStatus.UNAVAILABLE,
        )

    is_symlink = stat.S_ISLNK(metadata.st_mode)
    if stat.S_ISREG(metadata.st_mode):
        kind = ProtectedPathKind.FILE
        byte_size: int | None = metadata.st_size
    elif stat.S_ISDIR(metadata.st_mode):
        kind = ProtectedPathKind.DIRECTORY
        byte_size = None
    else:
        kind = ProtectedPathKind.OTHER
        byte_size = None
    mode = stat.S_IMODE(metadata.st_mode)
    valid = not is_symlink and kind is requirement.expected_kind
    if requirement.expected_mode is not None:
        valid = valid and mode == requirement.expected_mode
    return ProtectedPathObservation(
        role=requirement.role,
        path=str(path),
        kind=kind,
        exists=True,
        symlink=is_symlink,
        mode=mode,
        owner_uid=metadata.st_uid,
        group_gid=metadata.st_gid,
        byte_size=byte_size,
        check_status=HostCheckStatus.PASS if valid else HostCheckStatus.FAIL,
    )


def _default_command_runner(command: tuple[str, ...]) -> HostCommandResult:
    if type(command) is not tuple or not command:
        raise ValueError("host command must be a non-empty tuple")
    if command[0] == "systemctl":
        if len(command) < 3 or command[1] not in ("show", "is-enabled"):
            raise ValueError("host acceptance systemctl command is not allowlisted")
        if command[2] not in PHASE_G_REQUIRED_UNITS:
            raise ValueError("host acceptance unit is not allowlisted")
    elif command != ("ss", "-ltnH"):
        raise ValueError("host acceptance command is not allowlisted")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    return HostCommandResult(returncode=completed.returncode, stdout=completed.stdout)


def _default_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _default_resource_reader(state_path: Path) -> HostResourceObservation:
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    uptime_seconds: float | None = None
    try:
        uptime_seconds = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        pass
    try:
        load_average: tuple[float, float, float] | None = tuple(os.getloadavg())
    except OSError:
        load_average = None

    memory_total: int | None = None
    memory_available: int | None = None
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, separator, raw = line.partition(":")
            if not separator:
                continue
            pieces = raw.strip().split()
            if not pieces:
                continue
            values[key] = int(pieces[0], 10) * 1024
        memory_total = values.get("MemTotal")
        memory_available = values.get("MemAvailable")
    except (OSError, ValueError):
        pass

    try:
        usage = shutil.disk_usage(state_path)
        fs_total: int | None = usage.total
        fs_free: int | None = usage.free
    except OSError:
        fs_total = None
        fs_free = None

    return HostResourceObservation(
        boot_id=boot_id,
        uptime_seconds=uptime_seconds,
        load_average=load_average,
        memory_total_bytes=memory_total,
        memory_available_bytes=memory_available,
        state_filesystem_total_bytes=fs_total,
        state_filesystem_free_bytes=fs_free,
    )


def _parse_key_values(payload: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in payload.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in _SHOW_PROPERTIES and key not in result:
            result[key] = value
    return result


def _parse_non_negative_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        result = int(value, 10)
    except ValueError:
        return None
    return result if result >= 0 else None


def _combined_status(statuses: tuple[HostCheckStatus, ...]) -> HostCheckStatus:
    if any(status is HostCheckStatus.FAIL for status in statuses):
        return HostCheckStatus.FAIL
    if any(status is HostCheckStatus.UNAVAILABLE for status in statuses):
        return HostCheckStatus.UNAVAILABLE
    return HostCheckStatus.PASS


def _require_source_sha(value: object) -> None:
    if (
        type(value) is not str
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("expected_release_sha must be a lowercase 40-character source SHA")
