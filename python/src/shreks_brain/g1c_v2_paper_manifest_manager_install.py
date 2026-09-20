from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import zipfile


_RELEASE_MANIFEST_SCHEMA_VERSION = "g2-release-manifest-v1"
_SUPPORTED_PLATFORMS = frozenset(
    ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu")
)
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WHEEL_PATH_RE = re.compile(r"^wheelhouse/shreks_brain-[^/]+\.whl$")
_MANAGER_MEMBER = "shreks_brain/_sealed_deploy_control/paper_manifest_manager.py"
_MANAGER_SHEBANG = b"#!/opt/shreks/current/.venv/bin/python\n"
_RECEIPT_SCHEMA_NAME = "shreks.g1c_v2_paper_manifest_manager_installation"
_RECEIPT_SCHEMA_VERSION = 1
_DESTINATION_MODE = 0o755
_DESTINATION_UID = 0
_DESTINATION_GID = 0


class PaperManifestManagerInstallError(RuntimeError):
    """Raised when the exact release-bound PAPER manifest manager cannot be installed."""


@dataclass(frozen=True, slots=True)
class PaperManifestManagerInstallPaths:
    current_link: Path
    destination: Path

    def __post_init__(self) -> None:
        for name in ("current_link", "destination"):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise PaperManifestManagerInstallError(
                    f"{name} must be an absolute Path"
                )


@dataclass(frozen=True, slots=True)
class _ReleaseFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _ReleaseManifest:
    source_sha: str
    platform: str
    files: tuple[_ReleaseFile, ...]


