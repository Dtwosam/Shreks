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
    "shreks_g2_release_manager_process_activation",
    _RELEASE_DIR / "release_manager.py",
)
assert _MANAGER_SPEC is not None and _MANAGER_SPEC.loader is not None
release_manager = importlib.util.module_from_spec(_MANAGER_SPEC)
sys.modules[_MANAGER_SPEC.name] = release_manager
_MANAGER_SPEC.loader.exec_module(release_manager)


RUNTIME_SERVICES = (
    "shreks-observe.service",
    "shreks-paper-evidence.service",
    "shreks-paper-campaign.service",
)


def test_stop_runtime_stops_target_and_each_runtime_service() -> None:
    assert hasattr(release_manager, "_stop_runtime"), (
        "release activation must expose one helper that explicitly stops the target "
        "and all runtime services; stopping shreks.target alone leaves Wanted services running"
    )

    calls: list[tuple[str, ...]] = []
    release_manager._stop_runtime(calls.append)

    assert calls == [
        (
            "systemctl",
            "stop",
            "shreks.target",
            *RUNTIME_SERVICES,
        )
    ]
