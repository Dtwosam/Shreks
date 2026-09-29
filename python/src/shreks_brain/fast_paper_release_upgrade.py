from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable
import uuid

from .fast_paper_authoritative_cutover_config import (
    encode_fast_paper_authoritative_cutover_environment,
    read_fast_paper_authoritative_cutover_environment,
    validate_fast_paper_authoritative_cutover_environment,
)
from .fast_paper_physical_cutover import (
    FastPaperPhysicalCutoverPaths,
    HostCommandResult,
    _candidate_unit_from_wheel,
    _read_authoritative_statuses,
    _read_regular_no_follow,
    _read_systemd_state,
    _replace_file_atomically,
    _require_running,
    _require_status_advancement,
    _service_identity,
    _verify_process,
)
from .fast_paper_production_authorization import (
    authorization_fingerprint,
    read_and_verify_fast_paper_production_authorization,
)
from .fast_paper_release_authorization import (
    build_fast_paper_release_authorization,
    encode_fast_paper_release_authorization,
)
from .fast_paper_runtime.authoritative_release_handoff import (
    initialize_fast_paper_authoritative_release_handoff,
)
from .fast_paper_runtime.authoritative_runtime import (
    bootstrap_fast_paper_authoritative_runtime,
)
from .fast_paper_runtime.codec import (
    build_fast_paper_runtime_manifest,
    write_fast_paper_runtime_manifest,
    write_fast_paper_runtime_state,
)
from .fast_paper_runtime.shadow_buy_writer_policy import (
    build_fast_paper_shadow_buy_writer_policy,
    verify_fast_paper_shadow_buy_writer_policy_bindings,
    write_fast_paper_shadow_buy_writer_policy,
)
from .fast_paper_runtime.shadow_execution_input import (
    build_fast_paper_shadow_execution_policy,
    write_fast_paper_shadow_execution_policy,
)


_SCHEMA_VERSION = 1
_UNIT = "shreks-paper-campaign.service"
_OBSERVE_UNIT = "shreks-observe.service"
_EVIDENCE_UNIT = "shreks-paper-evidence.service"
_TARGET = "shreks.target"
_RUNTIME_UNITS = (_OBSERVE_UNIT, _EVIDENCE_UNIT, _UNIT, _TARGET)
_NATIVE_EXECUTABLES = {
    _OBSERVE_UNIT: "target/release/shreks-observe",
    _EVIDENCE_UNIT: "target/release/shreks-paper-evidence",
}
_FAST_MODULE = "shreks_brain.fast_paper_runtime.authoritative_runtime"
_MIN_OBSERVATION_SECONDS = 5
_MAX_OBSERVATION_SECONDS = 900


class FastPaperReleaseUpgradeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperReleaseUpgradePaths:
    current_link: Path
    systemd_dir: Path
    authoritative_config_path: Path
    history_root: Path
    receipt_root: Path
    proc_root: Path = Path("/proc")

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "systemd_dir",
            "authoritative_config_path",
            "history_root",
            "receipt_root",
            "proc_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise ValueError(f"{name} must be an absolute Path")

    @property
    def active_unit(self) -> Path:
        return self.systemd_dir / _UNIT


@dataclass(frozen=True, slots=True)
class ProtectedFileSnapshot:
    path: Path
    payload: bytes
    uid: int
    gid: int
    mode: int


@dataclass(frozen=True, slots=True)
class ArchivedMember:
    source: Path
    archive: Path


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]
Sleeper = Callable[[float], object]
Clock = Callable[[], int]


