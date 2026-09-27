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
from typing import Mapping
import zipfile


FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_commissioning_assets"
)
FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_VERSION = 1
FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES = (
    "shreks-fast-paper-shadow.service",
    "shreks-fast-paper-shadow.env.example",
)

_SUPPORTED_PLATFORMS = frozenset(
    (
        "x86_64-unknown-linux-gnu",
        "aarch64-unknown-linux-gnu",
    )
)
_PACKAGE_NAME = "shreks_brain._sealed_fast_paper_shadow_commissioning"
_PACKAGE_PREFIX = "shreks_brain/_sealed_fast_paper_shadow_commissioning/"
_MANIFEST_NAME = "manifest.json"
_INIT_NAME = "__init__.py"
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "source_sha",
        "platform",
        "assets",
        "manifest_fingerprint_sha256",
    }
)
_ASSET_KEYS = frozenset({"name", "size", "sha256"})


@dataclass(frozen=True, slots=True)
class FastPaperShadowCommissioningAsset:
    name: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if self.name not in FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES:
            raise ValueError("unsupported Fast PAPER shadow commissioning asset name")
        if (
            isinstance(self.size, bool)
            or not isinstance(self.size, int)
            or self.size < 0
        ):
            raise ValueError(
                "Fast PAPER shadow commissioning asset size must be non-negative"
            )
        _require_sha256(
            "Fast PAPER shadow commissioning asset SHA-256",
            self.sha256,
        )


@dataclass(frozen=True, slots=True)
class FastPaperShadowCommissioningManifest:
    schema_name: str
    schema_version: int
    source_sha: str
    platform: str
    assets: tuple[FastPaperShadowCommissioningAsset, ...]
    manifest_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_NAME:
            raise ValueError(
                "unsupported Fast PAPER shadow commissioning schema_name"
            )
        if (
            self.schema_version
            != FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported Fast PAPER shadow commissioning schema_version"
            )
        _require_source_sha(self.source_sha)
        if self.platform not in _SUPPORTED_PLATFORMS:
            raise ValueError(
                "unsupported Fast PAPER shadow commissioning platform"
            )
        if (
            not isinstance(self.assets, tuple)
            or not all(
                type(value) is FastPaperShadowCommissioningAsset
                for value in self.assets
            )
        ):
            raise ValueError(
                "Fast PAPER shadow commissioning assets must be exact records"
            )
        if (
            tuple(value.name for value in self.assets)
            != FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES
        ):
            raise ValueError(
                "Fast PAPER shadow commissioning asset set/order mismatch"
            )
        _require_sha256(
            "Fast PAPER shadow commissioning manifest fingerprint",
            self.manifest_fingerprint_sha256,
        )


