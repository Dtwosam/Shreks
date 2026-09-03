from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
import hashlib
import json
import math
import string

from shreks_brain.fast_learning.models import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTargetKind,
)


FAST_FORECAST_EVALUATION_SCHEMA_NAME = "shreks.fast_lane_forecast_evaluation"
FAST_FORECAST_EVALUATION_SCHEMA_VERSION = 1
_ARITH_REL_TOL = 1e-12
_ARITH_ABS_TOL = 1e-9
_COST_ADJUSTED_TARGETS = frozenset(
    {
        FastForecastTarget.BEST_COST_ADJUSTED_RETURN_BPS,
        FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
    }
)


class FastForecastEvaluationPartition(StrEnum):
    VALIDATION = "VALIDATION"
    TEST = "TEST"


@dataclass(frozen=True, slots=True)
class FastForecastEvaluationContext:
    decision_identity: tuple[object, ...]
    as_of_unix_ms: int
    market_regime: str
    strategy_families: tuple[str, ...]
    executable_exit_capacity_quote: float | None
    expected_round_trip_cost_bps: float | None

    def __post_init__(self) -> None:
        _validate_decision_identity(self.decision_identity)
        _non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if self.as_of_unix_ms != self.decision_identity[6]:
            raise ValueError("context as_of timestamp must match decision identity timestamp")
        _non_empty("market_regime", self.market_regime)
        if not isinstance(self.strategy_families, tuple) or not self.strategy_families:
            raise ValueError("strategy_families must be a non-empty tuple")
        for value in self.strategy_families:
            _non_empty("strategy family", value)
        if self.strategy_families != tuple(sorted(self.strategy_families)):
            raise ValueError("strategy_families must be in canonical sorted order")
        if len(set(self.strategy_families)) != len(self.strategy_families):
            raise ValueError("strategy_families must be unique")
        _optional_non_negative_finite(
            "executable_exit_capacity_quote", self.executable_exit_capacity_quote
        )
        _optional_non_negative_finite(
            "expected_round_trip_cost_bps", self.expected_round_trip_cost_bps
        )


@dataclass(frozen=True, slots=True)
class FastForecastEvaluationPolicy:
    version: str
    partition: FastForecastEvaluationPartition
    probability_bucket_count: int
    liquidity_capacity_quote_boundaries: tuple[float, ...]
    round_trip_cost_bps_boundaries: tuple[float, ...]
    binary_log_loss_clip_epsilon: float

    def __post_init__(self) -> None:
        _non_empty("version", self.version)
        if type(self.partition) is not FastForecastEvaluationPartition:
            raise ValueError("partition must be an exact FastForecastEvaluationPartition")
        if (
            isinstance(self.probability_bucket_count, bool)
            or not isinstance(self.probability_bucket_count, int)
            or self.probability_bucket_count < 2
            or self.probability_bucket_count > 100
        ):
            raise ValueError("probability_bucket_count must be an integer within [2, 100]")
        _boundaries(
            "liquidity_capacity_quote_boundaries",
            self.liquidity_capacity_quote_boundaries,
        )
        _boundaries(
            "round_trip_cost_bps_boundaries",
            self.round_trip_cost_bps_boundaries,
        )
        _finite("binary_log_loss_clip_epsilon", self.binary_log_loss_clip_epsilon)
        if not 0.0 < self.binary_log_loss_clip_epsilon < 0.5:
            raise ValueError("binary_log_loss_clip_epsilon must lie strictly within (0, 0.5)")


@dataclass(frozen=True, slots=True)
class FastCalibrationBucket:
    bucket_index: int
    lower_probability: float
    upper_probability: float
    observation_count: int
    mean_predicted_probability: float | None
    observed_positive_rate: float | None
    absolute_calibration_gap: float | None

    def __post_init__(self) -> None:
        _non_negative_int("bucket_index", self.bucket_index)
        _fraction("lower_probability", self.lower_probability)
        _fraction("upper_probability", self.upper_probability)
        if self.lower_probability >= self.upper_probability:
            raise ValueError("calibration bucket bounds must satisfy lower < upper")
        _non_negative_int("observation_count", self.observation_count)
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
        _fraction("mean_predicted_probability", self.mean_predicted_probability)
        _fraction("observed_positive_rate", self.observed_positive_rate)
        _fraction("absolute_calibration_gap", self.absolute_calibration_gap)
        _close(
            "absolute_calibration_gap",
            self.absolute_calibration_gap,
            abs(self.mean_predicted_probability - self.observed_positive_rate),
        )


