from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


FRESH_LAUNCH_SETUP_NAME = "fresh_launch_continuation"
FRESH_LAUNCH_CONFIRMATIONS_REQUIRED = 9
GRADUATION_BREAKOUT_SETUP_NAME = "graduation_breakout"
GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED = 8
FIRST_PULLBACK_SETUP_NAME = "first_pullback"
FIRST_PULLBACK_CONFIRMATIONS_REQUIRED = 9


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


class GraduationBreakoutReasonCode(StrEnum):
    SAFETY_NOT_PASS = "SAFETY_NOT_PASS"
    GRADUATION_NOT_VERIFIED = "GRADUATION_NOT_VERIFIED"
    GRADUATION_EVENT_NOT_PUMP = "GRADUATION_EVENT_NOT_PUMP"
    GRADUATION_VENUE_TRANSITION_INVALID = "GRADUATION_VENUE_TRANSITION_INVALID"
    GRADUATION_AFTER_AS_OF = "GRADUATION_AFTER_AS_OF"
    POST_GRADUATION_WINDOW_EXPIRED = "POST_GRADUATION_WINDOW_EXPIRED"
    SOURCE_DATA_TOO_OLD = "SOURCE_DATA_TOO_OLD"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    EXIT_PRICE_IMPACT_TOO_HIGH = "EXIT_PRICE_IMPACT_TOO_HIGH"
    MOVE_TOO_EXTENDED = "MOVE_TOO_EXTENDED"

    GRADUATION_TOO_RECENT = "GRADUATION_TOO_RECENT"
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
    LIQUIDITY_CHANGE_5M_UNKNOWN = "LIQUIDITY_CHANGE_5M_UNKNOWN"
    LIQUIDITY_CHANGE_5M_BELOW_MINIMUM = "LIQUIDITY_CHANGE_5M_BELOW_MINIMUM"
    DISTANCE_FROM_LOCAL_HIGH_UNKNOWN = "DISTANCE_FROM_LOCAL_HIGH_UNKNOWN"
    TOO_FAR_BELOW_LOCAL_HIGH = "TOO_FAR_BELOW_LOCAL_HIGH"
    RANGE_POSITION_UNKNOWN = "RANGE_POSITION_UNKNOWN"
    RANGE_POSITION_BELOW_MINIMUM = "RANGE_POSITION_BELOW_MINIMUM"

    ALL_CONFIRMATIONS_PASSED = "ALL_CONFIRMATIONS_PASSED"


class FirstPullbackReasonCode(StrEnum):
    SAFETY_NOT_PASS = "SAFETY_NOT_PASS"
    PULLBACK_AFTER_AS_OF = "PULLBACK_AFTER_AS_OF"
    PULLBACK_AFTER_MARKET_SOURCE = "PULLBACK_AFTER_MARKET_SOURCE"
    PULLBACK_WINDOW_EXPIRED = "PULLBACK_WINDOW_EXPIRED"
    INITIAL_IMPULSE_TOO_WEAK = "INITIAL_IMPULSE_TOO_WEAK"
    PULLBACK_TOO_DEEP = "PULLBACK_TOO_DEEP"
    PULLBACK_LOW_BROKEN = "PULLBACK_LOW_BROKEN"
    BREAKOUT_TOO_EXTENDED = "BREAKOUT_TOO_EXTENDED"
    SOURCE_DATA_TOO_OLD = "SOURCE_DATA_TOO_OLD"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    EXIT_PRICE_IMPACT_TOO_HIGH = "EXIT_PRICE_IMPACT_TOO_HIGH"
    MOVE_TOO_EXTENDED = "MOVE_TOO_EXTENDED"

    PULLBACK_NOT_OBSERVED = "PULLBACK_NOT_OBSERVED"
    INSUFFICIENT_STRUCTURE_SAMPLES = "INSUFFICIENT_STRUCTURE_SAMPLES"
    PULLBACK_TOO_RECENT = "PULLBACK_TOO_RECENT"
    PULLBACK_NOT_DEEP_ENOUGH = "PULLBACK_NOT_DEEP_ENOUGH"
    CURRENT_PRICE_UNKNOWN = "CURRENT_PRICE_UNKNOWN"
    LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN"
    EXIT_PRICE_IMPACT_UNKNOWN = "EXIT_PRICE_IMPACT_UNKNOWN"
    LIQUIDITY_RETENTION_UNKNOWN = "LIQUIDITY_RETENTION_UNKNOWN"
    TROUGH_BUY_FRACTION_UNKNOWN = "TROUGH_BUY_FRACTION_UNKNOWN"
    TX_COUNT_M5_UNKNOWN = "TX_COUNT_M5_UNKNOWN"
    TX_COUNT_M5_BELOW_MINIMUM = "TX_COUNT_M5_BELOW_MINIMUM"
    VOLUME_VELOCITY_UNKNOWN = "VOLUME_VELOCITY_UNKNOWN"
    VOLUME_VELOCITY_BELOW_MINIMUM = "VOLUME_VELOCITY_BELOW_MINIMUM"
    BUY_FRACTION_M5_UNKNOWN = "BUY_FRACTION_M5_UNKNOWN"
    BUY_FRACTION_M5_BELOW_MINIMUM = "BUY_FRACTION_M5_BELOW_MINIMUM"
    BUY_FRACTION_IMPROVEMENT_UNKNOWN = "BUY_FRACTION_IMPROVEMENT_UNKNOWN"
    BUY_FRACTION_IMPROVEMENT_BELOW_MINIMUM = (
        "BUY_FRACTION_IMPROVEMENT_BELOW_MINIMUM"
    )
    BUY_PRESSURE_ACCELERATION_UNKNOWN = "BUY_PRESSURE_ACCELERATION_UNKNOWN"
    BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM = (
        "BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM"
    )
    RETURN_1M_UNKNOWN = "RETURN_1M_UNKNOWN"
    RETURN_1M_BELOW_MINIMUM = "RETURN_1M_BELOW_MINIMUM"
    RECOVERY_FROM_TROUGH_UNKNOWN = "RECOVERY_FROM_TROUGH_UNKNOWN"
    RECOVERY_FROM_TROUGH_BELOW_MINIMUM = "RECOVERY_FROM_TROUGH_BELOW_MINIMUM"
    CURRENT_VS_PEAK_UNKNOWN = "CURRENT_VS_PEAK_UNKNOWN"
    CURRENT_VS_PEAK_BELOW_MINIMUM = "CURRENT_VS_PEAK_BELOW_MINIMUM"
    LIQUIDITY_RETENTION_BELOW_MINIMUM = "LIQUIDITY_RETENTION_BELOW_MINIMUM"

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


