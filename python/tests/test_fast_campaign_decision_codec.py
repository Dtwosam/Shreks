from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from shreks_brain.fast_campaign import (
    FastCampaignActionConstraints,
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionPosition,
    FastCampaignDecisionRequest,
    FastCampaignReduceExecutionCost,
    build_fast_campaign_decision_batch,
    decode_fast_campaign_decision_results,
    encode_fast_campaign_decision_batch,
    fast_campaign_result_to_paper_assessment,
)
from shreks_brain.fast_paper import FastPaperAction



ROOT = Path(__file__).resolve().parents[2]
SHARED_REQUEST_FIXTURE = (
    ROOT
    / "crates"
    / "shreks-core"
    / "tests"
    / "fixtures"
    / "fl9_campaign_decision_request.json"
)
SHARED_RESULT_FIXTURE = (
    ROOT
    / "crates"
    / "shreks-core"
    / "tests"
    / "fixtures"
    / "fl9_campaign_decision_results.json"
)


def _shared_fixture_batch():
    request = FastCampaignDecisionRequest(
        source_event_id="sig-cli:0",
        market_key="pump_fun_bonding_curve:mint-cli:quote-cli",
        source_sequence=1,
        as_of_unix_ms=1_000,
        features=tuple([0.0] * 169),
        position=FastCampaignDecisionPosition(kind="FLAT"),
        constraints=FastCampaignActionConstraints(
            max_exposure_fraction=1.0,
            buy_economically_allowed=True,
            expected_future_exit_cost_bps=10.0,
            reduce_execution_costs=(FastCampaignReduceExecutionCost(0.5, 20.0),),
            sell_executable=True,
            sell_now_cost_bps=15.0,
            force_sell=False,
        ),
    )
    policy = FastCampaignContinuousActionPolicy(
        version=1,
        horizons_ms=(1_000,),
        entry_exposure_candidates=(0.5, 1.0),
        reduce_target_exposure_candidates=(0.5,),
        adverse_excursion_weight=1.0,
        reversal_penalty_bps=100.0,
        route_unavailability_penalty_bps=100.0,
        horizon_disagreement_weight=1.0,
        minimum_buy_value_bps=1.0,
        minimum_hold_value_bps=1.0,
        missing_forecast_open_action="SELL",
    )
    return build_fast_campaign_decision_batch(policy, (request,))


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _batch():
    request = FastCampaignDecisionRequest(
        source_event_id="sig-a:0",
        market_key="pump_fun_bonding_curve:mint-a:quote-a",
        source_sequence=7,
        as_of_unix_ms=1_234,
        features=tuple([None] + [1.0] * 168),
        position=FastCampaignDecisionPosition(kind="FLAT"),
        constraints=FastCampaignActionConstraints(
            max_exposure_fraction=1.0,
            buy_economically_allowed=True,
            expected_future_exit_cost_bps=10.0,
            reduce_execution_costs=(
                FastCampaignReduceExecutionCost(0.5, 20.0),
            ),
            sell_executable=True,
            sell_now_cost_bps=15.0,
            force_sell=False,
        ),
    )
    policy = FastCampaignContinuousActionPolicy(
        version=1,
        horizons_ms=(1_000,),
        entry_exposure_candidates=(0.5, 1.0),
        reduce_target_exposure_candidates=(0.5,),
        adverse_excursion_weight=1.0,
        reversal_penalty_bps=100.0,
        route_unavailability_penalty_bps=100.0,
        horizon_disagreement_weight=1.0,
        minimum_buy_value_bps=1.0,
        minimum_hold_value_bps=1.0,
        missing_forecast_open_action="SELL",
    )
    return build_fast_campaign_decision_batch(policy, (request,))


