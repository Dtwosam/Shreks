from __future__ import annotations

from dataclasses import dataclass
import math


OBSERVER_MARKET_SCHEMA_VERSION = "e13-observer-market-v1"


@dataclass(frozen=True, slots=True)
class ObserverMarketReadPolicy:
    version: str
    source_priority: tuple[str, ...]
    max_current_age_ms: int
    local_range_lookback_ms: int

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        if not isinstance(self.source_priority, tuple) or not self.source_priority:
            raise ValueError("source_priority must be a non-empty tuple")
        if not all(isinstance(value, str) and value.strip() for value in self.source_priority):
            raise ValueError("source_priority must contain only non-empty strings")
        if len(set(self.source_priority)) != len(self.source_priority):
            raise ValueError("source_priority must not contain duplicates")
        _require_non_negative_int("max_current_age_ms", self.max_current_age_ms)
        _require_positive_int("local_range_lookback_ms", self.local_range_lookback_ms)


@dataclass(frozen=True, slots=True)
class ObserverCandidateIdentity:
    candidate_id: int
    mint: str
    pair_address: str
    discovery_source: str
    discovered_at_unix_ms: int
    venue: str | None

    def __post_init__(self) -> None:
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_empty_string("mint", self.mint)
        _require_string("pair_address", self.pair_address)
        _require_non_empty_string("discovery_source", self.discovery_source)
        _require_non_negative_int("discovered_at_unix_ms", self.discovered_at_unix_ms)
        _require_optional_non_empty_string("venue", self.venue)


@dataclass(frozen=True, slots=True)
class ObserverMarketSnapshot:
    row_id: int
    candidate_id: int
    observed_at_unix_ms: int
    source: str
    source_observed_at_unix_ms: int | None
    venue: str
    pair_address: str
    price_usd: float | None
    liquidity_usd: float | None
    volume_m5_usd: float | None
    volume_h1_usd: float | None
    buys_m5: int | None
    sells_m5: int | None
    buys_h1: int | None
    sells_h1: int | None
    pair_created_at_unix_ms: int | None

    def __post_init__(self) -> None:
        _require_positive_int("row_id", self.row_id)
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_non_empty_string("source", self.source)
        _require_optional_non_negative_int(
            "source_observed_at_unix_ms", self.source_observed_at_unix_ms
        )
        if (
            self.source_observed_at_unix_ms is not None
            and self.source_observed_at_unix_ms > self.observed_at_unix_ms
        ):
            raise ValueError(
                "source_observed_at_unix_ms cannot be later than observed_at_unix_ms"
            )
        _require_non_empty_string("venue", self.venue)
        _require_string("pair_address", self.pair_address)
        _require_optional_non_negative_finite("price_usd", self.price_usd)
        _require_optional_non_negative_finite("liquidity_usd", self.liquidity_usd)
        _require_optional_non_negative_finite("volume_m5_usd", self.volume_m5_usd)
        _require_optional_non_negative_finite("volume_h1_usd", self.volume_h1_usd)
        _require_optional_non_negative_int("buys_m5", self.buys_m5)
        _require_optional_non_negative_int("sells_m5", self.sells_m5)
        _require_optional_non_negative_int("buys_h1", self.buys_h1)
        _require_optional_non_negative_int("sells_h1", self.sells_h1)
        _require_optional_non_negative_int(
            "pair_created_at_unix_ms", self.pair_created_at_unix_ms
        )
        if (
            self.pair_created_at_unix_ms is not None
            and self.pair_created_at_unix_ms > self.observed_at_unix_ms
        ):
            raise ValueError(
                "pair_created_at_unix_ms cannot be later than observed_at_unix_ms"
            )


@dataclass(frozen=True, slots=True)
class ObservedMarketWindow:
    schema_version: str
    policy_version: str
    candidate: ObserverCandidateIdentity
    as_of_unix_ms: int
    selected_source: str
    selected_pair_address: str
    current: ObserverMarketSnapshot
    one_minute_ago: ObserverMarketSnapshot | None
    five_minutes_ago: ObserverMarketSnapshot | None
    fifteen_minutes_ago: ObserverMarketSnapshot | None
    pair_created_at_unix_ms: int | None
    local_high_price_usd: float | None
    local_low_price_usd: float | None

    def __post_init__(self) -> None:
        if self.schema_version != OBSERVER_MARKET_SCHEMA_VERSION:
            raise ValueError("unsupported observer market schema version")
        _require_non_empty_string("policy_version", self.policy_version)
        if type(self.candidate) is not ObserverCandidateIdentity:
            raise ValueError("candidate must be an ObserverCandidateIdentity")
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_empty_string("selected_source", self.selected_source)
        _require_string("selected_pair_address", self.selected_pair_address)
        if type(self.current) is not ObserverMarketSnapshot:
            raise ValueError("current must be an ObserverMarketSnapshot")

        self._validate_snapshot("current", self.current)
        for name, snapshot in (
            ("one_minute_ago", self.one_minute_ago),
            ("five_minutes_ago", self.five_minutes_ago),
            ("fifteen_minutes_ago", self.fifteen_minutes_ago),
        ):
            if snapshot is None:
                continue
            if type(snapshot) is not ObserverMarketSnapshot:
                raise ValueError(f"{name} must be an ObserverMarketSnapshot or None")
            self._validate_snapshot(name, snapshot)

        _require_optional_non_negative_int(
            "pair_created_at_unix_ms", self.pair_created_at_unix_ms
        )
        if (
            self.pair_created_at_unix_ms is not None
            and self.pair_created_at_unix_ms > self.current.observed_at_unix_ms
        ):
            raise ValueError(
                "pair_created_at_unix_ms cannot be later than current observation"
            )
        if (
            self.current.pair_created_at_unix_ms is not None
            and self.pair_created_at_unix_ms != self.current.pair_created_at_unix_ms
        ):
            raise ValueError("current pair_created_at_unix_ms must be authoritative")

        _require_optional_positive_finite(
            "local_high_price_usd", self.local_high_price_usd
        )
        _require_optional_positive_finite(
            "local_low_price_usd", self.local_low_price_usd
        )
        if (
            self.local_high_price_usd is not None
            and self.local_low_price_usd is not None
            and self.local_high_price_usd < self.local_low_price_usd
        ):
            raise ValueError("local_high_price_usd cannot be below local_low_price_usd")

    def _validate_snapshot(self, name: str, snapshot: ObserverMarketSnapshot) -> None:
        if snapshot.candidate_id != self.candidate.candidate_id:
            raise ValueError(f"{name} candidate_id does not match candidate")
        if snapshot.source != self.selected_source:
            raise ValueError(f"{name} source does not match selected_source")
        if snapshot.pair_address != self.selected_pair_address:
            raise ValueError(f"{name} pair_address does not match selected_pair_address")
        if snapshot.observed_at_unix_ms > self.as_of_unix_ms:
            raise ValueError(f"{name} observation cannot be later than as_of_unix_ms")


def _require_string(name: str, value: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_non_empty_string(name: str, value: str | None) -> None:
    if value is None:
        return
    _require_non_empty_string(name, value)


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_optional_non_negative_int(name: str, value: int | None) -> None:
    if value is None:
        return
    _require_non_negative_int(name, value)


def _require_optional_non_negative_finite(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def _require_optional_positive_finite(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
