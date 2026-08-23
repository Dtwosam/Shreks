from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.regime import MarketRegime
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import SetupState


class ScoreReasonCode(StrEnum):
    FEATURE_SCHEMA_UNSUPPORTED = "FEATURE_SCHEMA_UNSUPPORTED"
    FEATURE_SOURCE_AFTER_AS_OF = "FEATURE_SOURCE_AFTER_AS_OF"
    FEATURE_SOURCE_AGE_MISMATCH = "FEATURE_SOURCE_AGE_MISMATCH"
    SETUP_AS_OF_MISMATCH = "SETUP_AS_OF_MISMATCH"
    SETUP_FEATURE_SCHEMA_MISMATCH = "SETUP_FEATURE_SCHEMA_MISMATCH"
    REGIME_AS_OF_MISMATCH = "REGIME_AS_OF_MISMATCH"
    SAFETY_NOT_PASS_RESEARCH_ONLY = "SAFETY_NOT_PASS_RESEARCH_ONLY"
    SETUP_NOT_READY_RESEARCH_ONLY = "SETUP_NOT_READY_RESEARCH_ONLY"
    VOLUME_VELOCITY_UNKNOWN = "VOLUME_VELOCITY_UNKNOWN"
    BUY_FRACTION_M5_UNKNOWN = "BUY_FRACTION_M5_UNKNOWN"
    BUY_PRESSURE_ACCELERATION_UNKNOWN = "BUY_PRESSURE_ACCELERATION_UNKNOWN"
    LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN"
    EXIT_PRICE_IMPACT_UNKNOWN = "EXIT_PRICE_IMPACT_UNKNOWN"
    SAFETY_SOFT_PENALTIES_APPLIED = "SAFETY_SOFT_PENALTIES_APPLIED"
    TOTAL_SCORE_INCOMPLETE = "TOTAL_SCORE_INCOMPLETE"
    TOTAL_SCORE_AVAILABLE = "TOTAL_SCORE_AVAILABLE"


@dataclass(frozen=True, slots=True)
class ScoreFinding:
    code: ScoreReasonCode
    message: str
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ScoreReasonCode):
            raise ValueError("code must be a ScoreReasonCode")
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
class ScorePolicy:
    version: str
    required_feature_schema_version: str

    safety_weight: float
    money_flow_weight: float
    setup_quality_weight: float
    liquidity_executability_weight: float

    safety_liquidity_weak_penalty: float
    safety_holder_concentration_elevated_penalty: float
    safety_creator_concentration_elevated_penalty: float
    safety_exit_price_impact_elevated_penalty: float

    volume_velocity_zero: float
    volume_velocity_full: float
    buy_fraction_m5_zero: float
    buy_fraction_m5_full: float
    buy_pressure_acceleration_zero: float
    buy_pressure_acceleration_full: float

    liquidity_usd_zero: float
    liquidity_usd_full: float
    exit_price_impact_full: float
    exit_price_impact_zero: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_non_empty_string(
            "required_feature_schema_version", self.required_feature_schema_version
        )

        weights = (
            self.safety_weight,
            self.money_flow_weight,
            self.setup_quality_weight,
            self.liquidity_executability_weight,
        )
        for name, value in zip(
            (
                "safety_weight",
                "money_flow_weight",
                "setup_quality_weight",
                "liquidity_executability_weight",
            ),
            weights,
            strict=True,
        ):
            _require_bounded_finite(name, value, 0.0, 1.0)
        if not any(value > 0.0 for value in weights):
            raise ValueError("at least one score-family weight must be positive")
        if not math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("score-family weights must sum to 1.0")

        for name in (
            "safety_liquidity_weak_penalty",
            "safety_holder_concentration_elevated_penalty",
            "safety_creator_concentration_elevated_penalty",
            "safety_exit_price_impact_elevated_penalty",
        ):
            _require_bounded_finite(name, getattr(self, name), 0.0, 100.0)

        _require_non_negative_finite("volume_velocity_zero", self.volume_velocity_zero)
        _require_non_negative_finite("volume_velocity_full", self.volume_velocity_full)
        if self.volume_velocity_full <= self.volume_velocity_zero:
            raise ValueError("volume_velocity_full must be greater than volume_velocity_zero")

        _require_bounded_finite(
            "buy_fraction_m5_zero", self.buy_fraction_m5_zero, 0.0, 1.0
        )
        _require_bounded_finite(
            "buy_fraction_m5_full", self.buy_fraction_m5_full, 0.0, 1.0
        )
        if self.buy_fraction_m5_full <= self.buy_fraction_m5_zero:
            raise ValueError("buy_fraction_m5_full must be greater than buy_fraction_m5_zero")

        _require_finite(
            "buy_pressure_acceleration_zero", self.buy_pressure_acceleration_zero
        )
        _require_finite(
            "buy_pressure_acceleration_full", self.buy_pressure_acceleration_full
        )
        if self.buy_pressure_acceleration_full <= self.buy_pressure_acceleration_zero:
            raise ValueError(
                "buy_pressure_acceleration_full must be greater than "
                "buy_pressure_acceleration_zero"
            )

        _require_non_negative_finite("liquidity_usd_zero", self.liquidity_usd_zero)
        _require_non_negative_finite("liquidity_usd_full", self.liquidity_usd_full)
        if self.liquidity_usd_full <= self.liquidity_usd_zero:
            raise ValueError("liquidity_usd_full must be greater than liquidity_usd_zero")

        _require_non_negative_finite(
            "exit_price_impact_full", self.exit_price_impact_full
        )
        _require_non_negative_finite(
            "exit_price_impact_zero", self.exit_price_impact_zero
        )
        if self.exit_price_impact_zero <= self.exit_price_impact_full:
            raise ValueError(
                "exit_price_impact_zero must be greater than exit_price_impact_full"
            )


