from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.g1c_v2_entry_sizing_proposal import (
    G1CV2EntrySizingProposalError,
    decode_g1c_v2_entry_sizing_proposal,
    propose_g1c_v2_entry_sizing,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    encode_observer_paper_campaign_runtime_manifest,
)

from test_observer_campaign_runtime_manifest import _manifest


WSOL = "So11111111111111111111111111111111111111112"
EVIDENCE_FP = "a" * 64


def _source(tmp_path: Path) -> tuple[Path, bytes]:
    manifest = _manifest()
    payload = encode_observer_paper_campaign_runtime_manifest(manifest)
    path = tmp_path / "source.json"
    path.write_bytes(payload)
    return path, payload


def test_entry_sizing_proposal_preserves_source_quote_notional_by_flooring_raw_units(
    tmp_path: Path,
) -> None:
    source_path, source_bytes = _source(tmp_path)
    destination = tmp_path / "proposal.json"

    proposal = propose_g1c_v2_entry_sizing(
        source_runtime_manifest_path=source_path,
        target_quote_mint=WSOL,
        target_quote_decimals=9,
        target_quote_usd_per_token="200",
        quote_evidence_fingerprint_sha256=EVIDENCE_FP,
        quote_evidence_observed_at_unix_ms=1_999_999,
        destination=destination,
    )

    assert proposal["schema_name"] == "shreks.g1c_v2_entry_sizing_proposal"
    assert proposal["schema_version"] == 1
    assert proposal["status"] == "PROPOSAL_EVIDENCE_ONLY"
    assert proposal["sizing_policy"] == "preserve_source_quote_notional_floor"
    assert proposal["source_manifest_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert proposal["source_entry_input_amount"] == 25_000_000
    assert proposal["source_quote_decimals"] == 6
    assert proposal["source_quote_usd_per_token"] == "1"
    assert proposal["source_quote_notional_usd"] == "25"
    assert proposal["target_quote_mint"] == WSOL
    assert proposal["target_quote_decimals"] == 9
    assert proposal["target_quote_usd_per_token"] == "200"
    assert proposal["quote_evidence_fingerprint_sha256"] == EVIDENCE_FP
    assert proposal["proposed_entry_input_amount"] == 125_000_000
    assert proposal["proposed_quote_token_amount"] == "0.125"
    assert proposal["proposed_quote_notional_usd"] == "25"
    assert proposal["notional_shortfall_usd"] == "0"
    assert proposal["candidate_value_authority"] == "NOT_GRANTED"
    assert proposal["candidate_authoring_authority"] == "NOT_GRANTED"
    assert proposal["rotation_authority"] == "NOT_GRANTED"
    assert proposal["scoring_authority"] == "NOT_GRANTED"
    assert proposal["paper_promotion_authority"] == "BLOCKED"
    assert proposal["live_authority"] == "DISABLED"
    assert len(proposal["proposal_fingerprint_sha256"]) == 64
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert decode_g1c_v2_entry_sizing_proposal(
        destination.read_text(encoding="utf-8")
    ) == proposal


def test_entry_sizing_proposal_rounds_down_and_never_exceeds_source_notional(
    tmp_path: Path,
) -> None:
    source_path, _ = _source(tmp_path)
    proposal = propose_g1c_v2_entry_sizing(
        source_runtime_manifest_path=source_path,
        target_quote_mint=WSOL,
        target_quote_decimals=9,
        target_quote_usd_per_token="187.123456789",
        quote_evidence_fingerprint_sha256=EVIDENCE_FP,
        quote_evidence_observed_at_unix_ms=2_000_000,
        destination=tmp_path / "proposal.json",
    )

    assert proposal["proposed_entry_input_amount"] > 0
    assert float(proposal["proposed_quote_notional_usd"]) <= 25.0
    assert float(proposal["notional_shortfall_usd"]) >= 0.0
    assert float(proposal["notional_shortfall_usd"]) < 187.123456789 / 1_000_000_000


@pytest.mark.parametrize(
    ("overrides", "pattern"),
    (
        ({"target_quote_mint": _manifest().policy_bundle.quote_asset.mint}, "different"),
        ({"target_quote_decimals": -1}, "decimal"),
        ({"target_quote_usd_per_token": "0"}, "positive"),
        ({"target_quote_usd_per_token": "nan"}, "finite|decimal"),
        ({"quote_evidence_fingerprint_sha256": "bad"}, "SHA-256"),
        ({"quote_evidence_observed_at_unix_ms": -1}, "non-negative"),
    ),
)
def test_entry_sizing_proposal_rejects_invalid_reference_inputs(
    tmp_path: Path,
    overrides: dict[str, object],
    pattern: str,
) -> None:
    source_path, _ = _source(tmp_path)
    destination = tmp_path / "proposal.json"
    values = dict(
        source_runtime_manifest_path=source_path,
        target_quote_mint=WSOL,
        target_quote_decimals=9,
        target_quote_usd_per_token="200",
        quote_evidence_fingerprint_sha256=EVIDENCE_FP,
        quote_evidence_observed_at_unix_ms=2_000_000,
        destination=destination,
    )
    values.update(overrides)

    with pytest.raises(G1CV2EntrySizingProposalError, match=pattern):
        propose_g1c_v2_entry_sizing(**values)

    assert not destination.exists()


def test_entry_sizing_proposal_is_write_once_and_decoder_rejects_authority_escalation(
    tmp_path: Path,
) -> None:
    source_path, _ = _source(tmp_path)
    destination = tmp_path / "proposal.json"
    kwargs = dict(
        source_runtime_manifest_path=source_path,
        target_quote_mint=WSOL,
        target_quote_decimals=9,
        target_quote_usd_per_token="200",
        quote_evidence_fingerprint_sha256=EVIDENCE_FP,
        quote_evidence_observed_at_unix_ms=2_000_000,
        destination=destination,
    )
    proposal = propose_g1c_v2_entry_sizing(**kwargs)

    with pytest.raises(FileExistsError):
        propose_g1c_v2_entry_sizing(**kwargs)

    tampered = dict(proposal)
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
    with pytest.raises(G1CV2EntrySizingProposalError, match="authority|fingerprint"):
        decode_g1c_v2_entry_sizing_proposal(payload)


def test_entry_sizing_proposal_cli_is_offline_and_grants_no_runtime_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "shreks_brain" / "g1c_v2_entry_sizing_proposal.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-entry-sizing-proposal = '
        '"shreks_brain.g1c_v2_entry_sizing_proposal:main"'
        in pyproject
    )
    for forbidden in (
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "sqlite3",
        "systemctl",
        "subprocess",
        "candidate_authority",
        "candidate_authoring",
        "transition_binding",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
