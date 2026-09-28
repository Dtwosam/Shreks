from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping
import uuid
import zipfile

from .fast_paper_authoritative_cutover_config import (
    encode_fast_paper_authoritative_cutover_environment,
    read_fast_paper_authoritative_cutover_environment,
    validate_fast_paper_authoritative_cutover_environment,
)
from .fast_paper_cutover_authorization import (
    build_fast_paper_cutover_authorization,
    encode_fast_paper_cutover_authorization,
    read_fast_paper_cutover_authorization,
    verify_fast_paper_cutover_authorization,
)
from .fast_paper_physical_cutover import (
    FastPaperPhysicalCutoverError,
    HostCommandResult,
    _candidate_unit_from_wheel,
    _finalize_receipt,
    _read_authoritative_statuses,
    _read_regular_no_follow,
    _read_systemd_state,
    _replace_file_atomically,
    _require_running,
    _require_status_advancement,
    _require_stopped,
    _revoke_authorization_for_manual_recovery,
    _service_identity,
    _write_receipt_no_replace,
)
from .fast_paper_runtime.authoritative_release_handoff import (
    FastPaperAuthoritativeReleaseHandoffResult,
    initialize_fast_paper_authoritative_release_handoff,
)
from .fast_paper_runtime.authoritative_runtime import (
    bootstrap_fast_paper_authoritative_runtime,
)
from .fast_paper_runtime.codec import (
    build_fast_paper_runtime_manifest,
    build_fast_paper_runtime_state,
    read_fast_paper_runtime_manifest,
    read_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
    write_fast_paper_runtime_manifest,
    write_fast_paper_runtime_state,
)
from .fast_paper_runtime.shadow_buy_writer_policy import (
    build_fast_paper_shadow_buy_writer_policy,
    read_fast_paper_shadow_buy_writer_policy,
    verify_fast_paper_shadow_buy_writer_policy_bindings,
    write_fast_paper_shadow_buy_writer_policy,
)
from .fast_paper_runtime.shadow_execution_input import (
    build_fast_paper_shadow_execution_policy,
    read_fast_paper_shadow_execution_policy,
    write_fast_paper_shadow_execution_policy,
)
from .fast_paper_runtime.shadow_service import (
    read_fast_paper_shadow_service_policy,
)
from .fast_proof_tools import verify_fast_proof_tools_wheel
from .fast_runtime_tools import (
    FAST_RUNTIME_FEATURE_TOOL_NAME,
    verify_fast_runtime_tools_wheel,
)


_SCHEMA_NAME = "shreks.fast_paper_release_upgrade"
_SCHEMA_VERSION = 1
_FAILURE_SCHEMA_NAME = "shreks.fast_paper_release_upgrade_failure"

_RELEASE_MANIFEST_SCHEMA = "g2-release-manifest-v1"
_SUPPORTED_PLATFORMS = frozenset(
    ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu")
)
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UNIT = "shreks-paper-campaign.service"
_TARGET = "shreks.target"
_OBSERVE = "shreks-observe.service"
_EVIDENCE = "shreks-paper-evidence.service"
_FAST_MODULE = "shreks_brain.fast_paper_runtime.authoritative_runtime"
_REQUIRED_RELEASE_PATHS = frozenset(
    {
        "deploy/systemd/shreks-observe.service",
        "deploy/systemd/shreks-paper-campaign.service",
        "deploy/systemd/shreks-paper-evidence.service",
        "deploy/systemd/shreks.target",
        "target/release/shreks-observe",
        "target/release/shreks-paper-evidence",
    }
)
_PROOF_PREFIX = "shreks_brain/_sealed_fast_tools/"
_RUNTIME_PREFIX = "shreks_brain/_sealed_fast_runtime_tools/"
_SYSTEMD_SHOW_PROPERTIES = (
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
    *(f"-p={value}" for value in _SYSTEMD_SHOW_PROPERTIES),
)
_MIN_OBSERVATION_SECONDS = 5
_MAX_OBSERVATION_SECONDS = 900


class FastPaperReleaseUpgradeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperReleaseUpgradePaths:
    releases_dir: Path
    current_link: Path
    systemd_dir: Path
    authoritative_env_path: Path
    runtime_manifest_path: Path
    service_policy_path: Path
    execution_policy_path: Path
    buy_writer_policy_path: Path
    authorization_path: Path
    receipt_root: Path
    proc_root: Path = Path("/proc")

    def __post_init__(self) -> None:
        for name in (
            "releases_dir",
            "current_link",
            "systemd_dir",
            "authoritative_env_path",
            "runtime_manifest_path",
            "service_policy_path",
            "execution_policy_path",
            "buy_writer_policy_path",
            "authorization_path",
            "receipt_root",
            "proc_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise ValueError(f"{name} must be an absolute Path")

    @property
    def campaign_unit(self) -> Path:
        return self.systemd_dir / _UNIT

    def success_receipt_for(self, source_sha: str) -> Path:
        return self.receipt_root / f"success-{source_sha}.json"

    def failure_receipt_for(self, source_sha: str) -> Path:
        return self.receipt_root / f"failure-{source_sha}.json"


@dataclass(frozen=True, slots=True)
class _ReleaseIdentity:
    source_sha: str
    platform: str
    wheel_path: Path


@dataclass(frozen=True, slots=True)
class _SourceContext:
    release: Path
    manifest: object
    service_policy: object
    execution_policy: object
    buy_writer_policy: object
    environment: dict[str, str]
    config: object
    bootstrap: object
    authorization: dict[str, object]
    decision_state: object


@dataclass(frozen=True, slots=True)
class _TargetContext:
    release: Path
    identity: _ReleaseIdentity
    manifest: object
    execution_policy: object
    buy_writer_policy: object
    environment: dict[str, str]
    fast_run_id: str
    unit_payload: bytes
    commissioning_fingerprint_sha256: str


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]
Sleeper = Callable[[float], object]
Clock = Callable[[], int]


