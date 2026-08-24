from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
import string

from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
)


MODEL_TRAINING_SCHEMA_VERSION = "e3-training-v1"


class ModelFamily(StrEnum):
    LOGISTIC_REGRESSION = "LOGISTIC_REGRESSION"


class ClassWeightMode(StrEnum):
    NONE = "NONE"
    BALANCED = "BALANCED"


@dataclass(frozen=True, slots=True)
class ResearchReturnTarget:
    horizon_seconds: int
    minimum_return_pct: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.horizon_seconds, bool)
            or not isinstance(self.horizon_seconds, int)
            or self.horizon_seconds not in RESEARCH_OUTCOME_HORIZONS_SECONDS
        ):
            raise ValueError("horizon_seconds must be an approved D6 research horizon")
        _require_finite_number("minimum_return_pct", self.minimum_return_pct)


@dataclass(frozen=True, slots=True)
class LogisticRegressionTrainingPolicy:
    version: str
    regularization_c: float
    max_iterations: int
    tolerance: float
    class_weight_mode: ClassWeightMode

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_positive_finite("regularization_c", self.regularization_c)
        _require_positive_int("max_iterations", self.max_iterations)
        _require_positive_finite("tolerance", self.tolerance)
        if type(self.class_weight_mode) is not ClassWeightMode:
            raise ValueError("class_weight_mode must be a ClassWeightMode")


@dataclass(frozen=True, slots=True)
class ModelTrainingRequest:
    model_version: str
    model_family: ModelFamily
    feature_columns: tuple[str, ...]
    target: ResearchReturnTarget
    training_policy: LogisticRegressionTrainingPolicy

    def __post_init__(self) -> None:
        _require_non_empty_string("model_version", self.model_version)
        if type(self.model_family) is not ModelFamily:
            raise ValueError("model_family must be a ModelFamily")
        if not isinstance(self.feature_columns, tuple) or not self.feature_columns:
            raise ValueError("feature_columns must be a non-empty tuple")
        if not all(isinstance(value, str) and value.strip() for value in self.feature_columns):
            raise ValueError("feature_columns must contain non-empty strings")
        if len(set(self.feature_columns)) != len(self.feature_columns):
            raise ValueError("feature_columns cannot contain duplicate values")
        if type(self.target) is not ResearchReturnTarget:
            raise ValueError("target must be an exact ResearchReturnTarget")
        if type(self.training_policy) is not LogisticRegressionTrainingPolicy:
            raise ValueError(
                "training_policy must be an exact LogisticRegressionTrainingPolicy"
            )


@dataclass(frozen=True, slots=True)
class FeatureTransform:
    feature_name: str
    imputation_median: float
    mean: float
    scale: float

    def __post_init__(self) -> None:
        _require_non_empty_string("feature_name", self.feature_name)
        _require_finite_number("imputation_median", self.imputation_median)
        _require_finite_number("mean", self.mean)
        _require_positive_finite("scale", self.scale)


@dataclass(frozen=True, slots=True)
class TrainedLogisticRegressionModel:
    schema_version: str
    model_version: str
    model_family: ModelFamily
    training_policy_version: str
    research_dataset_schema_version: str
    target: ResearchReturnTarget
    feature_transforms: tuple[FeatureTransform, ...]
    coefficients: tuple[float, ...]
    intercept: float
    training_row_count: int
    positive_row_count: int
    negative_row_count: int
    target_unavailable_row_count: int
    min_training_as_of_unix_ms: int
    max_training_as_of_unix_ms: int
    training_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != MODEL_TRAINING_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {MODEL_TRAINING_SCHEMA_VERSION}"
            )
        _require_non_empty_string("model_version", self.model_version)
        if self.model_family is not ModelFamily.LOGISTIC_REGRESSION:
            raise ValueError("model_family must be LOGISTIC_REGRESSION")
        _require_non_empty_string("training_policy_version", self.training_policy_version)
        if self.research_dataset_schema_version != RESEARCH_DATASET_SCHEMA_VERSION:
            raise ValueError(
                "research_dataset_schema_version must equal sealed D6 schema"
            )
        if type(self.target) is not ResearchReturnTarget:
            raise ValueError("target must be an exact ResearchReturnTarget")

        if not isinstance(self.feature_transforms, tuple) or not self.feature_transforms:
            raise ValueError("feature_transforms must be a non-empty tuple")
        if not all(type(value) is FeatureTransform for value in self.feature_transforms):
            raise ValueError("feature_transforms must contain exact FeatureTransform values")
        transform_names = tuple(value.feature_name for value in self.feature_transforms)
        if len(set(transform_names)) != len(transform_names):
            raise ValueError("feature_transforms must use unique feature names")

        if not isinstance(self.coefficients, tuple) or not self.coefficients:
            raise ValueError("coefficients must be a non-empty tuple")
        if len(self.coefficients) != len(self.feature_transforms):
            raise ValueError("coefficient count must equal feature transform count")
        for value in self.coefficients:
            _require_finite_number("coefficient", value)
        _require_finite_number("intercept", self.intercept)

        _require_positive_int("training_row_count", self.training_row_count)
        _require_positive_int("positive_row_count", self.positive_row_count)
        _require_positive_int("negative_row_count", self.negative_row_count)
        if self.training_row_count < 2:
            raise ValueError("training_row_count must be at least 2")
        if self.positive_row_count + self.negative_row_count != self.training_row_count:
            raise ValueError("positive and negative row counts must reconcile to training_row_count")
        _require_non_negative_int(
            "target_unavailable_row_count", self.target_unavailable_row_count
        )
        _require_non_negative_int(
            "min_training_as_of_unix_ms", self.min_training_as_of_unix_ms
        )
        _require_non_negative_int(
            "max_training_as_of_unix_ms", self.max_training_as_of_unix_ms
        )
        if self.min_training_as_of_unix_ms > self.max_training_as_of_unix_ms:
            raise ValueError("min_training_as_of_unix_ms must be <= max_training_as_of_unix_ms")
        _require_sha256("training_fingerprint_sha256", self.training_fingerprint_sha256)


@dataclass(frozen=True, slots=True)
class ModelPrediction:
    model_version: str
    candidate_mint: str
    as_of_unix_ms: int
    positive_probability: float

    def __post_init__(self) -> None:
        _require_non_empty_string("model_version", self.model_version)
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_finite_number("positive_probability", self.positive_probability)
        if self.positive_probability < 0.0 or self.positive_probability > 1.0:
            raise ValueError("positive_probability must be within [0, 1]")


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_finite_number(name: str, value: float | int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_positive_finite(name: str, value: float | int) -> None:
    _require_finite_number(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_sha256(name: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(char not in string.hexdigits.lower() for char in value)
    ):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 hex digest")
