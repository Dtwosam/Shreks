from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from shreks_brain.fast_learning import FAST_FORECAST_FEATURE_NAMES


FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME = "shreks.fast_campaign_decision_batch"
FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME = "shreks.fast_campaign_decision_results"
FAST_CAMPAIGN_DECISION_SCHEMA_VERSION = 1

_ACTIONS = frozenset({"BUY", "SKIP", "HOLD", "REDUCE", "SELL"})
_REASONS = frozenset(
    {
        "BUY_SELECTED",
        "SKIP_SELECTED",
        "HOLD_SELECTED",
        "REDUCE_SELECTED",
        "SELL_SELECTED",
        "FORECAST_EVIDENCE_INCOMPLETE",
        "FORCE_SELL",
    }
)


@dataclass(frozen=True, slots=True)
class FastCampaignContinuousActionPolicy:
    version: int
    horizons_ms: tuple[int, ...]
    entry_exposure_candidates: tuple[float, ...]
    reduce_target_exposure_candidates: tuple[float, ...]
    adverse_excursion_weight: float
    reversal_penalty_bps: float
    route_unavailability_penalty_bps: float
    horizon_disagreement_weight: float
    minimum_buy_value_bps: float
    minimum_hold_value_bps: float
    missing_forecast_open_action: str

    def __post_init__(self) -> None:
        _require_positive_int("version", self.version)
        _require_positive_strictly_increasing_ints("horizons_ms", self.horizons_ms)
        _require_exposure_tuple(
            "entry_exposure_candidates",
            self.entry_exposure_candidates,
            require_non_empty=True,
            require_below_one=False,
        )
        _require_exposure_tuple(
            "reduce_target_exposure_candidates",
            self.reduce_target_exposure_candidates,
            require_non_empty=False,
            require_below_one=True,
        )
        for name in (
            "adverse_excursion_weight",
            "reversal_penalty_bps",
            "route_unavailability_penalty_bps",
            "horizon_disagreement_weight",
            "minimum_buy_value_bps",
            "minimum_hold_value_bps",
        ):
            _require_non_negative_finite(name, getattr(self, name))
        if self.missing_forecast_open_action not in {"REDUCE", "SELL"}:
            raise ValueError("missing_forecast_open_action must be REDUCE or SELL")
        if (
            self.missing_forecast_open_action == "REDUCE"
            and not self.reduce_target_exposure_candidates
        ):
            raise ValueError("REDUCE fallback requires reduction targets")


@dataclass(frozen=True, slots=True)
class FastCampaignDecisionPosition:
    kind: Literal["FLAT", "OPEN"]
    current_exposure_fraction: float | None = None

    def __post_init__(self) -> None:
        if self.kind == "FLAT":
            if self.current_exposure_fraction is not None:
                raise ValueError("FLAT position cannot carry current_exposure_fraction")
            return
        if self.kind != "OPEN":
            raise ValueError("position kind must be FLAT or OPEN")
        if self.current_exposure_fraction is None:
            raise ValueError("OPEN position requires current_exposure_fraction")
        _require_finite_interval(
            "current_exposure_fraction",
            self.current_exposure_fraction,
            minimum=0.0,
            maximum=1.0,
            minimum_open=True,
        )


@dataclass(frozen=True, slots=True)
class FastCampaignReduceExecutionCost:
    target_exposure_fraction: float
    execution_cost_bps: float

    def __post_init__(self) -> None:
        _require_finite_interval(
            "target_exposure_fraction",
            self.target_exposure_fraction,
            minimum=0.0,
            maximum=1.0,
            maximum_open=True,
        )
        _require_non_negative_finite("execution_cost_bps", self.execution_cost_bps)


@dataclass(frozen=True, slots=True)
class FastCampaignActionConstraints:
    max_exposure_fraction: float
    buy_economically_allowed: bool
    expected_future_exit_cost_bps: float
    reduce_execution_costs: tuple[FastCampaignReduceExecutionCost, ...]
    sell_executable: bool
    sell_now_cost_bps: float
    force_sell: bool

    def __post_init__(self) -> None:
        _require_finite_interval(
            "max_exposure_fraction",
            self.max_exposure_fraction,
            minimum=0.0,
            maximum=1.0,
        )
        if type(self.buy_economically_allowed) is not bool:
            raise ValueError("buy_economically_allowed must be bool")
        if type(self.sell_executable) is not bool:
            raise ValueError("sell_executable must be bool")
        if type(self.force_sell) is not bool:
            raise ValueError("force_sell must be bool")
        _require_non_negative_finite(
            "expected_future_exit_cost_bps", self.expected_future_exit_cost_bps
        )
        _require_non_negative_finite("sell_now_cost_bps", self.sell_now_cost_bps)
        if not isinstance(self.reduce_execution_costs, tuple):
            raise ValueError("reduce_execution_costs must be a tuple")
        previous: float | None = None
        for cost in self.reduce_execution_costs:
            if type(cost) is not FastCampaignReduceExecutionCost:
                raise ValueError(
                    "reduce_execution_costs must contain exact FastCampaignReduceExecutionCost values"
                )
            if previous is not None and cost.target_exposure_fraction <= previous:
                raise ValueError(
                    "reduce_execution_costs must be in strictly increasing target order"
                )
            previous = cost.target_exposure_fraction
        if self.force_sell and not self.sell_executable:
            raise ValueError("force_sell requires sell_executable")