def activate_fast_paper_release(
    *,
    target_release_dir: str | Path,
    target_fast_run_id: str,
    release_platform: str,
    observation_seconds: int,
    paths: FastPaperReleaseUpgradePaths,
    command_runner: CommandRunner | None = None,
    sleeper: Sleeper | None = None,
    clock_unix_ms: Clock | None = None,
) -> dict[str, object]:
    _require_root()
    duration = _observation_seconds(observation_seconds)
    target_release = _require_target_release(
        Path(target_release_dir),
        paths,
    )
    source_release = _require_current_release(paths)
    if source_release == target_release:
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER target release must differ from current release"
        )
    runner = _default_command_runner if command_runner is None else command_runner
    sleep = time.sleep if sleeper is None else sleeper
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms

    source_config, source_bootstrap, source_env = _source_runtime(
        paths.authoritative_config_path
    )
    source_manifest = source_bootstrap.decision_bootstrap.manifest
    if source_manifest.release_source_sha != source_release.name:
        raise FastPaperReleaseUpgradeError(
            "source Fast PAPER manifest does not match active release"
        )
    source_authorization = (
        read_and_verify_fast_paper_production_authorization(
            source_config.cutover_authorization_path,
            manifest=source_manifest,
            binding=source_bootstrap.execution_bootstrap.binding,
            execution_policy=(
                source_bootstrap.execution_bootstrap.execution_policy
            ),
        )
    )
    source_authorization_fp = authorization_fingerprint(
        source_authorization
    )

    source_wheel = _find_release_wheel(source_release)
    source_candidate, _ = _candidate_unit_from_wheel(
        source_wheel,
        expected_sha=source_release.name,
        platform=release_platform,
    )
    active_unit_payload, _active_unit_stat = _read_regular_no_follow(
        paths.active_unit,
        "active Fast PAPER unit",
    )
    if active_unit_payload != source_candidate:
        raise FastPaperReleaseUpgradeError(
            "active PAPER unit is not the sealed Fast unit for current release"
        )

    target_wheel = _find_release_wheel(target_release)
    target_candidate, target_commissioning_fp = _candidate_unit_from_wheel(
        target_wheel,
        expected_sha=target_release.name,
        platform=release_platform,
    )
    (
        target_manifest,
        target_execution_policy,
        target_buy_writer_policy,
    ) = _build_target_authorities(
        source_bootstrap,
        source_release=source_release,
        target_release=target_release,
    )
    verify_fast_paper_shadow_buy_writer_policy_bindings(
        target_manifest,
        source_bootstrap.decision_bootstrap.policy,
        target_buy_writer_policy,
    )

    state = _read_systemd_state(runner)
    _require_running(state, "authoritative Fast PAPER")
    physical_paths = FastPaperPhysicalCutoverPaths(
        current_link=paths.current_link,
        active_unit_destination=paths.active_unit,
        authoritative_config_path=paths.authoritative_config_path,
        cutover_authorization_path=source_config.cutover_authorization_path,
        commissioning_root=paths.receipt_root,
        proc_root=paths.proc_root,
    )
    _verify_process(
        physical_paths,
        source_release,
        state,
        expected_module=_FAST_MODULE,
    )

    _require_clean_handoff_boundary(source_bootstrap)
    target_history = paths.history_root / source_bootstrap.execution_bootstrap.binding.fast_run_id
    if target_history.exists() or target_history.is_symlink():
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER source-run history archive already exists"
        )
    receipt = paths.receipt_root / (
        f"release-upgrade-{source_release.name}-to-{target_release.name}.json"
    )
    failure_receipt = paths.receipt_root / (
        f"release-upgrade-failure-{source_release.name}-to-{target_release.name}.json"
    )
    for value in (receipt, failure_receipt):
        if value.exists() or value.is_symlink():
            raise FastPaperReleaseUpgradeError(
                "Fast PAPER release-upgrade receipt already exists"
            )

    protected = _snapshot_protected_files(
        paths,
        source_config,
    )
    current_units = _snapshot_units(paths)
    archived: tuple[ArchivedMember, ...] = ()
    target_start_attempted = False
    handoff_created = False
    artifacts_rotated = False
    current_switched = False

    try:
        _require_success(
            runner(("systemctl", "stop", _UNIT)),
            "source Fast PAPER stop",
        )
        stopped = _read_systemd_state(runner)
        if (
            stopped.active_state != "inactive"
            or stopped.sub_state != "dead"
            or stopped.main_pid != 0
        ):
            raise FastPaperReleaseUpgradeError(
                "source Fast PAPER did not stop cleanly"
            )

        source_config, source_bootstrap, source_env = _source_runtime(
            paths.authoritative_config_path
        )
        _require_clean_handoff_boundary(source_bootstrap)

        source_checkpoint = source_bootstrap.execution_bootstrap.checkpoint
        handoff_created_at_unix_ms = max(
            source_checkpoint.created_at_unix_ms,
            source_checkpoint.state_as_of_unix_ms,
        ) + 1
        handoff = initialize_fast_paper_authoritative_release_handoff(
            source_bootstrap.decision_bootstrap.manifest,
            target_manifest,
            source_bootstrap.execution_bootstrap.binding,
            target_execution_policy,
            source_bootstrap.decision_bootstrap.state,
            target_fast_run_id=target_fast_run_id,
            database_path=source_config.execution_config.database_path,
            created_at_unix_ms=handoff_created_at_unix_ms,
        )
        handoff_created = True

        archived = _archive_release_bound_sources(
            source_config,
            target_history,
        )

        target_env = dict(source_env)
        target_env[
            "SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID"
        ] = target_fast_run_id
        target_config = validate_fast_paper_authoritative_cutover_environment(
            target_env,
            target_manifest,
            authoritative_database_path=(
                source_config.execution_config.database_path
            ),
        )
        target_authorization = build_fast_paper_release_authorization(
            source_release_source_sha=source_release.name,
            source_authorization_fingerprint_sha256=source_authorization_fp,
            release_handoff_fingerprint_sha256=(
                handoff.handoff.handoff_fingerprint_sha256
            ),
            release_source_sha=target_manifest.release_source_sha,
            manifest_fingerprint_sha256=(
                target_manifest.manifest_fingerprint_sha256
            ),
            champion_version=target_manifest.champion_version,
            champion_fingerprint_sha256=(
                target_manifest.champion_fingerprint_sha256
            ),
            action_policy_version=target_manifest.action_policy.version,
            fast_run_id=target_fast_run_id,
            binding_fingerprint_sha256=(
                handoff.binding.binding_fingerprint_sha256
            ),
            execution_policy_fingerprint_sha256=(
                target_execution_policy.policy_fingerprint_sha256
            ),
            authorized_at_unix_ms=_clock_value(clock),
        )

        _stop_supporting_runtime(runner)
        _rotate_authorities(
            paths,
            source_config,
            target_env=target_env,
            target_manifest=target_manifest,
            target_execution_policy=target_execution_policy,
            target_buy_writer_policy=target_buy_writer_policy,
            target_decision_state=handoff.decision_state,
            target_authorization=target_authorization,
        )
        artifacts_rotated = True

        _install_target_units(
            paths,
            target_release,
            target_candidate,
        )
        _atomic_switch(paths.current_link, target_release)
        current_switched = True
        _require_success(
            runner(("systemctl", "daemon-reload")),
            "Fast PAPER release daemon reload",
        )
        target_start_attempted = True
        _require_success(
            runner(("systemctl", "start", _TARGET)),
            "Fast PAPER target release start",
        )
        _require_all_active(runner)

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

        running = _read_systemd_state(runner)
        _require_running(running, "target Fast PAPER")
        _verify_process(
            physical_paths,
            target_release,
            running,
            expected_module=_FAST_MODULE,
        )
        _verify_supporting_processes(
            paths,
            target_release,
            runner,
        )
        started_at = _clock_value(clock)
        sleep(float(duration))
        after = _read_systemd_state(runner)
        _require_running(after, "target Fast PAPER")
        if (
            after.main_pid != running.main_pid
            or after.invocation_id != running.invocation_id
            or after.n_restarts != running.n_restarts
        ):
            raise FastPaperReleaseUpgradeError(
                "target Fast PAPER process was not stable during observation"
            )
        statuses = _read_authoritative_statuses(
            runner,
            since_unix_ms=started_at,
        )
        _require_status_advancement(
            statuses,
            expected_manifest_fingerprint_sha256=(
                target_manifest.manifest_fingerprint_sha256
            ),
            expected_champion_fingerprint_sha256=(
                target_manifest.champion_fingerprint_sha256
            ),
        )

        material = {
            "schema_name": "shreks.fast_paper_release_upgrade",
            "schema_version": _SCHEMA_VERSION,
            "state": "FAST_PAPER_RELEASE_UPGRADE_ACTIVE",
            "source_release_source_sha": source_release.name,
            "target_release_source_sha": target_release.name,
            "source_fast_run_id": (
                source_bootstrap.execution_bootstrap.binding.fast_run_id
            ),
            "target_fast_run_id": target_fast_run_id,
            "release_handoff_fingerprint_sha256": (
                handoff.handoff.handoff_fingerprint_sha256
            ),
            "target_manifest_fingerprint_sha256": (
                target_manifest.manifest_fingerprint_sha256
            ),
            "target_binding_fingerprint_sha256": (
                handoff.binding.binding_fingerprint_sha256
            ),
            "target_execution_policy_fingerprint_sha256": (
                target_execution_policy.policy_fingerprint_sha256
            ),
            "target_authorization_fingerprint_sha256": (
                target_authorization[
                    "authorization_fingerprint_sha256"
                ]
            ),
            "target_commissioning_manifest_fingerprint_sha256": (
                target_commissioning_fp
            ),
            "archived_source_members": len(archived),
            "completed_cycles_start": statuses[0]["completed_cycles"],
            "completed_cycles_end": statuses[-1]["completed_cycles"],
            "production_paper_cutover": "ACTIVE",
            "production_paper_runtime": "FAST_LANE_LEARNED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
        result = _finalize(material)
        _write_receipt(receipt, result)
        return result
    except Exception as upgrade_error:
        try:
            _stop_all_runtime(runner)
        except Exception:
            pass
        if not target_start_attempted:
            _restore_pre_start(
                paths,
                protected=protected,
                units=current_units,
                archived=archived,
                source_release=source_release,
                runner=runner,
                current_switched=current_switched,
                artifacts_rotated=artifacts_rotated,
            )
            raise FastPaperReleaseUpgradeError(
                "Fast PAPER release upgrade failed before target start; source release restored"
            ) from upgrade_error

        _write_revoked_authorization(
            source_config.cutover_authorization_path,
            target_release_source_sha=target_release.name,
            target_fast_run_id=target_fast_run_id,
            handoff_fingerprint_sha256=(
                handoff.handoff.handoff_fingerprint_sha256
                if handoff_created
                else "0" * 64
            ),
            error=upgrade_error,
        )
        material = {
            "schema_name": "shreks.fast_paper_release_upgrade_failure",
            "schema_version": _SCHEMA_VERSION,
            "state": "MANUAL_RECOVERY_REQUIRED",
            "source_release_source_sha": source_release.name,
            "target_release_source_sha": target_release.name,
            "target_fast_run_id": target_fast_run_id,
            "target_start_attempted": True,
            "legacy_score_runtime_restored": False,
            "source_fast_runtime_restarted": False,
            "production_paper_cutover": "STOPPED_MANUAL_RECOVERY",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
            "error_type": type(upgrade_error).__name__,
        }
        _write_receipt(failure_receipt, _finalize(material))
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release upgrade failed after target start; all runtime authority remains stopped for manual recovery"
        ) from upgrade_error


