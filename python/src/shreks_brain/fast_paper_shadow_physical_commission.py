from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import grp
import re
import stat
import subprocess
import sys
import time
from typing import Callable, Mapping

from .fast_paper_shadow_host_prepare import (
    FastPaperShadowHostPreparePaths,
    preflight_fast_paper_shadow_host,
    read_fast_paper_shadow_host_environment,
    validate_fast_paper_shadow_production_environment,
)
from .fast_paper_runtime.shadow_supervisor import (
    bootstrap_fast_paper_shadow_supervisor,
)


_SCHEMA_VERSION = 1
_UNIT = "shreks-fast-paper-shadow.service"
_MODULE = "shreks_brain.fast_paper_runtime.shadow_supervisor"
_STATUS_SCHEMA = "shreks.fast_paper_shadow_supervisor_status"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_INVOCATION_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_MIN_OBSERVATION_SECONDS = 5
_MAX_OBSERVATION_SECONDS = 900
_ALLOWED_NON_ENABLED_STATES = frozenset(
    {"disabled", "static", "indirect", "generated", "transient"}
)
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


class FastPaperShadowPhysicalCommissionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or type(self.returncode) is not int:
            raise ValueError("returncode must be an exact integer")
        if type(self.stdout) is not str or type(self.stderr) is not str:
            raise ValueError("stdout/stderr must be exact strings")


@dataclass(frozen=True, slots=True)
class FastPaperShadowPhysicalCommissionPaths:
    current_link: Path
    unit_destination: Path
    config_destination: Path
    target_path: Path
    shadow_root: Path
    commissioning_root: Path
    proc_root: Path = Path("/proc")

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "unit_destination",
            "config_destination",
            "target_path",
            "shadow_root",
            "commissioning_root",
            "proc_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise ValueError(f"{name} must be an absolute Path")
        shadow = self.shadow_root.resolve(strict=False)
        commissioning = self.commissioning_root.resolve(strict=False)
        if commissioning == shadow or shadow in commissioning.parents:
            raise ValueError(
                "commissioning_root must stay outside the service-writable shadow tree"
            )

    @property
    def activation_receipt(self) -> Path:
        release = self.current_link.resolve(strict=False).name
        return self.commissioning_root / f"activation-{release}.json"

    @property
    def restart_receipt(self) -> Path:
        release = self.current_link.resolve(strict=False).name
        return self.commissioning_root / f"restart-{release}.json"


@dataclass(frozen=True, slots=True)
class SystemdShadowState:
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
    unit_file_state: str


@dataclass(frozen=True, slots=True)
class ProcessResourceSnapshot:
    cpu_ticks: int
    rss_bytes: int
    storage_bytes: int
    network_bytes: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True, slots=True)
class DurableShadowSnapshot:
    manifest_fingerprint_sha256: str
    run_id: str
    binding_fingerprint_sha256: str
    checkpoint_sequence: int
    checkpoint_payload_sha256: str
    runtime_state_fingerprint_sha256: str
    last_processed_source_sequence: int | None
    last_processed_source_event_id: str | None
    pending_buy_fingerprint_sha256: str | None
    market_position_ids: tuple[str, ...]


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]
Clock = Callable[[], int]
Sleeper = Callable[[float], object]


