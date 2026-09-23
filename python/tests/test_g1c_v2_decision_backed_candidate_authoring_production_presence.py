from __future__ import annotations

from pathlib import Path


def test_g1c_v2_decision_backed_candidate_authoring_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-g1c-v2-decision-backed-candidate-author"

    assert (
        f'DECISION_BACKED_CANDIDATE_AUTHORING="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$DECISION_BACKED_CANDIDATE_AUTHORING"' in workflow
    assert 'test ! -L "$DECISION_BACKED_CANDIDATE_AUTHORING"' in workflow
    assert 'test -x "$DECISION_BACKED_CANDIDATE_AUTHORING"' in workflow
    assert (
        'DECISION_BACKED_CANDIDATE_AUTHORING_RESOLVED="$(readlink -f '
        '"$DECISION_BACKED_CANDIDATE_AUTHORING")"'
        in workflow
    )
    assert (
        f'test "$DECISION_BACKED_CANDIDATE_AUTHORING_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_decision_backed_candidate_authoring "
        "as decision_backed_candidate_authoring"
        in workflow
    )
    assert (
        "decision-backed candidate authoring module is outside the exact deployed release"
        in workflow
    )
    assert "g1c_v2_decision_backed_candidate_authoring=present" in workflow
    assert "g1c_v2_decision_backed_candidate_authoring_path=%s" in workflow
    assert "g1c_v2_decision_backed_candidate_authoring_module=%s" in workflow

    assert 'exec "$DECISION_BACKED_CANDIDATE_AUTHORING"' not in workflow
    assert "decision_backed_candidate_authoring.main(" not in workflow

    assert "### Author one exact decision-backed G1C v2 candidate" in runbook
    assert script in runbook
    assert "--source-runtime-manifest" in runbook
    assert "--decision-backed-candidate-authority" in runbook
    assert "--destination" in runbook
    assert "There are no raw paper-run, timestamp, quote, entry-amount, cohort, request, or decision inputs." in runbook
    assert "must reproduce the candidate manifest SHA/fingerprint committed by the authority" in runbook
    assert "does not create a transition binding" in runbook
    assert "Do not run transition binding from this candidate alone." in runbook

    heading = "### Author one exact decision-backed G1C v2 candidate"
    section = runbook.split(heading, 1)[1].split("\n### ", 1)[0]
    assert 'EXPECTED_RELEASE_SHA="<exact-production-verified-release-sha>"' in section
    assert 'CURRENT_SHA="$(basename "$CURRENT_RELEASE")"' in section
    assert 'test "$CURRENT_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'MANIFEST_SHA="$(' in section
    assert 'test "$MANIFEST_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'sudo test ! -e "$CANDIDATE"' in section
    assert 'test "$(readlink -f /opt/shreks/current)" = "$CURRENT_RELEASE"' in section
