from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


PAPER_PROOF_SCHEMA_VERSION = "e12-paper-proof-v1"


class PaperProofDecision(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class PaperProofGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT = "INSUFFICIENT"


class PaperProofGateCode(StrEnum):
    E8_ASSESSMENT_ELIGIBLE = "E8_ASSESSMENT_ELIGIBLE"
    E8_REGISTRY_PROVENANCE = "E8_REGISTRY_PROVENANCE"
    MAX_PAPER_COST_BURDEN_PCT = "MAX_PAPER_COST_BURDEN_PCT"
    MAX_PAPER_DRAWDOWN_PCT = "MAX_PAPER_DRAWDOWN_PCT"
    MAX_PAPER_SINGLE_WINNER_SHARE = "MAX_PAPER_SINGLE_WINNER_SHARE"
    MIN_PAPER_DISTINCT_MINT_COUNT = "MIN_PAPER_DISTINCT_MINT_COUNT"
    MIN_PAPER_EVALUATION_SPAN = "MIN_PAPER_EVALUATION_SPAN"
    MIN_PAPER_NET_EXPECTANCY_PCT = "MIN_PAPER_NET_EXPECTANCY_PCT"
    MIN_PAPER_PROFIT_FACTOR = "MIN_PAPER_PROFIT_FACTOR"
    MIN_PAPER_TRADE_COUNT = "MIN_PAPER_TRADE_COUNT"
    PAPER_EVIDENCE_PROVENANCE = "PAPER_EVIDENCE_PROVENANCE"


@dataclass(frozen=True, slots=True)
class PaperProofPolicy:
    version: str
    min_trade_count: int
    min_distinct_mint_count: int
    min_evaluation_span_ms: int
    min_net_expectancy_pct: float
    min_profit_factor: float
    max_drawdown_pct: float
    max_cost_burden_pct: float
    max_single_winner_share_of_positive_pnl: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        for name in (
            "min_trade_count",
            "min_distinct_mint_count",
            "min_evaluation_span_ms",
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


@dataclass(frozen=True, slots=True)
class PaperProofGateResult:
    code: PaperProofGateCode
    status: PaperProofGateStatus
    observed_value: float | int | str | None
    threshold_value: float | int | str | None
    message: str

    def __post_init__(self) -> None:
        if type(self.code) is not PaperProofGateCode:
            raise ValueError("code must be a PaperProofGateCode")
        if type(self.status) is not PaperProofGateStatus:
            raise ValueError("status must be a PaperProofGateStatus")
        _validate_gate_value("observed_value", self.observed_value)
        _validate_gate_value("threshold_value", self.threshold_value)
        _require_non_empty_string("message", self.message)


@dataclass(frozen=True, slots=True)
class CandidateProofAssessment:
    schema_version: str
    policy_version: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    registry_fingerprint_sha256: str
    e8_assessment_fingerprint_sha256: str
    paper_run_id: str
    paper_ledger_fingerprint_sha256: str
    paper_evaluation_fingerprint_sha256: str
    paper_trade_evidence_fingerprint_sha256: str
    evaluated_at_unix_ms: int
    gates: tuple[PaperProofGateResult, ...]
    decision: PaperProofDecision
    assessment_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != PAPER_PROOF_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {PAPER_PROOF_SCHEMA_VERSION}"
            )
        for name in ("policy_version", "candidate_version", "paper_run_id"):
            _require_non_empty_string(name, getattr(self, name))
        for name in (
            "candidate_fingerprint_sha256",
            "registry_fingerprint_sha256",
            "e8_assessment_fingerprint_sha256",
            "paper_ledger_fingerprint_sha256",
            "paper_evaluation_fingerprint_sha256",
            "paper_trade_evidence_fingerprint_sha256",
            "assessment_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        _validate_gates(self.gates)
        if type(self.decision) is not PaperProofDecision:
            raise ValueError("decision must be a PaperProofDecision")
        expected = _decision_from_gates(self.gates)
        if self.decision is not expected:
            raise ValueError("decision must agree with gate status precedence")


def _decision_from_gates(
    gates: tuple[PaperProofGateResult, ...],
) -> PaperProofDecision:
    if any(gate.status is PaperProofGateStatus.FAIL for gate in gates):
        return PaperProofDecision.FAILED
    if any(gate.status is PaperProofGateStatus.INSUFFICIENT for gate in gates):
        return PaperProofDecision.INSUFFICIENT_EVIDENCE
    return PaperProofDecision.SUFFICIENT


def _validate_gates(gates: object) -> None:
    if not isinstance(gates, tuple) or not all(
        type(value) is PaperProofGateResult for value in gates
    ):
        raise ValueError("gates must be a tuple of exact PaperProofGateResult values")
    expected_codes = tuple(sorted(PaperProofGateCode, key=lambda value: value.value))
    actual_codes = tuple(value.code for value in gates)
    if actual_codes != expected_codes:
        raise ValueError("gates must contain every gate code exactly once in lexical order")


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
