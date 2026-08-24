from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.decision import DecisionAction


class ExitRouteState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class ExitReasonCode(StrEnum):
    FEATURE_SCHEMA_MISMATCH = "FEATURE_SCHEMA_MISMATCH"
    POSITION_NOT_OPEN = "POSITION_NOT_OPEN"
    STATE_POSITION_MISMATCH = "STATE_POSITION_MISMATCH"
    STATE_MINT_MISMATCH = "STATE_MINT_MISMATCH"
    STATE_POLICY_MISMATCH = "STATE_POLICY_MISMATCH"
    AS_OF_MISMATCH = "AS_OF_MISMATCH"
    CONTEXT_BEFORE_POSITION = "CONTEXT_BEFORE_POSITION"
    STATE_AFTER_AS_OF = "STATE_AFTER_AS_OF"
    GLOBAL_HALT_EXIT = "GLOBAL_HALT_EXIT"
    MAX_HOLD_EXIT = "MAX_HOLD_EXIT"
    MARKET_SOURCE_AFTER_AS_OF = "MARKET_SOURCE_AFTER_AS_OF"
    MARKET_SOURCE_TOO_OLD = "MARKET_SOURCE_TOO_OLD"
    EXECUTION_EVIDENCE_AFTER_AS_OF = "EXECUTION_EVIDENCE_AFTER_AS_OF"
    EXECUTION_EVIDENCE_TOO_OLD = "EXECUTION_EVIDENCE_TOO_OLD"
    CURRENT_PRICE_UNAVAILABLE = "CURRENT_PRICE_UNAVAILABLE"
    LIQUIDITY_ROUTE_UNAVAILABLE = "LIQUIDITY_ROUTE_UNAVAILABLE"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    EXIT_PRICE_IMPACT_TOO_HIGH = "EXIT_PRICE_IMPACT_TOO_HIGH"
    EXIT_CAPACITY_TOO_LOW = "EXIT_CAPACITY_TOO_LOW"
    HARD_STOP_TRIGGERED = "HARD_STOP_TRIGGERED"
    TRAILING_STOP_TRIGGERED = "TRAILING_STOP_TRIGGERED"
    WALLET_DISTRIBUTION_TRIGGERED = "WALLET_DISTRIBUTION_TRIGGERED"
    FLOW_DETERIORATION_TRIGGERED = "FLOW_DETERIORATION_TRIGGERED"
    MOMENTUM_DETERIORATION_TRIGGERED = "MOMENTUM_DETERIORATION_TRIGGERED"
    TAKE_PROFIT_TRIGGERED = "TAKE_PROFIT_TRIGGERED"
    NO_EXIT_TRIGGERED = "NO_EXIT_TRIGGERED"


@dataclass(frozen=True, slots=True)
class TakeProfitLevel:
    name: str
    trigger_return_pct: float
    reduce_fraction_of_current_quantity: float

    def __post_init__(self) -> None:
        _require_non_empty_string("name", self.name)
        _require_positive_finite("trigger_return_pct", self.trigger_return_pct)
        _require_fraction_open_zero(
            "reduce_fraction_of_current_quantity",
            self.reduce_fraction_of_current_quantity,
        )


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    version: str
    required_feature_schema_version: str
    max_market_data_age_ms: int
    max_execution_evidence_age_ms: int
    hard_stop_loss_pct: float | None
    take_profit_levels: tuple[TakeProfitLevel, ...]
    trailing_activation_return_pct: float | None
    trailing_stop_drawdown_pct: float | None
    max_hold_seconds: int | None
    flow_exit_max_buy_fraction_m5: float | None
    flow_exit_max_buy_pressure_acceleration: float | None
    momentum_exit_max_return_1m_pct: float | None
    momentum_exit_max_return_5m_pct: float | None
    min_liquidity_usd: float | None
    max_exit_price_impact_pct: float | None
    min_exit_capacity_fraction: float | None
    wallet_distribution_enabled: bool

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_non_empty_string(
            "required_feature_schema_version", self.required_feature_schema_version
        )
        _require_non_negative_int("max_market_data_age_ms", self.max_market_data_age_ms)
        _require_non_negative_int(
            "max_execution_evidence_age_ms", self.max_execution_evidence_age_ms
        )
        _require_optional_positive_finite("hard_stop_loss_pct", self.hard_stop_loss_pct)

        if not isinstance(self.take_profit_levels, tuple):
            raise ValueError("take_profit_levels must be a tuple")
        if not all(isinstance(level, TakeProfitLevel) for level in self.take_profit_levels):
            raise ValueError("take_profit_levels must contain only TakeProfitLevel values")
        names = tuple(level.name for level in self.take_profit_levels)
        if len(names) != len(set(names)):
            raise ValueError("take_profit_levels must use unique names")
        previous_trigger: float | None = None
        for level in self.take_profit_levels:
            if previous_trigger is not None and level.trigger_return_pct <= previous_trigger:
                raise ValueError("take_profit_levels triggers must be strictly increasing")
            previous_trigger = level.trigger_return_pct

        _require_optional_non_negative_finite(
            "trailing_activation_return_pct", self.trailing_activation_return_pct
        )
        _require_optional_positive_finite(
            "trailing_stop_drawdown_pct", self.trailing_stop_drawdown_pct
        )
        _require_pair(
            "trailing_activation_return_pct",
            self.trailing_activation_return_pct,
            "trailing_stop_drawdown_pct",
            self.trailing_stop_drawdown_pct,
        )

        _require_optional_positive_int("max_hold_seconds", self.max_hold_seconds)

        _require_optional_fraction_closed(
            "flow_exit_max_buy_fraction_m5", self.flow_exit_max_buy_fraction_m5
        )
        _require_optional_finite(
            "flow_exit_max_buy_pressure_acceleration",
            self.flow_exit_max_buy_pressure_acceleration,
        )
        _require_pair(
            "flow_exit_max_buy_fraction_m5",
            self.flow_exit_max_buy_fraction_m5,
            "flow_exit_max_buy_pressure_acceleration",
            self.flow_exit_max_buy_pressure_acceleration,
        )

        _require_optional_finite(
            "momentum_exit_max_return_1m_pct", self.momentum_exit_max_return_1m_pct
        )
        _require_optional_finite(
            "momentum_exit_max_return_5m_pct", self.momentum_exit_max_return_5m_pct
        )
        _require_pair(
            "momentum_exit_max_return_1m_pct",
            self.momentum_exit_max_return_1m_pct,
            "momentum_exit_max_return_5m_pct",
            self.momentum_exit_max_return_5m_pct,
        )

        _require_optional_non_negative_finite("min_liquidity_usd", self.min_liquidity_usd)
        _require_optional_non_negative_finite(
            "max_exit_price_impact_pct", self.max_exit_price_impact_pct
        )
        _require_optional_fraction_open_zero(
            "min_exit_capacity_fraction", self.min_exit_capacity_fraction
        )
        _require_bool("wallet_distribution_enabled", self.wallet_distribution_enabled)


