from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


PROMOTION_SCHEMA_VERSION = "e8-promotion-v1"


class PromotionDecision(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PromotionGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT = "INSUFFICIENT"


class PromotionGateCode(StrEnum):
    CURRENT_CHALLENGER = "CURRENT_CHALLENGER"
    MODEL_VALIDATION_PROVENANCE = "MODEL_VALIDATION_PROVENANCE"
    EVALUATION_MATCH = "EVALUATION_MATCH"
    TRADE_EVIDENCE_RECONCILIATION = "TRADE_EVIDENCE_RECONCILIATION"
    MIN_TRADE_COUNT = "MIN_TRADE_COUNT"
    MIN_EVALUATION_SPAN = "MIN_EVALUATION_SPAN"
    MIN_NET_EXPECTANCY_PCT = "MIN_NET_EXPECTANCY_PCT"
    MIN_PROFIT_FACTOR = "MIN_PROFIT_FACTOR"
    MAX_DRAWDOWN_PCT = "MAX_DRAWDOWN_PCT"
    MAX_COST_BURDEN_PCT = "MAX_COST_BURDEN_PCT"
    MAX_BRIER_SCORE = "MAX_BRIER_SCORE"
    MAX_EXPECTED_CALIBRATION_ERROR = "MAX_EXPECTED_CALIBRATION_ERROR"
    BASELINE_COVERAGE = "BASELINE_COVERAGE"
    BASELINE_EXPECTANCY_ADVANTAGE = "BASELINE_EXPECTANCY_ADVANTAGE"
    MAX_SINGLE_WINNER_SHARE = "MAX_SINGLE_WINNER_SHARE"
    SHADOW_PROVENANCE = "SHADOW_PROVENANCE"
    MIN_SHADOW_DECISION_COUNT = "MIN_SHADOW_DECISION_COUNT"
    MIN_SHADOW_DISTINCT_MINT_COUNT = "MIN_SHADOW_DISTINCT_MINT_COUNT"
    MIN_SHADOW_SPAN = "MIN_SHADOW_SPAN"


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    version: str
    min_trade_count: int
    min_evaluation_span_ms: int
    min_net_expectancy_pct: float
    min_profit_factor: float
    max_drawdown_pct: float
    max_cost_burden_pct: float
    max_brier_score: float
    max_expected_calibration_error: float
    required_baseline_versions: tuple[str, ...]
    min_baseline_expectancy_advantage_pct: float
    max_single_winner_share_of_positive_pnl: float
    min_shadow_decision_count: int
    min_shadow_distinct_mint_count: int
    min_shadow_span_ms: int

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        for name in (
            "min_trade_count",
            "min_evaluation_span_ms",
            "min_shadow_decision_count",
            "min_shadow_distinct_mint_count",
            "min_shadow_span_ms",
        ):
            _require_non_negative_int(name, getattr(self, name))
        _require_finite("min_net_expectancy_pct", self.min_net_expectancy_pct)
        _require_non_negative_finite("min_profit_factor", self.min_profit_factor)
        _require_percent("max_drawdown_pct", self.max_drawdown_pct)
        _require_percent("max_cost_burden_pct", self.max_cost_burden_pct)
        _require_fraction("max_brier_score", self.max_brier_score)
        _require_fraction(
            "max_expected_calibration_error", self.max_expected_calibration_error
        )
        _require_non_negative_finite(
            "min_baseline_expectancy_advantage_pct",
            self.min_baseline_expectancy_advantage_pct,
        )
        _require_fraction(
            "max_single_winner_share_of_positive_pnl",
            self.max_single_winner_share_of_positive_pnl,
        )
        _validate_baseline_versions(self.required_baseline_versions)


@dataclass(frozen=True, slots=True)
class PromotionGateResult:
    code: PromotionGateCode
    status: PromotionGateStatus
    observed_value: float | int | str | None
    threshold_value: float | int | str | None
    message: str

    def __post_init__(self) -> None:
        if type(self.code) is not PromotionGateCode:
            raise ValueError("code must be a PromotionGateCode")
        if type(self.status) is not PromotionGateStatus:
            raise ValueError("status must be a PromotionGateStatus")
        _validate_gate_value("observed_value", self.observed_value)
        _validate_gate_value("threshold_value", self.threshold_value)
        _require_non_empty_string("message", self.message)


@dataclass(frozen=True, slots=True)
class PromotionAssessment:
    schema_version: str
    policy_version: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    registry_fingerprint_sha256: str
    evaluation_fingerprint_sha256: str
    trade_evidence_fingerprint_sha256: str
    shadow_ledger_fingerprint_sha256: str
    baseline_evaluation_identities: tuple[tuple[str, str], ...]
    evaluated_at_unix_ms: int
    gates: tuple[PromotionGateResult, ...]
    decision: PromotionDecision
    assessment_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != PROMOTION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {PROMOTION_SCHEMA_VERSION}"
            )
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("candidate_version", self.candidate_version)
        for name in (
            "candidate_fingerprint_sha256",
            "registry_fingerprint_sha256",
            "evaluation_fingerprint_sha256",
            "trade_evidence_fingerprint_sha256",
            "shadow_ledger_fingerprint_sha256",
            "assessment_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _validate_baseline_identities(self.baseline_evaluation_identities)
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        _validate_gates(self.gates)
        if type(self.decision) is not PromotionDecision:
            raise ValueError("decision must be a PromotionDecision")
        expected = _decision_from_gates(self.gates)
        if self.decision is not expected:
            raise ValueError("decision must agree with gate status precedence")


def _decision_from_gates(gates: tuple[PromotionGateResult, ...]) -> PromotionDecision:
    if any(gate.status is PromotionGateStatus.FAIL for gate in gates):
        return PromotionDecision.INELIGIBLE
    if any(gate.status is PromotionGateStatus.INSUFFICIENT for gate in gates):
        return PromotionDecision.INSUFFICIENT_EVIDENCE
    return PromotionDecision.ELIGIBLE


def _validate_gates(gates: object) -> None:
    if not isinstance(gates, tuple) or not all(
        type(value) is PromotionGateResult for value in gates
    ):
        raise ValueError("gates must be a tuple of exact PromotionGateResult values")
    expected_codes = tuple(sorted(PromotionGateCode, key=lambda value: value.value))
    actual_codes = tuple(value.code for value in gates)
    if actual_codes != expected_codes:
        raise ValueError("gates must contain every gate code exactly once in lexical order")


def _validate_baseline_versions(values: object) -> None:
    if not isinstance(values, tuple) or not all(
        isinstance(value, str) and value.strip() for value in values
    ):
        raise ValueError("required_baseline_versions must be a tuple of non-empty strings")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError("required_baseline_versions must be unique and in lexical order")


def _validate_baseline_identities(values: object) -> None:
    if not isinstance(values, tuple):
        raise ValueError("baseline_evaluation_identities must be a tuple")
    versions: list[str] = []
    for value in values:
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], str)
            or not value[0].strip()
        ):
            raise ValueError(
                "baseline_evaluation_identities must contain (version, sha256) tuples"
            )
        _require_sha256("baseline_evaluation_identities", value[1])
        versions.append(value[0])
    if versions != sorted(versions) or len(versions) != len(set(versions)):
        raise ValueError(
            "baseline_evaluation_identities must have unique versions in lexical order"
        )


def _validate_gate_value(name: str, value: object) -> None:
    if value is None or isinstance(value, str):
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be None, string, integer, or finite float")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_fraction(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0 or value > 1:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 1]")


def _require_percent(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0 or value > 100:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 100]")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256 hex digest")
