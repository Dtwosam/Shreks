#!/usr/bin/env python3

import argparse
import gzip
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile


RELEASE_MANIFEST_SCHEMA_VERSION = "g2-release-manifest-v1"
SUPPORTED_PLATFORM = "x86_64-unknown-linux-gnu"

_REQUIRED_STATIC_PAYLOAD_PATHS = (
    "deploy/systemd/shreks-observe.service",
    "deploy/systemd/shreks-paper-campaign.service",
    "deploy/systemd/shreks-paper-evidence.service",
    "deploy/systemd/shreks-telemetry.service",
    "deploy/systemd/shreks-telemetry.timer",
    "deploy/systemd/shreks.target",
    "target/release/shreks-observe",
    "target/release/shreks-paper-evidence",
)
_WHEEL_PATH_RE = re.compile(r"^wheelhouse/shreks_brain-[^/]+\.whl$")
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_MANIFEST_PATH = "RELEASE_MANIFEST.json"


class ReleaseBundleError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ReleaseManifest:
    schema_version: str
    source_sha: str
    platform: str
    files: tuple[ReleaseFile, ...]


def validate_source_sha(value: str) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise ReleaseBundleError("source_sha must be exactly 40 lowercase hex characters")
    return value


def release_tag_for_sha(source_sha: str) -> str:
    return f"shreks-{validate_source_sha(source_sha)}"