@dataclass(frozen=True, slots=True)
class GraduationContext:
    event_type: str
    provider: str
    mint: str
    quote_mint: str
    from_venue: str
    to_venue: str
    pool_address: str
    signature: str
    slot: int
    detected_at_unix_ms: int
    occurred_at_unix_ms: int | None

    def __post_init__(self) -> None:
        for name in (
            "event_type",
            "provider",
            "mint",
            "quote_mint",
            "from_venue",
            "to_venue",
            "pool_address",
            "signature",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("slot", self.slot)
        _require_non_negative_int("detected_at_unix_ms", self.detected_at_unix_ms)
        if self.occurred_at_unix_ms is not None:
            _require_non_negative_int("occurred_at_unix_ms", self.occurred_at_unix_ms)


@dataclass(frozen=True, slots=True)
class GraduationBreakoutFinding:
    code: GraduationBreakoutReasonCode
    message: str
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None


@dataclass(frozen=True, slots=True)
class GraduationBreakoutPolicy:
    version: str
    min_seconds_since_graduation: float
    max_seconds_since_graduation: float
    max_source_age_ms: int
    min_liquidity_usd: float
    max_exit_price_impact_pct: float
    min_tx_count_m5: int
    min_volume_velocity_ratio: float
    min_buy_fraction_m5: float
    min_buy_pressure_acceleration: float
    min_return_1m_pct: float
    max_return_1m_pct: float
    min_liquidity_change_5m_pct: float
    min_distance_from_local_high_pct: float
    min_range_position_pct: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)

        for name in (
            "min_seconds_since_graduation",
            "max_seconds_since_graduation",
            "min_liquidity_usd",
            "max_exit_price_impact_pct",
            "min_volume_velocity_ratio",
        ):
            _require_non_negative_finite(name, getattr(self, name))

        _require_non_negative_int("max_source_age_ms", self.max_source_age_ms)
        _require_non_negative_int("min_tx_count_m5", self.min_tx_count_m5)

        for name in (
            "min_buy_pressure_acceleration",
            "min_return_1m_pct",
            "max_return_1m_pct",
            "min_liquidity_change_5m_pct",
            "min_distance_from_local_high_pct",
        ):
            _require_finite(name, getattr(self, name))

        _require_bounded_finite("min_buy_fraction_m5", self.min_buy_fraction_m5, 0, 1)
        _require_bounded_finite(
            "min_range_position_pct", self.min_range_position_pct, 0, 100
        )

        if self.max_seconds_since_graduation <= self.min_seconds_since_graduation:
            raise ValueError(
                "max_seconds_since_graduation must be greater than "
                "min_seconds_since_graduation"
            )
        if self.min_distance_from_local_high_pct > 0:
            raise ValueError("min_distance_from_local_high_pct must be <= 0")
        if self.max_return_1m_pct < self.min_return_1m_pct:
            raise ValueError("max_return_1m_pct must be >= min_return_1m_pct")


