from __future__ import annotations

from pathlib import Path


def test_decision_backed_rotation_plan_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-g1c-v2-decision-backed-rotation-plan"

    assert (
        f'DECISION_BACKED_ROTATION_PLAN="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$DECISION_BACKED_ROTATION_PLAN"' in workflow
    assert 'test ! -L "$DECISION_BACKED_ROTATION_PLAN"' in workflow
    assert 'test -x "$DECISION_BACKED_ROTATION_PLAN"' in workflow
    assert (
        'DECISION_BACKED_ROTATION_PLAN_RESOLVED="$(readlink -f '
        '"$DECISION_BACKED_ROTATION_PLAN")"'
        in workflow
    )
    assert (
        f'test "$DECISION_BACKED_ROTATION_PLAN_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_decision_backed_rotation_plan "
        "as decision_backed_rotation_plan"
        in workflow
    )
    assert (
        "decision-backed rotation plan module is outside the exact deployed release"
        in workflow
    )
    assert "g1c_v2_decision_backed_rotation_plan=present" in workflow
    assert "g1c_v2_decision_backed_rotation_plan_path=%s" in workflow
    assert "g1c_v2_decision_backed_rotation_plan_module=%s" in workflow

    assert 'exec "$DECISION_BACKED_ROTATION_PLAN"' not in workflow
    assert "decision_backed_rotation_plan.main(" not in workflow

    heading = "### Plan one exact decision-backed G1C v2 protected rotation"
    assert heading in runbook
    section = runbook[runbook.index(heading):]
    next_heading = "## Prove protected PAPER manifest rotation readiness"
    section = section[: section.index(next_heading)]

    assert script in section
    assert "--candidate-runtime-manifest" in section
    assert "--transition-binding" in section
    assert "--decision-backed-candidate-authority" in section
    assert "--readiness-receipt" in section
    assert "--expected-release-source-sha" in section
    assert (
        'PLAN_DIR="/root/shreks-g1c-v2-decision-backed-rotation-plan-$CURRENT_SHA"'
        in section
    )
    assert "rotation-plan.json" in section
    assert "READY_FOR_TRUSTED_ADMIN_ROTATION_CEREMONY" in section
    assert "planning_authority=READ_ONLY" in section
    assert "manifest_rotation_authority=NOT_EXERCISED" in section
    assert "scoring_authority=NOT_GRANTED" in section
    assert "paper_promotion_authority=BLOCKED" in section
    assert "live_authority=DISABLED" in section
    assert (
        "Do not execute the planned manager argv merely because this plan exists."
        in section
    )
    assert "sudo /usr/local/sbin/shreks-paper-manifest-manager rotate" not in section
