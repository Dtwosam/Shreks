from __future__ import annotations

from pathlib import Path


def test_g1c_v2_review_backed_entry_sizing_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    sizing_script = "shreks-g1c-v2-review-backed-entry-sizing"

    assert (
        f'REVIEW_BACKED_ENTRY_SIZING="/opt/shreks/current/.venv/bin/{sizing_script}"'
        in workflow
    )
    assert 'test -f "$REVIEW_BACKED_ENTRY_SIZING"' in workflow
    assert 'test ! -L "$REVIEW_BACKED_ENTRY_SIZING"' in workflow
    assert 'test -x "$REVIEW_BACKED_ENTRY_SIZING"' in workflow
    assert (
        'REVIEW_BACKED_ENTRY_SIZING_RESOLVED="$(readlink -f '
        '"$REVIEW_BACKED_ENTRY_SIZING")"'
        in workflow
    )
    assert (
        f'test "$REVIEW_BACKED_ENTRY_SIZING_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{sizing_script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_review_backed_entry_sizing "
        "as review_backed_entry_sizing"
        in workflow
    )
    assert (
        "review-backed entry sizing module is outside the exact deployed release"
        in workflow
    )
    assert "g1c_v2_review_backed_entry_sizing=present" in workflow
    assert "g1c_v2_review_backed_entry_sizing_path=%s" in workflow
    assert "g1c_v2_review_backed_entry_sizing_module=%s" in workflow

    assert 'exec "$REVIEW_BACKED_ENTRY_SIZING"' not in workflow
    assert "review_backed_entry_sizing.main(" not in workflow

    assert (
        "### Derive one evidence-only entry-sizing proposal from a valuation review"
        in runbook
    )
    assert sizing_script in runbook
    assert "MULTI_REFERENCE_REVIEW" in runbook
    assert "PROPOSAL_EVIDENCE_ONLY" in runbook
    assert "review fingerprint" in runbook
    assert "conservative evidence timestamp" in runbook
    assert "does not authorize production candidate values" in runbook
    assert "Do not run candidate authority from this proposal alone." in runbook

    sizing_section = runbook.split(
        "### Derive one evidence-only entry-sizing proposal from a valuation review",
        1,
    )[1].split(
        "### Produce one evidence-only entry-sizing proposal",
        1,
    )[0]
    assert 'TARGET_QUOTE_DECIMALS="9"' in sizing_section
    assert (
        'TARGET_QUOTE_DECIMALS="<reviewed-target-quote-decimals>"'
        not in sizing_section
    )
    assert 'EXPECTED_RELEASE_SHA="<exact-production-verified-release-sha>"' in sizing_section
    assert 'CURRENT_SHA="$(basename "$CURRENT_RELEASE")"' in sizing_section
    assert 'test "$CURRENT_SHA" = "$EXPECTED_RELEASE_SHA"' in sizing_section
    assert 'MANIFEST_SHA="$(' in sizing_section
    assert 'test "$MANIFEST_SHA" = "$EXPECTED_RELEASE_SHA"' in sizing_section
    assert 'test "$(readlink -f /opt/shreks/current)" = "$CURRENT_RELEASE"' in sizing_section
    assert 'sudo test ! -e "$PROPOSAL"' in sizing_section
