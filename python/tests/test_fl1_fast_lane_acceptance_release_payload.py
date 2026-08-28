from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORTER = "target/release/shreks-fast-lane-acceptance"


def test_verified_release_builds_and_copies_fast_lane_acceptance_binary():
    source = (_REPO_ROOT / "deploy" / "release" / "build_release.sh").read_text(
        encoding="utf-8"
    )
    assert "--bin shreks-fast-lane-acceptance" in source
    assert (
        'cp target/release/shreks-fast-lane-acceptance '
        '"$STAGING/target/release/shreks-fast-lane-acceptance"'
    ) in source


def test_release_manifest_allowlist_accepts_fast_lane_reporter_without_invalidating_legacy_releases():
    source = (_REPO_ROOT / "deploy" / "release" / "release_bundle.py").read_text(
        encoding="utf-8"
    )
    assert "_OPTIONAL_STATIC_PAYLOAD_PATHS" in source
    assert f'"{_REPORTER}"' in source


def test_release_manager_verifies_reporter_through_generic_manifest_integrity_checks():
    source = (_REPO_ROOT / "deploy" / "release" / "release_manager.py").read_text(
        encoding="utf-8"
    )
    assert "_verify_payloads_for_staging(staging_dir, manifest)" in source
    assert "_verify_stored_release(release_dir)" in source
