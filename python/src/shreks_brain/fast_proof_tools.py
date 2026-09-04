from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.resources import as_file, files
import json
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Mapping
import zipfile


FAST_PROOF_TOOLS_SCHEMA_NAME = "shreks.fast_proof_tools"
FAST_PROOF_TOOLS_SCHEMA_VERSION = 1
FAST_PROOF_TOOL_NAMES = (
    "export_fast_training_features",
    "shreks-fast-campaign-decision",
    "shreks-fast-entry-authority",
)

_SUPPORTED_PLATFORMS = frozenset(
    (
        "x86_64-unknown-linux-gnu",
        "aarch64-unknown-linux-gnu",
    )
)
_PACKAGE_PREFIX = "shreks_brain/_sealed_fast_tools/"
_MANIFEST_NAME = "manifest.json"
_INIT_NAME = "__init__.py"
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "source_sha",
        "platform",
        "tools",
        "manifest_fingerprint_sha256",
    }
)
_TOOL_KEYS = frozenset({"name", "size", "sha256"})


@dataclass(frozen=True, slots=True)
class FastProofTool:
    name: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if self.name not in FAST_PROOF_TOOL_NAMES:
            raise ValueError("unsupported fast proof tool name")
        if (
            not isinstance(self.size, int)
            or isinstance(self.size, bool)
            or self.size < 0
        ):
            raise ValueError("fast proof tool size must be non-negative")
        _require_sha256("fast proof tool sha256", self.sha256)


