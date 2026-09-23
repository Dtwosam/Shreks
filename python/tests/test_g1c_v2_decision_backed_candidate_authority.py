from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fl9_v2_runtime_manifest_discovery as discovery
import shreks_brain.g1c_v2_decision_backed_candidate_authority as authority_module

from shreks_brain.g1c_v2_candidate_value_decision import (
    decide_g1c_v2_candidate_value,
)
from shreks_brain.g1c_v2_candidate_value_preflight import (
    preflight_g1c_v2_candidate_value,
)
from shreks_brain.g1c_v2_decision_backed_candidate_authority import (
    G1CV2DecisionBackedCandidateAuthorityError,
    bind_g1c_v2_decision_backed_candidate_authority,
    decode_g1c_v2_decision_backed_candidate_authority,
)
from shreks_brain.g1c_v2_review_backed_entry_sizing import (
    propose_g1c_v2_entry_sizing_from_review,
)

from test_g1c_v2_review_backed_entry_sizing import _review
from test_observer_quote_asset_usd_evidence import WSOL
from test_g1c_v2_runtime_manifest_candidate_authority import (
    NEW_RUN_ID,
    _inputs,
)


def _approved_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, tuple[object, ...]]:
    inputs = _inputs(tmp_path, monkeypatch)
    (
        source,
        source_path,
        _source_bytes,
        cohort_path,
        request_path,
        _request,
    ) = inputs

    # The reusable candidate-authority fixture freezes a synthetic "quote-sol"
    # cohort. This bridge test must exercise the real review-backed WSOL
    # provenance while preserving the same authenticated request fingerprint.
    frozen = discovery.read_fl9_v2_cohort_acceptance(cohort_path)
    accepted = tuple(
        replace(
            item,
            decision_identity=(
                *item.decision_identity[:4],
                WSOL,
                *item.decision_identity[5:],
            ),
        )
        for item in frozen.accepted_decisions
    )
    ws_sol_frozen = SimpleNamespace(
        path=frozen.path,
        manifest=frozen.manifest,
        accepted_decisions=accepted,
        quarantined_decisions=frozen.quarantined_decisions,
    )
    monkeypatch.setattr(
        discovery,
        "read_fl9_v2_cohort_acceptance",
        lambda _path: ws_sol_frozen,
    )

    review_path, _review_document = _review(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    propose_g1c_v2_entry_sizing_from_review(
        source_runtime_manifest_path=source_path,
        review_path=review_path,
        target_quote_decimals=9,
        destination=proposal_path,
    )

    preflight_path = tmp_path / "preflight.json"
    preflight_g1c_v2_candidate_value(
        source_runtime_manifest_path=source_path,
        sizing_proposal_path=proposal_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=source.initial_state.last_cycle_at_unix_ms + 1_000,
        destination=preflight_path,
    )

    decision_path = tmp_path / "decision.json"
    decide_g1c_v2_candidate_value(
        sizing_proposal_path=proposal_path,
        decision="ACCEPT_PROPOSAL",
        decision_reason="Reviewed production economics accepted.",
        replacement_entry_input_amount=None,
        destination=decision_path,
    )
    return preflight_path, decision_path, inputs


def test_decision_backed_authority_binds_approved_values_to_exact_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight_path, decision_path, inputs = _approved_decision(tmp_path, monkeypatch)
    source, source_path, _source_bytes, cohort_path, request_path, _request = inputs
    destination = tmp_path / "decision-backed-authority.json"

    authority = bind_g1c_v2_decision_backed_candidate_authority(
        source_runtime_manifest_path=source_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        candidate_value_preflight_path=preflight_path,
        candidate_value_decision_path=decision_path,
        destination=destination,
    )

    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert authority["schema_name"] == (
        "shreks.g1c_v2_decision_backed_candidate_authority"
    )
    assert authority["schema_version"] == 2
    assert authority["authority_status"] == "BOUND_EXACT_CANONICAL_CANDIDATE"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert authority["candidate_value_preflight_fingerprint_sha256"] == (
        preflight["preflight_fingerprint_sha256"]
    )
    assert authority["candidate_compatibility"] == "COMPATIBLE"
    assert authority["preflight_authority"] == "EVIDENCE_ONLY"
    assert authority["candidate_value_decision_fingerprint_sha256"] == (
        decision["decision_fingerprint_sha256"]
    )
    assert authority["candidate_value_authority"] == (
        "EXPLICIT_PRODUCTION_DECISION_BOUND"
    )
    assert authority["candidate_quote_asset_mint"] == decision["target_quote_mint"]
    assert authority["candidate_quote_asset_decimals"] == (
        decision["target_quote_decimals"]
    )
    assert authority["candidate_entry_input_amount"] == (
        decision["selected_entry_input_amount"]
    )
    assert authority["candidate_authoring_authority"] == (
        "DECISION_BACKED_INPUTS_BOUND"
    )
    assert authority["installation_authority"] == "NOT_GRANTED"
    assert authority["activation_authority"] == "NOT_GRANTED"
    assert authority["rotation_authority"] == "NOT_GRANTED"
    assert authority["scoring_authority"] == "NOT_GRANTED"
    assert authority["paper_promotion_authority"] == "BLOCKED"
    assert authority["live_authority"] == "DISABLED"
    assert len(authority["derived_candidate_authority_fingerprint_sha256"]) == 64
    assert decode_g1c_v2_decision_backed_candidate_authority(
        destination.read_text(encoding="utf-8")
    ) == authority
    assert oct(destination.stat().st_mode & 0o777) == "0o600"


def test_decision_backed_authority_rejects_request_change_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight_path, decision_path, inputs = _approved_decision(
        tmp_path, monkeypatch
    )
    source, source_path, _source_bytes, cohort_path, request_path, _request = inputs
    destination = tmp_path / "authority.json"
    real_bind = authority_module.bind_g1c_v2_runtime_manifest_candidate_authority

    def bind_then_mutate_authority(**kwargs: object) -> dict[str, object]:
        derived = real_bind(**kwargs)
        request_path.write_text(
            request_path.read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )
        return derived

    monkeypatch.setattr(
        authority_module,
        "bind_g1c_v2_runtime_manifest_candidate_authority",
        bind_then_mutate_authority,
    )

    with pytest.raises(
        G1CV2DecisionBackedCandidateAuthorityError,
        match="authority changed while decision-backed authority was derived|authority authentication failed",
    ):
        bind_g1c_v2_decision_backed_candidate_authority(
            source_runtime_manifest_path=source_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            candidate_value_preflight_path=preflight_path,
            candidate_value_decision_path=decision_path,
            destination=destination,
        )

    assert not destination.exists()


def test_rejected_decision_cannot_grant_candidate_authoring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight_path, decision_path, inputs = _approved_decision(tmp_path, monkeypatch)
    source, source_path, _source_bytes, cohort_path, request_path, _request = inputs
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["status"] = "CANDIDATE_VALUE_REJECTED"
    decision["decision"] = "REJECT_PROPOSAL"
    decision["selected_entry_input_amount"] = None
    decision["candidate_value_authority"] = "NOT_GRANTED"
    decision_path.write_text(
        json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        G1CV2DecisionBackedCandidateAuthorityError,
        match="decision|fingerprint|approved",
    ):
        bind_g1c_v2_decision_backed_candidate_authority(
            source_runtime_manifest_path=source_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            candidate_value_preflight_path=preflight_path,
            candidate_value_decision_path=decision_path,
            destination=tmp_path / "authority.json",
        )


def test_decision_backed_authority_rejects_different_source_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight_path, decision_path, inputs = _approved_decision(tmp_path, monkeypatch)
    source, _source_path, _source_bytes, cohort_path, request_path, _request = inputs
    wrong_source = tmp_path / "wrong-source.json"
    wrong_source.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        G1CV2DecisionBackedCandidateAuthorityError,
        match="source|manifest|authentication",
    ):
        bind_g1c_v2_decision_backed_candidate_authority(
            source_runtime_manifest_path=wrong_source,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            candidate_value_preflight_path=preflight_path,
            candidate_value_decision_path=decision_path,
            destination=tmp_path / "authority.json",
        )




