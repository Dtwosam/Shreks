from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import math
import string

from .features import (
    FAST_FORECAST_FEATURE_NAMES,
    FAST_FORECAST_FEATURE_SCHEMA_VERSION,
    FastForecastFeatureTransform,
)


FAST_FORECAST_ARTIFACT_SCHEMA_NAME = "shreks.fast_lane_forecast_baseline"
FAST_FORECAST_ARTIFACT_SCHEMA_VERSION = 1


class FastForecastTargetKind(StrEnum):
    CONTINUOUS = "continuous"
    BINARY = "binary"


class FastForecastTarget(StrEnum):
    ENDPOINT_RETURN_BPS = "endpoint_return_bps"
    MFE_BPS = "mfe_bps"
    MAE_BPS = "mae_bps"
    BEST_COST_ADJUSTED_RETURN_BPS = "best_cost_adjusted_return_bps"
    ENDPOINT_COST_ADJUSTED_RETURN_BPS = "endpoint_cost_adjusted_return_bps"
    REVERSAL_OCCURRED = "reversal_occurred"
    ROUTE_UNAVAILABILITY_OBSERVED = "route_unavailability_observed"

    @property
    def kind(self) -> FastForecastTargetKind:
        if self in {
            FastForecastTarget.REVERSAL_OCCURRED,
            FastForecastTarget.ROUTE_UNAVAILABILITY_OBSERVED,
        }:
            return FastForecastTargetKind.BINARY
        return FastForecastTargetKind.CONTINUOUS


class FastForecastModelFamily(StrEnum):
    MEAN_REGRESSOR = "MEAN_REGRESSOR"
    RIDGE_REGRESSION = "RIDGE_REGRESSION"
    PRIOR_CLASSIFIER = "PRIOR_CLASSIFIER"
    LOGISTIC_REGRESSION = "LOGISTIC_REGRESSION"


@dataclass(frozen=True, slots=True)
class FastForecastTrainingPolicy:
    version: str
    ridge_alpha: float | None = None
    logistic_regularization_c: float | None = None
    logistic_max_iterations: int | None = None
    logistic_tolerance: float | None = None
    logistic_balanced_class_weight: bool | None = None

    def __post_init__(self) -> None:
        _non_empty("version", self.version)
        if self.ridge_alpha is not None:
            _positive_finite("ridge_alpha", self.ridge_alpha)
        if self.logistic_regularization_c is not None:
            _positive_finite(
                "logistic_regularization_c", self.logistic_regularization_c
            )
        if self.logistic_max_iterations is not None:
            _positive_int("logistic_max_iterations", self.logistic_max_iterations)
        if self.logistic_tolerance is not None:
            _positive_finite("logistic_tolerance", self.logistic_tolerance)
        if self.logistic_balanced_class_weight is not None and type(
            self.logistic_balanced_class_weight
        ) is not bool:
            raise ValueError("logistic_balanced_class_weight must be a boolean or None")


@dataclass(frozen=True, slots=True)
class FastForecastTrainingRequest:
    model_version: str
    model_family: FastForecastModelFamily
    target: FastForecastTarget
    horizon_ms: int
    training_policy: FastForecastTrainingPolicy

    def __post_init__(self) -> None:
        _non_empty("model_version", self.model_version)
        if type(self.model_family) is not FastForecastModelFamily:
            raise ValueError("model_family must be an exact FastForecastModelFamily")
        if type(self.target) is not FastForecastTarget:
            raise ValueError("target must be an exact FastForecastTarget")
        _positive_int("horizon_ms", self.horizon_ms)
        if type(self.training_policy) is not FastForecastTrainingPolicy:
            raise ValueError("training_policy must be an exact FastForecastTrainingPolicy")
        _validate_family_target(self.model_family, self.target)
        _validate_policy_for_family(self.model_family, self.training_policy)