def _source_runtime(path: Path):
    try:
        env = read_fast_paper_authoritative_cutover_environment(path)
        from .fast_paper_runtime.codec import read_fast_paper_runtime_manifest

        manifest = read_fast_paper_runtime_manifest(
            env["SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH"]
        )
        config = validate_fast_paper_authoritative_cutover_environment(
            env,
            manifest,
            authoritative_database_path=manifest.observer_database_path,
        )
        bootstrap = bootstrap_fast_paper_authoritative_runtime(config)
    except Exception as exc:
        raise FastPaperReleaseUpgradeError(
            "source Fast PAPER runtime authentication failed"
        ) from exc
    return config, bootstrap, env


def _build_target_authorities(
    source_bootstrap,
    *,
    source_release: Path,
    target_release: Path,
):
    source_manifest = source_bootstrap.decision_bootstrap.manifest
    target_manifest = build_fast_paper_runtime_manifest(
        release_source_sha=target_release.name,
        champion_path=_target_file(
            source_manifest.champion_path,
            source_release,
            target_release,
            allow_external=True,
        ),
        decision_binary_path=_target_file(
            source_manifest.decision_binary_path,
            source_release,
            target_release,
            allow_external=False,
        ),
        feature_feed_binary_path=_target_file(
            source_manifest.feature_feed_binary_path,
            source_release,
            target_release,
            allow_external=False,
        ),
        action_policy=source_manifest.action_policy,
        state_version=source_manifest.state_version,
        risk_policy_version=source_manifest.risk_policy_version,
        fill_policy_version=source_manifest.fill_policy_version,
        position_action_policy_version=(
            source_manifest.position_action_policy_version
        ),
        strategy_family=source_manifest.strategy_family,
        strategy_version=source_manifest.strategy_version,
        assessment_version=source_manifest.assessment_version,
        observer_database_path=source_manifest.observer_database_path,
        paper_evidence_path=source_manifest.paper_evidence_path,
        checkpoint_path=source_manifest.checkpoint_path,
        quote_provider=source_manifest.quote_provider,
        quote_mint=source_manifest.quote_mint,
        quote_decimals=source_manifest.quote_decimals,
        route_evidence_version=source_manifest.route_evidence_version,
    )
    source_execution = source_bootstrap.execution_bootstrap.execution_policy
    target_execution = build_fast_paper_shadow_execution_policy(
        target_manifest,
        risk_policy=source_execution.risk_policy,
        fill_policy=source_execution.fill_policy,
        position_action_policy=(
            source_execution.position_action_policy
        ),
    )
    source_buy = source_bootstrap.buy_writer_policy
    target_entry_binary = _target_file(
        source_buy.entry_authority_binary_path,
        source_release,
        target_release,
        allow_external=False,
    )
    target_buy = build_fast_paper_shadow_buy_writer_policy(
        market_read_policy=source_buy.market_read_policy,
        regime_read_policy=source_buy.regime_read_policy,
        regime_policy=source_buy.regime_policy,
        safety_policy=source_buy.safety_policy,
        safety_probe_identity=source_buy.safety_probe_identity,
        execution_economics_policies=(
            source_buy.execution_economics_policies
        ),
        operator_risk_control_path=source_buy.operator_risk_control_path,
        entry_authority_binary_path=target_entry_binary,
        entry_authority_binary_sha256=source_buy.entry_authority_binary_sha256,
        day_started_at_unix_ms=source_buy.day_started_at_unix_ms,
        data_healthy=source_buy.data_healthy,
        execution_healthy=source_buy.execution_healthy,
        global_risk_halt=source_buy.global_risk_halt,
    )
    return target_manifest, target_execution, target_buy


