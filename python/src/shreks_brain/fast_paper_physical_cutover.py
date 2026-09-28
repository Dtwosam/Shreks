from __future__ import annotations

import argparse
from dataclasses import dataclass
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping
import zipfile

from .fast_paper_authoritative_commissioning_assets import (
    verify_fast_paper_authoritative_commissioning_wheel,
)
from .fast_paper_authoritative_cutover_baseline import (
    read_fast_paper_authoritative_cutover_baseline_receipt,
)
from .fast_paper_authoritative_cutover_config import (
    read_fast_paper_authoritative_cutover_environment,
    validate_fast_paper_authoritative_cutover_environment,
)
from .fast_paper_authoritative_host_prepare import (
    preflight_fast_paper_authoritative_host,
)
from .fast_paper_cutover_authorization import (
    build_fast_paper_cutover_authorization,
    encode_fast_paper_cutover_authorization,
)
from .fast_paper_cutover_preflight import assess_fast_paper_cutover_preflight
from shreks_brain.observer_campaign.runtime_manifest import (
    decode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.paper_validation import load_latest_paper_checkpoint

from .fast_paper_runtime.authoritative_handoff import (
    refresh_pristine_fast_paper_authoritative_handoff,
)
from .fast_paper_runtime.authoritative_runtime import (
    bootstrap_fast_paper_authoritative_runtime,
)


_SCHEMA_VERSION = 1
_UNIT = "shreks-paper-campaign.service"
_SHADOW_UNIT = "shreks-fast-paper-shadow.service"
_FAST_MODULE = "shreks_brain.fast_paper_runtime.authoritative_runtime"
_LEGACY_MODULE = "shreks_brain.observer_campaign.runtime"
_STATUS_SCHEMA = "shreks.fast_paper_authoritative_runtime_status"
_PACKAGE_PREFIX = (
    "shreks_brain/_sealed_fast_paper_authoritative_commissioning/"
)
_CANDIDATE_ASSET = "shreks-paper-campaign.fast-paper.service"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_INVOCATION_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_MIN_OBSERVATION_SECONDS = 5
_MAX_OBSERVATION_SECONDS = 900
_SHOW_PROPERTIES = (
    "ActiveState",
    "SubState",
    "MainPID",
    "NRestarts",
    "ExecMainStatus",
    "InvocationID",
    "FragmentPath",
    "WorkingDirectory",
    "User",
    "Group",
    "PrivateNetwork",
)
_SHOW_COMMAND = (
    "systemctl",
    "show",
    _UNIT,
    "--property=" + ",".join(_SHOW_PROPERTIES),
    "--no-pager",
)
_SHADOW_SHOW_COMMAND = (
    "systemctl",
    "show",
    _SHADOW_UNIT,
    "--property=ActiveState,SubState,MainPID",
    "--no-pager",
)


class FastPaperPhysicalCutoverError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class FastPaperPhysicalCutoverPaths:
    current_link: Path
    active_unit_destination: Path
    authoritative_config_path: Path
    cutover_authorization_path: Path
    commissioning_root: Path
    proc_root: Path = Path("/proc")

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "active_unit_destination",
            "authoritative_config_path",
            "cutover_authorization_path",
            "commissioning_root",
            "proc_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise ValueError(f"{name} must be an absolute Path")

    @property
    def success_receipt(self) -> Path:
        return self.commissioning_root / (
            f"cutover-{self.current_link.resolve(strict=False).name}.json"
        )

    @property
    def failure_receipt(self) -> Path:
        return self.commissioning_root / (
            f"cutover-failure-{self.current_link.resolve(strict=False).name}.json"
        )


@dataclass(frozen=True, slots=True)
class SystemdState:
    active_state: str
    sub_state: str
    main_pid: int
    n_restarts: int
    exec_main_status: int
    invocation_id: str
    fragment_path: str
    working_directory: str
    user: str
    group: str
    private_network: str


@dataclass(frozen=True, slots=True)
class DurableAuthoritativeSnapshot:
    decision_state_fingerprint_sha256: str
    decision_cursor_sequence: int | None
    decision_members: tuple[str, ...]
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    runtime_state_fingerprint_sha256: str
    last_processed_source_sequence: int | None
    last_processed_source_event_id: str | None
    pending_buy: bool
    market_position_ids: tuple[str, ...]
    source_members: tuple[tuple[str, tuple[str, ...]], ...]


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]
Sleeper = Callable[[float], object]
Clock = Callable[[], int]


