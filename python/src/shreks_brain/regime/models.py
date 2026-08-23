from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


class MarketRegime(StrEnum):
    HOT = "HOT"
    NORMAL = "NORMAL"
    WEAK = "WEAK"
    DEAD = "DEAD"


class RegimeReasonCode(StrEnum):
    SOURCE_AFTER_AS_OF = "SOURCE_AFTER_AS_OF"
    SOURCE_DATA_TOO_OLD = "SOURCE_DATA_TOO_OLD"
    WINDOW_TOO_SHORT = "WINDOW_TOO_SHORT"
    NO_CANDIDATES = "NO_CANDIDATES"
    CANDIDATE_SAMPLE_TOO_SMALL = "CANDIDATE_SAMPLE_TOO_SMALL"
    MEDIAN_LIQUIDITY_UNKNOWN = "MEDIAN_LIQUIDITY_UNKNOWN"
    MEDIAN_VOLUME_M5_UNKNOWN = "MEDIAN_VOLUME_M5_UNKNOWN"
    OPPORTUNITY_RATE_DEAD = "OPPORTUNITY_RATE_DEAD"
    EXECUTABLE_FRACTION_DEAD = "EXECUTABLE_FRACTION_DEAD"
    OPPORTUNITY_RATE_WEAK = "OPPORTUNITY_RATE_WEAK"
    EXECUTABLE_FRACTION_WEAK = "EXECUTABLE_FRACTION_WEAK"
    LIQUIDITY_WEAK = "LIQUIDITY_WEAK"
    VOLUME_WEAK = "VOLUME_WEAK"
    ALL_HOT_MARKET_THRESHOLDS_PASSED = "ALL_HOT_MARKET_THRESHOLDS_PASSED"
    NORMAL_MIXED_MARKET = "NORMAL_MIXED_MARKET"
    PERFORMANCE_UNAVAILABLE = "PERFORMANCE_UNAVAILABLE"
    PERFORMANCE_AFTER_AS_OF = "PERFORMANCE_AFTER_AS_OF"
    PERFORMANCE_AFTER_MARKET_SOURCE = "PERFORMANCE_AFTER_MARKET_SOURCE"
    PERFORMANCE_SAMPLE_INSUFFICIENT = "PERFORMANCE_SAMPLE_INSUFFICIENT"
    PERFORMANCE_EXPECTANCY_UNKNOWN = "PERFORMANCE_EXPECTANCY_UNKNOWN"
    PERFORMANCE_EXPECTANCY_DEAD = "PERFORMANCE_EXPECTANCY_DEAD"
    PERFORMANCE_EXPECTANCY_WEAK = "PERFORMANCE_EXPECTANCY_WEAK"


@dataclass(frozen=True, slots=True)
class RegimeMarketWindow:
    as_of_unix_ms: int
    source_observed_at_unix_ms: int
    window_started_at_unix_ms: int
    candidate_count: int
    executable_candidate_count: int
    median_liquidity_usd: float | None
    median_volume_m5_usd: float | None

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_negative_int(
            "source_observed_at_unix_ms", self.source_observed_at_unix_ms
        )
        _require_non_negative_int(
            "window_started_at_unix_ms", self.window_started_at_unix_ms
        )
        if self.window_started_at_unix_ms >= self.source_observed_at_unix_ms:
            raise ValueError(
                "window_started_at_unix_ms must be earlier than "
                "source_observed_at_unix_ms"
            )

        _require_non_negative_int("candidate_count", self.candidate_count)
        _require_non_negative_int(
            "executable_candidate_count", self.executable_candidate_count
        )
        if self.executable_candidate_count > self.candidate_count:
            raise ValueError(
                "executable_candidate_count cannot exceed candidate_count"
            )

        _require_optional_non_negative_finite(
            "median_liquidity_usd", self.median_liquidity_usd
        )
        _require_optional_non_negative_finite(
            "median_volume_m5_usd", self.median_volume_m5_usd
        )


@dataclass(frozen=True, slots=True)
class RecentStrategyPerformance:
    observed_through_unix_ms: int
    closed_trade_count: int
    net_expectancy_after_costs_pct: float | None

    def __post_init__(self) -> None:
        _require_non_negative_int(
            "observed_through_unix_ms", self.observed_through_unix_ms
        )
        _require_non_negative_int("closed_trade_count", self.closed_trade_count)
        _require_optional_finite(
            "net_expectancy_after_costs_pct",
            self.net_expectancy_after_costs_pct,
        )


