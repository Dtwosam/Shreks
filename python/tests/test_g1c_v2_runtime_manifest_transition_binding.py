from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

import shreks_brain.fl9_v2_runtime_manifest_discovery as discovery
from shreks_brain.g1c_v2_runtime_manifest_candidate_authoring import (
    author_g1c_v2_runtime_manifest_candidate,
)
from shreks_brain.g1c_v2_runtime_manifest_transition_binding import (
    G1CV2RuntimeManifestTransitionBindingError,
    bind_g1c_v2_runtime_manifest_transition,
    decode_g1c_v2_runtime_manifest_transition_binding,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    build_observer_paper_campaign_runtime_manifest_v2,
    encode_observer_paper_campaign_runtime_manifest,
)

from test_fl9_v2_cohort_acceptance_artifact import _write as _write_cohort
from test_fl9_v2_runtime_manifest_discovery import (
    QUOTE,
    _bind_synthetic_cohort_to_request_authority,
    _prior_request_authority,
)
from test_observer_campaign_runtime_manifest import _manifest


NEW_RUN_ID = "paper-v2-transition-binding-20260920"
ENTRY_INPUT_AMOUNT = 125_000_000


def _inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    quote_mint: str = QUOTE,
):
    source = _manifest()
    source_path = tmp_path / "source-v1-paper-campaign.json"
    source_bytes = encode_observer_paper_campaign_runtime_manifest(source)
    source_path.write_bytes(source_bytes)

    candidate = author_g1c_v2_runtime_manifest_candidate(
        source_runtime_manifest_path=source_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=source.initial_state.last_cycle_at_unix_ms + 1_000,
        quote_asset_mint=quote_mint,
        quote_asset_decimals=9,
        entry_input_amount=ENTRY_INPUT_AMOUNT,
    )
    candidate_path = tmp_path / "candidate-v2-paper-campaign.json"
    candidate_bytes = encode_observer_paper_campaign_runtime_manifest(candidate)
    candidate_path.write_bytes(candidate_bytes)

    cohort = _write_cohort(tmp_path, "cohort")
    request_path, _policy_path, request, _policy = _prior_request_authority(
        tmp_path,
        cohort.path,
    )
    _bind_synthetic_cohort_to_request_authority(
        monkeypatch,
        cohort,
        request,
    )
    return (
        source,
        source_path,
        source_bytes,
        candidate,
        candidate_path,
        candidate_bytes,
        cohort.path,
        request_path,
    )


def test_binding_commits_exact_authored_candidate_and_compatible_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source,
        source_path,
        source_bytes,
        candidate,
        candidate_path,
        candidate_bytes,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)
    destination = tmp_path / "transition-binding.json"

    binding = bind_g1c_v2_runtime_manifest_transition(
        source_runtime_manifest_path=source_path,
        candidate_runtime_manifest_path=candidate_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        destination=destination,
    )

    assert binding["schema_name"] == (
        "shreks.g1c_v2_runtime_manifest_transition_binding"
    )
    assert binding["schema_version"] == 1
    assert binding["transition_kind"] == "new_run_quote_asset_rotation"
    assert binding["transition_status"] == "BOUND_COMPATIBLE_CANDIDATE"
    assert binding["source_paper_run_id"] == source.paper_run_id
    assert binding["candidate_paper_run_id"] == candidate.paper_run_id
    assert binding["candidate_quote_asset_mint"] == QUOTE
    assert binding["cohort_quote_mint"] == QUOTE
    assert binding["candidate_quote_usd_valuation_mode"] == "exact_market_ratio"
    assert binding["installation_authority"] == "NOT_GRANTED"
    assert binding["activation_authority"] == "NOT_GRANTED"
    assert binding["rotation_authority"] == "NOT_GRANTED"
    assert binding["scoring_authority"] == "NOT_GRANTED"
    assert binding["paper_promotion_authority"] == "BLOCKED"
    assert binding["live_authority"] == "DISABLED"
    assert len(binding["binding_fingerprint_sha256"]) == 64

    assert source_path.read_bytes() == source_bytes
    assert candidate_path.read_bytes() == candidate_bytes
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert (
        decode_g1c_v2_runtime_manifest_transition_binding(
            destination.read_text(encoding="utf-8")
        )
        == binding
    )


def test_binding_rejects_candidate_incompatible_with_frozen_cohort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _source,
        source_path,
        _source_bytes,
        _candidate,
        candidate_path,
        _candidate_bytes,
        cohort_path,
        request_path,
    ) = _inputs(
        tmp_path,
        monkeypatch,
        quote_mint="different-quote",
    )
    destination = tmp_path / "transition-binding.json"

    with pytest.raises(
        G1CV2RuntimeManifestTransitionBindingError,
        match="COMPATIBLE|cohort|assessment",
    ):
        bind_g1c_v2_runtime_manifest_transition(
            source_runtime_manifest_path=source_path,
            candidate_runtime_manifest_path=candidate_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            destination=destination,
        )
    assert not destination.exists()


def test_binding_rejects_authenticated_v2_manifest_not_exactly_authored_from_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _source,
        source_path,
        _source_bytes,
        candidate,
        candidate_path,
        _candidate_bytes,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)

    drifted = build_observer_paper_campaign_runtime_manifest_v2(
        paper_run_id=candidate.paper_run_id,
        candidate=candidate.candidate,
        initial_state=candidate.initial_state,
        policy_bundle=replace(
            candidate.policy_bundle,
            setup_name=f"{candidate.policy_bundle.setup_name}-drift",
        ),
        risk_environment=candidate.risk_environment,
        selection_policy=candidate.selection_policy,
        recent_performance=candidate.recent_performance,
        global_risk_halt=candidate.global_risk_halt,
        quote_usd_valuation_policy=candidate.quote_usd_valuation_policy,
    )
    candidate_path.write_bytes(
        encode_observer_paper_campaign_runtime_manifest(drifted)
    )
    destination = tmp_path / "transition-binding.json"

    with pytest.raises(
        G1CV2RuntimeManifestTransitionBindingError,
        match="exact canonical new-run derivation",
    ):
        bind_g1c_v2_runtime_manifest_transition(
            source_runtime_manifest_path=source_path,
            candidate_runtime_manifest_path=candidate_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            destination=destination,
        )
    assert not destination.exists()


def test_binding_is_write_once_and_decoder_rejects_authority_escalation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _source,
        source_path,
        _source_bytes,
        _candidate,
        candidate_path,
        _candidate_bytes,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)
    destination = tmp_path / "transition-binding.json"

    binding = bind_g1c_v2_runtime_manifest_transition(
        source_runtime_manifest_path=source_path,
        candidate_runtime_manifest_path=candidate_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        destination=destination,
    )
    with pytest.raises(FileExistsError):
        bind_g1c_v2_runtime_manifest_transition(
            source_runtime_manifest_path=source_path,
            candidate_runtime_manifest_path=candidate_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            destination=destination,
        )

    tampered = dict(binding)
    tampered["installation_authority"] = "GRANTED"
    tampered_payload = (
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
        G1CV2RuntimeManifestTransitionBindingError,
        match="installation_authority",
    ):
        decode_g1c_v2_runtime_manifest_transition_binding(tampered_payload)


def test_transition_binding_cli_is_registered_and_has_no_host_or_trade_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_runtime_manifest_transition_binding.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-runtime-manifest-transition-bind = '
        '"shreks_brain.g1c_v2_runtime_manifest_transition_binding:main"'
        in pyproject
    )

    for forbidden in (
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "systemctl",
        "subprocess",
        "sqlite3",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
