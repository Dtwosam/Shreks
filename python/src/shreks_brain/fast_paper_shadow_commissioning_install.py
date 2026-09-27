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

from .fast_paper_shadow_commissioning_assets import (
    FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES,
    decode_fast_paper_shadow_commissioning_manifest,
)


_RELEASE_MANIFEST_SCHEMA_VERSION = "g2-release-manifest-v1"
_SUPPORTED_PLATFORMS = frozenset(
    ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu")
)
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WHEEL_PATH_RE = re.compile(r"^wheelhouse/shreks_brain-[^/]+\.whl$")
_PACKAGE_PREFIX = "shreks_brain/_sealed_fast_paper_shadow_commissioning/"
_NESTED_MANIFEST_MEMBER = f"{_PACKAGE_PREFIX}manifest.json"
_UNIT_NAME = "shreks-fast-paper-shadow.service"
_ENV_EXAMPLE_NAME = "shreks-fast-paper-shadow.env.example"
_UNIT_MEMBER = f"{_PACKAGE_PREFIX}{_UNIT_NAME}"
_ENV_EXAMPLE_MEMBER = f"{_PACKAGE_PREFIX}{_ENV_EXAMPLE_NAME}"
_INIT_MEMBER = f"{_PACKAGE_PREFIX}__init__.py"

_PREFLIGHT_SCHEMA_NAME = "shreks.fast_paper_shadow_commissioning_preflight"
_INSTALL_SCHEMA_NAME = "shreks.fast_paper_shadow_commissioning_installation"
_SCHEMA_VERSION = 1

_DESTINATION_UID = 0
_DESTINATION_GID = 0
_DESTINATION_MODE = 0o644

_REQUIRED_UNIT_LINES = (
    "User=shreks",
    "Group=shreks",
    "WorkingDirectory=/opt/shreks/current",
    "EnvironmentFile=/etc/shreks/fast-paper-shadow.env",
    (
        "ExecStartPre=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.fast_paper_runtime.shadow_supervisor --preflight"
    ),
    (
        "ExecStart=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.fast_paper_runtime.shadow_supervisor"
    ),
    "PrivateNetwork=true",
    "ReadWritePaths=/var/lib/shreks/fast-paper-shadow",
)
_FORBIDDEN_UNIT_TEXT = (
    "WantedBy=shreks.target",
    "PartOf=shreks.target",
    "shreks-paper-campaign.service",
    "[Install]",
)


class FastPaperShadowCommissioningInstallError(RuntimeError):
    """Raised when dormant shadow-unit commissioning cannot be authenticated."""


