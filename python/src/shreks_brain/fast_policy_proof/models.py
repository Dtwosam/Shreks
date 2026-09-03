from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.evaluation import TradingEvaluationEvidence


FAST_POLICY_PROOF_SCHEMA_NAME = "shreks.fast_policy_superiority"
FAST_POLICY_PROOF_SCHEMA_VERSION = 1


class FastPolicyProofDecision(StrEnum):
    SUPERIOR = "SUPERIOR"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class FastPolicyProofGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT = "INSUFFICIENT"


class FastPolicyProofGateCode(StrEnum):
    BASELINE_COVERAGE = "BASELINE_COVERAGE"
    BASELINE_EXPECTANCY_ADVANTAGE = "BASELINE_EXPECTANCY_ADVANTAGE"
    CANDIDATE_PROVENANCE = "CANDIDATE_PROVENANCE"
    COMPARISON_POPULATION = "COMPARISON_POPULATION"
    EVALUATION_POLICY_MATCH = "EVALUATION_POLICY_MATCH"
    MAX_COST_BURDEN_PCT = "MAX_COST_BURDEN_PCT"
    MAX_DRAWDOWN_PCT = "MAX_DRAWDOWN_PCT"
    MAX_SINGLE_WINNER_SHARE = "MAX_SINGLE_WINNER_SHARE"
    MIN_DISTINCT_MARKET_COUNT = "MIN_DISTINCT_MARKET_COUNT"
    MIN_DISTINCT_TRADED_MINT_COUNT = "MIN_DISTINCT_TRADED_MINT_COUNT"
    MIN_EVALUATION_SPAN = "MIN_EVALUATION_SPAN"
    MIN_MATERIAL_DECISION_COUNT = "MIN_MATERIAL_DECISION_COUNT"
    MIN_NET_EXPECTANCY_PCT = "MIN_NET_EXPECTANCY_PCT"
    MIN_PROFIT_FACTOR = "MIN_PROFIT_FACTOR"
    MIN_TRADE_COUNT = "MIN_TRADE_COUNT"