@dataclass(frozen=True, slots=True)
class ScoreAssessment:
    policy_version: str
    feature_schema_version: str
    as_of_unix_ms: int
    source_observed_at_unix_ms: int
    safety_decision: SafetyDecision
    setup_name: str
    setup_policy_version: str
    setup_state: SetupState
    regime_policy_version: str
    market_regime: MarketRegime
    safety_quality_score: float
    money_flow_score: float | None
    setup_quality_score: float
    liquidity_executability_score: float | None
    total_score: float | None
    findings: tuple[ScoreFinding, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("feature_schema_version", self.feature_schema_version)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_negative_int(
            "source_observed_at_unix_ms", self.source_observed_at_unix_ms
        )
        if not isinstance(self.safety_decision, SafetyDecision):
            raise ValueError("safety_decision must be a SafetyDecision")
        _require_non_empty_string("setup_name", self.setup_name)
        _require_non_empty_string("setup_policy_version", self.setup_policy_version)
        if not isinstance(self.setup_state, SetupState):
            raise ValueError("setup_state must be a SetupState")
        _require_non_empty_string("regime_policy_version", self.regime_policy_version)
        if not isinstance(self.market_regime, MarketRegime):
            raise ValueError("market_regime must be a MarketRegime")

        _require_score("safety_quality_score", self.safety_quality_score)
        _require_optional_score("money_flow_score", self.money_flow_score)
        _require_score("setup_quality_score", self.setup_quality_score)
        _require_optional_score(
            "liquidity_executability_score", self.liquidity_executability_score
        )
        _require_optional_score("total_score", self.total_score)

        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, ScoreFinding) for finding in self.findings
        ):
            raise ValueError("findings must be a tuple of ScoreFinding values")


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: float | int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: float | int) -> None:
    _require_finite(name, value)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_bounded_finite(
    name: str, value: float | int, lower: float, upper: float
) -> None:
    _require_finite(name, value)
    if value < lower or value > upper:
        raise ValueError(f"{name} must be within [{lower}, {upper}]")


def _require_score(name: str, value: float | int) -> None:
    _require_bounded_finite(name, value, 0.0, 100.0)


def _require_optional_score(name: str, value: float | int | None) -> None:
    if value is None:
        return
    _require_score(name, value)
