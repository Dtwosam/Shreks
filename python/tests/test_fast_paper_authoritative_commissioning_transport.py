from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from shreks_brain.fast_paper_authoritative_commissioning_assets import (
    FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES,
    stage_fast_paper_authoritative_commissioning_package,
    verify_fast_paper_authoritative_commissioning_package,
    verify_fast_paper_authoritative_commissioning_wheel,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_SHA = "a" * 40
_PLATFORM = "x86_64-unknown-linux-gnu"


def _assets() -> dict[str, Path]:
    return {
        "shreks-paper-campaign.fast-paper.service": (
            _REPO_ROOT
            / "deploy"
            / "systemd"
            / "shreks-paper-campaign.fast-paper.service"
        ),
        "shreks-fast-paper-authoritative.env.example": (
            _REPO_ROOT
            / "deploy"
            / "systemd"
            / "shreks-fast-paper-authoritative.env.example"
        ),
    }


def test_authoritative_commissioning_package_and_wheel_are_exact(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    manifest = stage_fast_paper_authoritative_commissioning_package(
        source_sha=_SOURCE_SHA,
        platform=_PLATFORM,
        assets=_assets(),
        destination=package,
    )
    restored = verify_fast_paper_authoritative_commissioning_package(
        package,
        expected_source_sha=_SOURCE_SHA,
        expected_platform=_PLATFORM,
    )
    assert restored == manifest
    assert tuple(value.name for value in manifest.assets) == (
        FAST_PAPER_AUTHORITATIVE_COMMISSIONING_ASSET_NAMES
    )

    wheel = tmp_path / "shreks_brain-0.1.0-py3-none-any.whl"
    prefix = "shreks_brain/_sealed_fast_paper_authoritative_commissioning/"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in sorted(package.iterdir()):
            archive.write(path, f"{prefix}{path.name}")

    verified = verify_fast_paper_authoritative_commissioning_wheel(
        wheel,
        expected_source_sha=_SOURCE_SHA,
        expected_platform=_PLATFORM,
        expected_assets=_assets(),
    )
    assert verified == manifest


def test_authoritative_commissioning_rejects_legacy_or_shadow_entrypoint(
    tmp_path: Path,
) -> None:
    assets = _assets()
    unsafe = tmp_path / "unsafe.service"
    unsafe.write_text(
        assets["shreks-paper-campaign.fast-paper.service"]
        .read_text(encoding="utf-8")
        .replace(
            "shreks_brain.fast_paper_runtime.authoritative_runtime",
            "shreks_brain.observer_campaign.runtime",
        ),
        encoding="utf-8",
    )
    assets["shreks-paper-campaign.fast-paper.service"] = unsafe
    with pytest.raises(ValueError, match="required|forbidden"):
        stage_fast_paper_authoritative_commissioning_package(
            source_sha=_SOURCE_SHA,
            platform=_PLATFORM,
            assets=assets,
            destination=tmp_path / "unsafe-package",
        )


def test_release_build_seals_authoritative_candidate_without_switching_active_unit() -> None:
    build = (
        _REPO_ROOT / "deploy" / "release" / "build_release.sh"
    ).read_text(encoding="utf-8")
    pyproject = (
        _REPO_ROOT / "python" / "pyproject.toml"
    ).read_text(encoding="utf-8")
    active = (
        _REPO_ROOT / "deploy" / "systemd" / "shreks-paper-campaign.service"
    ).read_text(encoding="utf-8")
    candidate = (
        _REPO_ROOT
        / "deploy"
        / "systemd"
        / "shreks-paper-campaign.fast-paper.service"
    ).read_text(encoding="utf-8")

    assert "stage_fast_paper_authoritative_commissioning_package" in build
    assert "verify_fast_paper_authoritative_commissioning_wheel" in build
    assert (
        '"shreks_brain._sealed_fast_paper_authoritative_commissioning"'
        in pyproject
    )
    assert "shreks_brain.observer_campaign.runtime" in active
    assert "shreks_brain.fast_paper_runtime.authoritative_runtime" in candidate
