from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from shreks_brain.fast_campaign_paper import FastDeterministicPaperPosture
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicCandidateManifest,
    FastDeterministicLifecycleDecision,
    FastDeterministicLifecyclePolicy,
    build_fast_deterministic_lifecycle_results,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
    FastTrainingLifecycleEvent,
    FastTrainingReserveContext,
    FastTrainingWindowSummary,
)

from .models import (
    FastOfflineEntryExecution,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineExecutionTrade,
    FastOfflineGraduationFlowEvidence,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerContinuation,
    FastOfflineLongerRunnerEvidence,
    FastOfflineMarketSnapshot,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineRowEvidence,
    FastOfflineWalletCohortEvidence,
    FastOfflineWalletCohortEvidencePayload,
    FastOfflineWalletCohortSideSummary,
)


FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_NAME = "shreks.fast_deterministic_row_request"
FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_VERSION = 1
FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_NAME = "shreks.fast_deterministic_row_result"
FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_VERSION = 1

_RESULT_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "candidate_version",
        "candidate_fingerprint_sha256",
        "lifecycle_policy",
        "decision",
        "result_fingerprint_sha256",
    }
)
_POLICY_KEYS = frozenset(
    {
        "version",
        "entry_baseline_kind",
        "manager_baseline_kind",
        "entry_target_exposure_fraction",
        "reduce_remaining_fraction",
    }
)
_DECISION_KEYS = frozenset(
    {
        "source_event_id",
        "market_key",
        "source_sequence",
        "as_of_unix_ms",
        "posture",
        "component_kind",
        "component_version",
        "action",
        "current_exposure_fraction",
        "target_exposure_fraction",
    }
)


def build_fast_deterministic_row_request(
    *,
    record: FastTrainingFeatureRecord,
    manifest: FastDeterministicCandidateManifest,
    posture: FastDeterministicPaperPosture,
    evidence: FastOfflineRowEvidence,
) -> str:
    _validate_inputs(record, manifest, posture, evidence)
    document = {
        "schema_name": FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_NAME,
        "schema_version": FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_VERSION,
        "manifest": _manifest_to_wire(manifest),
        "record": _record_to_wire(record),
        "posture": _posture_to_wire(posture),
        "evidence": _evidence_to_wire(evidence),
    }
    return _canonical(document)