@dataclass(frozen=True, slots=True)
class FastCampaignDecisionRequest:
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    features: tuple[float | None, ...]
    position: FastCampaignDecisionPosition
    constraints: FastCampaignActionConstraints

    def __post_init__(self) -> None:
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_non_empty_string("market_key", self.market_key)
        _require_positive_int("source_sequence", self.source_sequence)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.features, tuple):
            raise ValueError("features must be a tuple")
        if len(self.features) != len(FAST_FORECAST_FEATURE_NAMES):
            raise ValueError(
                f"features must contain exactly {len(FAST_FORECAST_FEATURE_NAMES)} values"
            )
        for value in self.features:
            if value is not None:
                _require_finite("feature", value)
        if type(self.position) is not FastCampaignDecisionPosition:
            raise ValueError("position must be an exact FastCampaignDecisionPosition")
        if type(self.constraints) is not FastCampaignActionConstraints:
            raise ValueError("constraints must be exact FastCampaignActionConstraints")


@dataclass(frozen=True, slots=True)
class FastCampaignDecisionBatch:
    schema_name: str
    schema_version: int
    policy: FastCampaignContinuousActionPolicy
    decisions: tuple[FastCampaignDecisionRequest, ...]

    def __post_init__(self) -> None:
        if self.schema_name != FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME:
            raise ValueError("unsupported campaign decision request schema_name")
        if self.schema_version != FAST_CAMPAIGN_DECISION_SCHEMA_VERSION:
            raise ValueError("unsupported campaign decision request schema_version")
        if type(self.policy) is not FastCampaignContinuousActionPolicy:
            raise ValueError("policy must be an exact FastCampaignContinuousActionPolicy")
        if not isinstance(self.decisions, tuple) or not self.decisions:
            raise ValueError("decisions must be a non-empty tuple")

        seen: set[str] = set()
        latest_by_market: dict[str, tuple[int, int]] = {}
        for decision in self.decisions:
            if type(decision) is not FastCampaignDecisionRequest:
                raise ValueError("decisions must contain exact FastCampaignDecisionRequest values")
            if decision.source_event_id in seen:
                raise ValueError("duplicate source event identity")
            seen.add(decision.source_event_id)
            previous = latest_by_market.get(decision.market_key)
            if previous is not None:
                if decision.source_sequence <= previous[0]:
                    raise ValueError("per-market source sequence order regressed")
                if decision.as_of_unix_ms < previous[1]:
                    raise ValueError("per-market timestamp order regressed")
            latest_by_market[decision.market_key] = (
                decision.source_sequence,
                decision.as_of_unix_ms,
            )