def build_fast_paper_shadow_commissioning_manifest(
    *,
    source_sha: str,
    platform: str,
    assets: Mapping[str, Path],
) -> FastPaperShadowCommissioningManifest:
    _require_source_sha(source_sha)
    if platform not in _SUPPORTED_PLATFORMS:
        raise ValueError(
            "unsupported Fast PAPER shadow commissioning platform"
        )
    paths = _validate_asset_mapping(assets)
    records = tuple(
        FastPaperShadowCommissioningAsset(
            name=name,
            size=paths[name].stat().st_size,
            sha256=_sha256_file(paths[name]),
        )
        for name in FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES
    )
    material = _manifest_material(
        source_sha=source_sha,
        platform=platform,
        assets=records,
    )
    return FastPaperShadowCommissioningManifest(
        schema_name=FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_NAME,
        schema_version=FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_VERSION,
        source_sha=source_sha,
        platform=platform,
        assets=records,
        manifest_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_paper_shadow_commissioning_manifest(
    manifest: FastPaperShadowCommissioningManifest,
) -> str:
    if type(manifest) is not FastPaperShadowCommissioningManifest:
        raise ValueError(
            "manifest must be exact FastPaperShadowCommissioningManifest"
        )
    material = _manifest_material(
        source_sha=manifest.source_sha,
        platform=manifest.platform,
        assets=manifest.assets,
    )
    if (
        manifest.manifest_fingerprint_sha256
        != _sha256_canonical(material)
    ):
        raise ValueError(
            "Fast PAPER shadow commissioning manifest fingerprint mismatch"
        )
    return _canonical(
        {
            **material,
            "manifest_fingerprint_sha256": (
                manifest.manifest_fingerprint_sha256
            ),
        }
    ) + "\n"


def decode_fast_paper_shadow_commissioning_manifest(
    payload: str,
) -> FastPaperShadowCommissioningManifest:
    if not isinstance(payload, str) or not payload:
        raise ValueError(
            "Fast PAPER shadow commissioning manifest must be non-empty text"
        )
    try:
        raw = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Fast PAPER shadow commissioning manifest is malformed JSON"
        ) from exc
    if not isinstance(raw, dict) or frozenset(raw) != _MANIFEST_KEYS:
        raise ValueError(
            "Fast PAPER shadow commissioning manifest has unknown or missing fields"
        )
    if payload != _canonical(raw) + "\n":
        raise ValueError(
            "Fast PAPER shadow commissioning manifest must use canonical JSON"
        )
    raw_assets = raw["assets"]
    if not isinstance(raw_assets, list):
        raise ValueError(
            "Fast PAPER shadow commissioning assets must be a JSON array"
        )
    records: list[FastPaperShadowCommissioningAsset] = []
    for value in raw_assets:
        if not isinstance(value, dict) or frozenset(value) != _ASSET_KEYS:
            raise ValueError(
                "Fast PAPER shadow commissioning asset has unknown or missing fields"
            )
        records.append(
            FastPaperShadowCommissioningAsset(
                name=value["name"],
                size=value["size"],
                sha256=value["sha256"],
            )
        )
    manifest = FastPaperShadowCommissioningManifest(
        schema_name=raw["schema_name"],
        schema_version=raw["schema_version"],
        source_sha=raw["source_sha"],
        platform=raw["platform"],
        assets=tuple(records),
        manifest_fingerprint_sha256=raw[
            "manifest_fingerprint_sha256"
        ],
    )
    expected = _sha256_canonical(
        _manifest_material(
            source_sha=manifest.source_sha,
            platform=manifest.platform,
            assets=manifest.assets,
        )
    )
    if manifest.manifest_fingerprint_sha256 != expected:
        raise ValueError(
            "Fast PAPER shadow commissioning manifest fingerprint mismatch"
        )
    return manifest


