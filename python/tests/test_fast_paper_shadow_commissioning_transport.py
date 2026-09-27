from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import zipfile

import pytest

from shreks_brain.fast_paper_shadow_commissioning_assets import (
    FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES,
    FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_NAME,
    FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_VERSION,
    build_fast_paper_shadow_commissioning_manifest,
    decode_fast_paper_shadow_commissioning_manifest,
    encode_fast_paper_shadow_commissioning_manifest,
    materialize_fast_paper_shadow_commissioning_assets_from_directory,
    stage_fast_paper_shadow_commissioning_package,
    verify_fast_paper_shadow_commissioning_package,
    verify_fast_paper_shadow_commissioning_wheel,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILD_SCRIPT = _REPO_ROOT / "deploy" / "release" / "build_release.sh"
_RELEASE_BUNDLE = _REPO_ROOT / "deploy" / "release" / "release_bundle.py"
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"
_UNIT = _REPO_ROOT / "deploy" / "systemd" / "shreks-fast-paper-shadow.service"
_ENV = (
    _REPO_ROOT
    / "deploy"
    / "systemd"
    / "shreks-fast-paper-shadow.env.example"
)


def _assets(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "assets"
    root.mkdir(parents=True)
    unit = root / "shreks-fast-paper-shadow.service"
    env = root / "shreks-fast-paper-shadow.env.example"
    unit.write_text("[Service]\nExecStart=/exact/shadow\n", encoding="utf-8")
    env.write_text("SHREKS_FAST_PAPER_SHADOW_INTERVAL_SECONDS=2.0\n", encoding="utf-8")
    return {
        unit.name: unit,
        env.name: env,
    }


def test_commissioning_manifest_is_exact_canonical_and_fingerprints_assets(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    manifest = build_fast_paper_shadow_commissioning_manifest(
        source_sha="a" * 40,
        platform="aarch64-unknown-linux-gnu",
        assets=assets,
    )
    payload = encode_fast_paper_shadow_commissioning_manifest(manifest)

    assert decode_fast_paper_shadow_commissioning_manifest(payload) == manifest
    assert manifest.schema_name == FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_NAME
    assert manifest.schema_version == FAST_PAPER_SHADOW_COMMISSIONING_SCHEMA_VERSION
    assert tuple(value.name for value in manifest.assets) == (
        FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES
    )
    for value in manifest.assets:
        source = assets[value.name]
        assert value.size == source.stat().st_size
        assert value.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_commissioning_package_materialization_is_private_idempotent_and_tamper_evident(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    package = tmp_path / "package"
    manifest = stage_fast_paper_shadow_commissioning_package(
        source_sha="b" * 40,
        platform="x86_64-unknown-linux-gnu",
        assets=assets,
        destination=package,
    )
    assert verify_fast_paper_shadow_commissioning_package(
        package,
        expected_source_sha="b" * 40,
        expected_platform="x86_64-unknown-linux-gnu",
    ) == manifest

    root = tmp_path / "materialized"
    target = materialize_fast_paper_shadow_commissioning_assets_from_directory(
        package,
        root,
        expected_source_sha="b" * 40,
        expected_platform="x86_64-unknown-linux-gnu",
    )
    assert target == root / ("b" * 40)
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    for name in FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES:
        path = target / name
        assert path.read_bytes() == assets[name].read_bytes()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert (
        materialize_fast_paper_shadow_commissioning_assets_from_directory(
            package,
            root,
            expected_source_sha="b" * 40,
            expected_platform="x86_64-unknown-linux-gnu",
        )
        == target
    )

    (target / FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES[0]).write_bytes(
        b"drift"
    )
    with pytest.raises(ValueError, match="fingerprint|manifest|materialized|mismatch"):
        materialize_fast_paper_shadow_commissioning_assets_from_directory(
            package,
            root,
            expected_source_sha="b" * 40,
            expected_platform="x86_64-unknown-linux-gnu",
        )


def test_commissioning_wheel_verifier_requires_exact_package_and_checkout_bytes(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    package = tmp_path / "package"
    stage_fast_paper_shadow_commissioning_package(
        source_sha="c" * 40,
        platform="aarch64-unknown-linux-gnu",
        assets=assets,
        destination=package,
    )
    wheel = tmp_path / "shreks_brain-0.1.0-py3-none-any.whl"
    prefix = "shreks_brain/_sealed_fast_paper_shadow_commissioning/"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in sorted(package.iterdir()):
            archive.write(path, f"{prefix}{path.name}")

    verify_fast_paper_shadow_commissioning_wheel(
        wheel,
        expected_source_sha="c" * 40,
        expected_platform="aarch64-unknown-linux-gnu",
        expected_assets=assets,
    )

    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(
            f"{prefix}{FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES[0]}",
            b"tampered",
        )
    with pytest.raises(ValueError):
        verify_fast_paper_shadow_commissioning_wheel(
            wheel,
            expected_source_sha="c" * 40,
            expected_platform="aarch64-unknown-linux-gnu",
        )


def test_release_build_transports_commissioning_assets_inside_hashed_wheel_only() -> None:
    script = _BUILD_SCRIPT.read_text(encoding="utf-8")
    bundle = _RELEASE_BUNDLE.read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")

    for required in (
        "stage_fast_paper_shadow_commissioning_package",
        "verify_fast_paper_shadow_commissioning_wheel",
        "_sealed_fast_paper_shadow_commissioning",
        "shreks_brain._sealed_fast_paper_shadow_commissioning",
        "shreks-fast-paper-shadow.service",
        "shreks-fast-paper-shadow.env.example",
    ):
        assert required in (script + "\n" + pyproject)

    assert "deploy/systemd/shreks-fast-paper-shadow.service" not in bundle
    assert "deploy/systemd/shreks-fast-paper-shadow.env.example" not in bundle


def test_commissioning_transport_source_has_no_runtime_or_capital_authority() -> None:
    import shreks_brain.fast_paper_shadow_commissioning_assets as assets_module

    payload = Path(assets_module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "systemctl",
        "sudo ",
        "/etc/systemd",
        "/usr/local",
        "shreks_brain.scoring",
        "score_candidate",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in payload

    unit = _UNIT.read_text(encoding="utf-8")
    assert "WantedBy=shreks.target" not in unit
    assert "PartOf=shreks.target" not in unit
    assert "PrivateNetwork=true" in unit
    assert _ENV.is_file()
