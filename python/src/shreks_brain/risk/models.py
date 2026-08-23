from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.decision import DecisionAction
from shreks_brain.runtime import RuntimeMode


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class RiskState(StrEnum):
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"


class RiskReasonCode(StrEnum):
    DECISION_POLICY_MISMATCH = "DECISION_POLICY_MISMATCH"
    FEATURE_SCHEMA_UNSUPPORTED = "FEATURE_SCHEMA_UNSUPPORTED"
    DECISION_NOT_ENTER = "DECISION_NOT_ENTER"
    SAFETY_NOT_PASS = "SAFETY_NOT_PASS"
    SETUP_NOT_READY = "SETUP_NOT_READY"
    REGIME_DEAD = "REGIME_DEAD"
    TOTAL_SCORE_UNAVAILABLE = "TOTAL_SCORE_UNAVAILABLE"
    CONTEXT_AS_OF_MISMATCH = "CONTEXT_AS_OF_MISMATCH"
    OBSERVE_MODE_NO_INTENTS = "OBSERVE_MODE_NO_INTENTS"
    HALTED_MODE = "HALTED_MODE"
    LIVE_MODE_DISABLED = "LIVE_MODE_DISABLED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    DATA_HEALTH_UNKNOWN = "DATA_HEALTH_UNKNOWN"
    DATA_HEALTH_DEGRADED = "DATA_HEALTH_DEGRADED"
    EXECUTION_HEALTH_UNKNOWN = "EXECUTION_HEALTH_UNKNOWN"
    EXECUTION_HEALTH_DEGRADED = "EXECUTION_HEALTH_DEGRADED"
    TRADING_CAPITAL_UNKNOWN = "TRADING_CAPITAL_UNKNOWN"
    TRADING_CAPITAL_NON_POSITIVE = "TRADING_CAPITAL_NON_POSITIVE"
    OPEN_POSITION_COUNT_UNKNOWN = "OPEN_POSITION_COUNT_UNKNOWN"
    MAX_POSITIONS_REACHED = "MAX_POSITIONS_REACHED"
    AGGREGATE_OPEN_RISK_UNKNOWN = "AGGREGATE_OPEN_RISK_UNKNOWN"
    AGGREGATE_RISK_LIMIT_REACHED = "AGGREGATE_RISK_LIMIT_REACHED"
    DAILY_REALIZED_PNL_UNKNOWN = "DAILY_REALIZED_PNL_UNKNOWN"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    ROLLING_DRAWDOWN_UNKNOWN = "ROLLING_DRAWDOWN_UNKNOWN"
    ROLLING_DRAWDOWN_LIMIT_REACHED = "ROLLING_DRAWDOWN_LIMIT_REACHED"
    CONSECUTIVE_LOSSES_UNKNOWN = "CONSECUTIVE_LOSSES_UNKNOWN"
    LOSS_COOLDOWN_TIME_UNKNOWN = "LOSS_COOLDOWN_TIME_UNKNOWN"
    LOSS_COOLDOWN_TIME_AFTER_AS_OF = "LOSS_COOLDOWN_TIME_AFTER_AS_OF"
    LOSS_COOLDOWN_ACTIVE = "LOSS_COOLDOWN_ACTIVE"
    LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    PRICE_IMPACT_UNKNOWN = "PRICE_IMPACT_UNKNOWN"
    PRICE_IMPACT_NOTIONAL_UNKNOWN = "PRICE_IMPACT_NOTIONAL_UNKNOWN"
    PRICE_IMPACT_NOTIONAL_TOO_SMALL = "PRICE_IMPACT_NOTIONAL_TOO_SMALL"
    PRICE_IMPACT_TOO_HIGH = "PRICE_IMPACT_TOO_HIGH"
    MARKET_DATA_AGE_UNKNOWN = "MARKET_DATA_AGE_UNKNOWN"
    MARKET_DATA_TOO_OLD = "MARKET_DATA_TOO_OLD"
    DUPLICATE_ACTIVE_INTENT = "DUPLICATE_ACTIVE_INTENT"
    RISK_APPROVED = "RISK_APPROVED"


