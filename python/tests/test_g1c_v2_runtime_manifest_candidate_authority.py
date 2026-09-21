from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.g1c_v2_runtime_manifest_candidate_authoring import (
    author_g1c_v2_runtime_manifest_candidate,
)
from shreks_brain.g1c_v2_runtime_manifest_candidate_authority import (
    G1CV2RuntimeManifestCandidateAuthorityError,
    bind_g1c_v2_runtime_manifest_candidate_authority,
    decode_g1c_v2_runtime_manifest_candidate_authority,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    encode_observer_paper_campaign_runtime_manifest,
)

from test_fl9_v2_cohort_acceptance_artifact import _write as _write_cohort
from test_fl9_v2_runtime_manifest_discovery import (
    QUOTE,
    _bind_synthetic_cohort_to_request_authority,
    _prior_request_authority,
)
from test_observer_campaign_runtime_manifest import _manifest


NEW_RUN_ID = "paper-v2-explicit-authority-20260921"
ENTRY_INPUT_AMOUNT = 125_000_000


def _inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = _manifest()
    source_path = tmp_path / "source-v1-paper-campaign.json"
    source_bytes = encode_observer_paper_campaign_runtime_manifest(source)
    source_path.write_bytes(source_bytes)

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
    return source, source_path, source_bytes, cohort.path, request_path, request


def test_candidate_authority_binds_only_explicit_inputs_to_exact_candidate(
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
    ) = _inputs(tmp_path, monkeypatch)
    destination = tmp_path / "candidate-authority.json"
    start_at = source.initial_state.last_cycle_at_unix_ms + 1_000

    authority = bind_g1c_v2_runtime_manifest_candidate_authority(
        source_runtime_manifest_path=source_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=start_at,
        quote_asset_mint=QUOTE,
        quote_asset_decimals=9,
        entry_input_amount=ENTRY_INPUT_AMOUNT,
        destination=destination,
    )

    expected_candidate = author_g1c_v2_runtime_manifest_candidate(
        source_runtime_manifest_path=source_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=start_at,
        quote_asset_mint=QUOTE,
        quote_asset_decimals=9,
        entry_input_amount=ENTRY_INPUT_AMOUNT,
    )
    expected_candidate_bytes = encode_observer_paper_campaign_runtime_manifest(
        expected_candidate
    )

    assert authority["schema_name"] == (
        "shreks.g1c_v2_runtime_manifest_candidate_authority"
    )
    assert authority["schema_version"] == 1
    assert authority["authority_kind"] == "explicit_new_run_candidate_inputs"
    assert authority["authority_status"] == "BOUND_EXACT_CANONICAL_CANDIDATE"
    assert authority["source_manifest_sha256"] == hashlib.sha256(
        source_bytes
    ).hexdigest()
    assert authority["source_runtime_manifest_fingerprint_sha256"] == (
        source.manifest_fingerprint_sha256
    )
    assert authority["source_paper_run_id"] == source.paper_run_id
    assert authority["candidate_manifest_sha256"] == hashlib.sha256(
        expected_candidate_bytes
    ).hexdigest()
    assert authority["candidate_runtime_manifest_fingerprint_sha256"] == (
        expected_candidate.manifest_fingerprint_sha256
    )
    assert authority["candidate_paper_run_id"] == NEW_RUN_ID
    assert authority["candidate_start_at_unix_ms"] == start_at
    assert authority["candidate_quote_asset_mint"] == QUOTE
    assert authority["candidate_quote_asset_decimals"] == 9
    assert authority["candidate_entry_input_amount"] == ENTRY_INPUT_AMOUNT
    assert authority["candidate_quote_usd_valuation_mode"] == "exact_market_ratio"
    assert authority["cohort_quote_mint"] == QUOTE
    assert authority["request_fingerprint_sha256"] == (
        request.request_fingerprint_sha256
    )
    assert authority["request_release_source_sha"] == (
        request.expected_release_source_sha
    )
    assert authority["candidate_authoring_authority"] == "EXPLICIT_INPUTS_BOUND"
    assert authority["installation_authority"] == "NOT_GRANTED"
    assert authority["activation_authority"] == "NOT_GRANTED"
    assert authority["rotation_authority"] == "NOT_GRANTED"
    assert authority["scoring_authority"] == "NOT_GRANTED"
    assert authority["paper_promotion_authority"] == "BLOCKED"
    assert authority["live_authority"] == "DISABLED"
    assert len(authority["authority_fingerprint_sha256"]) == 64

    assert source_path.read_bytes() == source_bytes
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert (
        decode_g1c_v2_runtime_manifest_candidate_authority(
            destination.read_text(encoding="utf-8")
        )
        == authority
    )