@dataclass(frozen=True, slots=True)
class FastContinuousForecastMetrics:
    observation_count: int
    mean_predicted_value: float
    mean_actual_value: float
    mean_error: float
    mean_absolute_error: float
    root_mean_squared_error: float

    def __post_init__(self) -> None:
        _positive_int("observation_count", self.observation_count)
        for name in (
            "mean_predicted_value",
            "mean_actual_value",
            "mean_error",
            "mean_absolute_error",
            "root_mean_squared_error",
        ):
            _finite(name, getattr(self, name))
        if self.mean_absolute_error < 0.0:
            raise ValueError("mean_absolute_error must be non-negative")
        if self.root_mean_squared_error < 0.0:
            raise ValueError("root_mean_squared_error must be non-negative")
        _close(
            "mean_error reconciliation",
            self.mean_error,
            self.mean_predicted_value - self.mean_actual_value,
        )
        if self.mean_absolute_error + _ARITH_ABS_TOL < abs(self.mean_error):
            raise ValueError("mean_absolute_error contradicts mean_error")
        if self.root_mean_squared_error + _ARITH_ABS_TOL < self.mean_absolute_error:
            raise ValueError("root_mean_squared_error cannot be smaller than mean_absolute_error")


@dataclass(frozen=True, slots=True)
class FastBinaryForecastMetrics:
    observation_count: int
    positive_count: int
    mean_predicted_probability: float
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    calibration_buckets: tuple[FastCalibrationBucket, ...]

    def __post_init__(self) -> None:
        _positive_int("observation_count", self.observation_count)
        _non_negative_int("positive_count", self.positive_count)
        if self.positive_count > self.observation_count:
            raise ValueError("positive_count cannot exceed observation_count")
        _fraction("mean_predicted_probability", self.mean_predicted_probability)
        _fraction("brier_score", self.brier_score)
        _non_negative_finite("log_loss", self.log_loss)
        _fraction("expected_calibration_error", self.expected_calibration_error)
        if not isinstance(self.calibration_buckets, tuple) or not self.calibration_buckets:
            raise ValueError("calibration_buckets must be a non-empty tuple")
        if not all(type(value) is FastCalibrationBucket for value in self.calibration_buckets):
            raise ValueError("calibration_buckets must contain exact FastCalibrationBucket values")
        if tuple(value.bucket_index for value in self.calibration_buckets) != tuple(
            range(len(self.calibration_buckets))
        ):
            raise ValueError("calibration bucket indices must be contiguous from zero")
        _close(
            "first calibration lower bound",
            self.calibration_buckets[0].lower_probability,
            0.0,
        )
        _close(
            "last calibration upper bound",
            self.calibration_buckets[-1].upper_probability,
            1.0,
        )
        for previous, current in zip(
            self.calibration_buckets, self.calibration_buckets[1:]
        ):
            _close(
                "calibration bucket adjacency",
                previous.upper_probability,
                current.lower_probability,
            )
        if sum(value.observation_count for value in self.calibration_buckets) != self.observation_count:
            raise ValueError("calibration bucket observation counts do not reconcile")
        expected_positive = math.fsum(
            (value.observed_positive_rate or 0.0) * value.observation_count
            for value in self.calibration_buckets
        )
        _close("positive_count reconciliation", float(self.positive_count), expected_positive)
        expected_mean = math.fsum(
            (value.mean_predicted_probability or 0.0) * value.observation_count
            for value in self.calibration_buckets
        ) / self.observation_count
        _close("mean predicted probability reconciliation", self.mean_predicted_probability, expected_mean)
        expected_ece = math.fsum(
            (value.absolute_calibration_gap or 0.0)
            * value.observation_count
            / self.observation_count
            for value in self.calibration_buckets
        )
        _close("expected calibration error reconciliation", self.expected_calibration_error, expected_ece)


@dataclass(frozen=True, slots=True)
class FastForecastMetricPopulation:
    name: str
    prediction_count: int
    scored_observation_count: int
    target_unavailable_count: int
    continuous_metrics: FastContinuousForecastMetrics | None
    binary_metrics: FastBinaryForecastMetrics | None

    def __post_init__(self) -> None:
        _non_empty("name", self.name)
        for field_name in (
            "prediction_count",
            "scored_observation_count",
            "target_unavailable_count",
        ):
            _non_negative_int(field_name, getattr(self, field_name))
        if self.prediction_count <= 0:
            raise ValueError("metric population prediction_count must be positive")
        if self.scored_observation_count + self.target_unavailable_count != self.prediction_count:
            raise ValueError("metric population availability counts do not reconcile")
        if self.scored_observation_count == 0:
            if self.continuous_metrics is not None or self.binary_metrics is not None:
                raise ValueError("unavailable-only metric population cannot contain metrics")
            return
        has_continuous = self.continuous_metrics is not None
        has_binary = self.binary_metrics is not None
        if has_continuous == has_binary:
            raise ValueError("scored metric population requires exactly one metric payload")
        if self.continuous_metrics is not None:
            if type(self.continuous_metrics) is not FastContinuousForecastMetrics:
                raise ValueError("continuous_metrics must be exact FastContinuousForecastMetrics")
            if self.continuous_metrics.observation_count != self.scored_observation_count:
                raise ValueError("continuous metric observation count does not reconcile")
        if self.binary_metrics is not None:
            if type(self.binary_metrics) is not FastBinaryForecastMetrics:
                raise ValueError("binary_metrics must be exact FastBinaryForecastMetrics")
            if self.binary_metrics.observation_count != self.scored_observation_count:
                raise ValueError("binary metric observation count does not reconcile")


