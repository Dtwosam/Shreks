from __future__ import annotations

from pathlib import Path


def test_decision_backed_rotation_readiness_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-g1c-v2-decision-backed-rotation-readiness"

    assert (
        f'DECISION_BACKED_ROTATION_READINESS="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$DECISION_BACKED_ROTATION_READINESS"' in workflow
    assert 'test ! -L "$DECISION_BACKED_ROTATION_READINESS"' in workflow
    assert 'test -x "$DECISION_BACKED_ROTATION_READINESS"' in workflow
    assert (
        'DECISION_BACKED_ROTATION_READINESS_RESOLVED="$(readlink -f '
        '"$DECISION_BACKED_ROTATION_READINESS")"'
        in workflow
    )
    assert (
        f'test "$DECISION_BACKED_ROTATION_READINESS_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_decision_backed_rotation_readiness "
        "as decision_backed_rotation_readiness"
        in workflow
    )
    assert (
        "decision-backed rotation readiness module is outside the exact deployed release"
        in workflow
    )
    assert "g1c_v2_decision_backed_rotation_readiness=present" in workflow
    assert "g1c_v2_decision_backed_rotation_readiness_path=%s" in workflow
    assert "g1c_v2_decision_backed_rotation_readiness_module=%s" in workflow

    assert 'exec "$DECISION_BACKED_ROTATION_READINESS"' not in workflow
    assert "decision_backed_rotation_readiness.main(" not in workflow

    assert "### Prove exact decision-backed G1C v2 rotation readiness" in runbook
    assert script in runbook
    assert "--candidate-runtime-manifest" in runbook
    assert "--transition-binding" in runbook
    assert "--decision-backed-candidate-authority" in runbook
    assert "--installation-proof" in runbook
    assert "--expected-release-source-sha" in runbook
    assert "--expected-binding-fingerprint" not in runbook.split(
        "### Prove exact decision-backed G1C v2 rotation readiness", 1
    )[1].split("## Prove protected PAPER manifest rotation readiness", 1)[0]
    assert "fresh exact-release installation proof" in runbook
    assert "derives the binding fingerprint from the authenticated binding" in runbook
    assert "status=READY_EVIDENCE_ONLY" in runbook
    assert "manifest_rotation_authority=NOT_GRANTED" in runbook
    assert "paper_promotion_authority=BLOCKED" in runbook
    assert "live_authority=DISABLED" in runbook
    assert "does not invoke the manifest manager" in runbook
