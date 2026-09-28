from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Mapping
import zipfile


FAST_PAPER_AUTHORITATIVE_COMMISSIONING_SCHEMA_NAME = (
    "shreks.fast_paper_authoritative_commissioning_assets"
)
FAST_PAPER_AUTHORITATIVE_COMMISSIONING_SCHEMA_VERSION = 1
FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES = (
    "shreks-paper-campaign.fast-paper.service",
    "shreks-fast-paper-authoritative.env.example",
)

_SUPPORTED_PLATFORMS = frozenset(
    (
        "x86_64-unknown-linux-gnu",
        "aarch64-unknown-linux-gnu",
    )
)
_PACKAGE_PREFIX = (
    "shreks_brain/_sealed_fast_paper_authoritative_commissioning/"
)
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
_REQUIRED_UNIT_LINES = (
    "User=shreks",
    "Group=shreks",
    "WorkingDirectory=/opt/shreks/current",
    "EnvironmentFile=/etc/shreks/fast-paper-authoritative.env",
    (
        "ExecStartPre=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.fast_paper_runtime.authoritative_runtime --preflight"
    ),
    (
        "ExecStart=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.fast_paper_runtime.authoritative_runtime"
    ),
    "PrivateNetwork=true",
    "ReadWritePaths=/var/lib/shreks",
)
_FORBIDDEN_UNIT_TEXT = (
    "shreks_brain.fast_paper_runtime.shadow_supervisor",
    "shreks_brain.observer_campaign.runtime",
    "RuntimeMode.LIVE",
    "sign_transaction",
    "submit_transaction",
)


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeCommissioningAsset:
    name: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if self.name not in FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES:
            raise ValueError(
                "unsupported authoritative Fast PAPER commissioning asset name"
            )
        if (
            isinstance(self.size, bool)
            or not isinstance(self.size, int)
            or self.size < 0
        ):
            raise ValueError(
                "authoritative commissioning asset size must be non-negative"
            )
        _require_sha256(self.sha256)


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeCommissioningManifest:
    schema_name: str
    schema_version: int
    source_sha: str
    platform: str
    assets: tuple[FastPaperAuthoritativeCommissioningAsset, ...]
    manifest_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_PAPER_AUTHORITATIVE_COMMISSIONING_SCHEMA_NAME
        ):
            raise ValueError(
                "unsupported authoritative commissioning schema_name"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_AUTHORITATIVE_COMMISSIONING_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported authoritative commissioning schema_version"
            )
        _require_source_sha(self.source_sha)
        if self.platform not in _SUPPORTED_PLATFORMS:
            raise ValueError(
                "unsupported authoritative commissioning platform"
            )
        if (
            not isinstance(self.assets, tuple)
            or tuple(value.name for value in self.assets)
            != FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES
        ):
            raise ValueError(
                "authoritative commissioning asset set/order mismatch"
            )
        _require_sha256(self.manifest_fingerprint_sha256)


