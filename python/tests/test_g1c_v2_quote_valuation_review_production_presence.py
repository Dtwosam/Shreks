from __future__ import annotations

from pathlib import Path


def test_g1c_v2_quote_valuation_review_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    review_script = "shreks-g1c-v2-quote-valuation-review"

    assert (
        f'QUOTE_REVIEW="/opt/shreks/current/.venv/bin/{review_script}"'
        in workflow
    )
    assert 'test -f "$QUOTE_REVIEW"' in workflow
    assert 'test ! -L "$QUOTE_REVIEW"' in workflow
    assert 'test -x "$QUOTE_REVIEW"' in workflow
    assert 'QUOTE_REVIEW_RESOLVED="$(readlink -f "$QUOTE_REVIEW")"' in workflow
    assert (
        f'test "$QUOTE_REVIEW_RESOLVED" = "$EXPECTED/.venv/bin/{review_script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_quote_valuation_review as quote_review"
        in workflow
    )
    assert "quote valuation review module is outside the exact deployed release" in workflow
    assert "g1c_v2_quote_valuation_review=present" in workflow
    assert "g1c_v2_quote_valuation_review_path=%s" in workflow
    assert "g1c_v2_quote_valuation_review_module=%s" in workflow

    assert 'exec "$QUOTE_REVIEW"' not in workflow
    assert "quote_review.main(" not in workflow

    assert "### Review multiple exact quote-valuation references" in runbook
    assert review_script in runbook
    assert "REVIEW_EVIDENCE_ONLY" in runbook
    assert "median_exact_reference_values" in runbook
    assert "does not authorize production candidate values" in runbook
    assert "Do not run candidate authority from this review alone." in runbook
