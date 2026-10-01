from __future__ import annotations

from pathlib import Path


def test_fl9_v2_scoring_authority_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-fl9-v2-scoring-authority-decide"

    assert (
        f'FL9_V2_SCORING_AUTHORITY="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$FL9_V2_SCORING_AUTHORITY"' in workflow
    assert 'test ! -L "$FL9_V2_SCORING_AUTHORITY"' in workflow
    assert 'test -x "$FL9_V2_SCORING_AUTHORITY"' in workflow
    assert (
        'FL9_V2_SCORING_AUTHORITY_RESOLVED="$(readlink -f '
        '"$FL9_V2_SCORING_AUTHORITY")"'
        in workflow
    )
    assert (
        f'test "$FL9_V2_SCORING_AUTHORITY_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.fl9_v2_scoring_authority "
        "as fl9_v2_scoring_authority"
        in workflow
    )
    assert (
        "FL9 V2 scoring authority module is outside the exact deployed release"
        in workflow
    )
    assert "fl9_v2_scoring_authority_decide=present" in workflow
    assert "fl9_v2_scoring_authority_decide_path=%s" in workflow
    assert "fl9_v2_scoring_authority_decide_module=%s" in workflow

    assert 'exec "$FL9_V2_SCORING_AUTHORITY"' not in workflow
    assert "fl9_v2_scoring_authority.main(" not in workflow
    assert "decide_fl9_v2_scoring_authority(" not in workflow

    heading = "### Decide one discovery-backed FL9 V2 scoring authority"
    assert heading in runbook
    section = runbook[runbook.index(heading):]
    next_heading = "## Rollback"
    section = section[: section.index(next_heading)]

    assert script in section
    assert "--request-preparation" in section
    assert "--decision" in section
    assert "--decision-reason" in section
    assert "--destination" in section
    assert "AUTHORIZE_ONE_SCORING_RUN" in section
    assert "REJECT_SCORING_RUN" in section

    assert 'EXPECTED_RELEASE_SHA="<exact-production-verified-release-sha>"' in section
    assert 'CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"' in section
    assert 'CURRENT_SHA="$(basename "$CURRENT_RELEASE")"' in section
    assert 'test "$CURRENT_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'MANIFEST_SHA="$(' in section
    assert 'test "$MANIFEST_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'sudo test ! -e "$AUTHORITY"' in section
    assert 'test "$(readlink -f /opt/shreks/current)" = "$CURRENT_RELEASE"' in section

    assert "execution_scope=ONE_REQUEST_ONE_DESTINATION" in section
    assert "scoring_authority=EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN" in section
    assert "model_fitting_authority=EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN" in section
    assert "champion_publication_authority=SCORING_EVIDENCE_ONLY" in section
    assert "paper_promotion_authority=BLOCKED" in section
    assert "live_authority=DISABLED" in section
    assert "does not execute the prepared V2 host request" in section
