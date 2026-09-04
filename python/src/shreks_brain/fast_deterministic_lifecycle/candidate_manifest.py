from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import (
    FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME,
    FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION,
    FAST_DETERMINISTIC_CANDIDATE_STRATEGY_FAMILY,
    FastDeterministicCandidateManifest,
    FastDeterministicComponentPolicy,
    FastDeterministicLifecyclePolicy,
)


_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "candidate_version",
        "strategy_family",
        "strategy_version",
        "lifecycle_policy",
        "entry_policy",
        "manager_policy",
        "candidate_fingerprint_sha256",
    }
)
_LIFECYCLE_KEYS = frozenset(
    {
        "version",
        "entry_baseline_kind",
        "manager_baseline_kind",
        "entry_target_exposure_fraction",
        "reduce_remaining_fraction",
    }
)
_COMPONENT_KEYS = frozenset({"kind", "parameters"})
_ENTRY_KINDS = frozenset(
    {"IMPULSE_SCALP", "MICRO_PULLBACK", "PRE_GRADUATION", "GRADUATION_FLOW"}
)
_MANAGER_KINDS = frozenset({"WALLET_COHORT", "LONGER_RUNNER"})
_EXPECTED_PARAMETER_KEYS = {
    "IMPULSE_SCALP": frozenset(
        {
            "version",
            "signal_window_ms",
            "context_window_ms",
            "min_buy_count",
            "min_unique_buy_actors",
            "min_count_imbalance",
            "min_quote_flow_imbalance",
            "min_quote_flow_velocity_per_second",
            "min_quote_flow_acceleration_per_second2",
            "min_velocity_expansion_ratio",
            "min_recovery_from_local_low",
            "max_drawdown_from_local_high",
        }
    ),
    "MICRO_PULLBACK": frozenset(
        {
            "version",
            "reclaim_window_ms",
            "structure_window_ms",
            "min_impulse_move_fraction",
            "min_pullback_depth_fraction",
            "max_pullback_depth_fraction",
            "min_reclaim_fraction",
            "min_reclaim_buy_count",
            "min_reclaim_unique_buy_actors",
            "min_reclaim_buy_arrival_rate_per_second",
            "max_reclaim_sell_arrival_rate_per_second",
            "min_reclaim_count_imbalance",
            "min_reclaim_quote_flow_imbalance",
            "min_reclaim_quote_flow_velocity_per_second",
            "min_reclaim_quote_flow_acceleration_per_second2",
        }
    ),
    "PRE_GRADUATION": frozenset(
        {
            "version",
            "signal_window_ms",
            "context_window_ms",
            "graduation_target_real_base_reserve_raw",
            "maximum_pre_graduation_real_base_reserve_raw",
            "min_buy_count",
            "min_unique_buy_actors",
            "min_buy_arrival_rate_per_second",
            "min_count_imbalance",
            "min_quote_flow_imbalance",
            "min_quote_flow_velocity_per_second",
            "min_quote_flow_acceleration_per_second2",
            "min_velocity_expansion_ratio",
            "min_buy_participation_of_remaining",
        }
    ),
    "GRADUATION_FLOW": frozenset(
        {
            "version",
            "flow_window_ms",
            "max_graduation_age_ms",
            "min_pre_buy_count",
            "min_pre_quote_flow_velocity_per_second",
            "min_post_buy_count",
            "min_post_unique_buy_actors",
            "min_post_buy_arrival_rate_per_second",
            "max_post_sell_arrival_rate_per_second",
            "min_post_count_imbalance",
            "min_post_quote_flow_imbalance",
            "min_post_quote_flow_velocity_per_second",
            "min_post_quote_flow_acceleration_per_second2",
            "min_post_to_pre_velocity_ratio",
        }
    ),
    "WALLET_COHORT": frozenset(
        {
            "version",
            "min_support_wallet_count_for_ride",
            "min_confidence_weighted_support_for_ride",
            "min_independent_support_wallet_count_for_ride",
            "min_hold_horizon_wallet_weight_for_ride",
            "reduce_after_median_hold_ratio",
            "min_confidence_weighted_exit_for_reduce",
            "min_exit_pressure_ratio_for_reduce",
            "min_confidence_weighted_exit_for_sell",
            "min_exit_pressure_ratio_for_sell",
            "min_independent_exit_wallet_count_for_sell",
        }
    ),
    "LONGER_RUNNER": frozenset(
        {
            "version",
            "downside_risk_weight",
            "min_risk_adjusted_continuation_bps_for_hold",
            "max_risk_adjusted_continuation_bps_for_sell",
        }
    ),
}
_BASELINE_VERSIONS = {kind: 1 for kind in _EXPECTED_PARAMETER_KEYS}


