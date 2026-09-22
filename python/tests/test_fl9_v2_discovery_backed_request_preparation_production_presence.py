from __future__ import annotations

from pathlib import Path


def test_fl9_v2_discovery_backed_request_prepare_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-fl9-v2-discovery-backed-request-prepare"

    assert (
        f'FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARE="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARE"' in workflow
    assert 'test ! -L "$FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARE"' in workflow
    assert 'test -x "$FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARE"' in workflow
    assert (
        'FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARE_RESOLVED="$(readlink -f '
        '"$FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARE")"'
        in workflow
    )
    assert (
        f'test "$FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARE_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.fl9_v2_discovery_backed_request_preparation "
        "as discovery_backed_request_preparation"
        in workflow
    )
    assert (
        "discovery-backed request preparation module is outside the exact deployed release"
        in workflow
    )
    assert "fl9_v2_discovery_backed_request_prepare=present" in workflow
    assert "fl9_v2_discovery_backed_request_prepare_path=%s" in workflow
    assert "fl9_v2_discovery_backed_request_prepare_module=%s" in workflow

    assert 'exec "$FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARE"' not in workflow
    assert "discovery_backed_request_preparation.main(" not in workflow

    heading = "### Prepare one discovery-backed FL9 V2 request"
    assert heading in runbook
    section = runbook[runbook.index(heading):]
    next_heading = "## Rollback"
    section = section[: section.index(next_heading)]

    assert script in section
    for flag in (
        "--discovery-authority-binding",
        "--proof-workspace",
        "--observer-database",
        "--cohort",
        "--hydration-policy",
        "--training-economics-overlay",
        "--training-execution-cost-policy",
        "--request-destination",
        "--evidence-destination",
        "--preparation-destination",
        "--evaluation-policy",
        "--future-path-label-version",
        "--counterfactual-base-quantity",
        "--champion-version",
        "--model-version-prefix",
        "--training-policy-version",
        "--reason",
    ):
        assert flag in section

    assert "DISCOVERY_BOUND_REQUEST_ONLY" in section
    assert "scoring_authority=NOT_GRANTED" in section
    assert "champion_publication_authority=NOT_GRANTED" in section
    assert "paper_promotion_authority=BLOCKED" in section
    assert "live_authority=DISABLED" in section
    assert "does not execute scoring or model fitting" in section
