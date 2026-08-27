from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_DIR = _REPO_ROOT / "deploy" / "release"
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

_MANAGER_SPEC = importlib.util.spec_from_file_location(
    "shreks_g2_release_manager_first_install_test", _RELEASE_DIR / "release_manager.py"
)
assert _MANAGER_SPEC is not None and _MANAGER_SPEC.loader is not None
release_manager = importlib.util.module_from_spec(_MANAGER_SPEC)
sys.modules[_MANAGER_SPEC.name] = release_manager
_MANAGER_SPEC.loader.exec_module(release_manager)


def test_first_install_does_not_stop_target_before_units_exist(monkeypatch, tmp_path: Path):
    paths = release_manager.ReleasePaths(
        releases_dir=tmp_path / "opt" / "shreks" / "releases",
        current_link=tmp_path / "opt" / "shreks" / "current",
        systemd_dir=tmp_path / "etc" / "systemd" / "system",
    )
    release_dir = paths.releases_dir / ("a" * 40)
    release_dir.mkdir(parents=True)

    monkeypatch.setattr(release_manager, "_require_managed_release", lambda *_: None)
    monkeypatch.setattr(release_manager, "_current_release", lambda *_: None)
    monkeypatch.setattr(release_manager, "_install_units", lambda *_: None)
    monkeypatch.setattr(release_manager, "_atomic_switch", lambda *_: None)
    monkeypatch.setattr(release_manager, "_require_runtime_healthy", lambda *_: None)

    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> None:
        calls.append(command)
        if command == ("systemctl", "stop", "shreks.target"):
            raise RuntimeError("Unit shreks.target not loaded")

    release_manager.activate_release(release_dir, paths, command_runner=runner)

    assert calls == [
        ("systemctl", "daemon-reload"),
        ("systemctl", "start", "shreks.target"),
    ]