def preflight_fast_paper_release_upgrade(
    target_release: str | Path,
    *,
    paths: FastPaperReleaseUpgradePaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root()
    source = _load_source_context(
        paths,
        runtime_executable=runtime_executable,
    )
    target = _prepare_target_context(
        Path(target_release),
        source,
        paths=paths,
    )
    if target.identity.source_sha == source.manifest.release_source_sha:
        raise FastPaperReleaseUpgradeError(
            "target release must differ from current Fast PAPER release"
        )
    runner = _default_command_runner if command_runner is None else command_runner
    state = _read_systemd_state(runner)
    _require_running(state, "authoritative Fast PAPER service")
    _verify_fast_process(
        paths,
        source.release,
        state,
    )
    material = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "state": "READY_FOR_FAST_PAPER_RELEASE_UPGRADE",
        "source_release_source_sha": (
            source.manifest.release_source_sha
        ),
        "source_fast_run_id": (
            source.bootstrap.execution_bootstrap.binding.fast_run_id
        ),
        "source_manifest_fingerprint_sha256": (
            source.manifest.manifest_fingerprint_sha256
        ),
        "target_release_source_sha": target.identity.source_sha,
        "target_fast_run_id": target.fast_run_id,
        "target_manifest_fingerprint_sha256": (
            target.manifest.manifest_fingerprint_sha256
        ),
        "target_execution_policy_fingerprint_sha256": (
            target.execution_policy.policy_fingerprint_sha256
        ),
        "target_commissioning_fingerprint_sha256": (
            target.commissioning_fingerprint_sha256
        ),
        "service_control_authority": "NOT_EXERCISED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize_receipt(material)


def activate_fast_paper_release_upgrade(
    target_release: str | Path,
    *,
    paths: FastPaperReleaseUpgradePaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    observation_seconds: int = 5,
    command_runner: CommandRunner | None = None,
    sleeper: Sleeper = time.sleep,
    clock_unix_ms: Clock | None = None,
) -> dict[str, object]:
    _require_root()
    observation_seconds = _observation_seconds(observation_seconds)
    runner = _default_command_runner if command_runner is None else command_runner
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    source = _load_source_context(
        paths,
        runtime_executable=runtime_executable,
    )
    target = _prepare_target_context(
        Path(target_release),
        source,
        paths=paths,
    )
    _require_no_receipt(paths, target.identity.source_sha)
    state = _read_systemd_state(runner)
    _require_running(state, "authoritative Fast PAPER service")
    _verify_fast_process(paths, source.release, state)

    backup: _Backup | None = None
    paper_stopped = False
    start_attempted = False
    handoff: FastPaperAuthoritativeReleaseHandoffResult | None = None
    started_at_unix_ms = 0
    try:
        _run(runner, ("systemctl", "stop", _UNIT), "stop Fast PAPER")
        _require_stopped(
            _read_systemd_state(runner),
            "authoritative Fast PAPER service",
        )
        paper_stopped = True

        source = _load_source_context(
            paths,
            runtime_executable=runtime_executable,
        )
        backup = _capture_backup(source, paths)
        _replace_authorization_with_upgrade_marker(
            paths.authorization_path,
            source_release_sha=source.manifest.release_source_sha,
            target_release_sha=target.identity.source_sha,
            source_fast_run_id=(
                source.bootstrap.execution_bootstrap.binding.fast_run_id
            ),
            target_fast_run_id=target.fast_run_id,
        )

        handoff = initialize_fast_paper_authoritative_release_handoff(
            source.manifest,
            target.manifest,
            source.bootstrap.execution_bootstrap.binding,
            target.execution_policy,
            source.decision_state,
            target_fast_run_id=target.fast_run_id,
            database_path=source.config.execution_config.database_path,
            created_at_unix_ms=_clock_value(clock),
        )

        target_authorization = build_fast_paper_cutover_authorization(
            release_source_sha=target.manifest.release_source_sha,
            manifest_fingerprint_sha256=(
                target.manifest.manifest_fingerprint_sha256
            ),
            champion_version=target.manifest.champion_version,
            champion_fingerprint_sha256=(
                target.manifest.champion_fingerprint_sha256
            ),
            action_policy_version=target.manifest.action_policy.version,
            fast_run_id=target.fast_run_id,
            binding_fingerprint_sha256=(
                handoff.binding.binding_fingerprint_sha256
            ),
            execution_policy_fingerprint_sha256=(
                target.execution_policy.policy_fingerprint_sha256
            ),
            cutover_preflight_report_fingerprint_sha256=(
                str(
                    source.authorization[
                        "cutover_preflight_report_fingerprint_sha256"
                    ]
                )
            ),
            baseline_receipt_fingerprint_sha256=(
                str(
                    source.authorization[
                        "baseline_receipt_fingerprint_sha256"
                    ]
                )
            ),
            authorized_at_unix_ms=_clock_value(clock),
        )

        candidate_payloads = _target_control_payloads(
            target,
            handoff,
            target_authorization,
        )

        _stop_non_paper_runtime(runner)
        _install_target_controls(
            source,
            target,
            handoff,
            candidate_payloads,
            paths=paths,
        )
        _install_target_units(target, paths=paths)
        _atomic_switch(paths.current_link, target.release)
        _run(runner, ("systemctl", "daemon-reload"), "systemd daemon-reload")

        target_config = (
            validate_fast_paper_authoritative_cutover_environment(
                target.environment,
                target.manifest,
                authoritative_database_path=(
                    source.config.execution_config.database_path
                ),
            )
        )
        target_bootstrap = bootstrap_fast_paper_authoritative_runtime(
            target_config
        )
        if (
            target_bootstrap.execution_bootstrap.binding
            != handoff.binding
            or target_bootstrap.execution_bootstrap.checkpoint
            != handoff.checkpoint
            or target_bootstrap.execution_bootstrap.runtime_state
            != handoff.runtime_state
            or target_bootstrap.decision_bootstrap.state
            != handoff.decision_state
        ):
            raise FastPaperReleaseUpgradeError(
                "target Fast PAPER bootstrap does not match release handoff"
            )
        verify_fast_paper_cutover_authorization(
            target_authorization,
            manifest=target.manifest,
            binding=handoff.binding,
            execution_policy=target.execution_policy,
        )
        if backup is None:
            raise FastPaperReleaseUpgradeError(
                "post-stop source backup was not captured"
            )
        _replace_file_atomically(
            paths.authorization_path,
            candidate_payloads["authorization"],
            uid=backup.authorization_stat.st_uid,
            gid=backup.authorization_stat.st_gid,
            mode=stat.S_IMODE(backup.authorization_stat.st_mode),
        )

        started_at_unix_ms = _clock_value(clock)
        start_attempted = True
        _run(runner, ("systemctl", "start", _TARGET), "start target release")
        running = _wait_running(
            runner,
            timeout_seconds=30,
            sleeper=sleeper,
        )
        _verify_fast_process(paths, target.release, running)
        _require_other_services_active(runner)

        sleeper(float(observation_seconds))
        stable = _read_systemd_state(runner)
        _require_running(stable, "target authoritative Fast PAPER service")
        if (
            stable.main_pid != running.main_pid
            or stable.invocation_id != running.invocation_id
            or stable.n_restarts != running.n_restarts
        ):
            raise FastPaperReleaseUpgradeError(
                "target Fast PAPER service restarted during bounded observation"
            )
        statuses = _read_authoritative_statuses(
            runner,
            since_unix_ms=started_at_unix_ms,
        )
        _require_status_advancement(
            statuses,
            expected_manifest_fingerprint_sha256=(
                target.manifest.manifest_fingerprint_sha256
            ),
            expected_champion_fingerprint_sha256=(
                target.manifest.champion_fingerprint_sha256
            ),
        )
        final_bootstrap = bootstrap_fast_paper_authoritative_runtime(
            target_config
        )
        if (
            final_bootstrap.execution_bootstrap.binding.fast_run_id
            != target.fast_run_id
        ):
            raise FastPaperReleaseUpgradeError(
                "target runtime no longer uses successor Fast run"
            )

        material = {
            "schema_name": _SCHEMA_NAME,
            "schema_version": _SCHEMA_VERSION,
            "state": "FAST_PAPER_RELEASE_UPGRADE_ACTIVE",
            "source_release_source_sha": (
                source.manifest.release_source_sha
            ),
            "source_fast_run_id": (
                source.bootstrap.execution_bootstrap.binding.fast_run_id
            ),
            "target_release_source_sha": target.identity.source_sha,
            "target_fast_run_id": target.fast_run_id,
            "release_handoff_fingerprint_sha256": (
                handoff.handoff.handoff_fingerprint_sha256
            ),
            "target_manifest_fingerprint_sha256": (
                target.manifest.manifest_fingerprint_sha256
            ),
            "target_binding_fingerprint_sha256": (
                handoff.binding.binding_fingerprint_sha256
            ),
            "target_checkpoint_payload_sha256": (
                handoff.checkpoint.payload_sha256
            ),
            "target_runtime_state_fingerprint_sha256": (
                handoff.runtime_state.state_fingerprint_sha256
            ),
            "target_decision_state_fingerprint_sha256": (
                handoff.decision_state.state_fingerprint_sha256
            ),
            "target_authorization_fingerprint_sha256": (
                target_authorization[
                    "authorization_fingerprint_sha256"
                ]
            ),
            "authoritative_paper_runtime": "FAST_LANE_LEARNED_ACTIVE",
            "production_paper_cutover": "ACTIVE",
            "service_control_authority": (
                "EXERCISED_BY_PROTECTED_RELEASE_UPGRADE"
            ),
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
        receipt = _finalize_receipt(material)
        _write_receipt_no_replace(
            paths.success_receipt_for(target.identity.source_sha),
            receipt,
        )
        return receipt
    except Exception as error:
        if paper_stopped:
            try:
                if start_attempted:
                    _stop_all_runtime_best_effort(runner)
                    _revoke_authorization_for_manual_recovery(
                        paths.authorization_path,
                        release_source_sha=target.identity.source_sha,
                        error=error,
                    )
                    failure = _finalize_receipt(
                        {
                            "schema_name": _FAILURE_SCHEMA_NAME,
                            "schema_version": _SCHEMA_VERSION,
                            "state": "MANUAL_RECOVERY_REQUIRED",
                            "source_release_source_sha": (
                                source.manifest.release_source_sha
                            ),
                            "target_release_source_sha": (
                                target.identity.source_sha
                            ),
                            "target_fast_run_id": target.fast_run_id,
                            "target_start_attempted": True,
                            "source_fast_restarted": False,
                            "production_paper_cutover": (
                                "STOPPED_MANUAL_RECOVERY"
                            ),
                            "signing_submission_authority": "NOT_GRANTED",
                            "live_authority": "DISABLED",
                            "error_type": type(error).__name__,
                        }
                    )
                    _write_receipt_no_replace(
                        paths.failure_receipt_for(
                            target.identity.source_sha
                        ),
                        failure,
                    )
                else:
                    if backup is None:
                        raise FastPaperReleaseUpgradeError(
                            "source rollback backup is unavailable"
                        )
                    _restore_source_before_target_start(
                        source,
                        backup,
                        paths=paths,
                        runner=runner,
                        sleeper=sleeper,
                    )
            except Exception as recovery_error:
                raise FastPaperReleaseUpgradeError(
                    "Fast PAPER release upgrade failed and recovery failed"
                ) from recovery_error
        if start_attempted:
            raise FastPaperReleaseUpgradeError(
                "Fast PAPER release upgrade crossed target-start boundary; manual recovery required"
            ) from error
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release upgrade failed; source Fast release restored"
        ) from error


@dataclass(frozen=True, slots=True)
class _Backup:
    current_release: Path
    control_payloads: dict[Path, bytes]
    control_stats: dict[Path, os.stat_result]
    unit_payloads: dict[Path, bytes]
    authorization_payload: bytes
    authorization_stat: os.stat_result


def _load_source_context(
    paths: FastPaperReleaseUpgradePaths,
    *,
    runtime_executable: str | os.PathLike[str] | None,
) -> _SourceContext:
    release = _require_current_release(paths.current_link)
    identity = _verify_staged_release(release)
    if identity.source_sha != release.name:
        raise FastPaperReleaseUpgradeError(
            "current release directory does not match release manifest"
        )
    if runtime_executable is not None:
        executable = Path(runtime_executable)
        try:
            if (
                executable.is_symlink()
                or executable.resolve(strict=True).parent
                != (release / ".venv" / "bin").resolve(strict=True)
            ):
                raise FastPaperReleaseUpgradeError(
                    "release upgrade must execute from current release virtualenv"
                )
        except OSError as exc:
            raise FastPaperReleaseUpgradeError(
                "current release virtualenv identity cannot be resolved"
            ) from exc

    try:
        manifest = read_fast_paper_runtime_manifest(
            paths.runtime_manifest_path
        )
        verify_fast_paper_runtime_bindings(manifest)
        if manifest.release_source_sha != identity.source_sha:
            raise ValueError(
                "active Fast manifest release does not match current release"
            )
        service_policy = read_fast_paper_shadow_service_policy(
            paths.service_policy_path
        )
        execution_policy = read_fast_paper_shadow_execution_policy(
            manifest,
            paths.execution_policy_path,
        )
        buy_writer_policy = read_fast_paper_shadow_buy_writer_policy(
            paths.buy_writer_policy_path
        )
        verify_fast_paper_shadow_buy_writer_policy_bindings(
            manifest,
            service_policy,
            buy_writer_policy,
        )
        environment = read_fast_paper_authoritative_cutover_environment(
            paths.authoritative_env_path
        )
        config = validate_fast_paper_authoritative_cutover_environment(
            environment,
            manifest,
            authoritative_database_path=manifest.observer_database_path,
        )
        bootstrap = bootstrap_fast_paper_authoritative_runtime(config)
        decision_state = read_fast_paper_runtime_state(
            config.decision_config.checkpoint_path
        )
        if decision_state != build_fast_paper_runtime_state(
            manifest,
            cursor=decision_state.cursor,
        ):
            raise ValueError(
                "active learned decision state does not authenticate against manifest"
            )
        authorization = read_fast_paper_cutover_authorization(
            paths.authorization_path
        )
        verify_fast_paper_cutover_authorization(
            authorization,
            manifest=manifest,
            binding=bootstrap.execution_bootstrap.binding,
            execution_policy=execution_policy,
        )
    except Exception as exc:
        raise FastPaperReleaseUpgradeError(
            "current Fast PAPER release authority failed authentication"
        ) from exc
    return _SourceContext(
        release=release,
        manifest=manifest,
        service_policy=service_policy,
        execution_policy=execution_policy,
        buy_writer_policy=buy_writer_policy,
        environment=environment,
        config=config,
        bootstrap=bootstrap,
        authorization=authorization,
        decision_state=decision_state,
    )


def _prepare_target_context(
    release: Path,
    source: _SourceContext,
    *,
    paths: FastPaperReleaseUpgradePaths,
) -> _TargetContext:
    identity = _verify_staged_release(release)
    if identity.source_sha == source.manifest.release_source_sha:
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release upgrade target must be a distinct release"
        )
    wheel = identity.wheel_path
    try:
        proof_manifest = verify_fast_proof_tools_wheel(
            wheel,
            expected_source_sha=identity.source_sha,
            expected_platform=identity.platform,
        )
        runtime_manifest = verify_fast_runtime_tools_wheel(
            wheel,
            expected_source_sha=identity.source_sha,
            expected_platform=identity.platform,
        )
        unit_payload, commissioning_fingerprint = (
            _candidate_unit_from_wheel(
                wheel,
                expected_sha=identity.source_sha,
                platform=identity.platform,
            )
        )
    except Exception as exc:
        raise FastPaperReleaseUpgradeError(
            "target release sealed Fast assets failed authentication"
        ) from exc

    tool_root = release / ".venv" / "shreks-fast-tools"
    _require_target_tool_root(tool_root)
    proof_records = {
        value.name: value for value in proof_manifest.tools
    }
    decision_record = proof_records["shreks-fast-campaign-decision"]
    entry_record = proof_records["shreks-fast-entry-authority"]
    decision_binary = _materialize_target_wheel_binary(
        wheel,
        f"{_PROOF_PREFIX}shreks-fast-campaign-decision.bin",
        tool_root / "shreks-fast-campaign-decision",
        expected_size=decision_record.size,
        expected_sha256=decision_record.sha256,
    )
    entry_authority_binary = _materialize_target_wheel_binary(
        wheel,
        f"{_PROOF_PREFIX}shreks-fast-entry-authority.bin",
        tool_root / "shreks-fast-entry-authority",
        expected_size=entry_record.size,
        expected_sha256=entry_record.sha256,
    )
    feature_tool = _materialize_target_wheel_binary(
        wheel,
        f"{_RUNTIME_PREFIX}{FAST_RUNTIME_FEATURE_TOOL_NAME}.bin",
        tool_root / FAST_RUNTIME_FEATURE_TOOL_NAME,
        expected_size=runtime_manifest.size,
        expected_sha256=runtime_manifest.sha256,
    )
    target_champion = _target_path_for_same_asset(
        Path(source.manifest.champion_path),
        source.release,
        release,
        expected_sha256=source.manifest.champion_file_sha256,
    )
    try:
        target_manifest = build_fast_paper_runtime_manifest(
            release_source_sha=identity.source_sha,
            champion_path=target_champion,
            decision_binary_path=decision_binary,
            feature_feed_binary_path=feature_tool,
            action_policy=source.manifest.action_policy,
            state_version=source.manifest.state_version,
            risk_policy_version=source.manifest.risk_policy_version,
            fill_policy_version=source.manifest.fill_policy_version,
            position_action_policy_version=(
                source.manifest.position_action_policy_version
            ),
            strategy_family=source.manifest.strategy_family,
            strategy_version=source.manifest.strategy_version,
            assessment_version=source.manifest.assessment_version,
            observer_database_path=source.manifest.observer_database_path,
            paper_evidence_path=source.manifest.paper_evidence_path,
            checkpoint_path=source.manifest.checkpoint_path,
            quote_provider=source.manifest.quote_provider,
            quote_mint=source.manifest.quote_mint,
            quote_decimals=source.manifest.quote_decimals,
            route_evidence_version=source.manifest.route_evidence_version,
        )
        target_execution = build_fast_paper_shadow_execution_policy(
            target_manifest,
            risk_policy=source.execution_policy.risk_policy,
            fill_policy=source.execution_policy.fill_policy,
            position_action_policy=(
                source.execution_policy.position_action_policy
            ),
        )
        entry_sha = _sha256_file(entry_authority_binary)
        if entry_sha != source.buy_writer_policy.entry_authority_binary_sha256:
            raise ValueError(
                "target Fast entry-authority binary differs from active release"
            )
        target_buy = build_fast_paper_shadow_buy_writer_policy(
            market_read_policy=source.buy_writer_policy.market_read_policy,
            regime_read_policy=source.buy_writer_policy.regime_read_policy,
            regime_policy=source.buy_writer_policy.regime_policy,
            safety_policy=source.buy_writer_policy.safety_policy,
            safety_probe_identity=(
                source.buy_writer_policy.safety_probe_identity
            ),
            execution_economics_policies=(
                source.buy_writer_policy.execution_economics_policies
            ),
            operator_risk_control_path=(
                source.buy_writer_policy.operator_risk_control_path
            ),
            entry_authority_binary_path=entry_authority_binary,
            entry_authority_binary_sha256=entry_sha,
            day_started_at_unix_ms=(
                source.buy_writer_policy.day_started_at_unix_ms
            ),
            data_healthy=source.buy_writer_policy.data_healthy,
            execution_healthy=source.buy_writer_policy.execution_healthy,
            global_risk_halt=source.buy_writer_policy.global_risk_halt,
        )
        verify_fast_paper_shadow_buy_writer_policy_bindings(
            target_manifest,
            source.service_policy,
            target_buy,
        )
    except Exception as exc:
        raise FastPaperReleaseUpgradeError(
            "target Fast PAPER authority reconstruction failed"
        ) from exc

    target_run_id = _fresh_target_run_id(
        source.config.execution_config.database_path,
        identity.source_sha,
    )
    environment = dict(source.environment)
    environment[
        "SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID"
    ] = target_run_id
    try:
        validate_fast_paper_authoritative_cutover_environment(
            environment,
            target_manifest,
            authoritative_database_path=(
                source.config.execution_config.database_path
            ),
        )
    except Exception as exc:
        raise FastPaperReleaseUpgradeError(
            "target authoritative environment is incompatible"
        ) from exc

    # The release handoff enforces exact trading semantics. Re-check the
    # binary digests here before source PAPER is stopped so obvious target
    # incompatibility fails without service control.
    if (
        target_manifest.decision_binary_sha256
        != source.manifest.decision_binary_sha256
        or target_manifest.feature_feed_binary_sha256
        != source.manifest.feature_feed_binary_sha256
        or target_manifest.champion_fingerprint_sha256
        != source.manifest.champion_fingerprint_sha256
        or target_manifest.action_policy != source.manifest.action_policy
    ):
        raise FastPaperReleaseUpgradeError(
            "target release changes Fast trading semantics"
        )
    if proof_manifest.source_sha != identity.source_sha:
        raise FastPaperReleaseUpgradeError(
            "target proof-tool release identity changed"
        )
    if runtime_manifest.source_sha != identity.source_sha:
        raise FastPaperReleaseUpgradeError(
            "target runtime-tool release identity changed"
        )

    return _TargetContext(
        release=release,
        identity=identity,
        manifest=target_manifest,
        execution_policy=target_execution,
        buy_writer_policy=target_buy,
        environment=environment,
        fast_run_id=target_run_id,
        unit_payload=unit_payload,
        commissioning_fingerprint_sha256=commissioning_fingerprint,
    )