@dataclass(frozen=True, slots=True)
class FastForecastBaselineArtifact:
    schema_name: str
    schema_version: int
    model_version: str
    model_family: FastForecastModelFamily
    target: FastForecastTarget
    target_kind: FastForecastTargetKind
    horizon_ms: int
    feature_schema_version: int
    training_policy_version: str
    training_bundle_fingerprint_sha256: str
    future_path_label_version: int
    training_row_count: int
    target_unavailable_row_count: int
    positive_row_count: int | None
    negative_row_count: int | None
    min_training_decision_observed_at_unix_ms: int
    max_training_decision_observed_at_unix_ms: int
    training_data_fingerprint_sha256: str
    feature_transforms: tuple[FastForecastFeatureTransform, ...]
    coefficients: tuple[float, ...]
    intercept: float | None
    constant_prediction: float | None
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FORECAST_ARTIFACT_SCHEMA_NAME:
            raise ValueError("forecast artifact schema name is incompatible")
        if self.schema_version != FAST_FORECAST_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("forecast artifact schema version is incompatible")
        _non_empty("model_version", self.model_version)
        if type(self.model_family) is not FastForecastModelFamily:
            raise ValueError("artifact model_family is incompatible")
        if type(self.target) is not FastForecastTarget:
            raise ValueError("artifact target is incompatible")
        if type(self.target_kind) is not FastForecastTargetKind:
            raise ValueError("artifact target_kind is incompatible")
        if self.target_kind is not self.target.kind:
            raise ValueError("artifact target_kind contradicts target")
        _validate_family_target(self.model_family, self.target)
        _positive_int("horizon_ms", self.horizon_ms)
        if self.feature_schema_version != FAST_FORECAST_FEATURE_SCHEMA_VERSION:
            raise ValueError("artifact feature schema version is incompatible")
        _non_empty("training_policy_version", self.training_policy_version)
        _sha256(
            "training_bundle_fingerprint_sha256",
            self.training_bundle_fingerprint_sha256,
        )
        _positive_int("future_path_label_version", self.future_path_label_version)
        _positive_int("training_row_count", self.training_row_count)
        _non_negative_int(
            "target_unavailable_row_count", self.target_unavailable_row_count
        )
        _non_negative_int(
            "min_training_decision_observed_at_unix_ms",
            self.min_training_decision_observed_at_unix_ms,
        )
        _non_negative_int(
            "max_training_decision_observed_at_unix_ms",
            self.max_training_decision_observed_at_unix_ms,
        )
        if (
            self.min_training_decision_observed_at_unix_ms
            > self.max_training_decision_observed_at_unix_ms
        ):
            raise ValueError("artifact training timestamp range is incompatible")
        _sha256(
            "training_data_fingerprint_sha256",
            self.training_data_fingerprint_sha256,
        )
        _sha256("artifact_fingerprint_sha256", self.artifact_fingerprint_sha256)

        if self.target_kind is FastForecastTargetKind.BINARY:
            if self.positive_row_count is None or self.negative_row_count is None:
                raise ValueError("binary artifact must record positive/negative row counts")
            _non_negative_int("positive_row_count", self.positive_row_count)
            _non_negative_int("negative_row_count", self.negative_row_count)
            if self.positive_row_count + self.negative_row_count != self.training_row_count:
                raise ValueError("binary class counts must reconcile to training_row_count")
        elif self.positive_row_count is not None or self.negative_row_count is not None:
            raise ValueError("continuous artifact cannot carry binary class counts")

        trained = self.model_family in {
            FastForecastModelFamily.RIDGE_REGRESSION,
            FastForecastModelFamily.LOGISTIC_REGRESSION,
        }
        if trained:
            if len(self.feature_transforms) != len(FAST_FORECAST_FEATURE_NAMES):
                raise ValueError("trained artifact must contain the sealed feature transforms")
            if tuple(value.feature_name for value in self.feature_transforms) != FAST_FORECAST_FEATURE_NAMES:
                raise ValueError("trained artifact feature transforms are out of order")
            if any(type(value) is not FastForecastFeatureTransform for value in self.feature_transforms):
                raise ValueError("trained artifact transforms must use exact transform values")
            if len(self.coefficients) != len(self.feature_transforms):
                raise ValueError("trained artifact coefficient count must match feature count")
            for coefficient in self.coefficients:
                _finite("coefficient", coefficient)
            if self.intercept is None:
                raise ValueError("trained artifact requires an intercept")
            _finite("intercept", self.intercept)
            if self.constant_prediction is not None:
                raise ValueError("trained artifact cannot contain a constant prediction")
        else:
            if self.feature_transforms or self.coefficients or self.intercept is not None:
                raise ValueError("naive artifact cannot contain fitted linear parameters")
            if self.constant_prediction is None:
                raise ValueError("naive artifact requires a constant prediction")
            _finite("constant_prediction", self.constant_prediction)

        if self.target_kind is FastForecastTargetKind.BINARY and self.constant_prediction is not None:
            if not 0.0 <= self.constant_prediction <= 1.0:
                raise ValueError("binary constant prediction must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class FastForecastPrediction:
    model_version: str
    target: FastForecastTarget
    horizon_ms: int
    decision_identity: tuple[object, ...]
    predicted_value: float

    def __post_init__(self) -> None:
        _non_empty("model_version", self.model_version)
        if type(self.target) is not FastForecastTarget:
            raise ValueError("prediction target is incompatible")
        _positive_int("horizon_ms", self.horizon_ms)
        if not isinstance(self.decision_identity, tuple) or not self.decision_identity:
            raise ValueError("prediction decision_identity must be a non-empty tuple")
        _finite("predicted_value", self.predicted_value)
        if self.target.kind is FastForecastTargetKind.BINARY and not (
            0.0 <= self.predicted_value <= 1.0
        ):
            raise ValueError("binary prediction must be within [0, 1]")


def fast_forecast_artifact_fingerprint_sha256(
    artifact: FastForecastBaselineArtifact,
) -> str:
    if type(artifact) is not FastForecastBaselineArtifact:
        raise ValueError("artifact must be an exact FastForecastBaselineArtifact")
    payload = _artifact_payload(artifact, include_fingerprint=False)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def artifact_to_mapping(
    artifact: FastForecastBaselineArtifact,
    *,
    include_fingerprint: bool = True,
) -> dict[str, object]:
    if type(artifact) is not FastForecastBaselineArtifact:
        raise ValueError("artifact must be an exact FastForecastBaselineArtifact")
    return _artifact_payload(artifact, include_fingerprint=include_fingerprint)


def _artifact_payload(
    artifact: FastForecastBaselineArtifact,
    *,
    include_fingerprint: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_name": artifact.schema_name,
        "schema_version": artifact.schema_version,
        "model_version": artifact.model_version,
        "model_family": artifact.model_family.value,
        "target": artifact.target.value,
        "target_kind": artifact.target_kind.value,
        "horizon_ms": artifact.horizon_ms,
        "feature_schema_version": artifact.feature_schema_version,
        "training_policy_version": artifact.training_policy_version,
        "training_bundle_fingerprint_sha256": artifact.training_bundle_fingerprint_sha256,
        "future_path_label_version": artifact.future_path_label_version,
        "training_row_count": artifact.training_row_count,
        "target_unavailable_row_count": artifact.target_unavailable_row_count,
        "positive_row_count": artifact.positive_row_count,
        "negative_row_count": artifact.negative_row_count,
        "min_training_decision_observed_at_unix_ms": artifact.min_training_decision_observed_at_unix_ms,
        "max_training_decision_observed_at_unix_ms": artifact.max_training_decision_observed_at_unix_ms,
        "training_data_fingerprint_sha256": artifact.training_data_fingerprint_sha256,
        "feature_transforms": [
            {
                "feature_name": value.feature_name,
                "imputation_median": value.imputation_median,
                "mean": value.mean,
                "scale": value.scale,
            }
            for value in artifact.feature_transforms
        ],
        "coefficients": list(artifact.coefficients),
        "intercept": artifact.intercept,
        "constant_prediction": artifact.constant_prediction,
    }
    if include_fingerprint:
        payload["artifact_fingerprint_sha256"] = artifact.artifact_fingerprint_sha256
    return payload


def _validate_family_target(
    family: FastForecastModelFamily,
    target: FastForecastTarget,
) -> None:
    continuous_family = family in {
        FastForecastModelFamily.MEAN_REGRESSOR,
        FastForecastModelFamily.RIDGE_REGRESSION,
    }
    if continuous_family != (target.kind is FastForecastTargetKind.CONTINUOUS):
        raise ValueError("model family is incompatible with forecast target kind")


def _validate_policy_for_family(
    family: FastForecastModelFamily,
    policy: FastForecastTrainingPolicy,
) -> None:
    logistic_values = (
        policy.logistic_regularization_c,
        policy.logistic_max_iterations,
        policy.logistic_tolerance,
        policy.logistic_balanced_class_weight,
    )
    if family in {
        FastForecastModelFamily.MEAN_REGRESSOR,
        FastForecastModelFamily.PRIOR_CLASSIFIER,
    }:
        if policy.ridge_alpha is not None or any(value is not None for value in logistic_values):
            raise ValueError("naive model family training policy cannot contain fit parameters")
        return
    if family is FastForecastModelFamily.RIDGE_REGRESSION:
        if policy.ridge_alpha is None or any(value is not None for value in logistic_values):
            raise ValueError("ridge model family requires only ridge_alpha in its training policy")
        return
    if policy.ridge_alpha is not None or any(value is None for value in logistic_values):
        raise ValueError("logistic model family requires the complete logistic training policy")


def _non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")


def _positive_finite(name: str, value: object) -> None:
    _finite(name, value)
    if float(value) <= 0.0:
        raise ValueError(f"{name} must be positive")


def _positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 hex digest")
