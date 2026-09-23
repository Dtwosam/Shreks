from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys

import shreks_brain


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTROL_SOURCE = _REPO_ROOT / "deploy" / "release"


def test_installed_standalone_manifest_manager_loads_sealed_control_dependencies(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_root = tmp_path / "overlay" / "shreks_brain"
    control_package = package_root / "_sealed_deploy_control"
    control_package.mkdir(parents=True)
    (control_package / "__init__.py").write_text(
        '"""Sealed deployment-control payload; not a runtime API."""\n',
        encoding="utf-8",
    )
    for name in (
        "release_bundle.py",
        "release_manager.py",
        "paper_manifest_manager.py",
    ):
        shutil.copy2(_CONTROL_SOURCE / name, control_package / name)

    original_path = list(shreks_brain.__path__)
    monkeypatch.setattr(
        shreks_brain,
        "__path__",
        [*original_path, str(package_root)],
    )

    for name in tuple(sys.modules):
        if name.startswith("shreks_brain._sealed_deploy_control"):
            sys.modules.pop(name, None)

    installed = (
        tmp_path
        / "usr"
        / "local"
        / "sbin"
        / "shreks-paper-manifest-manager"
    )
    installed.parent.mkdir(parents=True)
    shutil.copy2(_CONTROL_SOURCE / "paper_manifest_manager.py", installed)

    spec = importlib.util.spec_from_file_location(
        "installed_shreks_paper_manifest_manager",
        installed,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    assert module.ReleaseBundleError.__module__ == (
        "shreks_brain._sealed_deploy_control.release_bundle"
    )
    assert module.ReleaseManagerError.__module__ == (
        "shreks_brain._sealed_deploy_control.release_manager"
    )


def test_sealed_release_manager_uses_package_relative_release_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_root = tmp_path / "overlay" / "shreks_brain"
    control_package = package_root / "_sealed_deploy_control"
    control_package.mkdir(parents=True)
    (control_package / "__init__.py").write_text(
        '"""Sealed deployment-control payload; not a runtime API."""\n',
        encoding="utf-8",
    )
    for name in ("release_bundle.py", "release_manager.py"):
        shutil.copy2(_CONTROL_SOURCE / name, control_package / name)

    original_path = list(shreks_brain.__path__)
    monkeypatch.setattr(
        shreks_brain,
        "__path__",
        [*original_path, str(package_root)],
    )

    for name in tuple(sys.modules):
        if name.startswith("shreks_brain._sealed_deploy_control"):
            sys.modules.pop(name, None)

    from shreks_brain._sealed_deploy_control import release_manager

    assert release_manager.ReleaseBundleError.__module__ == (
        "shreks_brain._sealed_deploy_control.release_bundle"
    )
