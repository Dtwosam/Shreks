from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_DIR = _REPO_ROOT / "deploy" / "release"
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

_MANAGER_SPEC = importlib.util.spec_from_file_location(
    "shreks_g2_release_manager_process_activation_test",
    _RELEASE_DIR / "release_manager.py",
)
assert _MANAGER_SPEC is not None and _MANAGER_SPEC.loader is not None
release_manager = importlib.util.module_from_spec(_MANAGER_SPEC)
sys.modules[_MANAGER_SPEC.name] = release_manager
_MANAGER_SPEC.loader.exec_module(release_manager)


def _paths(tmp_path: Path) -> release_manager.ReleasePaths:
    return release_manager.ReleasePaths(
        releases_dir=tmp_path / "opt" / "shreks" / "releases",
        current_link=tmp_path / "opt" / "shreks" / "current",
        systemd_dir=tmp_path / "etc" / "systemd" / "system",
    )


def test_upgrade_explicitly_stops_runtime_services_before_switch(monkeypatch, tmp_path: Path):
    paths = _paths(tmp_path)
    previous = paths.releases_dir / ("a" * 40)
    release_dir = paths.releases_dir / ("b" * 40)
    previous.mkdir(parents=True)
    release_dir.mkdir(parents=True)

    monkeypatch.setattr(release_manager, "_require_managed_release", lambda *_: None)
    monkeypatch.setattr(release_manager, "_current_release", lambda *_: previous)
    monkeypatch.setattr(release_manager, "_install_units", lambda *_: None)
    monkeypatch.setattr(release_manager, "_atomic_switch", lambda *_: None)
    monkeypatch.setattr(release_manager, "_require_runtime_healthy", lambda *_: None)

    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> None:
        calls.append(command)

    release_manager.activate_release(release_dir, paths, command_runner=runner)

    assert calls[0] == (
        "systemctl",
        "stop",
        "shreks-paper-campaign.service",
        "shreks-paper-evidence.service",
        "shreks-observe.service",
        "shreks.target",
    )
    assert calls[1:] == [
        ("systemctl", "daemon-reload"),
        ("systemctl", "start", "shreks.target"),
    ]


def test_same_release_reconciles_runtime_processes_instead_of_returning(
    monkeypatch, tmp_path: Path
):
    paths = _paths(tmp_path)
    release_dir = paths.releases_dir / ("b" * 40)
    release_dir.mkdir(parents=True)

    monkeypatch.setattr(release_manager, "_require_managed_release", lambda *_: None)
    monkeypatch.setattr(release_manager, "_current_release", lambda *_: release_dir)
    monkeypatch.setattr(release_manager, "_install_units", lambda *_: None)

    health_calls: list[Path | None] = []
    monkeypatch.setattr(
        release_manager,
        "_require_runtime_healthy",
        lambda _runner, active_release=None: health_calls.append(active_release),
    )

    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> None:
        calls.append(command)

    release_manager.activate_release(release_dir, paths, command_runner=runner)

    assert calls == [
        (
            "systemctl",
            "stop",
            "shreks-paper-campaign.service",
            "shreks-paper-evidence.service",
            "shreks-observe.service",
            "shreks.target",
        ),
        ("systemctl", "daemon-reload"),
        ("systemctl", "start", "shreks.target"),
    ]
    assert health_calls == [release_dir]


def test_runtime_process_identity_accepts_only_activated_release(tmp_path: Path):
    release_dir = tmp_path / "opt" / "shreks" / "releases" / ("b" * 40)
    release_dir.mkdir(parents=True)

    expected = {
        "shreks-observe.service": (
            101,
            release_dir / "target" / "release" / "shreks-observe",
            release_dir,
        ),
        "shreks-paper-evidence.service": (
            102,
            release_dir / "target" / "release" / "shreks-paper-evidence",
            release_dir,
        ),
        "shreks-paper-campaign.service": (
            103,
            release_dir / ".venv" / "bin" / "python3.12",
            release_dir,
        ),
    }

    release_manager._require_runtime_processes_from_release(
        release_dir,
        identity_reader=lambda unit: expected[unit],
    )


def test_runtime_process_identity_rejects_stale_previous_release(tmp_path: Path):
    release_dir = tmp_path / "opt" / "shreks" / "releases" / ("b" * 40)
    previous = tmp_path / "opt" / "shreks" / "releases" / ("a" * 40)
    release_dir.mkdir(parents=True)
    previous.mkdir(parents=True)

    identities = {
        "shreks-observe.service": (
            201,
            previous / "target" / "release" / "shreks-observe",
            previous,
        ),
        "shreks-paper-evidence.service": (
            202,
            release_dir / "target" / "release" / "shreks-paper-evidence",
            release_dir,
        ),
        "shreks-paper-campaign.service": (
            203,
            release_dir / ".venv" / "bin" / "python3.12",
            release_dir,
        ),
    }

    with pytest.raises(
        release_manager.ReleaseManagerError,
        match="shreks-observe.service.*activated release",
    ):
        release_manager._require_runtime_processes_from_release(
            release_dir,
            identity_reader=lambda unit: identities[unit],
        )


def test_runtime_process_identity_rejects_wrong_native_binary(tmp_path: Path):
    release_dir = tmp_path / "opt" / "shreks" / "releases" / ("b" * 40)
    release_dir.mkdir(parents=True)

    identities = {
        "shreks-observe.service": (
            301,
            release_dir / "target" / "release" / "not-shreks-observe",
            release_dir,
        ),
        "shreks-paper-evidence.service": (
            302,
            release_dir / "target" / "release" / "shreks-paper-evidence",
            release_dir,
        ),
        "shreks-paper-campaign.service": (
            303,
            release_dir / ".venv" / "bin" / "python3.12",
            release_dir,
        ),
    }

    with pytest.raises(
        release_manager.ReleaseManagerError,
        match="shreks-observe.service.*executable",
    ):
        release_manager._require_runtime_processes_from_release(
            release_dir,
            identity_reader=lambda unit: identities[unit],
        )
