from __future__ import annotations

import json
from pathlib import Path

from shreks_brain.fast_learning.models import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTargetKind,
)

from .models import (
    FAST_FORECAST_EVALUATION_SCHEMA_NAME,
    FAST_FORECAST_EVALUATION_SCHEMA_VERSION,
    FastBinaryForecastMetrics,
    FastCalibrationBucket,
    FastContinuousForecastMetrics,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
    FastForecastEvaluationReport,
    FastForecastMetricPopulation,
    fast_forecast_evaluation_report_fingerprint_sha256,
)


_REPORT_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "evaluation_policy",
        "validation_policy_version",
        "validation_run_fingerprint_sha256",
        "training_bundle_fingerprint_sha256",
        "model_version",
        "model_family",
        "target",
        "target_kind",
        "horizon_ms",
        "target_is_cost_adjusted",
        "fold_artifact_fingerprints",
        "context_fingerprint_sha256",
        "overall",
        "fold_populations",
        "regime_populations",
        "strategy_family_populations",
        "liquidity_bucket_populations",
        "cost_bucket_populations",
        "evaluation_report_fingerprint_sha256",
    }
)
_POLICY_KEYS = frozenset(
    {
        "version",
        "partition",
        "probability_bucket_count",
        "liquidity_capacity_quote_boundaries",
        "round_trip_cost_bps_boundaries",
        "binary_log_loss_clip_epsilon",
    }
)
_POPULATION_KEYS = frozenset(
    {
        "name",
        "prediction_count",
        "scored_observation_count",
        "target_unavailable_count",
        "continuous_metrics",
        "binary_metrics",
    }
)
_CONTINUOUS_KEYS = frozenset(
    {
        "observation_count",
        "mean_predicted_value",
        "mean_actual_value",
        "mean_error",
        "mean_absolute_error",
        "root_mean_squared_error",
    }
)
_BINARY_KEYS = frozenset(
    {
        "observation_count",
        "positive_count",
        "mean_predicted_probability",
        "brier_score",
        "log_loss",
        "expected_calibration_error",
        "calibration_buckets",
    }
)
_BUCKET_KEYS = frozenset(
    {
        "bucket_index",
        "lower_probability",
        "upper_probability",
        "observation_count",
        "mean_predicted_probability",
        "observed_positive_rate",
        "absolute_calibration_gap",
    }
)
_FOLD_FINGERPRINT_KEYS = frozenset({"fold_name", "artifact_fingerprint_sha256"})


def write_fast_forecast_evaluation_report(
    report: FastForecastEvaluationReport,
    path: str | Path,
) -> None:
    if type(report) is not FastForecastEvaluationReport:
        raise ValueError("report must be an exact FastForecastEvaluationReport")
    expected = fast_forecast_evaluation_report_fingerprint_sha256(report)
    if expected != report.evaluation_report_fingerprint_sha256:
        raise ValueError("forecast evaluation report fingerprint is inconsistent before write")
    destination = Path(path)
    if destination.exists():
        raise FileExistsError("forecast evaluation report path already exists")
    payload = _report_payload(report)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    destination.write_text(encoded, encoding="utf-8")