@dataclass(frozen=True, slots=True)
class GraduationBreakoutAssessment:
    setup_name: str
    policy_version: str
    feature_schema_version: str
    as_of_unix_ms: int
    graduation_mint: str | None
    graduation_detected_at_unix_ms: int | None
    seconds_since_graduation: float | None
    state: SetupState
    confirmation_score: float
    confirmations_passed: int
    confirmations_required: int
    findings: tuple[GraduationBreakoutFinding, ...]

    def __post_init__(self) -> None:
        if self.setup_name != GRADUATION_BREAKOUT_SETUP_NAME:
            raise ValueError(
                f"setup_name must be {GRADUATION_BREAKOUT_SETUP_NAME!r}"
            )
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("feature_schema_version", self.feature_schema_version)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)

        if self.graduation_mint is not None:
            _require_non_empty_string("graduation_mint", self.graduation_mint)
        if self.graduation_detected_at_unix_ms is not None:
            _require_non_negative_int(
                "graduation_detected_at_unix_ms",
                self.graduation_detected_at_unix_ms,
            )
        if self.seconds_since_graduation is not None:
            _require_non_negative_finite(
                "seconds_since_graduation", self.seconds_since_graduation
            )

        if not isinstance(self.state, SetupState):
            raise ValueError("state must be a SetupState")
        _require_non_negative_int("confirmations_passed", self.confirmations_passed)
        _require_non_negative_int("confirmations_required", self.confirmations_required)
        if self.confirmations_required <= 0:
            raise ValueError("confirmations_required must be positive")
        if self.confirmations_passed > self.confirmations_required:
            raise ValueError("confirmations_passed cannot exceed confirmations_required")
        _require_bounded_finite("confirmation_score", self.confirmation_score, 0, 100)


@dataclass(frozen=True, slots=True)
class PullbackContext:
    impulse_started_at_unix_ms: int
    peak_at_unix_ms: int
    trough_at_unix_ms: int
    impulse_start_price_usd: float
    peak_price_usd: float
    trough_price_usd: float
    peak_liquidity_usd: float | None
    trough_liquidity_usd: float | None
    trough_buy_fraction_m5: float | None
    sample_count: int

    def __post_init__(self) -> None:
        _require_non_negative_int(
            "impulse_started_at_unix_ms", self.impulse_started_at_unix_ms
        )
        _require_non_negative_int("peak_at_unix_ms", self.peak_at_unix_ms)
        _require_non_negative_int("trough_at_unix_ms", self.trough_at_unix_ms)
        if not (
            self.impulse_started_at_unix_ms
            < self.peak_at_unix_ms
            < self.trough_at_unix_ms
        ):
            raise ValueError(
                "pullback chronology must satisfy impulse start < peak < trough"
            )

        _require_positive_finite("impulse_start_price_usd", self.impulse_start_price_usd)
        _require_positive_finite("peak_price_usd", self.peak_price_usd)
        _require_positive_finite("trough_price_usd", self.trough_price_usd)
        if self.peak_price_usd < self.impulse_start_price_usd:
            raise ValueError("peak_price_usd cannot be below impulse_start_price_usd")
        if self.peak_price_usd <= self.trough_price_usd:
            raise ValueError("peak_price_usd must be greater than trough_price_usd")

        if self.peak_liquidity_usd is not None:
            _require_non_negative_finite("peak_liquidity_usd", self.peak_liquidity_usd)
        if self.trough_liquidity_usd is not None:
            _require_non_negative_finite(
                "trough_liquidity_usd", self.trough_liquidity_usd
            )
        if self.trough_buy_fraction_m5 is not None:
            _require_bounded_finite(
                "trough_buy_fraction_m5", self.trough_buy_fraction_m5, 0, 1
            )

        _require_non_negative_int("sample_count", self.sample_count)
        if self.sample_count < 3:
            raise ValueError("sample_count must be at least 3")


@dataclass(frozen=True, slots=True)
class FirstPullbackFinding:
    code: FirstPullbackReasonCode
    message: str
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None