def decode_fast_deterministic_candidate_manifest(
    payload: str,
) -> FastDeterministicCandidateManifest:
    if not isinstance(payload, str) or not payload:
        raise ValueError("deterministic candidate manifest payload must be a non-empty string")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("deterministic candidate manifest is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("deterministic candidate manifest must be a JSON object")
    if payload != _canonical(document):
        raise ValueError("deterministic candidate manifest must use canonical JSON")

    _require_exact_keys("deterministic candidate manifest", document, _TOP_KEYS)
    lifecycle_value = _require_dict(document["lifecycle_policy"], "lifecycle_policy")
    entry_value = _require_dict(document["entry_policy"], "entry_policy")
    manager_value = _require_dict(document["manager_policy"], "manager_policy")
    _require_exact_keys("lifecycle_policy", lifecycle_value, _LIFECYCLE_KEYS)
    _validate_component_structure(entry_value, "entry_policy")
    _validate_component_structure(manager_value, "manager_policy")

    material = dict(document)
    claimed = material.pop("candidate_fingerprint_sha256")
    expected = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    if claimed != expected:
        raise ValueError("deterministic candidate manifest fingerprint mismatch")

    lifecycle_policy = FastDeterministicLifecyclePolicy(**lifecycle_value)
    entry_policy = FastDeterministicComponentPolicy(
        kind=entry_value["kind"],
        parameters=entry_value["parameters"],
    )
    manager_policy = FastDeterministicComponentPolicy(
        kind=manager_value["kind"],
        parameters=manager_value["parameters"],
    )
    manifest = FastDeterministicCandidateManifest(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        candidate_version=document["candidate_version"],
        strategy_family=document["strategy_family"],
        strategy_version=document["strategy_version"],
        lifecycle_policy=lifecycle_policy,
        entry_policy=entry_policy,
        manager_policy=manager_policy,
        candidate_fingerprint_sha256=document["candidate_fingerprint_sha256"],
    )
    _validate_manifest_semantics(manifest)
    return manifest


def _validate_component_structure(value: dict[str, Any], name: str) -> None:
    _require_exact_keys(name, value, _COMPONENT_KEYS)
    kind = value["kind"]
    if not isinstance(kind, str) or kind not in _EXPECTED_PARAMETER_KEYS:
        raise ValueError(f"{name} kind is unsupported")
    parameters = _require_dict(value["parameters"], f"{name}.parameters")
    _require_exact_keys(
        f"{name}.parameters",
        parameters,
        _EXPECTED_PARAMETER_KEYS[kind],
    )
    for field, scalar in parameters.items():
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float)):
            raise ValueError(f"{name}.parameters must contain only numeric values")
        if isinstance(scalar, float) and not __import__("math").isfinite(scalar):
            raise ValueError(f"{name}.parameters must be finite")
    version = parameters["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"{name}.parameters.version must be an integer")
    if version != _BASELINE_VERSIONS[kind]:
        raise ValueError(f"{name} version does not match sealed FL6 baseline version")


def _validate_manifest_semantics(manifest: FastDeterministicCandidateManifest) -> None:
    if manifest.schema_name != FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME:
        raise ValueError("unsupported deterministic candidate manifest schema_name")
    if manifest.schema_version != FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported deterministic candidate manifest schema_version")
    if manifest.strategy_family != FAST_DETERMINISTIC_CANDIDATE_STRATEGY_FAMILY:
        raise ValueError("unsupported deterministic candidate strategy_family")
    if manifest.lifecycle_policy.version != 1:
        raise ValueError("unsupported deterministic lifecycle policy version")
    if manifest.lifecycle_policy.entry_baseline_kind not in _ENTRY_KINDS:
        raise ValueError("lifecycle entry kind must be an FL6.1-FL6.4 family")
    if manifest.lifecycle_policy.manager_baseline_kind not in _MANAGER_KINDS:
        raise ValueError("lifecycle manager kind must be an FL6.5-FL6.6 family")
    if manifest.entry_policy.kind != manifest.lifecycle_policy.entry_baseline_kind:
        raise ValueError("entry policy kind does not match lifecycle entry kind")
    if manifest.manager_policy.kind != manifest.lifecycle_policy.manager_baseline_kind:
        raise ValueError("manager policy kind does not match lifecycle manager kind")


def _require_dict(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


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


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
