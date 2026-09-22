from __future__ import annotations

from pathlib import Path


def test_helper_installation_proof_refresh_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-g1c-v2-paper-manifest-manager-install-proof-refresh"

    assert (
        f'INSTALL_PROOF_REFRESH="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$INSTALL_PROOF_REFRESH"' in workflow
    assert 'test ! -L "$INSTALL_PROOF_REFRESH"' in workflow
    assert 'test -x "$INSTALL_PROOF_REFRESH"' in workflow
    assert (
        'INSTALL_PROOF_REFRESH_RESOLVED="$(readlink -f "$INSTALL_PROOF_REFRESH")"'
        in workflow
    )
    assert (
        f'test "$INSTALL_PROOF_REFRESH_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_paper_manifest_manager_installation_proof_refresh "
        "as installation_proof_refresh"
        in workflow
    )
    assert (
        "manifest manager installation proof refresh module is outside the exact deployed release"
        in workflow
    )
    assert "paper_manifest_manager_installation_proof_refresh=present" in workflow
    assert "paper_manifest_manager_installation_proof_refresh_path=%s" in workflow
    assert "paper_manifest_manager_installation_proof_refresh_module=%s" in workflow

    assert 'exec "$INSTALL_PROOF_REFRESH"' not in workflow
    assert "installation_proof_refresh.main(" not in workflow

    assert "## Refresh the exact-release helper installation proof" in runbook
    assert script in runbook
    assert 'CURRENT_SHA="$(basename "$CURRENT_RELEASE")"' in runbook
    assert 'PROOF_DIR="/root/shreks-paper-manifest-manager-proof-refresh-$CURRENT_SHA"' in runbook
    assert "requires the helper to already match the exact current release" in runbook
    assert "does not install, replace, chmod, or chown the helper" in runbook
    assert "installation-proof.json" in runbook
    assert "manifest_rotation_authority=NOT_GRANTED" in runbook
    assert "Do not execute decision-backed readiness merely because this fresh proof exists." in runbook
