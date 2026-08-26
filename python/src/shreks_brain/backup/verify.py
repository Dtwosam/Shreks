from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3

from .manifest import decode_backup_manifest
from .models import BackupArtifactRole, BackupManifest, BackupManifestError


def verify_backup_bundle(bundle_path: str | os.PathLike[str]) -> BackupManifest:
    bundle = Path(bundle_path)
    if not bundle.is_dir() or bundle.is_symlink():
        raise BackupManifestError("backup bundle must be a real directory")

    manifest_path = bundle / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BackupManifestError("backup bundle manifest is missing or unsafe")
    try:
        manifest = decode_backup_manifest(manifest_path.read_bytes())
    except OSError as error:
        raise BackupManifestError("backup bundle manifest could not be read") from error

    expected_files = {"manifest.json"}
    for record in manifest.artifacts:
        artifact_path = bundle / record.relative_path
        _require_contained_regular_file(bundle, artifact_path)
        expected_files.add(record.relative_path)
        try:
            payload = artifact_path.read_bytes()
        except OSError as error:
            raise BackupManifestError("backup artifact could not be read") from error
        if len(payload) != record.byte_size:
            raise BackupManifestError("backup artifact byte-size mismatch")
        if hashlib.sha256(payload).hexdigest() != record.sha256:
            raise BackupManifestError("backup artifact checksum mismatch")

    actual_files: set[str] = set()
    for root, directories, files in os.walk(bundle, followlinks=False):
        root_path = Path(root)
        for directory in directories:
            candidate = root_path / directory
            if candidate.is_symlink():
                raise BackupManifestError("backup bundle contains a symlink")
        for filename in files:
            candidate = root_path / filename
            if candidate.is_symlink():
                raise BackupManifestError("backup bundle contains a symlink")
            try:
                relative = candidate.relative_to(bundle).as_posix()
            except ValueError as error:
                raise BackupManifestError("backup artifact escapes bundle root") from error
            actual_files.add(relative)
    if actual_files != expected_files:
        raise BackupManifestError("backup bundle contains missing or untracked files")

    sqlite_record = next(
        record
        for record in manifest.artifacts
        if record.role is BackupArtifactRole.OPERATIONAL_SQLITE
    )
    _verify_sqlite(bundle / sqlite_record.relative_path)
    return manifest


def _require_contained_regular_file(bundle: Path, artifact_path: Path) -> None:
    if artifact_path.is_symlink() or not artifact_path.is_file():
        raise BackupManifestError("backup artifact is missing or unsafe")
    try:
        bundle_resolved = bundle.resolve(strict=True)
        artifact_resolved = artifact_path.resolve(strict=True)
        artifact_resolved.relative_to(bundle_resolved)
    except (OSError, ValueError) as error:
        raise BackupManifestError("backup artifact escapes bundle root") from error


def _verify_sqlite(database_path: Path) -> None:
    try:
        connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise BackupManifestError("backup SQLite artifact could not be opened") from error
    try:
        row = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as error:
        raise BackupManifestError("backup SQLite integrity check failed") from error
    finally:
        connection.close()
    if row is None or row[0] != "ok":
        raise BackupManifestError("backup SQLite quick_check did not return ok")
