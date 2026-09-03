from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Any

from shreks_brain.fast_paper import FastPaperAction, FastPaperActionAssessment

from .models import (
    FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
    FastCampaignActionCandidate,
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionBatch,
    FastCampaignDecisionPosition,
    FastCampaignDecisionRequest,
    FastCampaignDecisionResult,
    FastCampaignDecisionResults,
    FastCampaignHorizonEvidence,
)


_TOP_RESULT_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "champion_version",
        "champion_fingerprint_sha256",
        "decisions",
        "batch_fingerprint_sha256",
    }
)
_DECISION_RESULT_KEYS = frozenset(
    {
        "source_event_id",
        "market_key",
        "source_sequence",
        "as_of_unix_ms",
        "policy_version",
        "action",
        "reason",
        "selected_horizon_ms",
        "current_exposure_fraction",
        "target_exposure_fraction",
        "selected_reward_bps",
        "selected_risk_bps",
        "selected_execution_cost_bps",
        "selected_value_bps",
        "horizon_evidence",
        "candidates",
    }
)
_HORIZON_KEYS = frozenset(
    {
        "horizon_ms",
        "entry_cost_adjusted_return_model_version",
        "endpoint_return_model_version",
        "mae_model_version",
        "reversal_model_version",
        "route_unavailability_model_version",
        "entry_cost_adjusted_return_bps",
        "raw_endpoint_return_bps",
        "mae_bps",
        "adverse_excursion_bps",
        "reversal_probability",
        "route_unavailability_probability",
        "disagreement_bps",
        "risk_bps",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "action",
        "horizon_ms",
        "target_exposure_fraction",
        "reward_bps",
        "risk_bps",
        "execution_cost_penalty_bps",
        "comparison_value_bps",
        "eligible",
    }
)


def encode_fast_campaign_decision_batch(
    batch: FastCampaignDecisionBatch,
) -> str:
    if type(batch) is not FastCampaignDecisionBatch:
        raise ValueError("batch must be an exact FastCampaignDecisionBatch")
    document = {
        "schema_name": batch.schema_name,
        "schema_version": batch.schema_version,
        "policy": _policy_document(batch.policy),
        "decisions": [_request_document(value) for value in batch.decisions],
    }
    return _canonical(document)


