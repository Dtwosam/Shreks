from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


class SafetyDecision(StrEnum):
    PASS = "PASS"
    REJECT = "REJECT"
    INCOMPLETE = "INCOMPLETE"


class SafetySeverity(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"
    DATA_QUALITY = "DATA_QUALITY"


class SafetyReasonCode(StrEnum):
    GLOBAL_RISK_HALT = "GLOBAL_RISK_HALT"
    MINT_AUTHORITY_ACTIVE = "MINT_AUTHORITY_ACTIVE"
    FREEZE_AUTHORITY_ACTIVE = "FREEZE_AUTHORITY_ACTIVE"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    HOLDER_CONCENTRATION_ABOVE_MAXIMUM = "HOLDER_CONCENTRATION_ABOVE_MAXIMUM"
    EXIT_QUOTE_UNAVAILABLE = "EXIT_QUOTE_UNAVAILABLE"
    EXECUTION_TRAP_DETECTED = "EXECUTION_TRAP_DETECTED"

    MINT_AUTHORITY_UNKNOWN = "MINT_AUTHORITY_UNKNOWN"
    FREEZE_AUTHORITY_UNKNOWN = "FREEZE_AUTHORITY_UNKNOWN"
    LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN"
    HOLDER_CONCENTRATION_UNKNOWN = "HOLDER_CONCENTRATION_UNKNOWN"
    EXIT_QUOTE_UNKNOWN = "EXIT_QUOTE_UNKNOWN"
    CRITICAL_DATA_STALE = "CRITICAL_DATA_STALE"
    CRITICAL_DATA_CONTRADICTORY = "CRITICAL_DATA_CONTRADICTORY"

    CREATOR_CONCENTRATION_ELEVATED = "CREATOR_CONCENTRATION_ELEVATED"
    LIQUIDITY_WEAK = "LIQUIDITY_WEAK"
    HOLDER_CONCENTRATION_ELEVATED = "HOLDER_CONCENTRATION_ELEVATED"
    EXIT_PRICE_IMPACT_ELEVATED = "EXIT_PRICE_IMPACT_ELEVATED"


@dataclass(frozen=True, slots=True)
class SafetyFinding:
    code: SafetyReasonCode
    severity: SafetySeverity
    message: str
    observed_value: float | bool | None = None
    threshold_value: float | None = None


@dataclass(frozen=True, slots=True)
class SafetyInputs:
    as_of_unix_ms: int
    mint_authority_active: bool | None
    freeze_authority_active: bool | None
    liquidity_usd: float | None
    top_holder_concentration_pct: float | None
    creator_concentration_pct: float | None
    exit_quote_available: bool | None
    exit_price_impact_pct: float | None
    execution_trap_detected: bool
    critical_data_observed_at_unix_ms: int | None
    critical_data_contradictory: bool
    global_risk_halt: bool

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_optional_bool("mint_authority_active", self.mint_authority_active)
        _require_optional_bool("freeze_authority_active", self.freeze_authority_active)
        _require_non_negative_finite("liquidity_usd", self.liquidity_usd)
        _require_percentage("top_holder_concentration_pct", self.top_holder_concentration_pct)
        _require_percentage("creator_concentration_pct", self.creator_concentration_pct)
        _require_optional_bool("exit_quote_available", self.exit_quote_available)
        _require_percentage("exit_price_impact_pct", self.exit_price_impact_pct)
        _require_bool("execution_trap_detected", self.execution_trap_detected)
        _require_non_negative_int(
            "critical_data_observed_at_unix_ms",
            self.critical_data_observed_at_unix_ms,
            allow_none=True,
        )
        _require_bool("critical_data_contradictory", self.critical_data_contradictory)
        _require_bool("global_risk_halt", self.global_risk_halt)


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    version: str
    min_liquidity_usd: float
    soft_min_liquidity_usd: float
    max_top_holder_concentration_pct: float
    soft_max_top_holder_concentration_pct: float
    soft_max_creator_concentration_pct: float
    soft_max_exit_price_impact_pct: float
    max_critical_data_age_ms: int
    require_known_authorities: bool = True
    require_liquidity: bool = True
    require_holder_concentration: bool = True
    require_exit_quote: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string")

        _require_non_negative_finite("min_liquidity_usd", self.min_liquidity_usd)
        _require_non_negative_finite("soft_min_liquidity_usd", self.soft_min_liquidity_usd)
        _require_percentage(
            "max_top_holder_concentration_pct",
            self.max_top_holder_concentration_pct,
        )
        _require_percentage(
            "soft_max_top_holder_concentration_pct",
            self.soft_max_top_holder_concentration_pct,
        )
        _require_percentage(
            "soft_max_creator_concentration_pct",
            self.soft_max_creator_concentration_pct,
        )
        _require_percentage(
            "soft_max_exit_price_impact_pct",
            self.soft_max_exit_price_impact_pct,
        )
        _require_non_negative_int("max_critical_data_age_ms", self.max_critical_data_age_ms)
        _require_bool("require_known_authorities", self.require_known_authorities)
        _require_bool("require_liquidity", self.require_liquidity)
        _require_bool("require_holder_concentration", self.require_holder_concentration)
        _require_bool("require_exit_quote", self.require_exit_quote)

        if self.soft_min_liquidity_usd < self.min_liquidity_usd:
            raise ValueError(
                "soft_min_liquidity_usd must be greater than or equal to min_liquidity_usd"
            )
        if self.soft_max_top_holder_concentration_pct > self.max_top_holder_concentration_pct:
            raise ValueError(
                "soft_max_top_holder_concentration_pct must be less than or equal to "
                "max_top_holder_concentration_pct"
            )


@dataclass(frozen=True, slots=True)
class SafetyAssessment:
    decision: SafetyDecision
    policy_version: str
    as_of_unix_ms: int
    findings: tuple[SafetyFinding, ...]

    @property
    def hard_findings(self) -> tuple[SafetyFinding, ...]:
        return tuple(
            finding for finding in self.findings if finding.severity is SafetySeverity.HARD
        )

    @property
    def data_quality_findings(self) -> tuple[SafetyFinding, ...]:
        return tuple(
            finding
            for finding in self.findings
            if finding.severity is SafetySeverity.DATA_QUALITY
        )

    @property
    def soft_findings(self) -> tuple[SafetyFinding, ...]:
        return tuple(
            finding for finding in self.findings if finding.severity is SafetySeverity.SOFT
        )


def _require_non_negative_finite(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def _require_percentage(name: str, value: float | None) -> None:
    if value is None:
        return
    _require_non_negative_finite(name, value)
    if value > 100:
        raise ValueError(f"{name} must be within [0, 100]")


def _require_non_negative_int(
    name: str,
    value: int | None,
    *,
    allow_none: bool = False,
) -> None:
    if value is None:
        if allow_none:
            return
        raise ValueError(f"{name} must be a non-negative integer")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bool(name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _require_optional_bool(name: str, value: bool | None) -> None:
    if value is not None:
        _require_bool(name, value)
