from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_DIR = _REPO_ROOT / "deploy" / "release"
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

_BUNDLE_SPEC = importlib.util.spec_from_file_location(
    "shreks_g4_release_bundle", _RELEASE_DIR / "release_bundle.py"
)
assert _BUNDLE_SPEC is not None and _BUNDLE_SPEC.loader is not None
release_bundle = importlib.util.module_from_spec(_BUNDLE_SPEC)
sys.modules[_BUNDLE_SPEC.name] = release_bundle
_BUNDLE_SPEC.loader.exec_module(release_bundle)

_MANAGER_SPEC = importlib.util.spec_from_file_location(
    "shreks_g4_release_manager", _RELEASE_DIR / "release_manager.py"
)
assert _MANAGER_SPEC is not None and _MANAGER_SPEC.loader is not None
release_manager = importlib.util.module_from_spec(_MANAGER_SPEC)
sys.modules[_MANAGER_SPEC.name] = release_manager
_MANAGER_SPEC.loader.exec_module(release_manager)

_TELEMETRY_UNITS = (
    "shreks-telemetry.service",
    "shreks-telemetry.timer",
)
_CORE_RUNTIME_UNITS = (
    "shreks-observe.service",
    "shreks-paper-evidence.service",
    "shreks-paper-campaign.service",
    "shreks.target",
)


def test_verified_release_payload_ships_telemetry_units() -> None:
    static_paths = set(release_bundle._REQUIRED_STATIC_PAYLOAD_PATHS)
    for unit in _TELEMETRY_UNITS:
        relative = f"deploy/systemd/{unit}"
        assert relative in static_paths

    build_script = (_RELEASE_DIR / "build_release.sh").read_text(encoding="utf-8")
    for unit in _TELEMETRY_UNITS:
        relative = f"deploy/systemd/{unit}"
        assert f'cp {relative} "$STAGING/{relative}"' in build_script


def test_release_manager_installs_telemetry_but_health_gates_only_core_paper_runtime() -> None:
    installed = tuple(release_manager._SYSTEMD_UNIT_NAMES)
    core = tuple(release_manager._CORE_RUNTIME_UNIT_NAMES)

    assert core == _CORE_RUNTIME_UNITS
    for unit in _TELEMETRY_UNITS:
        assert unit in installed
        assert unit not in core

    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> None:
        calls.append(command)

    release_manager._require_runtime_healthy(runner)
    assert calls == [
        ("systemctl", "is-active", "--quiet", unit)
        for unit in _CORE_RUNTIME_UNITS
    ]