def _validate_platform(value: str) -> str:
    if value != SUPPORTED_PLATFORM:
        raise ReleaseBundleError(f"unsupported release platform: {value!r}")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_release_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseBundleError("release file path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ReleaseBundleError(f"unsafe release path: {value!r}")
    if str(path) != value or "\\" in value:
        raise ReleaseBundleError(f"non-canonical release path: {value!r}")
    return value


def _validate_payload_paths(paths: tuple[str, ...] | list[str] | set[str]) -> None:
    normalized = tuple(sorted(paths))
    if len(normalized) != len(set(normalized)):
        raise ReleaseBundleError("duplicate release payload path")

    static = set(_REQUIRED_STATIC_PAYLOAD_PATHS)
    actual = set(normalized)
    missing = static - actual
    if missing:
        raise ReleaseBundleError(f"missing required release payloads: {sorted(missing)!r}")

    non_static = actual - static
    wheel_paths = sorted(path for path in non_static if _WHEEL_PATH_RE.fullmatch(path))
    unexpected = sorted(non_static - set(wheel_paths))
    if unexpected:
        raise ReleaseBundleError(f"unexpected release payloads: {unexpected!r}")
    if len(wheel_paths) != 1:
        raise ReleaseBundleError("release must contain exactly one shreks_brain wheel")


def _regular_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        raise ReleaseBundleError(f"release staging directory does not exist: {root}")

    result: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ReleaseBundleError(f"symlink not allowed in release tree: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ReleaseBundleError(f"non-regular file not allowed in release tree: {path}")
        relative = path.relative_to(root).as_posix()
        _validate_release_path(relative)
        result[relative] = path
    return result


def build_release_manifest(
    staging_dir: Path, source_sha: str, platform: str
) -> ReleaseManifest:
    source_sha = validate_source_sha(source_sha)
    platform = _validate_platform(platform)
    files = _regular_files(Path(staging_dir))
    files.pop(_CONTROL_MANIFEST_PATH, None)
    _validate_payload_paths(tuple(files))

    entries = tuple(
        ReleaseFile(
            path=relative,
            size=path.stat().st_size,
            sha256=_sha256_bytes(path.read_bytes()),
        )
        for relative, path in sorted(files.items())
    )
    return ReleaseManifest(
        schema_version=RELEASE_MANIFEST_SCHEMA_VERSION,
        source_sha=source_sha,
        platform=platform,
        files=entries,
    )


def _manifest_object(manifest: ReleaseManifest) -> dict[str, object]:
    return {
        "files": [
            {"path": entry.path, "sha256": entry.sha256, "size": entry.size}
            for entry in manifest.files
        ],
        "platform": manifest.platform,
        "schema_version": manifest.schema_version,
        "source_sha": manifest.source_sha,
    }


def encode_release_manifest(manifest: ReleaseManifest) -> bytes:
    _validate_manifest(manifest)
    return (
        json.dumps(_manifest_object(manifest), sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _require_exact_keys(value: object, expected: set[str], context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReleaseBundleError(f"{context} must be an object")
    if set(value) != expected:
        raise ReleaseBundleError(f"{context} keys must be exactly {sorted(expected)!r}")
    return value


def _decode_release_file(value: object) -> ReleaseFile:
    obj = _require_exact_keys(value, {"path", "sha256", "size"}, "release file")
    path = _validate_release_path(obj["path"])
    size = obj["size"]
    digest = obj["sha256"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ReleaseBundleError("release file size must be a non-negative integer")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise ReleaseBundleError("release file sha256 must be lowercase 64-character hex")
    return ReleaseFile(path=path, size=size, sha256=digest)


def decode_release_manifest(payload: bytes) -> ReleaseManifest:
    if not isinstance(payload, bytes):
        raise ReleaseBundleError("manifest payload must be bytes")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseBundleError("invalid release manifest JSON") from exc

    obj = _require_exact_keys(
        raw,
        {"files", "platform", "schema_version", "source_sha"},
        "release manifest",
    )
    if obj["schema_version"] != RELEASE_MANIFEST_SCHEMA_VERSION:
        raise ReleaseBundleError("unsupported release manifest schema_version")
    source_sha = validate_source_sha(obj["source_sha"])
    platform = _validate_platform(obj["platform"])
    raw_files = obj["files"]
    if not isinstance(raw_files, list):
        raise ReleaseBundleError("release manifest files must be a list")
    files = tuple(_decode_release_file(value) for value in raw_files)
    manifest = ReleaseManifest(
        schema_version=RELEASE_MANIFEST_SCHEMA_VERSION,
        source_sha=source_sha,
        platform=platform,
        files=files,
    )
    _validate_manifest(manifest)
    if encode_release_manifest(manifest) != payload:
        raise ReleaseBundleError("release manifest must use canonical encoding")
    return manifest


def _validate_manifest(manifest: ReleaseManifest) -> None:
    if manifest.schema_version != RELEASE_MANIFEST_SCHEMA_VERSION:
        raise ReleaseBundleError("unsupported release manifest schema_version")
    validate_source_sha(manifest.source_sha)
    _validate_platform(manifest.platform)
    paths = tuple(entry.path for entry in manifest.files)
    if paths != tuple(sorted(paths)):
        raise ReleaseBundleError("release manifest files must be sorted by path")
    _validate_payload_paths(paths)
    for entry in manifest.files:
        _validate_release_path(entry.path)
        if not isinstance(entry.size, int) or isinstance(entry.size, bool) or entry.size < 0:
            raise ReleaseBundleError("release file size must be a non-negative integer")
        if _SHA256_RE.fullmatch(entry.sha256) is None:
            raise ReleaseBundleError("release file sha256 must be lowercase 64-character hex")


def verify_release_tree(root: Path, manifest: ReleaseManifest) -> None:
    _validate_manifest(manifest)
    root = Path(root)
    files = _regular_files(root)
    control_path = files.pop(_CONTROL_MANIFEST_PATH, None)
    expected = {entry.path: entry for entry in manifest.files}
    if set(files) != set(expected):
        missing = sorted(set(expected) - set(files))
        unexpected = sorted(set(files) - set(expected))
        raise ReleaseBundleError(
            f"release tree mismatch: missing={missing!r} unexpected={unexpected!r}"
        )

    for relative, entry in expected.items():
        payload = files[relative].read_bytes()
        if len(payload) != entry.size or _sha256_bytes(payload) != entry.sha256:
            raise ReleaseBundleError(f"release payload verification failed: {relative}")

    if control_path is not None and control_path.read_bytes() != encode_release_manifest(manifest):
        raise ReleaseBundleError("embedded RELEASE_MANIFEST.json does not match manifest")


def _safe_archive_member_name(member: tarfile.TarInfo) -> str:
    name = _validate_release_path(member.name)
    if not member.isreg():
        raise ReleaseBundleError(f"release archive member must be a regular file: {name}")
    return name


def _archive_mode(relative: str) -> int:
    if relative.startswith("target/release/"):
        return 0o755
    return 0o644


def write_release_archive(
    staging_dir: Path, manifest: ReleaseManifest, archive_path: Path
) -> str:
    staging_dir = Path(staging_dir)
    archive_path = Path(archive_path)
    expected_manifest = encode_release_manifest(manifest)
    control_path = staging_dir / _CONTROL_MANIFEST_PATH
    if not control_path.is_file() or control_path.read_bytes() != expected_manifest:
        raise ReleaseBundleError(
            "staging tree must contain canonical RELEASE_MANIFEST.json before archiving"
        )
    verify_release_tree(staging_dir, manifest)

    member_names = [entry.path for entry in manifest.files] + [_CONTROL_MANIFEST_PATH]
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for relative in sorted(member_names):
                    payload = (staging_dir / relative).read_bytes()
                    info = tarfile.TarInfo(relative)
                    info.size = len(payload)
                    info.mode = _archive_mode(relative)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(payload))

    return _sha256_bytes(archive_path.read_bytes())


def _verify_checksum(archive_path: Path, checksum_path: Path) -> None:
    try:
        line = Path(checksum_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseBundleError("unable to read release checksum") from exc
    parts = line.strip().split()
    if len(parts) != 2 or _SHA256_RE.fullmatch(parts[0]) is None:
        raise ReleaseBundleError("invalid release checksum sidecar")
    if parts[1] != Path(archive_path).name:
        raise ReleaseBundleError("release checksum filename does not match archive")
    actual = _sha256_bytes(Path(archive_path).read_bytes())
    if actual != parts[0]:
        raise ReleaseBundleError("release archive checksum mismatch")


def _read_safe_archive_members(archive_path: Path) -> dict[str, bytes]:
    try:
        archive = tarfile.open(archive_path, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseBundleError("invalid release archive") from exc

    payloads: dict[str, bytes] = {}
    with archive:
        for member in archive.getmembers():
            name = _safe_archive_member_name(member)
            if name in payloads:
                raise ReleaseBundleError(f"duplicate release archive member: {name}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ReleaseBundleError(f"unable to read release archive member: {name}")
            payloads[name] = extracted.read()
    return payloads


def verify_release_archive(
    archive_path: Path, checksum_path: Path, manifest_path: Path
) -> ReleaseManifest:
    archive_path = Path(archive_path)
    _verify_checksum(archive_path, Path(checksum_path))
    archive_payloads = _read_safe_archive_members(archive_path)

    try:
        external_manifest_payload = Path(manifest_path).read_bytes()
    except OSError as exc:
        raise ReleaseBundleError("unable to read external release manifest") from exc
    manifest = decode_release_manifest(external_manifest_payload)

    expected_names = {entry.path for entry in manifest.files} | {_CONTROL_MANIFEST_PATH}
    if set(archive_payloads) != expected_names:
        missing = sorted(expected_names - set(archive_payloads))
        unexpected = sorted(set(archive_payloads) - expected_names)
        raise ReleaseBundleError(
            f"release archive member mismatch: missing={missing!r} unexpected={unexpected!r}"
        )
    if archive_payloads[_CONTROL_MANIFEST_PATH] != external_manifest_payload:
        raise ReleaseBundleError("embedded and external release manifests differ")

    expected = {entry.path: entry for entry in manifest.files}
    for relative, entry in expected.items():
        payload = archive_payloads[relative]
        if len(payload) != entry.size or _sha256_bytes(payload) != entry.sha256:
            raise ReleaseBundleError(f"release archive payload verification failed: {relative}")
    return manifest


def build_release_artifacts(
    staging_dir: Path,
    source_sha: str,
    platform: str,
    out_dir: Path,
) -> tuple[Path, Path, Path]:
    staging_dir = Path(staging_dir)
    out_dir = Path(out_dir)
    manifest = build_release_manifest(staging_dir, source_sha, platform)
    manifest_payload = encode_release_manifest(manifest)
    control_manifest = staging_dir / _CONTROL_MANIFEST_PATH
    control_manifest.write_bytes(manifest_payload)

    out_dir.mkdir(parents=True, exist_ok=True)
    external_manifest = out_dir / _CONTROL_MANIFEST_PATH
    external_manifest.write_bytes(manifest_payload)
    archive_path = out_dir / f"shreks-release-{manifest.source_sha}.tar.gz"
    archive_sha = write_release_archive(staging_dir, manifest, archive_path)
    checksum_path = out_dir / f"{archive_path.name}.sha256"
    checksum_path.write_text(
        f"{archive_sha}  {archive_path.name}\n",
        encoding="utf-8",
    )
    verify_release_archive(archive_path, checksum_path, external_manifest)
    return archive_path, checksum_path, external_manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and verify Shreks release bundles")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--staging", required=True, type=Path)
    build.add_argument("--source-sha", required=True)
    build.add_argument("--platform", default=SUPPORTED_PLATFORM)
    build.add_argument("--out-dir", required=True, type=Path)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", required=True, type=Path)
    verify.add_argument("--checksum", required=True, type=Path)
    verify.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "build":
            build_release_artifacts(
                args.staging,
                args.source_sha,
                args.platform,
                args.out_dir,
            )
        else:
            verify_release_archive(args.archive, args.checksum, args.manifest)
    except (OSError, ReleaseBundleError) as exc:
        print(f"release bundle error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
