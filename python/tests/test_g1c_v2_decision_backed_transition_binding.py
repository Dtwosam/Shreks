from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest

import shreks_brain.g1c_v2_decision_backed_transition_binding as bridge
from shreks_brain.g1c_v2_decision_backed_candidate_authority import (
    bind_g1c_v2_decision_backed_candidate_authority,
)
from shreks_brain.g1c_v2_decision_backed_candidate_authoring import (
    author_g1c_v2_candidate_from_decision_backed_authority,
)
from shreks_brain.g1c_v2_decision_backed_transition_binding import (
    G1CV2DecisionBackedTransitionBindingError,
    bind_g1c_v2_transition_from_decision_backed_authority,
)
from shreks_brain.g1c_v2_runtime_manifest_transition_binding import (
    decode_g1c_v2_runtime_manifest_transition_binding,
)

from test_g1c_v2_decision_backed_candidate_authority import _approved_decision
from test_g1c_v2_runtime_manifest_candidate_authority import NEW_RUN_ID


def _inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    decision_path, inputs = _approved_decision(tmp_path, monkeypatch)
    source, source_path, source_bytes, cohort_path, request_path, _request = inputs

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
    author_g1c_v2_candidate_from_decision_backed_authority(
        source_runtime_manifest_path=source_path,
        decision_backed_candidate_authority_path=authority_path,
        destination=candidate_path,
    )
    candidate_bytes = candidate_path.read_bytes()

    return (
        source_path,
        source_bytes,
        candidate_path,
        candidate_bytes,
        authority_path,
        authority,
        cohort_path,
        request_path,
    )


def test_bridge_writes_standard_transition_binding_bound_to_decision_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source_path,
        source_bytes,
        candidate_path,
        candidate_bytes,
        authority_path,
        authority,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)
    authority_bytes = authority_path.read_bytes()
    destination = tmp_path / "transition-binding.json"

    binding = bind_g1c_v2_transition_from_decision_backed_authority(
        source_runtime_manifest_path=source_path,
        candidate_runtime_manifest_path=candidate_path,
        decision_backed_candidate_authority_path=authority_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        destination=destination,
    )

    assert binding["schema_name"] == "shreks.g1c_v2_runtime_manifest_transition_binding"
    assert binding["schema_version"] == 1
    assert binding["transition_status"] == "BOUND_COMPATIBLE_CANDIDATE"

    for field in (
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "source_paper_run_id",
        "source_quote_asset_mint",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "candidate_paper_run_id",
        "candidate_start_at_unix_ms",
        "candidate_quote_asset_mint",
        "candidate_quote_asset_decimals",
        "candidate_quote_usd_valuation_mode",
        "cohort_artifact_fingerprint_sha256",
        "cohort_quote_mint",
        "request_fingerprint_sha256",
        "request_release_source_sha",
        "request_hydration_policy_fingerprint_sha256",
    ):
        assert binding[field] == authority[field]

    assert binding["installation_authority"] == "NOT_GRANTED"
    assert binding["activation_authority"] == "NOT_GRANTED"
    assert binding["rotation_authority"] == "NOT_GRANTED"
    assert binding["scoring_authority"] == "NOT_GRANTED"
    assert binding["paper_promotion_authority"] == "BLOCKED"
    assert binding["live_authority"] == "DISABLED"

    assert source_path.read_bytes() == source_bytes
    assert candidate_path.read_bytes() == candidate_bytes
    assert authority_path.read_bytes() == authority_bytes
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert (
        decode_g1c_v2_runtime_manifest_transition_binding(
            destination.read_text(encoding="utf-8")
        )
        == binding
    )


def test_bridge_rejects_candidate_not_committed_by_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source_path,
        _source_bytes,
        candidate_path,
        _candidate_bytes,
        authority_path,
        _authority,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    payload["paper_run_id"] = "different-run"
    candidate_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    destination = tmp_path / "transition-binding.json"

    with pytest.raises(
        G1CV2DecisionBackedTransitionBindingError,
        match="candidate|authority|authentication|fingerprint",
    ):
        bind_g1c_v2_transition_from_decision_backed_authority(
            source_runtime_manifest_path=source_path,
            candidate_runtime_manifest_path=candidate_path,
            decision_backed_candidate_authority_path=authority_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            destination=destination,
        )
    assert not destination.exists()


def test_bridge_rejects_transition_provenance_not_committed_by_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source_path,
        _source_bytes,
        candidate_path,
        _candidate_bytes,
        authority_path,
        _authority,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)
    destination = tmp_path / "transition-binding.json"

    original = bridge.bind_g1c_v2_runtime_manifest_transition

    def _drifted_binding(**kwargs):
        result = original(**kwargs)
        result["request_fingerprint_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(
        bridge,
        "bind_g1c_v2_runtime_manifest_transition",
        _drifted_binding,
    )

    with pytest.raises(
        G1CV2DecisionBackedTransitionBindingError,
        match="request_fingerprint_sha256|provenance|authority",
    ):
        bind_g1c_v2_transition_from_decision_backed_authority(
            source_runtime_manifest_path=source_path,
            candidate_runtime_manifest_path=candidate_path,
            decision_backed_candidate_authority_path=authority_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            destination=destination,
        )
    assert not destination.exists()


def test_bridge_rejects_authority_changed_during_derivation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source_path,
        _source_bytes,
        candidate_path,
        _candidate_bytes,
        authority_path,
        _authority,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)
    destination = tmp_path / "transition-binding.json"

    original = bridge.bind_g1c_v2_runtime_manifest_transition

    def _mutating_binding(**kwargs):
        result = original(**kwargs)
        authority_path.write_bytes(authority_path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        bridge,
        "bind_g1c_v2_runtime_manifest_transition",
        _mutating_binding,
    )

    with pytest.raises(
        G1CV2DecisionBackedTransitionBindingError,
        match="authority changed",
    ):
        bind_g1c_v2_transition_from_decision_backed_authority(
            source_runtime_manifest_path=source_path,
            candidate_runtime_manifest_path=candidate_path,
            decision_backed_candidate_authority_path=authority_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            destination=destination,
        )
    assert not destination.exists()


def test_bridge_is_write_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source_path,
        _source_bytes,
        candidate_path,
        _candidate_bytes,
        authority_path,
        _authority,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)
    destination = tmp_path / "transition-binding.json"
    destination.write_text("occupied\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        bind_g1c_v2_transition_from_decision_backed_authority(
            source_runtime_manifest_path=source_path,
            candidate_runtime_manifest_path=candidate_path,
            decision_backed_candidate_authority_path=authority_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            destination=destination,
        )


def test_decision_backed_transition_cli_has_no_raw_candidate_inputs() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_decision_backed_transition_binding.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-decision-backed-transition-bind = '
        '"shreks_brain.g1c_v2_decision_backed_transition_binding:main"'
        in pyproject
    )
    for required in (
        "--source-runtime-manifest",
        "--candidate-runtime-manifest",
        "--decision-backed-candidate-authority",
        "--cohort",
        "--v2-host-request-authority",
        "--destination",
    ):
        assert required in source

    for forbidden_argument in (
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
        "sqlite3",
        "ObserverMarketStore",
        "systemctl",
        "subprocess",
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "rotation_readiness",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden_runtime_surface not in source
