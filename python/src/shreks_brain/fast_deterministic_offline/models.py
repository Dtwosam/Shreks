from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.research.fast_training_features import (
    FastTrainingLifecycleEvent,
    FastTrainingReserveContext,
    FastTrainingWindowSummary,
)


@dataclass(frozen=True, slots=True)
class FastOfflineExecutionLegCost:
    effective_fee_bps: int
    expected_impact_bps: int
    expected_slippage_bps: int
    expected_latency_bps: int
    network_fee_quote: float
    priority_fee_quote: float
    expected_failure_cost_quote: float

    def __post_init__(self) -> None:
        for name in (
            "effective_fee_bps",
            "expected_impact_bps",
            "expected_slippage_bps",
            "expected_latency_bps",
        ):
            _require_bps(name, getattr(self, name))
        for name in (
            "network_fee_quote",
            "priority_fee_quote",
            "expected_failure_cost_quote",
        ):
            _require_non_negative_finite(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class FastOfflineExecutionCostModel:
    version: int
    entry: FastOfflineExecutionLegCost
    exit: FastOfflineExecutionLegCost

    def __post_init__(self) -> None:
        _require_positive_int("version", self.version)
        if type(self.entry) is not FastOfflineExecutionLegCost:
            raise ValueError("entry must be exact FastOfflineExecutionLegCost")
        if type(self.exit) is not FastOfflineExecutionLegCost:
            raise ValueError("exit must be exact FastOfflineExecutionLegCost")


@dataclass(frozen=True, slots=True)
class FastOfflineExecutionTrade:
    base_quantity: float
    executable_entry_price_quote: float
    forecast_exit_price_quote: float
    exit_capacity_base: float
    required_edge_bps: int
    risk_margin_bps: int

    def __post_init__(self) -> None:
        for name in (
            "base_quantity",
            "executable_entry_price_quote",
            "forecast_exit_price_quote",
            "exit_capacity_base",
        ):
            _require_positive_finite(name, getattr(self, name))
        if self.exit_capacity_base < self.base_quantity:
            raise ValueError("exit_capacity_base cannot be below base_quantity")
        _require_bps("required_edge_bps", self.required_edge_bps)
        _require_bps("risk_margin_bps", self.risk_margin_bps)


@dataclass(frozen=True, slots=True)
class FastOfflineEntryExecution:
    cost_model: FastOfflineExecutionCostModel
    trade: FastOfflineExecutionTrade

    def __post_init__(self) -> None:
        if type(self.cost_model) is not FastOfflineExecutionCostModel:
            raise ValueError("cost_model must be exact FastOfflineExecutionCostModel")
        if type(self.trade) is not FastOfflineExecutionTrade:
            raise ValueError("trade must be exact FastOfflineExecutionTrade")


@dataclass(frozen=True, slots=True)
class FastOfflineImpulseScalpEvidence:
    execution: FastOfflineEntryExecution | None

    @property
    def kind(self) -> str:
        return "IMPULSE_SCALP"


@dataclass(frozen=True, slots=True)
class FastOfflineMicroPullbackEvidence:
    execution: FastOfflineEntryExecution | None

    @property
    def kind(self) -> str:
        return "MICRO_PULLBACK"


@dataclass(frozen=True, slots=True)
class FastOfflinePreGraduationEvidence:
    execution: FastOfflineEntryExecution | None

    @property
    def kind(self) -> str:
        return "PRE_GRADUATION"


@dataclass(frozen=True, slots=True)
class FastOfflineMarketSnapshot:
    mint: str
    quote_mint: str
    venue: str
    as_of_unix_ms: int
    last_sequence: int | None
    last_price_quote: float | None
    last_reserve_context: FastTrainingReserveContext | None
    last_lifecycle_event: FastTrainingLifecycleEvent | None
    windows: tuple[FastTrainingWindowSummary, ...]

    def __post_init__(self) -> None:
        for name in ("mint", "quote_mint", "venue"):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if self.last_sequence is not None:
            _require_positive_int("last_sequence", self.last_sequence)
        if self.last_price_quote is not None:
            _require_positive_finite("last_price_quote", self.last_price_quote)
        if (
            self.last_reserve_context is not None
            and type(self.last_reserve_context) is not FastTrainingReserveContext
        ):
            raise ValueError(
                "last_reserve_context must be exact FastTrainingReserveContext or None"
            )
        if (
            self.last_lifecycle_event is not None
            and type(self.last_lifecycle_event) is not FastTrainingLifecycleEvent
        ):
            raise ValueError(
                "last_lifecycle_event must be exact FastTrainingLifecycleEvent or None"
            )
        if (
            not isinstance(self.windows, tuple)
            or not self.windows
            or not all(type(value) is FastTrainingWindowSummary for value in self.windows)
        ):
            raise ValueError(
                "windows must be a non-empty tuple of exact FastTrainingWindowSummary values"
            )


@dataclass(frozen=True, slots=True)
class FastOfflineGraduationFlowEvidence:
    pre_snapshot: FastOfflineMarketSnapshot
    boost_context: bool | None
    execution: FastOfflineEntryExecution | None

    def __post_init__(self) -> None:
        if type(self.pre_snapshot) is not FastOfflineMarketSnapshot:
            raise ValueError("pre_snapshot must be exact FastOfflineMarketSnapshot")
        if self.boost_context is not None and type(self.boost_context) is not bool:
            raise ValueError("boost_context must be bool or None")
        if self.execution is not None and type(self.execution) is not FastOfflineEntryExecution:
            raise ValueError("execution must be exact FastOfflineEntryExecution or None")

    @property
    def kind(self) -> str:
        return "GRADUATION_FLOW"


@dataclass(frozen=True, slots=True)
class FastOfflineWalletCohortSideSummary:
    strong_wallet_count: int
    confidence_weighted_strong_count: float
    independently_strong_wallet_count: int | None
    all_pairs_independent_under_evidence: bool | None

    def __post_init__(self) -> None:
        _require_non_negative_int("strong_wallet_count", self.strong_wallet_count)
        _require_non_negative_finite(
            "confidence_weighted_strong_count",
            self.confidence_weighted_strong_count,
        )
        if self.independently_strong_wallet_count is not None:
            _require_non_negative_int(
                "independently_strong_wallet_count",
                self.independently_strong_wallet_count,
            )
        if (
            self.all_pairs_independent_under_evidence is not None
            and type(self.all_pairs_independent_under_evidence) is not bool
        ):
            raise ValueError(
                "all_pairs_independent_under_evidence must be bool or None"
            )


@dataclass(frozen=True, slots=True)
class FastOfflineWalletCohortEvidencePayload:
    version: int
    wallet_feature_policy_version: str
    profile_policy_version: str | None
    relationship_policy_version: str
    support: FastOfflineWalletCohortSideSummary
    exits: FastOfflineWalletCohortSideSummary
    support_hold_horizon_wallet_weight: float
    confidence_weighted_support_median_hold_ms: float | None

    def __post_init__(self) -> None:
        _require_positive_int("version", self.version)
        _require_non_empty_string(
            "wallet_feature_policy_version",
            self.wallet_feature_policy_version,
        )
        if self.profile_policy_version is not None:
            _require_non_empty_string(
                "profile_policy_version",
                self.profile_policy_version,
            )
        _require_non_empty_string(
            "relationship_policy_version",
            self.relationship_policy_version,
        )
        if type(self.support) is not FastOfflineWalletCohortSideSummary:
            raise ValueError(
                "support must be exact FastOfflineWalletCohortSideSummary"
            )
        if type(self.exits) is not FastOfflineWalletCohortSideSummary:
            raise ValueError(
                "exits must be exact FastOfflineWalletCohortSideSummary"
            )
        _require_non_negative_finite(
            "support_hold_horizon_wallet_weight",
            self.support_hold_horizon_wallet_weight,
        )
        if self.confidence_weighted_support_median_hold_ms is not None:
            _require_non_negative_finite(
                "confidence_weighted_support_median_hold_ms",
                self.confidence_weighted_support_median_hold_ms,
            )


@dataclass(frozen=True, slots=True)
class FastOfflineWalletCohortEvidence:
    evidence: FastOfflineWalletCohortEvidencePayload | None

    @property
    def kind(self) -> str:
        return "WALLET_COHORT"


@dataclass(frozen=True, slots=True)
class FastOfflineLongerRunnerProtective:
    hard_stop_triggered: bool
    risk_limit_exit_required: bool
    liquidity_exit_required: bool

    def __post_init__(self) -> None:
        for name in (
            "hard_stop_triggered",
            "risk_limit_exit_required",
            "liquidity_exit_required",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be bool")


@dataclass(frozen=True, slots=True)
class FastOfflineLongerRunnerContinuation:
    version: int
    forecast_source_version: str
    forecast_horizon_ms: int
    base_quantity: float
    current_executable_exit_price_quote: float
    expected_future_exit_price_quote: float
    downside_exit_price_quote: float
    current_exit_capacity_base: float
    expected_future_exit_capacity_base: float
    expected_holding_cost_quote: float
    current_exit_costs: FastOfflineExecutionLegCost
    future_exit_costs: FastOfflineExecutionLegCost

    def __post_init__(self) -> None:
        _require_positive_int("version", self.version)
        _require_non_empty_string(
            "forecast_source_version",
            self.forecast_source_version,
        )
        _require_positive_int("forecast_horizon_ms", self.forecast_horizon_ms)
        for name in (
            "base_quantity",
            "current_executable_exit_price_quote",
            "expected_future_exit_price_quote",
            "downside_exit_price_quote",
            "current_exit_capacity_base",
            "expected_future_exit_capacity_base",
        ):
            _require_positive_finite(name, getattr(self, name))
        _require_non_negative_finite(
            "expected_holding_cost_quote",
            self.expected_holding_cost_quote,
        )
        if type(self.current_exit_costs) is not FastOfflineExecutionLegCost:
            raise ValueError(
                "current_exit_costs must be exact FastOfflineExecutionLegCost"
            )
        if type(self.future_exit_costs) is not FastOfflineExecutionLegCost:
            raise ValueError(
                "future_exit_costs must be exact FastOfflineExecutionLegCost"
            )


@dataclass(frozen=True, slots=True)
class FastOfflineLongerRunnerEvidence:
    protective: FastOfflineLongerRunnerProtective
    continuation: FastOfflineLongerRunnerContinuation | None

    def __post_init__(self) -> None:
        if type(self.protective) is not FastOfflineLongerRunnerProtective:
            raise ValueError(
                "protective must be exact FastOfflineLongerRunnerProtective"
            )
        if (
            self.continuation is not None
            and type(self.continuation) is not FastOfflineLongerRunnerContinuation
        ):
            raise ValueError(
                "continuation must be exact FastOfflineLongerRunnerContinuation or None"
            )

    @property
    def kind(self) -> str:
        return "LONGER_RUNNER"


FastOfflineRowEvidence = (
    FastOfflineImpulseScalpEvidence
    | FastOfflineMicroPullbackEvidence
    | FastOfflinePreGraduationEvidence
    | FastOfflineGraduationFlowEvidence
    | FastOfflineWalletCohortEvidence
    | FastOfflineLongerRunnerEvidence
)


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_bps(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 10_000
    ):
        raise ValueError(f"{name} must be an integer within [0, 10000]")


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
    ):
        raise ValueError(f"{name} must be finite and strictly positive")


def _require_non_negative_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")
