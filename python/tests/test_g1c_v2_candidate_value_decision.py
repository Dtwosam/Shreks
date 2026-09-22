from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.g1c_v2_candidate_value_decision import (
    G1CV2CandidateValueDecisionError,
    decide_g1c_v2_candidate_value,
    decode_g1c_v2_candidate_value_decision,
)
from shreks_brain.g1c_v2_entry_sizing_proposal import (
    propose_g1c_v2_entry_sizing,
)
from shreks_brain.g1c_v2_review_backed_entry_sizing import (
    propose_g1c_v2_entry_sizing_from_review,
)

from test_g1c_v2_review_backed_entry_sizing import _review, _source
from test_observer_quote_asset_usd_evidence import AS_OF, WSOL


def _review_backed_proposal(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    source = _source(tmp_path)
    review_path, _ = _review(tmp_path)
    path = tmp_path / "proposal.json"
    proposal = propose_g1c_v2_entry_sizing_from_review(
        source_runtime_manifest_path=source,
        review_path=review_path,
        target_quote_decimals=9,
        destination=path,
    )
    return path, proposal


def test_accept_review_backed_proposal_grants_only_candidate_value_authority(
    tmp_path: Path,
) -> None:
    proposal_path, proposal = _review_backed_proposal(tmp_path)
    destination = tmp_path / "decision.json"

    decision = decide_g1c_v2_candidate_value(
        sizing_proposal_path=proposal_path,
        decision="ACCEPT_PROPOSAL",
        decision_reason="Reviewed multi-reference sizing is accepted.",
        replacement_entry_input_amount=None,
        destination=destination,
    )

    assert decision["schema_name"] == "shreks.g1c_v2_candidate_value_decision"
    assert decision["status"] == "CANDIDATE_VALUE_APPROVED"
    assert decision["decision"] == "ACCEPT_PROPOSAL"
    assert decision["proposal_fingerprint_sha256"] == (
        proposal["proposal_fingerprint_sha256"]
    )
    assert decision["quote_evidence_authority"] == "MULTI_REFERENCE_REVIEW"
    assert decision["selected_entry_input_amount"] == (
        proposal["proposed_entry_input_amount"]
    )
    assert (
        decision["candidate_value_authority"]
        == "EXPLICIT_PRODUCTION_DECISION_BOUND"
    )
    assert decision["candidate_authoring_authority"] == "NOT_GRANTED"
    assert decision["rotation_authority"] == "NOT_GRANTED"
    assert decision["scoring_authority"] == "NOT_GRANTED"
    assert decision["paper_promotion_authority"] == "BLOCKED"
    assert decision["live_authority"] == "DISABLED"
    assert decode_g1c_v2_candidate_value_decision(
        destination.read_text(encoding="utf-8")
    ) == decision


def test_replace_review_backed_proposal_binds_explicit_replacement(
    tmp_path: Path,
) -> None:
    proposal_path, proposal = _review_backed_proposal(tmp_path)
    replacement = int(proposal["proposed_entry_input_amount"]) + 1

    decision = decide_g1c_v2_candidate_value(
        sizing_proposal_path=proposal_path,
        decision="REPLACE_PROPOSAL",
        decision_reason="Reviewed replacement amount is explicitly selected.",
        replacement_entry_input_amount=replacement,
        destination=tmp_path / "decision.json",
    )

    assert decision["status"] == "CANDIDATE_VALUE_APPROVED"
    assert decision["selected_entry_input_amount"] == replacement
    assert (
        decision["candidate_value_authority"]
        == "EXPLICIT_PRODUCTION_DECISION_BOUND"
    )
    assert decision["candidate_authoring_authority"] == "NOT_GRANTED"


def test_reject_review_backed_proposal_grants_no_candidate_value_authority(
    tmp_path: Path,
) -> None:
    proposal_path, _ = _review_backed_proposal(tmp_path)

    decision = decide_g1c_v2_candidate_value(
        sizing_proposal_path=proposal_path,
        decision="REJECT_PROPOSAL",
        decision_reason="Proposal is explicitly rejected.",
        replacement_entry_input_amount=None,
        destination=tmp_path / "decision.json",
    )

    assert decision["status"] == "CANDIDATE_VALUE_REJECTED"
    assert decision["selected_entry_input_amount"] is None
    assert decision["candidate_value_authority"] == "NOT_GRANTED"
    assert decision["candidate_authoring_authority"] == "NOT_GRANTED"


def test_explicit_reference_only_proposal_is_rejected(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    propose_g1c_v2_entry_sizing(
        source_runtime_manifest_path=source,
        target_quote_mint=WSOL,
        target_quote_decimals=9,
        target_quote_usd_per_token="125",
        quote_evidence_fingerprint_sha256="a" * 64,
        quote_evidence_observed_at_unix_ms=AS_OF,
        destination=proposal_path,
    )

    with pytest.raises(
        G1CV2CandidateValueDecisionError,
        match="MULTI_REFERENCE_REVIEW|review",
    ):
        decide_g1c_v2_candidate_value(
            sizing_proposal_path=proposal_path,
            decision="ACCEPT_PROPOSAL",
            decision_reason="Not sufficient.",
            replacement_entry_input_amount=None,
            destination=tmp_path / "decision.json",
        )


def test_tampered_proposal_is_rejected(tmp_path: Path) -> None:
    proposal_path, _ = _review_backed_proposal(tmp_path)
    document = json.loads(proposal_path.read_text(encoding="utf-8"))
    document["proposed_entry_input_amount"] += 1
    proposal_path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        G1CV2CandidateValueDecisionError,
        match="proposal|fingerprint",
    ):
        decide_g1c_v2_candidate_value(
            sizing_proposal_path=proposal_path,
            decision="ACCEPT_PROPOSAL",
            decision_reason="Should fail.",
            replacement_entry_input_amount=None,
            destination=tmp_path / "decision.json",
        )


@pytest.mark.parametrize(
    ("decision", "replacement"),
    [
        ("ACCEPT_PROPOSAL", 1),
        ("REJECT_PROPOSAL", 1),
        ("REPLACE_PROPOSAL", None),
    ],
)
def test_decision_replacement_contract_is_strict(
    tmp_path: Path,
    decision: str,
    replacement: int | None,
) -> None:
    proposal_path, _ = _review_backed_proposal(tmp_path)
    with pytest.raises(G1CV2CandidateValueDecisionError):
        decide_g1c_v2_candidate_value(
            sizing_proposal_path=proposal_path,
            decision=decision,
            decision_reason="Strict contract.",
            replacement_entry_input_amount=replacement,
            destination=tmp_path / "decision.json",
        )


def test_replace_requires_amount_different_from_proposal(tmp_path: Path) -> None:
    proposal_path, proposal = _review_backed_proposal(tmp_path)
    with pytest.raises(
        G1CV2CandidateValueDecisionError,
        match="differ",
    ):
        decide_g1c_v2_candidate_value(
            sizing_proposal_path=proposal_path,
            decision="REPLACE_PROPOSAL",
            decision_reason="No-op replacement is forbidden.",
            replacement_entry_input_amount=int(
                proposal["proposed_entry_input_amount"]
            ),
            destination=tmp_path / "decision.json",
        )


def test_candidate_value_decision_cli_has_no_downstream_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "shreks_brain" / "g1c_v2_candidate_value_decision.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-candidate-value-decision = '
        '"shreks_brain.g1c_v2_candidate_value_decision:main"'
        in pyproject
    )
    for forbidden in (
        "sqlite3",
        "ObserverMarketStore",
        "systemctl",
        "subprocess",
        "bind_g1c_v2_runtime_manifest_candidate_authority",
        "author_g1c_v2_runtime_manifest_candidate",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