def _target_file(
    value: str | Path,
    source_release: Path,
    target_release: Path,
    *,
    allow_external: bool,
) -> Path:
    path = Path(value).expanduser()
    try:
        resolved = path.resolve(strict=True)
        source = source_release.resolve(strict=True)
    except OSError as exc:
        raise FastPaperReleaseUpgradeError(
            "source release-bound authority path cannot be resolved"
        ) from exc
    try:
        relative = resolved.relative_to(source)
    except ValueError:
        if allow_external:
            return resolved
        raise FastPaperReleaseUpgradeError(
            "release-local Fast authority path escaped current release"
        )
    target = target_release / relative
    if target.is_symlink() or not target.is_file():
        raise FastPaperReleaseUpgradeError(
            "target release is missing a required Fast authority file"
        )
    return target.resolve(strict=True)


def _require_clean_handoff_boundary(bootstrap) -> None:
    execution = bootstrap.execution_bootstrap
    decision_cursor = bootstrap.decision_bootstrap.state.cursor
    decision_sequence = (
        None
        if decision_cursor is None
        else decision_cursor.decision_sequence
    )
    execution_sequence = (
        execution.runtime_state.last_processed_source_sequence
    )
    if execution.checkpoint.state.pending_buy is not None:
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release upgrade requires pending BUY resolution"
        )
    if decision_sequence != execution_sequence:
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release upgrade requires equal decision/execution cursors"
        )


