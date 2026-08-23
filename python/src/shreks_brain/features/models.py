from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.safety import SafetyAssessment, SafetyDecision


FEATURE_SCHEMA_VERSION = "b2-v1"

ANCHOR_1M_MIN_AGE_MS = 60_000
ANCHOR_1M_MAX_AGE_MS = 90_000
ANCHOR_5M_MIN_AGE_MS = 300_000
ANCHOR_5M_MAX_AGE_MS = 360_000
ANCHOR_15M_MIN_AGE_MS = 900_000
ANCHOR_15M_MAX_AGE_MS = 1_020_000


@dataclass(frozen=True, slots=True)
class MarketFeaturePoint:
    observed_at_unix_ms: int
    price_usd: float | None
    liquidity_usd: float | None
    volume_m5_usd: float | None
    volume_h1_usd: float | None
    buys_m5: int | None
    sells_m5: int | None
    buys_h1: int | None
    sells_h1: int | None

    def __post_init__(self) -> None:
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_non_negative_finite("price_usd", self.price_usd)
        _require_non_negative_finite("liquidity_usd", self.liquidity_usd)
        _require_non_negative_finite("volume_m5_usd", self.volume_m5_usd)
        _require_non_negative_finite("volume_h1_usd", self.volume_h1_usd)
        _require_optional_non_negative_int("buys_m5", self.buys_m5)
        _require_optional_non_negative_int("sells_m5", self.sells_m5)
        _require_optional_non_negative_int("buys_h1", self.buys_h1)
        _require_optional_non_negative_int("sells_h1", self.sells_h1)


@dataclass(frozen=True, slots=True)
class FeatureInputs:
    as_of_unix_ms: int
    current: MarketFeaturePoint
    one_minute_ago: MarketFeaturePoint | None
    five_minutes_ago: MarketFeaturePoint | None
    fifteen_minutes_ago: MarketFeaturePoint | None
    pair_created_at_unix_ms: int | None
    local_high_price_usd: float | None
    local_low_price_usd: float | None
    exit_price_impact_pct: float | None
    safety: SafetyAssessment

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.current, MarketFeaturePoint):
            raise ValueError("current must be a MarketFeaturePoint")
        if self.current.observed_at_unix_ms > self.as_of_unix_ms:
            raise ValueError("current observation cannot be later than as_of_unix_ms")

        _validate_anchor(
            "one_minute_ago",
            self.one_minute_ago,
            as_of_unix_ms=self.as_of_unix_ms,
            min_age_ms=ANCHOR_1M_MIN_AGE_MS,
            max_age_ms=ANCHOR_1M_MAX_AGE_MS,
        )
        _validate_anchor(
            "five_minutes_ago",
            self.five_minutes_ago,
            as_of_unix_ms=self.as_of_unix_ms,
            min_age_ms=ANCHOR_5M_MIN_AGE_MS,
            max_age_ms=ANCHOR_5M_MAX_AGE_MS,
        )
        _validate_anchor(
            "fifteen_minutes_ago",
            self.fifteen_minutes_ago,
            as_of_unix_ms=self.as_of_unix_ms,
            min_age_ms=ANCHOR_15M_MIN_AGE_MS,
            max_age_ms=ANCHOR_15M_MAX_AGE_MS,
        )

        if self.pair_created_at_unix_ms is not None:
            _require_non_negative_int(
                "pair_created_at_unix_ms", self.pair_created_at_unix_ms
            )
            if self.pair_created_at_unix_ms > self.current.observed_at_unix_ms:
                raise ValueError(
                    "pair_created_at_unix_ms cannot be later than the current observation"
                )
            if self.pair_created_at_unix_ms > self.as_of_unix_ms:
                raise ValueError(
                    "pair_created_at_unix_ms cannot be later than as_of_unix_ms"
                )

        _require_positive_finite("local_high_price_usd", self.local_high_price_usd)
        _require_positive_finite("local_low_price_usd", self.local_low_price_usd)
        if (
            self.local_high_price_usd is not None
            and self.local_low_price_usd is not None
            and self.local_high_price_usd < self.local_low_price_usd
        ):
            raise ValueError("local_high_price_usd cannot be below local_low_price_usd")

        _require_non_negative_finite(
            "exit_price_impact_pct", self.exit_price_impact_pct
        )

        if not isinstance(self.safety, SafetyAssessment):
            raise ValueError("safety must be a SafetyAssessment")
        if self.safety.as_of_unix_ms != self.as_of_unix_ms:
            raise ValueError(
                "safety.as_of_unix_ms must equal FeatureInputs.as_of_unix_ms"
            )


@dataclass(frozen=True, slots=True)
class FeatureVector:
    schema_version: str
    as_of_unix_ms: int
    source_observed_at_unix_ms: int
    source_age_ms: int
    safety_policy_version: str
    safety_decision: SafetyDecision

    token_age_seconds: float | None
    price_usd: float | None
    liquidity_usd: float | None
    liquidity_change_5m_pct: float | None
    exit_price_impact_pct: float | None

    volume_m5_usd: float | None
    volume_h1_usd: float | None
    volume_velocity_ratio: float | None
    tx_count_m5: int | None
    tx_count_h1: int | None

    buy_fraction_m5: float | None
    buy_fraction_h1: float | None
    buy_sell_ratio_m5: float | None
    buy_sell_ratio_h1: float | None
    buy_pressure_acceleration: float | None

    return_1m_pct: float | None
    return_5m_pct: float | None
    return_15m_pct: float | None
    momentum_acceleration_1m_vs_5m: float | None

    distance_from_local_high_pct: float | None
    range_position_pct: float | None

    safety_soft_finding_count: int
    safety_liquidity_weak: bool
    safety_holder_concentration_elevated: bool
    safety_creator_concentration_elevated: bool
    safety_exit_price_impact_elevated: bool

    missing_features: tuple[str, ...]


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_non_negative_int(name: str, value: int | None) -> None:
    if value is None:
        return
    _require_non_negative_int(name, value)


def _require_non_negative_finite(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def _require_positive_finite(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")


def _validate_anchor(
    name: str,
    point: MarketFeaturePoint | None,
    *,
    as_of_unix_ms: int,
    min_age_ms: int,
    max_age_ms: int,
) -> None:
    if point is None:
        return
    if not isinstance(point, MarketFeaturePoint):
        raise ValueError(f"{name} must be a MarketFeaturePoint or None")
    age_ms = as_of_unix_ms - point.observed_at_unix_ms
    if age_ms < min_age_ms or age_ms > max_age_ms:
        raise ValueError(
            f"{name} must be between {min_age_ms} and {max_age_ms} ms old"
        )
