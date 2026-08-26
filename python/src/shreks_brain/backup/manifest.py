from __future__ import annotations

import json

from .models import (
    BACKUP_MANIFEST_SCHEMA_VERSION,
    BackupArtifactRecord,
    BackupArtifactRole,
    BackupManifest,
    BackupManifestError,
)


_MANIFEST_KEYS = {
    "schema_version",
    "created_at_unix_ms",
    "paper_run_id",
    "campaign_manifest_fingerprint_sha256",
    "sqlite_quick_check",
    "completed",
    "artifacts",
}
_ARTIFACT_KEYS = {"role", "relative_path", "sha256", "byte_size", "required"}


def encode_backup_manifest(manifest: BackupManifest) -> bytes:
    if type(manifest) is not BackupManifest:
        raise BackupManifestError("manifest must be an exact BackupManifest")
    document = {
        "schema_version": manifest.schema_version,
        "created_at_unix_ms": manifest.created_at_unix_ms,
        "paper_run_id": manifest.paper_run_id,
        "campaign_manifest_fingerprint_sha256": manifest.campaign_manifest_fingerprint_sha256,
        "sqlite_quick_check": manifest.sqlite_quick_check,
        "completed": manifest.completed,
        "artifacts": [
            {
                "role": record.role.value,
                "relative_path": record.relative_path,
                "sha256": record.sha256,
                "byte_size": record.byte_size,
                "required": record.required,
            }
            for record in manifest.artifacts
        ],
    }
    try:
        return json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise BackupManifestError("backup manifest cannot be canonicalized") from error


def decode_backup_manifest(payload: bytes | str) -> BackupManifest:
    raw = _payload_bytes(payload)
    try:
        document = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, BackupManifestError) as error:
        if isinstance(error, BackupManifestError):
            raise
        raise BackupManifestError("backup manifest is not valid UTF-8 JSON") from error

    if not isinstance(document, dict) or set(document) != _MANIFEST_KEYS:
        raise BackupManifestError("backup manifest field set is malformed")
    artifacts_value = document["artifacts"]
    if not isinstance(artifacts_value, list) or not artifacts_value:
        raise BackupManifestError("backup manifest artifacts must be a non-empty array")

    records: list[BackupArtifactRecord] = []
    for artifact in artifacts_value:
        if not isinstance(artifact, dict) or set(artifact) != _ARTIFACT_KEYS:
            raise BackupManifestError("backup artifact field set is malformed")
        try:
            role = BackupArtifactRole(artifact["role"])
        except (TypeError, ValueError) as error:
            raise BackupManifestError("unknown backup artifact role") from error
        records.append(
            BackupArtifactRecord(
                role=role,
                relative_path=artifact["relative_path"],
                sha256=artifact["sha256"],
                byte_size=artifact["byte_size"],
                required=artifact["required"],
            )
        )

    manifest = BackupManifest(
        schema_version=document["schema_version"],
        created_at_unix_ms=document["created_at_unix_ms"],
        paper_run_id=document["paper_run_id"],
        campaign_manifest_fingerprint_sha256=document[
            "campaign_manifest_fingerprint_sha256"
        ],
        sqlite_quick_check=document["sqlite_quick_check"],
        completed=document["completed"],
        artifacts=tuple(records),
    )
    if encode_backup_manifest(manifest) != raw:
        raise BackupManifestError("backup manifest is not canonical")
    return manifest


def _payload_bytes(payload: bytes | str) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise BackupManifestError("backup manifest payload must be bytes or text")


def _reject_nonfinite(value: str) -> object:
    raise BackupManifestError(f"non-finite JSON constant is forbidden: {value}")
