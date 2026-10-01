from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

import shreks_brain.fl9_v2_discovery_backed_request_preparation as preparation
import shreks_brain.fl9_v2_scoring_authority as scoring_authority


SOURCE_SHA = "1" * 40
COHORT_FP = "2" * 64
HYDRATION_FP = "3" * 64
RUNTIME_FP = "4" * 64
DISCOVERY_BINDING_FP = "5" * 64
REQUEST_FP = "6" * 64
WSOL = "So11111111111111111111111111111111111111112"


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _write_preparation(
    tmp_path: Path,
    *,
    request_path: Path,
    request_payload: bytes,
    evidence_destination: Path,
    scoring_authority_value: str = "NOT_GRANTED",
) -> Path:
    material: dict[str, object] = {
        "schema_name": "shreks.fl9_v2_discovery_backed_request_preparation",
        "schema_version": 1,
        "discovery_binding_sha256": "7" * 64,
        "discovery_binding_fingerprint_sha256": DISCOVERY_BINDING_FP,
        "discovery_result_sha256": "8" * 64,
        "release_source_sha": SOURCE_SHA,
        "cohort_artifact_fingerprint_sha256": COHORT_FP,
        "hydration_policy_fingerprint_sha256": HYDRATION_FP,
        "runtime_manifest_source_kind": "active",
        "runtime_manifest_source_path": "/etc/shreks/paper-campaign.json",
        "runtime_manifest_fingerprint_sha256": RUNTIME_FP,
        "quote_asset_mint": WSOL,
        "quote_asset_decimals": 9,
        "quote_provider": "jupiter",
        "request_sha256": hashlib.sha256(request_payload).hexdigest(),
        "request_fingerprint_sha256": REQUEST_FP,
        "request_path": str(request_path),
        "evidence_destination": str(evidence_destination),
        "request_preparation_authority": "DISCOVERY_BOUND_REQUEST_ONLY",
        "scoring_authority": scoring_authority_value,
        "champion_publication_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    document = {
        **material,
        "preparation_fingerprint_sha256": preparation._sha256_canonical(material),
    }
    path = tmp_path / "preparation.json"
    path.write_text(_canonical(document), encoding="utf-8")
    return path


def _request_identity(evidence_destination: Path) -> SimpleNamespace:
    return SimpleNamespace(
        request_fingerprint_sha256=REQUEST_FP,
        expected_release_source_sha=SOURCE_SHA,
        expected_cohort_artifact_fingerprint_sha256=COHORT_FP,
        expected_hydration_policy_fingerprint_sha256=HYDRATION_FP,
        destination_path=str(evidence_destination),
    )


def test_authorize_one_scoring_run_writes_exact_bound_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / "request.json"
    request_payload = b'{"request":"exact"}\n'
    request_path.write_bytes(request_payload)
    evidence_destination = tmp_path / "evidence"
    preparation_path = _write_preparation(
        tmp_path,
        request_path=request_path,
        request_payload=request_payload,
        evidence_destination=evidence_destination,
    )
    monkeypatch.setattr(
        scoring_authority,
        "decode_fast_first_champion_v2_host_request",
        lambda _payload: _request_identity(evidence_destination),
    )

    destination = tmp_path / "scoring-authority.json"
    result = scoring_authority.decide_fl9_v2_scoring_authority(
        request_preparation_path=preparation_path,
        decision="AUTHORIZE_ONE_SCORING_RUN",
        decision_reason="reviewed exact discovery-backed evidence request",
        destination=destination,
    )

    assert result["status"] == "SCORING_AUTHORIZED"
    assert result["decision"] == "AUTHORIZE_ONE_SCORING_RUN"
    assert result["source_preparation_sha256"] == hashlib.sha256(
        preparation_path.read_bytes()
    ).hexdigest()
    assert result["request_sha256"] == hashlib.sha256(request_payload).hexdigest()
    assert result["request_fingerprint_sha256"] == REQUEST_FP
    assert result["release_source_sha"] == SOURCE_SHA
    assert result["cohort_artifact_fingerprint_sha256"] == COHORT_FP
    assert result["hydration_policy_fingerprint_sha256"] == HYDRATION_FP
    assert result["runtime_manifest_fingerprint_sha256"] == RUNTIME_FP
    assert result["evidence_destination"] == str(evidence_destination)
    assert result["scoring_authority"] == "EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN"
    assert result["model_fitting_authority"] == "EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN"
    assert result["champion_publication_authority"] == "SCORING_EVIDENCE_ONLY"
    assert result["paper_promotion_authority"] == "BLOCKED"
    assert result["live_authority"] == "DISABLED"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert scoring_authority.decode_fl9_v2_scoring_authority(
        destination.read_text(encoding="utf-8")
    ) == result


