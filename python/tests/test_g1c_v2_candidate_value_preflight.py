from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.g1c_v2_candidate_value_preflight import (
    G1CV2CandidateValuePreflightError,
    decode_g1c_v2_candidate_value_preflight,
    preflight_g1c_v2_candidate_value,
)
from shreks_brain.g1c_v2_entry_sizing_proposal import (
    propose_g1c_v2_entry_sizing,
)
from shreks_brain.g1c_v2_review_backed_entry_sizing import (
    propose_g1c_v2_entry_sizing_from_review,
)
from shreks_brain.g1c_v2_runtime_manifest_candidate_authoring import (
    author_g1c_v2_runtime_manifest_candidate,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    encode_observer_paper_campaign_runtime_manifest,
)

from test_g1c_v2_review_backed_entry_sizing import _review
from test_g1c_v2_runtime_manifest_candidate_authority import _inputs
from test_observer_quote_asset_usd_evidence import AS_OF, WSOL


NEW_RUN_ID = "paper-v2-candidate-preflight-20260923"


def _review_backed_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (
        source,
        source_path,
        source_bytes,
        cohort_path,
        request_path,
        request,
    ) = _inputs(tmp_path, monkeypatch)
    review_path, review = _review(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    proposal = propose_g1c_v2_entry_sizing_from_review(
        source_runtime_manifest_path=source_path,
        review_path=review_path,
        target_quote_decimals=9,
        destination=proposal_path,
    )
    return (
        source,
        source_path,
        source_bytes,
        cohort_path,
        request_path,
        request,
        review,
        proposal_path,
        proposal,
    )


def test_preflight_proves_exact_proposed_candidate_compatible_without_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source,
        source_path,
        source_bytes,
        cohort_path,
        request_path,
        request,
        review,
        proposal_path,
        proposal,
    ) = _review_backed_inputs(tmp_path, monkeypatch)
    destination = tmp_path / "preflight.json"
    start_at = source.initial_state.last_cycle_at_unix_ms + 5_000

    receipt = preflight_g1c_v2_candidate_value(
        source_runtime_manifest_path=source_path,
        sizing_proposal_path=proposal_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=start_at,
        destination=destination,
    )

    expected_candidate = author_g1c_v2_runtime_manifest_candidate(
        source_runtime_manifest_path=source_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=start_at,
        quote_asset_mint=str(proposal["target_quote_mint"]),
        quote_asset_decimals=int(proposal["target_quote_decimals"]),
        entry_input_amount=int(proposal["proposed_entry_input_amount"]),
    )
    expected_payload = encode_observer_paper_campaign_runtime_manifest(
        expected_candidate
    )

    assert receipt["schema_name"] == "shreks.g1c_v2_candidate_value_preflight"
    assert receipt["schema_version"] == 1
    assert receipt["status"] == "READY_FOR_EXPLICIT_CANDIDATE_VALUE_DECISION"
    assert receipt["preflight_authority"] == "EVIDENCE_ONLY"
    assert receipt["candidate_compatibility"] == "COMPATIBLE"
    assert receipt["source_manifest_sha256"] == hashlib.sha256(
        source_bytes
    ).hexdigest()
    assert receipt["source_runtime_manifest_fingerprint_sha256"] == (
        source.manifest_fingerprint_sha256
    )
    assert receipt["source_paper_run_id"] == source.paper_run_id
    assert receipt["source_proposal_sha256"] == hashlib.sha256(
        proposal_path.read_bytes()
    ).hexdigest()
    assert receipt["proposal_fingerprint_sha256"] == (
        proposal["proposal_fingerprint_sha256"]
    )
    assert receipt["quote_evidence_authority"] == "MULTI_REFERENCE_REVIEW"
    assert receipt["quote_evidence_fingerprint_sha256"] == (
        review["review_fingerprint_sha256"]
    )
    assert receipt["candidate_paper_run_id"] == NEW_RUN_ID
    assert receipt["candidate_start_at_unix_ms"] == start_at
    assert receipt["target_quote_mint"] == proposal["target_quote_mint"]
    assert receipt["target_quote_decimals"] == proposal["target_quote_decimals"]
    assert receipt["proposed_entry_input_amount"] == (
        proposal["proposed_entry_input_amount"]
    )
    assert receipt["candidate_manifest_sha256"] == hashlib.sha256(
        expected_payload
    ).hexdigest()
    assert receipt["candidate_runtime_manifest_fingerprint_sha256"] == (
        expected_candidate.manifest_fingerprint_sha256
    )
    assert receipt["cohort_quote_mint"] == proposal["target_quote_mint"]
    assert receipt["request_fingerprint_sha256"] == (
        request.request_fingerprint_sha256
    )
    assert receipt["request_release_source_sha"] == (
        request.expected_release_source_sha
    )
    assert receipt["candidate_value_authority"] == "NOT_GRANTED"
    assert receipt["candidate_authoring_authority"] == "NOT_GRANTED"
    assert receipt["rotation_authority"] == "NOT_GRANTED"
    assert receipt["scoring_authority"] == "NOT_GRANTED"
    assert receipt["paper_promotion_authority"] == "BLOCKED"
    assert receipt["live_authority"] == "DISABLED"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert (
        decode_g1c_v2_candidate_value_preflight(
            destination.read_text(encoding="utf-8")
        )
        == receipt
    )


