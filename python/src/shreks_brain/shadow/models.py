from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.decision import DecisionAction
from shreks_brain.regime import MarketRegime
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import SetupState


SHADOW_CHALLENGER_SCHEMA_VERSION = "e7-shadow-v1"
_ENTRY_ACTIONS = frozenset(
    (DecisionAction.REJECT, DecisionAction.WATCH, DecisionAction.ENTER)
)


class ShadowReasonCode(StrEnum):
    SAFETY_NOT_PASS = "SAFETY_NOT_PASS"
    SETUP_BLOCKED = "SETUP_BLOCKED"
    REGIME_DEAD = "REGIME_DEAD"
    SETUP_WATCH = "SETUP_WATCH"
    PROBABILITY_BELOW_ENTER_THRESHOLD = "PROBABILITY_BELOW_ENTER_THRESHOLD"
    PROBABILITY_ENTER_APPROVED = "PROBABILITY_ENTER_APPROVED"


@dataclass(frozen=True, slots=True)
class ShadowDecisionPolicy:
    version: str
    enter_min_probability: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_fraction("enter_min_probability", self.enter_min_probability)


@dataclass(frozen=True, slots=True)
class ShadowDecisionRecord:
    schema_version: str
    candidate_version: str
    strategy_version: str
    candidate_fingerprint_sha256: str
    registry_fingerprint_sha256: str
    model_version: str
    model_training_fingerprint_sha256: str
    target_horizon_seconds: int
    target_minimum_return_pct: float
    shadow_policy_version: str
    enter_min_probability: float
    candidate_mint: str
    as_of_unix_ms: int
    dataset_schema_version: str
    decision_feature_fingerprint_sha256: str
    setup_name: str
    safety_decision: str
    setup_state: str
    market_regime: str
    baseline_action: DecisionAction
    positive_probability: float
    challenger_action: DecisionAction
    reason: ShadowReasonCode
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != SHADOW_CHALLENGER_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {SHADOW_CHALLENGER_SCHEMA_VERSION}"
            )
        for name in (
            "candidate_version",
            "strategy_version",
            "model_version",
            "shadow_policy_version",
            "candidate_mint",
            "dataset_schema_version",
            "setup_name",
            "safety_decision",
            "setup_state",
            "market_regime",
        ):
            _require_non_empty_string(name, getattr(self, name))
        for name in (
            "candidate_fingerprint_sha256",
            "registry_fingerprint_sha256",
            "model_training_fingerprint_sha256",
            "decision_feature_fingerprint_sha256",
            "record_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _require_positive_int("target_horizon_seconds", self.target_horizon_seconds)
        _require_finite("target_minimum_return_pct", self.target_minimum_return_pct)
        _require_fraction("enter_min_probability", self.enter_min_probability)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_fraction("positive_probability", self.positive_probability)

        _require_enum_string(
            "safety_decision", self.safety_decision, {value.value for value in SafetyDecision}
        )
        _require_enum_string(
            "setup_state", self.setup_state, {value.value for value in SetupState}
        )
        _require_enum_string(
            "market_regime", self.market_regime, {value.value for value in MarketRegime}
        )

        if type(self.baseline_action) is not DecisionAction or self.baseline_action not in _ENTRY_ACTIONS:
            raise ValueError("baseline_action must be an entry-side DecisionAction")
        if type(self.challenger_action) is not DecisionAction or self.challenger_action not in _ENTRY_ACTIONS:
            raise ValueError("challenger_action must be an entry-side DecisionAction")
        if type(self.reason) is not ShadowReasonCode:
            raise ValueError("reason must be a ShadowReasonCode")

        expected_action = {
            ShadowReasonCode.SAFETY_NOT_PASS: DecisionAction.REJECT,
            ShadowReasonCode.SETUP_BLOCKED: DecisionAction.REJECT,
            ShadowReasonCode.REGIME_DEAD: DecisionAction.REJECT,
            ShadowReasonCode.SETUP_WATCH: DecisionAction.WATCH,
            ShadowReasonCode.PROBABILITY_BELOW_ENTER_THRESHOLD: DecisionAction.WATCH,
            ShadowReasonCode.PROBABILITY_ENTER_APPROVED: DecisionAction.ENTER,
        }[self.reason]
        if self.challenger_action is not expected_action:
            raise ValueError("challenger_action must agree with reason")
        if (
            self.reason is ShadowReasonCode.PROBABILITY_BELOW_ENTER_THRESHOLD
            and self.positive_probability >= self.enter_min_probability
        ):
            raise ValueError("below-threshold reason requires probability below threshold")
        if (
            self.reason is ShadowReasonCode.PROBABILITY_ENTER_APPROVED
            and self.positive_probability < self.enter_min_probability
        ):
            raise ValueError("enter-approved reason requires probability at or above threshold")


@dataclass(frozen=True, slots=True)
class ShadowEvidenceLedger:
    schema_version: str
    records: tuple[ShadowDecisionRecord, ...]
    ledger_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != SHADOW_CHALLENGER_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {SHADOW_CHALLENGER_SCHEMA_VERSION}"
            )
        if not isinstance(self.records, tuple) or not all(
            type(value) is ShadowDecisionRecord for value in self.records
        ):
            raise ValueError("records must be a tuple of exact ShadowDecisionRecord values")
        _require_sha256("ledger_fingerprint_sha256", self.ledger_fingerprint_sha256)
        if self.records != tuple(sorted(self.records, key=_record_sort_key)):
            raise ValueError("records must be in canonical order")
        identities = tuple(_decision_identity(value) for value in self.records)
        if len(identities) != len(set(identities)):
            raise ValueError("decision identity must be unique within the ledger")


def _decision_identity(record: ShadowDecisionRecord) -> tuple[str, str, int, str]:
    return (
        record.candidate_version,
        record.candidate_mint,
        record.as_of_unix_ms,
        record.shadow_policy_version,
    )


def _record_sort_key(record: ShadowDecisionRecord) -> tuple[int, str, str, str, str]:
    return (
        record.as_of_unix_ms,
        record.candidate_version,
        record.candidate_mint,
        record.shadow_policy_version,
        record.record_fingerprint_sha256,
    )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_fraction(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0.0 or value > 1.0:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 1]")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256 hex digest")


def _require_enum_string(name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} is not a supported value")
