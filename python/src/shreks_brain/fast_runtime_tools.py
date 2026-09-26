from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.resources import as_file, files
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile


FAST_RUNTIME_TOOLS_SCHEMA_NAME = "shreks.fast_runtime_tools"
FAST_RUNTIME_TOOLS_SCHEMA_VERSION = 1
FAST_RUNTIME_FEATURE_TOOL_NAME = "export_fast_runtime_features"

_SUPPORTED_PLATFORMS = frozenset(
    (
        "x86_64-unknown-linux-gnu",
        "aarch64-unknown-linux-gnu",
    )
)
_PACKAGE_PREFIX = "shreks_brain/_sealed_fast_runtime_tools/"
_MANIFEST_NAME = "manifest.json"
_INIT_NAME = "__init__.py"
_BINARY_NAME = f"{FAST_RUNTIME_FEATURE_TOOL_NAME}.bin"
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "source_sha",
        "platform",
        "tool_name",
        "size",
        "sha256",
        "manifest_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastRuntimeToolsManifest:
    schema_name: str
    schema_version: int
    source_sha: str
    platform: str
    tool_name: str
    size: int
    sha256: str
    manifest_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_RUNTIME_TOOLS_SCHEMA_NAME:
            raise ValueError("unsupported Fast runtime tools schema_name")
        if self.schema_version != FAST_RUNTIME_TOOLS_SCHEMA_VERSION:
            raise ValueError("unsupported Fast runtime tools schema_version")
        _require_source_sha(self.source_sha)
        if self.platform not in _SUPPORTED_PLATFORMS:
            raise ValueError("unsupported Fast runtime tools platform")
        if self.tool_name != FAST_RUNTIME_FEATURE_TOOL_NAME:
            raise ValueError("unsupported Fast runtime tool name")
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise ValueError("Fast runtime tool size must be non-negative")
        _require_sha256("Fast runtime tool SHA-256", self.sha256)
        _require_sha256(
            "Fast runtime tools manifest fingerprint",
            self.manifest_fingerprint_sha256,
        )


