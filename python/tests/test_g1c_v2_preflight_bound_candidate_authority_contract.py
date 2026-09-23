from __future__ import annotations

from pathlib import Path


def test_decision_backed_candidate_authority_is_preflight_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_decision_backed_candidate_authority.py"
    ).read_text(encoding="utf-8")

    assert (
        "decode_g1c_v2_candidate_value_preflight"
        in source
    )
    assert "candidate_value_preflight_path" in source
    assert "--candidate-value-preflight" in source
    assert "--paper-run-id" not in source
    assert "--start-at-unix-ms" not in source

    assert (
        '"candidate_value_preflight_fingerprint_sha256"'
        in source
    )
    assert '"candidate_compatibility"' in source
    assert '"preflight_authority"' in source
    assert '"source_proposal_sha256"' in source
    assert '"proposal_fingerprint_sha256"' in source

    assert '_ALLOWED_DECISIONS = {"ACCEPT_PROPOSAL"}' in source
    assert "preflighted candidate manifest SHA" in source
    assert "preflighted candidate fingerprint" in source
    assert "preflighted candidate run id" in source
    assert "preflighted candidate start time" in source