def preflight_fast_paper_shadow_physical(
    *,
    expected_release_source_sha: str,
    paths: FastPaperShadowPhysicalCommissionPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root()
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release = _require_release_runtime(
        paths,
        expected_sha,
        runtime_executable,
    )
    _run_protected_host_preflight(
        expected_sha=expected_sha,
        paths=paths,
        runtime_executable=runtime_executable,
    )
    runner = _default_command_runner if command_runner is None else command_runner
    state = _read_systemd_state(runner)
    _require_not_enabled(state)
    return _finalize_receipt(
        {
            "schema_name": "shreks.fast_paper_shadow_physical_preflight",
            "schema_version": _SCHEMA_VERSION,
            "state": "READY_FOR_ONE_TIME_DETACHED_START",
            "release_source_sha": expected_sha,
            "release_directory": str(release),
            "unit_file_state": state.unit_file_state,
            "active_state": state.active_state,
            "sub_state": state.sub_state,
            **_authority_fields("DORMANT_DETACHED"),
        }
    )


def activate_fast_paper_shadow(
    *,
    expected_release_source_sha: str,
    observation_seconds: int,
    paths: FastPaperShadowPhysicalCommissionPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
    clock_unix_ms: Clock | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, object]:
    _require_root()
    duration = _validate_observation_seconds(observation_seconds)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release = _require_release_runtime(
        paths,
        expected_sha,
        runtime_executable,
    )
    runner = _default_command_runner if command_runner is None else command_runner
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    sleep = time.sleep if sleeper is None else sleeper

    if paths.activation_receipt.exists() or paths.activation_receipt.is_symlink():
        raise FastPaperShadowPhysicalCommissionError(
            "successful activation receipt already exists for this release"
        )

    _run_protected_host_preflight(
        expected_sha=expected_sha,
        paths=paths,
        runtime_executable=runtime_executable,
    )
    before = _read_systemd_state(runner)
    _require_not_enabled(before)
    if before.active_state != "inactive" or before.sub_state != "dead":
        raise FastPaperShadowPhysicalCommissionError(
            "shadow unit must be inactive/dead before one-time activation"
        )
    if before.main_pid != 0:
        raise FastPaperShadowPhysicalCommissionError(
            "inactive shadow unit must not have a MainPID"
        )

    _require_command_success(
        runner(("systemctl", "daemon-reload")),
        "shadow daemon reload",
    )

    _run_protected_host_preflight(
        expected_sha=expected_sha,
        paths=paths,
        runtime_executable=runtime_executable,
    )
    after_reload = _read_systemd_state(runner)
    _require_not_enabled(after_reload)
    if (
        after_reload.active_state != "inactive"
        or after_reload.sub_state != "dead"
        or after_reload.main_pid != 0
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow unit changed state during daemon reload"
        )

    _require_command_success(
        runner(("systemctl", "start", _UNIT)),
        "shadow service start",
    )
    running = _wait_for_running(
        runner,
        timeout_seconds=min(30, duration),
        sleeper=sleep,
    )
    _require_not_enabled(running)

    observation = _observe_running(
        expected_sha=expected_sha,
        release=release,
        duration=duration,
        paths=paths,
        runner=runner,
        clock=clock,
        sleeper=sleep,
    )
    material = {
        "schema_name": "shreks.fast_paper_shadow_physical_activation",
        "schema_version": _SCHEMA_VERSION,
        "state": "ACTIVE_DETACHED_OBSERVED",
        "release_source_sha": expected_sha,
        "release_directory": str(release),
        **observation,
        **_authority_fields(),
    }
    receipt = _finalize_receipt(material)
    _write_receipt_no_replace(paths.activation_receipt, receipt)
    return receipt


def observe_fast_paper_shadow(
    *,
    expected_release_source_sha: str,
    observation_seconds: int,
    paths: FastPaperShadowPhysicalCommissionPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
    clock_unix_ms: Clock | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, object]:
    _require_root()
    duration = _validate_observation_seconds(observation_seconds)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release = _require_release_runtime(
        paths,
        expected_sha,
        runtime_executable,
    )
    _run_protected_host_preflight(
        expected_sha=expected_sha,
        paths=paths,
        runtime_executable=runtime_executable,
    )
    runner = _default_command_runner if command_runner is None else command_runner
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    sleep = time.sleep if sleeper is None else sleeper
    observation = _observe_running(
        expected_sha=expected_sha,
        release=release,
        duration=duration,
        paths=paths,
        runner=runner,
        clock=clock,
        sleeper=sleep,
    )
    return _finalize_receipt(
        {
            "schema_name": "shreks.fast_paper_shadow_physical_observation",
            "schema_version": _SCHEMA_VERSION,
            "state": "ACTIVE_DETACHED_OBSERVED",
            "release_source_sha": expected_sha,
            "release_directory": str(release),
            **observation,
            **_authority_fields(),
        }
    )


def prove_fast_paper_shadow_restart(
    *,
    expected_release_source_sha: str,
    observation_seconds: int,
    paths: FastPaperShadowPhysicalCommissionPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
    clock_unix_ms: Clock | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, object]:
    _require_root()
    duration = _validate_observation_seconds(observation_seconds)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release = _require_release_runtime(
        paths,
        expected_sha,
        runtime_executable,
    )
    activation = _read_receipt(paths.activation_receipt)
    if (
        activation.get("schema_name")
        != "shreks.fast_paper_shadow_physical_activation"
        or activation.get("state") != "ACTIVE_DETACHED_OBSERVED"
        or activation.get("release_source_sha") != expected_sha
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "activation receipt is missing or incompatible"
        )
    if paths.restart_receipt.exists() or paths.restart_receipt.is_symlink():
        raise FastPaperShadowPhysicalCommissionError(
            "successful restart receipt already exists for this release"
        )

    _run_protected_host_preflight(
        expected_sha=expected_sha,
        paths=paths,
        runtime_executable=runtime_executable,
    )
    runner = _default_command_runner if command_runner is None else command_runner
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    sleep = time.sleep if sleeper is None else sleeper

    before_unit = _read_systemd_state(runner)
    _require_not_enabled(before_unit)
    _require_running_state(before_unit)
    _verify_process_provenance(paths, release, before_unit.main_pid, before_unit)
    before_snapshot = _capture_durable_shadow_snapshot(paths)

    _require_command_success(
        runner(("systemctl", "restart", _UNIT)),
        "shadow service restart",
    )
    after_unit = _wait_for_running(
        runner,
        timeout_seconds=min(30, duration),
        sleeper=sleep,
    )
    _require_not_enabled(after_unit)
    if after_unit.main_pid == before_unit.main_pid:
        raise FastPaperShadowPhysicalCommissionError(
            "controlled restart did not change MainPID"
        )
    if after_unit.invocation_id == before_unit.invocation_id:
        raise FastPaperShadowPhysicalCommissionError(
            "controlled restart did not change InvocationID"
        )
    if after_unit.n_restarts != before_unit.n_restarts:
        raise FastPaperShadowPhysicalCommissionError(
            "automatic restart counter changed during controlled restart"
        )

    observation = _observe_running(
        expected_sha=expected_sha,
        release=release,
        duration=duration,
        paths=paths,
        runner=runner,
        clock=clock,
        sleeper=sleep,
    )
    after_snapshot = _capture_durable_shadow_snapshot(paths)
    _verify_restart_monotonicity(before_snapshot, after_snapshot)

    material = {
        "schema_name": "shreks.fast_paper_shadow_physical_restart",
        "schema_version": _SCHEMA_VERSION,
        "state": "RESTART_RECONSTRUCTION_PROVEN",
        "release_source_sha": expected_sha,
        "release_directory": str(release),
        "pre_restart_main_pid": before_unit.main_pid,
        "post_restart_main_pid": after_unit.main_pid,
        "pre_restart_invocation_id": before_unit.invocation_id,
        "post_restart_invocation_id": after_unit.invocation_id,
        "automatic_restart_delta": (
            after_unit.n_restarts - before_unit.n_restarts
        ),
        "pre_checkpoint_sequence": before_snapshot.checkpoint_sequence,
        "post_checkpoint_sequence": after_snapshot.checkpoint_sequence,
        "pre_last_processed_source_sequence": (
            before_snapshot.last_processed_source_sequence
        ),
        "post_last_processed_source_sequence": (
            after_snapshot.last_processed_source_sequence
        ),
        "run_id": after_snapshot.run_id,
        "binding_fingerprint_sha256": (
            after_snapshot.binding_fingerprint_sha256
        ),
        **observation,
        **_authority_fields(),
    }
    receipt = _finalize_receipt(material)
    _write_receipt_no_replace(paths.restart_receipt, receipt)
    return receipt


def parse_supervisor_status_journal(
    payload: str,
) -> tuple[dict[str, object], ...]:
    if type(payload) is not str:
        raise FastPaperShadowPhysicalCommissionError(
            "journal payload must be text"
        )
    statuses: list[dict[str, object]] = []
    for raw in payload.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            document = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        if (
            not isinstance(document, dict)
            or document.get("schema_name") != _STATUS_SCHEMA
        ):
            continue
        if line != _canonical(document).rstrip("\n"):
            raise FastPaperShadowPhysicalCommissionError(
                "shadow supervisor status journal must be canonical JSON"
            )
        if (
            document.get("schema_version") != 1
            or document.get("mode") != "PAPER_SHADOW_COORDINATED"
            or document.get("state") != "RUNNING"
        ):
            raise FastPaperShadowPhysicalCommissionError(
                "shadow supervisor status journal contains incompatible state"
            )
        for name in (
            "completed_cycles",
            "decisions_produced",
            "executions_committed",
            "paper_checkpoint_sequence",
            "open_market_positions",
        ):
            value = document.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise FastPaperShadowPhysicalCommissionError(
                    f"shadow supervisor status {name} is invalid"
                )
        statuses.append(document)
    return tuple(statuses)


def _require_status_advancement(
    statuses: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], dict[str, object]]:
    if len(statuses) < 2:
        raise FastPaperShadowPhysicalCommissionError(
            "bounded observation requires at least two supervisor status records"
        )
    first = statuses[0]
    last = statuses[-1]
    if int(last["completed_cycles"]) <= int(first["completed_cycles"]):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow supervisor completed cycles did not advance"
        )
    identity_names = (
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
    )
    identity = tuple(first.get(name) for name in identity_names)
    if any(tuple(item.get(name) for name in identity_names) != identity for item in statuses):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow supervisor runtime identity changed during observation"
        )
    return first, last