def test_candidate_authority_rejects_quote_mint_not_matching_frozen_cohort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_path, _source_bytes, cohort_path, request_path, _request = (
        _inputs(tmp_path, monkeypatch)
    )
    destination = tmp_path / "candidate-authority.json"

    with pytest.raises(
        G1CV2RuntimeManifestCandidateAuthorityError,
        match="cohort quote mint|quote asset",
    ):
        bind_g1c_v2_runtime_manifest_candidate_authority(
            source_runtime_manifest_path=source_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            paper_run_id=NEW_RUN_ID,
            start_at_unix_ms=source.initial_state.last_cycle_at_unix_ms + 1_000,
            quote_asset_mint="not-the-frozen-quote",
            quote_asset_decimals=9,
            entry_input_amount=ENTRY_INPUT_AMOUNT,
            destination=destination,
        )

    assert not destination.exists()


@pytest.mark.parametrize(
    ("overrides", "pattern"),
    (
        ({"paper_run_id": _manifest().paper_run_id}, "paper_run_id|new run|different"),
        ({"quote_asset_decimals": -1}, "decimal"),
        ({"entry_input_amount": 0}, "input|amount|positive"),
    ),
)
def test_candidate_authority_rejects_invalid_explicit_inputs_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    pattern: str,
) -> None:
    source, source_path, _source_bytes, cohort_path, request_path, _request = (
        _inputs(tmp_path, monkeypatch)
    )
    destination = tmp_path / "candidate-authority.json"
    values = {
        "paper_run_id": NEW_RUN_ID,
        "start_at_unix_ms": source.initial_state.last_cycle_at_unix_ms + 1_000,
        "quote_asset_mint": QUOTE,
        "quote_asset_decimals": 9,
        "entry_input_amount": ENTRY_INPUT_AMOUNT,
    }
    values.update(overrides)

    with pytest.raises(
        (G1CV2RuntimeManifestCandidateAuthorityError, ValueError),
        match=pattern,
    ):
        bind_g1c_v2_runtime_manifest_candidate_authority(
            source_runtime_manifest_path=source_path,
            cohort_path=cohort_path,
            v2_host_request_authority_path=request_path,
            destination=destination,
            **values,
        )

    assert not destination.exists()


def test_candidate_authority_is_write_once_and_decoder_rejects_escalation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_path, _source_bytes, cohort_path, request_path, _request = (
        _inputs(tmp_path, monkeypatch)
    )
    destination = tmp_path / "candidate-authority.json"
    kwargs = dict(
        source_runtime_manifest_path=source_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=source.initial_state.last_cycle_at_unix_ms + 1_000,
        quote_asset_mint=QUOTE,
        quote_asset_decimals=9,
        entry_input_amount=ENTRY_INPUT_AMOUNT,
        destination=destination,
    )

    authority = bind_g1c_v2_runtime_manifest_candidate_authority(**kwargs)

    with pytest.raises(FileExistsError):
        bind_g1c_v2_runtime_manifest_candidate_authority(**kwargs)

    tampered = dict(authority)
    tampered["rotation_authority"] = "GRANTED"
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
        G1CV2RuntimeManifestCandidateAuthorityError,
        match="rotation_authority|fingerprint",
    ):
        decode_g1c_v2_runtime_manifest_candidate_authority(payload)


def test_candidate_authority_cli_is_registered_and_has_no_host_or_trade_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_runtime_manifest_candidate_authority.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-runtime-manifest-candidate-authority-bind = '
        '"shreks_brain.g1c_v2_runtime_manifest_candidate_authority:main"'
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
        "promote_candidate",
        "publish_champion",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
