from __future__ import annotations

from pathlib import Path


def test_g1c_v2_candidate_value_preflight_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-g1c-v2-candidate-value-preflight"

    assert (
        f'CANDIDATE_VALUE_PREFLIGHT="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$CANDIDATE_VALUE_PREFLIGHT"' in workflow
    assert 'test ! -L "$CANDIDATE_VALUE_PREFLIGHT"' in workflow
    assert 'test -x "$CANDIDATE_VALUE_PREFLIGHT"' in workflow
    assert (
        'CANDIDATE_VALUE_PREFLIGHT_RESOLVED="$(readlink -f '
        '"$CANDIDATE_VALUE_PREFLIGHT")"'
        in workflow
    )
    assert (
        f'test "$CANDIDATE_VALUE_PREFLIGHT_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_candidate_value_preflight "
        "as candidate_value_preflight"
        in workflow
    )
    assert (
        "candidate value preflight module is outside the exact deployed release"
        in workflow
    )
    assert "g1c_v2_candidate_value_preflight=present" in workflow
    assert "g1c_v2_candidate_value_preflight_path=%s" in workflow
    assert "g1c_v2_candidate_value_preflight_module=%s" in workflow

    assert 'exec "$CANDIDATE_VALUE_PREFLIGHT"' not in workflow
    assert "candidate_value_preflight.main(" not in workflow

    heading = "### Preflight one G1C v2 candidate-value proposal for compatibility"
    assert heading in runbook
    section = runbook.split(heading, 1)[1].split("\n### ", 1)[0]
    assert script in section
    assert "--source-runtime-manifest" in section
    assert "--sizing-proposal" in section
    assert "--cohort" in section
    assert "--v2-host-request-authority" in section
    assert "--paper-run-id" in section
    assert "--start-at-unix-ms" in section
    assert "--destination" in section
    assert "MULTI_REFERENCE_REVIEW" in section
    assert "READY_FOR_EXPLICIT_CANDIDATE_VALUE_DECISION" in section
    assert "candidate_compatibility=COMPATIBLE" in section
    assert "preflight_authority=EVIDENCE_ONLY" in section
    assert "candidate_value_authority=NOT_GRANTED" in section
    assert "candidate_authoring_authority=NOT_GRANTED" in section
    assert "rotation_authority=NOT_GRANTED" in section
    assert "scoring_authority=NOT_GRANTED" in section
    assert "paper_promotion_authority=BLOCKED" in section
    assert "live_authority=DISABLED" in section
    assert "does not approve candidate values" in section
    assert "separate explicit candidate-value decision remains mandatory" in section