def _target_control_payloads(
    target: _TargetContext,
    handoff: FastPaperAuthoritativeReleaseHandoffResult,
    authorization: Mapping[str, object],
) -> dict[str, bytes]:
    directory = Path(tempfile.mkdtemp(prefix=".fast-release-controls-"))
    try:
        manifest_path = directory / "manifest.json"
        execution_path = directory / "execution.json"
        buy_path = directory / "buy.json"
        decision_path = directory / "decision.json"
        write_fast_paper_runtime_manifest(target.manifest, manifest_path)
        write_fast_paper_shadow_execution_policy(
            target.execution_policy,
            execution_path,
        )
        write_fast_paper_shadow_buy_writer_policy(
            target.buy_writer_policy,
            buy_path,
        )
        write_fast_paper_runtime_state(
            handoff.decision_state,
            decision_path,
        )
        return {
            "manifest": manifest_path.read_bytes(),
            "execution": execution_path.read_bytes(),
            "buy": buy_path.read_bytes(),
            "decision": decision_path.read_bytes(),
            "environment": (
                encode_fast_paper_authoritative_cutover_environment(
                    target.environment
                ).encode("utf-8")
            ),
            "authorization": (
                encode_fast_paper_cutover_authorization(
                    authorization
                ).encode("utf-8")
            ),
        }
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _install_target_controls(
    source: _SourceContext,
    target: _TargetContext,
    handoff: FastPaperAuthoritativeReleaseHandoffResult,
    payloads: Mapping[str, bytes],
    *,
    paths: FastPaperReleaseUpgradePaths,
) -> None:
    replacements = (
        (paths.runtime_manifest_path, payloads["manifest"]),
        (paths.execution_policy_path, payloads["execution"]),
        (paths.buy_writer_policy_path, payloads["buy"]),
        (
            source.config.decision_config.checkpoint_path,
            payloads["decision"],
        ),
        (paths.authoritative_env_path, payloads["environment"]),
    )
    _uid, service_gid = _service_identity()
    for path, payload in replacements:
        _before, metadata = _read_regular_no_follow(
            path,
            f"source control {path.name}",
        )
        _replace_file_atomically(
            path,
            payload,
            uid=metadata.st_uid,
            gid=metadata.st_gid,
            mode=stat.S_IMODE(metadata.st_mode),
        )

    # Authenticate the complete target control set before any release switch.
    manifest = read_fast_paper_runtime_manifest(
        paths.runtime_manifest_path
    )
    if manifest != target.manifest:
        raise FastPaperReleaseUpgradeError(
            "installed target manifest readback mismatch"
        )
    execution = read_fast_paper_shadow_execution_policy(
        manifest,
        paths.execution_policy_path,
    )
    if execution != target.execution_policy:
        raise FastPaperReleaseUpgradeError(
            "installed target execution policy readback mismatch"
        )
    buy = read_fast_paper_shadow_buy_writer_policy(
        paths.buy_writer_policy_path
    )
    if buy != target.buy_writer_policy:
        raise FastPaperReleaseUpgradeError(
            "installed target BUY writer policy readback mismatch"
        )
    verify_fast_paper_shadow_buy_writer_policy_bindings(
        manifest,
        source.service_policy,
        buy,
    )
    decision = read_fast_paper_runtime_state(
        source.config.decision_config.checkpoint_path
    )
    if decision != handoff.decision_state:
        raise FastPaperReleaseUpgradeError(
            "installed target decision state readback mismatch"
        )


