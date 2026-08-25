from __future__ import annotations

from dataclasses import fields
import importlib.util
from pathlib import Path
import stat
import sys

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_DIR = _REPO_ROOT / "deploy" / "release"
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

_BUNDLE_SPEC = importlib.util.spec_from_file_location(
    "shreks_g2_release_bundle_for_manager_tests", _RELEASE_DIR / "release_bundle.py"
)
assert _BUNDLE_SPEC is not None and _BUNDLE_SPEC.loader is not None
release_bundle = importlib.util.module_from_spec(_BUNDLE_SPEC)
sys.modules[_BUNDLE_SPEC.name] = release_bundle
_BUNDLE_SPEC.loader.exec_module(release_bundle)

_MANAGER_SPEC = importlib.util.spec_from_file_location(
    "shreks_g2_release_manager", _RELEASE_DIR / "release_manager.py"
)
assert _MANAGER_SPEC is not None and _MANAGER_SPEC.loader is not None
release_manager = importlib.util.module_from_spec(_MANAGER_SPEC)
sys.modules[_MANAGER_SPEC.name] = release_manager
_MANAGER_SPEC.loader.exec_module(release_manager)


PLATFORM = "x86_64-unknown-linux-gnu"
SHA_A = "a" * 40
SHA_B = "b" * 40


def _payloads(marker: str) -> dict[str, bytes]:
    return {
        "target/release/shreks-observe": f"observer-{marker}".encode(),
        "target/release/shreks-paper-evidence": f"evidence-{marker}".encode(),
        "deploy/systemd/shreks-observe.service": f"observe-unit-{marker}\n".encode(),
        "deploy/systemd/shreks-paper-evidence.service": f"evidence-unit-{marker}\n".encode(),
        "deploy/systemd/shreks-paper-campaign.service": f"campaign-unit-{marker}\n".encode(),
        "deploy/systemd/shreks.target": f"target-unit-{marker}\n".encode(),
        "wheelhouse/shreks_brain-0.1.0-py3-none-any.whl": f"wheel-{marker}".encode(),
    }


def _write_payload_tree(root: Path, marker: str) -> None:
    for relative, payload in _payloads(marker).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _build_bundle(tmp_path: Path, source_sha: str, marker: str):
    bundle_root = tmp_path / f"bundle-{source_sha}"
    staging = bundle_root / "staging"
    staging.mkdir(parents=True)
    _write_payload_tree(staging, marker)
    manifest = release_bundle.build_release_manifest(staging, source_sha, PLATFORM)
    manifest_payload = release_bundle.encode_release_manifest(manifest)
    (staging / "RELEASE_MANIFEST.json").write_bytes(manifest_payload)

    manifest_path = bundle_root / "RELEASE_MANIFEST.json"
    manifest_path.write_bytes(manifest_payload)
    archive_path = bundle_root / f"shreks-release-{source_sha}.tar.gz"
    archive_sha = release_bundle.write_release_archive(staging, manifest, archive_path)
    checksum_path = bundle_root / f"{archive_path.name}.sha256"
    checksum_path.write_text(f"{archive_sha}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, checksum_path, manifest_path, manifest


def _paths(tmp_path: Path):
    return release_manager.ReleasePaths(
        releases_dir=tmp_path / "opt" / "shreks" / "releases",
        current_link=tmp_path / "opt" / "shreks" / "current",
        systemd_dir=tmp_path / "etc" / "systemd" / "system",
    )


class StageRunner:
    def __init__(self):
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command: tuple[str, ...]) -> None:
        self.calls.append(command)
        if len(command) >= 4 and command[1:3] == ("-m", "venv"):
            venv = Path(command[-1])
            python = venv / "bin" / "python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("#!/bin/sh\n", encoding="utf-8")
            python.chmod(0o755)


class SymlinkVenvRunner(StageRunner):
    def __call__(self, command: tuple[str, ...]) -> None:
        self.calls.append(command)
        if len(command) >= 4 and command[1:3] == ("-m", "venv"):
            venv = Path(command[-1])
            bin_dir = venv / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            python3 = bin_dir / "python3"
            python3.write_text("#!/bin/sh\n", encoding="utf-8")
            python3.chmod(0o755)
            (bin_dir / "python").symlink_to("python3")


class FailingPipRunner(StageRunner):
    def __call__(self, command: tuple[str, ...]) -> None:
        super().__call__(command)
        if len(command) >= 4 and command[1:4] == ("-m", "pip", "install"):
            raise RuntimeError("simulated pip failure")


