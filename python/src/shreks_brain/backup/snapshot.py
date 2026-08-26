from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import sqlite3

from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeBootstrap,
    ObserverPaperCampaignRuntimeError,
    preflight_observer_paper_campaign_runtime,
)
from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfig,
    ObserverPaperCampaignRuntimeConfigError,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.risk_control import (
    RiskControlStateError,
    load_operator_risk_control_state,
)

from .manifest import encode_backup_manifest
from .models import (
    BACKUP_MANIFEST_SCHEMA_VERSION,
    BackupArtifactRecord,
    BackupArtifactRole,
    BackupManifest,
    BackupManifestError,
)
from .verify import verify_backup_bundle


class BackupSnapshotError(RuntimeError):
    """Raised when G8 cannot publish a coherent backup snapshot safely."""


@dataclass(frozen=True, slots=True)
class BackupSnapshotSources:
    operational_database_path: Path
    e11_path: Path
    campaign_manifest_path: Path
    risk_control_path: Path
    alert_state_path: Path | None = None

    def __post_init__(self) -> None:
        for name in (
            "operational_database_path",
            "e11_path",
            "campaign_manifest_path",
            "risk_control_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise BackupSnapshotError(f"{name} must be an absolute Path")
        if self.alert_state_path is not None and (
            not isinstance(self.alert_state_path, Path)
            or not self.alert_state_path.is_absolute()
        ):
            raise BackupSnapshotError("alert_state_path must be an absolute Path when supplied")


PreflightValidator = Callable[
    [ObserverPaperCampaignRuntimeConfig],
    ObserverPaperCampaignRuntimeBootstrap | object,
]


def create_backup_snapshot(
    backup_root: str | os.PathLike[str],
    sources: BackupSnapshotSources,
    *,
    created_at_unix_ms: int,
    max_capture_attempts: int,
    preflight_validator: PreflightValidator | None = None,
) -> Path:
    if type(sources) is not BackupSnapshotSources:
        raise BackupSnapshotError("sources must be an exact BackupSnapshotSources")
    if isinstance(created_at_unix_ms, bool) or not isinstance(created_at_unix_ms, int):
        raise BackupSnapshotError("created_at_unix_ms must be a non-negative integer")
    if created_at_unix_ms < 0:
        raise BackupSnapshotError("created_at_unix_ms must be a non-negative integer")
    if (
        isinstance(max_capture_attempts, bool)
        or not isinstance(max_capture_attempts, int)
        or max_capture_attempts < 1
        or max_capture_attempts > 100
    ):
        raise BackupSnapshotError("max_capture_attempts must be an integer from 1 through 100")
    if preflight_validator is not None and not callable(preflight_validator):
        raise BackupSnapshotError("preflight_validator must be callable when supplied")

    root = _prepare_backup_root(backup_root)
    validator = (
        _default_preflight_validator
        if preflight_validator is None
        else preflight_validator
    )
    last_error: BackupSnapshotError | None = None

    for attempt in range(1, max_capture_attempts + 1):
        temporary = root / (
            f".g8-capture-{created_at_unix_ms}-{attempt}-{secrets.token_hex(8)}"
        )
        try:
            temporary.mkdir(mode=0o700)
            os.chmod(temporary, 0o700)
            final = _capture_once(
                temporary,
                sources,
                created_at_unix_ms=created_at_unix_ms,
                preflight_validator=validator,
            )
            destination = root / final
            if destination.exists() or destination.is_symlink():
                raise BackupSnapshotError("completed backup destination already exists")
            os.replace(temporary, destination)
            os.chmod(destination, 0o700)
            return destination
        except BackupSnapshotError as error:
            last_error = error
            _cleanup_owned_temporary(root, temporary)
        except Exception:
            _cleanup_owned_temporary(root, temporary)
            raise

    raise BackupSnapshotError(
        f"backup capture did not produce a coherent snapshot after {max_capture_attempts} attempt(s)"
    ) from last_error


def _capture_once(
    temporary: Path,
    sources: BackupSnapshotSources,
    *,
    created_at_unix_ms: int,
    preflight_validator: PreflightValidator,
) -> str:
    for path in (
        sources.operational_database_path,
        sources.e11_path,
        sources.campaign_manifest_path,
        sources.risk_control_path,
    ):
        _require_regular_source(path)
    if sources.alert_state_path is not None:
        _require_regular_source(sources.alert_state_path)

    artifacts_dir = temporary / "artifacts"
    artifacts_dir.mkdir(mode=0o700)
    os.chmod(artifacts_dir, 0o700)

    destinations = {
        BackupArtifactRole.OPERATIONAL_SQLITE: artifacts_dir / "operational.sqlite3",
        BackupArtifactRole.E11_EVIDENCE: artifacts_dir / "e11.json",
        BackupArtifactRole.CAMPAIGN_MANIFEST: artifacts_dir / "paper-campaign.json",
        BackupArtifactRole.OPERATOR_RISK_CONTROL: artifacts_dir / "operator-control.json",
        BackupArtifactRole.ALERT_STATE: artifacts_dir / "alerts-state.json",
    }

    _online_sqlite_backup(
        sources.operational_database_path,
        destinations[BackupArtifactRole.OPERATIONAL_SQLITE],
    )
    _copy_exact(sources.e11_path, destinations[BackupArtifactRole.E11_EVIDENCE])
    _copy_exact(
        sources.campaign_manifest_path,
        destinations[BackupArtifactRole.CAMPAIGN_MANIFEST],
    )
    _copy_exact(
        sources.risk_control_path,
        destinations[BackupArtifactRole.OPERATOR_RISK_CONTROL],
    )
    if sources.alert_state_path is not None:
        _copy_exact(
            sources.alert_state_path,
            destinations[BackupArtifactRole.ALERT_STATE],
        )

    try:
        staged_manifest = decode_observer_paper_campaign_runtime_manifest(
            destinations[BackupArtifactRole.CAMPAIGN_MANIFEST].read_bytes()
        )
        load_operator_risk_control_state(
            destinations[BackupArtifactRole.OPERATOR_RISK_CONTROL]
        )
    except (
        OSError,
        ObserverPaperCampaignRuntimeManifestError,
        RiskControlStateError,
        TypeError,
        ValueError,
    ) as error:
        raise BackupSnapshotError("staged campaign or risk-control state is invalid") from error

    staged_config = ObserverPaperCampaignRuntimeConfig(
        observer_database_path=destinations[
            BackupArtifactRole.OPERATIONAL_SQLITE
        ].resolve(),
        evidence_path=destinations[BackupArtifactRole.E11_EVIDENCE].resolve(),
        manifest_path=destinations[BackupArtifactRole.CAMPAIGN_MANIFEST].resolve(),
        cycle_interval_seconds=1.0,
        max_cycles=1,
        risk_control_path=destinations[
            BackupArtifactRole.OPERATOR_RISK_CONTROL
        ].resolve(),
    )
    try:
        preflight_validator(staged_config)
    except Exception as error:
        raise BackupSnapshotError("staged PAPER recovery preflight failed") from error

    records = [
        _artifact_record(
            BackupArtifactRole.OPERATIONAL_SQLITE,
            destinations[BackupArtifactRole.OPERATIONAL_SQLITE],
            temporary,
            required=True,
        ),
        _artifact_record(
            BackupArtifactRole.E11_EVIDENCE,
            destinations[BackupArtifactRole.E11_EVIDENCE],
            temporary,
            required=True,
        ),
        _artifact_record(
            BackupArtifactRole.CAMPAIGN_MANIFEST,
            destinations[BackupArtifactRole.CAMPAIGN_MANIFEST],
            temporary,
            required=True,
        ),
        _artifact_record(
            BackupArtifactRole.OPERATOR_RISK_CONTROL,
            destinations[BackupArtifactRole.OPERATOR_RISK_CONTROL],
            temporary,
            required=True,
        ),
    ]
    if sources.alert_state_path is not None:
        records.append(
            _artifact_record(
                BackupArtifactRole.ALERT_STATE,
                destinations[BackupArtifactRole.ALERT_STATE],
                temporary,
                required=False,
            )
        )

    manifest = BackupManifest(
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
        created_at_unix_ms=created_at_unix_ms,
        paper_run_id=staged_manifest.paper_run_id,
        campaign_manifest_fingerprint_sha256=(
            staged_manifest.manifest_fingerprint_sha256
        ),
        sqlite_quick_check="ok",
        completed=True,
        artifacts=tuple(records),
    )
    manifest_path = temporary / "manifest.json"
    _write_private(manifest_path, encode_backup_manifest(manifest))
    try:
        verify_backup_bundle(temporary)
    except BackupManifestError as error:
        raise BackupSnapshotError("staged backup bundle verification failed") from error
    return f"{created_at_unix_ms}-{staged_manifest.manifest_fingerprint_sha256[:12]}"


def _default_preflight_validator(
    config: ObserverPaperCampaignRuntimeConfig,
) -> ObserverPaperCampaignRuntimeBootstrap:
    try:
        return preflight_observer_paper_campaign_runtime(
            config,
            status_sink=lambda _line: None,
        )
    except (
        ObserverPaperCampaignRuntimeError,
        ObserverPaperCampaignRuntimeConfigError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise BackupSnapshotError("staged PAPER recovery preflight failed") from error


def _prepare_backup_root(path: str | os.PathLike[str]) -> Path:
    try:
        raw = Path(path).expanduser()
        if raw.exists() and raw.is_symlink():
            raise BackupSnapshotError("backup root must not be a symlink")
        root = raw.resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink() or not root.is_dir():
            raise BackupSnapshotError("backup root must be a real directory")
        os.chmod(root, 0o700)
        return root
    except BackupSnapshotError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise BackupSnapshotError("backup root could not be prepared") from error


def _require_regular_source(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise BackupSnapshotError("required backup source is missing or unsafe")


def _online_sqlite_backup(source_path: Path, destination_path: Path) -> None:
    try:
        source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
        destination = sqlite3.connect(destination_path)
        try:
            source.backup(destination)
            destination.commit()
            row = destination.execute("PRAGMA quick_check").fetchone()
            if row is None or row[0] != "ok":
                raise BackupSnapshotError("staged SQLite quick_check did not return ok")

            journal_mode_row = destination.execute("PRAGMA journal_mode=DELETE").fetchone()
            if (
                journal_mode_row is None
                or not isinstance(journal_mode_row[0], str)
                or journal_mode_row[0].lower() != "delete"
            ):
                raise BackupSnapshotError(
                    "staged SQLite copy could not be normalized to single-file journaling"
                )
            destination.commit()
        finally:
            destination.close()
            source.close()

        _remove_staged_sqlite_sidecars(destination_path)
        os.chmod(destination_path, 0o600)
    except BackupSnapshotError:
        raise
    except (OSError, sqlite3.Error) as error:
        raise BackupSnapshotError("SQLite online backup failed") from error


def _remove_staged_sqlite_sidecars(destination_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{destination_path}{suffix}")
        if sidecar.is_symlink():
            raise BackupSnapshotError("staged SQLite sidecar is unexpectedly a symlink")
        try:
            if sidecar.exists():
                sidecar.unlink()
        except OSError as error:
            raise BackupSnapshotError(
                "staged SQLite sidecar could not be removed after DELETE normalization"
            ) from error


def _copy_exact(source: Path, destination: Path) -> None:
    try:
        payload = source.read_bytes()
    except OSError as error:
        raise BackupSnapshotError("backup source could not be read") from error
    _write_private(destination, payload)


def _write_private(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        os.chmod(path, 0o600)
    except OSError as error:
        raise BackupSnapshotError("private backup artifact could not be written") from error


def _artifact_record(
    role: BackupArtifactRole,
    path: Path,
    bundle_root: Path,
    *,
    required: bool,
) -> BackupArtifactRecord:
    try:
        payload = path.read_bytes()
        relative_path = path.relative_to(bundle_root).as_posix()
    except (OSError, ValueError) as error:
        raise BackupSnapshotError("staged backup artifact could not be hashed") from error
    return BackupArtifactRecord(
        role=role,
        relative_path=relative_path,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        required=required,
    )


def _cleanup_owned_temporary(root: Path, temporary: Path) -> None:
    try:
        temporary.relative_to(root)
    except ValueError:
        return
    if not temporary.name.startswith(".g8-capture-"):
        return
    try:
        if temporary.exists() and not temporary.is_symlink():
            shutil.rmtree(temporary)
    except OSError:
        pass
