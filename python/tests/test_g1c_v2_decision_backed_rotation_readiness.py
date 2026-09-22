from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import shreks_brain.g1c_v2_decision_backed_rotation_readiness as bridge
from shreks_brain.g1c_v2_decision_backed_candidate_authority import (
    bind_g1c_v2_decision_backed_candidate_authority,
)
from shreks_brain.g1c_v2_decision_backed_candidate_authoring import (
    author_g1c_v2_candidate_from_decision_backed_authority,
)
from shreks_brain.g1c_v2_decision_backed_transition_binding import (
    bind_g1c_v2_transition_from_decision_backed_authority,
)
from shreks_brain.g1c_v2_paper_manifest_rotation_readiness import (
    PaperManifestRotationReadinessPaths,
)

from test_g1c_v2_decision_backed_candidate_authority import _approved_decision
from test_g1c_v2_runtime_manifest_candidate_authority import NEW_RUN_ID


RELEASE_SHA = "e" * 40


def _inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    decision_path, inputs = _approved_decision(tmp_path, monkeypatch)
    source, source_path, _source_bytes, cohort_path, request_path, _request = inputs

    authority_path = tmp_path / "decision-backed-authority.json"
    authority = bind_g1c_v2_decision_backed_candidate_authority(
        source_runtime_manifest_path=source_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        candidate_value_decision_path=decision_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=source.initial_state.last_cycle_at_unix_ms + 1_000,
        destination=authority_path,
    )

    candidate_path = tmp_path / "candidate.json"
    candidate = author_g1c_v2_candidate_from_decision_backed_authority(
        source_runtime_manifest_path=source_path,
        decision_backed_candidate_authority_path=authority_path,
        destination=candidate_path,
    )

    binding_path = tmp_path / "transition-binding.json"
    binding = bind_g1c_v2_transition_from_decision_backed_authority(
        source_runtime_manifest_path=source_path,
        candidate_runtime_manifest_path=candidate_path,
        decision_backed_candidate_authority_path=authority_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        destination=binding_path,
    )

    paths = PaperManifestRotationReadinessPaths(
        current_link=Path("/opt/shreks/current"),
        env_file=Path("/etc/shreks/shreks.env"),
        active_manifest_path=Path("/etc/shreks/paper-campaign.json"),
        observer_database_path=Path("/var/lib/shreks/shreks.db"),
        evidence_path=Path("/var/lib/shreks/paper-evaluation-e11.json"),
        risk_control_path=Path("/var/lib/shreks/risk/operator-control.json"),
        deploy_sudoers=Path("/etc/sudoers.d/shreks-release-manager"),
        manager_destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
    )
    return authority_path, authority, candidate_path, candidate, binding_path, binding, paths


def _receipt(authority, binding):
    return {
        "schema_name": "shreks.g1c_v2_paper_manifest_rotation_readiness",
        "schema_version": 1,
        "status": "READY_EVIDENCE_ONLY",
        "release_source_sha": RELEASE_SHA,
        "source_manifest_sha256": authority["source_manifest_sha256"],
        "source_runtime_manifest_fingerprint_sha256": authority[
            "source_runtime_manifest_fingerprint_sha256"
        ],
        "source_paper_run_id": authority["source_paper_run_id"],
        "source_quote_asset_mint": authority["source_quote_asset_mint"],
        "candidate_manifest_sha256": authority["candidate_manifest_sha256"],
        "candidate_runtime_manifest_fingerprint_sha256": authority[
            "candidate_runtime_manifest_fingerprint_sha256"
        ],
        "candidate_paper_run_id": authority["candidate_paper_run_id"],
        "candidate_start_at_unix_ms": authority["candidate_start_at_unix_ms"],
        "candidate_quote_asset_mint": authority["candidate_quote_asset_mint"],
        "candidate_quote_asset_decimals": authority["candidate_quote_asset_decimals"],
        "binding_fingerprint_sha256": binding["binding_fingerprint_sha256"],
        "installation_authority": "PROVEN",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }


def test_wrapper_derives_binding_fingerprint_and_returns_standard_readiness_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        authority_path,
        authority,
        candidate_path,
        _candidate,
        binding_path,
        binding,
        paths,
    ) = _inputs(tmp_path, monkeypatch)
    before = {
        "authority": authority_path.read_bytes(),
        "candidate": candidate_path.read_bytes(),
        "binding": binding_path.read_bytes(),
    }
    calls = {}

    def _fake_readiness(**kwargs):
        calls.update(kwargs)
        return _receipt(authority, binding)

    monkeypatch.setattr(
        bridge,
        "prove_paper_manifest_rotation_readiness",
        _fake_readiness,
    )

    receipt = bridge.prove_decision_backed_paper_manifest_rotation_readiness(
        candidate_runtime_manifest_path=candidate_path,
        transition_binding_path=binding_path,
        decision_backed_candidate_authority_path=authority_path,
        installation_proof_payload=b"proof\n",
        expected_release_source_sha=RELEASE_SHA,
        paths=paths,
    )

    assert receipt == _receipt(authority, binding)
    assert calls["candidate_runtime_manifest_path"] == candidate_path.resolve()
    assert calls["transition_binding_path"] == binding_path.resolve()
    assert calls["installation_proof_payload"] == b"proof\n"
    assert calls["expected_binding_fingerprint_sha256"] == binding[
        "binding_fingerprint_sha256"
    ]
    assert calls["expected_release_source_sha"] == RELEASE_SHA
    assert calls["paths"] is paths

    assert authority_path.read_bytes() == before["authority"]
    assert candidate_path.read_bytes() == before["candidate"]
    assert binding_path.read_bytes() == before["binding"]


def test_wrapper_rejects_candidate_not_committed_by_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        authority_path,
        _authority,
        candidate_path,
        _candidate,
        binding_path,
        _binding,
        paths,
    ) = _inputs(tmp_path, monkeypatch)
    payload = candidate_path.read_bytes()
    candidate_path.write_bytes(payload + b" ")

    monkeypatch.setattr(
        bridge,
        "prove_paper_manifest_rotation_readiness",
        lambda **_kwargs: pytest.fail("readiness must not run"),
    )

    with pytest.raises(
        bridge.G1CV2DecisionBackedRotationReadinessError,
        match="candidate|authentication|authority|canonical",
    ):
        bridge.prove_decision_backed_paper_manifest_rotation_readiness(
            candidate_runtime_manifest_path=candidate_path,
            transition_binding_path=binding_path,
            decision_backed_candidate_authority_path=authority_path,
            installation_proof_payload=b"proof\n",
            expected_release_source_sha=RELEASE_SHA,
            paths=paths,
        )


def test_wrapper_rejects_readiness_receipt_provenance_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        authority_path,
        authority,
        candidate_path,
        _candidate,
        binding_path,
        binding,
        paths,
    ) = _inputs(tmp_path, monkeypatch)
    drifted = _receipt(authority, binding)
    drifted["candidate_manifest_sha256"] = "0" * 64

    monkeypatch.setattr(
        bridge,
        "prove_paper_manifest_rotation_readiness",
        lambda **_kwargs: drifted,
    )

    with pytest.raises(
        bridge.G1CV2DecisionBackedRotationReadinessError,
        match="candidate_manifest_sha256|receipt|authority",
    ):
        bridge.prove_decision_backed_paper_manifest_rotation_readiness(
            candidate_runtime_manifest_path=candidate_path,
            transition_binding_path=binding_path,
            decision_backed_candidate_authority_path=authority_path,
            installation_proof_payload=b"proof\n",
            expected_release_source_sha=RELEASE_SHA,
            paths=paths,
        )


def test_wrapper_rejects_authority_changed_during_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        authority_path,
        authority,
        candidate_path,
        _candidate,
        binding_path,
        binding,
        paths,
    ) = _inputs(tmp_path, monkeypatch)

    def _mutating_readiness(**_kwargs):
        authority_path.write_bytes(authority_path.read_bytes() + b" ")
        return _receipt(authority, binding)

    monkeypatch.setattr(
        bridge,
        "prove_paper_manifest_rotation_readiness",
        _mutating_readiness,
    )

    with pytest.raises(
        bridge.G1CV2DecisionBackedRotationReadinessError,
        match="authority changed",
    ):
        bridge.prove_decision_backed_paper_manifest_rotation_readiness(
            candidate_runtime_manifest_path=candidate_path,
            transition_binding_path=binding_path,
            decision_backed_candidate_authority_path=authority_path,
            installation_proof_payload=b"proof\n",
            expected_release_source_sha=RELEASE_SHA,
            paths=paths,
        )


def test_cli_exposes_no_raw_candidate_or_binding_fingerprint_inputs() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_decision_backed_rotation_readiness.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-decision-backed-rotation-readiness = '
        '"shreks_brain.g1c_v2_decision_backed_rotation_readiness:main"'
        in pyproject
    )
    for required in (
        "--candidate-runtime-manifest",
        "--transition-binding",
        "--decision-backed-candidate-authority",
        "--installation-proof",
        "--expected-release-source-sha",
    ):
        assert required in source

    for forbidden_argument in (
        "--expected-binding-fingerprint",
        "--paper-run-id",
        "--start-at-unix-ms",
        "--quote-asset-mint",
        "--quote-asset-decimals",
        "--entry-input-amount",
        "--candidate-value-decision",
        "--quote-valuation-review",
    ):
        assert forbidden_argument not in source

    for forbidden_runtime_surface in (
        "rotate_paper_manifest",
        "shreks-paper-manifest-manager rotate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden_runtime_surface not in source