@dataclass(frozen=True, slots=True)
class RiskFinding:
    code: RiskReasonCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, RiskReasonCode):
            raise ValueError("code must be a RiskReasonCode")
        _require_non_empty_string("message", self.message)


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    version: str
    required_decision_policy_version: str
    required_feature_schema_version: str
    target_position_notional_usd: float
    max_notional_per_position_usd: float
    max_capital_fraction_per_position: float
    max_simultaneous_positions: int
    max_aggregate_open_risk_usd: float
    max_daily_realized_loss_usd: float
    max_rolling_drawdown_pct: float
    cooldown_after_consecutive_losses: int
    cooldown_seconds: int
    min_liquidity_usd: float
    max_expected_price_impact_pct: float
    max_slippage_bps: int
    max_market_data_age_ms: int

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_non_empty_string(
            "required_decision_policy_version", self.required_decision_policy_version
        )
        _require_non_empty_string(
            "required_feature_schema_version", self.required_feature_schema_version
        )
        _require_positive_finite(
            "target_position_notional_usd", self.target_position_notional_usd
        )
        _require_positive_finite(
            "max_notional_per_position_usd", self.max_notional_per_position_usd
        )
        _require_fraction(
            "max_capital_fraction_per_position", self.max_capital_fraction_per_position
        )
        _require_positive_int("max_simultaneous_positions", self.max_simultaneous_positions)
        _require_positive_finite(
            "max_aggregate_open_risk_usd", self.max_aggregate_open_risk_usd
        )
        _require_positive_finite(
            "max_daily_realized_loss_usd", self.max_daily_realized_loss_usd
        )
        _require_finite("max_rolling_drawdown_pct", self.max_rolling_drawdown_pct)
        if not 0.0 < self.max_rolling_drawdown_pct <= 100.0:
            raise ValueError("max_rolling_drawdown_pct must be within (0, 100]")
        _require_positive_int(
            "cooldown_after_consecutive_losses", self.cooldown_after_consecutive_losses
        )
        _require_non_negative_int("cooldown_seconds", self.cooldown_seconds)
        _require_non_negative_finite("min_liquidity_usd", self.min_liquidity_usd)
        _require_non_negative_finite(
            "max_expected_price_impact_pct", self.max_expected_price_impact_pct
        )
        _require_bps("max_slippage_bps", self.max_slippage_bps)
        _require_non_negative_int("max_market_data_age_ms", self.max_market_data_age_ms)


