from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


G4_TELEMETRY_SCHEMA_VERSION = "g4-telemetry-snapshot-v1"


class LayerStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


def _require_status(value: object) -> None:
    if type(value) is not LayerStatus:
        raise ValueError("status must be an exact LayerStatus")


def _require_optional_timestamp(name: str, value: object) -> None:
    if value is not None:
        _require_non_negative_int(name, value)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_non_negative_int(name: str, value: object) -> None:
    if value is not None:
        _require_non_negative_int(name, value)


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be an exact bool")


def _require_optional_bool(name: str, value: object) -> None:
    if value is not None:
        _require_bool(name, value)


def _require_optional_string(name: str, value: object) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be None or a non-empty string")


def _require_source_errors(value: object) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError("source_errors must be a tuple of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError("source_errors must not contain duplicates")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_optional_finite(name: str, value: object) -> None:
    if value is not None:
        _require_finite(name, value)


def _require_optional_non_negative_finite(name: str, value: object) -> None:
    if value is not None:
        _require_non_negative_finite(name, value)


@dataclass(frozen=True, slots=True)
class TradingPerformanceTelemetry:
    trade_count: int
    win_count: int
    loss_count: int
    flat_count: int
    gross_pnl_usd: float
    net_pnl_usd: float
    net_expectancy_usd: float | None
    net_expectancy_pct: float | None
    profit_factor: float | None
    maximum_drawdown_usd: float
    maximum_drawdown_pct: float
    win_rate: float | None
    turnover_usd: float
    execution_friction_usd: float
    explicit_cost_usd: float
    total_cost_usd: float
    cost_burden_pct: float | None

    def __post_init__(self) -> None:
        for name in ("trade_count", "win_count", "loss_count", "flat_count"):
            _require_non_negative_int(name, getattr(self, name))
        if self.trade_count != self.win_count + self.loss_count + self.flat_count:
            raise ValueError("trade counts must reconcile")
        for name in ("gross_pnl_usd", "net_pnl_usd"):
            _require_finite(name, getattr(self, name))
        for name in (
            "maximum_drawdown_usd",
            "maximum_drawdown_pct",
            "turnover_usd",
            "execution_friction_usd",
            "explicit_cost_usd",
            "total_cost_usd",
        ):
            _require_non_negative_finite(name, getattr(self, name))
        for name in (
            "net_expectancy_usd",
            "net_expectancy_pct",
            "profit_factor",
            "win_rate",
            "cost_burden_pct",
        ):
            _require_optional_finite(name, getattr(self, name))
        if self.profit_factor is not None and self.profit_factor < 0:
            raise ValueError("profit_factor must be non-negative")
        if self.win_rate is not None and not 0 <= self.win_rate <= 1:
            raise ValueError("win_rate must be within [0, 1]")
        if self.cost_burden_pct is not None and self.cost_burden_pct < 0:
            raise ValueError("cost_burden_pct must be non-negative")
        if not math.isclose(
            self.total_cost_usd,
            self.execution_friction_usd + self.explicit_cost_usd,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("total_cost_usd must reconcile")
        if not math.isclose(
            self.net_pnl_usd,
            self.gross_pnl_usd - self.total_cost_usd,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("net_pnl_usd must reconcile")


@dataclass(frozen=True, slots=True)
class SystemTelemetry:
    status: LayerStatus
    observed_at_unix_ms: int | None
    source_errors: tuple[str, ...]
    provider_count: int | None
    unhealthy_provider_count: int | None
    latest_market_observed_at_unix_ms: int | None
    market_age_ms: int | None
    latest_ingestion_checkpoint_at_unix_ms: int | None
    paper_last_cycle_at_unix_ms: int | None
    accounting_status: str | None
    host_metrics_available: bool

    def __post_init__(self) -> None:
        _require_status(self.status)
        _require_optional_timestamp("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_source_errors(self.source_errors)
        _require_optional_non_negative_int("provider_count", self.provider_count)
        _require_optional_non_negative_int("unhealthy_provider_count", self.unhealthy_provider_count)
        if (
            self.provider_count is not None
            and self.unhealthy_provider_count is not None
            and self.unhealthy_provider_count > self.provider_count
        ):
            raise ValueError("unhealthy_provider_count cannot exceed provider_count")
        _require_optional_timestamp(
            "latest_market_observed_at_unix_ms", self.latest_market_observed_at_unix_ms
        )
        _require_optional_non_negative_int("market_age_ms", self.market_age_ms)
        _require_optional_timestamp(
            "latest_ingestion_checkpoint_at_unix_ms",
            self.latest_ingestion_checkpoint_at_unix_ms,
        )
        _require_optional_timestamp(
            "paper_last_cycle_at_unix_ms", self.paper_last_cycle_at_unix_ms
        )
        _require_optional_string("accounting_status", self.accounting_status)
        _require_bool("host_metrics_available", self.host_metrics_available)


@dataclass(frozen=True, slots=True)
class TradingTelemetry:
    status: LayerStatus
    observed_at_unix_ms: int | None
    source_errors: tuple[str, ...]
    candidate_count: int | None
    holder_distribution_count: int | None
    paper_quote_count: int | None
    terminal_paper_entry_count: int | None
    open_position_count: int | None
    closed_position_count: int | None
    pending_entry: bool | None
    candidate_version: str | None
    candidate_mint: str | None
    paper_run_id: str | None
    historical_score_count: int | None
    historical_decision_count: int | None

    def __post_init__(self) -> None:
        _require_status(self.status)
        _require_optional_timestamp("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_source_errors(self.source_errors)
        for name in (
            "candidate_count",
            "holder_distribution_count",
            "paper_quote_count",
            "terminal_paper_entry_count",
            "open_position_count",
            "closed_position_count",
            "historical_score_count",
            "historical_decision_count",
        ):
            _require_optional_non_negative_int(name, getattr(self, name))
        _require_optional_bool("pending_entry", self.pending_entry)
        for name in ("candidate_version", "candidate_mint", "paper_run_id"):
            _require_optional_string(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class MoneyTelemetry:
    status: LayerStatus
    observed_at_unix_ms: int | None
    source_errors: tuple[str, ...]
    starting_cash_usd: float | None
    cash_balance_usd: float | None
    realized_pnl_usd: float | None
    unrealized_pnl_usd: float | None
    accumulated_costs_usd: float | None
    open_cost_basis_usd: float | None
    open_position_count: int | None
    daily_loss_usd: float | None
    performance: TradingPerformanceTelemetry | None

    def __post_init__(self) -> None:
        _require_status(self.status)
        _require_optional_timestamp("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_source_errors(self.source_errors)
        for name in (
            "starting_cash_usd",
            "cash_balance_usd",
            "accumulated_costs_usd",
            "open_cost_basis_usd",
        ):
            _require_optional_non_negative_finite(name, getattr(self, name))
        for name in ("realized_pnl_usd", "unrealized_pnl_usd", "daily_loss_usd"):
            _require_optional_finite(name, getattr(self, name))
        _require_optional_non_negative_int("open_position_count", self.open_position_count)
        if self.performance is not None and type(self.performance) is not TradingPerformanceTelemetry:
            raise ValueError("performance must be an exact TradingPerformanceTelemetry or None")


@dataclass(frozen=True, slots=True)
class ProofRiskTelemetry:
    status: LayerStatus
    observed_at_unix_ms: int | None
    source_errors: tuple[str, ...]
    proof_decision: str | None
    proof_gate_count: int | None
    proof_pass_count: int | None
    proof_fail_count: int | None
    proof_insufficient_count: int | None
    promotion_decision: str | None
    promotion_gate_count: int | None
    global_risk_halt: bool | None
    accounting_integrity: str | None
    live_state: str
    kill_switch_active: bool | None
    proof_trade_count: int | None
    proof_distinct_mint_count: int | None
    proof_net_expectancy_pct: float | None
    proof_profit_factor: float | None
    proof_maximum_drawdown_pct: float | None
    proof_cost_burden_pct: float | None

    def __post_init__(self) -> None:
        _require_status(self.status)
        _require_optional_timestamp("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_source_errors(self.source_errors)
        for name in ("proof_decision", "promotion_decision", "accounting_integrity"):
            _require_optional_string(name, getattr(self, name))
        for name in (
            "proof_gate_count",
            "proof_pass_count",
            "proof_fail_count",
            "proof_insufficient_count",
            "promotion_gate_count",
            "proof_trade_count",
            "proof_distinct_mint_count",
        ):
            _require_optional_non_negative_int(name, getattr(self, name))
        if self.proof_gate_count is not None and all(
            value is not None
            for value in (
                self.proof_pass_count,
                self.proof_fail_count,
                self.proof_insufficient_count,
            )
        ):
            if (
                (self.proof_pass_count or 0)
                + (self.proof_fail_count or 0)
                + (self.proof_insufficient_count or 0)
                != self.proof_gate_count
            ):
                raise ValueError("proof gate counts must reconcile")
        _require_optional_bool("global_risk_halt", self.global_risk_halt)
        if self.live_state != "DISABLED":
            raise ValueError("G4 PAPER telemetry live_state must be DISABLED")
        _require_optional_bool("kill_switch_active", self.kill_switch_active)
        for name in (
            "proof_net_expectancy_pct",
            "proof_profit_factor",
            "proof_maximum_drawdown_pct",
            "proof_cost_burden_pct",
        ):
            _require_optional_finite(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    schema_version: str
    generated_at_unix_ms: int
    mode: str
    overall_status: LayerStatus
    system: SystemTelemetry
    trading: TradingTelemetry
    money: MoneyTelemetry
    proof_risk: ProofRiskTelemetry

    def __post_init__(self) -> None:
        if self.schema_version != G4_TELEMETRY_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {G4_TELEMETRY_SCHEMA_VERSION}"
            )
        _require_non_negative_int("generated_at_unix_ms", self.generated_at_unix_ms)
        if self.mode != "PAPER":
            raise ValueError("G4 snapshot mode must be PAPER")
        _require_status(self.overall_status)
        for name, expected in (
            ("system", SystemTelemetry),
            ("trading", TradingTelemetry),
            ("money", MoneyTelemetry),
            ("proof_risk", ProofRiskTelemetry),
        ):
            if type(getattr(self, name)) is not expected:
                raise ValueError(f"{name} must be an exact {expected.__name__}")