def install_release_bound_paper_manifest_manager(
    *,
    expected_release_source_sha: str,
    paths: PaperManifestManagerInstallPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    if type(paths) is not PaperManifestManagerInstallPaths:
        raise PaperManifestManagerInstallError(
            "install paths must be an exact PaperManifestManagerInstallPaths"
        )
    if os.geteuid() != 0:
        raise PaperManifestManagerInstallError(
            "PAPER manifest manager installation requires root"
        )

    expected_sha = _validate_source_sha(expected_release_source_sha)
    release_dir = _require_current_release(paths.current_link, expected_sha)
    _require_release_runtime_executable(
        release_dir,
        Path(sys.executable if runtime_executable is None else runtime_executable),
    )

    manifest_payload, _ = _read_regular_no_follow(
        release_dir / "RELEASE_MANIFEST.json",
        label="current release manifest",
    )
    manifest = _decode_release_manifest(manifest_payload)
    if manifest.source_sha != expected_sha:
        raise PaperManifestManagerInstallError(
            "current release manifest source SHA does not match expected release"
        )

    wheel_record = _require_single_wheel_record(manifest)
    wheel_path = release_dir / PurePosixPath(wheel_record.path)
    wheel_payload, _ = _read_regular_no_follow(
        wheel_path,
        label="release wheel",
    )
    if len(wheel_payload) != wheel_record.size:
        raise PaperManifestManagerInstallError(
            "release wheel size does not match release manifest"
        )
    wheel_sha256 = hashlib.sha256(wheel_payload).hexdigest()
    if wheel_sha256 != wheel_record.sha256:
        raise PaperManifestManagerInstallError(
            "release wheel hash does not match release manifest"
        )

    manager_payload = _extract_manager_payload(wheel_payload)
    manager_sha256 = hashlib.sha256(manager_payload).hexdigest()

    existing = _inspect_existing_destination(
        paths.destination,
        expected_payload=manager_payload,
    )
    if existing:
        return _receipt(
            status="ALREADY_INSTALLED",
            expected_release_source_sha=expected_sha,
            release_dir=release_dir,
            wheel_record=wheel_record,
            wheel_sha256=wheel_sha256,
            manager_sha256=manager_sha256,
            destination=paths.destination,
        )

    _publish_no_replace(paths.destination, manager_payload)
    _require_installed_destination(
        paths.destination,
        expected_payload=manager_payload,
    )
    return _receipt(
        status="INSTALLED",
        expected_release_source_sha=expected_sha,
        release_dir=release_dir,
        wheel_record=wheel_record,
        wheel_sha256=wheel_sha256,
        manager_sha256=manager_sha256,
        destination=paths.destination,
    )


def _production_paths() -> PaperManifestManagerInstallPaths:
    return PaperManifestManagerInstallPaths(
        current_link=Path("/opt/shreks/current"),
        destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
    )


def _validate_source_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise PaperManifestManagerInstallError(
            "expected release source SHA must be exactly 40 lowercase hex characters"
        )
    return value


def _require_current_release(current_link: Path, expected_sha: str) -> Path:
    if not current_link.is_symlink():
        raise PaperManifestManagerInstallError(
            "current release must be an existing symlink"
        )
    try:
        release_dir = current_link.resolve(strict=True)
    except OSError as error:
        raise PaperManifestManagerInstallError(
            "current release symlink could not be resolved"
        ) from error
    if not release_dir.is_dir() or release_dir.name != expected_sha:
        raise PaperManifestManagerInstallError(
            "current release directory does not match expected release SHA"
        )
    return release_dir


def _require_release_runtime_executable(
    release_dir: Path,
    executable: Path,
) -> None:
    try:
        if executable.is_symlink():
            raise PaperManifestManagerInstallError(
                "installer runtime executable must not be a symlink"
            )
        resolved_executable = executable.resolve(strict=True)
        expected_bin = (release_dir / ".venv" / "bin").resolve(strict=True)
    except OSError as error:
        raise PaperManifestManagerInstallError(
            "installer runtime executable could not be resolved"
        ) from error
    if not resolved_executable.is_file() or resolved_executable.parent != expected_bin:
        raise PaperManifestManagerInstallError(
            "installer must execute from the exact current release virtualenv"
        )


def _decode_release_manifest(payload: bytes) -> _ReleaseManifest:
    if not isinstance(payload, bytes):
        raise PaperManifestManagerInstallError(
            "release manifest payload must be bytes"
        )
    try:
        raw = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_json,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        PaperManifestManagerInstallError,
    ) as error:
        if isinstance(error, PaperManifestManagerInstallError):
            raise
        raise PaperManifestManagerInstallError(
            "release manifest is not valid canonical JSON"
        ) from error

    if not isinstance(raw, dict) or set(raw) != {
        "files",
        "platform",
        "schema_version",
        "source_sha",
    }:
        raise PaperManifestManagerInstallError(
            "release manifest keys are invalid"
        )
    if raw["schema_version"] != _RELEASE_MANIFEST_SCHEMA_VERSION:
        raise PaperManifestManagerInstallError(
            "release manifest schema is unsupported"
        )
    source_sha = _validate_source_sha(raw["source_sha"])
    platform = raw["platform"]
    if not isinstance(platform, str) or platform not in _SUPPORTED_PLATFORMS:
        raise PaperManifestManagerInstallError(
            "release manifest platform is unsupported"
        )
    raw_files = raw["files"]
    if not isinstance(raw_files, list):
        raise PaperManifestManagerInstallError(
            "release manifest files must be a list"
        )

    files: list[_ReleaseFile] = []
    seen: set[str] = set()
    for value in raw_files:
        if not isinstance(value, dict) or set(value) != {"path", "sha256", "size"}:
            raise PaperManifestManagerInstallError(
                "release manifest file record is invalid"
            )
        path = _validate_release_relative_path(value["path"])
        if path in seen:
            raise PaperManifestManagerInstallError(
                "release manifest contains duplicate file paths"
            )
        seen.add(path)
        size = value["size"]
        digest = value["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise PaperManifestManagerInstallError(
                "release manifest file size is invalid"
            )
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise PaperManifestManagerInstallError(
                "release manifest file hash is invalid"
            )
        files.append(_ReleaseFile(path=path, size=size, sha256=digest))

    if tuple(record.path for record in files) != tuple(
        sorted(record.path for record in files)
    ):
        raise PaperManifestManagerInstallError(
            "release manifest file records must be sorted"
        )

    canonical = (
        json.dumps(
            raw,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if canonical != payload:
        raise PaperManifestManagerInstallError(
            "release manifest must use canonical encoding"
        )

    return _ReleaseManifest(
        source_sha=source_sha,
        platform=platform,
        files=tuple(files),
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PaperManifestManagerInstallError(
                "JSON objects must not contain duplicate keys"
            )
        result[key] = value
    return result


def _reject_non_finite_json(value: str) -> object:
    raise PaperManifestManagerInstallError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _validate_release_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PaperManifestManagerInstallError(
            "release manifest file path is invalid"
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or str(path) != value
    ):
        raise PaperManifestManagerInstallError(
            "release manifest file path is unsafe"
        )
    return value


def _require_single_wheel_record(
    manifest: _ReleaseManifest,
) -> _ReleaseFile:
    wheels = tuple(
        record
        for record in manifest.files
        if _WHEEL_PATH_RE.fullmatch(record.path)
    )
    if len(wheels) != 1:
        raise PaperManifestManagerInstallError(
            "release manifest must contain exactly one Shreks wheel"
        )
    return wheels[0]


def _extract_manager_payload(wheel_payload: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(wheel_payload), "r") as archive:
            matches = tuple(
                info
                for info in archive.infolist()
                if info.filename == _MANAGER_MEMBER
            )
            if len(matches) != 1:
                raise PaperManifestManagerInstallError(
                    "release wheel must contain exactly one sealed PAPER manifest manager"
                )
            info = matches[0]
            if info.is_dir() or (info.flag_bits & 0x1):
                raise PaperManifestManagerInstallError(
                    "sealed PAPER manifest manager wheel member is unsafe"
                )
            payload = archive.read(info)
    except PaperManifestManagerInstallError:
        raise
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as error:
        raise PaperManifestManagerInstallError(
            "release wheel could not be read safely"
        ) from error

    if not payload.startswith(_MANAGER_SHEBANG):
        raise PaperManifestManagerInstallError(
            "sealed PAPER manifest manager payload is not the expected executable"
        )
    return payload


def _read_regular_no_follow(
    path: Path,
    *,
    label: str,
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise PaperManifestManagerInstallError(
            f"{label} must be an existing regular non-symlink file"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PaperManifestManagerInstallError(
                f"{label} must be a regular file"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            metadata.st_dev != after.st_dev
            or metadata.st_ino != after.st_ino
            or metadata.st_size != after.st_size
            or metadata.st_mtime_ns != after.st_mtime_ns
            or len(payload) != metadata.st_size
        ):
            raise PaperManifestManagerInstallError(
                f"{label} changed while being read"
            )
        return payload, after
    finally:
        os.close(descriptor)


def _inspect_existing_destination(
    destination: Path,
    *,
    expected_payload: bytes,
) -> bool:
    try:
        payload, metadata = _read_regular_no_follow(
            destination,
            label="PAPER manifest manager destination",
        )
    except PaperManifestManagerInstallError as error:
        try:
            destination.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            raise
        raise error

    if payload != expected_payload:
        raise PaperManifestManagerInstallError(
            "PAPER manifest manager destination already exists with different bytes"
        )
    _require_destination_metadata(metadata)
    return True


def _require_destination_metadata(metadata: os.stat_result) -> None:
    if (
        metadata.st_uid != _DESTINATION_UID
        or metadata.st_gid != _DESTINATION_GID
        or stat.S_IMODE(metadata.st_mode) != _DESTINATION_MODE
    ):
        raise PaperManifestManagerInstallError(
            "PAPER manifest manager destination metadata is not exact"
        )


def _publish_no_replace(destination: Path, payload: bytes) -> None:
    parent = destination.parent
    try:
        parent_metadata = parent.lstat()
    except OSError as error:
        raise PaperManifestManagerInstallError(
            "PAPER manifest manager destination parent is unavailable"
        ) from error
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(parent_metadata.st_mode):
        raise PaperManifestManagerInstallError(
            "PAPER manifest manager destination parent is unsafe"
        )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.install-",
        dir=parent,
    )
    temporary = Path(temporary_name)
    linked = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), _DESTINATION_UID, _DESTINATION_GID)
            os.fchmod(handle.fileno(), _DESTINATION_MODE)
            os.fsync(handle.fileno())

        try:
            os.link(
                temporary,
                destination,
                follow_symlinks=False,
            )
            linked = True
        except FileExistsError as error:
            raise PaperManifestManagerInstallError(
                "PAPER manifest manager destination appeared during installation"
            ) from error
        except OSError as error:
            raise PaperManifestManagerInstallError(
                "PAPER manifest manager could not be published"
            ) from error

        temporary.unlink()
        _fsync_directory(parent)
    except Exception:
        try:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
        except OSError:
            pass
        if linked:
            # The destination is intentionally left in place once published.
            # The caller verifies exact bytes and metadata before claiming success.
            try:
                _fsync_directory(parent)
            except PaperManifestManagerInstallError:
                pass
        raise


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise PaperManifestManagerInstallError(
            "PAPER manifest manager destination directory could not be synced"
        ) from error


def _require_installed_destination(
    destination: Path,
    *,
    expected_payload: bytes,
) -> None:
    payload, metadata = _read_regular_no_follow(
        destination,
        label="installed PAPER manifest manager",
    )
    if payload != expected_payload:
        raise PaperManifestManagerInstallError(
            "installed PAPER manifest manager bytes do not match sealed release"
        )
    _require_destination_metadata(metadata)


def _receipt(
    *,
    status: str,
    expected_release_source_sha: str,
    release_dir: Path,
    wheel_record: _ReleaseFile,
    wheel_sha256: str,
    manager_sha256: str,
    destination: Path,
) -> dict[str, object]:
    return {
        "schema_name": _RECEIPT_SCHEMA_NAME,
        "schema_version": _RECEIPT_SCHEMA_VERSION,
        "status": status,
        "release_source_sha": expected_release_source_sha,
        "release_directory": str(release_dir),
        "wheel_relative_path": wheel_record.path,
        "wheel_sha256": wheel_sha256,
        "wheel_member": _MANAGER_MEMBER,
        "manager_sha256": manager_sha256,
        "destination": str(destination),
        "destination_uid": _DESTINATION_UID,
        "destination_gid": _DESTINATION_GID,
        "destination_mode": "0755",
        "installation_authority": "EXERCISED_EXACT_RELEASE_BOUND_HELPER_ONLY",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }


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
            "Install the exact sealed PAPER manifest manager from the current "
            "immutable Shreks release without replacing an existing different helper."
        )
    )
    parser.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        receipt = install_release_bound_paper_manifest_manager(
            expected_release_source_sha=args.expected_release_source_sha,
            paths=_production_paths(),
        )
    except (
        PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.write(
            _canonical_json(
                {
                    "schema_name": _RECEIPT_SCHEMA_NAME,
                    "schema_version": _RECEIPT_SCHEMA_VERSION,
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                    "manifest_rotation_authority": "NOT_GRANTED",
                    "scoring_authority": "NOT_GRANTED",
                    "paper_promotion_authority": "BLOCKED",
                    "live_authority": "DISABLED",
                }
            )
        )
        return 1
    sys.stdout.write(_canonical_json(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
