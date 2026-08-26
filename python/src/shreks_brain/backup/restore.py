from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from shreks_brain.observer_campaign.runtime import (
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
from shreks_brain.paper_validation import PaperCheckpointError, load_latest_paper_checkpoint
from shreks_brain.risk_control import RiskControlStateError, load_operator_risk_control_state

from .models import BackupArtifactRole, BackupManifestError
from .verify import verify_backup_bundle


class BackupRestoreError(RuntimeError):
    """Raised when a G8 bundle cannot be restored safely to staging."""


@dataclass(frozen=True, slots=True)
class BackupRestoreResult:
    paper_run_id: str
    campaign_manifest_fingerprint_sha256: str
    checkpoint_sequence: int
    state_as_of_unix_ms: int
    verified_artifact_sha256: dict[str, str]


_DESTINATION_NAMES = {
    BackupArtifactRole.OPERATIONAL_SQLITE: "operational.sqlite3",
    BackupArtifactRole.E11_EVIDENCE: "e11.json",
    BackupArtifactRole.CAMPAIGN_MANIFEST: "paper-campaign.json",
    BackupArtifactRole.OPERATOR_RISK_CONTROL: "operator-control.json",
    BackupArtifactRole.ALERT_STATE: "alerts-state.json",
}


def restore_backup_bundle(
    bundle_path: str | os.PathLike[str],
    staging_path: str | os.PathLike[str],
) -> BackupRestoreResult:
    try:
        manifest = verify_backup_bundle(bundle_path)
    except (BackupManifestError, OSError, TypeError, ValueError) as error:
        raise BackupRestoreError("backup bundle verification failed") from error

    bundle = Path(bundle_path)
    staging = Path(staging_path)
    _require_available_staging_target(staging)

    created_staging = not staging.exists()
    try:
        if created_staging:
            staging.mkdir(mode=0o700)
        os.chmod(staging, 0o700)

        restored_paths: dict[BackupArtifactRole, Path] = {}
        for record in manifest.artifacts:
            destination_name = _DESTINATION_NAMES.get(record.role)
            if destination_name is None:
                raise BackupRestoreError("backup bundle contains an unsupported artifact role")
            source = bundle / record.relative_path
            destination = staging / destination_name
            _copy_private(source, destination)
            restored_paths[record.role] = destination

        database_path = restored_paths[BackupArtifactRole.OPERATIONAL_SQLITE]
        evidence_path = restored_paths[BackupArtifactRole.E11_EVIDENCE]
        campaign_path = restored_paths[BackupArtifactRole.CAMPAIGN_MANIFEST]
        risk_path = restored_paths[BackupArtifactRole.OPERATOR_RISK_CONTROL]

        try:
            campaign = decode_observer_paper_campaign_runtime_manifest(
                campaign_path.read_bytes()
            )
            if campaign.paper_run_id != manifest.paper_run_id:
                raise BackupRestoreError("restored campaign run attribution mismatch")
            if (
                campaign.manifest_fingerprint_sha256
                != manifest.campaign_manifest_fingerprint_sha256
            ):
                raise BackupRestoreError("restored campaign fingerprint mismatch")
            load_operator_risk_control_state(risk_path)
        except BackupRestoreError:
            raise
        except (
            OSError,
            ObserverPaperCampaignRuntimeManifestError,
            RiskControlStateError,
            TypeError,
            ValueError,
        ) as error:
            raise BackupRestoreError("restored campaign or control state is invalid") from error

        config = ObserverPaperCampaignRuntimeConfig(
            observer_database_path=database_path.resolve(),
            evidence_path=evidence_path.resolve(),
            manifest_path=campaign_path.resolve(),
            cycle_interval_seconds=1.0,
            max_cycles=1,
            risk_control_path=risk_path.resolve(),
        )
        try:
            preflight_observer_paper_campaign_runtime(
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
            raise BackupRestoreError("restored PAPER preflight failed") from error

        try:
            checkpoint = load_latest_paper_checkpoint(
                database_path,
                manifest.paper_run_id,
            )
        except (OSError, PaperCheckpointError, TypeError, ValueError) as error:
            raise BackupRestoreError("restored PAPER checkpoint could not be loaded") from error
        if checkpoint is None:
            raise BackupRestoreError("restored PAPER checkpoint is missing")

        return BackupRestoreResult(
            paper_run_id=manifest.paper_run_id,
            campaign_manifest_fingerprint_sha256=(
                manifest.campaign_manifest_fingerprint_sha256
            ),
            checkpoint_sequence=checkpoint.sequence,
            state_as_of_unix_ms=checkpoint.state.as_of_unix_ms,
            verified_artifact_sha256={
                record.role.value: record.sha256 for record in manifest.artifacts
            },
        )
    except BackupRestoreError:
        _cleanup_failed_staging(staging, created_staging=created_staging)
        raise
    except OSError as error:
        _cleanup_failed_staging(staging, created_staging=created_staging)
        raise BackupRestoreError("staging restore failed closed") from error


def _require_available_staging_target(staging: Path) -> None:
    if staging.is_symlink():
        raise BackupRestoreError("staging target must not be a symlink")
    if staging.exists():
        if not staging.is_dir():
            raise BackupRestoreError("staging target must be a directory")
        try:
            if any(staging.iterdir()):
                raise BackupRestoreError("staging target must be empty")
        except OSError as error:
            raise BackupRestoreError("staging target could not be inspected") from error
    parent = staging.parent
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        raise BackupRestoreError("staging parent is unsafe")


def _copy_private(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise BackupRestoreError("verified source artifact became unsafe")
    if destination.exists() or destination.is_symlink():
        raise BackupRestoreError("staging artifact already exists")
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with source.open("rb") as source_handle, os.fdopen(descriptor, "wb") as output:
                shutil.copyfileobj(source_handle, output)
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        os.chmod(destination, 0o600)
    except OSError as error:
        raise BackupRestoreError("staging artifact could not be copied") from error


def _cleanup_failed_staging(staging: Path, *, created_staging: bool) -> None:
    try:
        if staging.is_symlink() or not staging.exists() or not staging.is_dir():
            return
        for child in staging.iterdir():
            if child.is_file() and not child.is_symlink() and child.name in _DESTINATION_NAMES.values():
                child.unlink()
        if created_staging and not any(staging.iterdir()):
            staging.rmdir()
    except OSError:
        pass