def test_replaced_decision_is_rejected_without_compatible_replacement_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight_path, decision_path, inputs = _approved_decision(
        tmp_path, monkeypatch
    )
    source, source_path, _source_bytes, cohort_path, request_path, _request = inputs
    approved = json.loads(decision_path.read_text(encoding="utf-8"))
    replacement_path = tmp_path / "replacement-decision.json"
    decide_g1c_v2_candidate_value(
        sizing_proposal_path=tmp_path / "proposal.json",
        decision="REPLACE_PROPOSAL",
        decision_reason="Replacement must be preflighted separately.",
        replacement_entry_input_amount=(
            int(approved["selected_entry_input_amount"]) + 1
        ),
        destination=replacement_path,
    )

    with pytest.raises(
        G1CV2DecisionBackedCandidateAuthorityError,
        match="accept|preflight|decision",
    ):
        bind_g1c_v2_decision_backed_candidate_authority(
            source_runtime_manifest_path=source_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            candidate_value_preflight_path=preflight_path,
            candidate_value_decision_path=replacement_path,
            destination=tmp_path / "replacement-authority.json",
        )


def test_decision_backed_authority_cli_has_no_raw_candidate_value_inputs() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_decision_backed_candidate_authority.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-decision-backed-candidate-authority-bind = '
        '"shreks_brain.g1c_v2_decision_backed_candidate_authority:main"'
        in pyproject
    )
    assert "--candidate-value-preflight" in source
    assert "--candidate-value-decision" in source
    assert "--paper-run-id" not in source
    assert "--start-at-unix-ms" not in source
    assert "--quote-asset-mint" not in source
    assert "--quote-asset-decimals" not in source
    assert "--entry-input-amount" not in source

    for forbidden in (
        "sqlite3",
        "ObserverMarketStore",
        "systemctl",
        "subprocess",
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