def _install_target_units(
    target: _TargetContext,
    *,
    paths: FastPaperReleaseUpgradePaths,
) -> None:
    payloads = {
        _OBSERVE: (
            target.release
            / "deploy"
            / "systemd"
            / _OBSERVE
        ).read_bytes(),
        _EVIDENCE: (
            target.release
            / "deploy"
            / "systemd"
            / _EVIDENCE
        ).read_bytes(),
        _TARGET: (
            target.release
            / "deploy"
            / "systemd"
            / _TARGET
        ).read_bytes(),
        _UNIT: target.unit_payload,
    }
    for name, payload in payloads.items():
        _replace_file_atomically(
            paths.systemd_dir / name,
            payload,
            uid=0,
            gid=0,
            mode=0o644,
        )


def _capture_backup(
    source: _SourceContext,
    paths: FastPaperReleaseUpgradePaths,
) -> _Backup:
    control_paths = (
        paths.runtime_manifest_path,
        paths.execution_policy_path,
        paths.buy_writer_policy_path,
        source.config.decision_config.checkpoint_path,
        paths.authoritative_env_path,
    )
    payloads: dict[Path, bytes] = {}
    stats: dict[Path, os.stat_result] = {}
    for path in control_paths:
        payload, metadata = _read_regular_no_follow(
            path,
            f"source upgrade backup {path.name}",
        )
        payloads[path] = payload
        stats[path] = metadata
    units: dict[Path, bytes] = {}
    for name in (_OBSERVE, _EVIDENCE, _TARGET, _UNIT):
        path = paths.systemd_dir / name
        payload, _metadata = _read_regular_no_follow(
            path,
            f"source systemd unit {name}",
        )
        units[path] = payload
    authorization_payload, authorization_stat = _read_regular_no_follow(
        paths.authorization_path,
        "source Fast PAPER authorization",
    )
    return _Backup(
        current_release=source.release,
        control_payloads=payloads,
        control_stats=stats,
        unit_payloads=units,
        authorization_payload=authorization_payload,
        authorization_stat=authorization_stat,
    )


