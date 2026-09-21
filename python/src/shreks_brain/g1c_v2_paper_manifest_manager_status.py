from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer


_SCHEMA_NAME = "shreks.g1c_v2_paper_manifest_manager_status"
_SCHEMA_VERSION = 1
_DESTINATION_UID = 0
_DESTINATION_GID = 0
_DESTINATION_MODE = 0o755


class PaperManifestManagerStatusError(RuntimeError):
    """Raised when the read-only helper status cannot be established safely."""


@dataclass(frozen=True, slots=True)
class PaperManifestManagerStatusPaths:
    current_link: Path
    destination: Path

    def __post_init__(self) -> None:
        for name in ("current_link", "destination"):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise PaperManifestManagerStatusError(
                    f"{name} must be an absolute Path"
                )


def inspect_release_bound_paper_manifest_manager_status(
    *,
    expected_release_source_sha: str,
    paths: PaperManifestManagerStatusPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    if type(paths) is not PaperManifestManagerStatusPaths:
        raise PaperManifestManagerStatusError(
            "status paths must be an exact PaperManifestManagerStatusPaths"
        )

    try:
        expected_sha = installer._validate_source_sha(expected_release_source_sha)
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
            raise PaperManifestManagerStatusError(
                "current release manifest source SHA does not match expected release"
            )

        wheel_record = installer._require_single_wheel_record(manifest)
        wheel_payload, _ = installer._read_regular_no_follow(
            release_dir / wheel_record.path,
            label="release wheel",
        )
        if len(wheel_payload) != wheel_record.size:
            raise PaperManifestManagerStatusError(
                "release wheel size does not match release manifest"
            )
        wheel_sha256 = hashlib.sha256(wheel_payload).hexdigest()
        if wheel_sha256 != wheel_record.sha256:
            raise PaperManifestManagerStatusError(
                "release wheel hash does not match release manifest"
            )
        expected_manager_payload = installer._extract_manager_payload(wheel_payload)
    except installer.PaperManifestManagerInstallError as error:
        raise PaperManifestManagerStatusError(
            "current sealed manager release material could not be authenticated"
        ) from error

    expected_manager_sha256 = hashlib.sha256(expected_manager_payload).hexdigest()
    observation = _inspect_destination(
        paths.destination,
        expected_payload=expected_manager_payload,
    )
    return {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": observation["status"],
        "release_source_sha": expected_sha,
        "release_directory": str(release_dir),
        "wheel_relative_path": wheel_record.path,
        "wheel_sha256": wheel_sha256,
        "expected_manager_sha256": expected_manager_sha256,
        "destination": str(paths.destination),
        "destination_present": observation["destination_present"],
        "destination_type": observation["destination_type"],
        "destination_sha256": observation["destination_sha256"],
        "destination_uid": observation["destination_uid"],
        "destination_gid": observation["destination_gid"],
        "destination_mode": observation["destination_mode"],
        "bytes_match_current_release": observation["bytes_match_current_release"],
        "metadata_match_expected": observation["metadata_match_expected"],
        "observation_authority": "READ_ONLY",
        "installation_authority": "NOT_EXERCISED",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }


def _inspect_destination(
    destination: Path,
    *,
    expected_payload: bytes,
) -> dict[str, object]:
    try:
        metadata = destination.lstat()
    except FileNotFoundError:
        return _destination_observation(
            status="ABSENT",
            present=False,
            destination_type="absent",
        )
    except OSError as error:
        raise PaperManifestManagerStatusError(
            "PAPER manifest manager destination could not be inspected"
        ) from error

    if stat.S_ISLNK(metadata.st_mode):
        return _destination_observation(
            status="PRESENT_UNSAFE_TYPE",
            present=True,
            destination_type="symlink",
            metadata=metadata,
        )
    if not stat.S_ISREG(metadata.st_mode):
        return _destination_observation(
            status="PRESENT_UNSAFE_TYPE",
            present=True,
            destination_type=_file_type(metadata.st_mode),
            metadata=metadata,
        )

    try:
        payload, stable_metadata = installer._read_regular_no_follow(
            destination,
            label="PAPER manifest manager destination",
        )
    except installer.PaperManifestManagerInstallError as error:
        raise PaperManifestManagerStatusError(
            "PAPER manifest manager destination could not be read stably"
        ) from error

    digest = hashlib.sha256(payload).hexdigest()
    bytes_match = payload == expected_payload
    metadata_match = (
        stable_metadata.st_uid == _DESTINATION_UID
        and stable_metadata.st_gid == _DESTINATION_GID
        and stat.S_IMODE(stable_metadata.st_mode) == _DESTINATION_MODE
    )
    if not bytes_match:
        status = "PRESENT_DIFFERENT_BYTES"
    elif not metadata_match:
        status = "PRESENT_METADATA_MISMATCH"
    else:
        status = "MATCHED_CURRENT_RELEASE"

    return _destination_observation(
        status=status,
        present=True,
        destination_type="regular",
        metadata=stable_metadata,
        destination_sha256=digest,
        bytes_match=bytes_match,
        metadata_match=metadata_match,
    )


def _destination_observation(
    *,
    status: str,
    present: bool,
    destination_type: str,
    metadata: os.stat_result | None = None,
    destination_sha256: str | None = None,
    bytes_match: bool | None = None,
    metadata_match: bool | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "destination_present": present,
        "destination_type": destination_type,
        "destination_sha256": destination_sha256,
        "destination_uid": None if metadata is None else metadata.st_uid,
        "destination_gid": None if metadata is None else metadata.st_gid,
        "destination_mode": (
            None
            if metadata is None
            else f"{stat.S_IMODE(metadata.st_mode):04o}"
        ),
        "bytes_match_current_release": bytes_match,
        "metadata_match_expected": metadata_match,
    }


def _file_type(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    return "other"


def _production_paths() -> PaperManifestManagerStatusPaths:
    return PaperManifestManagerStatusPaths(
        current_link=Path("/opt/shreks/current"),
        destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
    )


def _canonical_json(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect the installed PAPER manifest manager against the exact "
            "sealed manager bytes in the current immutable Shreks release."
        )
    )
    parser.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = inspect_release_bound_paper_manifest_manager_status(
            expected_release_source_sha=args.expected_release_source_sha,
            paths=_production_paths(),
        )
    except (
        PaperManifestManagerStatusError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.write(
            _canonical_json(
                {
                    "schema_name": _SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "status": "INSPECTION_FAILED",
                    "error_type": type(error).__name__,
                    "observation_authority": "READ_ONLY",
                    "installation_authority": "NOT_EXERCISED",
                    "manifest_rotation_authority": "NOT_GRANTED",
                    "scoring_authority": "NOT_GRANTED",
                    "paper_promotion_authority": "BLOCKED",
                    "live_authority": "DISABLED",
                }
            )
        )
        return 1
    sys.stdout.write(_canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