def stage_fast_paper_shadow_commissioning_package(
    *,
    source_sha: str,
    platform: str,
    assets: Mapping[str, Path],
    destination: str | Path,
) -> FastPaperShadowCommissioningManifest:
    paths = _validate_asset_mapping(assets)
    manifest = build_fast_paper_shadow_commissioning_manifest(
        source_sha=source_sha,
        platform=platform,
        assets=paths,
    )
    destination_path = Path(destination)
    if destination_path.exists() or destination_path.is_symlink():
        raise ValueError(
            "Fast PAPER shadow commissioning package destination must not exist"
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
            '"""Sealed Fast PAPER shadow commissioning assets."""\n',
            encoding="utf-8",
        )
        (temporary / _INIT_NAME).chmod(0o600)
        for record in manifest.assets:
            target = temporary / record.name
            target.write_bytes(paths[record.name].read_bytes())
            target.chmod(0o600)
        (temporary / _MANIFEST_NAME).write_text(
            encode_fast_paper_shadow_commissioning_manifest(manifest),
            encoding="utf-8",
        )
        (temporary / _MANIFEST_NAME).chmod(0o600)
        verify_fast_paper_shadow_commissioning_package(
            temporary,
            expected_source_sha=source_sha,
            expected_platform=platform,
        )
        os.replace(temporary, destination_path)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def verify_fast_paper_shadow_commissioning_package(
    package: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
    allow_python_cache: bool = False,
) -> FastPaperShadowCommissioningManifest:
    root = Path(package)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "Fast PAPER shadow commissioning package must be a real directory"
        )
    expected_names = {
        _INIT_NAME,
        _MANIFEST_NAME,
        *FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES,
    }
    actual_names: set[str] = set()
    for child in root.iterdir():
        if allow_python_cache and child.name == "__pycache__":
            _verify_python_cache(child)
            continue
        if child.is_symlink() or not child.is_file():
            raise ValueError(
                "Fast PAPER shadow commissioning package may contain regular files only"
            )
        actual_names.add(child.name)
    if actual_names != expected_names:
        raise ValueError(
            "Fast PAPER shadow commissioning package member set mismatch"
        )
    manifest = decode_fast_paper_shadow_commissioning_manifest(
        (root / _MANIFEST_NAME).read_text(encoding="utf-8")
    )
    _require_manifest_identity(
        manifest,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    _verify_asset_payloads(
        manifest,
        {
            name: (root / name).read_bytes()
            for name in FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES
        },
    )
    return manifest


def verify_fast_paper_shadow_commissioning_wheel(
    wheel_path: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
    expected_assets: Mapping[str, Path] | None = None,
) -> FastPaperShadowCommissioningManifest:
    path = Path(wheel_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "Fast PAPER shadow commissioning wheel must be an existing file"
        )
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                info.filename
                for info in archive.infolist()
                if info.filename.startswith(_PACKAGE_PREFIX)
            ]
            expected_names = {
                f"{_PACKAGE_PREFIX}{_INIT_NAME}",
                f"{_PACKAGE_PREFIX}{_MANIFEST_NAME}",
                *(
                    f"{_PACKAGE_PREFIX}{name}"
                    for name in FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES
                ),
            }
            if len(names) != len(set(names)) or set(names) != expected_names:
                raise ValueError(
                    "Fast PAPER shadow commissioning wheel package member set mismatch"
                )
            manifest = decode_fast_paper_shadow_commissioning_manifest(
                archive.read(
                    f"{_PACKAGE_PREFIX}{_MANIFEST_NAME}"
                ).decode("utf-8")
            )
            payloads = {
                name: archive.read(f"{_PACKAGE_PREFIX}{name}")
                for name in FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES
            }
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(
            "unable to verify Fast PAPER shadow commissioning wheel"
        ) from exc
    _require_manifest_identity(
        manifest,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    _verify_asset_payloads(manifest, payloads)
    if expected_assets is not None:
        paths = _validate_asset_mapping(expected_assets)
        for record in manifest.assets:
            source = paths[record.name]
            if (
                source.stat().st_size != record.size
                or _sha256_file(source) != record.sha256
            ):
                raise ValueError(
                    "Fast PAPER shadow commissioning wheel does not match checkout assets"
                )
    return manifest


def materialize_fast_paper_shadow_commissioning_assets(
    destination_root: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> Path:
    try:
        resource = files(_PACKAGE_NAME)
    except ModuleNotFoundError as exc:
        raise ValueError(
            "sealed Fast PAPER shadow commissioning assets are unavailable"
        ) from exc
    with as_file(resource) as package:
        return _materialize_fast_paper_shadow_commissioning_assets(
            package,
            destination_root,
            expected_source_sha=expected_source_sha,
            expected_platform=expected_platform,
            allow_python_cache=True,
        )


def materialize_fast_paper_shadow_commissioning_assets_from_directory(
    package: str | Path,
    destination_root: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> Path:
    return _materialize_fast_paper_shadow_commissioning_assets(
        package,
        destination_root,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
        allow_python_cache=False,
    )


def _materialize_fast_paper_shadow_commissioning_assets(
    package: str | Path,
    destination_root: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
    allow_python_cache: bool,
) -> Path:
    manifest = verify_fast_paper_shadow_commissioning_package(
        package,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
        allow_python_cache=allow_python_cache,
    )
    root = Path(destination_root)
    if root.is_symlink():
        raise ValueError(
            "Fast PAPER shadow commissioning destination root must not be a symlink"
        )
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not root.is_dir():
        raise ValueError(
            "Fast PAPER shadow commissioning destination root must be a directory"
        )
    root.chmod(0o700)
    target = root / manifest.source_sha
    if target.exists() or target.is_symlink():
        _verify_materialized_assets(target, manifest)
        return target

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{manifest.source_sha}.",
            dir=root,
        )
    )
    try:
        temporary.chmod(0o700)
        package_path = Path(package)
        for record in manifest.assets:
            output = temporary / record.name
            output.write_bytes(
                (package_path / record.name).read_bytes()
            )
            output.chmod(0o600)
        (temporary / _MANIFEST_NAME).write_text(
            encode_fast_paper_shadow_commissioning_manifest(manifest),
            encoding="utf-8",
        )
        (temporary / _MANIFEST_NAME).chmod(0o600)
        _verify_materialized_assets(temporary, manifest)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    _verify_materialized_assets(target, manifest)
    return target


def _verify_materialized_assets(
    target: Path,
    manifest: FastPaperShadowCommissioningManifest,
) -> None:
    if target.is_symlink() or not target.is_dir():
        raise ValueError(
            "materialized Fast PAPER shadow commissioning assets must be a real directory"
        )
    if stat.S_IMODE(target.stat().st_mode) != 0o700:
        raise ValueError(
            "materialized Fast PAPER shadow commissioning directory permissions must be 0700"
        )
    expected_names = {
        _MANIFEST_NAME,
        *FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES,
    }
    actual_names: set[str] = set()
    for child in target.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError(
                "materialized Fast PAPER shadow commissioning members must be regular files"
            )
        actual_names.add(child.name)
        if stat.S_IMODE(child.stat().st_mode) != 0o600:
            raise ValueError(
                "materialized Fast PAPER shadow commissioning file permissions must be 0600"
            )
    if actual_names != expected_names:
        raise ValueError(
            "materialized Fast PAPER shadow commissioning member set mismatch"
        )
    persisted = decode_fast_paper_shadow_commissioning_manifest(
        (target / _MANIFEST_NAME).read_text(encoding="utf-8")
    )
    if persisted != manifest:
        raise ValueError(
            "materialized Fast PAPER shadow commissioning manifest mismatch"
        )
    _verify_asset_payloads(
        manifest,
        {
            name: (target / name).read_bytes()
            for name in FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES
        },
    )


def _verify_python_cache(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(
            "Fast PAPER shadow commissioning Python cache must be a real directory"
        )
    for child in path.iterdir():
        if (
            child.is_symlink()
            or not child.is_file()
            or not child.name.startswith("__init__.")
            or not child.name.endswith(".pyc")
        ):
            raise ValueError(
                "Fast PAPER shadow commissioning Python cache member is unexpected"
            )


def _validate_asset_mapping(
    assets: Mapping[str, Path],
) -> dict[str, Path]:
    if not isinstance(assets, Mapping):
        raise ValueError(
            "Fast PAPER shadow commissioning assets must be a mapping"
        )
    if set(assets) != set(FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES):
        raise ValueError(
            "Fast PAPER shadow commissioning mapping must contain the exact asset set"
        )
    result: dict[str, Path] = {}
    for name in FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES:
        path = Path(assets[name])
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                f"Fast PAPER shadow commissioning asset {name} must be a regular file"
            )
        result[name] = path
    return result


def _manifest_material(
    *,
    source_sha: str,
    platform: str,
    assets: tuple[FastPaperShadowCommissioningAsset, ...],
) -> dict[str, object]:
    _require_source_sha(source_sha)
    if platform not in _SUPPORTED_PLATFORMS:
        raise ValueError(
            "unsupported Fast PAPER shadow commissioning platform"
        )
    if tuple(value.name for value in assets) != (
        FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES
    ):
        raise ValueError(
            "Fast PAPER shadow commissioning asset set/order mismatch"
        )
    return {
        "schema_name": FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_VERSION,
        "source_sha": source_sha,
        "platform": platform,
        "assets": [
            {
                "name": value.name,
                "size": value.size,
                "sha256": value.sha256,
            }
            for value in assets
        ],
    }


def _require_manifest_identity(
    manifest: FastPaperShadowCommissioningManifest,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> None:
    _require_source_sha(expected_source_sha)
    if expected_platform not in _SUPPORTED_PLATFORMS:
        raise ValueError(
            "unsupported expected Fast PAPER shadow commissioning platform"
        )
    if manifest.source_sha != expected_source_sha:
        raise ValueError(
            "Fast PAPER shadow commissioning source SHA mismatch"
        )
    if manifest.platform != expected_platform:
        raise ValueError(
            "Fast PAPER shadow commissioning platform mismatch"
        )


def _verify_asset_payloads(
    manifest: FastPaperShadowCommissioningManifest,
    payloads: Mapping[str, bytes],
) -> None:
    if set(payloads) != set(FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES):
        raise ValueError(
            "Fast PAPER shadow commissioning asset payload set mismatch"
        )
    for record in manifest.assets:
        payload = payloads[record.name]
        if not isinstance(payload, bytes):
            raise ValueError(
                "Fast PAPER shadow commissioning asset payload must be bytes"
            )
        if (
            len(payload) != record.size
            or hashlib.sha256(payload).hexdigest() != record.sha256
        ):
            raise ValueError(
                f"Fast PAPER shadow commissioning asset {record.name} fingerprint mismatch"
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
            "Fast PAPER shadow commissioning asset changed while fingerprinting"
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
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _require_source_sha(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            "Fast PAPER shadow commissioning source_sha must be 40 lowercase hex characters"
        )


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
