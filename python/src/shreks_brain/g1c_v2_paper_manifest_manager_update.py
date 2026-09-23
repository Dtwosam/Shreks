from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import (
    g1c_v2_paper_manifest_manager_installation_proof as installation_proof,
)


_SCHEMA_NAME = "shreks.g1c_v2_paper_manifest_manager_update"
_SCHEMA_VERSION = 1
_STATUS_UPDATED = "UPDATED"
_UPDATE_AUTHORITY = "EXERCISED_EXACT_RELEASE_BOUND_HELPER_REPLACEMENT_ONLY"
_NOT_EXERCISED = "NOT_EXERCISED"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"
_REQUIRED_PROOF_AUTHORITY = "PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY"
_SHA256_LENGTH = 64
_PROOF_MODE = 0o600


class PaperManifestManagerUpdateError(RuntimeError):
    """Raised when an exact proven helper cannot be replaced safely."""


def update_release_bound_paper_manifest_manager(
    *,
    expected_release_source_sha: str,
    prior_installation_proof_path: str | Path,
    paths: installer.PaperManifestManagerInstallPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    if type(paths) is not installer.PaperManifestManagerInstallPaths:
        raise PaperManifestManagerUpdateError(
            "update paths must be exact PaperManifestManagerInstallPaths"
        )
    if os.geteuid() != 0:
        raise PaperManifestManagerUpdateError(
            "PAPER manifest manager update requires root"
        )

    expected_sha = installer._validate_source_sha(expected_release_source_sha)
    material = _release_material(
        expected_sha=expected_sha,
        paths=paths,
        runtime_executable=runtime_executable,
    )
    prior_payload, prior = _load_prior_proof(
        prior_installation_proof_path,
        paths=paths,
        expected_new_release_sha=expected_sha,
    )

    old_payload, old_metadata = installer._read_regular_no_follow(
        paths.destination,
        label="installed PAPER manifest manager",
    )
    installer._require_destination_metadata(old_metadata)
    old_sha256 = hashlib.sha256(old_payload).hexdigest()
    if old_sha256 != prior["manager_sha256"]:
        raise PaperManifestManagerUpdateError(
            "installed helper does not match prior verified installation proof"
        )

    new_payload = material["manager_payload"]
    new_sha256 = material["manager_sha256"]
    if old_sha256 == new_sha256:
        raise PaperManifestManagerUpdateError(
            "installed helper already matches current release; use proof refresh"
        )

    current_before = installer._require_current_release(
        paths.current_link,
        expected_sha,
    )
    if current_before != material["release_directory_path"]:
        raise PaperManifestManagerUpdateError(
            "current release changed before helper replacement"
        )

    _replace_exact_existing(
        destination=paths.destination,
        old_payload=old_payload,
        new_payload=new_payload,
    )

    try:
        current_after = installer._require_current_release(
            paths.current_link,
            expected_sha,
        )
        if current_after != material["release_directory_path"]:
            raise PaperManifestManagerUpdateError(
                "current release changed during helper replacement"
            )
        installer._require_installed_destination(
            paths.destination,
            expected_payload=new_payload,
        )
    except Exception as error:
        try:
            _replace_exact_existing(
                destination=paths.destination,
                old_payload=new_payload,
                new_payload=old_payload,
            )
            installer._require_installed_destination(
                paths.destination,
                expected_payload=old_payload,
            )
        except Exception as rollback_error:
            raise PaperManifestManagerUpdateError(
                "helper replacement failed and prior helper rollback failed"
            ) from rollback_error
        raise PaperManifestManagerUpdateError(
            "helper replacement failed; prior verified helper restored"
        ) from error

    return {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS_UPDATED,
        "release_source_sha": expected_sha,
        "release_directory": str(material["release_directory_path"]),
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "wheel_member": installer._MANAGER_MEMBER,
        "manager_sha256": new_sha256,
        "destination": str(paths.destination),
        "destination_uid": installer._DESTINATION_UID,
        "destination_gid": installer._DESTINATION_GID,
        "destination_mode": "0755",
        "prior_installation_proof_sha256": hashlib.sha256(
            prior_payload
        ).hexdigest(),
        "prior_installation_proof_fingerprint_sha256": prior[
            "proof_fingerprint_sha256"
        ],
        "prior_release_source_sha": prior["release_source_sha"],
        "prior_manager_sha256": old_sha256,
        "helper_update_authority": _UPDATE_AUTHORITY,
        "manifest_rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }


def _release_material(
    *,
    expected_sha: str,
    paths: installer.PaperManifestManagerInstallPaths,
    runtime_executable: str | os.PathLike[str] | None,
) -> dict[str, object]:
    release_dir = installer._require_current_release(
        paths.current_link,
        expected_sha,
    )
    installer._require_release_runtime_executable(
        release_dir,
        Path(sys.executable if runtime_executable is None else runtime_executable),
    )

    manifest_payload, _ = installer._read_regular_no_follow(
        release_dir / "RELEASE_MANIFEST.json",
        label="current release manifest",
    )
    manifest = installer._decode_release_manifest(manifest_payload)
    if manifest.source_sha != expected_sha:
        raise PaperManifestManagerUpdateError(
            "current release manifest source SHA does not match expected release"
        )

    wheel_record = installer._require_single_wheel_record(manifest)
    wheel_path = release_dir / wheel_record.path
    wheel_payload, _ = installer._read_regular_no_follow(
        wheel_path,
        label="release wheel",
    )
    if len(wheel_payload) != wheel_record.size:
        raise PaperManifestManagerUpdateError(
            "release wheel size does not match release manifest"
        )
    wheel_sha256 = hashlib.sha256(wheel_payload).hexdigest()
    if wheel_sha256 != wheel_record.sha256:
        raise PaperManifestManagerUpdateError(
            "release wheel hash does not match release manifest"
        )

    manager_payload = installer._extract_manager_payload(wheel_payload)
    return {
        "release_directory_path": release_dir,
        "wheel_relative_path": wheel_record.path,
        "wheel_sha256": wheel_sha256,
        "manager_payload": manager_payload,
        "manager_sha256": hashlib.sha256(manager_payload).hexdigest(),
    }


def _load_prior_proof(
    raw_path: str | Path,
    *,
    paths: installer.PaperManifestManagerInstallPaths,
    expected_new_release_sha: str,
) -> tuple[bytes, dict[str, object]]:
    path = Path(raw_path).expanduser()
    payload, metadata = installer._read_regular_no_follow(
        path,
        label="prior helper installation proof",
    )
    if (
        metadata.st_uid != installer._DESTINATION_UID
        or metadata.st_gid != installer._DESTINATION_GID
        or stat.S_IMODE(metadata.st_mode) != _PROOF_MODE
    ):
        raise PaperManifestManagerUpdateError(
            "prior helper installation proof metadata is not exact"
        )
    try:
        document = installation_proof._decode(
            payload,
            "prior helper installation proof",
        )
    except installation_proof.PaperManifestManagerInstallationProofError as error:
        raise PaperManifestManagerUpdateError(
            "prior helper installation proof is not trusted canonical JSON"
        ) from error

    expected = {
        "schema_name": installation_proof._PROOF_SCHEMA,
        "schema_version": installation_proof._SCHEMA_VERSION,
        "status": "VERIFIED",
        "manager_destination": str(paths.destination),
        "destination_uid": installer._DESTINATION_UID,
        "destination_gid": installer._DESTINATION_GID,
        "destination_mode": "0755",
        "campaign_manifest_unchanged": True,
        "deploy_sudoers_unchanged": True,
        "service_lifecycle_unchanged": True,
        "installation_authority": _REQUIRED_PROOF_AUTHORITY,
        "manifest_rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            raise PaperManifestManagerUpdateError(
                f"prior helper installation proof {field} is not acceptable"
            )

    if document.get("proof_fingerprint_sha256") != installation_proof._fingerprint(
        document,
        "proof_fingerprint_sha256",
    ):
        raise PaperManifestManagerUpdateError(
            "prior helper installation proof fingerprint is invalid"
        )

    prior_release_sha = installer._validate_source_sha(
        document.get("release_source_sha")
    )
    if prior_release_sha == expected_new_release_sha:
        raise PaperManifestManagerUpdateError(
            "prior helper proof must bind an earlier release"
        )
    _require_sha256("manager_sha256", document.get("manager_sha256"))
    return payload, document


def _require_safe_parent(destination: Path) -> None:
    parent = destination.parent
    try:
        metadata = parent.lstat()
    except OSError as error:
        raise PaperManifestManagerUpdateError(
            "PAPER manifest manager destination parent is unavailable"
        ) from error
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != installer._DESTINATION_UID
        or metadata.st_gid != installer._DESTINATION_GID
        or mode & 0o022
    ):
        raise PaperManifestManagerUpdateError(
            "PAPER manifest manager destination parent is unsafe"
        )


def _replace_exact_existing(
    *,
    destination: Path,
    old_payload: bytes,
    new_payload: bytes,
) -> None:
    _require_safe_parent(destination)

    observed, metadata = installer._read_regular_no_follow(
        destination,
        label="installed PAPER manifest manager",
    )
    installer._require_destination_metadata(metadata)
    if observed != old_payload:
        raise PaperManifestManagerUpdateError(
            "installed PAPER manifest manager changed before replacement"
        )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.update-",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    replaced = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(new_payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(
                handle.fileno(),
                installer._DESTINATION_UID,
                installer._DESTINATION_GID,
            )
            os.fchmod(handle.fileno(), installer._DESTINATION_MODE)
            os.fsync(handle.fileno())

        observed_before, metadata_before = installer._read_regular_no_follow(
            destination,
            label="installed PAPER manifest manager",
        )
        installer._require_destination_metadata(metadata_before)
        if observed_before != old_payload:
            raise PaperManifestManagerUpdateError(
                "installed PAPER manifest manager changed during replacement"
            )

        os.replace(temporary, destination)
        replaced = True
        installer._fsync_directory(destination.parent)
    except Exception:
        if not replaced:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _require_sha256(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PaperManifestManagerUpdateError(
            f"{name} must be lowercase SHA-256 hex"
        )
    return value


def _production_paths() -> installer.PaperManifestManagerInstallPaths:
    return installer.PaperManifestManagerInstallPaths(
        current_link=Path("/opt/shreks/current"),
        destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
    )


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-paper-manifest-manager-update",
        description=(
            "Replace one prior VERIFIED exact helper with the exact helper "
            "from the current immutable release, without runtime authority."
        ),
    )
    parser.add_argument("expected_release_source_sha")
    parser.add_argument("--prior-installation-proof", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = update_release_bound_paper_manifest_manager(
            expected_release_source_sha=args.expected_release_source_sha,
            prior_installation_proof_path=args.prior_installation_proof,
            paths=_production_paths(),
        )
    except (
        PaperManifestManagerUpdateError,
        installation_proof.PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.buffer.write(
            _canonical(
                {
                    "schema_name": _SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                    "helper_update_authority": _NOT_EXERCISED,
                    "manifest_rotation_authority": _NOT_GRANTED,
                    "scoring_authority": _NOT_GRANTED,
                    "paper_promotion_authority": _BLOCKED,
                    "live_authority": _DISABLED,
                }
            )
        )
        return 1

    sys.stdout.buffer.write(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