def decode_fast_campaign_decision_results(
    payload: str,
) -> FastCampaignDecisionResults:
    if not isinstance(payload, str) or not payload:
        raise ValueError("campaign result payload must be a non-empty string")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("campaign result payload is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("campaign result payload must be a JSON object")
    if payload != _canonical(document):
        raise ValueError("campaign result payload must use canonical JSON")
    _require_exact_keys("campaign result", document, _TOP_RESULT_KEYS)

    material = dict(document)
    claimed_fingerprint = material.pop("batch_fingerprint_sha256")
    expected_fingerprint = _sha(material)
    if claimed_fingerprint != expected_fingerprint:
        raise ValueError("campaign result fingerprint mismatch")

    decisions_value = document["decisions"]
    if not isinstance(decisions_value, list):
        raise ValueError("campaign result decisions must be a list")
    decisions = tuple(_decode_decision(value) for value in decisions_value)
    return FastCampaignDecisionResults(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        champion_version=document["champion_version"],
        champion_fingerprint_sha256=document["champion_fingerprint_sha256"],
        decisions=decisions,
        batch_fingerprint_sha256=document["batch_fingerprint_sha256"],
    )


def fast_campaign_result_to_paper_assessment(
    result: FastCampaignDecisionResult,
    *,
    assessment_version: str,
    strategy_family: str,
    strategy_version: str,
) -> FastPaperActionAssessment:
    if type(result) is not FastCampaignDecisionResult:
        raise ValueError("result must be an exact FastCampaignDecisionResult")
    try:
        action = FastPaperAction(result.action)
    except ValueError as exc:
        raise ValueError("campaign result action is incompatible with Fast PAPER") from exc
    horizon = (
        "selected_horizon_ms=none"
        if result.selected_horizon_ms is None
        else f"selected_horizon_ms={result.selected_horizon_ms}"
    )
    reasons = (
        result.reason,
        horizon,
        f"selected_value_bps={result.selected_value_bps:.17g}",
        f"target_exposure_fraction={result.target_exposure_fraction:.17g}",
    )
    return FastPaperActionAssessment(
        version=assessment_version,
        source_event_id=result.source_event_id,
        market_key=result.market_key,
        source_sequence=result.source_sequence,
        as_of_unix_ms=result.as_of_unix_ms,
        strategy_family=strategy_family,
        strategy_version=strategy_version,
        action=action,
        reasons=reasons,
    )


def _policy_document(policy: FastCampaignContinuousActionPolicy) -> dict[str, Any]:
    return {
        "version": policy.version,
        "horizons_ms": list(policy.horizons_ms),
        "entry_exposure_candidates": list(policy.entry_exposure_candidates),
        "reduce_target_exposure_candidates": list(
            policy.reduce_target_exposure_candidates
        ),
        "adverse_excursion_weight": policy.adverse_excursion_weight,
        "reversal_penalty_bps": policy.reversal_penalty_bps,
        "route_unavailability_penalty_bps": policy.route_unavailability_penalty_bps,
        "horizon_disagreement_weight": policy.horizon_disagreement_weight,
        "minimum_buy_value_bps": policy.minimum_buy_value_bps,
        "minimum_hold_value_bps": policy.minimum_hold_value_bps,
        "missing_forecast_open_action": policy.missing_forecast_open_action,
    }


def _request_document(request: FastCampaignDecisionRequest) -> dict[str, Any]:
    position: dict[str, Any]
    if request.position.kind == "FLAT":
        position = {"kind": "FLAT"}
    else:
        position = {
            "kind": "OPEN",
            "current_exposure_fraction": request.position.current_exposure_fraction,
        }
    return {
        "source_event_id": request.source_event_id,
        "market_key": request.market_key,
        "source_sequence": request.source_sequence,
        "as_of_unix_ms": request.as_of_unix_ms,
        "features": list(request.features),
        "position": position,
        "constraints": {
            "max_exposure_fraction": request.constraints.max_exposure_fraction,
            "buy_economically_allowed": request.constraints.buy_economically_allowed,
            "expected_future_exit_cost_bps": request.constraints.expected_future_exit_cost_bps,
            "reduce_execution_costs": [
                {
                    "target_exposure_fraction": value.target_exposure_fraction,
                    "execution_cost_bps": value.execution_cost_bps,
                }
                for value in request.constraints.reduce_execution_costs
            ],
            "sell_executable": request.constraints.sell_executable,
            "sell_now_cost_bps": request.constraints.sell_now_cost_bps,
            "force_sell": request.constraints.force_sell,
        },
    }


def _decode_decision(value: Any) -> FastCampaignDecisionResult:
    if not isinstance(value, dict):
        raise ValueError("campaign result decision must be an object")
    _require_exact_keys("campaign result decision", value, _DECISION_RESULT_KEYS)

    horizons_value = value["horizon_evidence"]
    candidates_value = value["candidates"]
    if not isinstance(horizons_value, list):
        raise ValueError("horizon_evidence must be a list")
    if not isinstance(candidates_value, list):
        raise ValueError("candidates must be a list")

    return FastCampaignDecisionResult(
        source_event_id=value["source_event_id"],
        market_key=value["market_key"],
        source_sequence=value["source_sequence"],
        as_of_unix_ms=value["as_of_unix_ms"],
        policy_version=value["policy_version"],
        action=value["action"],
        reason=value["reason"],
        selected_horizon_ms=value["selected_horizon_ms"],
        current_exposure_fraction=value["current_exposure_fraction"],
        target_exposure_fraction=value["target_exposure_fraction"],
        selected_reward_bps=value["selected_reward_bps"],
        selected_risk_bps=value["selected_risk_bps"],
        selected_execution_cost_bps=value["selected_execution_cost_bps"],
        selected_value_bps=value["selected_value_bps"],
        horizon_evidence=tuple(_decode_horizon(item) for item in horizons_value),
        candidates=tuple(_decode_candidate(item) for item in candidates_value),
    )


def _decode_horizon(value: Any) -> FastCampaignHorizonEvidence:
    if not isinstance(value, dict):
        raise ValueError("campaign horizon evidence must be an object")
    _require_exact_keys("campaign horizon evidence", value, _HORIZON_KEYS)
    return FastCampaignHorizonEvidence(**value)


def _decode_candidate(value: Any) -> FastCampaignActionCandidate:
    if not isinstance(value, dict):
        raise ValueError("campaign candidate must be an object")
    _require_exact_keys("campaign candidate", value, _CANDIDATE_KEYS)
    return FastCampaignActionCandidate(**value)


def _require_exact_keys(name: str, value: dict[str, Any], expected: frozenset[str]) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ValueError(
            f"{name} has unknown or missing fields: "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )


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
