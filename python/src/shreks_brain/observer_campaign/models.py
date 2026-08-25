from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import math


OBSERVER_PAPER_CAMPAIGN_SCHEMA_VERSION = "e15-observer-paper-v1"
_MAX_U64 = 2**64 - 1


class ObserverPaperQuotePurpose(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"


@dataclass(frozen=True, slots=True)
class ObserverPaperQuoteAsset:
    mint: str
    decimals: int
    usd_per_token: float

    def __post_init__(self) -> None:
        _require_non_empty_string("mint", self.mint)
        _require_decimals("decimals", self.decimals)
        _require_positive_finite("usd_per_token", self.usd_per_token)


@dataclass(frozen=True, slots=True)
class ObserverPaperQuoteIdentity:
    candidate_id: int
    purpose: ObserverPaperQuotePurpose
    provider: str
    probe_policy_version: str
    input_mint: str
    output_mint: str
    taker: str
    input_amount: int
    slippage_bps: int

    def __post_init__(self) -> None:
        _require_positive_int("candidate_id", self.candidate_id)
        if type(self.purpose) is not ObserverPaperQuotePurpose:
            raise ValueError("purpose must be an ObserverPaperQuotePurpose")
        _require_non_empty_string("provider", self.provider)
        _require_non_empty_string("probe_policy_version", self.probe_policy_version)
        _require_non_empty_string("input_mint", self.input_mint)
        _require_non_empty_string("output_mint", self.output_mint)
        if self.input_mint == self.output_mint:
            raise ValueError("input_mint and output_mint must differ")
        _require_non_empty_string("taker", self.taker)
        _require_u64("input_amount", self.input_amount, positive=True)
        _require_slippage_bps(self.slippage_bps)


@dataclass(frozen=True, slots=True)
class ObserverPaperQuoteEvidence:
    identity: ObserverPaperQuoteIdentity
    output_amount: int
    minimum_output_amount: int
    route_available: bool
    price_impact_pct: str | None
    route_labels: tuple[str, ...]
    quoted_at_unix_ms: int

    def __post_init__(self) -> None:
        if type(self.identity) is not ObserverPaperQuoteIdentity:
            raise ValueError("identity must be an ObserverPaperQuoteIdentity")
        _require_u64("output_amount", self.output_amount)
        _require_u64("minimum_output_amount", self.minimum_output_amount)
        if self.minimum_output_amount > self.output_amount:
            raise ValueError("minimum_output_amount must not exceed output_amount")
        if type(self.route_available) is not bool:
            raise ValueError("route_available must be a boolean")
        _require_optional_non_negative_decimal_string(
            "price_impact_pct", self.price_impact_pct
        )
        if not isinstance(self.route_labels, tuple) or not all(
            isinstance(label, str) and bool(label.strip()) for label in self.route_labels
        ):
            raise ValueError("route_labels must be a tuple of non-empty strings")
        if self.route_available:
            if self.output_amount == 0:
                raise ValueError("route-available quote must have positive output_amount")
            if not self.route_labels:
                raise ValueError("route-available quote must identify at least one route")
        else:
            if self.output_amount != 0 or self.minimum_output_amount != 0:
                raise ValueError("unavailable quote must have zero output amounts")
            if self.price_impact_pct is not None:
                raise ValueError("unavailable quote must not carry price impact")
            if self.route_labels:
                raise ValueError("unavailable quote must not carry route labels")
        _require_non_negative_int("quoted_at_unix_ms", self.quoted_at_unix_ms)


@dataclass(frozen=True, slots=True)
class ObserverRegimeReadPolicy:
    version: str
    window_ms: int
    max_snapshot_age_ms: int
    source_priority: tuple[str, ...]
    entry_probe_policy_version: str
    quote_asset_mint: str
    entry_input_amount: int
    taker: str
    slippage_bps: int

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_positive_int("window_ms", self.window_ms)
        _require_non_negative_int("max_snapshot_age_ms", self.max_snapshot_age_ms)
        _require_unique_non_empty_strings("source_priority", self.source_priority)
        _require_non_empty_string(
            "entry_probe_policy_version", self.entry_probe_policy_version
        )
        _require_non_empty_string("quote_asset_mint", self.quote_asset_mint)
        _require_u64("entry_input_amount", self.entry_input_amount, positive=True)
        _require_non_empty_string("taker", self.taker)
        _require_slippage_bps(self.slippage_bps)


@dataclass(frozen=True, slots=True)
class ObserverPaperRiskEnvironment:
    trading_capital_usd: float
    day_started_at_unix_ms: int
    data_healthy: bool
    execution_healthy: bool
    kill_switch_active: bool

    def __post_init__(self) -> None:
        _require_positive_finite("trading_capital_usd", self.trading_capital_usd)
        _require_non_negative_int("day_started_at_unix_ms", self.day_started_at_unix_ms)
        _require_bool("data_healthy", self.data_healthy)
        _require_bool("execution_healthy", self.execution_healthy)
        _require_bool("kill_switch_active", self.kill_switch_active)


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


def _require_u64(name: str, value: int, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a u64 integer")
    minimum = 1 if positive else 0
    if value < minimum or value > _MAX_U64:
        qualifier = "positive " if positive else ""
        raise ValueError(f"{name} must be a {qualifier}u64 integer")


def _require_decimals(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError(f"{name} must be an integer within [0, 255]")


def _require_slippage_bps(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError("slippage_bps must be an integer within [0, 10000]")


def _require_positive_finite(name: str, value: float | int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")


def _require_bool(name: str, value: bool) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")


def _require_unique_non_empty_strings(name: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError(f"{name} must be a non-empty tuple")
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError(f"{name} must contain only non-empty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")


def _require_optional_non_negative_decimal_string(name: str, value: str | None) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-negative finite decimal string or None")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(
            f"{name} must be a non-negative finite decimal string or None"
        ) from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{name} must be a non-negative finite decimal string or None")