class SystemctlRunner:
    def __init__(self, fail_first_health_check: bool = False):
        self.calls: list[tuple[str, ...]] = []
        self.fail_first_health_check = fail_first_health_check
        self.health_checks = 0

    def __call__(self, command: tuple[str, ...]) -> None:
        self.calls.append(command)
        if command == ("systemctl", "is-active", "--quiet", "shreks.target"):
            self.health_checks += 1
            if self.fail_first_health_check and self.health_checks == 1:
                raise RuntimeError("simulated inactive target")


def _stage(
    tmp_path: Path,
    paths,
    source_sha: str,
    marker: str,
    *,
    runner: StageRunner | None = None,
) -> Path:
    archive, checksum, manifest, _ = _build_bundle(tmp_path, source_sha, marker)
    return release_manager.stage_release(
        archive,
        checksum,
        manifest,
        paths,
        python_executable="/usr/bin/python3",
        command_runner=runner or StageRunner(),
    )


def test_release_paths_expose_only_release_current_and_systemd_locations(tmp_path: Path):
    assert {field.name for field in fields(release_manager.ReleasePaths)} == {
        "releases_dir",
        "current_link",
        "systemd_dir",
    }
    paths = _paths(tmp_path)
    rendered = " ".join(str(getattr(paths, field.name)) for field in fields(paths))
    assert "/etc/shreks" not in rendered
    assert "/var/lib/shreks" not in rendered


def test_stage_release_verifies_bundle_builds_final_path_copied_venv_and_preserves_payload(tmp_path: Path):
    paths = _paths(tmp_path)
    runner = StageRunner()
    archive, checksum, manifest_path, manifest = _build_bundle(tmp_path, SHA_A, "a")

    release_dir = release_manager.stage_release(
        archive,
        checksum,
        manifest_path,
        paths,
        python_executable="/usr/bin/python3",
        command_runner=runner,
    )

    assert release_dir == paths.releases_dir / SHA_A
    assert release_dir.is_dir()
    assert stat.S_IMODE(release_dir.stat().st_mode) == 0o755
    assert (release_dir / "RELEASE_MANIFEST.json").read_bytes() == manifest_path.read_bytes()
    for entry in manifest.files:
        assert (release_dir / entry.path).is_file()
    assert stat.S_IMODE((release_dir / "target/release/shreks-observe").stat().st_mode) & 0o111
    assert stat.S_IMODE((release_dir / "target/release/shreks-paper-evidence").stat().st_mode) & 0o111

    venv = release_dir / ".venv"
    wheel = next((release_dir / "wheelhouse").glob("shreks_brain-*.whl"))
    assert runner.calls == [
        ("/usr/bin/python3", "-m", "venv", "--copies", str(venv)),
        (
            str(venv / "bin" / "python"),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            str(wheel),
        ),
    ]
    assert not paths.current_link.exists()


def test_stage_release_rejects_symlinked_virtualenv_and_cleans_incomplete_release(tmp_path: Path):
    paths = _paths(tmp_path)
    archive, checksum, manifest_path, _ = _build_bundle(tmp_path, SHA_A, "a")

    with pytest.raises(release_manager.ReleaseManagerError):
        release_manager.stage_release(
            archive,
            checksum,
            manifest_path,
            paths,
            command_runner=SymlinkVenvRunner(),
        )

    assert not (paths.releases_dir / SHA_A).exists()
    assert not paths.current_link.exists()


def test_venv_install_failure_cleans_release_without_touching_current(tmp_path: Path):
    paths = _paths(tmp_path)
    archive, checksum, manifest_path, _ = _build_bundle(tmp_path, SHA_A, "a")

    with pytest.raises(release_manager.ReleaseManagerError):
        release_manager.stage_release(
            archive,
            checksum,
            manifest_path,
            paths,
            command_runner=FailingPipRunner(),
        )

    assert not (paths.releases_dir / SHA_A).exists()
    assert not paths.current_link.exists()


def test_stage_failure_never_changes_current_or_creates_release(tmp_path: Path):
    paths = _paths(tmp_path)
    archive, checksum, manifest_path, _ = _build_bundle(tmp_path, SHA_A, "a")
    checksum.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")

    with pytest.raises(release_manager.ReleaseManagerError):
        release_manager.stage_release(
            archive,
            checksum,
            manifest_path,
            paths,
            command_runner=StageRunner(),
        )

    assert not paths.current_link.exists()
    assert not (paths.releases_dir / SHA_A).exists()


