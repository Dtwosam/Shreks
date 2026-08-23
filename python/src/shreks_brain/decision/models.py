from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.regime import MarketRegime
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import SetupState


class DecisionAction(StrEnum):
    REJECT = "REJECT"
    WATCH = "WATCH"
    ENTER = "ENTER"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class DecisionReasonCode(StrEnum):
    SCORE_POLICY_MISMATCH = "SCORE_POLICY_MISMATCH"
    SAFETY_REJECTED = "SAFETY_REJECTED"
    SAFETY_INCOMPLETE = "SAFETY_INCOMPLETE"
    SETUP_BLOCKED = "SETUP_BLOCKED"
    SETUP_WATCH = "SETUP_WATCH"
    SETUP_RULE_MISSING = "SETUP_RULE_MISSING"
    SETUP_DISABLED = "SETUP_DISABLED"
    REGIME_DEAD = "REGIME_DEAD"
    REGIME_DISABLED = "REGIME_DISABLED"
    TOTAL_SCORE_UNAVAILABLE = "TOTAL_SCORE_UNAVAILABLE"
    TOTAL_SCORE_BELOW_THRESHOLD = "TOTAL_SCORE_BELOW_THRESHOLD"
    ENTRY_APPROVED = "ENTRY_APPROVED"


@dataclass(frozen=True, slots=True)
class DecisionFinding:
    code: DecisionReasonCode
    message: str
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, DecisionReasonCode):
            raise ValueError("code must be a DecisionReasonCode")
        _require_non_empty_string("message", self.message)
        if self.observed_value is not None:
            if isinstance(self.observed_value, bool) or not isinstance(
                self.observed_value, (int, float, str)
            ):
                raise ValueError("observed_value must be numeric, string, or None")
            if isinstance(self.observed_value, float) and not math.isfinite(
                self.observed_value
            ):
                raise ValueError("observed_value must be finite when numeric")
        if self.threshold_value is not None:
            _require_finite("threshold_value", self.threshold_value)


@dataclass(frozen=True, slots=True)
class SetupDecisionRule:
    setup_name: str
    enabled: bool
    hot_min_score: float | None
    normal_min_score: float | None
    weak_min_score: float | None

    def __post_init__(self) -> None:
        _require_non_empty_string("setup_name", self.setup_name)
        _require_bool("enabled", self.enabled)
        for name in ("hot_min_score", "normal_min_score", "weak_min_score"):
            _require_optional_score(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    version: str
    required_score_policy_version: str
    setup_rules: tuple[SetupDecisionRule, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_non_empty_string(
            "required_score_policy_version", self.required_score_policy_version
        )
        if not isinstance(self.setup_rules, tuple) or not self.setup_rules:
            raise ValueError("setup_rules must be a non-empty tuple")
        if not all(isinstance(rule, SetupDecisionRule) for rule in self.setup_rules):
            raise ValueError("setup_rules must contain only SetupDecisionRule values")
        names = tuple(rule.setup_name for rule in self.setup_rules)
        if len(set(names)) != len(names):
            raise ValueError("setup_rules must use unique setup_name values")


@dataclass(frozen=True, slots=True)
class TradeDecision:
    policy_version: str
    mint: str
    as_of_unix_ms: int
    action: DecisionAction
    score_policy_version: str
    feature_schema_version: str
    safety_decision: SafetyDecision
    setup_name: str
    setup_policy_version: str
    setup_state: SetupState
    market_regime: MarketRegime
    total_score: float | None
    required_score_threshold: float | None
    findings: tuple[DecisionFinding, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.action, DecisionAction):
            raise ValueError("action must be a DecisionAction")
        _require_non_empty_string("score_policy_version", self.score_policy_version)
        _require_non_empty_string("feature_schema_version", self.feature_schema_version)
        if not isinstance(self.safety_decision, SafetyDecision):
            raise ValueError("safety_decision must be a SafetyDecision")
        _require_non_empty_string("setup_name", self.setup_name)
        _require_non_empty_string("setup_policy_version", self.setup_policy_version)
        if not isinstance(self.setup_state, SetupState):
            raise ValueError("setup_state must be a SetupState")
        if not isinstance(self.market_regime, MarketRegime):
            raise ValueError("market_regime must be a MarketRegime")
        _require_optional_score("total_score", self.total_score)
        _require_optional_score(
            "required_score_threshold", self.required_score_threshold
        )
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, DecisionFinding) for finding in self.findings
        ):
            raise ValueError("findings must be a tuple of DecisionFinding values")


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bool(name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _require_finite(name: str, value: float | int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_optional_score(name: str, value: float | int | None) -> None:
    if value is None:
        return
    _require_finite(name, value)
    if value < 0.0 or value > 100.0:
        raise ValueError(f"{name} must be within [0, 100]")
