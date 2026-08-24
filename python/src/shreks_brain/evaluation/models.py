from __future__ import annotations

from dataclasses import dataclass
import math


TRADING_EVALUATION_SCHEMA_VERSION = "e5-trading-evaluation-v1"
_ARITH_REL_TOL = 1e-12
_ARITH_ABS_TOL = 1e-9


@dataclass(frozen=True, slots=True)
class TradingEvaluationPolicy:
    version: str
    starting_equity_usd: float
    calibration_bucket_count: int

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_positive_finite("starting_equity_usd", self.starting_equity_usd)
        if (
            isinstance(self.calibration_bucket_count, bool)
            or not isinstance(self.calibration_bucket_count, int)
            or self.calibration_bucket_count < 2
            or self.calibration_bucket_count > 100
        ):
            raise ValueError("calibration_bucket_count must be an integer within [2, 100]")


@dataclass(frozen=True, slots=True)
class EvaluatedTrade:
    candidate_version: str
    position_id: str
    candidate_mint: str
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
            "candidate_mint",
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
        if self.turnover_usd < self.entry_notional_usd:
            raise ValueError("turnover_usd must be at least entry_notional_usd")
        _require_finite("gross_pnl_usd", self.gross_pnl_usd)
        _require_non_negative_finite(
            "execution_friction_usd", self.execution_friction_usd
        )
        _require_non_negative_finite("explicit_cost_usd", self.explicit_cost_usd)
        _require_finite("net_pnl_usd", self.net_pnl_usd)
        _require_close(
            "net_pnl_usd",
            self.net_pnl_usd,
            self.gross_pnl_usd
            - self.execution_friction_usd
            - self.explicit_cost_usd,
        )