def read_fast_forecast_evaluation_report(
    path: str | Path,
) -> FastForecastEvaluationReport:
    source = Path(path)
    if not source.is_file():
        raise ValueError("forecast evaluation report source must be an existing file")
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("forecast evaluation report JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("forecast evaluation report root must be an object")
    report = _report_from_payload(payload)
    expected = fast_forecast_evaluation_report_fingerprint_sha256(report)
    if expected != report.evaluation_report_fingerprint_sha256:
        raise ValueError("forecast evaluation report fingerprint is invalid or tampered")
    return report


def _report_payload(report: FastForecastEvaluationReport) -> dict[str, object]:
    return {
        "schema_name": report.schema_name,
        "schema_version": report.schema_version,
        "evaluation_policy": _policy_payload(report.evaluation_policy),
        "validation_policy_version": report.validation_policy_version,
        "validation_run_fingerprint_sha256": report.validation_run_fingerprint_sha256,
        "training_bundle_fingerprint_sha256": report.training_bundle_fingerprint_sha256,
        "model_version": report.model_version,
        "model_family": report.model_family.value,
        "target": report.target.value,
        "target_kind": report.target_kind.value,
        "horizon_ms": report.horizon_ms,
        "target_is_cost_adjusted": report.target_is_cost_adjusted,
        "fold_artifact_fingerprints": [
            {
                "fold_name": fold_name,
                "artifact_fingerprint_sha256": fingerprint,
            }
            for fold_name, fingerprint in report.fold_artifact_fingerprints
        ],
        "context_fingerprint_sha256": report.context_fingerprint_sha256,
        "overall": _population_payload(report.overall),
        "fold_populations": [_population_payload(value) for value in report.fold_populations],
        "regime_populations": [_population_payload(value) for value in report.regime_populations],
        "strategy_family_populations": [
            _population_payload(value) for value in report.strategy_family_populations
        ],
        "liquidity_bucket_populations": [
            _population_payload(value) for value in report.liquidity_bucket_populations
        ],
        "cost_bucket_populations": [
            _population_payload(value) for value in report.cost_bucket_populations
        ],
        "evaluation_report_fingerprint_sha256": report.evaluation_report_fingerprint_sha256,
    }


def _policy_payload(policy: FastForecastEvaluationPolicy) -> dict[str, object]:
    return {
        "version": policy.version,
        "partition": policy.partition.value,
        "probability_bucket_count": policy.probability_bucket_count,
        "liquidity_capacity_quote_boundaries": list(
            policy.liquidity_capacity_quote_boundaries
        ),
        "round_trip_cost_bps_boundaries": list(policy.round_trip_cost_bps_boundaries),
        "binary_log_loss_clip_epsilon": policy.binary_log_loss_clip_epsilon,
    }


def _population_payload(population: FastForecastMetricPopulation) -> dict[str, object]:
    return {
        "name": population.name,
        "prediction_count": population.prediction_count,
        "scored_observation_count": population.scored_observation_count,
        "target_unavailable_count": population.target_unavailable_count,
        "continuous_metrics": (
            None
            if population.continuous_metrics is None
            else {
                "observation_count": population.continuous_metrics.observation_count,
                "mean_predicted_value": population.continuous_metrics.mean_predicted_value,
                "mean_actual_value": population.continuous_metrics.mean_actual_value,
                "mean_error": population.continuous_metrics.mean_error,
                "mean_absolute_error": population.continuous_metrics.mean_absolute_error,
                "root_mean_squared_error": population.continuous_metrics.root_mean_squared_error,
            }
        ),
        "binary_metrics": (
            None
            if population.binary_metrics is None
            else {
                "observation_count": population.binary_metrics.observation_count,
                "positive_count": population.binary_metrics.positive_count,
                "mean_predicted_probability": population.binary_metrics.mean_predicted_probability,
                "brier_score": population.binary_metrics.brier_score,
                "log_loss": population.binary_metrics.log_loss,
                "expected_calibration_error": population.binary_metrics.expected_calibration_error,
                "calibration_buckets": [
                    {
                        "bucket_index": bucket.bucket_index,
                        "lower_probability": bucket.lower_probability,
                        "upper_probability": bucket.upper_probability,
                        "observation_count": bucket.observation_count,
                        "mean_predicted_probability": bucket.mean_predicted_probability,
                        "observed_positive_rate": bucket.observed_positive_rate,
                        "absolute_calibration_gap": bucket.absolute_calibration_gap,
                    }
                    for bucket in population.binary_metrics.calibration_buckets
                ],
            }
        ),
    }


def _report_from_payload(payload: dict[str, object]) -> FastForecastEvaluationReport:
    _exact_keys("forecast evaluation report", payload, _REPORT_KEYS)
    if payload["schema_name"] != FAST_FORECAST_EVALUATION_SCHEMA_NAME:
        raise ValueError("forecast evaluation report schema name is incompatible")
    if payload["schema_version"] != FAST_FORECAST_EVALUATION_SCHEMA_VERSION:
        raise ValueError("forecast evaluation report schema version is incompatible")
    policy_payload = _object("evaluation_policy", payload["evaluation_policy"])
    _exact_keys("evaluation_policy", policy_payload, _POLICY_KEYS)
    policy = FastForecastEvaluationPolicy(
        version=_string("evaluation policy version", policy_payload["version"]),
        partition=_enum(
            FastForecastEvaluationPartition,
            "evaluation partition",
            policy_payload["partition"],
        ),
        probability_bucket_count=_int(
            "probability_bucket_count", policy_payload["probability_bucket_count"]
        ),
        liquidity_capacity_quote_boundaries=_float_tuple(
            "liquidity_capacity_quote_boundaries",
            policy_payload["liquidity_capacity_quote_boundaries"],
        ),
        round_trip_cost_bps_boundaries=_float_tuple(
            "round_trip_cost_bps_boundaries",
            policy_payload["round_trip_cost_bps_boundaries"],
        ),
        binary_log_loss_clip_epsilon=_float(
            "binary_log_loss_clip_epsilon",
            policy_payload["binary_log_loss_clip_epsilon"],
        ),
    )
    folds_raw = _list("fold_artifact_fingerprints", payload["fold_artifact_fingerprints"])
    folds: list[tuple[str, str]] = []
    for raw in folds_raw:
        row = _object("fold artifact fingerprint", raw)
        _exact_keys("fold artifact fingerprint", row, _FOLD_FINGERPRINT_KEYS)
        folds.append(
            (
                _string("fold_name", row["fold_name"]),
                _string("artifact_fingerprint_sha256", row["artifact_fingerprint_sha256"]),
            )
        )
    return FastForecastEvaluationReport(
        schema_name=_string("schema_name", payload["schema_name"]),
        schema_version=_int("schema_version", payload["schema_version"]),
        evaluation_policy=policy,
        validation_policy_version=_string(
            "validation_policy_version", payload["validation_policy_version"]
        ),
        validation_run_fingerprint_sha256=_string(
            "validation_run_fingerprint_sha256",
            payload["validation_run_fingerprint_sha256"],
        ),
        training_bundle_fingerprint_sha256=_string(
            "training_bundle_fingerprint_sha256",
            payload["training_bundle_fingerprint_sha256"],
        ),
        model_version=_string("model_version", payload["model_version"]),
        model_family=_enum(FastForecastModelFamily, "model_family", payload["model_family"]),
        target=_enum(FastForecastTarget, "target", payload["target"]),
        target_kind=_enum(FastForecastTargetKind, "target_kind", payload["target_kind"]),
        horizon_ms=_int("horizon_ms", payload["horizon_ms"]),
        target_is_cost_adjusted=_bool(
            "target_is_cost_adjusted", payload["target_is_cost_adjusted"]
        ),
        fold_artifact_fingerprints=tuple(folds),
        context_fingerprint_sha256=_string(
            "context_fingerprint_sha256", payload["context_fingerprint_sha256"]
        ),
        overall=_population_from_payload(payload["overall"]),
        fold_populations=_population_tuple_from_payload(
            "fold_populations", payload["fold_populations"]
        ),
        regime_populations=_population_tuple_from_payload(
            "regime_populations", payload["regime_populations"]
        ),
        strategy_family_populations=_population_tuple_from_payload(
            "strategy_family_populations", payload["strategy_family_populations"]
        ),
        liquidity_bucket_populations=_population_tuple_from_payload(
            "liquidity_bucket_populations", payload["liquidity_bucket_populations"]
        ),
        cost_bucket_populations=_population_tuple_from_payload(
            "cost_bucket_populations", payload["cost_bucket_populations"]
        ),
        evaluation_report_fingerprint_sha256=_string(
            "evaluation_report_fingerprint_sha256",
            payload["evaluation_report_fingerprint_sha256"],
        ),
    )


def _population_tuple_from_payload(name: str, value: object) -> tuple[FastForecastMetricPopulation, ...]:
    return tuple(_population_from_payload(item) for item in _list(name, value))


def _population_from_payload(value: object) -> FastForecastMetricPopulation:
    payload = _object("metric population", value)
    _exact_keys("metric population", payload, _POPULATION_KEYS)
    continuous_raw = payload["continuous_metrics"]
    binary_raw = payload["binary_metrics"]
    continuous = None
    if continuous_raw is not None:
        row = _object("continuous_metrics", continuous_raw)
        _exact_keys("continuous_metrics", row, _CONTINUOUS_KEYS)
        continuous = FastContinuousForecastMetrics(
            observation_count=_int("observation_count", row["observation_count"]),
            mean_predicted_value=_float("mean_predicted_value", row["mean_predicted_value"]),
            mean_actual_value=_float("mean_actual_value", row["mean_actual_value"]),
            mean_error=_float("mean_error", row["mean_error"]),
            mean_absolute_error=_float("mean_absolute_error", row["mean_absolute_error"]),
            root_mean_squared_error=_float(
                "root_mean_squared_error", row["root_mean_squared_error"]
            ),
        )
    binary = None
    if binary_raw is not None:
        row = _object("binary_metrics", binary_raw)
        _exact_keys("binary_metrics", row, _BINARY_KEYS)
        buckets: list[FastCalibrationBucket] = []
        for raw_bucket in _list("calibration_buckets", row["calibration_buckets"]):
            bucket = _object("calibration bucket", raw_bucket)
            _exact_keys("calibration bucket", bucket, _BUCKET_KEYS)
            buckets.append(
                FastCalibrationBucket(
                    bucket_index=_int("bucket_index", bucket["bucket_index"]),
                    lower_probability=_float(
                        "lower_probability", bucket["lower_probability"]
                    ),
                    upper_probability=_float(
                        "upper_probability", bucket["upper_probability"]
                    ),
                    observation_count=_int(
                        "observation_count", bucket["observation_count"]
                    ),
                    mean_predicted_probability=_optional_float(
                        "mean_predicted_probability",
                        bucket["mean_predicted_probability"],
                    ),
                    observed_positive_rate=_optional_float(
                        "observed_positive_rate", bucket["observed_positive_rate"]
                    ),
                    absolute_calibration_gap=_optional_float(
                        "absolute_calibration_gap", bucket["absolute_calibration_gap"]
                    ),
                )
            )
        binary = FastBinaryForecastMetrics(
            observation_count=_int("observation_count", row["observation_count"]),
            positive_count=_int("positive_count", row["positive_count"]),
            mean_predicted_probability=_float(
                "mean_predicted_probability", row["mean_predicted_probability"]
            ),
            brier_score=_float("brier_score", row["brier_score"]),
            log_loss=_float("log_loss", row["log_loss"]),
            expected_calibration_error=_float(
                "expected_calibration_error", row["expected_calibration_error"]
            ),
            calibration_buckets=tuple(buckets),
        )
    return FastForecastMetricPopulation(
        name=_string("name", payload["name"]),
        prediction_count=_int("prediction_count", payload["prediction_count"]),
        scored_observation_count=_int(
            "scored_observation_count", payload["scored_observation_count"]
        ),
        target_unavailable_count=_int(
            "target_unavailable_count", payload["target_unavailable_count"]
        ),
        continuous_metrics=continuous,
        binary_metrics=binary,
    )


def _exact_keys(name: str, payload: dict[str, object], expected: frozenset[str]) -> None:
    actual = frozenset(payload)
    if actual != expected:
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        raise ValueError(f"{name} has incompatible keys; unknown={unknown}, missing={missing}")


def _object(name: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _list(name: str, value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _string(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _optional_float(name: str, value: object) -> float | None:
    return None if value is None else _float(name, value)


def _float_tuple(name: str, value: object) -> tuple[float, ...]:
    return tuple(_float(name, item) for item in _list(name, value))


def _bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool")
    return value


def _enum(enum_type, name: str, value: object):
    raw = _string(name, value)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise ValueError(f"{name} is incompatible") from exc


def _reject_json_constant(value: str):
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
