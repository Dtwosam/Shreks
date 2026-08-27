from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_DIR = _REPO_ROOT / "deploy" / "release"
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

_BUNDLE_SPEC = importlib.util.spec_from_file_location(
    "shreks_g2_release_bundle_for_linux_venv_tests", _RELEASE_DIR / "release_bundle.py"
)
assert _BUNDLE_SPEC is not None and _BUNDLE_SPEC.loader is not None
release_bundle = importlib.util.module_from_spec(_BUNDLE_SPEC)
sys.modules[_BUNDLE_SPEC.name] = release_bundle
_BUNDLE_SPEC.loader.exec_module(release_bundle)

_MANAGER_SPEC = importlib.util.spec_from_file_location(
    "shreks_g2_release_manager_for_linux_venv_tests", _RELEASE_DIR / "release_manager.py"
)
assert _MANAGER_SPEC is not None and _MANAGER_SPEC.loader is not None
release_manager = importlib.util.module_from_spec(_MANAGER_SPEC)
sys.modules[_MANAGER_SPEC.name] = release_manager
_MANAGER_SPEC.loader.exec_module(release_manager)


def _minimal_copied_venv(tmp_path: Path) -> Path:
    release_dir = tmp_path / "release"
    venv = release_dir / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    (venv / "lib").mkdir()
    return release_dir


def test_runtime_venv_accepts_standard_linux_lib64_to_lib_symlink(tmp_path: Path):
    release_dir = _minimal_copied_venv(tmp_path)
    venv = release_dir / ".venv"
    (venv / "lib64").symlink_to("lib")

    release_manager._verify_runtime_venv(release_dir)


def test_runtime_venv_still_rejects_other_symlinks(tmp_path: Path):
    release_dir = _minimal_copied_venv(tmp_path)
    venv = release_dir / ".venv"
    (venv / "escape").symlink_to("/tmp")

    with pytest.raises(release_manager.ReleaseManagerError, match="symlinks are not allowed"):
        release_manager._verify_runtime_venv(release_dir)
