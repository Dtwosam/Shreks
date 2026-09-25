from __future__ import annotations

from pathlib import Path


def test_fast_lane_has_no_fl9_v2_scoring_authority_control_path() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    pyproject = (repo_root / "python" / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (repo_root / "deploy" / "release" / "README.md").read_text(
        encoding="utf-8"
    )
    master = (repo_root / "SHREKS_MASTER_SOURCE_OF_TRUTH.md").read_text(
        encoding="utf-8"
    )
    build_order = (repo_root / "SHREKS_BUILD_ORDER.md").read_text(
        encoding="utf-8"
    )

    assert "shreks-fl9-v2-scoring-authority-decide" not in pyproject
    assert not (
        repo_root
        / "python"
        / "src"
        / "shreks_brain"
        / "fl9_v2_scoring_authority.py"
    ).exists()
    assert not (repo_root / "python" / "tests" / "test_fl9_v2_scoring_authority.py").exists()
    assert not (
        repo_root
        / "python"
        / "tests"
        / "test_fl9_v2_scoring_authority_production_presence.py"
    ).exists()

    assert "FL9_V2_SCORING_AUTHORITY" not in workflow
    assert "fl9_v2_scoring_authority_decide=present" not in workflow
    assert "### Decide one discovery-backed FL9 V2 scoring authority" not in runbook
    assert "AUTHORIZE_ONE_SCORING_RUN" not in runbook
    assert "REJECT_SCORING_RUN" not in runbook

    assert not (
        repo_root
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-09-25-fl9-v2-one-request-scoring-authority-design.md"
    ).exists()
    assert not (
        repo_root
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-09-25-fl9-v2-scoring-authority-production-presence-design.md"
    ).exists()

    assert (
        "EVENT -> UPDATE STATE -> FORECAST FUTURE PATHS -> PRICE EXECUTION -> "
        "ESTIMATE NET EV -> CHOOSE ACTION -> RISK CHECK -> EXECUTE/WAIT -> "
        "RECORD -> LEARN"
        in master
    )
    assert "## FL9 — Learned continuous action policy" in build_order
    assert "Evaluate `BUY`, `SKIP`, `HOLD`, `REDUCE`, and `SELL`" in build_order

    # Legacy deterministic scoring is preserved only as a baseline/research signal.
    assert (
        "Legacy Fresh Launch, Graduation/Breakout, First Pullback, deterministic "
        "scoring, and the existing PAPER campaign remain useful as **baselines, "
        "research signals, and compatibility tests**."
        in build_order
    )