@dataclass(frozen=True, slots=True)
class FirstPullbackPolicy:
    version: str
    min_seconds_since_trough: float
    max_seconds_since_trough: float
    max_source_age_ms: int
    min_structure_samples: int
    min_initial_impulse_pct: float
    min_pullback_depth_pct: float
    max_pullback_depth_pct: float
    min_recovery_from_trough_pct: float
    min_current_vs_peak_pct: float
    max_current_vs_peak_pct: float
    min_liquidity_retention_pct: float
    min_liquidity_usd: float
    max_exit_price_impact_pct: float
    min_tx_count_m5: int
    min_volume_velocity_ratio: float
    min_buy_fraction_m5: float
    min_buy_fraction_improvement: float
    min_buy_pressure_acceleration: float
    min_return_1m_pct: float
    max_return_1m_pct: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)

        for name in (
            "min_seconds_since_trough",
            "max_seconds_since_trough",
            "min_initial_impulse_pct",
            "min_pullback_depth_pct",
            "max_pullback_depth_pct",
            "min_recovery_from_trough_pct",
            "min_liquidity_retention_pct",
            "min_liquidity_usd",
            "max_exit_price_impact_pct",
            "min_volume_velocity_ratio",
        ):
            _require_non_negative_finite(name, getattr(self, name))

        _require_non_negative_int("max_source_age_ms", self.max_source_age_ms)
        _require_non_negative_int("min_structure_samples", self.min_structure_samples)
        _require_non_negative_int("min_tx_count_m5", self.min_tx_count_m5)
        if self.min_structure_samples < 3:
            raise ValueError("min_structure_samples must be at least 3")

        for name in (
            "min_current_vs_peak_pct",
            "max_current_vs_peak_pct",
            "min_buy_fraction_improvement",
            "min_buy_pressure_acceleration",
            "min_return_1m_pct",
            "max_return_1m_pct",
        ):
            _require_finite(name, getattr(self, name))

        _require_bounded_finite("min_buy_fraction_m5", self.min_buy_fraction_m5, 0, 1)

        if self.max_seconds_since_trough <= self.min_seconds_since_trough:
            raise ValueError(
                "max_seconds_since_trough must be greater than min_seconds_since_trough"
            )
        if self.max_pullback_depth_pct >= 100:
            raise ValueError("max_pullback_depth_pct must be less than 100")
        if self.max_pullback_depth_pct < self.min_pullback_depth_pct:
            raise ValueError(
                "max_pullback_depth_pct must be >= min_pullback_depth_pct"
            )
        if self.max_current_vs_peak_pct < self.min_current_vs_peak_pct:
            raise ValueError(
                "max_current_vs_peak_pct must be >= min_current_vs_peak_pct"
            )
        if self.max_return_1m_pct < self.min_return_1m_pct:
            raise ValueError("max_return_1m_pct must be >= min_return_1m_pct")


@dataclass(frozen=True, slots=True)
class FirstPullbackAssessment:
    setup_name: str
    policy_version: str
    feature_schema_version: str
    as_of_unix_ms: int
    state: SetupState
    seconds_since_trough: float | None
    impulse_return_pct: float | None
    pullback_depth_pct: float | None
    recovery_from_trough_pct: float | None
    current_vs_peak_pct: float | None
    liquidity_retention_pct: float | None
    buy_fraction_improvement: float | None
    confirmation_score: float
    confirmations_passed: int
    confirmations_required: int
    findings: tuple[FirstPullbackFinding, ...]

    def __post_init__(self) -> None:
        if self.setup_name != FIRST_PULLBACK_SETUP_NAME:
            raise ValueError(f"setup_name must be {FIRST_PULLBACK_SETUP_NAME!r}")
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("feature_schema_version", self.feature_schema_version)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.state, SetupState):
            raise ValueError("state must be a SetupState")

        for name in (
            "seconds_since_trough",
            "impulse_return_pct",
            "pullback_depth_pct",
            "recovery_from_trough_pct",
            "liquidity_retention_pct",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_finite(name, value)
        for name in ("current_vs_peak_pct", "buy_fraction_improvement"):
            value = getattr(self, name)
            if value is not None:
                _require_finite(name, value)

        _require_non_negative_int("confirmations_passed", self.confirmations_passed)
        _require_non_negative_int("confirmations_required", self.confirmations_required)
        if self.confirmations_required <= 0:
            raise ValueError("confirmations_required must be positive")
        if self.confirmations_passed > self.confirmations_required:
            raise ValueError("confirmations_passed cannot exceed confirmations_required")
        _require_bounded_finite("confirmation_score", self.confirmation_score, 0, 100)


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: float) -> None:
    _require_finite(name, value)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_positive_finite(name: str, value: float) -> None:
    _require_finite(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bounded_finite(name: str, value: float, lower: float, upper: float) -> None:
    _require_finite(name, value)
    if value < lower or value > upper:
        raise ValueError(f"{name} must be within [{lower}, {upper}]")