@dataclass(frozen=True, slots=True)
class FastForecastEvaluationReport:
    schema_name: str
    schema_version: int
    evaluation_policy: FastForecastEvaluationPolicy
    validation_policy_version: str
    validation_run_fingerprint_sha256: str
    training_bundle_fingerprint_sha256: str
    model_version: str
    model_family: FastForecastModelFamily
    target: FastForecastTarget
    target_kind: FastForecastTargetKind
    horizon_ms: int
    target_is_cost_adjusted: bool
    fold_artifact_fingerprints: tuple[tuple[str, str], ...]
    context_fingerprint_sha256: str
    overall: FastForecastMetricPopulation
    fold_populations: tuple[FastForecastMetricPopulation, ...]
    regime_populations: tuple[FastForecastMetricPopulation, ...]
    strategy_family_populations: tuple[FastForecastMetricPopulation, ...]
    liquidity_bucket_populations: tuple[FastForecastMetricPopulation, ...]
    cost_bucket_populations: tuple[FastForecastMetricPopulation, ...]
    evaluation_report_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FORECAST_EVALUATION_SCHEMA_NAME:
            raise ValueError("forecast evaluation schema name is incompatible")
        if self.schema_version != FAST_FORECAST_EVALUATION_SCHEMA_VERSION:
            raise ValueError("forecast evaluation schema version is incompatible")
        if type(self.evaluation_policy) is not FastForecastEvaluationPolicy:
            raise ValueError("evaluation_policy must be exact FastForecastEvaluationPolicy")
        _non_empty("validation_policy_version", self.validation_policy_version)
        _sha256("validation_run_fingerprint_sha256", self.validation_run_fingerprint_sha256)
        _sha256("training_bundle_fingerprint_sha256", self.training_bundle_fingerprint_sha256)
        _non_empty("model_version", self.model_version)
        if type(self.model_family) is not FastForecastModelFamily:
            raise ValueError("model_family must be exact FastForecastModelFamily")
        if type(self.target) is not FastForecastTarget:
            raise ValueError("target must be exact FastForecastTarget")
        if type(self.target_kind) is not FastForecastTargetKind or self.target_kind is not self.target.kind:
            raise ValueError("target_kind must exactly match target")
        _positive_int("horizon_ms", self.horizon_ms)
        if type(self.target_is_cost_adjusted) is not bool:
            raise ValueError("target_is_cost_adjusted must be a bool")
        if self.target_is_cost_adjusted != (self.target in _COST_ADJUSTED_TARGETS):
            raise ValueError("target_is_cost_adjusted contradicts target")
        _fold_artifact_fingerprints(self.fold_artifact_fingerprints)
        _sha256("context_fingerprint_sha256", self.context_fingerprint_sha256)
        if type(self.overall) is not FastForecastMetricPopulation or self.overall.name != "overall":
            raise ValueError("overall must be the exact overall metric population")
        if self.overall.scored_observation_count <= 0:
            raise ValueError("overall forecast evaluation population requires scorable evidence")
        dimensions = (
            ("fold_populations", self.fold_populations, True),
            ("regime_populations", self.regime_populations, True),
            ("strategy_family_populations", self.strategy_family_populations, False),
            ("liquidity_bucket_populations", self.liquidity_bucket_populations, True),
            ("cost_bucket_populations", self.cost_bucket_populations, True),
        )
        for name, values, reconcile in dimensions:
            _population_tuple(name, values)
            for value in values:
                _metric_kind(value, self.target_kind)
            if reconcile:
                _reconcile_dimension(name, values, self.overall)
        _metric_kind(self.overall, self.target_kind)
        _sha256(
            "evaluation_report_fingerprint_sha256",
            self.evaluation_report_fingerprint_sha256,
        )


