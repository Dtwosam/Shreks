from __future__ import annotations

from pathlib import Path


def test_g1c_v2_decision_backed_candidate_authority_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-g1c-v2-decision-backed-candidate-authority-bind"

    assert (
        f'DECISION_BACKED_CANDIDATE_AUTHORITY="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$DECISION_BACKED_CANDIDATE_AUTHORITY"' in workflow
    assert 'test ! -L "$DECISION_BACKED_CANDIDATE_AUTHORITY"' in workflow
    assert 'test -x "$DECISION_BACKED_CANDIDATE_AUTHORITY"' in workflow
    assert (
        'DECISION_BACKED_CANDIDATE_AUTHORITY_RESOLVED="$(readlink -f '
        '"$DECISION_BACKED_CANDIDATE_AUTHORITY")"'
        in workflow
    )
    assert (
        f'test "$DECISION_BACKED_CANDIDATE_AUTHORITY_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_decision_backed_candidate_authority "
        "as decision_backed_candidate_authority"
        in workflow
    )
    assert (
        "decision-backed candidate authority module is outside the exact deployed release"
        in workflow
    )
    assert "g1c_v2_decision_backed_candidate_authority=present" in workflow
    assert "g1c_v2_decision_backed_candidate_authority_path=%s" in workflow
    assert "g1c_v2_decision_backed_candidate_authority_module=%s" in workflow

    assert 'exec "$DECISION_BACKED_CANDIDATE_AUTHORITY"' not in workflow
    assert "decision_backed_candidate_authority.main(" not in workflow

    assert "### Bind one decision-backed G1C v2 candidate authority" in runbook
    assert script in runbook
    assert "--candidate-value-preflight" in runbook
    assert "--candidate-value-decision" in runbook
    assert "--paper-run-id" not in runbook.split(
        "### Bind one decision-backed G1C v2 candidate authority", 1
    )[1].split("\n### ", 1)[0]
    assert "--start-at-unix-ms" not in runbook.split(
        "### Bind one decision-backed G1C v2 candidate authority", 1
    )[1].split("\n### ", 1)[0]
    assert "candidate_compatibility=COMPATIBLE" in runbook
    assert "preflight_authority=EVIDENCE_ONLY" in runbook
    assert "EXPLICIT_PRODUCTION_DECISION_BOUND" in runbook
    assert "DECISION_BACKED_INPUTS_BOUND" in runbook
    assert "There are no raw paper-run, timestamp, quote-mint, quote-decimals, or entry-amount inputs." in runbook
    assert "does not emit or stage a runtime-manifest candidate" in runbook
    assert "Do not run transition binding from this authority alone." in runbook