@dataclass(frozen=True, slots=True)
class FastCampaignHorizonEvidence:
    horizon_ms: int
    entry_cost_adjusted_return_model_version: str
    endpoint_return_model_version: str
    mae_model_version: str
    reversal_model_version: str
    route_unavailability_model_version: str
    entry_cost_adjusted_return_bps: float
    raw_endpoint_return_bps: float
    mae_bps: float
    adverse_excursion_bps: float
    reversal_probability: float
    route_unavailability_probability: float
    disagreement_bps: float
    risk_bps: float

    def __post_init__(self) -> None:
        _require_positive_int("horizon_ms", self.horizon_ms)
        for name in (
            "entry_cost_adjusted_return_model_version",
            "endpoint_return_model_version",
            "mae_model_version",
            "reversal_model_version",
            "route_unavailability_model_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        for name in (
            "entry_cost_adjusted_return_bps",
            "raw_endpoint_return_bps",
            "mae_bps",
            "adverse_excursion_bps",
            "reversal_probability",
            "route_unavailability_probability",
            "disagreement_bps",
            "risk_bps",
        ):
            _require_finite(name, getattr(self, name))
        for name in ("reversal_probability", "route_unavailability_probability"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie within [0,1]")


@dataclass(frozen=True, slots=True)
class FastCampaignActionCandidate:
    action: str
    horizon_ms: int | None
    target_exposure_fraction: float
    reward_bps: float
    risk_bps: float
    execution_cost_penalty_bps: float
    comparison_value_bps: float
    eligible: bool

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError("candidate action is unsupported")
        if self.horizon_ms is not None:
            _require_positive_int("horizon_ms", self.horizon_ms)
        _require_finite_interval(
            "target_exposure_fraction",
            self.target_exposure_fraction,
            minimum=0.0,
            maximum=1.0,
        )
        for name in (
            "reward_bps",
            "risk_bps",
            "execution_cost_penalty_bps",
            "comparison_value_bps",
        ):
            _require_finite(name, getattr(self, name))
        if type(self.eligible) is not bool:
            raise ValueError("eligible must be bool")


@dataclass(frozen=True, slots=True)
class FastCampaignDecisionResult:
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    policy_version: int
    action: str
    reason: str
    selected_horizon_ms: int | None
    current_exposure_fraction: float
    target_exposure_fraction: float
    selected_reward_bps: float
    selected_risk_bps: float
    selected_execution_cost_bps: float
    selected_value_bps: float
    horizon_evidence: tuple[FastCampaignHorizonEvidence, ...]
    candidates: tuple[FastCampaignActionCandidate, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_non_empty_string("market_key", self.market_key)
        _require_positive_int("source_sequence", self.source_sequence)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_positive_int("policy_version", self.policy_version)
        if self.action not in _ACTIONS:
            raise ValueError("result action is unsupported")
        if self.reason not in _REASONS:
            raise ValueError("result reason is unsupported")
        if self.selected_horizon_ms is not None:
            _require_positive_int("selected_horizon_ms", self.selected_horizon_ms)
        for name in (
            "current_exposure_fraction",
            "target_exposure_fraction",
            "selected_reward_bps",
            "selected_risk_bps",
            "selected_execution_cost_bps",
            "selected_value_bps",
        ):
            _require_finite(name, getattr(self, name))
        if not isinstance(self.horizon_evidence, tuple):
            raise ValueError("horizon_evidence must be a tuple")
        if not isinstance(self.candidates, tuple) or not self.candidates:
            raise ValueError("candidates must be a non-empty tuple")


@dataclass(frozen=True, slots=True)
class FastCampaignDecisionResults:
    schema_name: str
    schema_version: int
    champion_version: str
    champion_fingerprint_sha256: str
    decisions: tuple[FastCampaignDecisionResult, ...]
    batch_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME:
            raise ValueError("unsupported campaign result schema_name")
        if self.schema_version != FAST_CAMPAIGN_DECISION_SCHEMA_VERSION:
            raise ValueError("unsupported campaign result schema_version")
        _require_non_empty_string("champion_version", self.champion_version)
        _require_sha256("champion_fingerprint_sha256", self.champion_fingerprint_sha256)
        _require_sha256("batch_fingerprint_sha256", self.batch_fingerprint_sha256)
        if not isinstance(self.decisions, tuple) or not self.decisions:
            raise ValueError("result decisions must be a non-empty tuple")


def build_fast_campaign_decision_batch(
    policy: FastCampaignContinuousActionPolicy,
    decisions: tuple[FastCampaignDecisionRequest, ...],
) -> FastCampaignDecisionBatch:
    return FastCampaignDecisionBatch(
        schema_name=FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME,
        schema_version=FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        policy=policy,
        decisions=decisions,
    )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if float(value) < 0.0:
        raise ValueError(f"{name} must be non-negative")


def _require_finite_interval(
    name: str,
    value: object,
    *,
    minimum: float,
    maximum: float,
    minimum_open: bool = False,
    maximum_open: bool = False,
) -> None:
    _require_finite(name, value)
    scalar = float(value)
    minimum_ok = scalar > minimum if minimum_open else scalar >= minimum
    maximum_ok = scalar < maximum if maximum_open else scalar <= maximum
    if not minimum_ok or not maximum_ok:
        raise ValueError(f"{name} is outside the permitted interval")


def _require_positive_strictly_increasing_ints(
    name: str, values: object
) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError(f"{name} must be a non-empty tuple")
    previous: int | None = None
    for value in values:
        _require_positive_int(name, value)
        if previous is not None and value <= previous:
            raise ValueError(f"{name} must be strictly increasing")
        previous = value


def _require_exposure_tuple(
    name: str,
    values: object,
    *,
    require_non_empty: bool,
    require_below_one: bool,
) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple")
    if require_non_empty and not values:
        raise ValueError(f"{name} cannot be empty")
    previous: float | None = None
    for value in values:
        _require_finite_interval(
            name,
            value,
            minimum=0.0,
            maximum=1.0,
            minimum_open=True,
            maximum_open=require_below_one,
        )
        scalar = float(value)
        if previous is not None and scalar <= previous:
            raise ValueError(f"{name} must be strictly increasing")
        previous = scalar


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