def _observe_running(
    *,
    expected_sha: str,
    release: Path,
    duration: int,
    paths: FastPaperShadowPhysicalCommissionPaths,
    runner: CommandRunner,
    clock: Clock,
    sleeper: Sleeper,
) -> dict[str, object]:
    start_ms = _clock_value(clock)
    first_unit = _read_systemd_state(runner)
    _require_not_enabled(first_unit)
    _require_running_state(first_unit)
    _verify_process_provenance(paths, release, first_unit.main_pid, first_unit)
    first_resource = _read_process_resources(
        paths,
        first_unit.main_pid,
    )
    _require_private_network(first_resource)

    sleeper(float(duration))

    last_unit = _read_systemd_state(runner)
    _require_not_enabled(last_unit)
    _require_running_state(last_unit)
    if (
        last_unit.main_pid != first_unit.main_pid
        or last_unit.invocation_id != first_unit.invocation_id
        or last_unit.n_restarts != first_unit.n_restarts
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process PID/restart identity was not stable during observation"
        )
    _verify_process_provenance(paths, release, last_unit.main_pid, last_unit)
    last_resource = _read_process_resources(
        paths,
        last_unit.main_pid,
    )
    _require_private_network(last_resource)

    journal = runner(
        (
            "journalctl",
            "-u",
            _UNIT,
            "--since",
            f"@{start_ms // 1000}",
            "--output=cat",
            "--no-pager",
        )
    )
    _require_command_success(journal, "shadow supervisor journal read")
    statuses = parse_supervisor_status_journal(journal.stdout)
    first_status, last_status = _require_status_advancement(statuses)

    cpu_delta = last_resource.cpu_ticks - first_resource.cpu_ticks
    if cpu_delta < 0:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process CPU ticks regressed during observation"
        )
    try:
        clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError, TypeError):
        clock_ticks = 100
    if clock_ticks <= 0:
        clock_ticks = 100
    cpu_percent = (
        float(cpu_delta) / float(clock_ticks) / float(duration) * 100.0
    )
    if not math.isfinite(cpu_percent) or cpu_percent < 0.0:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process CPU observation is invalid"
        )

    network_start = dict(
        (name, (rx, tx))
        for name, rx, tx in first_resource.network_bytes
    )
    network_end = dict(
        (name, (rx, tx))
        for name, rx, tx in last_resource.network_bytes
    )
    if set(network_start) != set(network_end):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow private-network interfaces changed during observation"
        )
    network_rx_delta = sum(
        network_end[name][0] - network_start[name][0]
        for name in network_start
    )
    network_tx_delta = sum(
        network_end[name][1] - network_start[name][1]
        for name in network_start
    )
    if network_rx_delta < 0 or network_tx_delta < 0:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow private-network counters regressed"
        )

    return {
        "observed_at_unix_ms": start_ms,
        "observation_seconds": duration,
        "main_pid": first_unit.main_pid,
        "invocation_id": first_unit.invocation_id,
        "unit_file_state": first_unit.unit_file_state,
        "n_restarts": first_unit.n_restarts,
        "exec_main_status": first_unit.exec_main_status,
        "manifest_fingerprint_sha256": last_status[
            "manifest_fingerprint_sha256"
        ],
        "champion_version": last_status["champion_version"],
        "champion_fingerprint_sha256": last_status[
            "champion_fingerprint_sha256"
        ],
        "action_policy_version": last_status["action_policy_version"],
        "completed_cycles_start": first_status["completed_cycles"],
        "completed_cycles_end": last_status["completed_cycles"],
        "completed_cycles_delta": (
            int(last_status["completed_cycles"])
            - int(first_status["completed_cycles"])
        ),
        "decisions_produced_delta": (
            int(last_status["decisions_produced"])
            - int(first_status["decisions_produced"])
        ),
        "executions_committed_delta": (
            int(last_status["executions_committed"])
            - int(first_status["executions_committed"])
        ),
        "decision_cursor_sequence_start": first_status.get(
            "decision_cursor_sequence"
        ),
        "decision_cursor_sequence_end": last_status.get(
            "decision_cursor_sequence"
        ),
        "execution_cursor_sequence_start": first_status.get(
            "execution_cursor_sequence"
        ),
        "execution_cursor_sequence_end": last_status.get(
            "execution_cursor_sequence"
        ),
        "paper_checkpoint_sequence_start": first_status[
            "paper_checkpoint_sequence"
        ],
        "paper_checkpoint_sequence_end": last_status[
            "paper_checkpoint_sequence"
        ],
        "pending_buy": bool(last_status.get("pending_buy")),
        "open_market_positions": last_status["open_market_positions"],
        "cpu_ticks_delta": cpu_delta,
        "cpu_percent": cpu_percent,
        "rss_bytes_start": first_resource.rss_bytes,
        "rss_bytes_end": last_resource.rss_bytes,
        "rss_bytes_peak": max(
            first_resource.rss_bytes,
            last_resource.rss_bytes,
        ),
        "shadow_storage_bytes_start": first_resource.storage_bytes,
        "shadow_storage_bytes_end": last_resource.storage_bytes,
        "shadow_storage_bytes_delta": (
            last_resource.storage_bytes - first_resource.storage_bytes
        ),
        "private_network_interfaces": sorted(network_start),
        "private_network_non_loopback_interfaces": sorted(
            name for name in network_start if name != "lo"
        ),
        "private_network_rx_bytes_delta": network_rx_delta,
        "private_network_tx_bytes_delta": network_tx_delta,
    }


