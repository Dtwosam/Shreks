from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from shreks_brain.fast_deterministic_lifecycle import (
    FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME,
    FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION,
    FastDeterministicCandidateManifest,
    decode_fast_deterministic_candidate_manifest,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_candidate_manifest_v1.json"
)


def _payload() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reseal(document: dict[str, object]) -> str:
    material = dict(document)
    material.pop("candidate_fingerprint_sha256", None)
    document["candidate_fingerprint_sha256"] = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    return _canonical(document)


def test_shared_golden_candidate_manifest_decodes_exact_identity() -> None:
    manifest = decode_fast_deterministic_candidate_manifest(_payload())

    assert type(manifest) is FastDeterministicCandidateManifest
    assert manifest.schema_name == FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME
    assert manifest.schema_version == FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION
    assert manifest.candidate_version == "fl9-baseline-impulse-scalp-longer-runner-v1"
    assert manifest.strategy_family == "fast_deterministic_lifecycle"
    assert manifest.strategy_version == "impulse-scalp__longer-runner-v1"
    assert (
        manifest.candidate_fingerprint_sha256
        == "7377f016783f80c6d3935ff41efd7a66b8da280df13cd7be8d2e6c03146a8676"
    )
    assert manifest.lifecycle_policy.entry_baseline_kind == "IMPULSE_SCALP"
    assert manifest.lifecycle_policy.manager_baseline_kind == "LONGER_RUNNER"
    assert manifest.entry_policy.kind == "IMPULSE_SCALP"
    assert manifest.manager_policy.kind == "LONGER_RUNNER"
    assert manifest.entry_policy.parameters["signal_window_ms"] == 500
    assert (
        manifest.manager_policy.parameters[
            "min_risk_adjusted_continuation_bps_for_hold"
        ]
        == 100.0
    )


def test_candidate_manifest_requires_canonical_json_and_authenticates_before_semantics() -> None:
    document = json.loads(_payload())

    with pytest.raises(ValueError, match="canonical"):
        decode_fast_deterministic_candidate_manifest(json.dumps(document, indent=2))

    document["entry_policy"]["parameters"]["min_buy_count"] = 6
    tampered = _canonical(document)
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_deterministic_candidate_manifest(tampered)

    document = json.loads(_payload())
    document["entry_policy"]["kind"] = "MICRO_PULLBACK"
    payload = _reseal(document)
    with pytest.raises(ValueError, match="entry|kind|parameters"):
        decode_fast_deterministic_candidate_manifest(payload)


def test_candidate_manifest_rejects_unknown_fields_and_dynamic_decision_content() -> None:
    document = json.loads(_payload())
    document["market_key"] = "not-candidate-config"
    payload = _reseal(document)
    with pytest.raises(ValueError, match="unknown|missing"):
        decode_fast_deterministic_candidate_manifest(payload)

    document = json.loads(_payload())
    document["entry_policy"]["parameters"]["forecast_exit_price_quote"] = 0.02
    payload = _reseal(document)
    with pytest.raises(ValueError, match="unknown|parameters"):
        decode_fast_deterministic_candidate_manifest(payload)


def test_candidate_identity_changes_when_selected_policy_configuration_changes() -> None:
    original = decode_fast_deterministic_candidate_manifest(_payload())
    document = json.loads(_payload())
    document["entry_policy"]["parameters"]["min_buy_count"] = 6
    changed = decode_fast_deterministic_candidate_manifest(_reseal(document))

    assert (
        changed.candidate_fingerprint_sha256
        != original.candidate_fingerprint_sha256
    )
    assert changed.candidate_version == original.candidate_version
    assert changed.strategy_version == original.strategy_version


def test_candidate_manifest_package_has_no_market_paper_or_live_authority() -> None:
    package = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_lifecycle"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    )

    for forbidden in (
        "FastTrainingFeatureRecord",
        "FastMarketSnapshot",
        "FastCampaignDecisionResult",
        "PaperLedger",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "RiskContext",
        "requests.",
        "sqlite3",
        "RuntimeMode",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source