def _snapshot_protected_files(paths, config):
    values = (
        config.decision_config.manifest_path,
        config.execution_config.execution_policy_path,
        config.buy_writer_policy_path,
        config.decision_config.checkpoint_path,
        paths.authoritative_config_path,
        config.cutover_authorization_path,
    )
    result = []
    for value in values:
        if value is None:
            raise FastPaperReleaseUpgradeError(
                "required protected Fast PAPER path is missing"
            )
        path = Path(value)
        payload, metadata = _read_regular_no_follow(
            path,
            "protected Fast PAPER authority file",
        )
        result.append(
            ProtectedFileSnapshot(
                path=path,
                payload=payload,
                uid=metadata.st_uid,
                gid=metadata.st_gid,
                mode=stat.S_IMODE(metadata.st_mode),
            )
        )
    return tuple(result)


def _snapshot_units(paths):
    result = []
    for name in _RUNTIME_UNITS:
        path = paths.systemd_dir / name
        payload, metadata = _read_regular_no_follow(
            path,
            f"active systemd unit {name}",
        )
        result.append(
            ProtectedFileSnapshot(
                path=path,
                payload=payload,
                uid=metadata.st_uid,
                gid=metadata.st_gid,
                mode=stat.S_IMODE(metadata.st_mode),
            )
        )
    return tuple(result)


def _archive_release_bound_sources(config, archive_root: Path):
    roots = (
        ("decision", config.decision_config.evidence_directory),
        ("execution", config.execution_config.source_directory),
        ("buy", config.buy_authority_source_directory),
        ("quote_usd", config.quote_usd_source_directory),
        ("reduction", config.reduction_source_directory),
        ("retry", config.pending_buy_retry_source_directory),
    )
    archive_root.mkdir(parents=True, mode=0o700)
    os.chmod(archive_root, 0o700)
    members = []
    checkpoint = config.decision_config.checkpoint_path
    for name, root in roots:
        target = archive_root / name
        target.mkdir(mode=0o700)
        for child in sorted(root.iterdir()):
            if checkpoint is not None and child == checkpoint:
                continue
            if child.is_symlink() or not child.is_file():
                raise FastPaperReleaseUpgradeError(
                    "release-bound source root contains a non-regular member"
                )
            destination = target / child.name
            os.replace(child, destination)
            members.append(
                ArchivedMember(source=child, archive=destination)
            )
    return tuple(members)