def _capture_durable_shadow_snapshot(
    paths: FastPaperShadowPhysicalCommissionPaths,
) -> DurableShadowSnapshot:
    try:
        environment = read_fast_paper_shadow_host_environment(
            paths.config_destination
        )
        provision_config = (
            validate_fast_paper_shadow_production_environment(environment)
        )
        bootstrap = bootstrap_fast_paper_shadow_supervisor(
            provision_config.supervisor_config
        )
        decision = bootstrap.decision_bootstrap
        execution = bootstrap.execution_bootstrap
        runtime = execution.runtime_state
        pending = runtime.pending_buy
        pending_fingerprint = None
        if pending is not None:
            pending_fingerprint = hashlib.sha256(
                _canonical(
                    {
                        "market_key": pending.market_key,
                        "mint": pending.mint,
                        "source_event_id": pending.source_event_id,
                        "target_exposure_fraction": (
                            pending.target_exposure_fraction
                        ),
                    }
                ).encode("utf-8")
            ).hexdigest()
        position_ids = tuple(
            item.position_id for item in runtime.market_positions
        )
        if len(position_ids) != len(set(position_ids)):
            raise ValueError("shadow market position IDs are not unique")
        return DurableShadowSnapshot(
            manifest_fingerprint_sha256=(
                decision.manifest.manifest_fingerprint_sha256
            ),
            run_id=execution.binding.run_id,
            binding_fingerprint_sha256=(
                execution.binding.binding_fingerprint_sha256
            ),
            checkpoint_sequence=execution.checkpoint.sequence,
            checkpoint_payload_sha256=execution.checkpoint.payload_sha256,
            runtime_state_fingerprint_sha256=(
                runtime.state_fingerprint_sha256
            ),
            last_processed_source_sequence=(
                runtime.last_processed_source_sequence
            ),
            last_processed_source_event_id=(
                runtime.last_processed_source_event_id
            ),
            pending_buy_fingerprint_sha256=pending_fingerprint,
            market_position_ids=position_ids,
        )
    except Exception as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "durable shadow state snapshot failed closed"
        ) from exc