def build_fast_paper_authoritative_commissioning_manifest(
    *,
    source_sha: str,
    platform: str,
    assets: Mapping[str, Path],
) -> FastPaperAuthoritativeCommissioningManifest:
    _require_source_sha(source_sha)
    if platform not in _SUPPORTED_PLATFORMS:
        raise ValueError("unsupported authoritative commissioning platform")
    paths = _validate_assets(assets)
    records = tuple(
        FastPaperAuthoritativeCommissioningAsset(
            name=name,
            size=paths[name].stat().st_size,
            sha256=_sha256_file(paths[name]),
        )
        for name in FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES
    )
    material = _manifest_material(
        source_sha=source_sha,
        platform=platform,
        assets=records,
    )
    return FastPaperAuthoritativeCommissioningManifest(
        schema_name=FAST_PAPER_AUTHORITATIVE_COMMISSIONING_SCHEMA_NAME,
        schema_version=FAST_PAPER_AUTHORITATIVE_COMMISSIONING_SCHEMA_VERSION,
        source_sha=source_sha,
        platform=platform,
        assets=records,
        manifest_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_paper_authoritative_commissioning_manifest(
    manifest: FastPaperAuthoritativeCommissioningManifest,
) -> str:
    if type(manifest) is not FastPaperAuthoritativeCommissioningManifest:
        raise ValueError(
            "manifest must be exact FastPaperAuthoritativeCommissioningManifest"
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
            "authoritative commissioning manifest fingerprint mismatch"
        )
    return _canonical(
        {
            **material,
            "manifest_fingerprint_sha256": (
                manifest.manifest_fingerprint_sha256
            ),
        }
    ) + "\n"


def decode_fast_paper_authoritative_commissioning_manifest(
    payload: str,
) -> FastPaperAuthoritativeCommissioningManifest:
    try:
        raw = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "authoritative commissioning manifest is malformed JSON"
        ) from exc
    if type(raw) is not dict or frozenset(raw) != _MANIFEST_KEYS:
        raise ValueError(
            "authoritative commissioning manifest has unknown or missing fields"
        )
    if payload != _canonical(raw) + "\n":
        raise ValueError(
            "authoritative commissioning manifest must use canonical JSON"
        )
    raw_assets = raw["assets"]
    if not isinstance(raw_assets, list):
        raise ValueError(
            "authoritative commissioning assets must be a JSON array"
        )
    records = tuple(
        FastPaperAuthoritativeCommissioningAsset(
            name=value["name"],
            size=value["size"],
            sha256=value["sha256"],
        )
        for value in raw_assets
        if type(value) is dict and frozenset(value) == _ASSET_KEYS
    )
    if len(records) != len(raw_assets):
        raise ValueError(
            "authoritative commissioning asset has unknown or missing fields"
        )
    manifest = FastPaperAuthoritativeCommissioningManifest(
        schema_name=raw["schema_name"],
        schema_version=raw["schema_version"],
        source_sha=raw["source_sha"],
        platform=raw["platform"],
        assets=records,
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
            "authoritative commissioning manifest fingerprint mismatch"
        )
    return manifest