def _restore_source_before_target_start(
    source: _SourceContext,
    backup: _Backup,
    *,
    paths: FastPaperReleaseUpgradePaths,
    runner: CommandRunner,
    sleeper: Sleeper,
) -> None:
    _stop_all_runtime_best_effort(runner)
    for path, payload in backup.control_payloads.items():
        metadata = backup.control_stats[path]
        _replace_file_atomically(
            path,
            payload,
            uid=metadata.st_uid,
            gid=metadata.st_gid,
            mode=stat.S_IMODE(metadata.st_mode),
        )
    for path, payload in backup.unit_payloads.items():
        _replace_file_atomically(
            path,
            payload,
            uid=0,
            gid=0,
            mode=0o644,
        )
    _atomic_switch(paths.current_link, backup.current_release)
    _run(runner, ("systemctl", "daemon-reload"), "rollback daemon-reload")
    _replace_file_atomically(
        paths.authorization_path,
        backup.authorization_payload,
        uid=backup.authorization_stat.st_uid,
        gid=backup.authorization_stat.st_gid,
        mode=stat.S_IMODE(backup.authorization_stat.st_mode),
    )
    _run(runner, ("systemctl", "start", _TARGET), "restart source Fast release")
    running = _wait_running(runner, timeout_seconds=30, sleeper=sleeper)
    _verify_fast_process(paths, backup.current_release, running)