def _verify_restart_monotonicity(
    before: DurableShadowSnapshot,
    after: DurableShadowSnapshot,
) -> None:
    if type(before) is not DurableShadowSnapshot or type(after) is not DurableShadowSnapshot:
        raise FastPaperShadowPhysicalCommissionError(
            "restart snapshots must be exact DurableShadowSnapshot values"
        )
    for name in (
        "manifest_fingerprint_sha256",
        "run_id",
        "binding_fingerprint_sha256",
    ):
        if getattr(before, name) != getattr(after, name):
            raise FastPaperShadowPhysicalCommissionError(
                f"shadow restart changed {name}"
            )
    if after.checkpoint_sequence < before.checkpoint_sequence:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow checkpoint sequence regressed across restart"
        )
    before_source = before.last_processed_source_sequence
    after_source = after.last_processed_source_sequence
    if before_source is not None and (
        after_source is None or after_source < before_source
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow processed source sequence regressed across restart"
        )
    if len(after.market_position_ids) != len(set(after.market_position_ids)):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow market position identities duplicated after restart"
        )
    if (
        before.pending_buy_fingerprint_sha256 is not None
        and after_source == before_source
        and after.pending_buy_fingerprint_sha256
        != before.pending_buy_fingerprint_sha256
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "pending BUY identity changed without durable source advancement"
        )


def _run_protected_host_preflight(
    *,
    expected_sha: str,
    paths: FastPaperShadowPhysicalCommissionPaths,
    runtime_executable: str | os.PathLike[str] | None,
) -> None:
    service_uid, service_gid = _resolve_service_identity()
    try:
        result = preflight_fast_paper_shadow_host(
            expected_release_source_sha=expected_sha,
            paths=FastPaperShadowHostPreparePaths(
                current_link=paths.current_link,
                unit_destination=paths.unit_destination,
                config_destination=paths.config_destination,
                shadow_root=paths.shadow_root,
                target_path=paths.target_path,
            ),
            runtime_executable=runtime_executable,
            service_uid=service_uid,
            service_gid=service_gid,
        )
    except Exception as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "protected shadow host readiness failed"
        ) from exc
    if (
        result.get("state")
        != "READY_FOR_DORMANT_SYSTEMD_LOAD_REVIEW"
        or result.get("release_source_sha") != expected_sha
        or result.get("live_authority") != "DISABLED"
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "protected shadow host readiness result is incompatible"
        )