@dataclass(frozen=True, slots=True)
class RiskContext:
    as_of_unix_ms: int
    trading_capital_usd: float | None
    open_position_count: int | None
    aggregate_open_risk_usd: float | None
    daily_realized_pnl_usd: float | None
    rolling_drawdown_pct: float | None
    consecutive_losses: int | None
    last_loss_at_unix_ms: int | None
    liquidity_usd: float | None
    expected_price_impact_pct: float | None
    price_impact_notional_usd: float | None
    market_data_age_ms: int | None
    data_healthy: bool | None
    execution_healthy: bool | None
    kill_switch_active: bool
    active_intent_keys: frozenset[str]

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_optional_non_negative_finite(
            "trading_capital_usd", self.trading_capital_usd
        )
        _require_optional_non_negative_int(
            "open_position_count", self.open_position_count
        )
        _require_optional_non_negative_finite(
            "aggregate_open_risk_usd", self.aggregate_open_risk_usd
        )
        _require_optional_finite(
            "daily_realized_pnl_usd", self.daily_realized_pnl_usd
        )
        if self.rolling_drawdown_pct is not None:
            _require_finite("rolling_drawdown_pct", self.rolling_drawdown_pct)
            if not 0.0 <= self.rolling_drawdown_pct <= 100.0:
                raise ValueError("rolling_drawdown_pct must be within [0, 100]")
        _require_optional_non_negative_int("consecutive_losses", self.consecutive_losses)
        _require_optional_non_negative_int(
            "last_loss_at_unix_ms", self.last_loss_at_unix_ms
        )
        _require_optional_non_negative_finite("liquidity_usd", self.liquidity_usd)
        _require_optional_non_negative_finite(
            "expected_price_impact_pct", self.expected_price_impact_pct
        )
        _require_optional_non_negative_finite(
            "price_impact_notional_usd", self.price_impact_notional_usd
        )
        _require_optional_non_negative_int("market_data_age_ms", self.market_data_age_ms)
        _require_optional_bool("data_healthy", self.data_healthy)
        _require_optional_bool("execution_healthy", self.execution_healthy)
        _require_bool("kill_switch_active", self.kill_switch_active)
        if not isinstance(self.active_intent_keys, frozenset):
            raise ValueError("active_intent_keys must be a frozenset")
        if not all(
            isinstance(key, str) and key.strip() for key in self.active_intent_keys
        ):
            raise ValueError("active_intent_keys must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class TradeIntent:
    mint: str
    side: TradeSide
    requested_notional_usd: float
    max_slippage_bps: int
    strategy_name: str
    strategy_version: str
    score_policy_version: str
    decision_policy_version: str
    risk_policy_version: str
    reason: str
    idempotency_key: str
    execution_mode: RuntimeMode
    as_of_unix_ms: int

    def __post_init__(self) -> None:
        _require_non_empty_string("mint", self.mint)
        if not isinstance(self.side, TradeSide):
            raise ValueError("side must be a TradeSide")
        _require_positive_finite("requested_notional_usd", self.requested_notional_usd)
        _require_bps("max_slippage_bps", self.max_slippage_bps)
        for name in (
            "strategy_name",
            "strategy_version",
            "score_policy_version",
            "decision_policy_version",
            "risk_policy_version",
            "reason",
            "idempotency_key",
        ):
            _require_non_empty_string(name, getattr(self, name))
        if not isinstance(self.execution_mode, RuntimeMode):
            raise ValueError("execution_mode must be a RuntimeMode")
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    policy_version: str
    mint: str
    as_of_unix_ms: int
    state: RiskState
    decision_action: DecisionAction
    execution_mode: RuntimeMode
    requested_notional_usd: float | None
    idempotency_key: str | None
    findings: tuple[RiskFinding, ...]
    intent: TradeIntent | None

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.state, RiskState):
            raise ValueError("state must be a RiskState")
        if not isinstance(self.decision_action, DecisionAction):
            raise ValueError("decision_action must be a DecisionAction")
        if not isinstance(self.execution_mode, RuntimeMode):
            raise ValueError("execution_mode must be a RuntimeMode")
        if not isinstance(self.findings, tuple) or len(self.findings) != 1:
            raise ValueError("findings must contain exactly one RiskFinding")
        if not all(isinstance(finding, RiskFinding) for finding in self.findings):
            raise ValueError("findings must contain only RiskFinding values")

        if self.state is RiskState.REJECTED:
            if (
                self.requested_notional_usd is not None
                or self.idempotency_key is not None
                or self.intent is not None
            ):
                raise ValueError("rejected risk assessments cannot carry an intent")
            if self.findings[0].code is RiskReasonCode.RISK_APPROVED:
                raise ValueError("rejected risk assessments cannot be RISK_APPROVED")
            return

        if self.decision_action is not DecisionAction.ENTER:
            raise ValueError("approved risk assessments require an ENTER decision")
        if self.requested_notional_usd is None:
            raise ValueError("approved risk assessments require requested_notional_usd")
        _require_positive_finite("requested_notional_usd", self.requested_notional_usd)
        if self.idempotency_key is None:
            raise ValueError("approved risk assessments require idempotency_key")
        _require_non_empty_string("idempotency_key", self.idempotency_key)
        if self.intent is None:
            raise ValueError("approved risk assessments require intent")
        if self.findings[0].code is not RiskReasonCode.RISK_APPROVED:
            raise ValueError("approved risk assessments require RISK_APPROVED")
        if self.intent.mint != self.mint:
            raise ValueError("intent mint must match risk assessment")
        if self.intent.as_of_unix_ms != self.as_of_unix_ms:
            raise ValueError("intent as_of_unix_ms must match risk assessment")
        if self.intent.execution_mode is not self.execution_mode:
            raise ValueError("intent execution_mode must match risk assessment")
        if self.intent.requested_notional_usd != self.requested_notional_usd:
            raise ValueError("intent requested_notional_usd must match risk assessment")
        if self.intent.idempotency_key != self.idempotency_key:
            raise ValueError("intent idempotency_key must match risk assessment")
        if self.intent.risk_policy_version != self.policy_version:
            raise ValueError("intent risk_policy_version must match risk assessment")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _require_optional_bool(name: str, value: object | None) -> None:
    if value is not None:
        _require_bool(name, value)


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_positive_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be strictly positive")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_optional_finite(name: str, value: object | None) -> None:
    if value is not None:
        _require_finite(name, value)


def _require_optional_non_negative_finite(
    name: str, value: object | None
) -> None:
    if value is not None:
        _require_non_negative_finite(name, value)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _require_optional_non_negative_int(name: str, value: object | None) -> None:
    if value is not None:
        _require_non_negative_int(name, value)


def _require_fraction(name: str, value: object) -> None:
    _require_finite(name, value)
    if not 0 < value <= 1:  # type: ignore[operator]
        raise ValueError(f"{name} must be within (0, 1]")


def _require_bps(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError(f"{name} must be an integer within [0, 10000]")