def test_reject_scoring_run_grants_no_scoring_or_publication_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / "request.json"
    request_payload = b'{"request":"exact"}\n'
    request_path.write_bytes(request_payload)
    evidence_destination = tmp_path / "evidence"
    preparation_path = _write_preparation(
        tmp_path,
        request_path=request_path,
        request_payload=request_payload,
        evidence_destination=evidence_destination,
    )
    monkeypatch.setattr(
        scoring_authority,
        "decode_fast_first_champion_v2_host_request",
        lambda _payload: _request_identity(evidence_destination),
    )

    result = scoring_authority.decide_fl9_v2_scoring_authority(
        request_preparation_path=preparation_path,
        decision="REJECT_SCORING_RUN",
        decision_reason="review rejected this evidence attempt",
        destination=tmp_path / "rejected.json",
    )

    assert result["status"] == "SCORING_REJECTED"
    assert result["scoring_authority"] == "NOT_GRANTED"
    assert result["model_fitting_authority"] == "NOT_GRANTED"
    assert result["champion_publication_authority"] == "NOT_GRANTED"
    assert result["paper_promotion_authority"] == "BLOCKED"
    assert result["live_authority"] == "DISABLED"


def test_request_bytes_must_match_preparation_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / "request.json"
    original = b'{"request":"exact"}\n'
    request_path.write_bytes(original)
    evidence_destination = tmp_path / "evidence"
    preparation_path = _write_preparation(
        tmp_path,
        request_path=request_path,
        request_payload=original,
        evidence_destination=evidence_destination,
    )
    request_path.write_bytes(b'{"request":"changed"}\n')
    monkeypatch.setattr(
        scoring_authority,
        "decode_fast_first_champion_v2_host_request",
        lambda _payload: _request_identity(evidence_destination),
    )

    with pytest.raises(
        scoring_authority.FL9V2ScoringAuthorityError,
        match="request SHA-256",
    ):
        scoring_authority.decide_fl9_v2_scoring_authority(
            request_preparation_path=preparation_path,
            decision="AUTHORIZE_ONE_SCORING_RUN",
            decision_reason="must fail",
            destination=tmp_path / "authority.json",
        )
    assert not (tmp_path / "authority.json").exists()


def test_preparation_must_still_have_no_scoring_authority(
    tmp_path: Path,
) -> None:
    request_path = tmp_path / "request.json"
    request_payload = b'{"request":"exact"}\n'
    request_path.write_bytes(request_payload)
    preparation_path = _write_preparation(
        tmp_path,
        request_path=request_path,
        request_payload=request_payload,
        evidence_destination=tmp_path / "evidence",
        scoring_authority_value="ALREADY_GRANTED",
    )

    with pytest.raises(
        scoring_authority.FL9V2ScoringAuthorityError,
        match="preparation receipt authentication failed",
    ):
        scoring_authority.decide_fl9_v2_scoring_authority(
            request_preparation_path=preparation_path,
            decision="AUTHORIZE_ONE_SCORING_RUN",
            decision_reason="must fail",
            destination=tmp_path / "authority.json",
        )


def test_authority_writer_never_overwrites_existing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / "request.json"
    request_payload = b'{"request":"exact"}\n'
    request_path.write_bytes(request_payload)
    evidence_destination = tmp_path / "evidence"
    preparation_path = _write_preparation(
        tmp_path,
        request_path=request_path,
        request_payload=request_payload,
        evidence_destination=evidence_destination,
    )
    monkeypatch.setattr(
        scoring_authority,
        "decode_fast_first_champion_v2_host_request",
        lambda _payload: _request_identity(evidence_destination),
    )
    destination = tmp_path / "authority.json"

    scoring_authority.decide_fl9_v2_scoring_authority(
        request_preparation_path=preparation_path,
        decision="REJECT_SCORING_RUN",
        decision_reason="first immutable decision",
        destination=destination,
    )
    with pytest.raises(FileExistsError):
        scoring_authority.decide_fl9_v2_scoring_authority(
            request_preparation_path=preparation_path,
            decision="AUTHORIZE_ONE_SCORING_RUN",
            decision_reason="cannot overwrite",
            destination=destination,
        )


def test_cli_and_authority_firewall() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "shreks_brain" / "fl9_v2_scoring_authority.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-fl9-v2-scoring-authority-decide = '
        '"shreks_brain.fl9_v2_scoring_authority:main"'
        in pyproject
    )

    for forbidden in (
        "run_fast_first_champion_v2_host_request",
        "build_fast_first_champion_v2(",
        "write_fast_first_champion_v2_evidence",
        "score_candidate",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source

    for authority in (
        '"paper_promotion_authority": _BLOCKED',
        '"live_authority": _DISABLED',
    ):
        assert authority in source