def test_preflight_rejects_non_review_backed_sizing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source,
        source_path,
        _source_bytes,
        cohort_path,
        request_path,
        _request,
    ) = _inputs(tmp_path, monkeypatch)
    proposal_path = tmp_path / "proposal.json"
    propose_g1c_v2_entry_sizing(
        source_runtime_manifest_path=source_path,
        target_quote_mint=WSOL,
        target_quote_decimals=9,
        target_quote_usd_per_token="125",
        quote_evidence_fingerprint_sha256="a" * 64,
        quote_evidence_observed_at_unix_ms=AS_OF,
        destination=proposal_path,
    )

    with pytest.raises(
        G1CV2CandidateValuePreflightError,
        match="MULTI_REFERENCE_REVIEW|review",
    ):
        preflight_g1c_v2_candidate_value(
            source_runtime_manifest_path=source_path,
            sizing_proposal_path=proposal_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            paper_run_id=NEW_RUN_ID,
            start_at_unix_ms=source.initial_state.last_cycle_at_unix_ms + 5_000,
            destination=tmp_path / "preflight.json",
        )


def test_preflight_rejects_tampered_proposal_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source,
        source_path,
        _source_bytes,
        cohort_path,
        request_path,
        _request,
        _review_document,
        proposal_path,
        _proposal,
    ) = _review_backed_inputs(tmp_path, monkeypatch)
    document = json.loads(proposal_path.read_text(encoding="utf-8"))
    document["proposed_entry_input_amount"] += 1
    proposal_path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    destination = tmp_path / "preflight.json"

    with pytest.raises(
        G1CV2CandidateValuePreflightError,
        match="proposal|fingerprint",
    ):
        preflight_g1c_v2_candidate_value(
            source_runtime_manifest_path=source_path,
            sizing_proposal_path=proposal_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            paper_run_id=NEW_RUN_ID,
            start_at_unix_ms=source.initial_state.last_cycle_at_unix_ms + 5_000,
            destination=destination,
        )

    assert not destination.exists()


def test_preflight_decoder_rejects_authority_escalation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source,
        source_path,
        _source_bytes,
        cohort_path,
        request_path,
        _request,
        _review_document,
        proposal_path,
        _proposal,
    ) = _review_backed_inputs(tmp_path, monkeypatch)
    destination = tmp_path / "preflight.json"
    receipt = preflight_g1c_v2_candidate_value(
        source_runtime_manifest_path=source_path,
        sizing_proposal_path=proposal_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=source.initial_state.last_cycle_at_unix_ms + 5_000,
        destination=destination,
    )

    tampered = dict(receipt)
    tampered["candidate_value_authority"] = "GRANTED"
    payload = (
        json.dumps(
            tampered,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )

    with pytest.raises(
        G1CV2CandidateValuePreflightError,
        match="candidate_value_authority|fingerprint|authority",
    ):
        decode_g1c_v2_candidate_value_preflight(payload)


def test_preflight_cli_is_registered_and_has_no_downstream_runtime_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "shreks_brain" / "g1c_v2_candidate_value_preflight.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-candidate-value-preflight = '
        '"shreks_brain.g1c_v2_candidate_value_preflight:main"'
        in pyproject
    )

    for forbidden in (
        "sqlite3",
        "ObserverMarketStore",
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "systemctl",
        "subprocess",
        "decide_g1c_v2_candidate_value",
        "bind_g1c_v2_runtime_manifest_candidate_authority",
        "bind_g1c_v2_decision_backed_candidate_authority",
        "author_g1c_v2_candidate_from_decision_backed_authority",
        "bind_g1c_v2_decision_backed_transition",
        "rotation_readiness",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
