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
    assert "### 2.9 No scoring control path" in master
    assert (
        "OBSERVE -> LABEL -> TRAIN CHALLENGER -> CHRONOLOGICAL REPLAY -> "
        "PAPER/SHADOW -> COMPARE NET EXPECTANCY/RISK/COST/LATENCY -> "
        "PROMOTE PROVEN CHAMPION -> RUN -> RECORD ACTUAL + COUNTERFACTUAL "
        "OUTCOMES -> RETRAIN"
        in master
    )
    assert "Training may run repeatedly and automatically" in master
    assert (
        "No new scoring subsystem, scoring authority, score threshold, or "
        "score-gated approval path may be introduced"
        in master
    )
    assert (
        "Existing legacy deterministic score artifacts may remain only as "
        "frozen compatibility/regression baselines"
        in master
    )
    assert (
        "deterministic scores, and current setup engines remain useful as "
        "baselines/features/challengers"
        not in master
    )
    assert (
        "The existing deterministic score is retained as an interpretable "
        "baseline/feature"
        not in master
    )

    assert "## FL9 — Learned continuous action policy" in build_order
    assert "Evaluate `BUY`, `SKIP`, `HOLD`, `REDUCE`, and `SELL`" in build_order
    assert "## 4.9 No scoring control path" in build_order
    assert (
        "Any implementation slice that introduces scoring authority, "
        "score-gated action approval, or a score-to-trade control path is "
        "architecture drift"
        in build_order
    )
    assert (
        "Legacy deterministic score artifacts are frozen comparison fixtures, "
        "not an extensible trading architecture"
        in build_order
    )
    assert "SCORING_AUTHORITY=" not in build_order
    assert "SCORING_CONTROL_PATH=FORBIDDEN" in build_order