@dataclass(frozen=True, slots=True)
class RegimePolicy:
    version: str
    max_source_age_ms: int
    min_window_seconds: float
    min_candidate_samples: int

    dead_max_candidate_rate_per_hour: float
    weak_min_candidate_rate_per_hour: float
    hot_min_candidate_rate_per_hour: float

    dead_max_executable_fraction: float
    weak_min_executable_fraction: float
    hot_min_executable_fraction: float

    weak_min_median_liquidity_usd: float
    hot_min_median_liquidity_usd: float
    weak_min_median_volume_m5_usd: float
    hot_min_median_volume_m5_usd: float

    min_performance_sample_count: int
    dead_performance_expectancy_pct: float
    weak_performance_expectancy_pct: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_non_negative_int("max_source_age_ms", self.max_source_age_ms)
        _require_positive_finite("min_window_seconds", self.min_window_seconds)
        _require_positive_int("min_candidate_samples", self.min_candidate_samples)

        for name in (
            "dead_max_candidate_rate_per_hour",
            "weak_min_candidate_rate_per_hour",
            "hot_min_candidate_rate_per_hour",
            "weak_min_median_liquidity_usd",
            "hot_min_median_liquidity_usd",
            "weak_min_median_volume_m5_usd",
            "hot_min_median_volume_m5_usd",
        ):
            _require_non_negative_finite(name, getattr(self, name))

        for name in (
            "dead_max_executable_fraction",
            "weak_min_executable_fraction",
            "hot_min_executable_fraction",
        ):
            _require_bounded_finite(name, getattr(self, name), 0.0, 1.0)

        _require_positive_int(
            "min_performance_sample_count", self.min_performance_sample_count
        )
        _require_finite(
            "dead_performance_expectancy_pct",
            self.dead_performance_expectancy_pct,
        )
        _require_finite(
            "weak_performance_expectancy_pct",
            self.weak_performance_expectancy_pct,
        )

        if not (
            self.dead_max_candidate_rate_per_hour
            <= self.weak_min_candidate_rate_per_hour
            <= self.hot_min_candidate_rate_per_hour
        ):
            raise ValueError(
                "candidate-rate thresholds must satisfy dead <= weak <= hot"
            )
        if not (
            self.dead_max_executable_fraction
            <= self.weak_min_executable_fraction
            <= self.hot_min_executable_fraction
        ):
            raise ValueError(
                "executable-fraction thresholds must satisfy dead <= weak <= hot"
            )
        if self.weak_min_median_liquidity_usd > self.hot_min_median_liquidity_usd:
            raise ValueError("liquidity thresholds must satisfy weak <= hot")
        if self.weak_min_median_volume_m5_usd > self.hot_min_median_volume_m5_usd:
            raise ValueError("volume thresholds must satisfy weak <= hot")
        if self.dead_performance_expectancy_pct > self.weak_performance_expectancy_pct:
            raise ValueError(
                "performance expectancy thresholds must satisfy dead <= weak"
            )


@dataclass(frozen=True, slots=True)
class RegimeFinding:
    code: RegimeReasonCode
    message: str
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, RegimeReasonCode):
            raise ValueError("code must be a RegimeReasonCode")
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
class RegimeAssessment:
    policy_version: str
    as_of_unix_ms: int
    source_observed_at_unix_ms: int
    window_started_at_unix_ms: int
    source_age_ms: int | None
    window_seconds: float
    candidate_count: int
    candidate_rate_per_hour: float
    executable_fraction: float | None
    median_liquidity_usd: float | None
    median_volume_m5_usd: float | None
    base_regime: MarketRegime
    regime: MarketRegime
    performance_sample_count: int | None
    performance_net_expectancy_after_costs_pct: float | None
    performance_applied: bool
    findings: tuple[RegimeFinding, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_negative_int(
            "source_observed_at_unix_ms", self.source_observed_at_unix_ms
        )
        _require_non_negative_int(
            "window_started_at_unix_ms", self.window_started_at_unix_ms
        )
        if self.window_started_at_unix_ms >= self.source_observed_at_unix_ms:
            raise ValueError(
                "window_started_at_unix_ms must be earlier than "
                "source_observed_at_unix_ms"
            )

        if self.source_age_ms is not None:
            _require_non_negative_int("source_age_ms", self.source_age_ms)
        _require_positive_finite("window_seconds", self.window_seconds)
        _require_non_negative_int("candidate_count", self.candidate_count)
        _require_non_negative_finite(
            "candidate_rate_per_hour", self.candidate_rate_per_hour
        )
        if self.executable_fraction is not None:
            _require_bounded_finite(
                "executable_fraction", self.executable_fraction, 0.0, 1.0
            )
        _require_optional_non_negative_finite(
            "median_liquidity_usd", self.median_liquidity_usd
        )
        _require_optional_non_negative_finite(
            "median_volume_m5_usd", self.median_volume_m5_usd
        )

        if not isinstance(self.base_regime, MarketRegime):
            raise ValueError("base_regime must be a MarketRegime")
        if not isinstance(self.regime, MarketRegime):
            raise ValueError("regime must be a MarketRegime")

        if self.performance_sample_count is not None:
            _require_non_negative_int(
                "performance_sample_count", self.performance_sample_count
            )
        _require_optional_finite(
            "performance_net_expectancy_after_costs_pct",
            self.performance_net_expectancy_after_costs_pct,
        )
        if not isinstance(self.performance_applied, bool):
            raise ValueError("performance_applied must be a boolean")
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, RegimeFinding) for finding in self.findings
        ):
            raise ValueError("findings must be a tuple of RegimeFinding values")


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: int) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_finite(name: str, value: float | int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: float | int) -> None:
    _require_finite(name, value)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_positive_finite(name: str, value: float | int) -> None:
    _require_finite(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_optional_finite(name: str, value: float | int | None) -> None:
    if value is None:
        return
    _require_finite(name, value)


def _require_optional_non_negative_finite(
    name: str, value: float | int | None
) -> None:
    if value is None:
        return
    _require_non_negative_finite(name, value)


def _require_bounded_finite(
    name: str, value: float | int, lower: float, upper: float
) -> None:
    _require_finite(name, value)
    if value < lower or value > upper:
        raise ValueError(f"{name} must be within [{lower}, {upper}]")