def _replace_authorization_with_upgrade_marker(
    path: Path,
    *,
    source_release_sha: str,
    target_release_sha: str,
    source_fast_run_id: str,
    target_fast_run_id: str,
) -> None:
    payload, metadata = _read_regular_no_follow(
        path,
        "Fast PAPER cutover authorization",
    )
    if not payload:
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER authorization is empty"
        )
    material = {
        "schema_name": "shreks.fast_paper_release_upgrade_guard",
        "schema_version": 1,
        "state": "UPGRADE_IN_PROGRESS",
        "source_release_source_sha": source_release_sha,
        "target_release_source_sha": target_release_sha,
        "source_fast_run_id": source_fast_run_id,
        "target_fast_run_id": target_fast_run_id,
        "production_paper_cutover": "PAUSED_FOR_RELEASE_UPGRADE",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    document = {
        **material,
        "guard_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }
    _replace_file_atomically(
        path,
        (_canonical(document) + "\n").encode("utf-8"),
        uid=metadata.st_uid,
        gid=metadata.st_gid,
        mode=stat.S_IMODE(metadata.st_mode),
    )


def _verify_staged_release(release: Path) -> _ReleaseIdentity:
    if release.is_symlink() or not release.is_dir():
        raise FastPaperReleaseUpgradeError(
            "target release must be an existing regular directory"
        )
    manifest_path = release / "RELEASE_MANIFEST.json"
    payload, _ = _read_regular_no_follow(
        manifest_path,
        "release manifest",
    )
    try:
        raw = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise FastPaperReleaseUpgradeError(
            "release manifest is malformed"
        ) from exc
    if (
        not isinstance(raw, dict)
        or set(raw) != {"files", "platform", "schema_version", "source_sha"}
        or raw["schema_version"] != _RELEASE_MANIFEST_SCHEMA
        or not isinstance(raw["source_sha"], str)
        or _SOURCE_SHA_RE.fullmatch(raw["source_sha"]) is None
        or raw["platform"] not in _SUPPORTED_PLATFORMS
        or not isinstance(raw["files"], list)
    ):
        raise FastPaperReleaseUpgradeError(
            "release manifest identity is incompatible"
        )
    if payload != (_canonical(raw) + "\n").encode("utf-8"):
        raise FastPaperReleaseUpgradeError(
            "release manifest must use canonical JSON"
        )
    expected: dict[str, tuple[int, str]] = {}
    for value in raw["files"]:
        if (
            not isinstance(value, dict)
            or set(value) != {"path", "sha256", "size"}
            or not isinstance(value["path"], str)
            or not value["path"]
            or value["path"].startswith("/")
            or ".." in Path(value["path"]).parts
            or isinstance(value["size"], bool)
            or not isinstance(value["size"], int)
            or value["size"] < 0
            or not isinstance(value["sha256"], str)
            or _SHA256_RE.fullmatch(value["sha256"]) is None
            or value["path"] in expected
        ):
            raise FastPaperReleaseUpgradeError(
                "release manifest file entry is invalid"
            )
        expected[value["path"]] = (value["size"], value["sha256"])
    if not _REQUIRED_RELEASE_PATHS.issubset(expected):
        raise FastPaperReleaseUpgradeError(
            "release manifest is missing required runtime payloads"
        )
    wheels = tuple(
        name
        for name in expected
        if name.startswith("wheelhouse/")
        and name.endswith(".whl")
    )
    if len(wheels) != 1:
        raise FastPaperReleaseUpgradeError(
            "release manifest must contain exactly one Shreks wheel"
        )
    for relative, (size, digest) in expected.items():
        path = release / relative
        if path.is_symlink() or not path.is_file():
            raise FastPaperReleaseUpgradeError(
                f"release payload is unavailable: {relative}"
            )
        if path.stat().st_size != size or _sha256_file(path) != digest:
            raise FastPaperReleaseUpgradeError(
                f"release payload fingerprint mismatch: {relative}"
            )
    if release.name != raw["source_sha"]:
        raise FastPaperReleaseUpgradeError(
            "release directory name does not match source SHA"
        )
    python = release / ".venv" / "bin" / "python"
    if python.is_symlink() or not python.is_file():
        raise FastPaperReleaseUpgradeError(
            "staged release virtualenv is unavailable"
        )
    return _ReleaseIdentity(
        source_sha=raw["source_sha"],
        platform=raw["platform"],
        wheel_path=release / wheels[0],
    )


def _require_target_tool_root(root: Path) -> None:
    if root.is_symlink():
        raise FastPaperReleaseUpgradeError(
            "target Fast tool root must not be a symlink"
        )
    root.mkdir(parents=True, mode=0o755, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise FastPaperReleaseUpgradeError(
            "target Fast tool root must be a real directory"
        )
    os.chmod(root, 0o755)


def _materialize_target_wheel_binary(
    wheel: Path,
    member: str,
    destination: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> Path:
    try:
        with zipfile.ZipFile(wheel) as archive:
            payload = archive.read(member)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise FastPaperReleaseUpgradeError(
            "sealed target Fast binary cannot be read"
        ) from exc
    if (
        len(payload) != expected_size
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise FastPaperReleaseUpgradeError(
            "sealed target Fast binary fingerprint mismatch"
        )
    if destination.is_symlink():
        raise FastPaperReleaseUpgradeError(
            "target Fast binary destination must not be a symlink"
        )
    if destination.exists():
        if (
            not destination.is_file()
            or destination.read_bytes() != payload
        ):
            raise FastPaperReleaseUpgradeError(
                "existing target Fast binary differs from sealed release"
            )
        os.chmod(destination, 0o755)
        return destination.resolve(strict=True)

    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o755,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(destination, 0o755)
        _fsync_directory(destination.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return destination.resolve(strict=True)


def _target_path_for_same_asset(
    source: Path,
    source_release: Path,
    target_release: Path,
    *,
    expected_sha256: str,
) -> Path:
    try:
        source_resolved = source.resolve(strict=True)
        source_release_resolved = source_release.resolve(strict=True)
    except OSError as exc:
        raise FastPaperReleaseUpgradeError(
            "source release-bound asset cannot be resolved"
        ) from exc
    if (
        source_resolved == source_release_resolved
        or source_release_resolved not in source_resolved.parents
    ):
        if _sha256_file(source_resolved) != expected_sha256:
            raise FastPaperReleaseUpgradeError(
                "persistent source asset fingerprint changed"
            )
        return source_resolved
    relative = source_resolved.relative_to(source_release_resolved)
    target = target_release / relative
    if (
        target.is_symlink()
        or not target.is_file()
        or _sha256_file(target) != expected_sha256
    ):
        raise FastPaperReleaseUpgradeError(
            "target release does not preserve release-local asset"
        )
    return target.resolve(strict=True)


def _fresh_target_run_id(
    database_path: str | Path,
    target_source_sha: str,
) -> str:
    import sqlite3

    base = f"fast-release-{target_source_sha}"
    database = Path(database_path)
    if database.is_symlink() or not database.is_file():
        raise FastPaperReleaseUpgradeError(
            "authoritative database is unavailable for target run selection"
        )
    try:
        connection = sqlite3.connect(
            f"file:{database}?mode=ro",
            uri=True,
            timeout=1.0,
        )
    except sqlite3.Error as exc:
        raise FastPaperReleaseUpgradeError(
            "authoritative database cannot be opened for target run selection"
        ) from exc
    try:
        for ordinal in range(1, 10_000):
            candidate = base if ordinal == 1 else f"{base}.{ordinal}"
            occupied = False
            for table, column in (
                ("fast_paper_authoritative_bindings", "fast_run_id"),
                ("paper_loop_checkpoints", "run_id"),
                (
                    "fast_paper_authoritative_runtime_states",
                    "fast_run_id",
                ),
                (
                    "fast_paper_authoritative_release_handoffs",
                    "target_run_id",
                ),
            ):
                try:
                    row = connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",
                        (candidate,),
                    ).fetchone()
                except sqlite3.OperationalError as exc:
                    if "no such table" in str(exc).lower():
                        continue
                    raise
                if row is None or row[0] != 0:
                    occupied = True
                    break
            if not occupied:
                return candidate
    except sqlite3.Error as exc:
        raise FastPaperReleaseUpgradeError(
            "target Fast run namespace selection failed"
        ) from exc
    finally:
        connection.close()
    raise FastPaperReleaseUpgradeError(
        "no fresh Fast release run namespace is available"
    )


def _require_current_release(current: Path) -> Path:
    if not current.is_symlink():
        raise FastPaperReleaseUpgradeError(
            "current release must be a symlink"
        )
    try:
        release = current.resolve(strict=True)
    except OSError as exc:
        raise FastPaperReleaseUpgradeError(
            "current release symlink cannot be resolved"
        ) from exc
    if not release.is_dir():
        raise FastPaperReleaseUpgradeError(
            "current release target must be a directory"
        )
    return release


def _atomic_switch(current: Path, release: Path) -> None:
    temporary = current.parent / (
        f".{current.name}.fast-upgrade-{os.getpid()}-{uuid.uuid4().hex}"
    )
    try:
        temporary.symlink_to(release)
        os.replace(temporary, current)
        _fsync_directory(current.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_fast_process(
    paths: FastPaperReleaseUpgradePaths,
    release: Path,
    state,
) -> None:
    if state.fragment_path != str(paths.campaign_unit):
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER FragmentPath is not exact"
        )
    if (
        state.working_directory != "/opt/shreks/current"
        or state.user != "shreks"
        or state.group != "shreks"
        or state.private_network.lower() not in ("yes", "true")
    ):
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER systemd identity is incompatible"
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
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER process provenance is unavailable"
        ) from exc
    expected_python = str(
        paths.current_link / ".venv" / "bin" / "python"
    )
    if (
        cwd != release
        or len(args) < 3
        or args[0] != expected_python
        or args[1] != "-m"
        or args[2] != _FAST_MODULE
    ):
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER process does not match authoritative release runtime"
        )


def _wait_running(
    runner: CommandRunner,
    *,
    timeout_seconds: int,
    sleeper: Sleeper,
):
    last = _read_systemd_state(runner)
    for index in range(max(1, timeout_seconds)):
        try:
            _require_running(last, "Fast PAPER service")
            return last
        except FastPaperPhysicalCutoverError:
            if index + 1 >= max(1, timeout_seconds):
                break
            sleeper(1.0)
            last = _read_systemd_state(runner)
    raise FastPaperReleaseUpgradeError(
        "target Fast PAPER service did not become healthy"
    )


def _stop_non_paper_runtime(runner: CommandRunner) -> None:
    for name in (_EVIDENCE, _OBSERVE, _TARGET):
        _run(runner, ("systemctl", "stop", name), f"stop {name}")


def _stop_all_runtime_best_effort(runner: CommandRunner) -> None:
    for name in (_UNIT, _EVIDENCE, _OBSERVE, _TARGET):
        try:
            runner(("systemctl", "stop", name))
        except Exception:
            pass


def _require_other_services_active(runner: CommandRunner) -> None:
    for name in (_OBSERVE, _EVIDENCE, _TARGET):
        _run(
            runner,
            ("systemctl", "is-active", "--quiet", name),
            f"verify {name}",
        )


def _run(
    runner: CommandRunner,
    command: tuple[str, ...],
    label: str,
) -> HostCommandResult:
    result = runner(command)
    if result.returncode != 0 or result.stderr.strip():
        raise FastPaperReleaseUpgradeError(f"{label} failed")
    return result


def _default_command_runner(
    command: tuple[str, ...],
) -> HostCommandResult:
    allowed = (
        command == _SHOW_COMMAND
        or command
        in tuple(
            ("systemctl", "stop", value)
            for value in (_UNIT, _EVIDENCE, _OBSERVE, _TARGET)
        )
        or command == ("systemctl", "start", _TARGET)
        or command == ("systemctl", "daemon-reload")
        or command
        in tuple(
            ("systemctl", "is-active", "--quiet", value)
            for value in (_OBSERVE, _EVIDENCE, _TARGET)
        )
        or (
            len(command) == 8
            and command[:3] == ("journalctl", "-u", _UNIT)
            and command[3] == "--since"
            and command[5:] == ("--no-pager", "-o", "cat")
        )
    )
    if not allowed:
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release host command is outside the allowlist"
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
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release host command invocation failed"
        ) from exc
    return HostCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _require_no_receipt(
    paths: FastPaperReleaseUpgradePaths,
    target_source_sha: str,
) -> None:
    paths.receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(paths.receipt_root, 0o700)
    for path in (
        paths.success_receipt_for(target_source_sha),
        paths.failure_receipt_for(target_source_sha),
    ):
        if path.exists() or path.is_symlink():
            raise FastPaperReleaseUpgradeError(
                "Fast PAPER release upgrade receipt already exists"
            )


def _observation_seconds(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not _MIN_OBSERVATION_SECONDS
        <= value
        <= _MAX_OBSERVATION_SECONDS
    ):
        raise FastPaperReleaseUpgradeError(
            "observation seconds must be an integer from 5 through 900"
        )
    return value


def _clock_value(clock: Clock) -> int:
    try:
        value = clock()
    except Exception as exc:
        raise FastPaperReleaseUpgradeError(
            "release upgrade clock failed"
        ) from exc
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise FastPaperReleaseUpgradeError(
            "release upgrade clock must return non-negative integer"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release upgrade requires root"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise FastPaperReleaseUpgradeError(
            "file changed while being fingerprinted"
        )
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _production_paths() -> FastPaperReleaseUpgradePaths:
    return FastPaperReleaseUpgradePaths(
        releases_dir=Path("/opt/shreks/releases"),
        current_link=Path("/opt/shreks/current"),
        systemd_dir=Path("/etc/systemd/system"),
        authoritative_env_path=Path(
            "/etc/shreks/fast-paper-authoritative.env"
        ),
        runtime_manifest_path=Path(
            "/etc/shreks/fast-paper-runtime-manifest.json"
        ),
        service_policy_path=Path(
            "/etc/shreks/fast-paper-shadow-service-policy.json"
        ),
        execution_policy_path=Path(
            "/etc/shreks/fast-paper-shadow-execution-policy.json"
        ),
        buy_writer_policy_path=Path(
            "/etc/shreks/fast-paper-shadow-buy-writer-policy.json"
        ),
        authorization_path=Path(
            "/etc/shreks/fast-paper-cutover-authorization.json"
        ),
        receipt_root=Path("/root/shreks-fast-paper-release-upgrade"),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Protected Fast PAPER immutable release upgrade"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "activate-staged"):
        command = commands.add_parser(name)
        command.add_argument("target_release", type=Path)
        if name == "activate-staged":
            command.add_argument(
                "--observe-seconds",
                type=int,
                default=5,
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = _production_paths()
    try:
        if args.command == "preflight":
            receipt = preflight_fast_paper_release_upgrade(
                args.target_release,
                paths=paths,
                runtime_executable=sys.executable,
            )
        else:
            receipt = activate_fast_paper_release_upgrade(
                args.target_release,
                paths=paths,
                runtime_executable=sys.executable,
                observation_seconds=args.observe_seconds,
            )
    except (
        FastPaperReleaseUpgradeError,
        FastPaperPhysicalCutoverError,
    ) as exc:
        print(
            _canonical(
                {
                    "schema_name": _FAILURE_SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "state": "FAILED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                    "error_type": type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(_canonical(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
