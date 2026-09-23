from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from shreks_brain.g1c_v2_decision_backed_candidate_authority import (
    bind_g1c_v2_decision_backed_candidate_authority,
)
from shreks_brain.g1c_v2_decision_backed_candidate_authoring import (
    G1CV2DecisionBackedCandidateAuthoringError,
    author_g1c_v2_candidate_from_decision_backed_authority,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    decode_observer_paper_campaign_runtime_manifest,
)

from test_g1c_v2_decision_backed_candidate_authority import _approved_decision


def _authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, object]]:
    preflight_path, decision_path, inputs = _approved_decision(tmp_path, monkeypatch)
    source, source_path, _source_bytes, cohort_path, request_path, _request = inputs
    authority_path = tmp_path / "decision-backed-authority.json"
    authority = bind_g1c_v2_decision_backed_candidate_authority(
        source_runtime_manifest_path=source_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        candidate_value_preflight_path=preflight_path,
        candidate_value_decision_path=decision_path,
        destination=authority_path,
    )
    return source_path, authority_path, authority


def test_authoring_writes_exact_candidate_committed_by_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path, authority_path, authority = _authority(tmp_path, monkeypatch)
    source_before = source_path.read_bytes()
    authority_before = authority_path.read_bytes()
    destination = tmp_path / "candidate.json"

    candidate = author_g1c_v2_candidate_from_decision_backed_authority(
        source_runtime_manifest_path=source_path,
        decision_backed_candidate_authority_path=authority_path,
        destination=destination,
    )

    payload = destination.read_bytes()
    decoded = decode_observer_paper_campaign_runtime_manifest(payload)

    assert decoded == candidate
    assert hashlib.sha256(payload).hexdigest() == authority["candidate_manifest_sha256"]
    assert (
        candidate.manifest_fingerprint_sha256
        == authority["candidate_runtime_manifest_fingerprint_sha256"]
    )
    assert candidate.paper_run_id == authority["candidate_paper_run_id"]
    assert (
        candidate.initial_state.last_cycle_at_unix_ms
        == authority["candidate_start_at_unix_ms"]
    )
    assert (
        candidate.policy_bundle.quote_asset.mint
        == authority["candidate_quote_asset_mint"]
    )
    assert (
        candidate.policy_bundle.quote_asset.decimals
        == authority["candidate_quote_asset_decimals"]
    )
    assert (
        candidate.policy_bundle.entry_quote_identity.input_amount
        == authority["candidate_entry_input_amount"]
    )
    assert source_path.read_bytes() == source_before
    assert authority_path.read_bytes() == authority_before
    assert oct(destination.stat().st_mode & 0o777) == "0o600"


def test_authoring_rejects_tampered_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path, authority_path, _authority_document = _authority(
        tmp_path, monkeypatch
    )
    document = json.loads(authority_path.read_text(encoding="utf-8"))
    document["candidate_entry_input_amount"] += 1
    authority_path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        G1CV2DecisionBackedCandidateAuthoringError,
        match="authority|fingerprint|authentication",
    ):
        author_g1c_v2_candidate_from_decision_backed_authority(
            source_runtime_manifest_path=source_path,
            decision_backed_candidate_authority_path=authority_path,
            destination=tmp_path / "candidate.json",
        )


def test_authoring_rejects_source_not_bound_by_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_path, authority_path, _authority_document = _authority(
        tmp_path, monkeypatch
    )
    wrong_source = tmp_path / "wrong-source.json"
    wrong_source.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        G1CV2DecisionBackedCandidateAuthoringError,
        match="source|manifest|authentication",
    ):
        author_g1c_v2_candidate_from_decision_backed_authority(
            source_runtime_manifest_path=wrong_source,
            decision_backed_candidate_authority_path=authority_path,
            destination=tmp_path / "candidate.json",
        )


def test_authoring_is_write_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path, authority_path, _authority_document = _authority(
        tmp_path, monkeypatch
    )
    destination = tmp_path / "candidate.json"
    destination.write_text("occupied\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        author_g1c_v2_candidate_from_decision_backed_authority(
            source_runtime_manifest_path=source_path,
            decision_backed_candidate_authority_path=authority_path,
            destination=destination,
        )


def test_decision_backed_authoring_cli_exposes_no_raw_candidate_inputs() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_decision_backed_candidate_authoring.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-decision-backed-candidate-author = '
        '"shreks_brain.g1c_v2_decision_backed_candidate_authoring:main"'
        in pyproject
    )
    assert "--source-runtime-manifest" in source
    assert "--decision-backed-candidate-authority" in source
    assert "--destination" in source

    for forbidden_argument in (
        "--paper-run-id",
        "--start-at-unix-ms",
        "--quote-asset-mint",
        "--quote-asset-decimals",
        "--entry-input-amount",
        "--cohort",
        "--v2-host-request-authority",
        "--candidate-value-decision",
    ):
        assert forbidden_argument not in source

    for forbidden_runtime_surface in (
        "sqlite3",
        "ObserverMarketStore",
        "systemctl",
        "subprocess",
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "transition_binding",
        "rotation_readiness",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden_runtime_surface not in source