def _response_payload() -> str:
    decision = {
        "source_event_id": "sig-a:0",
        "market_key": "pump_fun_bonding_curve:mint-a:quote-a",
        "source_sequence": 7,
        "as_of_unix_ms": 1_234,
        "policy_version": 1,
        "action": "BUY",
        "reason": "BUY_SELECTED",
        "selected_horizon_ms": 1_000,
        "current_exposure_fraction": 0.0,
        "target_exposure_fraction": 0.5,
        "selected_reward_bps": 120.0,
        "selected_risk_bps": 35.0,
        "selected_execution_cost_bps": 0.0,
        "selected_value_bps": 51.25,
        "horizon_evidence": [
            {
                "horizon_ms": 1_000,
                "entry_cost_adjusted_return_model_version": "entry-v1",
                "endpoint_return_model_version": "endpoint-v1",
                "mae_model_version": "mae-v1",
                "reversal_model_version": "reversal-v1",
                "route_unavailability_model_version": "route-v1",
                "entry_cost_adjusted_return_bps": 120.0,
                "raw_endpoint_return_bps": 140.0,
                "mae_bps": -20.0,
                "adverse_excursion_bps": 20.0,
                "reversal_probability": 0.1,
                "route_unavailability_probability": 0.05,
                "disagreement_bps": 0.0,
                "risk_bps": 35.0,
            }
        ],
        "candidates": [
            {
                "action": "SKIP",
                "horizon_ms": None,
                "target_exposure_fraction": 0.0,
                "reward_bps": 0.0,
                "risk_bps": 0.0,
                "execution_cost_penalty_bps": 0.0,
                "comparison_value_bps": 0.0,
                "eligible": True,
            },
            {
                "action": "BUY",
                "horizon_ms": 1_000,
                "target_exposure_fraction": 0.5,
                "reward_bps": 120.0,
                "risk_bps": 35.0,
                "execution_cost_penalty_bps": 0.0,
                "comparison_value_bps": 51.25,
                "eligible": True,
            },
        ],
    }
    material = {
        "schema_name": "shreks.fast_campaign_decision_results",
        "schema_version": 1,
        "champion_version": "champion-v1",
        "champion_fingerprint_sha256": "a" * 64,
        "decisions": [decision],
    }
    document = {
        **material,
        "batch_fingerprint_sha256": _sha(material),
    }
    return _canonical(document)


def test_request_encoder_is_canonical_and_preserves_null_features() -> None:
    payload = encode_fast_campaign_decision_batch(_batch())
    assert payload == _canonical(json.loads(payload))
    document = json.loads(payload)
    assert document["decisions"][0]["features"][0] is None
    assert len(document["decisions"][0]["features"]) == 169



def test_shared_rust_request_fixture_matches_python_canonical_wire() -> None:
    payload = encode_fast_campaign_decision_batch(_shared_fixture_batch())
    assert payload == SHARED_REQUEST_FIXTURE.read_text(encoding="utf-8")



def test_shared_rust_result_fixture_decodes_and_validates_in_python() -> None:
    payload = SHARED_RESULT_FIXTURE.read_text(encoding="utf-8")
    results = decode_fast_campaign_decision_results(payload)
    assert results.champion_version == "fl9-campaign-cli-fixture-v1"
    assert results.champion_fingerprint_sha256 == (
        "a5cd91e4053175465ee7512f8c2882c37ab82c05a5bf3c92fbfb6115dfa03efb"
    )
    assert results.batch_fingerprint_sha256 == (
        "5f1d9a5badf59af4dba6f480e40232dcab43fa910e54caffb30886b1d7089eeb"
    )
    assert len(results.decisions) == 1
    assert results.decisions[0].action == "BUY"
    assert results.decisions[0].target_exposure_fraction == pytest.approx(1.0)


def test_result_decoder_validates_canonical_fingerprint_and_rounds_into_fl7_assessment() -> None:
    payload = _response_payload()
    results = decode_fast_campaign_decision_results(payload)
    assert results.champion_version == "champion-v1"
    assert len(results.decisions) == 1
    result = results.decisions[0]
    assert result.action == "BUY"
    assert result.selected_horizon_ms == 1_000
    assert result.selected_value_bps == pytest.approx(51.25)

    assessment = fast_campaign_result_to_paper_assessment(
        result,
        assessment_version="fl9-campaign-assessment-v1",
        strategy_family="fl9-continuous-action",
        strategy_version="fl9-v1",
    )
    assert assessment.action is FastPaperAction.BUY
    assert assessment.source_event_id == "sig-a:0"
    assert assessment.market_key == "pump_fun_bonding_curve:mint-a:quote-a"
    assert assessment.source_sequence == 7
    assert assessment.as_of_unix_ms == 1_234
    assert "BUY_SELECTED" in assessment.reasons[0]
    assert any("1000" in value for value in assessment.reasons)


def test_result_decoder_rejects_unknown_noncanonical_and_tampered_payloads() -> None:
    payload = _response_payload()
    document = json.loads(payload)

    unknown = dict(document)
    unknown["unexpected"] = True
    with pytest.raises(ValueError, match="field|unknown|malformed"):
        decode_fast_campaign_decision_results(_canonical(unknown))

    with pytest.raises(ValueError, match="canonical"):
        decode_fast_campaign_decision_results(
            json.dumps(document, indent=2, sort_keys=False)
        )

    tampered = dict(document)
    tampered["batch_fingerprint_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_campaign_decision_results(_canonical(tampered))
