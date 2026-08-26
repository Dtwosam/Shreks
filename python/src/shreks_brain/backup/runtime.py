from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import json
import os
from pathlib import Path
import shutil
import time

from .config import BackupRuntimeConfig, BackupRuntimeConfigError, load_backup_runtime_config
from .models import BackupManifest, BackupManifestError
from .restore import BackupRestoreError, BackupRestoreResult, restore_backup_bundle
from .snapshot import BackupSnapshotError, BackupSnapshotSources, create_backup_snapshot
from .verify import verify_backup_bundle


class BackupRuntimeError(RuntimeError):
    """Raised when a G8 backup runtime command cannot complete safely."""


StatusSink = Callable[[str], None]


def run_backup_command(
    config: BackupRuntimeConfig,
    *,
    created_at_unix_ms: int | None = None,
    status_sink: StatusSink = print,
) -> Path:
    if type(config) is not BackupRuntimeConfig:
        raise BackupRuntimeError("backup runtime configuration is invalid")
    created_at = _created_at(created_at_unix_ms)
    sources = BackupSnapshotSources(
        operational_database_path=config.operational_database_path,
        e11_path=config.e11_path,
        campaign_manifest_path=config.campaign_manifest_path,
        risk_control_path=config.risk_control_path,
        alert_state_path=config.alert_state_path,
    )
    try:
        bundle = create_backup_snapshot(
            config.backup_root,
            sources,
            created_at_unix_ms=created_at,
            max_capture_attempts=config.max_capture_attempts,
        )
        manifest = verify_backup_bundle(bundle)
        prune_backup_retention(config.backup_root, config.retention_count)
    except (BackupManifestError, BackupSnapshotError, OSError, TypeError, ValueError) as error:
        raise BackupRuntimeError("backup command failed closed") from error

    _emit(
        status_sink,
        {
            "operation": "backup",
            "state": "COMPLETED",
            "paper_run_id": manifest.paper_run_id,
            "campaign_manifest_fingerprint_sha256": (
                manifest.campaign_manifest_fingerprint_sha256
            ),
            "created_at_unix_ms": manifest.created_at_unix_ms,
            "artifact_count": len(manifest.artifacts),
        },
    )
    return bundle


def run_verify_command(
    bundle_path: str | os.PathLike[str],
    *,
    status_sink: StatusSink = print,
) -> BackupManifest:
    try:
        manifest = verify_backup_bundle(bundle_path)
    except (BackupManifestError, OSError, TypeError, ValueError) as error:
        raise BackupRuntimeError("backup verification command failed") from error
    _emit(
        status_sink,
        {
            "operation": "verify",
            "state": "VERIFIED",
            "paper_run_id": manifest.paper_run_id,
            "campaign_manifest_fingerprint_sha256": (
                manifest.campaign_manifest_fingerprint_sha256
            ),
            "created_at_unix_ms": manifest.created_at_unix_ms,
            "artifact_count": len(manifest.artifacts),
        },
    )
    return manifest


def run_restore_command(
    bundle_path: str | os.PathLike[str],
    staging_path: str | os.PathLike[str],
    *,
    status_sink: StatusSink = print,
) -> BackupRestoreResult:
    try:
        result = restore_backup_bundle(bundle_path, staging_path)
    except (BackupRestoreError, OSError, TypeError, ValueError) as error:
        raise BackupRuntimeError("backup restore command failed closed") from error
    _emit(
        status_sink,
        {
            "operation": "restore",
            "state": "STAGED_VERIFIED",
            "paper_run_id": result.paper_run_id,
            "campaign_manifest_fingerprint_sha256": (
                result.campaign_manifest_fingerprint_sha256
            ),
            "checkpoint_sequence": result.checkpoint_sequence,
            "state_as_of_unix_ms": result.state_as_of_unix_ms,
            "artifact_count": len(result.verified_artifact_sha256),
        },
    )
    return result


def prune_backup_retention(
    backup_root: str | os.PathLike[str],
    retention_count: int,
) -> tuple[Path, ...]:
    if isinstance(retention_count, bool) or type(retention_count) is not int or retention_count < 1:
        raise BackupRuntimeError("retention count must be a positive integer")
    root = Path(backup_root)
    if root.is_symlink() or not root.is_dir():
        raise BackupRuntimeError("backup root must be a real directory for retention")

    verified: list[tuple[int, str, Path]] = []
    try:
        children = tuple(root.iterdir())
    except OSError as error:
        raise BackupRuntimeError("backup root could not be listed") from error
    for child in children:
        if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
            continue
        try:
            manifest = verify_backup_bundle(child)
        except (BackupManifestError, OSError, TypeError, ValueError):
            continue
        if not manifest.completed:
            continue
        verified.append((manifest.created_at_unix_ms, child.name, child))

    verified.sort(key=lambda item: (item[0], item[1]))
    if len(verified) <= retention_count:
        return ()
    delete_count = len(verified) - retention_count
    removable = verified[:delete_count]
    newest = verified[-1][2]
    removed: list[Path] = []
    for _created_at, _name, path in removable:
        if path == newest:
            continue
        try:
            path.relative_to(root)
        except ValueError as error:
            raise BackupRuntimeError("retention candidate escaped backup root") from error
        try:
            shutil.rmtree(path)
        except OSError as error:
            raise BackupRuntimeError("verified backup bundle could not be pruned") from error
        removed.append(path)
    return tuple(removed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shreks-backup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backup")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("bundle")
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("bundle")
    restore_parser.add_argument("staging")
    try:
        args = parser.parse_args(argv)
        if args.command == "backup":
            run_backup_command(load_backup_runtime_config())
        elif args.command == "verify":
            run_verify_command(args.bundle)
        elif args.command == "restore":
            run_restore_command(args.bundle, args.staging)
        else:
            raise BackupRuntimeError("unsupported backup command")
        return 0
    except (
        BackupRuntimeConfigError,
        BackupRuntimeError,
        BackupRestoreError,
        BackupSnapshotError,
        BackupManifestError,
        OSError,
        TypeError,
        ValueError,
    ):
        return 1


def _created_at(value: int | None) -> int:
    if value is None:
        return time.time_ns() // 1_000_000
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise BackupRuntimeError("backup creation timestamp is invalid")
    return value


def _emit(status_sink: StatusSink, payload: dict[str, object]) -> None:
    if not callable(status_sink):
        raise BackupRuntimeError("status sink must be callable")
    status_sink(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


if __name__ == "__main__":
    raise SystemExit(main())
