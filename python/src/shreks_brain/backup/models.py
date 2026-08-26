from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


BACKUP_MANIFEST_SCHEMA_VERSION = "g8-backup-bundle-v1"


class BackupManifestError(ValueError):
    """Raised when a G8 backup manifest or bundle is unsafe or malformed."""


class BackupArtifactRole(str, Enum):
    OPERATIONAL_SQLITE = "operational_sqlite"
    E11_EVIDENCE = "e11_evidence"
    CAMPAIGN_MANIFEST = "campaign_manifest"
    OPERATOR_RISK_CONTROL = "operator_risk_control"
    ALERT_STATE = "alert_state"


_ROLE_ORDER = {
    BackupArtifactRole.OPERATIONAL_SQLITE: 0,
    BackupArtifactRole.E11_EVIDENCE: 1,
    BackupArtifactRole.CAMPAIGN_MANIFEST: 2,
    BackupArtifactRole.OPERATOR_RISK_CONTROL: 3,
    BackupArtifactRole.ALERT_STATE: 4,
}
_REQUIRED_ROLES = frozenset(
    {
        BackupArtifactRole.OPERATIONAL_SQLITE,
        BackupArtifactRole.E11_EVIDENCE,
        BackupArtifactRole.CAMPAIGN_MANIFEST,
        BackupArtifactRole.OPERATOR_RISK_CONTROL,
    }
)


@dataclass(frozen=True, slots=True)
class BackupArtifactRecord:
    role: BackupArtifactRole
    relative_path: str
    sha256: str
    byte_size: int
    required: bool

    def __post_init__(self) -> None:
        if type(self.role) is not BackupArtifactRole:
            raise BackupManifestError("artifact role must be a BackupArtifactRole")
        _require_safe_relative_path(self.relative_path)
        _require_sha256("artifact sha256", self.sha256)
        if isinstance(self.byte_size, bool) or not isinstance(self.byte_size, int):
            raise BackupManifestError("artifact byte_size must be a non-negative integer")
        if self.byte_size < 0:
            raise BackupManifestError("artifact byte_size must be a non-negative integer")
        if type(self.required) is not bool:
            raise BackupManifestError("artifact required must be a boolean")


@dataclass(frozen=True, slots=True)
class BackupManifest:
    schema_version: str
    created_at_unix_ms: int
    paper_run_id: str
    campaign_manifest_fingerprint_sha256: str
    sqlite_quick_check: str
    completed: bool
    artifacts: tuple[BackupArtifactRecord, ...]

    def __post_init__(self) -> None:
        if self.schema_version != BACKUP_MANIFEST_SCHEMA_VERSION:
            raise BackupManifestError("unsupported backup manifest schema version")
        if isinstance(self.created_at_unix_ms, bool) or not isinstance(
            self.created_at_unix_ms, int
        ):
            raise BackupManifestError("created_at_unix_ms must be a non-negative integer")
        if self.created_at_unix_ms < 0:
            raise BackupManifestError("created_at_unix_ms must be a non-negative integer")
        _require_non_empty_text("paper_run_id", self.paper_run_id)
        _require_sha256(
            "campaign_manifest_fingerprint_sha256",
            self.campaign_manifest_fingerprint_sha256,
        )
        if self.sqlite_quick_check != "ok":
            raise BackupManifestError("sqlite_quick_check must be exactly 'ok'")
        if self.completed is not True:
            raise BackupManifestError("completed must be exactly true")
        if type(self.artifacts) is not tuple or not self.artifacts:
            raise BackupManifestError("artifacts must be a non-empty tuple")
        if any(type(record) is not BackupArtifactRecord for record in self.artifacts):
            raise BackupManifestError("artifacts must contain exact BackupArtifactRecord values")

        roles = [record.role for record in self.artifacts]
        paths = [record.relative_path for record in self.artifacts]
        if len(set(roles)) != len(roles):
            raise BackupManifestError("artifact roles must be unique")
        if len(set(paths)) != len(paths):
            raise BackupManifestError("artifact paths must be unique")
        if not _REQUIRED_ROLES.issubset(roles):
            raise BackupManifestError("required PAPER recovery artifact role is missing")

        for record in self.artifacts:
            if record.role in _REQUIRED_ROLES and record.required is not True:
                raise BackupManifestError("core PAPER recovery artifacts must be required")
            if record.role is BackupArtifactRole.ALERT_STATE and record.required is not False:
                raise BackupManifestError("alert_state must be the optional G8 artifact")

        normalized = tuple(sorted(self.artifacts, key=lambda item: _ROLE_ORDER[item.role]))
        object.__setattr__(self, "artifacts", normalized)


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise BackupManifestError(f"{name} must be non-empty trimmed text")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise BackupManifestError(f"{name} must be a lowercase SHA-256 hex string")
    if value != value.lower() or any(character not in "0123456789abcdef" for character in value):
        raise BackupManifestError(f"{name} must be a lowercase SHA-256 hex string")


def _require_safe_relative_path(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise BackupManifestError("artifact relative_path must be non-empty text")
    if "\\" in value or value.startswith("/") or value.endswith("/"):
        raise BackupManifestError("artifact relative_path is unsafe")
    raw_parts = value.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise BackupManifestError("artifact relative_path is unsafe")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value:
        raise BackupManifestError("artifact relative_path is unsafe")
    if not raw_parts or raw_parts[0] != "artifacts":
        raise BackupManifestError("artifact relative_path must be below artifacts/")