@dataclass(frozen=True, slots=True)
class FastProofToolsManifest:
    schema_name: str
    schema_version: int
    source_sha: str
    platform: str
    tools: tuple[FastProofTool, ...]
    manifest_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PROOF_TOOLS_SCHEMA_NAME:
            raise ValueError("unsupported fast proof tools schema_name")
        if self.schema_version != FAST_PROOF_TOOLS_SCHEMA_VERSION:
            raise ValueError("unsupported fast proof tools schema_version")
        _require_source_sha(self.source_sha)
        if self.platform not in _SUPPORTED_PLATFORMS:
            raise ValueError("unsupported fast proof tools platform")
        if (
            not isinstance(self.tools, tuple)
            or not all(type(value) is FastProofTool for value in self.tools)
        ):
            raise ValueError("fast proof tools must be exact tool records")
        names = tuple(value.name for value in self.tools)
        if names != FAST_PROOF_TOOL_NAMES:
            raise ValueError(
                "fast proof tools must contain exactly the canonical tool set"
            )
        _require_sha256(
            "fast proof tools manifest fingerprint",
            self.manifest_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class FastProofToolSet:
    source_sha: str
    platform: str
    paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        _require_source_sha(self.source_sha)
        if self.platform not in _SUPPORTED_PLATFORMS:
            raise ValueError("unsupported fast proof toolset platform")
        if (
            not isinstance(self.paths, tuple)
            or tuple(path.name for path in self.paths)
            != FAST_PROOF_TOOL_NAMES
        ):
            raise ValueError(
                "fast proof toolset paths must contain the canonical tool set"
            )


def build_fast_proof_tools_manifest(
    *,
    source_sha: str,
    platform: str,
    tools: Mapping[str, Path],
) -> FastProofToolsManifest:
    _require_source_sha(source_sha)
    if platform not in _SUPPORTED_PLATFORMS:
        raise ValueError("unsupported fast proof tools platform")
    tool_paths = _validate_tool_mapping(tools)
    records = tuple(
        FastProofTool(
            name=name,
            size=tool_paths[name].stat().st_size,
            sha256=_sha256_file(tool_paths[name]),
        )
        for name in FAST_PROOF_TOOL_NAMES
    )
    material = _manifest_material(
        source_sha=source_sha,
        platform=platform,
        tools=records,
    )
    return FastProofToolsManifest(
        schema_name=FAST_PROOF_TOOLS_SCHEMA_NAME,
        schema_version=FAST_PROOF_TOOLS_SCHEMA_VERSION,
        source_sha=source_sha,
        platform=platform,
        tools=records,
        manifest_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_proof_tools_manifest(
    manifest: FastProofToolsManifest,
) -> str:
    if type(manifest) is not FastProofToolsManifest:
        raise ValueError(
            "manifest must be exact FastProofToolsManifest"
        )
    material = _manifest_material(
        source_sha=manifest.source_sha,
        platform=manifest.platform,
        tools=manifest.tools,
    )
    expected = _sha256_canonical(material)
    if manifest.manifest_fingerprint_sha256 != expected:
        raise ValueError("fast proof tools manifest fingerprint mismatch")
    return _canonical(
        {
            **material,
            "manifest_fingerprint_sha256": (
                manifest.manifest_fingerprint_sha256
            ),
        }
    ) + "\n"


def decode_fast_proof_tools_manifest(
    payload: str,
) -> FastProofToolsManifest:
    if not isinstance(payload, str) or not payload:
        raise ValueError(
            "fast proof tools manifest payload must be non-empty text"
        )
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(
            "fast proof tools manifest must have one trailing newline"
        )
    try:
        raw = json.loads(
            payload,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("fast proof tools manifest is malformed JSON") from exc
    if not isinstance(raw, dict) or frozenset(raw) != _MANIFEST_KEYS:
        raise ValueError(
            "fast proof tools manifest has unknown or missing fields"
        )
    if payload != _canonical(raw) + "\n":
        raise ValueError(
            "fast proof tools manifest must use canonical JSON"
        )

    raw_tools = raw["tools"]
    if not isinstance(raw_tools, list):
        raise ValueError("fast proof tools must be a JSON array")
    tools: list[FastProofTool] = []
    for value in raw_tools:
        if not isinstance(value, dict) or frozenset(value) != _TOOL_KEYS:
            raise ValueError(
                "fast proof tool entry has unknown or missing fields"
            )
        tools.append(
            FastProofTool(
                name=value["name"],
                size=value["size"],
                sha256=value["sha256"],
            )
        )

    manifest = FastProofToolsManifest(
        schema_name=raw["schema_name"],
        schema_version=raw["schema_version"],
        source_sha=raw["source_sha"],
        platform=raw["platform"],
        tools=tuple(tools),
        manifest_fingerprint_sha256=raw[
            "manifest_fingerprint_sha256"
        ],
    )
    material = _manifest_material(
        source_sha=manifest.source_sha,
        platform=manifest.platform,
        tools=manifest.tools,
    )
    if (
        manifest.manifest_fingerprint_sha256
        != _sha256_canonical(material)
    ):
        raise ValueError("fast proof tools manifest fingerprint mismatch")
    return manifest


def stage_fast_proof_tools_package(
    *,
    source_sha: str,
    platform: str,
    tools: Mapping[str, Path],
    destination: str | Path,
) -> FastProofToolsManifest:
    tool_paths = _validate_tool_mapping(tools)
    manifest = build_fast_proof_tools_manifest(
        source_sha=source_sha,
        platform=platform,
        tools=tool_paths,
    )
    destination_path = Path(destination)
    if destination_path.exists() or destination_path.is_symlink():
        raise ValueError(
            "fast proof tools package destination must not already exist"
        )
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}.",
            dir=destination_path.parent,
        )
    )
    try:
        (temporary / _INIT_NAME).write_text(
            '"""Sealed native Fast Lane proof-tool payload."""\n',
            encoding="utf-8",
        )
        for record in manifest.tools:
            source = tool_paths[record.name]
            target = temporary / f"{record.name}.bin"
            target.write_bytes(source.read_bytes())
            target.chmod(0o600)
        (temporary / _MANIFEST_NAME).write_text(
            encode_fast_proof_tools_manifest(manifest),
            encoding="utf-8",
        )
        (temporary / _MANIFEST_NAME).chmod(0o600)
        (temporary / _INIT_NAME).chmod(0o600)
        verify_fast_proof_tools_package(
            temporary,
            expected_source_sha=source_sha,
            expected_platform=platform,
        )
        os.replace(temporary, destination_path)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def verify_fast_proof_tools_package(
    package: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> FastProofToolsManifest:
    root = Path(package)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "fast proof tools package must be an existing real directory"
        )
    expected_names = {
        _INIT_NAME,
        _MANIFEST_NAME,
        *(f"{name}.bin" for name in FAST_PROOF_TOOL_NAMES),
    }
    actual_names: set[str] = set()
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                "fast proof tools package may contain regular files only"
            )
        actual_names.add(path.name)
    if actual_names != expected_names:
        raise ValueError(
            "fast proof tools package member set mismatch"
        )

    manifest = decode_fast_proof_tools_manifest(
        (root / _MANIFEST_NAME).read_text(encoding="utf-8")
    )
    _require_manifest_identity(
        manifest,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    _verify_tool_payloads(
        manifest,
        {
            name: (root / f"{name}.bin").read_bytes()
            for name in FAST_PROOF_TOOL_NAMES
        },
    )
    return manifest


def verify_fast_proof_tools_wheel(
    wheel_path: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
    expected_tools: Mapping[str, Path] | None = None,
) -> FastProofToolsManifest:
    path = Path(wheel_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "fast proof tools wheel must identify an existing file"
        )
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                info.filename
                for info in archive.infolist()
                if info.filename.startswith(_PACKAGE_PREFIX)
            ]
            if len(names) != len(set(names)):
                raise ValueError(
                    "fast proof tools wheel contains duplicate package members"
                )
            expected_members = {
                f"{_PACKAGE_PREFIX}{_INIT_NAME}",
                f"{_PACKAGE_PREFIX}{_MANIFEST_NAME}",
                *(
                    f"{_PACKAGE_PREFIX}{name}.bin"
                    for name in FAST_PROOF_TOOL_NAMES
                ),
            }
            if set(names) != expected_members:
                raise ValueError(
                    "fast proof tools wheel package member set mismatch"
                )
            manifest = decode_fast_proof_tools_manifest(
                archive.read(
                    f"{_PACKAGE_PREFIX}{_MANIFEST_NAME}"
                ).decode("utf-8")
            )
            payloads = {
                name: archive.read(f"{_PACKAGE_PREFIX}{name}.bin")
                for name in FAST_PROOF_TOOL_NAMES
            }
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("unable to verify fast proof tools wheel") from exc

    _require_manifest_identity(
        manifest,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    _verify_tool_payloads(manifest, payloads)

    if expected_tools is not None:
        expected_paths = _validate_tool_mapping(expected_tools)
        for record in manifest.tools:
            source = expected_paths[record.name]
            if (
                source.stat().st_size != record.size
                or _sha256_file(source) != record.sha256
            ):
                raise ValueError(
                    "fast proof tools wheel does not match native build output"
                )
    return manifest


def materialize_fast_proof_tools(
    destination_root: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> FastProofToolSet:
    try:
        resource = files("shreks_brain._sealed_fast_tools")
    except ModuleNotFoundError as exc:
        raise ValueError(
            "sealed fast proof tools are unavailable in this installation"
        ) from exc
    with as_file(resource) as package:
        return materialize_fast_proof_tools_from_directory(
            package,
            destination_root,
            expected_source_sha=expected_source_sha,
            expected_platform=expected_platform,
        )


def materialize_fast_proof_tools_from_directory(
    package: str | Path,
    destination_root: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> FastProofToolSet:
    manifest = verify_fast_proof_tools_package(
        package,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    root = Path(destination_root)
    if root.is_symlink():
        raise ValueError(
            "fast proof tools destination root must not be a symlink"
        )
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    target = root / manifest.source_sha
    if target.exists() or target.is_symlink():
        return _verify_materialized_toolset(target, manifest)

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{manifest.source_sha}.",
            dir=root,
        )
    )
    try:
        temporary.chmod(0o700)
        package_path = Path(package)
        for record in manifest.tools:
            source = package_path / f"{record.name}.bin"
            destination = temporary / record.name
            destination.write_bytes(source.read_bytes())
            destination.chmod(0o700)
        (temporary / _MANIFEST_NAME).write_text(
            encode_fast_proof_tools_manifest(manifest),
            encoding="utf-8",
        )
        (temporary / _MANIFEST_NAME).chmod(0o600)
        _verify_materialized_toolset(temporary, manifest)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    return _verify_materialized_toolset(target, manifest)


def _verify_materialized_toolset(
    target: Path,
    manifest: FastProofToolsManifest,
) -> FastProofToolSet:
    if target.is_symlink() or not target.is_dir():
        raise ValueError(
            "materialized fast proof tools must be a real directory"
        )
    expected_names = {_MANIFEST_NAME, *FAST_PROOF_TOOL_NAMES}
    actual_names: set[str] = set()
    for path in target.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                "materialized fast proof tools may contain regular files only"
            )
        actual_names.add(path.name)
    if actual_names != expected_names:
        raise ValueError("materialized fast proof tools member set mismatch")

    persisted = decode_fast_proof_tools_manifest(
        (target / _MANIFEST_NAME).read_text(encoding="utf-8")
    )
    if persisted != manifest:
        raise ValueError(
            "materialized fast proof tools manifest mismatch"
        )
    payloads = {
        name: (target / name).read_bytes()
        for name in FAST_PROOF_TOOL_NAMES
    }
    _verify_tool_payloads(manifest, payloads)
    paths = tuple(target / name for name in FAST_PROOF_TOOL_NAMES)
    for path in paths:
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise ValueError(
                "materialized fast proof tool permissions must be 0700"
            )
    return FastProofToolSet(
        source_sha=manifest.source_sha,
        platform=manifest.platform,
        paths=paths,
    )


def _validate_tool_mapping(
    tools: Mapping[str, Path],
) -> dict[str, Path]:
    if not isinstance(tools, Mapping):
        raise ValueError("fast proof tools must be a mapping")
    if set(tools) != set(FAST_PROOF_TOOL_NAMES):
        raise ValueError(
            "fast proof tools mapping must contain exactly the canonical tool set"
        )
    result: dict[str, Path] = {}
    for name in FAST_PROOF_TOOL_NAMES:
        path = Path(tools[name])
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                f"fast proof tool {name} must be an existing regular file"
            )
        result[name] = path
    return result


