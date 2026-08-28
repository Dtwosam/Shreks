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


def test_release_manifest_allowlist_requires_fast_lane_acceptance_binary():
    source = (_REPO_ROOT / "deploy" / "release" / "release_bundle.py").read_text(
        encoding="utf-8"
    )
    assert f'"{_REPORTER}"' in source


def test_release_manager_verifies_fast_lane_acceptance_binary():
    source = (_REPO_ROOT / "deploy" / "release" / "release_manager.py").read_text(
        encoding="utf-8"
    )
    assert f'"{_REPORTER}"' in source