def fast_forecast_evaluation_report_fingerprint_sha256(
    report: FastForecastEvaluationReport,
) -> str:
    if type(report) is not FastForecastEvaluationReport:
        raise ValueError("report must be an exact FastForecastEvaluationReport")
    payload = {
        field.name: getattr(report, field.name)
        for field in fields(report)
        if field.name != "evaluation_report_fingerprint_sha256"
    }
    encoded = json.dumps(
        _canonical_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fast_forecast_context_fingerprint_sha256(
    contexts: tuple[FastForecastEvaluationContext, ...],
) -> str:
    if not isinstance(contexts, tuple) or not contexts:
        raise ValueError("contexts must be a non-empty tuple")
    if not all(type(value) is FastForecastEvaluationContext for value in contexts):
        raise ValueError("contexts must contain exact FastForecastEvaluationContext values")
    encoded = json.dumps(
        _canonical_value(contexts),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _metric_kind(population: FastForecastMetricPopulation, kind: FastForecastTargetKind) -> None:
    if population.scored_observation_count == 0:
        if population.continuous_metrics is not None or population.binary_metrics is not None:
            raise ValueError("unavailable-only population cannot contain metric payloads")
        return
    if kind is FastForecastTargetKind.CONTINUOUS and population.continuous_metrics is None:
        raise ValueError("continuous target requires continuous metrics for scored populations")
    if kind is FastForecastTargetKind.BINARY and population.binary_metrics is None:
        raise ValueError("binary target requires binary metrics for scored populations")


def _reconcile_dimension(
    name: str,
    values: tuple[FastForecastMetricPopulation, ...],
    overall: FastForecastMetricPopulation,
) -> None:
    if not values:
        raise ValueError(f"{name} cannot be empty")
    if sum(value.prediction_count for value in values) != overall.prediction_count:
        raise ValueError(f"{name} prediction counts do not reconcile to overall")
    if sum(value.scored_observation_count for value in values) != overall.scored_observation_count:
        raise ValueError(f"{name} scored counts do not reconcile to overall")
    if sum(value.target_unavailable_count for value in values) != overall.target_unavailable_count:
        raise ValueError(f"{name} unavailable counts do not reconcile to overall")


def _population_tuple(name: str, values: object) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError(f"{name} must be a non-empty tuple")
    if not all(type(value) is FastForecastMetricPopulation for value in values):
        raise ValueError(f"{name} must contain exact FastForecastMetricPopulation values")
    names = tuple(value.name for value in values)
    if names != tuple(sorted(names)):
        raise ValueError(f"{name} must be in lexical name order")
    if len(set(names)) != len(names):
        raise ValueError(f"{name} names must be unique")


def _fold_artifact_fingerprints(values: object) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError("fold_artifact_fingerprints must be a non-empty tuple")
    names: list[str] = []
    for value in values:
        if not isinstance(value, tuple) or len(value) != 2:
            raise ValueError("fold artifact fingerprint rows must be two-item tuples")
        name, digest = value
        _non_empty("fold artifact name", name)
        _sha256("fold artifact fingerprint", digest)
        names.append(name)
    if tuple(names) != tuple(sorted(names)) or len(set(names)) != len(names):
        raise ValueError("fold artifact fingerprints must use unique lexical fold names")


def _validate_decision_identity(identity: object) -> None:
    if not isinstance(identity, tuple) or len(identity) != 7:
        raise ValueError("decision_identity must use the exact FL8.1 seven-field tuple")
    signature, ordinal, sequence, mint, quote_mint, venue, observed = identity
    _non_empty("decision signature", signature)
    _non_negative_int("decision ordinal", ordinal)
    _non_negative_int("decision sequence", sequence)
    _non_empty("decision mint", mint)
    _non_empty("decision quote mint", quote_mint)
    _non_empty("decision venue", venue)
    _non_negative_int("decision observed timestamp", observed)


def _boundaries(name: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    previous: float | None = None
    for item in value:
        _non_negative_finite(name, item)
        current = float(item)
        if previous is not None and current <= previous:
            raise ValueError(f"{name} must be strictly increasing")
        previous = current


def _canonical_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("evaluation fingerprint cannot contain non-finite floats")
        return {"float_hex": value.hex()}
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical_value(getattr(value, field.name))
            for field in fields(value)
        }
    raise TypeError(f"unsupported forecast evaluation fingerprint value: {type(value).__name__}")


def _non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")


def _non_negative_finite(name: str, value: object) -> None:
    _finite(name, value)
    if float(value) < 0.0:
        raise ValueError(f"{name} must be non-negative")


def _optional_non_negative_finite(name: str, value: object) -> None:
    if value is not None:
        _non_negative_finite(name, value)


def _fraction(name: str, value: object) -> None:
    _finite(name, value)
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be within [0, 1]")


def _sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 digest")


def _close(name: str, actual: float, expected: float) -> None:
    if not math.isclose(
        actual,
        expected,
        rel_tol=_ARITH_REL_TOL,
        abs_tol=_ARITH_ABS_TOL,
    ):
        raise ValueError(f"{name} does not reconcile")