@dataclass(frozen=True, slots=True)
class FastPolicyRunEvidence:
    schema_name: str
    schema_version: int
    paper_run_id: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    strategy_version: str
    trading_evaluation: TradingEvaluationEvidence
    event_population_fingerprint_sha256: str
    action_journal_fingerprint_sha256: str
    material_update_count: int
    decision_count: int
    distinct_market_count: int
    observed_from_unix_ms: int
    observed_through_unix_ms: int
    run_evidence_fingerprint_sha256: str

    def __post_init__(self) -> None:
        _require_schema(self.schema_name, self.schema_version)
        for name in ("paper_run_id", "candidate_version", "strategy_version"):
            _require_non_empty_string(name, getattr(self, name))
        for name in (
            "candidate_fingerprint_sha256",
            "event_population_fingerprint_sha256",
            "action_journal_fingerprint_sha256",
            "run_evidence_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if type(self.trading_evaluation) is not TradingEvaluationEvidence:
            raise ValueError(
                "trading_evaluation must be an exact TradingEvaluationEvidence"
            )
        if self.trading_evaluation.candidate_version != self.candidate_version:
            raise ValueError(
                "trading evaluation candidate_version must match run evidence"
            )
        for name in (
            "material_update_count",
            "decision_count",
            "distinct_market_count",
            "observed_from_unix_ms",
            "observed_through_unix_ms",
        ):
            _require_non_negative_int(name, getattr(self, name))
        if self.decision_count != self.material_update_count:
            raise ValueError(
                "decision_count must equal material_update_count for Fast PAPER evidence"
            )
        if self.observed_through_unix_ms < self.observed_from_unix_ms:
            raise ValueError(
                "observed_through_unix_ms cannot precede observed_from_unix_ms"
            )


@dataclass(frozen=True, slots=True)
class FastPolicySuperiorityPolicy:
    version: str
    required_baseline_versions: tuple[str, ...]
    min_material_decision_count: int
    min_distinct_market_count: int
    min_evaluation_span_ms: int
    min_trade_count: int
    min_distinct_traded_mint_count: int
    min_net_expectancy_pct: float
    min_profit_factor: float
    max_drawdown_pct: float
    max_cost_burden_pct: float
    max_single_winner_share_of_positive_pnl: float
    min_baseline_expectancy_advantage_pct: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        values = self.required_baseline_versions
        if (
            not isinstance(values, tuple)
            or not values
            or not all(isinstance(value, str) and value.strip() for value in values)
        ):
            raise ValueError(
                "required_baseline_versions must be a non-empty tuple of strings"
            )
        if values != tuple(sorted(values)) or len(values) != len(set(values)):
            raise ValueError(
                "required_baseline_versions must be unique and in lexical order"
            )
        for name in (
            "min_material_decision_count",
            "min_distinct_market_count",
            "min_evaluation_span_ms",
            "min_trade_count",
            "min_distinct_traded_mint_count",
        ):
            _require_non_negative_int(name, getattr(self, name))
        _require_finite("min_net_expectancy_pct", self.min_net_expectancy_pct)
        _require_non_negative_finite("min_profit_factor", self.min_profit_factor)
        _require_percent("max_drawdown_pct", self.max_drawdown_pct)
        _require_percent("max_cost_burden_pct", self.max_cost_burden_pct)
        _require_fraction(
            "max_single_winner_share_of_positive_pnl",
            self.max_single_winner_share_of_positive_pnl,
        )
        _require_finite(
            "min_baseline_expectancy_advantage_pct",
            self.min_baseline_expectancy_advantage_pct,
        )


@dataclass(frozen=True, slots=True)
class FastPolicyProofGateResult:
    code: FastPolicyProofGateCode
    status: FastPolicyProofGateStatus
    observed_value: float | int | str | None
    threshold_value: float | int | str | None
    message: str

    def __post_init__(self) -> None:
        if type(self.code) is not FastPolicyProofGateCode:
            raise ValueError("code must be an exact FastPolicyProofGateCode")
        if type(self.status) is not FastPolicyProofGateStatus:
            raise ValueError("status must be an exact FastPolicyProofGateStatus")
        _validate_gate_value("observed_value", self.observed_value)
        _validate_gate_value("threshold_value", self.threshold_value)
        _require_non_empty_string("message", self.message)


@dataclass(frozen=True, slots=True)
class FastPolicySuperiorityReport:
    schema_name: str
    schema_version: int
    policy_version: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    candidate_run_evidence_fingerprint_sha256: str
    candidate_evaluation_fingerprint_sha256: str
    event_population_fingerprint_sha256: str
    baseline_evaluation_identities: tuple[tuple[str, str, str], ...]
    best_baseline_version: str | None
    best_baseline_evaluation_fingerprint_sha256: str | None
    candidate_net_expectancy_pct: float | None
    best_baseline_net_expectancy_pct: float | None
    expectancy_advantage_pct: float | None
    gates: tuple[FastPolicyProofGateResult, ...]
    decision: FastPolicyProofDecision
    report_fingerprint_sha256: str

    def __post_init__(self) -> None:
        _require_schema(self.schema_name, self.schema_version)
        for name in ("policy_version", "candidate_version"):
            _require_non_empty_string(name, getattr(self, name))
        for name in (
            "candidate_fingerprint_sha256",
            "candidate_run_evidence_fingerprint_sha256",
            "candidate_evaluation_fingerprint_sha256",
            "event_population_fingerprint_sha256",
            "report_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _validate_baseline_identities(self.baseline_evaluation_identities)
        paired = (
            self.best_baseline_version,
            self.best_baseline_evaluation_fingerprint_sha256,
            self.best_baseline_net_expectancy_pct,
            self.expectancy_advantage_pct,
        )
        if any(value is None for value in paired) and not all(
            value is None for value in paired
        ):
            raise ValueError("best baseline report fields must be all present or all absent")
        if self.best_baseline_version is not None:
            _require_non_empty_string(
                "best_baseline_version", self.best_baseline_version
            )
            assert self.best_baseline_evaluation_fingerprint_sha256 is not None
            _require_sha256(
                "best_baseline_evaluation_fingerprint_sha256",
                self.best_baseline_evaluation_fingerprint_sha256,
            )
            assert self.best_baseline_net_expectancy_pct is not None
            assert self.expectancy_advantage_pct is not None
            _require_finite(
                "best_baseline_net_expectancy_pct",
                self.best_baseline_net_expectancy_pct,
            )
            _require_finite("expectancy_advantage_pct", self.expectancy_advantage_pct)
        if self.candidate_net_expectancy_pct is not None:
            _require_finite(
                "candidate_net_expectancy_pct", self.candidate_net_expectancy_pct
            )

        if (
            not isinstance(self.gates, tuple)
            or not all(type(value) is FastPolicyProofGateResult for value in self.gates)
        ):
            raise ValueError(
                "gates must be a tuple of exact FastPolicyProofGateResult values"
            )
        expected_codes = tuple(
            sorted(FastPolicyProofGateCode, key=lambda value: value.value)
        )
        actual_codes = tuple(value.code for value in self.gates)
        if actual_codes != expected_codes:
            raise ValueError("gates must contain every gate code once in lexical order")
        if type(self.decision) is not FastPolicyProofDecision:
            raise ValueError("decision must be an exact FastPolicyProofDecision")
        if self.decision is not _decision_from_gates(self.gates):
            raise ValueError("decision must agree with gate status precedence")


def _decision_from_gates(
    gates: tuple[FastPolicyProofGateResult, ...],
) -> FastPolicyProofDecision:
    if any(value.status is FastPolicyProofGateStatus.FAIL for value in gates):
        return FastPolicyProofDecision.FAILED
    if any(
        value.status is FastPolicyProofGateStatus.INSUFFICIENT for value in gates
    ):
        return FastPolicyProofDecision.INSUFFICIENT_EVIDENCE
    return FastPolicyProofDecision.SUPERIOR


def _validate_baseline_identities(values: object) -> None:
    if not isinstance(values, tuple):
        raise ValueError("baseline_evaluation_identities must be a tuple")
    versions: list[str] = []
    for value in values:
        if (
            not isinstance(value, tuple)
            or len(value) != 3
            or not isinstance(value[0], str)
            or not value[0].strip()
        ):
            raise ValueError(
                "baseline identities must contain (version, run_sha256, evaluation_sha256)"
            )
        _require_sha256("baseline run fingerprint", value[1])
        _require_sha256("baseline evaluation fingerprint", value[2])
        versions.append(value[0])
    if versions != sorted(versions) or len(versions) != len(set(versions)):
        raise ValueError("baseline identities must be unique and lexical")


def _validate_gate_value(name: str, value: object) -> None:
    if value is None or isinstance(value, str):
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be None, string, integer, or finite float")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_schema(name: object, version: object) -> None:
    if name != FAST_POLICY_PROOF_SCHEMA_NAME:
        raise ValueError(
            f"schema_name must equal {FAST_POLICY_PROOF_SCHEMA_NAME}"
        )
    if version != FAST_POLICY_PROOF_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must equal {FAST_POLICY_PROOF_SCHEMA_VERSION}"
        )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
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
        raise ValueError(
            f"{name} must be a lowercase 64-character SHA-256 hex digest"
        )
