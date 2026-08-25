from __future__ import annotations

import json
import math
import string
from typing import Mapping

from .engine import evaluate_trading_performance
from .evidence import TradingEvaluationEvidence
from .models import EvaluatedTrade, ProbabilityObservation, TradingEvaluationPolicy


EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION = "e10-evaluation-evidence-v1"

_DOCUMENT_FIELDS = frozenset({"schema_version", "evaluations"})
_EVALUATION_FIELDS = frozenset(
    {
        "candidate_version",
        "evaluation_fingerprint_sha256",
        "policy",
        "trades",
        "probability_observations",
    }
)
_POLICY_FIELDS = frozenset(
    {"version", "starting_equity_usd", "calibration_bucket_count"}
)
_TRADE_FIELDS = frozenset(
    {
        "candidate_version",
        "position_id",
        "candidate_mint",
        "setup_name",
        "market_regime",
        "opened_at_unix_ms",
        "closed_at_unix_ms",
        "entry_notional_usd",
        "turnover_usd",
        "gross_pnl_usd",
        "execution_friction_usd",
        "explicit_cost_usd",
        "net_pnl_usd",
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "candidate_version",
        "model_version",
        "candidate_mint",
        "as_of_unix_ms",
        "positive_probability",
        "target_positive",
        "setup_name",
        "market_regime",
        "fold_name",
    }
)


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"value is not canonical-JSON serializable: {error}"
        ) from error


def build_evidence(
    candidate_version: str,
    trades: tuple[EvaluatedTrade, ...],
    probability_observations: tuple[ProbabilityObservation, ...],
    policy: TradingEvaluationPolicy,
) -> TradingEvaluationEvidence:
    report = evaluate_trading_performance(
        trades,
        probability_observations,
        policy,
        candidate_version,
    )
    canonical_trades = tuple(
        sorted(
            trades,
            key=lambda trade: (
                trade.closed_at_unix_ms,
                trade.opened_at_unix_ms,
                trade.position_id,
                trade.candidate_mint,
            ),
        )
    )
    canonical_observations = tuple(
        sorted(
            probability_observations,
            key=lambda observation: (
                observation.as_of_unix_ms,
                observation.candidate_mint,
            ),
        )
    )
    return TradingEvaluationEvidence(
        candidate_version=candidate_version,
        policy=policy,
        trades=canonical_trades,
        probability_observations=canonical_observations,
        report=report,
    )


def build_evidence_document(
    evidence_values: tuple[TradingEvaluationEvidence, ...],
) -> dict[str, object]:
    if not isinstance(evidence_values, tuple):
        raise ValueError("evidence_values must be a tuple")
    seen: set[tuple[str, str]] = set()
    records: list[dict[str, object]] = []
    for evidence in evidence_values:
        if type(evidence) is not TradingEvaluationEvidence:
            raise ValueError(
                "evidence_values must contain exact TradingEvaluationEvidence values"
            )
        identity = (
            evidence.candidate_version,
            evidence.report.evaluation_fingerprint_sha256,
        )
        if identity in seen:
            raise ValueError("evaluation evidence contains duplicate evaluation identity")
        seen.add(identity)
        records.append(_evidence_to_dict(evidence))
    return {
        "schema_version": EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION,
        "evaluations": records,
    }


def decode_evidence_document(
    document: object,
) -> tuple[TradingEvaluationEvidence, ...]:
    mapping = _require_exact_mapping(
        "evaluation evidence document", document, _DOCUMENT_FIELDS
    )
    if mapping["schema_version"] != EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION:
        raise ValueError(
            "evaluation evidence document schema_version must equal "
            f"{EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION}"
        )
    raw_evaluations = mapping["evaluations"]
    if not isinstance(raw_evaluations, list):
        raise ValueError("evaluations must be a list")

    seen: set[tuple[str, str]] = set()
    evidence_values: list[TradingEvaluationEvidence] = []
    for raw_evaluation in raw_evaluations:
        record = _require_exact_mapping(
            "evaluation evidence", raw_evaluation, _EVALUATION_FIELDS
        )
        candidate_version = record["candidate_version"]
        if not isinstance(candidate_version, str) or not candidate_version.strip():
            raise ValueError("candidate_version must be a non-empty string")
        stored_fingerprint = record["evaluation_fingerprint_sha256"]
        _require_sha256("evaluation_fingerprint_sha256", stored_fingerprint)

        policy = _decode_policy(record["policy"])
        trades = _decode_trades(record["trades"])
        observations = _decode_observations(record["probability_observations"])
        evidence = build_evidence(candidate_version, trades, observations, policy)

        if trades != evidence.trades:
            raise ValueError("trades must be persisted in sealed E5 canonical order")
        if observations != evidence.probability_observations:
            raise ValueError(
                "probability_observations must be persisted in sealed E5 canonical order"
            )
        if stored_fingerprint != evidence.report.evaluation_fingerprint_sha256:
            raise ValueError(
                "evaluation fingerprint does not match reconstructed sealed E5 evidence"
            )

        identity = (candidate_version, stored_fingerprint)
        if identity in seen:
            raise ValueError("evaluation evidence contains duplicate evaluation identity")
        seen.add(identity)
        evidence_values.append(evidence)
    return tuple(evidence_values)