@dataclass(frozen=True, slots=True)
class ProbabilityObservation:
    candidate_version: str
    model_version: str
    candidate_mint: str
    as_of_unix_ms: int
    positive_probability: float
    target_positive: bool
    setup_name: str
    market_regime: str
    fold_name: str

    def __post_init__(self) -> None:
        for name in (
            "candidate_version",
            "model_version",
            "candidate_mint",
            "setup_name",
            "market_regime",
            "fold_name",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_fraction("positive_probability", self.positive_probability)
        if type(self.target_positive) is not bool:
            raise ValueError("target_positive must be an exact bool")


@dataclass(frozen=True, slots=True)
class TradingPerformanceMetrics:
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
    average_winner_usd: float | None
    average_loser_usd: float | None
    win_rate: float | None
    turnover_usd: float
    turnover_to_starting_equity: float
    execution_friction_usd: float
    explicit_cost_usd: float
    total_cost_usd: float
    cost_burden_pct: float | None

    def __post_init__(self) -> None:
        for name in ("trade_count", "win_count", "loss_count", "flat_count"):
            _require_non_negative_int(name, getattr(self, name))
        if self.trade_count != self.win_count + self.loss_count + self.flat_count:
            raise ValueError("trade counts must reconcile")

        _require_finite("gross_pnl_usd", self.gross_pnl_usd)
        _require_finite("net_pnl_usd", self.net_pnl_usd)
        _require_optional_finite("net_expectancy_usd", self.net_expectancy_usd)
        _require_optional_finite("net_expectancy_pct", self.net_expectancy_pct)
        _require_optional_non_negative_finite("profit_factor", self.profit_factor)
        _require_non_negative_finite("maximum_drawdown_usd", self.maximum_drawdown_usd)
        _require_fraction_percent("maximum_drawdown_pct", self.maximum_drawdown_pct)
        _require_optional_finite("average_winner_usd", self.average_winner_usd)
        _require_optional_finite("average_loser_usd", self.average_loser_usd)
        _require_optional_fraction("win_rate", self.win_rate)
        _require_non_negative_finite("turnover_usd", self.turnover_usd)
        _require_non_negative_finite(
            "turnover_to_starting_equity", self.turnover_to_starting_equity
        )
        _require_non_negative_finite(
            "execution_friction_usd", self.execution_friction_usd
        )
        _require_non_negative_finite("explicit_cost_usd", self.explicit_cost_usd)
        _require_non_negative_finite("total_cost_usd", self.total_cost_usd)
        _require_optional_non_negative_finite("cost_burden_pct", self.cost_burden_pct)

        _require_close(
            "total_cost_usd",
            self.total_cost_usd,
            self.execution_friction_usd + self.explicit_cost_usd,
        )
        _require_close(
            "net_pnl_usd",
            self.net_pnl_usd,
            self.gross_pnl_usd - self.total_cost_usd,
        )

        if self.trade_count == 0:
            if any(
                value is not None
                for value in (
                    self.net_expectancy_usd,
                    self.net_expectancy_pct,
                    self.profit_factor,
                    self.average_winner_usd,
                    self.average_loser_usd,
                    self.win_rate,
                    self.cost_burden_pct,
                )
            ):
                raise ValueError("undefined empty-trade metrics must be None")
            for name in (
                "gross_pnl_usd",
                "net_pnl_usd",
                "maximum_drawdown_usd",
                "maximum_drawdown_pct",
                "turnover_usd",
                "turnover_to_starting_equity",
                "execution_friction_usd",
                "explicit_cost_usd",
                "total_cost_usd",
            ):
                _require_zero(name, getattr(self, name))
            return

        if self.net_expectancy_usd is None or self.net_expectancy_pct is None:
            raise ValueError("non-empty metrics require expectancy values")
        if self.win_rate is None:
            raise ValueError("non-empty metrics require win_rate")
        if self.turnover_usd <= 0.0:
            raise ValueError("non-empty metrics require positive turnover_usd")
        if self.cost_burden_pct is None:
            raise ValueError("non-empty metrics require cost_burden_pct")

        _require_close(
            "net_expectancy_usd",
            self.net_expectancy_usd,
            self.net_pnl_usd / self.trade_count,
        )
        _require_close("win_rate", self.win_rate, self.win_count / self.trade_count)
        _require_close(
            "cost_burden_pct",
            self.cost_burden_pct,
            self.total_cost_usd / self.turnover_usd * 100.0,
        )

        if self.win_count == 0:
            if self.average_winner_usd is not None:
                raise ValueError("average_winner_usd must be None with no wins")
        elif self.average_winner_usd is None or self.average_winner_usd <= 0.0:
            raise ValueError("wins require a strictly positive average_winner_usd")

        if self.loss_count == 0:
            if self.average_loser_usd is not None:
                raise ValueError("average_loser_usd must be None with no losses")
        elif self.average_loser_usd is None or self.average_loser_usd >= 0.0:
            raise ValueError("losses require a strictly negative average_loser_usd")

        expected_net = 0.0
        if self.average_winner_usd is not None:
            expected_net += self.average_winner_usd * self.win_count
        if self.average_loser_usd is not None:
            expected_net += self.average_loser_usd * self.loss_count
        _require_close("winner/loser net_pnl_usd", self.net_pnl_usd, expected_net)


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    bucket_index: int
    lower_probability: float
    upper_probability: float
    observation_count: int
    mean_predicted_probability: float | None
    observed_positive_rate: float | None
    absolute_calibration_gap: float | None

    def __post_init__(self) -> None:
        _require_non_negative_int("bucket_index", self.bucket_index)
        _require_fraction("lower_probability", self.lower_probability)
        _require_fraction("upper_probability", self.upper_probability)
        if self.lower_probability >= self.upper_probability:
            raise ValueError("calibration bucket bounds must satisfy lower < upper")
        _require_non_negative_int("observation_count", self.observation_count)

        if self.observation_count == 0:
            if any(
                value is not None
                for value in (
                    self.mean_predicted_probability,
                    self.observed_positive_rate,
                    self.absolute_calibration_gap,
                )
            ):
                raise ValueError("empty calibration buckets require None statistics")
            return

        if (
            self.mean_predicted_probability is None
            or self.observed_positive_rate is None
            or self.absolute_calibration_gap is None
        ):
            raise ValueError("non-empty calibration buckets require statistics")
        _require_fraction(
            "mean_predicted_probability", self.mean_predicted_probability
        )
        _require_fraction("observed_positive_rate", self.observed_positive_rate)
        _require_fraction(
            "absolute_calibration_gap", self.absolute_calibration_gap
        )
        _require_close(
            "absolute_calibration_gap",
            self.absolute_calibration_gap,
            abs(self.mean_predicted_probability - self.observed_positive_rate),
        )


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    observation_count: int
    positive_count: int
    brier_score: float
    expected_calibration_error: float
    buckets: tuple[CalibrationBucket, ...]

    def __post_init__(self) -> None:
        _require_positive_int("observation_count", self.observation_count)
        _require_non_negative_int("positive_count", self.positive_count)
        if self.positive_count > self.observation_count:
            raise ValueError("positive_count cannot exceed observation_count")
        _require_fraction("brier_score", self.brier_score)
        _require_fraction(
            "expected_calibration_error", self.expected_calibration_error
        )
        if not isinstance(self.buckets, tuple) or not self.buckets:
            raise ValueError("buckets must be a non-empty tuple")
        if not all(type(value) is CalibrationBucket for value in self.buckets):
            raise ValueError("buckets must contain exact CalibrationBucket values")
        if tuple(value.bucket_index for value in self.buckets) != tuple(
            range(len(self.buckets))
        ):
            raise ValueError("calibration bucket indices must be contiguous from zero")
        if not math.isclose(
            self.buckets[0].lower_probability,
            0.0,
            rel_tol=_ARITH_REL_TOL,
            abs_tol=_ARITH_ABS_TOL,
        ):
            raise ValueError("calibration buckets must start at probability zero")
        if not math.isclose(
            self.buckets[-1].upper_probability,
            1.0,
            rel_tol=_ARITH_REL_TOL,
            abs_tol=_ARITH_ABS_TOL,
        ):
            raise ValueError("calibration buckets must end at probability one")
        for previous, current in zip(self.buckets, self.buckets[1:]):
            _require_close(
                "calibration bucket adjacency",
                previous.upper_probability,
                current.lower_probability,
            )
        if sum(value.observation_count for value in self.buckets) != self.observation_count:
            raise ValueError("calibration bucket counts must reconcile")

        expected_positive = math.fsum(
            (value.observed_positive_rate or 0.0) * value.observation_count
            for value in self.buckets
        )
        _require_close("positive_count", float(self.positive_count), expected_positive)
        expected_ece = math.fsum(
            (value.absolute_calibration_gap or 0.0)
            * value.observation_count
            / self.observation_count
            for value in self.buckets
        )
        _require_close(
            "expected_calibration_error",
            self.expected_calibration_error,
            expected_ece,
        )


@dataclass(frozen=True, slots=True)
class SegmentPerformance:
    segment_name: str
    metrics: TradingPerformanceMetrics

    def __post_init__(self) -> None:
        _require_non_empty_string("segment_name", self.segment_name)
        if type(self.metrics) is not TradingPerformanceMetrics:
            raise ValueError("metrics must be an exact TradingPerformanceMetrics")


@dataclass(frozen=True, slots=True)
class TradingEvaluationReport:
    schema_version: str
    policy_version: str
    candidate_version: str
    metrics: TradingPerformanceMetrics
    calibration: CalibrationReport | None
    setup_performance: tuple[SegmentPerformance, ...]
    regime_performance: tuple[SegmentPerformance, ...]
    evaluation_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != TRADING_EVALUATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {TRADING_EVALUATION_SCHEMA_VERSION}"
            )
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("candidate_version", self.candidate_version)
        if type(self.metrics) is not TradingPerformanceMetrics:
            raise ValueError("metrics must be an exact TradingPerformanceMetrics")
        if self.calibration is not None and type(self.calibration) is not CalibrationReport:
            raise ValueError("calibration must be an exact CalibrationReport or None")
        self._validate_segments("setup_performance", self.setup_performance)
        self._validate_segments("regime_performance", self.regime_performance)
        _require_sha256(
            "evaluation_fingerprint_sha256", self.evaluation_fingerprint_sha256
        )

    def _validate_segments(
        self, name: str, segments: tuple[SegmentPerformance, ...]
    ) -> None:
        if not isinstance(segments, tuple) or not all(
            type(value) is SegmentPerformance for value in segments
        ):
            raise ValueError(f"{name} must be a tuple of exact SegmentPerformance values")
        names = tuple(value.segment_name for value in segments)
        if names != tuple(sorted(names)):
            raise ValueError(f"{name} must be in lexical segment order")
        if len(names) != len(set(names)):
            raise ValueError(f"{name} segment names must be unique")
        if self.metrics.trade_count == 0:
            if segments:
                raise ValueError(f"{name} must be empty when there are no trades")
            return
        if not segments:
            raise ValueError(f"{name} cannot be empty when trades exist")
        if any(value.metrics.trade_count == 0 for value in segments):
            raise ValueError(f"{name} cannot contain empty segments")
        if sum(value.metrics.trade_count for value in segments) != self.metrics.trade_count:
            raise ValueError(f"{name} trade counts must reconcile to overall metrics")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
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


def _require_fraction(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0 or value > 1:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 1]")


def _require_optional_fraction(name: str, value: object | None) -> None:
    if value is not None:
        _require_fraction(name, value)


def _require_fraction_percent(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0 or value > 100:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 100]")


def _require_close(name: str, actual: float, expected: float) -> None:
    if not math.isclose(
        actual,
        expected,
        rel_tol=_ARITH_REL_TOL,
        abs_tol=_ARITH_ABS_TOL,
    ):
        raise ValueError(f"{name} is inconsistent")


def _require_zero(name: str, value: float) -> None:
    _require_close(name, value, 0.0)


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256 hex digest")
