from __future__ import annotations

import importlib.util
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_DIR = _REPO_ROOT / "deploy" / "release"
_REPORTER = "target/release/shreks-fast-lane-acceptance"
_HISTORICAL_STATIC_PAYLOADS = {
    "deploy/systemd/shreks-observe.service",
    "deploy/systemd/shreks-paper-campaign.service",
    "deploy/systemd/shreks-paper-evidence.service",
    "deploy/systemd/shreks.target",
    "target/release/shreks-observe",
    "target/release/shreks-paper-evidence",
}


def _load_release_bundle():
    module_path = _RELEASE_DIR / "release_bundle.py"
    spec = importlib.util.spec_from_file_location(
        "shreks_fl1_legacy_verifier_compatibility", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verified_release_keeps_historical_runtime_payload_paths_only():
    build_script = (_RELEASE_DIR / "build_release.sh").read_text(encoding="utf-8")
    bundle_source = (_RELEASE_DIR / "release_bundle.py").read_text(encoding="utf-8")
    release_bundle = _load_release_bundle()

    assert set(release_bundle._REQUIRED_STATIC_PAYLOAD_PATHS) == _HISTORICAL_STATIC_PAYLOADS
    assert not hasattr(release_bundle, "_OPTIONAL_STATIC_PAYLOAD_PATHS")
    assert _REPORTER not in bundle_source
    assert "--bin shreks-fast-lane-acceptance" not in build_script
    assert "cp target/release/shreks-fast-lane-acceptance" not in build_script


def test_release_manager_runtime_binary_allowlist_stays_historically_compatible():
    manager_source = (_RELEASE_DIR / "release_manager.py").read_text(encoding="utf-8")

    assert '"target/release/shreks-observe"' in manager_source
    assert '"target/release/shreks-paper-evidence"' in manager_source
    assert _REPORTER not in manager_source
    assert "_verify_payloads_for_staging(staging_dir, manifest)" in manager_source
    assert "_verify_stored_release(release_dir)" in manager_source
