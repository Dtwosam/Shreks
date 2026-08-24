from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any

from .models import (
    CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
    ChampionChallengerRegistry,
    RegistryCandidate,
    RegistryEvaluationEvidence,
    RegistryStatus,
    RegistryStatusEvent,
)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def candidate_to_dict(
    candidate: RegistryCandidate, *, include_fingerprint: bool = True
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": candidate.schema_version,
        "candidate_version": candidate.candidate_version,
        "strategy_version": candidate.strategy_version,
        "model_version": candidate.model_version,
        "model_training_schema_version": candidate.model_training_schema_version,
        "model_training_fingerprint_sha256": candidate.model_training_fingerprint_sha256,
        "feature_schema_version": candidate.feature_schema_version,
        "feature_columns": list(candidate.feature_columns),
        "training_started_at_unix_ms": candidate.training_started_at_unix_ms,
        "training_ended_at_unix_ms": candidate.training_ended_at_unix_ms,
        "validation_schema_version": candidate.validation_schema_version,
        "validation_policy_version": candidate.validation_policy_version,
        "validation_run_fingerprint_sha256": candidate.validation_run_fingerprint_sha256,
        "evaluation": evaluation_to_dict(candidate.evaluation),
        "registered_at_unix_ms": candidate.registered_at_unix_ms,
        "initial_status": candidate.initial_status.value,
    }
    if include_fingerprint:
        result["candidate_fingerprint_sha256"] = candidate.candidate_fingerprint_sha256
    return result


def evaluation_to_dict(evidence: RegistryEvaluationEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "policy_version": evidence.policy_version,
        "evaluation_fingerprint_sha256": evidence.evaluation_fingerprint_sha256,
        "trade_count": evidence.trade_count,
        "net_pnl_usd": evidence.net_pnl_usd,
        "net_expectancy_usd": evidence.net_expectancy_usd,
        "net_expectancy_pct": evidence.net_expectancy_pct,
        "profit_factor": evidence.profit_factor,
        "maximum_drawdown_usd": evidence.maximum_drawdown_usd,
        "maximum_drawdown_pct": evidence.maximum_drawdown_pct,
        "win_rate": evidence.win_rate,
        "turnover_usd": evidence.turnover_usd,
        "total_cost_usd": evidence.total_cost_usd,
        "brier_score": evidence.brier_score,
        "expected_calibration_error": evidence.expected_calibration_error,
    }


def event_to_dict(
    event: RegistryStatusEvent, *, include_fingerprint: bool = True
) -> dict[str, object]:
    result: dict[str, object] = {
        "candidate_version": event.candidate_version,
        "from_status": event.from_status.value,
        "to_status": event.to_status.value,
        "decision_reference": event.decision_reference,
        "decided_at_unix_ms": event.decided_at_unix_ms,
        "reason": event.reason,
    }
    if include_fingerprint:
        result["event_fingerprint_sha256"] = event.event_fingerprint_sha256
    return result


def registry_to_dict(
    registry: ChampionChallengerRegistry, *, include_fingerprint: bool = True
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": registry.schema_version,
        "candidates": [candidate_to_dict(value) for value in registry.candidates],
        "status_events": [event_to_dict(value) for value in registry.status_events],
    }
    if include_fingerprint:
        result["registry_fingerprint_sha256"] = registry.registry_fingerprint_sha256
    return result


def compute_candidate_fingerprint(candidate: RegistryCandidate) -> str:
    return _sha256(candidate_to_dict(candidate, include_fingerprint=False))


def compute_event_fingerprint(event: RegistryStatusEvent) -> str:
    return _sha256(event_to_dict(event, include_fingerprint=False))


def compute_registry_fingerprint(registry: ChampionChallengerRegistry) -> str:
    return _sha256(registry_to_dict(registry, include_fingerprint=False))


def build_registry(
    candidates: tuple[RegistryCandidate, ...],
    status_events: tuple[RegistryStatusEvent, ...],
) -> ChampionChallengerRegistry:
    ordered_candidates = tuple(sorted(candidates, key=lambda value: value.candidate_version))
    ordered_events = tuple(
        sorted(
            status_events,
            key=lambda value: (
                value.decided_at_unix_ms,
                value.candidate_version,
                value.event_fingerprint_sha256,
            ),
        )
    )
    draft = ChampionChallengerRegistry(
        schema_version=CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
        candidates=ordered_candidates,
        status_events=ordered_events,
        registry_fingerprint_sha256="0" * 64,
    )
    return replace(draft, registry_fingerprint_sha256=compute_registry_fingerprint(draft))


def decode_registry_document(value: object) -> ChampionChallengerRegistry:
    document = _exact_dict(
        value,
        {
            "schema_version",
            "candidates",
            "status_events",
            "registry_fingerprint_sha256",
        },
        "registry",
    )
    raw_candidates = _list(document["candidates"], "candidates")
    raw_events = _list(document["status_events"], "status_events")
    candidates = tuple(_decode_candidate(value) for value in raw_candidates)
    events = tuple(_decode_event(value) for value in raw_events)
    registry = ChampionChallengerRegistry(
        schema_version=_string(document["schema_version"], "schema_version"),
        candidates=candidates,
        status_events=events,
        registry_fingerprint_sha256=_string(
            document["registry_fingerprint_sha256"], "registry_fingerprint_sha256"
        ),
    )
    actual = compute_registry_fingerprint(registry)
    if actual != registry.registry_fingerprint_sha256:
        raise ValueError("registry fingerprint does not match persisted content")
    return registry