def _rotate_authorities(
    paths,
    config,
    *,
    target_env,
    target_manifest,
    target_execution_policy,
    target_buy_writer_policy,
    target_decision_state,
    target_authorization,
):
    payloads = _materialize_authority_payloads(
        target_manifest,
        target_execution_policy,
        target_buy_writer_policy,
        target_decision_state,
    )
    replacements = {
        config.decision_config.manifest_path: payloads["manifest"],
        config.execution_config.execution_policy_path: payloads["execution"],
        config.buy_writer_policy_path: payloads["buy"],
        config.decision_config.checkpoint_path: payloads["decision"],
        paths.authoritative_config_path: (
            encode_fast_paper_authoritative_cutover_environment(
                target_env
            ).encode("utf-8")
        ),
        config.cutover_authorization_path: (
            encode_fast_paper_release_authorization(
                target_authorization
            ).encode("utf-8")
        ),
    }
    for path, payload in replacements.items():
        if path is None:
            raise FastPaperReleaseUpgradeError(
                "target protected authority path is missing"
            )
        _replace_preserving_metadata(Path(path), payload)


def _materialize_authority_payloads(
    manifest,
    execution_policy,
    buy_writer_policy,
    decision_state,
):
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        manifest_path = root / "manifest.json"
        execution_path = root / "execution.json"
        buy_path = root / "buy.json"
        decision_path = root / "decision.json"
        write_fast_paper_runtime_manifest(manifest, manifest_path)
        write_fast_paper_shadow_execution_policy(
            execution_policy,
            execution_path,
        )
        write_fast_paper_shadow_buy_writer_policy(
            buy_writer_policy,
            buy_path,
        )
        write_fast_paper_runtime_state(
            decision_state,
            decision_path,
        )
        return {
            "manifest": manifest_path.read_bytes(),
            "execution": execution_path.read_bytes(),
            "buy": buy_path.read_bytes(),
            "decision": decision_path.read_bytes(),
        }


def _replace_preserving_metadata(path: Path, payload: bytes) -> None:
    existing, metadata = _read_regular_no_follow(
        path,
        "protected Fast PAPER authority file",
    )
    del existing
    _replace_file_atomically(
        path,
        payload,
        uid=metadata.st_uid,
        gid=metadata.st_gid,
        mode=stat.S_IMODE(metadata.st_mode),
    )


def _install_target_units(paths, target_release, fast_unit):
    for name in (_OBSERVE_UNIT, _EVIDENCE_UNIT, _TARGET):
        source = target_release / "deploy" / "systemd" / name
        if source.is_symlink() or not source.is_file():
            raise FastPaperReleaseUpgradeError(
                f"target release systemd unit is missing: {name}"
            )
        _replace_file_atomically(
            paths.systemd_dir / name,
            source.read_bytes(),
            uid=0,
            gid=0,
            mode=0o644,
        )
    _replace_file_atomically(
        paths.active_unit,
        fast_unit,
        uid=0,
        gid=0,
        mode=0o644,
    )


