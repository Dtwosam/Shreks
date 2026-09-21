from __future__ import annotations

from pathlib import Path


def test_g1c_v2_candidate_economics_tools_have_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    entry_script = "shreks-g1c-v2-entry-sizing-proposal"
    reference_script = "shreks-g1c-v2-quote-valuation-reference"

    assert (
        f'ENTRY_SIZING="/opt/shreks/current/.venv/bin/{entry_script}"'
        in workflow
    )
    assert 'test -f "$ENTRY_SIZING"' in workflow
    assert 'test ! -L "$ENTRY_SIZING"' in workflow
    assert 'test -x "$ENTRY_SIZING"' in workflow
    assert 'ENTRY_SIZING_RESOLVED="$(readlink -f "$ENTRY_SIZING")"' in workflow
    assert (
        f'test "$ENTRY_SIZING_RESOLVED" = "$EXPECTED/.venv/bin/{entry_script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_entry_sizing_proposal as entry_sizing"
        in workflow
    )
    assert "entry sizing proposal module is outside the exact deployed release" in workflow
    assert "g1c_v2_entry_sizing_proposal=present" in workflow
    assert "g1c_v2_entry_sizing_proposal_path=%s" in workflow
    assert "g1c_v2_entry_sizing_proposal_module=%s" in workflow

    assert (
        f'QUOTE_REFERENCE="/opt/shreks/current/.venv/bin/{reference_script}"'
        in workflow
    )
    assert 'test -f "$QUOTE_REFERENCE"' in workflow
    assert 'test ! -L "$QUOTE_REFERENCE"' in workflow
    assert 'test -x "$QUOTE_REFERENCE"' in workflow
    assert (
        'QUOTE_REFERENCE_RESOLVED="$(readlink -f "$QUOTE_REFERENCE")"'
        in workflow
    )
    assert (
        f'test "$QUOTE_REFERENCE_RESOLVED" = "$EXPECTED/.venv/bin/{reference_script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_quote_valuation_reference as quote_reference"
        in workflow
    )
    assert "quote valuation reference module is outside the exact deployed release" in workflow
    assert "g1c_v2_quote_valuation_reference=present" in workflow
    assert "g1c_v2_quote_valuation_reference_path=%s" in workflow
    assert "g1c_v2_quote_valuation_reference_module=%s" in workflow

    assert 'exec "$ENTRY_SIZING"' not in workflow
    assert 'exec "$QUOTE_REFERENCE"' not in workflow
    assert "entry_sizing.main(" not in workflow
    assert "quote_reference.main(" not in workflow

    assert "## Capture G1C v2 valuation and sizing evidence" in runbook
    assert reference_script in runbook
    assert entry_script in runbook
    assert "REFERENCE_EVIDENCE_ONLY" in runbook
    assert "PROPOSAL_EVIDENCE_ONLY" in runbook
    assert "does not authorize production candidate values" in runbook
    assert "Do not run candidate authority from this evidence alone." in runbook
