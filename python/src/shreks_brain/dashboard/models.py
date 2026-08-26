from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from pathlib import Path

from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfig,
)
from shreks_brain.telemetry import TelemetrySnapshot


class DashboardEvidenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_PERSISTED = "NOT_PERSISTED"


@dataclass(frozen=True, slots=True)
class DashboardSourceConfig:
    telemetry_path: Path
    paper_runtime_config: ObserverPaperCampaignRuntimeConfig

    def __post_init__(self) -> None:
        if not isinstance(self.telemetry_path, Path):
            raise ValueError("telemetry_path must be a Path")
        if type(self.paper_runtime_config) is not ObserverPaperCampaignRuntimeConfig:
            raise ValueError(
                "paper_runtime_config must be an exact ObserverPaperCampaignRuntimeConfig"
            )


@dataclass(frozen=True, slots=True)
class DashboardTradeSummary:
    candidate_version: str
    position_id: str
    mint: str
    setup_name: str
    market_regime: str
    opened_at_unix_ms: int
    closed_at_unix_ms: int
    entry_notional_usd: float
    turnover_usd: float
    gross_pnl_usd: float
    execution_friction_usd: float
    explicit_cost_usd: float
    net_pnl_usd: float

    def __post_init__(self) -> None:
        for name in (
            "candidate_version",
            "position_id",
            "mint",
            "setup_name",
            "market_regime",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("opened_at_unix_ms", self.opened_at_unix_ms)
        _require_non_negative_int("closed_at_unix_ms", self.closed_at_unix_ms)
        if self.closed_at_unix_ms < self.opened_at_unix_ms:
            raise ValueError("closed_at_unix_ms cannot precede opened_at_unix_ms")
        _require_positive_finite("entry_notional_usd", self.entry_notional_usd)
        _require_positive_finite("turnover_usd", self.turnover_usd)
        for name in ("gross_pnl_usd", "net_pnl_usd"):
            _require_finite(name, getattr(self, name))
        for name in ("execution_friction_usd", "explicit_cost_usd"):
            _require_non_negative_finite(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class DashboardLedgerEvent:
    sequence: int
    side: str
    execution_state: str
    paper_execution_reason_code: str
    ledger_reason_code: str
    strategy_name: str
    strategy_version: str
    score_policy_version: str
    decision_policy_version: str
    risk_policy_version: str
    paper_policy_version: str
    booked_at_unix_ms: int
    filled_quantity: float
    filled_notional_usd: float
    explicit_cost_usd: float
    realized_pnl_delta_usd: float

    def __post_init__(self) -> None:
        _require_positive_int("sequence", self.sequence)
        for name in (
            "side",
            "execution_state",
            "paper_execution_reason_code",
            "ledger_reason_code",
            "strategy_name",
            "strategy_version",
            "score_policy_version",
            "decision_policy_version",
            "risk_policy_version",
            "paper_policy_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("booked_at_unix_ms", self.booked_at_unix_ms)
        for name in ("filled_quantity", "filled_notional_usd", "explicit_cost_usd"):
            _require_non_negative_finite(name, getattr(self, name))
        _require_finite("realized_pnl_delta_usd", self.realized_pnl_delta_usd)


@dataclass(frozen=True, slots=True)
class DashboardTradeDetail:
    summary: DashboardTradeSummary
    ledger_events: tuple[DashboardLedgerEvent, ...]
    safety_assessment: DashboardEvidenceAvailability
    feature_vector: DashboardEvidenceAvailability
    score_assessment: DashboardEvidenceAvailability
    entry_decision: DashboardEvidenceAvailability
    risk_assessment: DashboardEvidenceAvailability
    entry_quote: DashboardEvidenceAvailability
    strategic_exit_reason: DashboardEvidenceAvailability

    def __post_init__(self) -> None:
        if type(self.summary) is not DashboardTradeSummary:
            raise ValueError("summary must be an exact DashboardTradeSummary")
        if not isinstance(self.ledger_events, tuple) or not all(
            type(value) is DashboardLedgerEvent for value in self.ledger_events
        ):
            raise ValueError("ledger_events must contain exact DashboardLedgerEvent values")
        sequences = tuple(value.sequence for value in self.ledger_events)
        if sequences != tuple(sorted(sequences)) or len(sequences) != len(set(sequences)):
            raise ValueError("ledger_events must have unique ascending sequences")
        for name in (
            "safety_assessment",
            "feature_vector",
            "score_assessment",
            "entry_decision",
            "risk_assessment",
            "entry_quote",
            "strategic_exit_reason",
        ):
            if type(getattr(self, name)) is not DashboardEvidenceAvailability:
                raise ValueError(f"{name} must be an exact DashboardEvidenceAvailability")


@dataclass(frozen=True, slots=True)
class DashboardSnapshotSource:
    telemetry: TelemetrySnapshot
    telemetry_file_mtime_ns: int
    trades: tuple[DashboardTradeSummary, ...]

    def __post_init__(self) -> None:
        if type(self.telemetry) is not TelemetrySnapshot:
            raise ValueError("telemetry must be an exact TelemetrySnapshot")
        _require_non_negative_int("telemetry_file_mtime_ns", self.telemetry_file_mtime_ns)
        if not isinstance(self.trades, tuple) or not all(
            type(value) is DashboardTradeSummary for value in self.trades
        ):
            raise ValueError("trades must contain exact DashboardTradeSummary values")
        keys = tuple(value.position_id for value in self.trades)
        if len(keys) != len(set(keys)):
            raise ValueError("dashboard trade position IDs must be unique")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value <= 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be positive")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_positive_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be positive")
