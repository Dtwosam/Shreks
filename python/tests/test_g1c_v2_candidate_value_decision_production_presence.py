from __future__ import annotations

from pathlib import Path


def test_g1c_v2_candidate_value_decision_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    decision_script = "shreks-g1c-v2-candidate-value-decision"

    assert (
        f'CANDIDATE_VALUE_DECISION="/opt/shreks/current/.venv/bin/{decision_script}"'
        in workflow
    )
    assert 'test -f "$CANDIDATE_VALUE_DECISION"' in workflow
    assert 'test ! -L "$CANDIDATE_VALUE_DECISION"' in workflow
    assert 'test -x "$CANDIDATE_VALUE_DECISION"' in workflow
    assert (
        'CANDIDATE_VALUE_DECISION_RESOLVED="$(readlink -f '
        '"$CANDIDATE_VALUE_DECISION")"'
        in workflow
    )
    assert (
        f'test "$CANDIDATE_VALUE_DECISION_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{decision_script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_candidate_value_decision "
        "as candidate_value_decision"
        in workflow
    )
    assert (
        "candidate value decision module is outside the exact deployed release"
        in workflow
    )
    assert "g1c_v2_candidate_value_decision=present" in workflow
    assert "g1c_v2_candidate_value_decision_path=%s" in workflow
    assert "g1c_v2_candidate_value_decision_module=%s" in workflow

    assert 'exec "$CANDIDATE_VALUE_DECISION"' not in workflow
    assert "candidate_value_decision.main(" not in workflow

    assert "### Record one explicit G1C v2 candidate-value decision" in runbook
    assert decision_script in runbook
    assert "MULTI_REFERENCE_REVIEW" in runbook
    assert "ACCEPT_PROPOSAL" in runbook
    assert "REJECT_PROPOSAL" in runbook
    assert "REPLACE_PROPOSAL" in runbook
    assert "EXPLICIT_PRODUCTION_DECISION_BOUND" in runbook
    assert "does not invoke candidate authority" in runbook
    assert "Do not run candidate authority from this decision alone." in runbook
    assert "separately explicit new-run identity/time inputs" not in runbook
    assert "future run identity/time only from the preflight" in runbook
    assert (
        "REPLACE_PROPOSAL is not eligible for the current schema-v2 "
        "candidate-authority path"
        in runbook
    )

    heading = "### Record one explicit G1C v2 candidate-value decision"
    section = runbook.split(heading, 1)[1].split("\n### ", 1)[0]
    assert 'EXPECTED_RELEASE_SHA="<exact-production-verified-release-sha>"' in section
    assert 'CURRENT_SHA="$(basename "$CURRENT_RELEASE")"' in section
    assert 'test "$CURRENT_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'MANIFEST_SHA="$(' in section
    assert 'test "$MANIFEST_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'sudo test ! -e "$DECISION_FILE"' in section
    assert 'test "$(readlink -f /opt/shreks/current)" = "$CURRENT_RELEASE"' in section
