from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


FRESH_LAUNCH_SETUP_NAME = "fresh_launch_continuation"
FRESH_LAUNCH_CONFIRMATIONS_REQUIRED = 9


class SetupState(StrEnum):
    BLOCKED = "BLOCKED"
    WATCH = "WATCH"
    READY = "READY"


class FreshLaunchReasonCode(StrEnum):
    SAFETY_NOT_PASS = "SAFETY_NOT_PASS"
    SETUP_WINDOW_EXPIRED = "SETUP_WINDOW_EXPIRED"
    SOURCE_DATA_TOO_OLD = "SOURCE_DATA_TOO_OLD"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    EXIT_PRICE_IMPACT_TOO_HIGH = "EXIT_PRICE_IMPACT_TOO_HIGH"
    MOVE_TOO_EXTENDED = "MOVE_TOO_EXTENDED"

    SETUP_TOO_YOUNG = "SETUP_TOO_YOUNG"
    TOKEN_AGE_UNKNOWN = "TOKEN_AGE_UNKNOWN"
    SOURCE_AGE_UNKNOWN = "SOURCE_AGE_UNKNOWN"
    LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN"
    EXIT_PRICE_IMPACT_UNKNOWN = "EXIT_PRICE_IMPACT_UNKNOWN"
    TX_COUNT_M5_UNKNOWN = "TX_COUNT_M5_UNKNOWN"
    TX_COUNT_M5_BELOW_MINIMUM = "TX_COUNT_M5_BELOW_MINIMUM"
    VOLUME_VELOCITY_UNKNOWN = "VOLUME_VELOCITY_UNKNOWN"
    VOLUME_VELOCITY_BELOW_MINIMUM = "VOLUME_VELOCITY_BELOW_MINIMUM"
    BUY_FRACTION_M5_UNKNOWN = "BUY_FRACTION_M5_UNKNOWN"
    BUY_FRACTION_M5_BELOW_MINIMUM = "BUY_FRACTION_M5_BELOW_MINIMUM"
    BUY_PRESSURE_ACCELERATION_UNKNOWN = "BUY_PRESSURE_ACCELERATION_UNKNOWN"
    BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM = (
        "BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM"
    )
    RETURN_1M_UNKNOWN = "RETURN_1M_UNKNOWN"
    RETURN_1M_BELOW_MINIMUM = "RETURN_1M_BELOW_MINIMUM"
    RETURN_5M_UNKNOWN = "RETURN_5M_UNKNOWN"
    RETURN_5M_BELOW_MINIMUM = "RETURN_5M_BELOW_MINIMUM"
    LIQUIDITY_CHANGE_5M_UNKNOWN = "LIQUIDITY_CHANGE_5M_UNKNOWN"
    LIQUIDITY_CHANGE_5M_BELOW_MINIMUM = "LIQUIDITY_CHANGE_5M_BELOW_MINIMUM"
    DISTANCE_FROM_LOCAL_HIGH_UNKNOWN = "DISTANCE_FROM_LOCAL_HIGH_UNKNOWN"
    TOO_FAR_BELOW_LOCAL_HIGH = "TOO_FAR_BELOW_LOCAL_HIGH"
    RANGE_POSITION_UNKNOWN = "RANGE_POSITION_UNKNOWN"
    RANGE_POSITION_BELOW_MINIMUM = "RANGE_POSITION_BELOW_MINIMUM"

    ALL_CONFIRMATIONS_PASSED = "ALL_CONFIRMATIONS_PASSED"


@dataclass(frozen=True, slots=True)
class SetupFinding:
    code: FreshLaunchReasonCode
    message: str
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None


@dataclass(frozen=True, slots=True)
class FreshLaunchPolicy:
    version: str
    min_age_seconds: float
    max_age_seconds: float
    max_source_age_ms: int
    min_liquidity_usd: float
    max_exit_price_impact_pct: float
    max_return_5m_pct: float
    min_tx_count_m5: int
    min_volume_velocity_ratio: float
    min_buy_fraction_m5: float
    min_buy_pressure_acceleration: float
    min_return_1m_pct: float
    min_return_5m_pct: float
    min_liquidity_change_5m_pct: float
    min_distance_from_local_high_pct: float
    min_range_position_pct: float

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string")

        for name in (
            "min_age_seconds",
            "max_age_seconds",
            "min_liquidity_usd",
            "max_exit_price_impact_pct",
            "max_return_5m_pct",
            "min_volume_velocity_ratio",
        ):
            _require_non_negative_finite(name, getattr(self, name))

        _require_non_negative_int("max_source_age_ms", self.max_source_age_ms)
        _require_non_negative_int("min_tx_count_m5", self.min_tx_count_m5)

        for name in (
            "min_buy_pressure_acceleration",
            "min_return_1m_pct",
            "min_return_5m_pct",
            "min_liquidity_change_5m_pct",
            "min_distance_from_local_high_pct",
        ):
            _require_finite(name, getattr(self, name))

        _require_bounded_finite("min_buy_fraction_m5", self.min_buy_fraction_m5, 0, 1)
        _require_bounded_finite(
            "min_range_position_pct", self.min_range_position_pct, 0, 100
        )

        if self.max_age_seconds <= self.min_age_seconds:
            raise ValueError("max_age_seconds must be greater than min_age_seconds")
        if self.min_distance_from_local_high_pct > 0:
            raise ValueError("min_distance_from_local_high_pct must be <= 0")
        if self.max_return_5m_pct < self.min_return_5m_pct:
            raise ValueError("max_return_5m_pct must be >= min_return_5m_pct")


@dataclass(frozen=True, slots=True)
class FreshLaunchAssessment:
    setup_name: str
    policy_version: str
    feature_schema_version: str
    as_of_unix_ms: int
    state: SetupState
    confirmation_score: float
    confirmations_passed: int
    confirmations_required: int
    findings: tuple[SetupFinding, ...]

    def __post_init__(self) -> None:
        if self.setup_name != FRESH_LAUNCH_SETUP_NAME:
            raise ValueError(f"setup_name must be {FRESH_LAUNCH_SETUP_NAME!r}")
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        if not isinstance(self.feature_schema_version, str) or not self.feature_schema_version.strip():
            raise ValueError("feature_schema_version must be a non-empty string")
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_negative_int("confirmations_passed", self.confirmations_passed)
        _require_non_negative_int("confirmations_required", self.confirmations_required)
        if self.confirmations_required <= 0:
            raise ValueError("confirmations_required must be positive")
        if self.confirmations_passed > self.confirmations_required:
            raise ValueError("confirmations_passed cannot exceed confirmations_required")
        _require_bounded_finite("confirmation_score", self.confirmation_score, 0, 100)


def _require_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: float) -> None:
    _require_finite(name, value)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bounded_finite(name: str, value: float, lower: float, upper: float) -> None:
    _require_finite(name, value)
    if value < lower or value > upper:
        raise ValueError(f"{name} must be within [{lower}, {upper}]")