def test_existing_verified_release_is_reused_without_reinstall(tmp_path: Path):
    paths = _paths(tmp_path)
    first = StageRunner()
    release_dir = _stage(tmp_path / "first", paths, SHA_A, "a", runner=first)
    archive, checksum, manifest_path, _ = _build_bundle(tmp_path / "second", SHA_A, "a")
    second = StageRunner()

    reused = release_manager.stage_release(
        archive,
        checksum,
        manifest_path,
        paths,
        command_runner=second,
    )

    assert reused == release_dir
    assert second.calls == []


def test_existing_release_with_tampered_payload_fails_closed(tmp_path: Path):
    paths = _paths(tmp_path)
    release_dir = _stage(tmp_path / "first", paths, SHA_A, "a")
    (release_dir / "target/release/shreks-observe").write_bytes(b"tampered")
    archive, checksum, manifest_path, _ = _build_bundle(tmp_path / "second", SHA_A, "a")

    with pytest.raises(release_manager.ReleaseManagerError):
        release_manager.stage_release(
            archive,
            checksum,
            manifest_path,
            paths,
            command_runner=StageRunner(),
        )


def test_successful_activation_atomically_points_current_and_installs_units(tmp_path: Path):
    paths = _paths(tmp_path)
    release_dir = _stage(tmp_path / "bundle", paths, SHA_A, "a")
    runner = SystemctlRunner()

    release_manager.activate_release(release_dir, paths, command_runner=runner)

    assert paths.current_link.is_symlink()
    assert paths.current_link.resolve() == release_dir.resolve()
    assert runner.calls == [
        ("systemctl", "stop", "shreks.target"),
        ("systemctl", "daemon-reload"),
        ("systemctl", "start", "shreks.target"),
        ("systemctl", "is-active", "--quiet", "shreks.target"),
    ]
    for name in (
        "shreks-observe.service",
        "shreks-paper-evidence.service",
        "shreks-paper-campaign.service",
        "shreks.target",
    ):
        assert (paths.systemd_dir / name).read_bytes() == (
            release_dir / "deploy" / "systemd" / name
        ).read_bytes()


def test_failed_activation_restores_previous_release_and_units(tmp_path: Path):
    paths = _paths(tmp_path)
    previous = _stage(tmp_path / "previous", paths, SHA_B, "previous")
    new = _stage(tmp_path / "new", paths, SHA_A, "new")
    release_manager.activate_release(previous, paths, command_runner=SystemctlRunner())
    previous_units = {
        path.name: path.read_bytes() for path in paths.systemd_dir.iterdir() if path.is_file()
    }

    runner = SystemctlRunner(fail_first_health_check=True)
    with pytest.raises(release_manager.ReleaseManagerError):
        release_manager.activate_release(new, paths, command_runner=runner)

    assert paths.current_link.resolve() == previous.resolve()
    assert {
        path.name: path.read_bytes() for path in paths.systemd_dir.iterdir() if path.is_file()
    } == previous_units
    assert runner.health_checks == 2
    assert runner.calls.count(("systemctl", "daemon-reload")) == 2
    assert runner.calls.count(("systemctl", "start", "shreks.target")) == 2


def test_first_deploy_health_failure_leaves_no_active_release_claim(tmp_path: Path):
    paths = _paths(tmp_path)
    release_dir = _stage(tmp_path / "new", paths, SHA_A, "new")
    runner = SystemctlRunner(fail_first_health_check=True)

    with pytest.raises(release_manager.ReleaseManagerError):
        release_manager.activate_release(release_dir, paths, command_runner=runner)

    assert not paths.current_link.exists()
    assert ("systemctl", "stop", "shreks.target") in runner.calls


def test_activate_existing_reverifies_payload_before_any_systemctl_call(tmp_path: Path):
    paths = _paths(tmp_path)
    release_dir = _stage(tmp_path / "bundle", paths, SHA_A, "a")
    (release_dir / "target/release/shreks-paper-evidence").write_bytes(b"tampered")
    runner = SystemctlRunner()

    with pytest.raises(release_manager.ReleaseManagerError):
        release_manager.activate_existing(SHA_A, paths, command_runner=runner)

    assert runner.calls == []
    assert not paths.current_link.exists()


def test_current_path_must_be_absent_or_symlink(tmp_path: Path):
    paths = _paths(tmp_path)
    release_dir = _stage(tmp_path / "bundle", paths, SHA_A, "a")
    paths.current_link.parent.mkdir(parents=True, exist_ok=True)
    paths.current_link.write_text("not-a-symlink", encoding="utf-8")
    runner = SystemctlRunner()

    with pytest.raises(release_manager.ReleaseManagerError):
        release_manager.activate_release(release_dir, paths, command_runner=runner)

    assert runner.calls == []