def _manifest_material(
    *,
    source_sha: str,
    platform: str,
    tools: tuple[FastProofTool, ...],
) -> dict[str, object]:
    _require_source_sha(source_sha)
    if platform not in _SUPPORTED_PLATFORMS:
        raise ValueError("unsupported fast proof tools platform")
    if tuple(value.name for value in tools) != FAST_PROOF_TOOL_NAMES:
        raise ValueError(
            "fast proof tools must contain exactly the canonical tool set"
        )
    return {
        "schema_name": FAST_PROOF_TOOLS_SCHEMA_NAME,
        "schema_version": FAST_PROOF_TOOLS_SCHEMA_VERSION,
        "source_sha": source_sha,
        "platform": platform,
        "tools": [
            {
                "name": value.name,
                "size": value.size,
                "sha256": value.sha256,
            }
            for value in tools
        ],
    }


def _require_manifest_identity(
    manifest: FastProofToolsManifest,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> None:
    _require_source_sha(expected_source_sha)
    if expected_platform not in _SUPPORTED_PLATFORMS:
        raise ValueError("unsupported expected fast proof tools platform")
    if manifest.source_sha != expected_source_sha:
        raise ValueError("fast proof tools source SHA mismatch")
    if manifest.platform != expected_platform:
        raise ValueError("fast proof tools platform mismatch")


def _verify_tool_payloads(
    manifest: FastProofToolsManifest,
    payloads: Mapping[str, bytes],
) -> None:
    if set(payloads) != set(FAST_PROOF_TOOL_NAMES):
        raise ValueError("fast proof tool payload set mismatch")
    for record in manifest.tools:
        payload = payloads[record.name]
        if not isinstance(payload, bytes):
            raise ValueError("fast proof tool payload must be bytes")
        if (
            len(payload) != record.size
            or hashlib.sha256(payload).hexdigest() != record.sha256
        ):
            raise ValueError(
                f"fast proof tool {record.name} size/SHA fingerprint mismatch"
            )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(
            "fast proof tool changed while fingerprinting"
        )
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
        raise ValueError(
            "fast proof tools source_sha must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")
