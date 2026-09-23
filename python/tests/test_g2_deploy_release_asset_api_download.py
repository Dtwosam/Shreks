from __future__ import annotations

from pathlib import Path


def test_deploy_downloads_only_verified_release_asset_ids_via_api() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    assert "gh release download" not in workflow
    assert '"asset_id"' in workflow
    assert "release asset id is invalid" in workflow
    assert "release asset ids must be unique" in workflow
    assert "release-asset-download-map" in workflow
    assert (
        'gh api -H "Accept: application/octet-stream" '
        '"repos/$GITHUB_REPOSITORY/releases/assets/$ASSET_ID"'
        in workflow
    )
    assert 'test "$(find dist/deploy -maxdepth 1 -type f | wc -l)" -eq 3' in workflow

    download_api = workflow.index(
        'gh api -H "Accept: application/octet-stream" '
        '"repos/$GITHUB_REPOSITORY/releases/assets/$ASSET_ID"'
    )
    local_verify = workflow.index("release_bundle.py verify", download_api)
    host_tokens = [
        workflow.find(token, download_api)
        for token in ('ssh "', 'scp "')
        if workflow.find(token, download_api) != -1
    ]
    assert host_tokens
    assert download_api < local_verify < min(host_tokens)