@dataclass(frozen=True, slots=True)
class FastPaperShadowCommissioningInstallPaths:
    current_link: Path
    unit_destination: Path

    def __post_init__(self) -> None:
        for name in ("current_link", "unit_destination"):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise FastPaperShadowCommissioningInstallError(
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


@dataclass(frozen=True, slots=True)
class _AuthenticatedCommissioningUnit:
    release_dir: Path
    release_manifest: _ReleaseManifest
    wheel_record: _ReleaseFile
    wheel_sha256: str
    commissioning_manifest_fingerprint_sha256: str
    unit_payload: bytes
    unit_sha256: str


def preflight_release_bound_fast_paper_shadow_unit(
    *,
    expected_release_source_sha: str,
    paths: FastPaperShadowCommissioningInstallPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    _require_root()
    _require_exact_paths(paths)
    context = _authenticate_commissioning_unit(
        expected_release_source_sha=expected_release_source_sha,
        current_link=paths.current_link,
        runtime_executable=runtime_executable,
    )
    _require_safe_destination_parent(paths.unit_destination)
    installed = _inspect_existing_destination(
        paths.unit_destination,
        expected_payload=context.unit_payload,
    )
    return _receipt(
        schema_name=_PREFLIGHT_SCHEMA_NAME,
        status=(
            "READY_ALREADY_INSTALLED"
            if installed
            else "READY_TO_INSTALL"
        ),
        context=context,
        destination=paths.unit_destination,
    )


def install_release_bound_fast_paper_shadow_unit(
    *,
    expected_release_source_sha: str,
    paths: FastPaperShadowCommissioningInstallPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    _require_root()
    _require_exact_paths(paths)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    context = _authenticate_commissioning_unit(
        expected_release_source_sha=expected_sha,
        current_link=paths.current_link,
        runtime_executable=runtime_executable,
    )
    _require_safe_destination_parent(paths.unit_destination)

    if _inspect_existing_destination(
        paths.unit_destination,
        expected_payload=context.unit_payload,
    ):
        return _receipt(
            schema_name=_INSTALL_SCHEMA_NAME,
            status="ALREADY_INSTALLED",
            context=context,
            destination=paths.unit_destination,
        )

    current_before_publish = _require_current_release(
        paths.current_link,
        expected_sha,
    )
    if current_before_publish != context.release_dir:
        raise FastPaperShadowCommissioningInstallError(
            "current release changed before unit publication"
        )

    _publish_no_replace(paths.unit_destination, context.unit_payload)
    _require_installed_destination(
        paths.unit_destination,
        expected_payload=context.unit_payload,
    )
    return _receipt(
        schema_name=_INSTALL_SCHEMA_NAME,
        status="INSTALLED",
        context=context,
        destination=paths.unit_destination,
    )


def _production_paths() -> FastPaperShadowCommissioningInstallPaths:
    return FastPaperShadowCommissioningInstallPaths(
        current_link=Path("/opt/shreks/current"),
        unit_destination=Path(
            "/etc/systemd/system/shreks-fast-paper-shadow.service"
        ),
    )


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperShadowCommissioningInstallError(
            "Fast PAPER shadow commissioning requires root"
        )


def _require_exact_paths(
    paths: FastPaperShadowCommissioningInstallPaths,
) -> None:
    if type(paths) is not FastPaperShadowCommissioningInstallPaths:
        raise FastPaperShadowCommissioningInstallError(
            "paths must be exact FastPaperShadowCommissioningInstallPaths"
        )


def _authenticate_commissioning_unit(
    *,
    expected_release_source_sha: str,
    current_link: Path,
    runtime_executable: str | os.PathLike[str] | None,
) -> _AuthenticatedCommissioningUnit:
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release_dir = _require_current_release(current_link, expected_sha)
    executable = Path(
        sys.executable if runtime_executable is None else runtime_executable
    )
    _require_release_runtime_executable(release_dir, executable)

    manifest_payload, _ = _read_regular_no_follow(
        release_dir / "RELEASE_MANIFEST.json",
        label="current release manifest",
    )
    release_manifest = _decode_release_manifest(manifest_payload)
    if release_manifest.source_sha != expected_sha:
        raise FastPaperShadowCommissioningInstallError(
            "current release manifest source SHA does not match expected release"
        )

    wheel_record = _require_single_wheel_record(release_manifest)
    wheel_path = release_dir / PurePosixPath(wheel_record.path)
    wheel_payload, _ = _read_regular_no_follow(
        wheel_path,
        label="release wheel",
    )
    if len(wheel_payload) != wheel_record.size:
        raise FastPaperShadowCommissioningInstallError(
            "release wheel size does not match release manifest"
        )
    wheel_sha256 = hashlib.sha256(wheel_payload).hexdigest()
    if wheel_sha256 != wheel_record.sha256:
        raise FastPaperShadowCommissioningInstallError(
            "release wheel hash does not match release manifest"
        )

    nested_manifest, unit_payload = _extract_commissioning_package(
        wheel_payload
    )
    if nested_manifest.source_sha != expected_sha:
        raise FastPaperShadowCommissioningInstallError(
            "commissioning manifest source SHA does not match active release"
        )
    if nested_manifest.platform != release_manifest.platform:
        raise FastPaperShadowCommissioningInstallError(
            "commissioning manifest platform does not match release manifest"
        )

    _require_unit_safety(unit_payload)
    return _AuthenticatedCommissioningUnit(
        release_dir=release_dir,
        release_manifest=release_manifest,
        wheel_record=wheel_record,
        wheel_sha256=wheel_sha256,
        commissioning_manifest_fingerprint_sha256=(
            nested_manifest.manifest_fingerprint_sha256
        ),
        unit_payload=unit_payload,
        unit_sha256=hashlib.sha256(unit_payload).hexdigest(),
    )


def _validate_source_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowCommissioningInstallError(
            "expected release source SHA must be exactly 40 lowercase hex characters"
        )
    return value


def _require_current_release(
    current_link: Path,
    expected_sha: str,
) -> Path:
    if not current_link.is_symlink():
        raise FastPaperShadowCommissioningInstallError(
            "current release must be an existing symlink"
        )
    try:
        release_dir = current_link.resolve(strict=True)
    except OSError as exc:
        raise FastPaperShadowCommissioningInstallError(
            "current release symlink could not be resolved"
        ) from exc
    if not release_dir.is_dir() or release_dir.name != expected_sha:
        raise FastPaperShadowCommissioningInstallError(
            "current release directory does not match expected release SHA"
        )
    return release_dir


def _require_release_runtime_executable(
    release_dir: Path,
    executable: Path,
) -> None:
    try:
        if executable.is_symlink():
            raise FastPaperShadowCommissioningInstallError(
                "commissioning runtime executable must not be a symlink"
            )
        resolved_executable = executable.resolve(strict=True)
        expected_bin = (release_dir / ".venv" / "bin").resolve(strict=True)
    except OSError as exc:
        raise FastPaperShadowCommissioningInstallError(
            "commissioning runtime executable could not be resolved"
        ) from exc
    if (
        not resolved_executable.is_file()
        or resolved_executable.parent != expected_bin
    ):
        raise FastPaperShadowCommissioningInstallError(
            "commissioning must execute from the exact current release virtualenv"
        )


def _decode_release_manifest(payload: bytes) -> _ReleaseManifest:
    if not isinstance(payload, bytes):
        raise FastPaperShadowCommissioningInstallError(
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
        FastPaperShadowCommissioningInstallError,
    ) as exc:
        if isinstance(exc, FastPaperShadowCommissioningInstallError):
            raise
        raise FastPaperShadowCommissioningInstallError(
            "release manifest is not valid canonical JSON"
        ) from exc

    if not isinstance(raw, dict) or set(raw) != {
        "files",
        "platform",
        "schema_version",
        "source_sha",
    }:
        raise FastPaperShadowCommissioningInstallError(
            "release manifest keys are invalid"
        )
    if raw["schema_version"] != _RELEASE_MANIFEST_SCHEMA_VERSION:
        raise FastPaperShadowCommissioningInstallError(
            "release manifest schema is unsupported"
        )
    source_sha = _validate_source_sha(raw["source_sha"])
    platform = raw["platform"]
    if not isinstance(platform, str) or platform not in _SUPPORTED_PLATFORMS:
        raise FastPaperShadowCommissioningInstallError(
            "release manifest platform is unsupported"
        )
    raw_files = raw["files"]
    if not isinstance(raw_files, list):
        raise FastPaperShadowCommissioningInstallError(
            "release manifest files must be a list"
        )

    files: list[_ReleaseFile] = []
    seen: set[str] = set()
    for value in raw_files:
        if (
            not isinstance(value, dict)
            or set(value) != {"path", "sha256", "size"}
        ):
            raise FastPaperShadowCommissioningInstallError(
                "release manifest file record is invalid"
            )
        path = _validate_release_relative_path(value["path"])
        if path in seen:
            raise FastPaperShadowCommissioningInstallError(
                "release manifest contains duplicate file paths"
            )
        seen.add(path)
        size = value["size"]
        digest = value["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise FastPaperShadowCommissioningInstallError(
                "release manifest file size is invalid"
            )
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise FastPaperShadowCommissioningInstallError(
                "release manifest file hash is invalid"
            )
        files.append(_ReleaseFile(path=path, size=size, sha256=digest))

    if tuple(value.path for value in files) != tuple(
        sorted(value.path for value in files)
    ):
        raise FastPaperShadowCommissioningInstallError(
            "release manifest file records must be sorted"
        )

    if _canonical(raw).encode("utf-8") != payload:
        raise FastPaperShadowCommissioningInstallError(
            "release manifest must use canonical encoding"
        )
    return _ReleaseManifest(
        source_sha=source_sha,
        platform=platform,
        files=tuple(files),
    )


def _validate_release_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise FastPaperShadowCommissioningInstallError(
            "release manifest file path is invalid"
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or str(path) != value
    ):
        raise FastPaperShadowCommissioningInstallError(
            "release manifest file path is unsafe"
        )
    return value


def _require_single_wheel_record(
    manifest: _ReleaseManifest,
) -> _ReleaseFile:
    wheels = tuple(
        value
        for value in manifest.files
        if _WHEEL_PATH_RE.fullmatch(value.path)
    )
    if len(wheels) != 1:
        raise FastPaperShadowCommissioningInstallError(
            "release manifest must contain exactly one Shreks wheel"
        )
    return wheels[0]


def _extract_commissioning_package(wheel_payload: bytes):
    expected_members = {
        _INIT_MEMBER,
        _NESTED_MANIFEST_MEMBER,
        _UNIT_MEMBER,
        _ENV_EXAMPLE_MEMBER,
    }
    try:
        with zipfile.ZipFile(io.BytesIO(wheel_payload), "r") as archive:
            members = [
                info
                for info in archive.infolist()
                if info.filename.startswith(_PACKAGE_PREFIX)
            ]
            names = [info.filename for info in members]
            if (
                len(names) != len(set(names))
                or set(names) != expected_members
            ):
                raise FastPaperShadowCommissioningInstallError(
                    "release wheel commissioning package member set is invalid"
                )
            for info in members:
                if info.is_dir() or (info.flag_bits & 0x1):
                    raise FastPaperShadowCommissioningInstallError(
                        "release wheel commissioning package member is unsafe"
                    )
            nested_payload = archive.read(
                _NESTED_MANIFEST_MEMBER
            ).decode("utf-8")
            unit_payload = archive.read(_UNIT_MEMBER)
            env_payload = archive.read(_ENV_EXAMPLE_MEMBER)
    except FastPaperShadowCommissioningInstallError:
        raise
    except (
        KeyError,
        OSError,
        RuntimeError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        raise FastPaperShadowCommissioningInstallError(
            "release wheel commissioning package could not be read safely"
        ) from exc

    try:
        nested_manifest = decode_fast_paper_shadow_commissioning_manifest(
            nested_payload
        )
    except (TypeError, ValueError) as exc:
        raise FastPaperShadowCommissioningInstallError(
            "release wheel commissioning manifest is invalid"
        ) from exc

    records = {value.name: value for value in nested_manifest.assets}
    if set(records) != set(FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES):
        raise FastPaperShadowCommissioningInstallError(
            "release wheel commissioning manifest asset set is invalid"
        )
    payloads = {
        _UNIT_NAME: unit_payload,
        _ENV_EXAMPLE_NAME: env_payload,
    }
    for name, payload in payloads.items():
        record = records[name]
        if (
            len(payload) != record.size
            or hashlib.sha256(payload).hexdigest() != record.sha256
        ):
            raise FastPaperShadowCommissioningInstallError(
                f"release wheel commissioning asset fingerprint mismatch: {name}"
            )
    return nested_manifest, unit_payload


def _require_unit_safety(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FastPaperShadowCommissioningInstallError(
            "commissioning unit safety shape is invalid"
        ) from exc
    lines = set(text.splitlines())
    if any(required not in lines for required in _REQUIRED_UNIT_LINES):
        raise FastPaperShadowCommissioningInstallError(
            "commissioning unit safety shape is invalid"
        )
    if any(forbidden in text for forbidden in _FORBIDDEN_UNIT_TEXT):
        raise FastPaperShadowCommissioningInstallError(
            "commissioning unit safety shape is invalid"
        )


def _read_regular_no_follow(
    path: Path,
    *,
    label: str,
) -> tuple[bytes, os.stat_result]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FastPaperShadowCommissioningInstallError(
            f"{label} must be an existing regular non-symlink file"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise FastPaperShadowCommissioningInstallError(
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
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(payload) != before.st_size
        ):
            raise FastPaperShadowCommissioningInstallError(
                f"{label} changed while being read"
            )
        return payload, after
    finally:
        os.close(descriptor)


def _require_safe_destination_parent(destination: Path) -> None:
    parent = destination.parent
    try:
        metadata = parent.lstat()
    except OSError as exc:
        raise FastPaperShadowCommissioningInstallError(
            "commissioning unit destination parent is unavailable"
        ) from exc
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != _DESTINATION_UID
        or metadata.st_gid != _DESTINATION_GID
        or mode & 0o022
    ):
        raise FastPaperShadowCommissioningInstallError(
            "commissioning unit destination parent is unsafe"
        )


def _inspect_existing_destination(
    destination: Path,
    *,
    expected_payload: bytes,
) -> bool:
    try:
        payload, metadata = _read_regular_no_follow(
            destination,
            label="commissioning unit destination",
        )
    except FastPaperShadowCommissioningInstallError as exc:
        try:
            destination.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            raise
        raise exc

    if payload != expected_payload:
        raise FastPaperShadowCommissioningInstallError(
            "commissioning unit destination already exists with different bytes"
        )
    _require_destination_metadata(metadata)
    return True


def _require_destination_metadata(metadata: os.stat_result) -> None:
    if (
        metadata.st_uid != _DESTINATION_UID
        or metadata.st_gid != _DESTINATION_GID
        or stat.S_IMODE(metadata.st_mode) != _DESTINATION_MODE
    ):
        raise FastPaperShadowCommissioningInstallError(
            "commissioning unit destination metadata is not exact"
        )


def _publish_no_replace(destination: Path, payload: bytes) -> None:
    _require_safe_destination_parent(destination)
    parent = destination.parent
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
            os.fchown(
                handle.fileno(),
                _DESTINATION_UID,
                _DESTINATION_GID,
            )
            os.fchmod(handle.fileno(), _DESTINATION_MODE)
            os.fsync(handle.fileno())

        try:
            os.link(temporary, destination, follow_symlinks=False)
            linked = True
        except FileExistsError as exc:
            raise FastPaperShadowCommissioningInstallError(
                "commissioning unit destination appeared during publication"
            ) from exc
        except OSError as exc:
            raise FastPaperShadowCommissioningInstallError(
                "commissioning unit could not be published"
            ) from exc

        temporary.unlink()
        _fsync_directory(parent)
    except Exception:
        try:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
        except OSError:
            pass
        if linked:
            try:
                _fsync_directory(parent)
            except FastPaperShadowCommissioningInstallError:
                pass
        raise


def _require_installed_destination(
    destination: Path,
    *,
    expected_payload: bytes,
) -> None:
    payload, metadata = _read_regular_no_follow(
        destination,
        label="installed commissioning unit",
    )
    if payload != expected_payload:
        raise FastPaperShadowCommissioningInstallError(
            "installed commissioning unit bytes do not match sealed release"
        )
    _require_destination_metadata(metadata)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise FastPaperShadowCommissioningInstallError(
            "commissioning unit destination directory could not be synced"
        ) from exc


def _receipt(
    *,
    schema_name: str,
    status: str,
    context: _AuthenticatedCommissioningUnit,
    destination: Path,
) -> dict[str, object]:
    material: dict[str, object] = {
        "schema_name": schema_name,
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "release_source_sha": context.release_manifest.source_sha,
        "release_dir": str(context.release_dir),
        "wheel_relative_path": context.wheel_record.path,
        "wheel_sha256": context.wheel_sha256,
        "commissioning_manifest_fingerprint_sha256": (
            context.commissioning_manifest_fingerprint_sha256
        ),
        "unit_sha256": context.unit_sha256,
        "unit_destination": str(destination),
        "unit_destination_uid": _DESTINATION_UID,
        "unit_destination_gid": _DESTINATION_GID,
        "unit_destination_mode": "0644",
        "service_activation_authority": "NOT_GRANTED",
        "paper_cutover_authority": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return {
        **material,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FastPaperShadowCommissioningInstallError(
                "JSON objects must not contain duplicate keys"
            )
        result[key] = value
    return result


def _reject_non_finite_json(value: str) -> object:
    raise FastPaperShadowCommissioningInstallError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _failure_document(error: BaseException) -> str:
    return _canonical(
        {
            "schema_name": (
                "shreks.fast_paper_shadow_commissioning_failure"
            ),
            "schema_version": _SCHEMA_VERSION,
            "status": "FAILED",
            "error_type": type(error).__name__,
            "service_activation_authority": "NOT_GRANTED",
            "paper_cutover_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-commissioning"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("expected_release_source_sha")
    install = commands.add_parser("install")
    install.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight_release_bound_fast_paper_shadow_unit(
                expected_release_source_sha=(
                    args.expected_release_source_sha
                ),
                paths=_production_paths(),
            )
        else:
            result = install_release_bound_fast_paper_shadow_unit(
                expected_release_source_sha=(
                    args.expected_release_source_sha
                ),
                paths=_production_paths(),
            )
    except FastPaperShadowCommissioningInstallError as exc:
        print(_failure_document(exc), end="", file=sys.stderr)
        return 1
    print(_canonical(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
