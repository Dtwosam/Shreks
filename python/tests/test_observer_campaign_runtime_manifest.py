from __future__ import annotations

from dataclasses import replace
import json

import pytest

from shreks_brain.observer_campaign.coordinator import (
    ObserverPaperCampaignSelectionPolicy,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION,
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
    OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION,
    ObserverPaperQuoteUsdValuationMode,
    ObserverPaperQuoteUsdValuationPolicy,
    ObserverPaperCampaignRuntimeManifestError,
    build_observer_paper_campaign_runtime_manifest,
    build_observer_paper_campaign_runtime_manifest_v2,
    decode_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.regime import RecentStrategyPerformance
from shreks_brain.registry.codec import compute_candidate_fingerprint

from test_observer_campaign_runner import RUN_ID, _bundle, _candidate, _environment, _state


def _valid_candidate():
    draft = _candidate()
    return replace(
        draft,
        candidate_fingerprint_sha256=compute_candidate_fingerprint(draft),
    )


def _manifest(*, recent_performance=None):
    return build_observer_paper_campaign_runtime_manifest(
        paper_run_id=RUN_ID,
        candidate=_valid_candidate(),
        initial_state=_state(),
        policy_bundle=_bundle(),
        risk_environment=_environment(),
        selection_policy=ObserverPaperCampaignSelectionPolicy(
            recent_lookback_ms=120_000,
            max_entry_candidates=25,
        ),
        recent_performance=recent_performance,
        global_risk_halt=False,
    )


def _find_tagged_type(value, type_name: str):
    if isinstance(value, dict):
        if value.get("$type") == type_name:
            return value
        for nested in value.values():
            found = _find_tagged_type(nested, type_name)
            if found is not None:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _find_tagged_type(nested, type_name)
            if found is not None:
                return found
    return None


def test_manifest_round_trip_is_exact_canonical_and_fingerprinted() -> None:
    recent = RecentStrategyPerformance(
        observed_through_unix_ms=900_000,
        closed_trade_count=12,
        net_expectancy_after_costs_pct=1.25,
    )
    manifest = _manifest(recent_performance=recent)

    encoded = encode_observer_paper_campaign_runtime_manifest(manifest)
    decoded = decode_observer_paper_campaign_runtime_manifest(encoded)

    assert decoded == manifest
    assert decoded.schema_version == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION
    assert decoded.paper_run_id == RUN_ID
    assert decoded.initial_state == _state()
    assert decoded.policy_bundle == _bundle()
    assert decoded.risk_environment == _environment()
    assert decoded.recent_performance == recent
    assert len(decoded.manifest_fingerprint_sha256) == 64
    assert encode_observer_paper_campaign_runtime_manifest(decoded) == encoded
    assert encoded == json.dumps(
        json.loads(encoded.decode("utf-8")),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def test_manifest_exact_top_level_keys_are_required() -> None:
    document = json.loads(encode_observer_paper_campaign_runtime_manifest(_manifest()))

    missing = dict(document)
    missing.pop("selection_policy")
    with pytest.raises(ObserverPaperCampaignRuntimeManifestError, match="field"):
        decode_observer_paper_campaign_runtime_manifest(json.dumps(missing))

    extra = dict(document)
    extra["unexpected"] = True
    with pytest.raises(ObserverPaperCampaignRuntimeManifestError, match="field"):
        decode_observer_paper_campaign_runtime_manifest(json.dumps(extra))


def test_manifest_rejects_content_and_fingerprint_tampering() -> None:
    document = json.loads(encode_observer_paper_campaign_runtime_manifest(_manifest()))

    tampered = dict(document)
    tampered["paper_run_id"] = "other-run"
    raw = json.dumps(
        tampered,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    with pytest.raises(ObserverPaperCampaignRuntimeManifestError, match="fingerprint"):
        decode_observer_paper_campaign_runtime_manifest(raw)

    bad_fingerprint = dict(document)
    bad_fingerprint["manifest_fingerprint_sha256"] = "0" * 64
    raw = json.dumps(
        bad_fingerprint,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    with pytest.raises(ObserverPaperCampaignRuntimeManifestError, match="fingerprint"):
        decode_observer_paper_campaign_runtime_manifest(raw)


def test_manifest_rejects_noncanonical_payload_and_unknown_tagged_types() -> None:
    encoded = encode_observer_paper_campaign_runtime_manifest(_manifest())
    document = json.loads(encoded)

    with pytest.raises(ObserverPaperCampaignRuntimeManifestError, match="canonical"):
        decode_observer_paper_campaign_runtime_manifest(
            json.dumps(document, indent=2, ensure_ascii=False)
        )

    malformed = json.loads(encoded)
    policy = _find_tagged_type(malformed, "ScorePolicy")
    assert policy is not None
    policy["$type"] = "UnknownPolicy"
    raw = json.dumps(
        malformed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    with pytest.raises(ObserverPaperCampaignRuntimeManifestError, match="type"):
        decode_observer_paper_campaign_runtime_manifest(raw)


def test_manifest_rejects_missing_nested_policy_fields_instead_of_defaulting() -> None:
    document = json.loads(encode_observer_paper_campaign_runtime_manifest(_manifest()))
    score_policy = _find_tagged_type(document, "ScorePolicy")
    assert score_policy is not None
    score_policy["fields"].pop("safety_weight")
    raw = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    with pytest.raises(ObserverPaperCampaignRuntimeManifestError, match="field"):
        decode_observer_paper_campaign_runtime_manifest(raw)


def test_manifest_rejects_invalid_registry_candidate_fingerprint() -> None:
    with pytest.raises(ObserverPaperCampaignRuntimeManifestError, match="candidate fingerprint"):
        build_observer_paper_campaign_runtime_manifest(
            paper_run_id=RUN_ID,
            candidate=_candidate(),
            initial_state=_state(),
            policy_bundle=_bundle(),
            risk_environment=_environment(),
            selection_policy=ObserverPaperCampaignSelectionPolicy(
                recent_lookback_ms=120_000,
                max_entry_candidates=25,
            ),
            recent_performance=None,
            global_risk_halt=False,
        )


def _manifest_v2():
    source = _manifest()
    return build_observer_paper_campaign_runtime_manifest_v2(
        paper_run_id=source.paper_run_id,
        candidate=source.candidate,
        initial_state=source.initial_state,
        policy_bundle=source.policy_bundle,
        risk_environment=source.risk_environment,
        selection_policy=source.selection_policy,
        recent_performance=source.recent_performance,
        global_risk_halt=source.global_risk_halt,
        quote_usd_valuation_policy=ObserverPaperQuoteUsdValuationPolicy(
            version=OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION,
            mode=ObserverPaperQuoteUsdValuationMode.EXACT_MARKET_RATIO,
        ),
    )


def test_v1_manifest_bytes_remain_legacy_exact_without_quote_valuation_field() -> None:
    encoded = encode_observer_paper_campaign_runtime_manifest(_manifest())
    document = json.loads(encoded)

    assert document["schema_version"] == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION
    assert "quote_usd_valuation_policy" not in document
    assert decode_observer_paper_campaign_runtime_manifest(encoded) == _manifest()


def test_v2_manifest_round_trip_is_canonical_fingerprinted_and_explicitly_dynamic() -> None:
    manifest = _manifest_v2()

    encoded = encode_observer_paper_campaign_runtime_manifest(manifest)
    document = json.loads(encoded)
    decoded = decode_observer_paper_campaign_runtime_manifest(encoded)

    assert manifest.schema_version == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    assert document["schema_version"] == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    assert set(document) == {
        "schema_version",
        "paper_run_id",
        "candidate",
        "initial_state_checkpoint",
        "policy_bundle",
        "risk_environment",
        "selection_policy",
        "recent_performance",
        "global_risk_halt",
        "quote_usd_valuation_policy",
        "manifest_fingerprint_sha256",
    }
    assert decoded == manifest
    assert decoded.quote_usd_valuation_policy is not None
    assert (
        decoded.quote_usd_valuation_policy.mode
        is ObserverPaperQuoteUsdValuationMode.EXACT_MARKET_RATIO
    )
    assert encode_observer_paper_campaign_runtime_manifest(decoded) == encoded


def test_v2_manifest_requires_exact_dynamic_policy_and_legacy_usd_sentinel() -> None:
    source = _manifest()
    bad_bundle = replace(
        source.policy_bundle,
        quote_asset=replace(
            source.policy_bundle.quote_asset,
            usd_per_token=165.0,
        ),
    )
    with pytest.raises(
        ObserverPaperCampaignRuntimeManifestError,
        match="sentinel|usd_per_token|valuation",
    ):
        build_observer_paper_campaign_runtime_manifest_v2(
            paper_run_id=source.paper_run_id,
            candidate=source.candidate,
            initial_state=source.initial_state,
            policy_bundle=bad_bundle,
            risk_environment=source.risk_environment,
            selection_policy=source.selection_policy,
            recent_performance=source.recent_performance,
            global_risk_halt=source.global_risk_halt,
            quote_usd_valuation_policy=ObserverPaperQuoteUsdValuationPolicy(
                version=OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION,
                mode=ObserverPaperQuoteUsdValuationMode.EXACT_MARKET_RATIO,
            ),
        )

    encoded = encode_observer_paper_campaign_runtime_manifest(_manifest_v2())
    document = json.loads(encoded)
    document.pop("quote_usd_valuation_policy")
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"))
    with pytest.raises(
        ObserverPaperCampaignRuntimeManifestError,
        match="field|valuation",
    ):
        decode_observer_paper_campaign_runtime_manifest(raw)