def _evidence_to_dict(evidence: TradingEvaluationEvidence) -> dict[str, object]:
    return {
        "candidate_version": evidence.candidate_version,
        "evaluation_fingerprint_sha256": evidence.report.evaluation_fingerprint_sha256,
        "policy": _policy_to_dict(evidence.policy),
        "trades": [_trade_to_dict(trade) for trade in evidence.trades],
        "probability_observations": [
            _observation_to_dict(observation)
            for observation in evidence.probability_observations
        ],
    }


def _policy_to_dict(policy: TradingEvaluationPolicy) -> dict[str, object]:
    return {
        "version": policy.version,
        "starting_equity_usd": policy.starting_equity_usd,
        "calibration_bucket_count": policy.calibration_bucket_count,
    }


def _trade_to_dict(trade: EvaluatedTrade) -> dict[str, object]:
    return {
        "candidate_version": trade.candidate_version,
        "position_id": trade.position_id,
        "candidate_mint": trade.candidate_mint,
        "setup_name": trade.setup_name,
        "market_regime": trade.market_regime,
        "opened_at_unix_ms": trade.opened_at_unix_ms,
        "closed_at_unix_ms": trade.closed_at_unix_ms,
        "entry_notional_usd": trade.entry_notional_usd,
        "turnover_usd": trade.turnover_usd,
        "gross_pnl_usd": trade.gross_pnl_usd,
        "execution_friction_usd": trade.execution_friction_usd,
        "explicit_cost_usd": trade.explicit_cost_usd,
        "net_pnl_usd": trade.net_pnl_usd,
    }


def _observation_to_dict(observation: ProbabilityObservation) -> dict[str, object]:
    return {
        "candidate_version": observation.candidate_version,
        "model_version": observation.model_version,
        "candidate_mint": observation.candidate_mint,
        "as_of_unix_ms": observation.as_of_unix_ms,
        "positive_probability": observation.positive_probability,
        "target_positive": observation.target_positive,
        "setup_name": observation.setup_name,
        "market_regime": observation.market_regime,
        "fold_name": observation.fold_name,
    }


def _decode_policy(value: object) -> TradingEvaluationPolicy:
    mapping = _require_exact_mapping("evaluation policy", value, _POLICY_FIELDS)
    return TradingEvaluationPolicy(
        version=mapping["version"],  # type: ignore[arg-type]
        starting_equity_usd=mapping["starting_equity_usd"],  # type: ignore[arg-type]
        calibration_bucket_count=mapping["calibration_bucket_count"],  # type: ignore[arg-type]
    )


def _decode_trades(value: object) -> tuple[EvaluatedTrade, ...]:
    if not isinstance(value, list):
        raise ValueError("trades must be a list")
    trades: list[EvaluatedTrade] = []
    for raw_trade in value:
        mapping = _require_exact_mapping("evaluated trade", raw_trade, _TRADE_FIELDS)
        trades.append(
            EvaluatedTrade(
                candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
                position_id=mapping["position_id"],  # type: ignore[arg-type]
                candidate_mint=mapping["candidate_mint"],  # type: ignore[arg-type]
                setup_name=mapping["setup_name"],  # type: ignore[arg-type]
                market_regime=mapping["market_regime"],  # type: ignore[arg-type]
                opened_at_unix_ms=mapping["opened_at_unix_ms"],  # type: ignore[arg-type]
                closed_at_unix_ms=mapping["closed_at_unix_ms"],  # type: ignore[arg-type]
                entry_notional_usd=mapping["entry_notional_usd"],  # type: ignore[arg-type]
                turnover_usd=mapping["turnover_usd"],  # type: ignore[arg-type]
                gross_pnl_usd=mapping["gross_pnl_usd"],  # type: ignore[arg-type]
                execution_friction_usd=mapping["execution_friction_usd"],  # type: ignore[arg-type]
                explicit_cost_usd=mapping["explicit_cost_usd"],  # type: ignore[arg-type]
                net_pnl_usd=mapping["net_pnl_usd"],  # type: ignore[arg-type]
            )
        )
    return tuple(trades)


def _decode_observations(value: object) -> tuple[ProbabilityObservation, ...]:
    if not isinstance(value, list):
        raise ValueError("probability_observations must be a list")
    observations: list[ProbabilityObservation] = []
    for raw_observation in value:
        mapping = _require_exact_mapping(
            "probability observation", raw_observation, _OBSERVATION_FIELDS
        )
        observations.append(
            ProbabilityObservation(
                candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
                model_version=mapping["model_version"],  # type: ignore[arg-type]
                candidate_mint=mapping["candidate_mint"],  # type: ignore[arg-type]
                as_of_unix_ms=mapping["as_of_unix_ms"],  # type: ignore[arg-type]
                positive_probability=mapping["positive_probability"],  # type: ignore[arg-type]
                target_positive=mapping["target_positive"],  # type: ignore[arg-type]
                setup_name=mapping["setup_name"],  # type: ignore[arg-type]
                market_regime=mapping["market_regime"],  # type: ignore[arg-type]
                fold_name=mapping["fold_name"],  # type: ignore[arg-type]
            )
        )
    return tuple(observations)


def _require_exact_mapping(
    name: str,
    value: object,
    expected_fields: frozenset[str],
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if frozenset(value) != expected_fields or len(value) != len(expected_fields):
        raise ValueError(f"{name} fields must match the sealed schema exactly")
    return value


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(
            f"{name} must be a 64-character lowercase SHA-256 hex digest"
        )


def _require_finite_number(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
