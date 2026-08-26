from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_DIR = _REPO_ROOT / "deploy" / "release"
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

_BUNDLE_SPEC = importlib.util.spec_from_file_location(
    "shreks_arm64_release_bundle", _RELEASE_DIR / "release_bundle.py"
)
assert _BUNDLE_SPEC is not None and _BUNDLE_SPEC.loader is not None
release_bundle = importlib.util.module_from_spec(_BUNDLE_SPEC)
sys.modules[_BUNDLE_SPEC.name] = release_bundle
_BUNDLE_SPEC.loader.exec_module(release_bundle)

_MANAGER_SPEC = importlib.util.spec_from_file_location(
    "shreks_arm64_release_manager", _RELEASE_DIR / "release_manager.py"
)
assert _MANAGER_SPEC is not None and _MANAGER_SPEC.loader is not None
release_manager = importlib.util.module_from_spec(_MANAGER_SPEC)
sys.modules[_MANAGER_SPEC.name] = release_manager
_MANAGER_SPEC.loader.exec_module(release_manager)


SOURCE_SHA = "a" * 40
X86_PLATFORM = "x86_64-unknown-linux-gnu"
ARM64_PLATFORM = "aarch64-unknown-linux-gnu"
PAYLOADS = {
    "target/release/shreks-observe": b"observer-binary",
    "target/release/shreks-paper-evidence": b"evidence-binary",
    "deploy/systemd/shreks-observe.service": b"observe-unit\n",
    "deploy/systemd/shreks-paper-evidence.service": b"evidence-unit\n",
    "deploy/systemd/shreks-paper-campaign.service": b"campaign-unit\n",
    "deploy/systemd/shreks.target": b"target-unit\n",
    "wheelhouse/shreks_brain-0.1.0-py3-none-any.whl": b"wheel-bytes",
}


def _write_payload_tree(root: Path) -> None:
    for relative, payload in PAYLOADS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _build_bundle(tmp_path: Path, platform: str):
    staging = tmp_path / "staging"
    staging.mkdir(parents=True)
    _write_payload_tree(staging)
    manifest = release_bundle.build_release_manifest(staging, SOURCE_SHA, platform)
    manifest_payload = release_bundle.encode_release_manifest(manifest)
    (staging / "RELEASE_MANIFEST.json").write_bytes(manifest_payload)

    manifest_path = tmp_path / "RELEASE_MANIFEST.json"
    manifest_path.write_bytes(manifest_payload)
    archive_path = tmp_path / f"shreks-release-{SOURCE_SHA}.tar.gz"
    archive_sha = release_bundle.write_release_archive(staging, manifest, archive_path)
    checksum_path = tmp_path / f"{archive_path.name}.sha256"
    checksum_path.write_text(
        f"{archive_sha}  {archive_path.name}\n", encoding="utf-8"
    )
    return archive_path, checksum_path, manifest_path


def test_release_manifest_accepts_exactly_x86_64_and_aarch64_linux_gnu(tmp_path: Path):
    for index, platform in enumerate((X86_PLATFORM, ARM64_PLATFORM)):
        staging = tmp_path / f"supported-{index}"
        staging.mkdir()
        _write_payload_tree(staging)
        manifest = release_bundle.build_release_manifest(staging, SOURCE_SHA, platform)
        assert release_bundle.decode_release_manifest(
            release_bundle.encode_release_manifest(manifest)
        ).platform == platform

    for index, platform in enumerate(
        (
            "arm64-unknown-linux-gnu",
            "aarch64-unknown-linux-musl",
            "x86_64-apple-darwin",
            "riscv64gc-unknown-linux-gnu",
            "",
        )
    ):
        staging = tmp_path / f"unsupported-{index}"
        staging.mkdir()
        _write_payload_tree(staging)
        with pytest.raises(release_bundle.ReleaseBundleError, match="unsupported release platform"):
            release_bundle.build_release_manifest(staging, SOURCE_SHA, platform)


def test_release_manager_rejects_manifest_platform_mismatch_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    archive, checksum, manifest = _build_bundle(tmp_path / "bundle", ARM64_PLATFORM)
    monkeypatch.setattr(
        release_manager.os, "uname", lambda: SimpleNamespace(machine="x86_64")
    )
    paths = release_manager.ReleasePaths(
        releases_dir=tmp_path / "opt" / "shreks" / "releases",
        current_link=tmp_path / "opt" / "shreks" / "current",
        systemd_dir=tmp_path / "etc" / "systemd" / "system",
    )

    def unexpected_command(command: tuple[str, ...]) -> None:
        raise AssertionError(f"platform mismatch must fail before staging: {command!r}")

    with pytest.raises(release_manager.ReleaseManagerError, match="platform"):
        release_manager.stage_release(
            archive,
            checksum,
            manifest,
            paths,
            command_runner=unexpected_command,
        )

    assert not paths.releases_dir.exists()


def test_release_manager_unknown_host_architecture_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        release_manager.os, "uname", lambda: SimpleNamespace(machine="mystery64")
    )
    with pytest.raises(release_manager.ReleaseManagerError, match="unsupported host architecture"):
        release_manager._host_release_platform()


def test_build_script_requires_requested_platform_to_equal_native_rust_host():
    script = (_RELEASE_DIR / "build_release.sh").read_text(encoding="utf-8")

    assert 'PLATFORM="${PLATFORM:-x86_64-unknown-linux-gnu}"' in script
    assert "rustc -vV" in script
    assert "host:" in script
    assert "requested release platform does not match native Rust host" in script
    assert '--platform "$PLATFORM"' in script


def test_ci_has_native_arm64_release_build_job():
    workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "ARM64 release build" in workflow
    assert "ubuntu-24.04-arm" in workflow
    assert "PLATFORM: aarch64-unknown-linux-gnu" in workflow
    assert "deploy/release/build_release.sh" in workflow
    assert "release_bundle.py verify" in workflow
