from __future__ import annotations

from pathlib import Path


def test_paper_manifest_manager_update_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    pyproject = (repo_root / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    script = "shreks-g1c-v2-paper-manifest-manager-update"

    assert (
        f'PAPER_MANIFEST_MANAGER_UPDATE="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$PAPER_MANIFEST_MANAGER_UPDATE"' in workflow
    assert 'test ! -L "$PAPER_MANIFEST_MANAGER_UPDATE"' in workflow
    assert 'test -x "$PAPER_MANIFEST_MANAGER_UPDATE"' in workflow
    assert (
        'PAPER_MANIFEST_MANAGER_UPDATE_RESOLVED="$(readlink -f '
        '"$PAPER_MANIFEST_MANAGER_UPDATE")"'
        in workflow
    )
    assert (
        f'test "$PAPER_MANIFEST_MANAGER_UPDATE_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_paper_manifest_manager_update "
        "as paper_manifest_manager_update"
        in workflow
    )
    assert "paper_manifest_manager_update=present" in workflow
    assert "paper_manifest_manager_update_path=%s" in workflow
    assert "paper_manifest_manager_update_module=%s" in workflow

    assert 'exec "$PAPER_MANIFEST_MANAGER_UPDATE"' not in workflow
    assert "paper_manifest_manager_update.main(" not in workflow

    assert (
        f'{script} = "shreks_brain.g1c_v2_paper_manifest_manager_update:main"'
        in pyproject
    )