def _resolve_service_identity() -> tuple[int, int]:
    try:
        account = pwd.getpwnam("shreks")
        group = grp.getgrnam("shreks")
    except KeyError as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "shreks service identity is unavailable"
        ) from exc
    if account.pw_gid != group.gr_gid:
        raise FastPaperShadowPhysicalCommissionError(
            "shreks service identity is inconsistent"
        )
    return account.pw_uid, group.gr_gid


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperShadowPhysicalCommissionError(
            "physical shadow commissioning requires root"
        )


def _validate_source_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowPhysicalCommissionError(
            "expected release SHA must be exactly 40 lowercase hex characters"
        )
    return value


def _validate_observation_seconds(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < _MIN_OBSERVATION_SECONDS
        or value > _MAX_OBSERVATION_SECONDS
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "observation seconds must be an integer from 5 through 900"
        )
    return value


def _require_release_runtime(
    paths: FastPaperShadowPhysicalCommissionPaths,
    expected_sha: str,
    runtime_executable: str | os.PathLike[str] | None,
) -> Path:
    current = paths.current_link
    if not current.is_symlink():
        raise FastPaperShadowPhysicalCommissionError(
            "current release must be a symlink"
        )
    try:
        release = current.resolve(strict=True)
    except OSError as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "current release cannot be resolved"
        ) from exc
    if release.name != expected_sha or not release.is_dir():
        raise FastPaperShadowPhysicalCommissionError(
            "current release does not match expected SHA"
        )
    executable = Path(
        sys.executable if runtime_executable is None else runtime_executable
    )
    try:
        if executable.is_symlink():
            raise FastPaperShadowPhysicalCommissionError(
                "commissioning runtime executable must not be a symlink"
            )
        resolved = executable.resolve(strict=True)
        expected_bin = (release / ".venv" / "bin").resolve(strict=True)
    except OSError as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning runtime executable cannot be resolved"
        ) from exc
    if not resolved.is_file() or resolved.parent != expected_bin:
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning must execute from exact active release virtualenv"
        )
    return release


def _read_systemd_state(runner: CommandRunner) -> SystemdShadowState:
    show = runner(_SHOW_COMMAND)
    _require_command_success(show, "shadow systemd show")
    enabled = runner(("systemctl", "is-enabled", _UNIT))
    unit_file_state = enabled.stdout.strip()
    if not unit_file_state:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow unit file state is unavailable"
        )
    fields = _parse_key_values(show.stdout)
    try:
        main_pid = int(fields["MainPID"], 10)
        n_restarts = int(fields["NRestarts"], 10)
        exec_main_status = int(fields["ExecMainStatus"], 10)
    except (KeyError, ValueError) as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow systemd numeric state is invalid"
        ) from exc
    if main_pid < 0 or n_restarts < 0 or exec_main_status < 0:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow systemd numeric state must be non-negative"
        )
    invocation = fields.get("InvocationID", "")
    if invocation and _INVOCATION_RE.fullmatch(invocation) is None:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow systemd InvocationID is invalid"
        )
    return SystemdShadowState(
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
        unit_file_state=unit_file_state,
    )


def _require_not_enabled(state: SystemdShadowState) -> None:
    if state.unit_file_state not in _ALLOWED_NON_ENABLED_STATES:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow unit is enabled or has an unsupported unit-file state"
        )


def _require_running_state(state: SystemdShadowState) -> None:
    if (
        state.active_state != "active"
        or state.sub_state != "running"
        or state.main_pid <= 0
        or state.exec_main_status != 0
        or not state.invocation_id
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow service is not healthy active/running"
        )


def _wait_for_running(
    runner: CommandRunner,
    *,
    timeout_seconds: int,
    sleeper: Sleeper,
) -> SystemdShadowState:
    attempts = max(1, timeout_seconds)
    last = _read_systemd_state(runner)
    for index in range(attempts):
        if (
            last.active_state == "active"
            and last.sub_state == "running"
            and last.main_pid > 0
            and last.exec_main_status == 0
            and last.invocation_id
        ):
            return last
        if index + 1 < attempts:
            sleeper(1.0)
            last = _read_systemd_state(runner)
    raise FastPaperShadowPhysicalCommissionError(
        "shadow service did not become healthy within bounded wait"
    )


def _verify_process_provenance(
    paths: FastPaperShadowPhysicalCommissionPaths,
    release: Path,
    pid: int,
    unit: SystemdShadowState,
) -> None:
    if unit.fragment_path != str(paths.unit_destination):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow systemd FragmentPath is not exact"
        )
    if unit.working_directory != "/opt/shreks/current":
        raise FastPaperShadowPhysicalCommissionError(
            "shadow systemd WorkingDirectory is not exact"
        )
    if unit.user != "shreks" or unit.group != "shreks":
        raise FastPaperShadowPhysicalCommissionError(
            "shadow systemd service identity is not exact"
        )
    if unit.private_network.lower() not in ("yes", "true"):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow systemd PrivateNetwork is not enabled"
        )

    proc = paths.proc_root / str(pid)
    try:
        cwd = (proc / "cwd").resolve(strict=True)
        cmdline = (proc / "cmdline").read_bytes().split(b"\0")
    except OSError as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process provenance cannot be read"
        ) from exc
    if cwd != release:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process cwd is outside exact active release"
        )
    args = [
        item.decode("utf-8", errors="strict")
        for item in cmdline
        if item
    ]
    expected_python = str(paths.current_link / ".venv" / "bin" / "python")
    if (
        len(args) < 3
        or args[0] != expected_python
        or args[1] != "-m"
        or args[2] != _MODULE
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process command line is not exact release supervisor"
        )