def _atomic_switch(current_link: Path, target_release: Path) -> None:
    if not current_link.is_symlink():
        raise FastPaperReleaseUpgradeError(
            "current release must remain a symlink"
        )
    temporary = current_link.parent / (
        f".{current_link.name}.fast-upgrade-{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.symlink_to(target_release)
        os.replace(temporary, current_link)
    finally:
        temporary.unlink(missing_ok=True)


def _stop_all_runtime(runner: CommandRunner) -> None:
    _require_success(
        runner(
            (
                "systemctl",
                "stop",
                _UNIT,
                _EVIDENCE_UNIT,
                _OBSERVE_UNIT,
            )
        ),
        "runtime service stop",
    )
    _require_success(
        runner(("systemctl", "stop", _TARGET)),
        "runtime target stop",
    )


def _stop_supporting_runtime(runner: CommandRunner) -> None:
    _require_success(
        runner(("systemctl", "stop", _EVIDENCE_UNIT, _OBSERVE_UNIT)),
        "supporting runtime stop",
    )
    _require_success(
        runner(("systemctl", "stop", _TARGET)),
        "target stop",
    )


def _require_all_active(runner: CommandRunner) -> None:
    for unit in _RUNTIME_UNITS:
        _require_success(
            runner(("systemctl", "is-active", "--quiet", unit)),
            f"{unit} health check",
        )


def _verify_supporting_processes(
    paths,
    target_release,
    runner,
):
    for unit, relative in _NATIVE_EXECUTABLES.items():
        result = runner(
            (
                "systemctl",
                "show",
                unit,
                "--property=MainPID",
                "--no-pager",
            )
        )
        _require_success(result, f"{unit} process lookup")
        rows = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                rows[key] = value
        try:
            pid = int(rows["MainPID"])
        except (KeyError, ValueError) as exc:
            raise FastPaperReleaseUpgradeError(
                f"{unit} MainPID is invalid"
            ) from exc
        if pid <= 0:
            raise FastPaperReleaseUpgradeError(
                f"{unit} has no running process"
            )
        proc = paths.proc_root / str(pid)
        try:
            cwd = (proc / "cwd").resolve(strict=True)
            executable = (proc / "exe").resolve(strict=True)
        except OSError as exc:
            raise FastPaperReleaseUpgradeError(
                f"{unit} process provenance is unavailable"
            ) from exc
        if cwd != target_release.resolve(strict=True):
            raise FastPaperReleaseUpgradeError(
                f"{unit} cwd does not match target release"
            )
        if executable != (
            target_release / relative
        ).resolve(strict=True):
            raise FastPaperReleaseUpgradeError(
                f"{unit} executable does not match target release"
            )


def _restore_pre_start(
    paths,
    *,
    protected,
    units,
    archived,
    source_release,
    runner,
    current_switched,
    artifacts_rotated,
):
    del current_switched, artifacts_rotated
    for snapshot in protected:
        _replace_file_atomically(
            snapshot.path,
            snapshot.payload,
            uid=snapshot.uid,
            gid=snapshot.gid,
            mode=snapshot.mode,
        )
    for member in reversed(archived):
        member.source.parent.mkdir(parents=True, exist_ok=True)
        os.replace(member.archive, member.source)
    _remove_empty_archive(paths.history_root)
    for snapshot in units:
        _replace_file_atomically(
            snapshot.path,
            snapshot.payload,
            uid=snapshot.uid,
            gid=snapshot.gid,
            mode=snapshot.mode,
        )
    _atomic_switch(paths.current_link, source_release)
    _require_success(
        runner(("systemctl", "daemon-reload")),
        "source release rollback daemon reload",
    )
    _require_success(
        runner(("systemctl", "start", _TARGET)),
        "source release rollback start",
    )
    _require_all_active(runner)


def _remove_empty_archive(history_root: Path) -> None:
    if not history_root.exists() or history_root.is_symlink():
        return
    for path in sorted(
        history_root.rglob("*"),
        key=lambda value: len(value.parts),
        reverse=True,
    ):
        if path.is_dir() and not path.is_symlink():
            try:
                path.rmdir()
            except OSError:
                pass


def _write_revoked_authorization(
    path: Path,
    *,
    target_release_source_sha: str,
    target_fast_run_id: str,
    handoff_fingerprint_sha256: str,
    error: BaseException,
):
    material = {
        "schema_name": "shreks.fast_paper_release_authorization_revocation",
        "schema_version": 1,
        "state": "REVOKED_MANUAL_RECOVERY",
        "target_release_source_sha": target_release_source_sha,
        "target_fast_run_id": target_fast_run_id,
        "release_handoff_fingerprint_sha256": (
            handoff_fingerprint_sha256
        ),
        "production_paper_cutover": "STOPPED_MANUAL_RECOVERY",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
        "error_type": type(error).__name__,
    }
    document = _finalize(material)
    _replace_preserving_metadata(
        path,
        (_canonical(document) + "\n").encode("utf-8"),
    )


def _find_release_wheel(release: Path) -> Path:
    wheels = tuple(sorted((release / "wheelhouse").glob("*.whl")))
    if len(wheels) != 1:
        raise FastPaperReleaseUpgradeError(
            "release must contain exactly one wheel"
        )
    wheel = wheels[0]
    if wheel.is_symlink() or not wheel.is_file():
        raise FastPaperReleaseUpgradeError(
            "release wheel must be a regular non-symlink file"
        )
    return wheel


def _require_target_release(
    release: Path,
    paths: FastPaperReleaseUpgradePaths,
) -> Path:
    if release.is_symlink() or not release.is_dir():
        raise FastPaperReleaseUpgradeError(
            "target release must be an existing regular directory"
        )
    resolved = release.resolve(strict=True)
    if len(resolved.name) != 40 or any(
        ch not in "0123456789abcdef" for ch in resolved.name
    ):
        raise FastPaperReleaseUpgradeError(
            "target release directory name must be a source SHA"
        )
    current_parent = paths.current_link.parent / "releases"
    if current_parent.exists():
        try:
            if resolved.parent != current_parent.resolve(strict=True):
                raise FastPaperReleaseUpgradeError(
                    "target release is outside managed release directory"
                )
        except OSError as exc:
            raise FastPaperReleaseUpgradeError(
                "managed release directory cannot be resolved"
            ) from exc
    python = resolved / ".venv" / "bin" / "python"
    if python.is_symlink() or not python.is_file():
        raise FastPaperReleaseUpgradeError(
            "target release virtualenv is missing"
        )
    return resolved


def _require_current_release(paths):
    if not paths.current_link.is_symlink():
        raise FastPaperReleaseUpgradeError(
            "current release must be a symlink"
        )
    try:
        release = paths.current_link.resolve(strict=True)
    except OSError as exc:
        raise FastPaperReleaseUpgradeError(
            "current release cannot be resolved"
        ) from exc
    if len(release.name) != 40:
        raise FastPaperReleaseUpgradeError(
            "current release directory name is invalid"
        )
    return release


def _require_success(result: HostCommandResult, label: str) -> None:
    if result.returncode != 0 or result.stderr.strip():
        raise FastPaperReleaseUpgradeError(f"{label} failed")


def _default_command_runner(command: tuple[str, ...]) -> HostCommandResult:
    allowed = (
        command[0:2] == ("systemctl", "stop")
        and all(
            value in (_UNIT, _EVIDENCE_UNIT, _OBSERVE_UNIT, _TARGET)
            for value in command[2:]
        )
    ) or (
        command == ("systemctl", "start", _TARGET)
        or command == ("systemctl", "daemon-reload")
        or (
            len(command) == 4
            and command[:3] == ("systemctl", "is-active", "--quiet")
            and command[3] in _RUNTIME_UNITS
        )
        or (
            len(command) == 5
            and command[:2] == ("systemctl", "show")
            and command[2] in (_OBSERVE_UNIT, _EVIDENCE_UNIT)
            and command[3:] == ("--property=MainPID", "--no-pager")
        )
        or (
            len(command) == 5
            and command[:3] == ("systemctl", "show", _UNIT)
            and command[3].startswith("--property=")
            and command[4] == "--no-pager"
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
            "Fast PAPER release-upgrade host command is outside allowlist"
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
            "Fast PAPER release-upgrade host command failed"
        ) from exc
    return HostCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _write_receipt(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.exists() or path.is_symlink():
        raise FastPaperReleaseUpgradeError(
            "release-upgrade receipt already exists"
        )
    payload = (_canonical(document) + "\n").encode("utf-8")
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
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _finalize(material: dict[str, object]) -> dict[str, object]:
    return {
        **material,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


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
    value = clock()
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperReleaseUpgradeError(
            "release-upgrade clock must return non-negative integer unix-ms"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperReleaseUpgradeError(
            "Fast PAPER release upgrade requires root"
        )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _production_paths() -> FastPaperReleaseUpgradePaths:
    return FastPaperReleaseUpgradePaths(
        current_link=Path("/opt/shreks/current"),
        systemd_dir=Path("/etc/systemd/system"),
        authoritative_config_path=Path(
            "/etc/shreks/fast-paper-authoritative.env"
        ),
        history_root=Path(
            "/var/lib/shreks/fast-paper-authoritative/release-history"
        ),
        receipt_root=Path("/root/shreks-fast-paper-release-upgrades"),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-release-upgrade"
    )
    parser.add_argument("target_release_dir")
    parser.add_argument("target_fast_run_id")
    parser.add_argument("--release-platform", required=True)
    parser.add_argument("--observe-seconds", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(
        sys.argv[1:] if argv is None else argv
    )
    try:
        result = activate_fast_paper_release(
            target_release_dir=args.target_release_dir,
            target_fast_run_id=args.target_fast_run_id,
            release_platform=args.release_platform,
            observation_seconds=args.observe_seconds,
            paths=_production_paths(),
        )
    except Exception as exc:
        print(
            _canonical(
                {
                    "schema_name": "shreks.fast_paper_release_upgrade_failure",
                    "schema_version": _SCHEMA_VERSION,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "production_paper_cutover": "NOT_CONFIRMED",
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