def _decode_candidate(value: object) -> RegistryCandidate:
    data = _exact_dict(
        value,
        {
            "schema_version",
            "candidate_version",
            "strategy_version",
            "model_version",
            "model_training_schema_version",
            "model_training_fingerprint_sha256",
            "feature_schema_version",
            "feature_columns",
            "training_started_at_unix_ms",
            "training_ended_at_unix_ms",
            "validation_schema_version",
            "validation_policy_version",
            "validation_run_fingerprint_sha256",
            "evaluation",
            "registered_at_unix_ms",
            "initial_status",
            "candidate_fingerprint_sha256",
        },
        "candidate",
    )
    candidate = RegistryCandidate(
        schema_version=_string(data["schema_version"], "candidate.schema_version"),
        candidate_version=_string(data["candidate_version"], "candidate_version"),
        strategy_version=_string(data["strategy_version"], "strategy_version"),
        model_version=_optional_string(data["model_version"], "model_version"),
        model_training_schema_version=_optional_string(
            data["model_training_schema_version"], "model_training_schema_version"
        ),
        model_training_fingerprint_sha256=_optional_string(
            data["model_training_fingerprint_sha256"],
            "model_training_fingerprint_sha256",
        ),
        feature_schema_version=_string(
            data["feature_schema_version"], "feature_schema_version"
        ),
        feature_columns=tuple(
            _string(item, "feature column")
            for item in _list(data["feature_columns"], "feature_columns")
        ),
        training_started_at_unix_ms=_optional_int(
            data["training_started_at_unix_ms"], "training_started_at_unix_ms"
        ),
        training_ended_at_unix_ms=_optional_int(
            data["training_ended_at_unix_ms"], "training_ended_at_unix_ms"
        ),
        validation_schema_version=_optional_string(
            data["validation_schema_version"], "validation_schema_version"
        ),
        validation_policy_version=_optional_string(
            data["validation_policy_version"], "validation_policy_version"
        ),
        validation_run_fingerprint_sha256=_optional_string(
            data["validation_run_fingerprint_sha256"],
            "validation_run_fingerprint_sha256",
        ),
        evaluation=_decode_evaluation(data["evaluation"]),
        registered_at_unix_ms=_int(data["registered_at_unix_ms"], "registered_at_unix_ms"),
        initial_status=_status(data["initial_status"], "initial_status"),
        candidate_fingerprint_sha256=_string(
            data["candidate_fingerprint_sha256"], "candidate_fingerprint_sha256"
        ),
    )
    actual = compute_candidate_fingerprint(candidate)
    if actual != candidate.candidate_fingerprint_sha256:
        raise ValueError(
            f"candidate fingerprint does not match persisted content for {candidate.candidate_version}"
        )
    return candidate


def _decode_evaluation(value: object) -> RegistryEvaluationEvidence:
    fields = {
        "schema_version",
        "policy_version",
        "evaluation_fingerprint_sha256",
        "trade_count",
        "net_pnl_usd",
        "net_expectancy_usd",
        "net_expectancy_pct",
        "profit_factor",
        "maximum_drawdown_usd",
        "maximum_drawdown_pct",
        "win_rate",
        "turnover_usd",
        "total_cost_usd",
        "brier_score",
        "expected_calibration_error",
    }
    data = _exact_dict(value, fields, "evaluation")
    return RegistryEvaluationEvidence(**data)  # type: ignore[arg-type]


def _decode_event(value: object) -> RegistryStatusEvent:
    data = _exact_dict(
        value,
        {
            "candidate_version",
            "from_status",
            "to_status",
            "decision_reference",
            "decided_at_unix_ms",
            "reason",
            "event_fingerprint_sha256",
        },
        "status event",
    )
    event = RegistryStatusEvent(
        candidate_version=_string(data["candidate_version"], "candidate_version"),
        from_status=_status(data["from_status"], "from_status"),
        to_status=_status(data["to_status"], "to_status"),
        decision_reference=_string(data["decision_reference"], "decision_reference"),
        decided_at_unix_ms=_int(data["decided_at_unix_ms"], "decided_at_unix_ms"),
        reason=_string(data["reason"], "reason"),
        event_fingerprint_sha256=_string(
            data["event_fingerprint_sha256"], "event_fingerprint_sha256"
        ),
    )
    actual = compute_event_fingerprint(event)
    if actual != event.event_fingerprint_sha256:
        raise ValueError("status event fingerprint does not match persisted content")
    return event


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _exact_dict(value: object, keys: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} must contain exactly the expected fields")
    return value


def _list(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _optional_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _int(value, name)


def _status(value: object, name: str) -> RegistryStatus:
    raw = _string(value, name)
    try:
        return RegistryStatus(raw)
    except ValueError as error:
        raise ValueError(f"{name} is not a known RegistryStatus") from error