def build_fast_runtime_tools_manifest(
    *,
    source_sha: str,
    platform: str,
    tool: str | Path,
) -> FastRuntimeToolsManifest:
    _require_source_sha(source_sha)
    if platform not in _SUPPORTED_PLATFORMS:
        raise ValueError("unsupported Fast runtime tools platform")
    path = _require_tool_path(tool)
    material = {
        "schema_name": FAST_RUNTIME_TOOLS_SCHEMA_NAME,
        "schema_version": FAST_RUNTIME_TOOLS_SCHEMA_VERSION,
        "source_sha": source_sha,
        "platform": platform,
        "tool_name": FAST_RUNTIME_FEATURE_TOOL_NAME,
        "size": path.stat().st_size,
        "sha256": _sha256_file(path),
    }
    return FastRuntimeToolsManifest(
        **material,
        manifest_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_runtime_tools_manifest(
    manifest: FastRuntimeToolsManifest,
) -> str:
    if type(manifest) is not FastRuntimeToolsManifest:
        raise ValueError("manifest must be an exact FastRuntimeToolsManifest")
    material = _manifest_material(manifest)
    if _sha256_canonical(material) != manifest.manifest_fingerprint_sha256:
        raise ValueError("Fast runtime tools manifest fingerprint mismatch")
    return _canonical(
        {
            **material,
            "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        }
    ) + "\n"


def decode_fast_runtime_tools_manifest(
    payload: str,
) -> FastRuntimeToolsManifest:
    if not isinstance(payload, str) or not payload:
        raise ValueError("Fast runtime tools manifest payload must be non-empty text")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Fast runtime tools manifest is malformed JSON") from exc
    if not isinstance(value, dict) or frozenset(value) != _MANIFEST_KEYS:
        raise ValueError("Fast runtime tools manifest has unknown or missing fields")
    if payload != _canonical(value) + "\n":
        raise ValueError("Fast runtime tools manifest must use canonical JSON")
    manifest = FastRuntimeToolsManifest(**value)
    if _sha256_canonical(_manifest_material(manifest)) != manifest.manifest_fingerprint_sha256:
        raise ValueError("Fast runtime tools manifest fingerprint mismatch")
    return manifest


def stage_fast_runtime_tools_package(
    *,
    source_sha: str,
    platform: str,
    tool: str | Path,
    destination: str | Path,
) -> FastRuntimeToolsManifest:
    source = _require_tool_path(tool)
    manifest = build_fast_runtime_tools_manifest(
        source_sha=source_sha,
        platform=platform,
        tool=source,
    )
    destination_path = Path(destination)
    if destination_path.exists() or destination_path.is_symlink():
        raise ValueError("Fast runtime tools package destination must not already exist")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}.",
            dir=destination_path.parent,
        )
    )
    try:
        (temporary / _INIT_NAME).write_text(
            '"""Sealed native Fast Lane runtime-tool payload."""\n',
            encoding="utf-8",
        )
        (temporary / _INIT_NAME).chmod(0o600)
        binary = temporary / _BINARY_NAME
        binary.write_bytes(source.read_bytes())
        binary.chmod(0o600)
        (temporary / _MANIFEST_NAME).write_text(
            encode_fast_runtime_tools_manifest(manifest),
            encoding="utf-8",
        )
        (temporary / _MANIFEST_NAME).chmod(0o600)
        verify_fast_runtime_tools_package(
            temporary,
            expected_source_sha=source_sha,
            expected_platform=platform,
        )
        os.replace(temporary, destination_path)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def verify_fast_runtime_tools_package(
    package: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
    allow_python_cache: bool = False,
) -> FastRuntimeToolsManifest:
    root = Path(package)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Fast runtime tools package must be a real directory")
    expected = {_INIT_NAME, _MANIFEST_NAME, _BINARY_NAME}
    actual: set[str] = set()
    for child in root.iterdir():
        if allow_python_cache and child.name == "__pycache__":
            if child.is_symlink() or not child.is_dir():
                raise ValueError("Fast runtime tools Python cache must be a real directory")
            for cache_file in child.iterdir():
                if (
                    cache_file.is_symlink()
                    or not cache_file.is_file()
                    or not cache_file.name.startswith("__init__.")
                    or not cache_file.name.endswith(".pyc")
                ):
                    raise ValueError("Fast runtime tools Python cache member is unexpected")
            continue
        if child.is_symlink() or not child.is_file():
            raise ValueError("Fast runtime tools package may contain regular files only")
        actual.add(child.name)
    if actual != expected:
        raise ValueError("Fast runtime tools package member set mismatch")

    manifest = decode_fast_runtime_tools_manifest(
        (root / _MANIFEST_NAME).read_text(encoding="utf-8")
    )
    _require_manifest_identity(
        manifest,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    payload = root / _BINARY_NAME
    if payload.stat().st_size != manifest.size or _sha256_file(payload) != manifest.sha256:
        raise ValueError("Fast runtime feature tool size/SHA fingerprint mismatch")
    return manifest


def verify_fast_runtime_tools_wheel(
    wheel_path: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
    expected_tool: str | Path | None = None,
) -> FastRuntimeToolsManifest:
    path = Path(wheel_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Fast runtime tools wheel must identify an existing file")
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                info.filename
                for info in archive.infolist()
                if info.filename.startswith(_PACKAGE_PREFIX)
            ]
            expected = {
                f"{_PACKAGE_PREFIX}{_INIT_NAME}",
                f"{_PACKAGE_PREFIX}{_MANIFEST_NAME}",
                f"{_PACKAGE_PREFIX}{_BINARY_NAME}",
            }
            if len(names) != len(set(names)) or set(names) != expected:
                raise ValueError("Fast runtime tools wheel package member set mismatch")
            manifest = decode_fast_runtime_tools_manifest(
                archive.read(f"{_PACKAGE_PREFIX}{_MANIFEST_NAME}").decode("utf-8")
            )
            payload = archive.read(f"{_PACKAGE_PREFIX}{_BINARY_NAME}")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("unable to verify Fast runtime tools wheel") from exc

    _require_manifest_identity(
        manifest,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    if len(payload) != manifest.size or hashlib.sha256(payload).hexdigest() != manifest.sha256:
        raise ValueError("Fast runtime feature tool wheel payload fingerprint mismatch")
    if expected_tool is not None:
        source = _require_tool_path(expected_tool)
        if source.stat().st_size != manifest.size or _sha256_file(source) != manifest.sha256:
            raise ValueError("Fast runtime tools wheel does not match native build output")
    return manifest


def materialize_fast_runtime_feature_tool(
    destination_root: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> Path:
    try:
        resource = files("shreks_brain._sealed_fast_runtime_tools")
    except ModuleNotFoundError as exc:
        raise ValueError("sealed Fast runtime tool is unavailable") from exc
    with as_file(resource) as package:
        return materialize_fast_runtime_feature_tool_from_directory(
            package,
            destination_root,
            expected_source_sha=expected_source_sha,
            expected_platform=expected_platform,
            allow_python_cache=True,
        )


def materialize_fast_runtime_feature_tool_from_directory(
    package: str | Path,
    destination_root: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
    allow_python_cache: bool = False,
) -> Path:
    manifest = verify_fast_runtime_tools_package(
        package,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
        allow_python_cache=allow_python_cache,
    )
    root = Path(destination_root)
    if root.is_symlink():
        raise ValueError("Fast runtime tool destination root must not be a symlink")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    target_dir = root / manifest.source_sha
    target = target_dir / FAST_RUNTIME_FEATURE_TOOL_NAME

    if target_dir.exists() or target_dir.is_symlink():
        if target_dir.is_symlink() or not target_dir.is_dir():
            raise ValueError("materialized Fast runtime toolset must be a real directory")
        if set(path.name for path in target_dir.iterdir()) != {
            FAST_RUNTIME_FEATURE_TOOL_NAME,
            _MANIFEST_NAME,
        }:
            raise ValueError("materialized Fast runtime toolset member set mismatch")
        persisted = decode_fast_runtime_tools_manifest(
            (target_dir / _MANIFEST_NAME).read_text(encoding="utf-8")
        )
        if persisted != manifest:
            raise ValueError("materialized Fast runtime tools manifest mismatch")
        _verify_materialized_tool(target, manifest)
        return target

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{manifest.source_sha}.",
            dir=root,
        )
    )
    try:
        temporary.chmod(0o700)
        source = Path(package) / _BINARY_NAME
        binary = temporary / FAST_RUNTIME_FEATURE_TOOL_NAME
        binary.write_bytes(source.read_bytes())
        binary.chmod(0o700)
        (temporary / _MANIFEST_NAME).write_text(
            encode_fast_runtime_tools_manifest(manifest),
            encoding="utf-8",
        )
        (temporary / _MANIFEST_NAME).chmod(0o600)
        _verify_materialized_tool(binary, manifest)
        os.replace(temporary, target_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return target


def _verify_materialized_tool(
    path: Path,
    manifest: FastRuntimeToolsManifest,
) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("materialized Fast runtime feature tool must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise ValueError("materialized Fast runtime feature tool permissions must be 0700")
    if path.stat().st_size != manifest.size or _sha256_file(path) != manifest.sha256:
        raise ValueError("materialized Fast runtime feature tool fingerprint mismatch")


def _manifest_material(
    manifest: FastRuntimeToolsManifest,
) -> dict[str, object]:
    return {
        "schema_name": manifest.schema_name,
        "schema_version": manifest.schema_version,
        "source_sha": manifest.source_sha,
        "platform": manifest.platform,
        "tool_name": manifest.tool_name,
        "size": manifest.size,
        "sha256": manifest.sha256,
    }


def _require_manifest_identity(
    manifest: FastRuntimeToolsManifest,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> None:
    _require_source_sha(expected_source_sha)
    if expected_platform not in _SUPPORTED_PLATFORMS:
        raise ValueError("unsupported expected Fast runtime tools platform")
    if manifest.source_sha != expected_source_sha:
        raise ValueError("Fast runtime tools source SHA mismatch")
    if manifest.platform != expected_platform:
        raise ValueError("Fast runtime tools platform mismatch")


def _require_tool_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Fast runtime feature tool must be an existing regular file")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError("Fast runtime feature tool changed while fingerprinting")
    return digest.hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_source_sha(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Fast runtime tools source_sha must be 40 lowercase hex characters")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")