def decode_fast_deterministic_row_result(
    payload: str,
    *,
    manifest: FastDeterministicCandidateManifest,
    record: FastTrainingFeatureRecord,
    posture: FastDeterministicPaperPosture,
) -> FastDeterministicLifecycleDecision:
    if not isinstance(payload, str) or not payload:
        raise ValueError("deterministic row result payload must be a non-empty string")
    if type(manifest) is not FastDeterministicCandidateManifest:
        raise ValueError("manifest must be exact FastDeterministicCandidateManifest")
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be exact FastTrainingFeatureRecord")
    if type(posture) is not FastDeterministicPaperPosture:
        raise ValueError("posture must be exact FastDeterministicPaperPosture")

    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("deterministic row result is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("deterministic row result must be a JSON object")
    _require_exact_keys("deterministic row result", document, _RESULT_KEYS)
    if payload != _rust_result_json(document):
        raise ValueError("deterministic row result must use canonical Rust wire JSON")

    policy_raw = _require_dict(document["lifecycle_policy"], "lifecycle_policy")
    decision_raw = _require_dict(document["decision"], "decision")
    _require_exact_keys("lifecycle_policy", policy_raw, _POLICY_KEYS)
    _require_exact_keys("decision", decision_raw, _DECISION_KEYS)

    claimed = document["result_fingerprint_sha256"]
    _require_sha256("result_fingerprint_sha256", claimed)
    material = dict(document)
    material.pop("result_fingerprint_sha256")
    expected = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    if claimed != expected:
        raise ValueError("deterministic row result fingerprint mismatch")

    if document["schema_name"] != FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_NAME:
        raise ValueError("unsupported deterministic row result schema_name")
    if document["schema_version"] != FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_VERSION:
        raise ValueError("unsupported deterministic row result schema_version")
    if document["candidate_version"] != manifest.candidate_version:
        raise ValueError("deterministic row result candidate version mismatch")
    if (
        document["candidate_fingerprint_sha256"]
        != manifest.candidate_fingerprint_sha256
    ):
        raise ValueError("deterministic row result candidate fingerprint mismatch")

    try:
        policy = FastDeterministicLifecyclePolicy(**policy_raw)
    except TypeError as exc:
        raise ValueError("deterministic row result lifecycle policy is invalid") from exc
    if policy != manifest.lifecycle_policy:
        raise ValueError("deterministic row result lifecycle policy mismatch")

    try:
        decision = FastDeterministicLifecycleDecision(**decision_raw)
    except TypeError as exc:
        raise ValueError("deterministic row result decision is invalid") from exc

    # Reuse sealed Python lifecycle semantic validation for the one returned decision.
    build_fast_deterministic_lifecycle_results(policy, (decision,))

    expected_source_event_id = (
        f"{record.decision_signature}:{record.decision_ordinal}"
    )
    expected_market_key = _record_market_key(record)
    if (
        decision.source_event_id != expected_source_event_id
        or decision.market_key != expected_market_key
        or decision.source_sequence != record.decision_sequence
        or decision.as_of_unix_ms != record.decision_observed_at_unix_ms
    ):
        raise ValueError("deterministic row result source/row identity mismatch")
    if decision.posture != posture.posture:
        raise ValueError("deterministic row result posture mismatch")
    if posture.posture == "OPEN":
        if (
            decision.current_exposure_fraction is None
            or posture.current_exposure_fraction is None
            or not math.isclose(
                decision.current_exposure_fraction,
                posture.current_exposure_fraction,
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(
                "deterministic row result OPEN exposure does not match PAPER posture"
            )
    elif decision.current_exposure_fraction is not None:
        raise ValueError("deterministic row result FLAT exposure must be null")
    return decision


def _validate_inputs(
    record: FastTrainingFeatureRecord,
    manifest: FastDeterministicCandidateManifest,
    posture: FastDeterministicPaperPosture,
    evidence: FastOfflineRowEvidence,
) -> None:
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be exact FastTrainingFeatureRecord")
    if type(manifest) is not FastDeterministicCandidateManifest:
        raise ValueError("manifest must be exact FastDeterministicCandidateManifest")
    if type(posture) is not FastDeterministicPaperPosture:
        raise ValueError("posture must be exact FastDeterministicPaperPosture")
    allowed_types = (
        FastOfflineImpulseScalpEvidence,
        FastOfflineMicroPullbackEvidence,
        FastOfflinePreGraduationEvidence,
        FastOfflineGraduationFlowEvidence,
        FastOfflineWalletCohortEvidence,
        FastOfflineLongerRunnerEvidence,
    )
    if type(evidence) not in allowed_types:
        raise ValueError("evidence must be an exact supported offline row evidence type")

    expected_market = _record_market_key(record)
    if posture.market_key != expected_market:
        raise ValueError("PAPER posture market key does not match FL8.1 row market")

    expected_kind = (
        manifest.lifecycle_policy.entry_baseline_kind
        if posture.posture == "FLAT"
        else manifest.lifecycle_policy.manager_baseline_kind
    )
    if evidence.kind != expected_kind:
        raise ValueError(
            "offline evidence family does not match manifest-selected posture component"
        )
    if posture.posture == "OPEN":
        if posture.current_exposure_fraction is None or posture.opened_at_unix_ms is None:
            raise ValueError("OPEN PAPER posture is incomplete")
        if posture.opened_at_unix_ms > record.decision_observed_at_unix_ms:
            raise ValueError("OPEN PAPER position cannot open after decision row")


def _manifest_to_wire(manifest: FastDeterministicCandidateManifest) -> dict[str, object]:
    return {
        "schema_name": manifest.schema_name,
        "schema_version": manifest.schema_version,
        "candidate_version": manifest.candidate_version,
        "strategy_family": manifest.strategy_family,
        "strategy_version": manifest.strategy_version,
        "lifecycle_policy": _policy_to_wire(manifest.lifecycle_policy),
        "entry_policy": {
            "kind": manifest.entry_policy.kind,
            "parameters": dict(manifest.entry_policy.parameters),
        },
        "manager_policy": {
            "kind": manifest.manager_policy.kind,
            "parameters": dict(manifest.manager_policy.parameters),
        },
        "candidate_fingerprint_sha256": manifest.candidate_fingerprint_sha256,
    }


def _policy_to_wire(policy: FastDeterministicLifecyclePolicy) -> dict[str, object]:
    return {
        "version": policy.version,
        "entry_baseline_kind": policy.entry_baseline_kind,
        "manager_baseline_kind": policy.manager_baseline_kind,
        "entry_target_exposure_fraction": policy.entry_target_exposure_fraction,
        "reduce_remaining_fraction": policy.reduce_remaining_fraction,
    }


def _record_to_wire(record: FastTrainingFeatureRecord) -> dict[str, object]:
    return {
        "schema_name": record.schema_name,
        "schema_version": record.schema_version,
        "decision_signature": record.decision_signature,
        "decision_ordinal": record.decision_ordinal,
        "decision_sequence": record.decision_sequence,
        "mint": record.mint,
        "quote_mint": record.quote_mint,
        "venue": record.venue,
        "decision_observed_at_unix_ms": record.decision_observed_at_unix_ms,
        "decision_provider": record.decision_provider,
        "decision_source_observed_at_unix_ms": (
            record.decision_source_observed_at_unix_ms
        ),
        "decision_occurred_at_unix_ms": record.decision_occurred_at_unix_ms,
        "decision_slot": record.decision_slot,
        "decision_event_kind": record.decision_event_kind,
        "decision_actor": record.decision_actor,
        "decision_executable_entry_price_quote": (
            record.decision_executable_entry_price_quote
        ),
        "decision_entry_total_quote": record.decision_entry_total_quote,
        "snapshot_as_of_unix_ms": record.snapshot_as_of_unix_ms,
        "snapshot_last_sequence": record.snapshot_last_sequence,
        "snapshot_last_price_quote": record.snapshot_last_price_quote,
        "last_reserve_context": _reserve_to_wire(record.last_reserve_context),
        "last_lifecycle_event": _lifecycle_to_wire(record.last_lifecycle_event),
        "windows": [_window_to_wire(value) for value in record.windows],
    }


def _reserve_to_wire(
    value: FastTrainingReserveContext | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is not FastTrainingReserveContext:
        raise ValueError(
            "last_reserve_context must be exact FastTrainingReserveContext or None"
        )
    if value.kind == "pump_curve":
        required = {
            "virtual_base_reserve_raw": value.virtual_base_reserve_raw,
            "virtual_quote_reserve_raw": value.virtual_quote_reserve_raw,
            "real_base_reserve_raw": value.real_base_reserve_raw,
            "real_quote_reserve_raw": value.real_quote_reserve_raw,
        }
        if any(item is None for item in required.values()):
            raise ValueError("pump_curve reserve context is incomplete")
        return {
            "kind": "pump_curve",
            **required,
            "base_decimals": value.base_decimals,
            "quote_decimals": value.quote_decimals,
        }
    if value.kind == "pump_swap_pool":
        if value.pool_base_reserve_raw is None or value.pool_quote_reserve_raw is None:
            raise ValueError("pump_swap_pool reserve context is incomplete")
        return {
            "kind": "pump_swap_pool",
            "pool_base_reserve_raw": value.pool_base_reserve_raw,
            "pool_quote_reserve_raw": value.pool_quote_reserve_raw,
            "virtual_quote_reserve_raw": value.virtual_quote_reserve_raw,
            "base_decimals": value.base_decimals,
            "quote_decimals": value.quote_decimals,
        }
    raise ValueError("unsupported FL8.1 reserve context kind")


def _lifecycle_to_wire(
    value: FastTrainingLifecycleEvent | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is not FastTrainingLifecycleEvent:
        raise ValueError(
            "last_lifecycle_event must be exact FastTrainingLifecycleEvent or None"
        )
    return {
        "kind": value.kind,
        "provider": value.provider,
        "mint": value.mint,
        "quote_mint": value.quote_mint,
        "from_venue": value.from_venue,
        "to_venue": value.to_venue,
        "pool_address": value.pool_address,
        "signature": value.signature,
        "slot": value.slot,
        "detected_at_unix_ms": value.detected_at_unix_ms,
        "occurred_at_unix_ms": value.occurred_at_unix_ms,
    }


def _window_to_wire(value: FastTrainingWindowSummary) -> dict[str, object]:
    if type(value) is not FastTrainingWindowSummary:
        raise ValueError("windows must contain exact FastTrainingWindowSummary values")
    return {
        "window_ms": value.window_ms,
        "buy_count": value.buy_count,
        "sell_count": value.sell_count,
        "unique_buy_actors": value.unique_buy_actors,
        "unique_sell_actors": value.unique_sell_actors,
        "buy_arrival_rate_per_second": value.buy_arrival_rate_per_second,
        "sell_arrival_rate_per_second": value.sell_arrival_rate_per_second,
        "count_imbalance": value.count_imbalance,
        "buy_base_quantity": value.buy_base_quantity,
        "sell_base_quantity": value.sell_base_quantity,
        "buy_quote_quantity": value.buy_quote_quantity,
        "sell_quote_quantity": value.sell_quote_quantity,
        "net_quote_quantity": value.net_quote_quantity,
        "quote_flow_imbalance": value.quote_flow_imbalance,
        "quote_flow_velocity_per_second": value.quote_flow_velocity_per_second,
        "quote_flow_acceleration_per_second2": (
            value.quote_flow_acceleration_per_second2
        ),
        "local_high_price_quote": value.local_high_price_quote,
        "local_high_sequence": value.local_high_sequence,
        "local_high_observed_at_unix_ms": value.local_high_observed_at_unix_ms,
        "local_low_price_quote": value.local_low_price_quote,
        "local_low_sequence": value.local_low_sequence,
        "local_low_observed_at_unix_ms": value.local_low_observed_at_unix_ms,
        "post_high_low_price_quote": value.post_high_low_price_quote,
        "post_high_low_sequence": value.post_high_low_sequence,
        "post_high_low_observed_at_unix_ms": (
            value.post_high_low_observed_at_unix_ms
        ),
        "last_price_quote": value.last_price_quote,
        "drawdown_from_local_high": value.drawdown_from_local_high,
        "recovery_from_local_low": value.recovery_from_local_low,
    }


def _posture_to_wire(posture: FastDeterministicPaperPosture) -> dict[str, object]:
    if posture.posture == "FLAT":
        return {"kind": "FLAT"}
    assert posture.current_exposure_fraction is not None
    assert posture.opened_at_unix_ms is not None
    return {
        "kind": "OPEN",
        "current_exposure_fraction": posture.current_exposure_fraction,
        "opened_at_unix_ms": posture.opened_at_unix_ms,
    }


def _evidence_to_wire(evidence: FastOfflineRowEvidence) -> dict[str, object]:
    if isinstance(
        evidence,
        (
            FastOfflineImpulseScalpEvidence,
            FastOfflineMicroPullbackEvidence,
            FastOfflinePreGraduationEvidence,
        ),
    ):
        return {
            "kind": evidence.kind,
            "execution": _entry_execution_to_wire(evidence.execution),
        }
    if type(evidence) is FastOfflineGraduationFlowEvidence:
        return {
            "kind": evidence.kind,
            "pre_snapshot": _snapshot_to_wire(evidence.pre_snapshot),
            "boost_context": evidence.boost_context,
            "execution": _entry_execution_to_wire(evidence.execution),
        }
    if type(evidence) is FastOfflineWalletCohortEvidence:
        return {
            "kind": evidence.kind,
            "evidence": _wallet_payload_to_wire(evidence.evidence),
        }
    if type(evidence) is FastOfflineLongerRunnerEvidence:
        return {
            "kind": evidence.kind,
            "protective": {
                "hard_stop_triggered": evidence.protective.hard_stop_triggered,
                "risk_limit_exit_required": (
                    evidence.protective.risk_limit_exit_required
                ),
                "liquidity_exit_required": (
                    evidence.protective.liquidity_exit_required
                ),
            },
            "continuation": _continuation_to_wire(evidence.continuation),
        }
    raise ValueError("unsupported offline row evidence")


def _entry_execution_to_wire(
    value: FastOfflineEntryExecution | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is not FastOfflineEntryExecution:
        raise ValueError("execution must be exact FastOfflineEntryExecution or None")
    return {
        "cost_model": _cost_model_to_wire(value.cost_model),
        "trade": _trade_to_wire(value.trade),
    }


def _cost_model_to_wire(value: FastOfflineExecutionCostModel) -> dict[str, object]:
    return {
        "version": value.version,
        "entry": _leg_to_wire(value.entry),
        "exit": _leg_to_wire(value.exit),
    }


def _leg_to_wire(value: FastOfflineExecutionLegCost) -> dict[str, object]:
    return {
        "effective_fee_bps": value.effective_fee_bps,
        "expected_impact_bps": value.expected_impact_bps,
        "expected_slippage_bps": value.expected_slippage_bps,
        "expected_latency_bps": value.expected_latency_bps,
        "network_fee_quote": value.network_fee_quote,
        "priority_fee_quote": value.priority_fee_quote,
        "expected_failure_cost_quote": value.expected_failure_cost_quote,
    }


def _trade_to_wire(value: FastOfflineExecutionTrade) -> dict[str, object]:
    return {
        "base_quantity": value.base_quantity,
        "executable_entry_price_quote": value.executable_entry_price_quote,
        "forecast_exit_price_quote": value.forecast_exit_price_quote,
        "exit_capacity_base": value.exit_capacity_base,
        "required_edge_bps": value.required_edge_bps,
        "risk_margin_bps": value.risk_margin_bps,
    }


def _snapshot_to_wire(value: FastOfflineMarketSnapshot) -> dict[str, object]:
    return {
        "mint": value.mint,
        "quote_mint": value.quote_mint,
        "venue": value.venue,
        "as_of_unix_ms": value.as_of_unix_ms,
        "last_sequence": value.last_sequence,
        "last_price_quote": value.last_price_quote,
        "last_reserve_context": _reserve_to_wire(value.last_reserve_context),
        "last_lifecycle_event": _lifecycle_to_wire(value.last_lifecycle_event),
        "windows": [_window_to_wire(item) for item in value.windows],
    }


def _wallet_side_to_wire(
    value: FastOfflineWalletCohortSideSummary,
) -> dict[str, object]:
    return {
        "strong_wallet_count": value.strong_wallet_count,
        "confidence_weighted_strong_count": value.confidence_weighted_strong_count,
        "independently_strong_wallet_count": value.independently_strong_wallet_count,
        "all_pairs_independent_under_evidence": (
            value.all_pairs_independent_under_evidence
        ),
    }


def _wallet_payload_to_wire(
    value: FastOfflineWalletCohortEvidencePayload | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "version": value.version,
        "wallet_feature_policy_version": value.wallet_feature_policy_version,
        "profile_policy_version": value.profile_policy_version,
        "relationship_policy_version": value.relationship_policy_version,
        "support": _wallet_side_to_wire(value.support),
        "exits": _wallet_side_to_wire(value.exits),
        "support_hold_horizon_wallet_weight": (
            value.support_hold_horizon_wallet_weight
        ),
        "confidence_weighted_support_median_hold_ms": (
            value.confidence_weighted_support_median_hold_ms
        ),
    }


def _continuation_to_wire(
    value: FastOfflineLongerRunnerContinuation | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "version": value.version,
        "forecast_source_version": value.forecast_source_version,
        "forecast_horizon_ms": value.forecast_horizon_ms,
        "base_quantity": value.base_quantity,
        "current_executable_exit_price_quote": (
            value.current_executable_exit_price_quote
        ),
        "expected_future_exit_price_quote": value.expected_future_exit_price_quote,
        "downside_exit_price_quote": value.downside_exit_price_quote,
        "current_exit_capacity_base": value.current_exit_capacity_base,
        "expected_future_exit_capacity_base": value.expected_future_exit_capacity_base,
        "expected_holding_cost_quote": value.expected_holding_cost_quote,
        "current_exit_costs": _leg_to_wire(value.current_exit_costs),
        "future_exit_costs": _leg_to_wire(value.future_exit_costs),
    }


def _record_market_key(record: FastTrainingFeatureRecord) -> str:
    return f"{record.venue}:{record.mint}:{record.quote_mint}"


def _require_exact_keys(
    name: str,
    value: dict[str, Any],
    expected: frozenset[str],
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ValueError(
            f"{name} has unknown or missing fields: "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )


def _require_dict(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _rust_result_json(document: dict[str, Any]) -> str:
    policy = _require_dict(document["lifecycle_policy"], "lifecycle_policy")
    decision = _require_dict(document["decision"], "decision")
    ordered = {
        "schema_name": document["schema_name"],
        "schema_version": document["schema_version"],
        "candidate_version": document["candidate_version"],
        "candidate_fingerprint_sha256": document["candidate_fingerprint_sha256"],
        "lifecycle_policy": {
            "version": policy["version"],
            "entry_baseline_kind": policy["entry_baseline_kind"],
            "manager_baseline_kind": policy["manager_baseline_kind"],
            "entry_target_exposure_fraction": policy[
                "entry_target_exposure_fraction"
            ],
            "reduce_remaining_fraction": policy["reduce_remaining_fraction"],
        },
        "decision": {
            "source_event_id": decision["source_event_id"],
            "market_key": decision["market_key"],
            "source_sequence": decision["source_sequence"],
            "as_of_unix_ms": decision["as_of_unix_ms"],
            "posture": decision["posture"],
            "component_kind": decision["component_kind"],
            "component_version": decision["component_version"],
            "action": decision["action"],
            "current_exposure_fraction": decision["current_exposure_fraction"],
            "target_exposure_fraction": decision["target_exposure_fraction"],
        },
        "result_fingerprint_sha256": document["result_fingerprint_sha256"],
    }
    return json.dumps(
        ordered,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
