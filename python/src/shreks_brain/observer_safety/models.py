from __future__ import annotations

from dataclasses import dataclass
import math


_MAX_U64 = 2**64 - 1


@dataclass(frozen=True, slots=True)
class ObserverSafetyProbeIdentity:
    probe_policy_version: str
    output_mint: str
    input_amount: int
    taker: str
    slippage_bps: int

    def __post_init__(self) -> None:
        _require_non_empty_string("probe_policy_version", self.probe_policy_version)
        _require_non_empty_string("output_mint", self.output_mint)
        _require_u64("input_amount", self.input_amount, positive=True)
        _require_non_empty_string("taker", self.taker)
        _require_slippage_bps(self.slippage_bps)


@dataclass(frozen=True, slots=True)
class ObserverMintSafetyEvidence:
    candidate_id: int
    provider: str
    mint: str
    mint_authority: str | None
    freeze_authority: str | None
    slot: int
    observed_at_unix_ms: int

    def __post_init__(self) -> None:
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_empty_string("provider", self.provider)
        _require_non_empty_string("mint", self.mint)
        _require_optional_non_empty_string("mint_authority", self.mint_authority)
        _require_optional_non_empty_string("freeze_authority", self.freeze_authority)
        _require_u64("slot", self.slot)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)


@dataclass(frozen=True, slots=True)
class ObserverHolderSafetyEvidence:
    candidate_id: int
    provider: str
    mint: str
    last_indexed_slot: int
    observed_at_unix_ms: int
    complete: bool
    top_holder_concentration_pct: float | None

    def __post_init__(self) -> None:
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_empty_string("provider", self.provider)
        _require_non_empty_string("mint", self.mint)
        _require_u64("last_indexed_slot", self.last_indexed_slot)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        if type(self.complete) is not bool:
            raise ValueError("complete must be a boolean")
        if not self.complete and self.top_holder_concentration_pct is not None:
            raise ValueError(
                "top_holder_concentration_pct must be None when holder evidence is incomplete"
            )
        _require_optional_percentage(
            "top_holder_concentration_pct", self.top_holder_concentration_pct
        )


@dataclass(frozen=True, slots=True)
class ObserverExitQuoteSafetyEvidence:
    candidate_id: int
    provider: str
    probe_policy_version: str
    input_mint: str
    output_mint: str
    taker: str
    input_amount: int
    output_amount: int
    minimum_output_amount: int
    slippage_bps: int
    route_available: bool
    price_impact_pct: str | None
    quoted_at_unix_ms: int

    def __post_init__(self) -> None:
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_empty_string("provider", self.provider)
        _require_non_empty_string("probe_policy_version", self.probe_policy_version)
        _require_non_empty_string("input_mint", self.input_mint)
        _require_non_empty_string("output_mint", self.output_mint)
        if self.input_mint == self.output_mint:
            raise ValueError("input_mint and output_mint must differ")
        _require_non_empty_string("taker", self.taker)
        _require_u64("input_amount", self.input_amount, positive=True)
        _require_u64("output_amount", self.output_amount)
        _require_u64("minimum_output_amount", self.minimum_output_amount)
        if self.minimum_output_amount > self.output_amount:
            raise ValueError("minimum_output_amount must not exceed output_amount")
        _require_slippage_bps(self.slippage_bps)
        if type(self.route_available) is not bool:
            raise ValueError("route_available must be a boolean")
        _require_optional_non_empty_string("price_impact_pct", self.price_impact_pct)
        _require_non_negative_int("quoted_at_unix_ms", self.quoted_at_unix_ms)


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_non_empty_string(name: str, value: str | None) -> None:
    if value is not None:
        _require_non_empty_string(name, value)


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_u64(name: str, value: int, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a u64 integer")
    minimum = 1 if positive else 0
    if value < minimum or value > _MAX_U64:
        qualifier = "positive " if positive else ""
        raise ValueError(f"{name} must be a {qualifier}u64 integer")


def _require_slippage_bps(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError("slippage_bps must be an integer within [0, 10000]")


def _require_optional_percentage(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite percentage")
    if not math.isfinite(value) or not 0.0 <= float(value) <= 100.0:
        raise ValueError(f"{name} must be within [0, 100]")