def stage_fast_paper_authoritative_commissioning_package(
    *,
    source_sha: str,
    platform: str,
    assets: Mapping[str, Path],
    destination: str | Path,
) -> FastPaperAuthoritativeCommissioningManifest:
    paths = _validate_assets(assets)
    _require_unit_safety(
        paths["shreks-paper-campaign.fast-paper.service"].read_bytes()
    )
    manifest = build_fast_paper_authoritative_commissioning_manifest(
        source_sha=source_sha,
        platform=platform,
        assets=paths,
    )
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise ValueError(
            "authoritative commissioning package destination must not exist"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent)
    )
    try:
        (temporary / _INIT_NAME).write_text(
            '"""Sealed authoritative Fast PAPER commissioning assets."""\n',
            encoding="utf-8",
        )
        for record in manifest.assets:
            (temporary / record.name).write_bytes(
                paths[record.name].read_bytes()
            )
        (temporary / _MANIFEST_NAME).write_text(
            encode_fast_paper_authoritative_commissioning_manifest(manifest),
            encoding="utf-8",
        )
        verify_fast_paper_authoritative_commissioning_package(
            temporary,
            expected_source_sha=source_sha,
            expected_platform=platform,
        )
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def verify_fast_paper_authoritative_commissioning_package(
    package: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> FastPaperAuthoritativeCommissioningManifest:
    root = Path(package)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "authoritative commissioning package must be a real directory"
        )
    expected_names = {
        _INIT_NAME,
        _MANIFEST_NAME,
        *FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES,
    }
    if {
        child.name for child in root.iterdir()
        if not child.is_symlink() and child.is_file()
    } != expected_names:
        raise ValueError(
            "authoritative commissioning package member set mismatch"
        )
    if any(child.is_symlink() or not child.is_file() for child in root.iterdir()):
        raise ValueError(
            "authoritative commissioning package may contain regular files only"
        )
    manifest = decode_fast_paper_authoritative_commissioning_manifest(
        (root / _MANIFEST_NAME).read_text(encoding="utf-8")
    )
    _require_manifest_identity(
        manifest,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    _verify_payloads(
        manifest,
        {
            name: (root / name).read_bytes()
            for name in FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES
        },
    )
    return manifest


def verify_fast_paper_authoritative_commissioning_wheel(
    wheel_path: str | Path,
    *,
    expected_source_sha: str,
    expected_platform: str,
    expected_assets: Mapping[str, Path] | None = None,
) -> FastPaperAuthoritativeCommissioningManifest:
    path = Path(wheel_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "authoritative commissioning wheel must be an existing file"
        )
    expected_names = {
        f"{_PACKAGE_PREFIX}{_INIT_NAME}",
        f"{_PACKAGE_PREFIX}{_MANIFEST_NAME}",
        *(
            f"{_PACKAGE_PREFIX}{name}"
            for name in FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES
        ),
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                info.filename
                for info in archive.infolist()
                if info.filename.startswith(_PACKAGE_PREFIX)
            ]
            if len(names) != len(set(names)) or set(names) != expected_names:
                raise ValueError(
                    "authoritative commissioning wheel package member set mismatch"
                )
            manifest = (
                decode_fast_paper_authoritative_commissioning_manifest(
                    archive.read(
                        f"{_PACKAGE_PREFIX}{_MANIFEST_NAME}"
                    ).decode("utf-8")
                )
            )
            payloads = {
                name: archive.read(f"{_PACKAGE_PREFIX}{name}")
                for name in FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES
            }
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(
            "unable to verify authoritative commissioning wheel"
        ) from exc
    _require_manifest_identity(
        manifest,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    _verify_payloads(manifest, payloads)
    if expected_assets is not None:
        paths = _validate_assets(expected_assets)
        for record in manifest.assets:
            if payloads[record.name] != paths[record.name].read_bytes():
                raise ValueError(
                    "authoritative commissioning wheel does not match checkout assets"
                )
    return manifest


def _verify_payloads(
    manifest: FastPaperAuthoritativeCommissioningManifest,
    payloads: Mapping[str, bytes],
) -> None:
    records = {value.name: value for value in manifest.assets}
    if set(payloads) != set(records):
        raise ValueError(
            "authoritative commissioning payload set mismatch"
        )
    for name, payload in payloads.items():
        record = records[name]
        if len(payload) != record.size or hashlib.sha256(payload).hexdigest() != record.sha256:
            raise ValueError(
                "authoritative commissioning payload fingerprint mismatch"
            )
    _require_unit_safety(
        payloads["shreks-paper-campaign.fast-paper.service"]
    )


def _require_unit_safety(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "authoritative Fast PAPER unit must be UTF-8"
        ) from exc
    for line in _REQUIRED_UNIT_LINES:
        if line not in text:
            raise ValueError(
                f"authoritative Fast PAPER unit is missing required line: {line}"
            )
    for token in _FORBIDDEN_UNIT_TEXT:
        if token in text:
            raise ValueError(
                f"authoritative Fast PAPER unit contains forbidden text: {token}"
            )


def _validate_assets(assets: Mapping[str, Path]) -> dict[str, Path]:
    if (
        not isinstance(assets, Mapping)
        or set(assets)
        != set(FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES)
    ):
        raise ValueError(
            "authoritative commissioning assets must contain exact member set"
        )
    result = {}
    for name in FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES:
        path = Path(assets[name])
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                f"authoritative commissioning asset {name} must be a regular file"
            )
        result[name] = path
    return result


def _manifest_material(
    *,
    source_sha: str,
    platform: str,
    assets: tuple[FastPaperAuthoritativeCommissioningAsset, ...],
) -> dict[str, object]:
    return {
        "schema_name": FAST_PAPER_AUTHORITATIVE_COMMISSIONING_SCHEMA_NAME,
        "schema_version": FAST_PAPER_AUTHORITATIVE_COMMISSIONING_SCHEMA_VERSION,
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
    manifest: FastPaperAuthoritativeCommissioningManifest,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> None:
    _require_source_sha(expected_source_sha)
    if (
        manifest.source_sha != expected_source_sha
        or manifest.platform != expected_platform
    ):
        raise ValueError(
            "authoritative commissioning release/platform identity mismatch"
        )


def _require_source_sha(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            "authoritative commissioning source SHA must be 40 lowercase hex"
        )


def _require_sha256(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            "authoritative commissioning SHA-256 must be 64 lowercase hex"
        )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


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
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