def _read_process_resources(
    paths: FastPaperShadowPhysicalCommissionPaths,
    pid: int,
) -> ProcessResourceSnapshot:
    proc = paths.proc_root / str(pid)
    try:
        stat_payload = (proc / "stat").read_text(encoding="utf-8").strip()
        status_payload = (proc / "status").read_text(encoding="utf-8")
        network_payload = (proc / "net" / "dev").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process resource evidence is unavailable"
        ) from exc

    right = stat_payload.rfind(")")
    if right < 0:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process stat payload is invalid"
        )
    rest = stat_payload[right + 2 :].split()
    try:
        user_ticks = int(rest[11], 10)
        system_ticks = int(rest[12], 10)
    except (IndexError, ValueError) as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process CPU counters are invalid"
        ) from exc
    if user_ticks < 0 or system_ticks < 0:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process CPU counters must be non-negative"
        )

    rss_kib: int | None = None
    for line in status_payload.splitlines():
        if line.startswith("VmRSS:"):
            pieces = line.split()
            if len(pieces) >= 2:
                try:
                    rss_kib = int(pieces[1], 10)
                except ValueError:
                    rss_kib = None
            break
    if rss_kib is None or rss_kib < 0:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow process RSS observation is invalid"
        )

    network: list[tuple[str, int, int]] = []
    for line in network_payload.splitlines()[2:]:
        if ":" not in line:
            continue
        name, raw = line.split(":", 1)
        fields = raw.split()
        if len(fields) < 16:
            raise FastPaperShadowPhysicalCommissionError(
                "shadow private-network counters are invalid"
            )
        try:
            rx = int(fields[0], 10)
            tx = int(fields[8], 10)
        except ValueError as exc:
            raise FastPaperShadowPhysicalCommissionError(
                "shadow private-network counters are invalid"
            ) from exc
        if rx < 0 or tx < 0:
            raise FastPaperShadowPhysicalCommissionError(
                "shadow private-network counters must be non-negative"
            )
        network.append((name.strip(), rx, tx))

    return ProcessResourceSnapshot(
        cpu_ticks=user_ticks + system_ticks,
        rss_bytes=rss_kib * 1024,
        storage_bytes=_shadow_storage_bytes(paths.shadow_root),
        network_bytes=tuple(sorted(network)),
    )


def _require_private_network(snapshot: ProcessResourceSnapshot) -> None:
    non_loopback = tuple(
        name for name, _rx, _tx in snapshot.network_bytes if name != "lo"
    )
    if non_loopback:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow private network exposes non-loopback interfaces"
        )


def _shadow_storage_bytes(root: Path) -> int:
    if root.is_symlink() or not root.is_dir():
        raise FastPaperShadowPhysicalCommissionError(
            "shadow storage root must be a regular directory"
        )
    total = 0
    try:
        for path in root.rglob("*"):
            if path.is_symlink():
                raise FastPaperShadowPhysicalCommissionError(
                    "shadow storage tree contains a symlink"
                )
            if path.is_file():
                total += path.stat().st_size
    except OSError as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "shadow storage evidence cannot be collected"
        ) from exc
    return total


def _default_command_runner(command: tuple[str, ...]) -> HostCommandResult:
    if type(command) is not tuple:
        raise FastPaperShadowPhysicalCommissionError(
            "host command must be an exact tuple"
        )
    allowed = False
    if command in (
        ("systemctl", "daemon-reload"),
        ("systemctl", "start", _UNIT),
        ("systemctl", "restart", _UNIT),
        _SHOW_COMMAND,
        ("systemctl", "is-enabled", _UNIT),
    ):
        allowed = True
    elif (
        len(command) == 7
        and command[0:4] == ("journalctl", "-u", _UNIT, "--since")
        and re.fullmatch(r"@[0-9]+", command[4]) is not None
        and command[5:] == ("--output=cat", "--no-pager")
    ):
        allowed = True
    if not allowed:
        raise FastPaperShadowPhysicalCommissionError(
            "host command is outside physical commissioning allowlist"
        )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    return HostCommandResult(
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )


def _write_receipt_no_replace(
    path: Path,
    document: Mapping[str, object],
) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning receipt path must be absolute"
        )
    parent = path.parent
    if parent.is_symlink():
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning evidence root must not be a symlink"
        )
    if not parent.exists():
        try:
            parent.mkdir(mode=0o700)
            parent.chmod(0o700)
            _fsync_directory(parent.parent)
        except OSError as exc:
            raise FastPaperShadowPhysicalCommissionError(
                "commissioning evidence root could not be created"
            ) from exc
    if not parent.is_dir() or stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning evidence root must use mode 0700"
        )
    payload = _canonical(dict(document)).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning receipt destination already exists or is unsafe"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o600)
            os.fsync(handle.fileno())
        _fsync_directory(parent)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _read_receipt(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise FastPaperShadowPhysicalCommissionError(
            "activation receipt is missing"
        )
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise FastPaperShadowPhysicalCommissionError(
            "activation receipt mode is invalid"
        )
    try:
        payload = path.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "activation receipt is invalid"
        ) from exc
    if not isinstance(document, dict) or payload != _canonical(document):
        raise FastPaperShadowPhysicalCommissionError(
            "activation receipt is not canonical"
        )
    fingerprint = document.get("receipt_fingerprint_sha256")
    material = dict(document)
    material.pop("receipt_fingerprint_sha256", None)
    if (
        not isinstance(fingerprint, str)
        or fingerprint != hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest()
    ):
        raise FastPaperShadowPhysicalCommissionError(
            "activation receipt fingerprint mismatch"
        )
    return document


def _finalize_receipt(
    material: Mapping[str, object],
) -> dict[str, object]:
    document = dict(material)
    if "receipt_fingerprint_sha256" in document:
        raise FastPaperShadowPhysicalCommissionError(
            "receipt material may not predefine its fingerprint"
        )
    return {
        **document,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(document).encode("utf-8")
        ).hexdigest(),
    }


def _authority_fields(
    shadow_runtime: str = "ACTIVE_DETACHED",
) -> dict[str, str]:
    return {
        "shadow_runtime": shadow_runtime,
        "shadow_enable_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "authoritative_paper_runtime": "LEGACY_UNCHANGED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }


def _require_command_success(
    result: HostCommandResult,
    label: str,
) -> None:
    if type(result) is not HostCommandResult or result.returncode != 0:
        raise FastPaperShadowPhysicalCommissionError(
            f"{label} failed closed"
        )


def _parse_key_values(payload: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in payload.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in _SHOW_PROPERTIES and key not in result:
            result[key] = value
    return result


def _clock_value(clock: Clock) -> int:
    try:
        value = clock()
    except Exception as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning clock failed"
        ) from exc
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning clock must return a non-negative integer"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise FastPaperShadowPhysicalCommissionError(
            "commissioning directory sync failed"
        ) from exc


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _production_paths() -> FastPaperShadowPhysicalCommissionPaths:
    root = Path("/var/lib/shreks/fast-paper-shadow")
    return FastPaperShadowPhysicalCommissionPaths(
        current_link=Path("/opt/shreks/current"),
        unit_destination=Path(
            "/etc/systemd/system/shreks-fast-paper-shadow.service"
        ),
        config_destination=Path("/etc/shreks/fast-paper-shadow.env"),
        target_path=Path("/etc/systemd/system/shreks.target"),
        shadow_root=root,
        commissioning_root=Path(
            "/root/shreks-fast-paper-shadow-commissioning"
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-physical-commission"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("expected_release_source_sha")
    for name in ("activate", "observe", "restart-proof"):
        command = commands.add_parser(name)
        command.add_argument("expected_release_source_sha")
        command.add_argument(
            "--observe-seconds",
            type=int,
            required=True,
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = _production_paths()
    try:
        if args.command == "preflight":
            result = preflight_fast_paper_shadow_physical(
                expected_release_source_sha=args.expected_release_source_sha,
                paths=paths,
            )
        elif args.command == "activate":
            result = activate_fast_paper_shadow(
                expected_release_source_sha=args.expected_release_source_sha,
                observation_seconds=args.observe_seconds,
                paths=paths,
            )
        elif args.command == "observe":
            result = observe_fast_paper_shadow(
                expected_release_source_sha=args.expected_release_source_sha,
                observation_seconds=args.observe_seconds,
                paths=paths,
            )
        else:
            result = prove_fast_paper_shadow_restart(
                expected_release_source_sha=args.expected_release_source_sha,
                observation_seconds=args.observe_seconds,
                paths=paths,
            )
    except FastPaperShadowPhysicalCommissionError as exc:
        print(
            _canonical(
                {
                    "schema_name": (
                        "shreks.fast_paper_shadow_physical_failure"
                    ),
                    "schema_version": _SCHEMA_VERSION,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "production_paper_cutover": "NOT_GRANTED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            end="",
            file=sys.stderr,
        )
        return 1
    print(_canonical(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
