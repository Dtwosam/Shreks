from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from shreks_brain.fast_paper import FastPaperAction, FastPaperActionAssessment

from .models import (
    FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME,
    FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION,
    FastDeterministicLifecycleDecision,
    FastDeterministicLifecyclePolicy,
    FastDeterministicLifecycleResults,
)


_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "policy",
        "decisions",
        "batch_fingerprint_sha256",
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
_ENTRY_KINDS = frozenset(
    {"IMPULSE_SCALP", "MICRO_PULLBACK", "PRE_GRADUATION", "GRADUATION_FLOW"}
)
_MANAGER_KINDS = frozenset({"WALLET_COHORT", "LONGER_RUNNER"})


def decode_fast_deterministic_lifecycle_results(
    payload: str,
) -> FastDeterministicLifecycleResults:
    if not isinstance(payload, str) or not payload:
        raise ValueError("deterministic lifecycle payload must be a non-empty string")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("deterministic lifecycle payload is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("deterministic lifecycle payload must be a JSON object")
    if payload != _canonical(document):
        raise ValueError("deterministic lifecycle payload must use canonical JSON")

    _require_exact_keys("deterministic lifecycle result", document, _TOP_KEYS)
    policy_value = document["policy"]
    decisions_value = document["decisions"]
    if not isinstance(policy_value, dict):
        raise ValueError("policy must be an object")
    if not isinstance(decisions_value, list) or not decisions_value:
        raise ValueError("decisions must be a non-empty list")

    _require_exact_keys("deterministic lifecycle policy", policy_value, _POLICY_KEYS)
    for value in decisions_value:
        if not isinstance(value, dict):
            raise ValueError("deterministic lifecycle decision must be an object")
        _require_exact_keys("deterministic lifecycle decision", value, _DECISION_KEYS)

    material = dict(document)
    claimed = material.pop("batch_fingerprint_sha256")
    expected = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    if claimed != expected:
        raise ValueError("deterministic lifecycle fingerprint mismatch")

    policy = FastDeterministicLifecyclePolicy(**policy_value)
    decisions = tuple(_decode_decision(value) for value in decisions_value)
    result = FastDeterministicLifecycleResults(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        policy=policy,
        decisions=decisions,
        batch_fingerprint_sha256=document["batch_fingerprint_sha256"],
    )
    _validate_semantics(result)
    return result


def fast_deterministic_lifecycle_to_paper_assessment(
    decision: FastDeterministicLifecycleDecision,
    *,
    assessment_version: str,
    strategy_family: str,
    strategy_version: str,
) -> FastPaperActionAssessment:
    if type(decision) is not FastDeterministicLifecycleDecision:
        raise ValueError("decision must be exact FastDeterministicLifecycleDecision")
    for name, value in (
        ("assessment_version", assessment_version),
        ("strategy_family", strategy_family),
        ("strategy_version", strategy_version),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    try:
        action = FastPaperAction(decision.action)
    except ValueError as exc:
        raise ValueError("lifecycle action is incompatible with Fast PAPER") from exc

    current = (
        "none"
        if decision.current_exposure_fraction is None
        else _number(decision.current_exposure_fraction)
    )
    reasons = (
        f"component_kind={decision.component_kind}",
        f"component_version={decision.component_version}",
        f"posture={decision.posture}",
        f"current_exposure_fraction={current}",
        f"target_exposure_fraction={_number(decision.target_exposure_fraction)}",
    )
    return FastPaperActionAssessment(
        version=assessment_version,
        source_event_id=decision.source_event_id,
        market_key=decision.market_key,
        source_sequence=decision.source_sequence,
        as_of_unix_ms=decision.as_of_unix_ms,
        strategy_family=strategy_family,
        strategy_version=strategy_version,
        action=action,
        reasons=reasons,
    )


def _decode_decision(value: Any) -> FastDeterministicLifecycleDecision:
    if not isinstance(value, dict):
        raise ValueError("deterministic lifecycle decision must be an object")
    _require_exact_keys("deterministic lifecycle decision", value, _DECISION_KEYS)
    return FastDeterministicLifecycleDecision(**value)


def _validate_semantics(results: FastDeterministicLifecycleResults) -> None:
    if results.schema_name != FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME:
        raise ValueError("unsupported deterministic lifecycle schema_name")
    if results.schema_version != FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION:
        raise ValueError("unsupported deterministic lifecycle schema_version")
    if results.policy.entry_baseline_kind not in _ENTRY_KINDS:
        raise ValueError("invalid entry baseline kind")
    if results.policy.manager_baseline_kind not in _MANAGER_KINDS:
        raise ValueError("invalid manager baseline kind")

    seen: set[str] = set()
    latest_by_market: dict[str, tuple[int, int]] = {}
    for decision in results.decisions:
        if decision.source_event_id in seen:
            raise ValueError("duplicate source_event_id")
        seen.add(decision.source_event_id)

        if decision.posture == "FLAT":
            if decision.component_kind != results.policy.entry_baseline_kind:
                raise ValueError("FLAT component kind must match entry baseline")
            if decision.current_exposure_fraction is not None:
                raise ValueError("FLAT current exposure must be null")
            if decision.action == "BUY":
                if not _nearly_equal(
                    decision.target_exposure_fraction,
                    results.policy.entry_target_exposure_fraction,
                ):
                    raise ValueError("BUY target exposure must match entry target")
            elif decision.action == "SKIP":
                if decision.target_exposure_fraction != 0.0:
                    raise ValueError("SKIP target exposure must be zero")
            else:
                raise ValueError("FLAT action must be BUY or SKIP")
        else:
            if decision.component_kind != results.policy.manager_baseline_kind:
                raise ValueError("OPEN component kind must match manager baseline")
            current = decision.current_exposure_fraction
            if current is None:
                raise ValueError("OPEN current exposure is required")
            if decision.action == "HOLD":
                if not _nearly_equal(decision.target_exposure_fraction, current):
                    raise ValueError("HOLD target exposure must equal current exposure")
            elif decision.action == "REDUCE":
                expected = current * results.policy.reduce_remaining_fraction
                if (
                    not math.isfinite(expected)
                    or expected <= 0.0
                    or expected >= current
                    or not _nearly_equal(decision.target_exposure_fraction, expected)
                ):
                    raise ValueError(
                        "REDUCE target exposure must match lifecycle remaining fraction"
                    )
            elif decision.action == "SELL":
                if decision.target_exposure_fraction != 0.0:
                    raise ValueError("SELL target exposure must be zero")
            else:
                raise ValueError("OPEN action must be HOLD, REDUCE, or SELL")

        previous = latest_by_market.get(decision.market_key)
        if previous is not None:
            if decision.source_sequence <= previous[0]:
                raise ValueError("per-market source sequence must strictly increase")
            if decision.as_of_unix_ms < previous[1]:
                raise ValueError("per-market timestamp cannot move backward")
        latest_by_market[decision.market_key] = (
            decision.source_sequence,
            decision.as_of_unix_ms,
        )


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


def _number(value: float) -> str:
    return json.dumps(
        float(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _nearly_equal(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