@dataclass(frozen=True, slots=True)
class ExitExecutionContext:
    as_of_unix_ms: int
    observed_at_unix_ms: int
    route_state: ExitRouteState
    available_exit_notional_usd: float | None
    expected_exit_price_impact_pct: float | None
    price_impact_notional_usd: float | None
    wallet_distribution_detected: bool | None
    global_halt_active: bool

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        if not isinstance(self.route_state, ExitRouteState):
            raise ValueError("route_state must be an ExitRouteState")
        _require_optional_non_negative_finite(
            "available_exit_notional_usd", self.available_exit_notional_usd
        )
        _require_optional_non_negative_finite(
            "expected_exit_price_impact_pct", self.expected_exit_price_impact_pct
        )
        _require_optional_positive_finite(
            "price_impact_notional_usd", self.price_impact_notional_usd
        )
        if (self.expected_exit_price_impact_pct is None) != (
            self.price_impact_notional_usd is None
        ):
            raise ValueError(
                "expected_exit_price_impact_pct and price_impact_notional_usd must be paired"
            )
        _require_optional_bool(
            "wallet_distribution_detected", self.wallet_distribution_detected
        )
        _require_bool("global_halt_active", self.global_halt_active)


@dataclass(frozen=True, slots=True)
class ExitState:
    policy_version: str
    position_id: str
    mint: str
    initialized_at_unix_ms: int
    last_evaluated_at_unix_ms: int
    high_water_price_usd: float
    high_water_at_unix_ms: int
    completed_take_profit_levels: frozenset[str]

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("position_id", self.position_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("initialized_at_unix_ms", self.initialized_at_unix_ms)
        _require_non_negative_int(
            "last_evaluated_at_unix_ms", self.last_evaluated_at_unix_ms
        )
        if self.last_evaluated_at_unix_ms < self.initialized_at_unix_ms:
            raise ValueError(
                "last_evaluated_at_unix_ms must not precede initialized_at_unix_ms"
            )
        _require_positive_finite("high_water_price_usd", self.high_water_price_usd)
        _require_non_negative_int("high_water_at_unix_ms", self.high_water_at_unix_ms)
        if self.high_water_at_unix_ms < self.initialized_at_unix_ms:
            raise ValueError("high_water_at_unix_ms must not precede initialized_at_unix_ms")
        if self.high_water_at_unix_ms > self.last_evaluated_at_unix_ms:
            raise ValueError("high_water_at_unix_ms must not exceed last_evaluated_at_unix_ms")
        if not isinstance(self.completed_take_profit_levels, frozenset):
            raise ValueError("completed_take_profit_levels must be a frozenset")
        if not all(
            isinstance(name, str) and name.strip()
            for name in self.completed_take_profit_levels
        ):
            raise ValueError(
                "completed_take_profit_levels must contain non-empty strings"
            )


@dataclass(frozen=True, slots=True)
class ExitFinding:
    code: ExitReasonCode
    message: str
    primary: bool
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ExitReasonCode):
            raise ValueError("code must be an ExitReasonCode")
        _require_non_empty_string("message", self.message)
        _require_bool("primary", self.primary)
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
class ExitAssessment:
    policy_version: str
    feature_schema_version: str
    position_id: str
    mint: str
    as_of_unix_ms: int
    action: DecisionAction
    primary_reason: ExitReasonCode
    target_reduction_fraction: float
    target_quantity: float
    position_age_seconds: float | None
    current_price_usd: float | None
    current_market_value_usd: float | None
    price_return_pct: float | None
    drawdown_from_high_water_pct: float | None
    exit_capacity_fraction: float | None
    triggered_take_profit_level: str | None
    next_state: ExitState
    findings: tuple[ExitFinding, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("feature_schema_version", self.feature_schema_version)
        _require_non_empty_string("position_id", self.position_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if self.action not in (
            DecisionAction.HOLD,
            DecisionAction.REDUCE,
            DecisionAction.EXIT,
        ):
            raise ValueError("action must be HOLD, REDUCE, or EXIT")
        if not isinstance(self.primary_reason, ExitReasonCode):
            raise ValueError("primary_reason must be an ExitReasonCode")
        _require_fraction_closed(
            "target_reduction_fraction", self.target_reduction_fraction
        )
        _require_non_negative_finite("target_quantity", self.target_quantity)
        _require_optional_non_negative_finite(
            "position_age_seconds", self.position_age_seconds
        )
        _require_optional_positive_finite("current_price_usd", self.current_price_usd)
        _require_optional_non_negative_finite(
            "current_market_value_usd", self.current_market_value_usd
        )
        _require_optional_finite("price_return_pct", self.price_return_pct)
        _require_optional_finite(
            "drawdown_from_high_water_pct", self.drawdown_from_high_water_pct
        )
        _require_optional_fraction_closed(
            "exit_capacity_fraction", self.exit_capacity_fraction
        )
        if self.triggered_take_profit_level is not None:
            _require_non_empty_string(
                "triggered_take_profit_level", self.triggered_take_profit_level
            )
        if not isinstance(self.next_state, ExitState):
            raise ValueError("next_state must be an ExitState")
        if self.next_state.position_id != self.position_id:
            raise ValueError("next_state position_id must match assessment")
        if self.next_state.mint != self.mint:
            raise ValueError("next_state mint must match assessment")
        if self.next_state.policy_version != self.policy_version:
            raise ValueError("next_state policy_version must match assessment")

        if self.action is DecisionAction.HOLD:
            if not _is_zero(self.target_reduction_fraction) or not _is_zero(
                self.target_quantity
            ):
                raise ValueError("HOLD requires zero target reduction")
        elif self.action is DecisionAction.REDUCE:
            if not 0.0 < self.target_reduction_fraction < 1.0:
                raise ValueError("REDUCE requires target_reduction_fraction within (0,1)")
            if self.target_quantity <= 0.0:
                raise ValueError("REDUCE requires positive target_quantity")
        else:
            if not math.isclose(
                self.target_reduction_fraction, 1.0, rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError("EXIT requires target_reduction_fraction equal to 1")
            if self.target_quantity <= 0.0:
                raise ValueError("EXIT requires positive target_quantity")

        if not isinstance(self.findings, tuple) or not self.findings:
            raise ValueError("findings must be a non-empty tuple")
        if not all(isinstance(finding, ExitFinding) for finding in self.findings):
            raise ValueError("findings must contain only ExitFinding values")
        primaries = tuple(finding for finding in self.findings if finding.primary)
        if len(primaries) != 1:
            raise ValueError("findings must contain exactly one primary finding")
        if primaries[0].code is not self.primary_reason:
            raise ValueError("primary finding code must match primary_reason")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _require_optional_bool(name: str, value: object | None) -> None:
    if value is not None:
        _require_bool(name, value)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_optional_positive_int(name: str, value: object | None) -> None:
    if value is not None:
        _require_positive_int(name, value)


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_optional_finite(name: str, value: object | None) -> None:
    if value is not None:
        _require_finite(name, value)


def _require_positive_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be strictly positive")


def _require_optional_positive_finite(name: str, value: object | None) -> None:
    if value is not None:
        _require_positive_finite(name, value)


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_optional_non_negative_finite(name: str, value: object | None) -> None:
    if value is not None:
        _require_non_negative_finite(name, value)


def _require_fraction_open_zero(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0 or value > 1:  # type: ignore[operator]
        raise ValueError(f"{name} must be within (0, 1]")


def _require_optional_fraction_open_zero(name: str, value: object | None) -> None:
    if value is not None:
        _require_fraction_open_zero(name, value)


def _require_fraction_closed(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0 or value > 1:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 1]")


def _require_optional_fraction_closed(name: str, value: object | None) -> None:
    if value is not None:
        _require_fraction_closed(name, value)


def _require_pair(
    name_a: str,
    value_a: object | None,
    name_b: str,
    value_b: object | None,
) -> None:
    if (value_a is None) != (value_b is None):
        raise ValueError(f"{name_a} and {name_b} must be both set or both None")


def _is_zero(value: float) -> bool:
    return math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-12)