def preflight_fast_paper_physical_cutover(
    *,
    expected_release_source_sha: str,
    authoritative_release_wheel_path: str | Path,
    release_platform: str,
    baseline_receipt_path: str | Path,
    paths: FastPaperPhysicalCutoverPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root()
    expected_sha = _source_sha(expected_release_source_sha)
    release = _require_release_runtime(
        paths,
        expected_sha,
        runtime_executable,
    )
    service_uid, service_gid = _service_identity()
    host = preflight_fast_paper_authoritative_host(
        expected_release_source_sha=expected_sha,
        current_link=paths.current_link,
        config_destination=paths.authoritative_config_path,
        baseline_receipt_path=baseline_receipt_path,
        runtime_executable=runtime_executable,
        service_uid=service_uid,
        service_gid=service_gid,
    )
    if (
        host.get("state") != "READY_FOR_PROTECTED_PAPER_CUTOVER_REVIEW"
        or host.get("release_source_sha") != expected_sha
    ):
        raise FastPaperPhysicalCutoverError(
            "authoritative protected-host readiness is incompatible"
        )
    candidate, commissioning_fp = _candidate_unit_from_wheel(
        authoritative_release_wheel_path,
        expected_sha=expected_sha,
        platform=release_platform,
    )
    legacy_payload, legacy_stat = _read_regular_no_follow(
        paths.active_unit_destination,
        "active legacy PAPER unit",
    )
    expected_legacy = (
        release / "deploy" / "systemd" / _UNIT
    ).read_bytes()
    if legacy_payload != expected_legacy:
        raise FastPaperPhysicalCutoverError(
            "active PAPER unit does not match exact release legacy unit"
        )
    _require_root_unit_metadata(legacy_stat)

    runner = _default_command_runner if command_runner is None else command_runner
    legacy = _read_systemd_state(runner)
    _require_running(legacy, "legacy PAPER")
    _verify_process(
        paths,
        release,
        legacy,
        expected_module=_LEGACY_MODULE,
        require_private_network=False,
    )
    _require_shadow_quiescent(runner)
    _require_authorization_absent(paths.cutover_authorization_path)

    config = _load_authoritative_config(paths.authoritative_config_path)
    snapshot = _capture_authoritative_snapshot(config)
    _require_pristine_authoritative_snapshot(snapshot, config)

    return _finalize_receipt(
        {
            "schema_name": "shreks.fast_paper_physical_cutover_preflight",
            "schema_version": _SCHEMA_VERSION,
            "state": "READY_FOR_PROTECTED_PAPER_CUTOVER",
            "release_source_sha": expected_sha,
            "release_directory": str(release),
            "authoritative_commissioning_manifest_fingerprint_sha256": (
                commissioning_fp
            ),
            "candidate_unit_sha256": hashlib.sha256(candidate).hexdigest(),
            "legacy_unit_sha256": hashlib.sha256(legacy_payload).hexdigest(),
            "fast_run_id": host["fast_run_id"],
            "baseline_receipt_fingerprint_sha256": (
                host["baseline_receipt_fingerprint_sha256"]
            ),
            "production_paper_cutover": "NOT_GRANTED",
            "service_control_authority": "NOT_EXERCISED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
    )


def activate_fast_paper_physical_cutover(
    *,
    expected_release_source_sha: str,
    authoritative_release_wheel_path: str | Path,
    release_platform: str,
    baseline_receipt_path: str | Path,
    fast_manifest_path: str | Path,
    champion_registry_path: str | Path,
    shadow_restart_receipt_path: str | Path,
    shadow_ledger_database_path: str | Path,
    legacy_runtime_manifest_path: str | Path,
    legacy_observer_database_path: str | Path,
    observation_seconds: int,
    paths: FastPaperPhysicalCutoverPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
    sleeper: Sleeper | None = None,
    clock_unix_ms: Clock | None = None,
) -> dict[str, object]:
    _require_root()
    duration = _observation_seconds(observation_seconds)
    expected_sha = _source_sha(expected_release_source_sha)
    release = _require_release_runtime(
        paths,
        expected_sha,
        runtime_executable,
    )
    if paths.success_receipt.exists() or paths.success_receipt.is_symlink():
        raise FastPaperPhysicalCutoverError(
            "successful physical cutover receipt already exists"
        )
    runner = _default_command_runner if command_runner is None else command_runner
    sleep = time.sleep if sleeper is None else sleeper
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms

    preflight = preflight_fast_paper_physical_cutover(
        expected_release_source_sha=expected_sha,
        authoritative_release_wheel_path=authoritative_release_wheel_path,
        release_platform=release_platform,
        baseline_receipt_path=baseline_receipt_path,
        paths=paths,
        runtime_executable=runtime_executable,
        command_runner=runner,
    )
    candidate, commissioning_fp = _candidate_unit_from_wheel(
        authoritative_release_wheel_path,
        expected_sha=expected_sha,
        platform=release_platform,
    )
    legacy_payload, legacy_stat = _read_regular_no_follow(
        paths.active_unit_destination,
        "active legacy PAPER unit",
    )
    config = _load_authoritative_config(paths.authoritative_config_path)
    stopped_legacy = False
    authorization_created = False
    candidate_installed = False
    fast_start_attempted = False
    pre_start_snapshot: DurableAuthoritativeSnapshot | None = None

    try:
        _require_success(
            runner(("systemctl", "stop", _UNIT)),
            "legacy PAPER stop",
        )
        stopped_legacy = True
        stopped = _read_systemd_state(runner)
        _require_stopped(stopped, "legacy PAPER")
        _require_shadow_quiescent(runner)

        bootstrap = _refresh_final_legacy_handoff(
            config,
            legacy_runtime_manifest_path=legacy_runtime_manifest_path,
            legacy_observer_database_path=legacy_observer_database_path,
            created_at_unix_ms=_clock_value(clock),
        )
        pre_start_snapshot = _capture_authoritative_snapshot(config)
        _require_pristine_authoritative_snapshot(
            pre_start_snapshot,
            config,
        )

        report = assess_fast_paper_cutover_preflight(
            fast_manifest_path=fast_manifest_path,
            champion_registry_path=champion_registry_path,
            shadow_restart_receipt_path=shadow_restart_receipt_path,
            shadow_ledger_database_path=shadow_ledger_database_path,
            legacy_runtime_manifest_path=legacy_runtime_manifest_path,
            legacy_observer_database_path=legacy_observer_database_path,
            authoritative_runtime_env_path=paths.authoritative_config_path,
            authoritative_decision_baseline_receipt_path=(
                baseline_receipt_path
            ),
            authoritative_release_wheel_path=(
                authoritative_release_wheel_path
            ),
            release_platform=release_platform,
            expected_release_sha=expected_sha,
        )
        if report.get("decision") != "CUTOVER_PREFLIGHT_READY":
            raise FastPaperPhysicalCutoverError(
                "final stopped-legacy cutover preflight is not READY"
            )

        baseline = read_fast_paper_authoritative_cutover_baseline_receipt(
            baseline_receipt_path
        )
        authorization = build_fast_paper_cutover_authorization(
            release_source_sha=expected_sha,
            manifest_fingerprint_sha256=(
                bootstrap.decision_bootstrap.manifest.manifest_fingerprint_sha256
            ),
            champion_version=(
                bootstrap.decision_bootstrap.manifest.champion_version
            ),
            champion_fingerprint_sha256=(
                bootstrap.decision_bootstrap.manifest.champion_fingerprint_sha256
            ),
            action_policy_version=(
                bootstrap.decision_bootstrap.manifest.action_policy.version
            ),
            fast_run_id=bootstrap.execution_bootstrap.binding.fast_run_id,
            binding_fingerprint_sha256=(
                bootstrap.execution_bootstrap.binding.binding_fingerprint_sha256
            ),
            execution_policy_fingerprint_sha256=(
                bootstrap.execution_bootstrap.execution_policy.policy_fingerprint_sha256
            ),
            cutover_preflight_report_fingerprint_sha256=(
                report["report_fingerprint_sha256"]
            ),
            baseline_receipt_fingerprint_sha256=(
                baseline["receipt_fingerprint_sha256"]
            ),
            authorized_at_unix_ms=_clock_value(clock),
        )
        _write_authorization_no_replace(
            paths.cutover_authorization_path,
            encode_fast_paper_cutover_authorization(
                authorization
            ).encode("utf-8"),
        )
        authorization_created = True

        _replace_unit(paths.active_unit_destination, candidate)
        candidate_installed = True
        _require_success(
            runner(("systemctl", "daemon-reload")),
            "PAPER cutover daemon reload",
        )
        fast_start_attempted = True
        _require_success(
            runner(("systemctl", "start", _UNIT)),
            "authoritative Fast PAPER start",
        )
        running = _wait_running(
            runner,
            timeout_seconds=min(30, duration),
            sleeper=sleep,
        )
        _verify_process(
            paths,
            release,
            running,
            expected_module=_FAST_MODULE,
        )
        started_at_unix_ms = _clock_value(clock)
        sleep(float(duration))
        after = _read_systemd_state(runner)
        _require_running(after, "authoritative Fast PAPER")
        if (
            after.main_pid != running.main_pid
            or after.invocation_id != running.invocation_id
            or after.n_restarts != running.n_restarts
        ):
            raise FastPaperPhysicalCutoverError(
                "authoritative Fast PAPER process was not stable during observation"
            )
        _verify_process(
            paths,
            release,
            after,
            expected_module=_FAST_MODULE,
        )
        statuses = _read_authoritative_statuses(
            runner,
            since_unix_ms=started_at_unix_ms,
        )
        _require_status_advancement(
            statuses,
            expected_manifest_fingerprint_sha256=(
                bootstrap.decision_bootstrap.manifest.manifest_fingerprint_sha256
            ),
            expected_champion_fingerprint_sha256=(
                bootstrap.decision_bootstrap.manifest.champion_fingerprint_sha256
            ),
        )
        after_snapshot = _capture_authoritative_snapshot(config)
        if pre_start_snapshot is None:
            raise FastPaperPhysicalCutoverError(
                "authoritative pre-start snapshot is missing"
            )
        _require_monotonic_authoritative_snapshot(
            pre_start_snapshot,
            after_snapshot,
        )

        material = {
            "schema_name": "shreks.fast_paper_physical_cutover",
            "schema_version": _SCHEMA_VERSION,
            "state": "PRODUCTION_PAPER_CUTOVER_ACTIVE",
            "release_source_sha": expected_sha,
            "release_directory": str(release),
            "authoritative_commissioning_manifest_fingerprint_sha256": (
                commissioning_fp
            ),
            "cutover_preflight_report_fingerprint_sha256": (
                report["report_fingerprint_sha256"]
            ),
            "authorization_fingerprint_sha256": (
                authorization["authorization_fingerprint_sha256"]
            ),
            "candidate_unit_sha256": hashlib.sha256(candidate).hexdigest(),
            "legacy_unit_sha256": hashlib.sha256(legacy_payload).hexdigest(),
            "main_pid": after.main_pid,
            "invocation_id": after.invocation_id,
            "n_restarts": after.n_restarts,
            "observation_seconds": duration,
            "completed_cycles_start": statuses[0]["completed_cycles"],
            "completed_cycles_end": statuses[-1]["completed_cycles"],
            "decisions_produced_end": statuses[-1]["decisions_produced"],
            "executions_committed_end": statuses[-1]["executions_committed"],
            "paper_checkpoint_sequence_start": (
                pre_start_snapshot.paper_checkpoint_sequence
            ),
            "paper_checkpoint_sequence_end": (
                after_snapshot.paper_checkpoint_sequence
            ),
            "legacy_paper_runtime": "STOPPED",
            "authoritative_paper_runtime": "FAST_LANE_LEARNED_ACTIVE",
            "production_paper_cutover": "ACTIVE",
            "service_control_authority": "EXERCISED_BY_PROTECTED_CEREMONY",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
        receipt = _finalize_receipt(material)
        _write_receipt_no_replace(paths.success_receipt, receipt)
        return receipt
    except Exception as cutover_error:
        if stopped_legacy:
            _recover_failed_cutover(
                paths=paths,
                runner=runner,
                release=release,
                config=config,
                pre_start_snapshot=pre_start_snapshot,
                legacy_payload=legacy_payload,
                legacy_stat=legacy_stat,
                authorization_created=authorization_created,
                candidate_installed=candidate_installed,
                fast_start_attempted=fast_start_attempted,
                error=cutover_error,
            )
        if isinstance(cutover_error, FastPaperPhysicalCutoverError):
            raise
        raise FastPaperPhysicalCutoverError(
            "physical PAPER cutover failed"
        ) from cutover_error


def _recover_failed_cutover(
    *,
    paths: FastPaperPhysicalCutoverPaths,
    runner: CommandRunner,
    release: Path,
    config,
    pre_start_snapshot: DurableAuthoritativeSnapshot | None,
    legacy_payload: bytes,
    legacy_stat: os.stat_result,
    authorization_created: bool,
    candidate_installed: bool,
    fast_start_attempted: bool,
    error: BaseException,
) -> None:
    try:
        runner(("systemctl", "stop", _UNIT))
    except Exception:
        pass
    after_snapshot = None
    if fast_start_attempted:
        try:
            after_snapshot = _capture_authoritative_snapshot(config)
        except Exception:
            after_snapshot = None

    if authorization_created:
        _remove_authorization(paths.cutover_authorization_path)
    if candidate_installed:
        _replace_unit(
            paths.active_unit_destination,
            legacy_payload,
            uid=legacy_stat.st_uid,
            gid=legacy_stat.st_gid,
            mode=stat.S_IMODE(legacy_stat.st_mode),
        )
        _require_success(
            runner(("systemctl", "daemon-reload")),
            "legacy PAPER rollback daemon reload",
        )

    if not fast_start_attempted:
        _require_success(
            runner(("systemctl", "start", _UNIT)),
            "legacy PAPER pre-activation rollback start",
        )
        restored = _wait_running(
            runner,
            timeout_seconds=30,
            sleeper=time.sleep,
        )
        _verify_process(
            paths,
            release,
            restored,
            expected_module=_LEGACY_MODULE,
            require_private_network=False,
        )
        raise FastPaperPhysicalCutoverError(
            "physical PAPER cutover failed before Fast start; "
            "legacy PAPER authority restored"
        ) from error

    state_changed = (
        pre_start_snapshot is None
        or after_snapshot is None
        or after_snapshot != pre_start_snapshot
    )
    failure = _finalize_receipt(
        {
            "schema_name": "shreks.fast_paper_physical_cutover_failure",
            "schema_version": _SCHEMA_VERSION,
            "state": "MANUAL_RECOVERY_REQUIRED",
            "release_source_sha": release.name,
            "authoritative_state_changed": state_changed,
            "legacy_unit_restored": candidate_installed,
            "legacy_service_restarted": False,
            "authorization_revoked": authorization_created,
            "production_paper_cutover": "STOPPED_MANUAL_RECOVERY",
            "service_control_authority": "EXERCISED_BY_PROTECTED_CEREMONY",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
            "error_type": type(error).__name__,
        }
    )
    _write_receipt_no_replace(paths.failure_receipt, failure)
    raise FastPaperPhysicalCutoverError(
        "physical PAPER cutover failed after Fast start; "
        "legacy score authority is not restored and PAPER remains stopped "
        "for manual recovery"
    ) from error


def _refresh_final_legacy_handoff(
    config,
    *,
    legacy_runtime_manifest_path: str | Path,
    legacy_observer_database_path: str | Path,
    created_at_unix_ms: int,
):
    try:
        before = bootstrap_fast_paper_authoritative_runtime(config)
        legacy_payload, _ = _read_regular_no_follow(
            Path(legacy_runtime_manifest_path),
            "final legacy PAPER runtime manifest",
        )
        legacy_manifest = (
            decode_observer_paper_campaign_runtime_manifest(
                legacy_payload
            )
        )
        legacy_checkpoint = load_latest_paper_checkpoint(
            legacy_observer_database_path,
            legacy_manifest.paper_run_id,
        )
        if legacy_checkpoint is None:
            raise ValueError(
                "final legacy PAPER checkpoint is missing"
            )
        result = refresh_pristine_fast_paper_authoritative_handoff(
            before.decision_bootstrap.manifest,
            before.execution_bootstrap.execution_policy,
            legacy_checkpoint,
            legacy_runtime_manifest_fingerprint_sha256=(
                legacy_manifest.manifest_fingerprint_sha256
            ),
            fast_run_id=before.execution_bootstrap.binding.fast_run_id,
            database_path=config.execution_config.database_path,
            created_at_unix_ms=created_at_unix_ms,
        )
        after = bootstrap_fast_paper_authoritative_runtime(config)
    except Exception as exc:
        raise FastPaperPhysicalCutoverError(
            "final legacy-to-Fast handoff refresh failed closed"
        ) from exc
    if (
        after.execution_bootstrap.binding != result.binding
        or after.execution_bootstrap.checkpoint != result.checkpoint
        or after.execution_bootstrap.checkpoint.sequence != 0
    ):
        raise FastPaperPhysicalCutoverError(
            "refreshed authoritative handoff bootstrap mismatch"
        )
    return after


def _candidate_unit_from_wheel(
    wheel_path: str | Path,
    *,
    expected_sha: str,
    platform: str,
) -> tuple[bytes, str]:
    manifest = verify_fast_paper_authoritative_commissioning_wheel(
        wheel_path,
        expected_source_sha=expected_sha,
        expected_platform=platform,
    )
    path = Path(wheel_path)
    try:
        with zipfile.ZipFile(path) as archive:
            payload = archive.read(
                f"{_PACKAGE_PREFIX}{_CANDIDATE_ASSET}"
            )
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise FastPaperPhysicalCutoverError(
            "sealed authoritative candidate unit cannot be read"
        ) from exc
    record = next(
        value for value in manifest.assets if value.name == _CANDIDATE_ASSET
    )
    if (
        len(payload) != record.size
        or hashlib.sha256(payload).hexdigest() != record.sha256
    ):
        raise FastPaperPhysicalCutoverError(
            "sealed authoritative candidate unit fingerprint mismatch"
        )
    return payload, manifest.manifest_fingerprint_sha256


def _load_authoritative_config(path: Path):
    try:
        env = read_fast_paper_authoritative_cutover_environment(path)
        from .fast_paper_runtime.codec import read_fast_paper_runtime_manifest

        manifest = read_fast_paper_runtime_manifest(
            env["SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH"]
        )
        return validate_fast_paper_authoritative_cutover_environment(
            env,
            manifest,
            authoritative_database_path=manifest.observer_database_path,
        )
    except Exception as exc:
        raise FastPaperPhysicalCutoverError(
            "authoritative runtime config authentication failed"
        ) from exc


def _capture_authoritative_snapshot(
    config,
) -> DurableAuthoritativeSnapshot:
    try:
        bootstrap = bootstrap_fast_paper_authoritative_runtime(config)
        decision = bootstrap.decision_bootstrap
        execution = bootstrap.execution_bootstrap
        cursor = decision.state.cursor
        runtime = execution.runtime_state
        source_roots = (
            ("execution", config.execution_config.source_directory),
            ("buy", config.buy_authority_source_directory),
            ("quote_usd", config.quote_usd_source_directory),
            ("reduction", config.reduction_source_directory),
            ("retry", config.pending_buy_retry_source_directory),
        )
        return DurableAuthoritativeSnapshot(
            decision_state_fingerprint_sha256=(
                decision.state.state_fingerprint_sha256
            ),
            decision_cursor_sequence=(
                None if cursor is None else cursor.decision_sequence
            ),
            decision_members=tuple(
                sorted(
                    child.name
                    for child in config.decision_config.evidence_directory.iterdir()
                )
            ),
            paper_checkpoint_sequence=execution.checkpoint.sequence,
            paper_checkpoint_payload_sha256=execution.checkpoint.payload_sha256,
            runtime_state_fingerprint_sha256=(
                runtime.state_fingerprint_sha256
            ),
            last_processed_source_sequence=(
                runtime.last_processed_source_sequence
            ),
            last_processed_source_event_id=(
                runtime.last_processed_source_event_id
            ),
            pending_buy=execution.checkpoint.state.pending_buy is not None,
            market_position_ids=tuple(
                value.position_id for value in runtime.market_positions
            ),
            source_members=tuple(
                (
                    name,
                    tuple(sorted(child.name for child in root.iterdir())),
                )
                for name, root in source_roots
            ),
        )
    except Exception as exc:
        raise FastPaperPhysicalCutoverError(
            "authoritative durable snapshot failed closed"
        ) from exc


def _require_pristine_authoritative_snapshot(snapshot, config) -> None:
    checkpoint = config.decision_config.checkpoint_path
    if checkpoint is None:
        raise FastPaperPhysicalCutoverError(
            "authoritative decision checkpoint path is missing"
        )
    if snapshot.decision_members != (checkpoint.name,):
        raise FastPaperPhysicalCutoverError(
            "authoritative decision directory is not pristine"
        )
    if any(members for _name, members in snapshot.source_members):
        raise FastPaperPhysicalCutoverError(
            "authoritative execution authority roots are not pristine"
        )
    if (
        snapshot.paper_checkpoint_sequence != 0
        or snapshot.last_processed_source_sequence is not None
        or snapshot.last_processed_source_event_id is not None
        or snapshot.pending_buy
        or snapshot.market_position_ids
    ):
        raise FastPaperPhysicalCutoverError(
            "authoritative economic state is not pristine before cutover"
        )


def _require_monotonic_authoritative_snapshot(before, after) -> None:
    if after.paper_checkpoint_sequence < before.paper_checkpoint_sequence:
        raise FastPaperPhysicalCutoverError(
            "authoritative PAPER checkpoint regressed after cutover"
        )
    if (
        after.paper_checkpoint_sequence == before.paper_checkpoint_sequence
        and after.paper_checkpoint_payload_sha256
        != before.paper_checkpoint_payload_sha256
    ):
        raise FastPaperPhysicalCutoverError(
            "authoritative checkpoint changed without sequence advancement"
        )
    if (
        before.decision_cursor_sequence is not None
        and (
            after.decision_cursor_sequence is None
            or after.decision_cursor_sequence
            < before.decision_cursor_sequence
        )
    ):
        raise FastPaperPhysicalCutoverError(
            "authoritative decision cursor regressed after cutover"
        )
    if (
        before.last_processed_source_sequence is not None
        and (
            after.last_processed_source_sequence is None
            or after.last_processed_source_sequence
            < before.last_processed_source_sequence
        )
    ):
        raise FastPaperPhysicalCutoverError(
            "authoritative execution cursor regressed after cutover"
        )


def _read_authoritative_statuses(
    runner: CommandRunner,
    *,
    since_unix_ms: int,
) -> tuple[dict[str, object], ...]:
    result = runner(
        (
            "journalctl",
            "-u",
            _UNIT,
            "--since",
            f"@{since_unix_ms / 1000.0:.3f}",
            "--no-pager",
            "-o",
            "cat",
        )
    )
    _require_success(result, "authoritative Fast PAPER journal read")
    values = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and value.get("schema_name") == _STATUS_SCHEMA
            and value.get("state") == "RUNNING"
        ):
            values.append(value)
    if len(values) < 2:
        raise FastPaperPhysicalCutoverError(
            "bounded cutover observation lacks two authoritative runtime statuses"
        )
    return tuple(values)


def _require_status_advancement(
    statuses: tuple[dict[str, object], ...],
    *,
    expected_manifest_fingerprint_sha256: str,
    expected_champion_fingerprint_sha256: str,
) -> None:
    previous = -1
    for value in statuses:
        if (
            value.get("mode") != "PAPER_AUTHORITATIVE_FAST"
            or value.get("production_paper_cutover")
            != "GRANTED_AND_ACTIVE"
            or value.get("signing_submission_authority") != "NOT_GRANTED"
            or value.get("live") != "DISABLED"
            or value.get("manifest_fingerprint_sha256")
            != expected_manifest_fingerprint_sha256
            or value.get("champion_fingerprint_sha256")
            != expected_champion_fingerprint_sha256
        ):
            raise FastPaperPhysicalCutoverError(
                "authoritative runtime status identity is incompatible"
            )
        cycles = value.get("completed_cycles")
        if isinstance(cycles, bool) or not isinstance(cycles, int):
            raise FastPaperPhysicalCutoverError(
                "authoritative runtime completed_cycles is invalid"
            )
        if cycles <= previous:
            raise FastPaperPhysicalCutoverError(
                "authoritative runtime cycles did not advance"
            )
        previous = cycles


def _read_systemd_state(runner: CommandRunner) -> SystemdState:
    result = runner(_SHOW_COMMAND)
    _require_success(result, "PAPER systemd show")
    fields = _parse_key_values(result.stdout)
    try:
        main_pid = int(fields["MainPID"])
        n_restarts = int(fields["NRestarts"])
        exec_main_status = int(fields["ExecMainStatus"])
    except (KeyError, ValueError) as exc:
        raise FastPaperPhysicalCutoverError(
            "PAPER systemd numeric state is invalid"
        ) from exc
    invocation = fields.get("InvocationID", "")
    if invocation and _INVOCATION_RE.fullmatch(invocation) is None:
        raise FastPaperPhysicalCutoverError(
            "PAPER systemd invocation id is invalid"
        )
    return SystemdState(
        active_state=fields.get("ActiveState", "unknown"),
        sub_state=fields.get("SubState", "unknown"),
        main_pid=main_pid,
        n_restarts=n_restarts,
        exec_main_status=exec_main_status,
        invocation_id=invocation,
        fragment_path=fields.get("FragmentPath", ""),
        working_directory=fields.get("WorkingDirectory", ""),
        user=fields.get("User", ""),
        group=fields.get("Group", ""),
        private_network=fields.get("PrivateNetwork", ""),
    )


def _require_shadow_quiescent(runner: CommandRunner) -> None:
    result = runner(_SHADOW_SHOW_COMMAND)
    _require_success(result, "detached shadow systemd show")
    fields = _parse_key_values(result.stdout)
    try:
        main_pid = int(fields["MainPID"])
    except (KeyError, ValueError) as exc:
        raise FastPaperPhysicalCutoverError(
            "detached shadow systemd state is invalid"
        ) from exc
    if (
        fields.get("ActiveState") != "inactive"
        or fields.get("SubState") != "dead"
        or main_pid != 0
    ):
        raise FastPaperPhysicalCutoverError(
            "detached shadow must remain inactive/dead during cutover"
        )


def _require_running(state: SystemdState, label: str) -> None:
    if (
        state.active_state != "active"
        or state.sub_state != "running"
        or state.main_pid <= 0
        or state.exec_main_status != 0
        or not state.invocation_id
    ):
        raise FastPaperPhysicalCutoverError(
            f"{label} is not healthy active/running"
        )


def _require_stopped(state: SystemdState, label: str) -> None:
    if (
        state.active_state != "inactive"
        or state.sub_state != "dead"
        or state.main_pid != 0
    ):
        raise FastPaperPhysicalCutoverError(
            f"{label} did not stop cleanly"
        )


def _wait_running(
    runner: CommandRunner,
    *,
    timeout_seconds: int,
    sleeper: Sleeper,
) -> SystemdState:
    last = _read_systemd_state(runner)
    for index in range(max(1, timeout_seconds)):
        try:
            _require_running(last, "PAPER service")
            return last
        except FastPaperPhysicalCutoverError:
            if index + 1 >= max(1, timeout_seconds):
                break
            sleeper(1.0)
            last = _read_systemd_state(runner)
    raise FastPaperPhysicalCutoverError(
        "PAPER service did not become healthy within bounded wait"
    )


def _verify_process(
    paths: FastPaperPhysicalCutoverPaths,
    release: Path,
    state: SystemdState,
    *,
    expected_module: str,
    require_private_network: bool = True,
) -> None:
    if state.fragment_path != str(paths.active_unit_destination):
        raise FastPaperPhysicalCutoverError(
            "PAPER unit FragmentPath is not exact"
        )
    if (
        state.working_directory != "/opt/shreks/current"
        or state.user != "shreks"
        or state.group != "shreks"
    ):
        raise FastPaperPhysicalCutoverError(
            "PAPER service identity is not exact"
        )
    if (
        require_private_network
        and state.private_network.lower() not in ("yes", "true")
    ):
        raise FastPaperPhysicalCutoverError(
            "authoritative Fast PAPER PrivateNetwork is not enabled"
        )
    proc = paths.proc_root / str(state.main_pid)
    try:
        cwd = (proc / "cwd").resolve(strict=True)
        args = [
            value.decode("utf-8", errors="strict")
            for value in (proc / "cmdline").read_bytes().split(b"\0")
            if value
        ]
    except (OSError, UnicodeError) as exc:
        raise FastPaperPhysicalCutoverError(
            "PAPER process provenance is unavailable"
        ) from exc
    expected_python = str(paths.current_link / ".venv" / "bin" / "python")
    if (
        cwd != release
        or len(args) < 3
        or args[0] != expected_python
        or args[1] != "-m"
        or args[2] != expected_module
    ):
        raise FastPaperPhysicalCutoverError(
            "PAPER process does not match expected release runtime"
        )


def _replace_unit(
    destination: Path,
    payload: bytes,
    *,
    uid: int = 0,
    gid: int = 0,
    mode: int = 0o644,
) -> None:
    parent = destination.parent
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.cutover-",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), uid, gid)
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_directory(parent)
    finally:
        temporary.unlink(missing_ok=True)


def _write_authorization_no_replace(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise FastPaperPhysicalCutoverError(
            "cutover authorization already exists"
        )
    _require_safe_root_parent(path.parent)
    _uid, gid = _service_identity()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.cutover-",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    linked = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), 0, gid)
            os.fchmod(handle.fileno(), 0o640)
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
        linked = True
        temporary.unlink()
        _fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        if linked:
            path.unlink(missing_ok=True)
        raise


def _remove_authorization(path: Path) -> None:
    if path.is_symlink():
        raise FastPaperPhysicalCutoverError(
            "cutover authorization path became a symlink"
        )
    path.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _require_authorization_absent(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FastPaperPhysicalCutoverError(
            "production cutover authorization must not exist before ceremony"
        )


def _require_root_unit_metadata(value: os.stat_result) -> None:
    if (
        value.st_uid != 0
        or value.st_gid != 0
        or stat.S_IMODE(value.st_mode) != 0o644
    ):
        raise FastPaperPhysicalCutoverError(
            "active legacy PAPER unit metadata is not root:root 0644"
        )


def _read_regular_no_follow(
    path: Path,
    label: str,
) -> tuple[bytes, os.stat_result]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FastPaperPhysicalCutoverError(
            f"{label} must be an existing regular non-symlink file"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise FastPaperPhysicalCutoverError(
                f"{label} must be a regular file"
            )
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(payload) != before.st_size
        ):
            raise FastPaperPhysicalCutoverError(
                f"{label} changed while being read"
            )
        return payload, after
    finally:
        os.close(descriptor)


def _parse_key_values(payload: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in payload.splitlines():
        if not raw:
            continue
        if "=" not in raw:
            raise FastPaperPhysicalCutoverError(
                "systemd property output is malformed"
            )
        key, value = raw.split("=", 1)
        if key in values:
            raise FastPaperPhysicalCutoverError(
                "systemd property output contains duplicate keys"
            )
        values[key] = value
    return values


def _require_success(result: HostCommandResult, label: str) -> None:
    if result.returncode != 0 or result.stderr.strip():
        raise FastPaperPhysicalCutoverError(f"{label} failed")


def _default_command_runner(command: tuple[str, ...]) -> HostCommandResult:
    allowed = (
        command == _SHOW_COMMAND
        or command == _SHADOW_SHOW_COMMAND
        or command in (
            ("systemctl", "stop", _UNIT),
            ("systemctl", "start", _UNIT),
            ("systemctl", "daemon-reload"),
        )
        or (
            len(command) == 8
            and command[:3] == ("journalctl", "-u", _UNIT)
            and command[3] == "--since"
            and command[5:] == ("--no-pager", "-o", "cat")
        )
    )
    if not allowed:
        raise FastPaperPhysicalCutoverError(
            "physical cutover host command is outside the allowlist"
        )
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise FastPaperPhysicalCutoverError(
            "physical cutover host command invocation failed"
        ) from exc
    return HostCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _require_release_runtime(
    paths: FastPaperPhysicalCutoverPaths,
    expected_sha: str,
    runtime_executable: str | os.PathLike[str] | None,
) -> Path:
    current = paths.current_link
    if not current.is_symlink():
        raise FastPaperPhysicalCutoverError(
            "current release must be a symlink"
        )
    try:
        release = current.resolve(strict=True)
    except OSError as exc:
        raise FastPaperPhysicalCutoverError(
            "current release cannot be resolved"
        ) from exc
    if release.name != expected_sha or not release.is_dir():
        raise FastPaperPhysicalCutoverError(
            "current release does not match expected SHA"
        )
    executable = Path(
        sys.executable if runtime_executable is None else runtime_executable
    )
    try:
        if executable.is_symlink():
            raise FastPaperPhysicalCutoverError(
                "cutover runtime executable must not be a symlink"
            )
        resolved = executable.resolve(strict=True)
        expected_bin = (release / ".venv" / "bin").resolve(strict=True)
    except OSError as exc:
        raise FastPaperPhysicalCutoverError(
            "cutover runtime executable cannot be resolved"
        ) from exc
    if not resolved.is_file() or resolved.parent != expected_bin:
        raise FastPaperPhysicalCutoverError(
            "cutover must execute from exact current release virtualenv"
        )
    return release


def _service_identity() -> tuple[int, int]:
    try:
        user = pwd.getpwnam("shreks")
        group = grp.getgrnam("shreks")
    except KeyError as exc:
        raise FastPaperPhysicalCutoverError(
            "shreks service identity is unavailable"
        ) from exc
    if user.pw_gid != group.gr_gid:
        raise FastPaperPhysicalCutoverError(
            "shreks service identity is inconsistent"
        )
    return user.pw_uid, group.gr_gid


def _require_safe_root_parent(path: Path) -> None:
    try:
        value = path.lstat()
    except OSError as exc:
        raise FastPaperPhysicalCutoverError(
            "cutover authorization parent is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(value.st_mode)
        or not stat.S_ISDIR(value.st_mode)
        or value.st_uid != 0
        or stat.S_IMODE(value.st_mode) & 0o022
    ):
        raise FastPaperPhysicalCutoverError(
            "cutover authorization parent metadata is unsafe"
        )


def _write_receipt_no_replace(
    path: Path,
    document: Mapping[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.exists() or path.is_symlink():
        raise FastPaperPhysicalCutoverError(
            "physical cutover receipt already exists"
        )
    payload = (_canonical(dict(document)) + "\n").encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _finalize_receipt(material: dict[str, object]) -> dict[str, object]:
    return {
        **material,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _source_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperPhysicalCutoverError(
            "expected release SHA must be exactly 40 lowercase hex"
        )
    return value


def _observation_seconds(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < _MIN_OBSERVATION_SECONDS
        or value > _MAX_OBSERVATION_SECONDS
    ):
        raise FastPaperPhysicalCutoverError(
            "observation seconds must be an integer from 5 through 900"
        )
    return value


def _clock_value(clock: Clock) -> int:
    value = clock()
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperPhysicalCutoverError(
            "cutover clock must return non-negative integer unix-ms"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperPhysicalCutoverError(
            "physical PAPER cutover requires root"
        )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _production_paths() -> FastPaperPhysicalCutoverPaths:
    return FastPaperPhysicalCutoverPaths(
        current_link=Path("/opt/shreks/current"),
        active_unit_destination=Path(
            "/etc/systemd/system/shreks-paper-campaign.service"
        ),
        authoritative_config_path=Path(
            "/etc/shreks/fast-paper-authoritative.env"
        ),
        cutover_authorization_path=Path(
            "/etc/shreks/fast-paper-cutover-authorization.json"
        ),
        commissioning_root=Path("/root/shreks-fast-paper-cutover"),
    )


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("expected_release_source_sha")
    parser.add_argument("--authoritative-release-wheel-path", required=True)
    parser.add_argument("--release-platform", required=True)
    parser.add_argument("--baseline-receipt-path", required=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-physical-cutover"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    _add_common_arguments(preflight)

    activate = commands.add_parser("activate")
    _add_common_arguments(activate)
    activate.add_argument("--fast-manifest-path", required=True)
    activate.add_argument("--champion-registry-path", required=True)
    activate.add_argument("--shadow-restart-receipt-path", required=True)
    activate.add_argument("--shadow-ledger-database-path", required=True)
    activate.add_argument("--legacy-runtime-manifest-path", required=True)
    activate.add_argument("--legacy-observer-database-path", required=True)
    activate.add_argument("--observe-seconds", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(
        sys.argv[1:] if argv is None else argv
    )
    paths = _production_paths()
    common = {
        "expected_release_source_sha": args.expected_release_source_sha,
        "authoritative_release_wheel_path": (
            args.authoritative_release_wheel_path
        ),
        "release_platform": args.release_platform,
        "baseline_receipt_path": args.baseline_receipt_path,
        "paths": paths,
    }
    try:
        if args.command == "preflight":
            result = preflight_fast_paper_physical_cutover(**common)
        else:
            result = activate_fast_paper_physical_cutover(
                fast_manifest_path=args.fast_manifest_path,
                champion_registry_path=args.champion_registry_path,
                shadow_restart_receipt_path=(
                    args.shadow_restart_receipt_path
                ),
                shadow_ledger_database_path=(
                    args.shadow_ledger_database_path
                ),
                legacy_runtime_manifest_path=(
                    args.legacy_runtime_manifest_path
                ),
                legacy_observer_database_path=(
                    args.legacy_observer_database_path
                ),
                observation_seconds=args.observe_seconds,
                **common,
            )
    except Exception as exc:
        print(
            _canonical(
                {
                    "schema_name": "shreks.fast_paper_physical_cutover_failure",
                    "schema_version": _SCHEMA_VERSION,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "production_paper_cutover": "NOT_ACTIVE",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
