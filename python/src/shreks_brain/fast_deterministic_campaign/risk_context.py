from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.paper import (
    PaperLedger,
    derive_paper_risk_accounting_facts,
)
from shreks_brain.risk import RiskContext


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignRiskEnvironment:
    trading_capital_usd: float
    day_started_at_unix_ms: int
    liquidity_usd: float | None
    expected_price_impact_pct: float | None
    price_impact_notional_usd: float | None
    market_observed_at_unix_ms: int
    data_healthy: bool | None
    execution_healthy: bool | None
    kill_switch_active: bool
    active_intent_keys: frozenset[str]
    operator_entry_halt_active: bool = False

    def __post_init__(self) -> None:
        _require_positive_finite("trading_capital_usd", self.trading_capital_usd)
        _require_non_negative_int(
            "day_started_at_unix_ms",
            self.day_started_at_unix_ms,
        )
        _require_optional_non_negative_finite(
            "liquidity_usd",
            self.liquidity_usd,
        )
        _require_optional_non_negative_finite(
            "expected_price_impact_pct",
            self.expected_price_impact_pct,
        )
        _require_optional_positive_finite(
            "price_impact_notional_usd",
            self.price_impact_notional_usd,
        )
        if (
            (self.expected_price_impact_pct is None)
            != (self.price_impact_notional_usd is None)
        ):
            raise ValueError(
                "price-impact value and notional must be both present or both absent"
            )
        _require_non_negative_int(
            "market_observed_at_unix_ms",
            self.market_observed_at_unix_ms,
        )
        _require_optional_bool("data_healthy", self.data_healthy)
        _require_optional_bool("execution_healthy", self.execution_healthy)
        _require_bool("kill_switch_active", self.kill_switch_active)
        _require_bool(
            "operator_entry_halt_active",
            self.operator_entry_halt_active,
        )
        if not isinstance(self.active_intent_keys, frozenset):
            raise ValueError("active_intent_keys must be a frozenset")
        if not all(
            isinstance(value, str) and value.strip()
            for value in self.active_intent_keys
        ):
            raise ValueError(
                "active_intent_keys must contain non-empty strings"
            )


def build_fast_deterministic_campaign_risk_context(
    ledger: PaperLedger,
    environment: FastDeterministicCampaignRiskEnvironment,
    *,
    as_of_unix_ms: int,
) -> RiskContext:
    if type(ledger) is not PaperLedger:
        raise ValueError("ledger must be exact PaperLedger")
    if type(environment) is not FastDeterministicCampaignRiskEnvironment:
        raise ValueError(
            "environment must be exact FastDeterministicCampaignRiskEnvironment"
        )
    _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
    if environment.day_started_at_unix_ms > as_of_unix_ms:
        raise ValueError("risk day start cannot be after evaluation time")
    if environment.market_observed_at_unix_ms > as_of_unix_ms:
        raise ValueError("risk market evidence cannot be from the future")

    accounting = derive_paper_risk_accounting_facts(
        ledger,
        day_started_at_unix_ms=environment.day_started_at_unix_ms,
    )
    return RiskContext(
        as_of_unix_ms=as_of_unix_ms,
        trading_capital_usd=environment.trading_capital_usd,
        open_position_count=accounting.open_position_count,
        aggregate_open_risk_usd=accounting.aggregate_open_risk_usd,
        daily_realized_pnl_usd=accounting.daily_realized_pnl_usd,
        rolling_drawdown_pct=accounting.rolling_drawdown_pct,
        consecutive_losses=accounting.consecutive_losses,
        last_loss_at_unix_ms=accounting.last_loss_at_unix_ms,
        liquidity_usd=environment.liquidity_usd,
        expected_price_impact_pct=environment.expected_price_impact_pct,
        price_impact_notional_usd=environment.price_impact_notional_usd,
        market_data_age_ms=(
            as_of_unix_ms - environment.market_observed_at_unix_ms
        ),
        data_healthy=environment.data_healthy,
        execution_healthy=environment.execution_healthy,
        kill_switch_active=environment.kill_switch_active,
        active_intent_keys=environment.active_intent_keys,
        operator_entry_halt_active=environment.operator_entry_halt_active,
    )


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")


def _require_optional_bool(name: str, value: object) -> None:
    if value is not None:
        _require_bool(name, value)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be finite")


def _require_positive_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be strictly positive")


def _require_optional_positive_finite(name: str, value: object) -> None:
    if value is not None:
        _require_positive_finite(name, value)


def _require_optional_non_negative_finite(name: str, value: object) -> None:
    if value is not None:
        _require_finite(name, value)
        if value < 0:  # type: ignore[operator]
            raise ValueError(f"{name} must be non-negative")
