from __future__ import annotations

from dataclasses import dataclass
import string

from shreks_brain.learning import (
    ModelPrediction,
    ModelTrainingRequest,
    TrainedLogisticRegressionModel,
)


TIME_AWARE_VALIDATION_SCHEMA_VERSION = "e4-time-validation-v1"


@dataclass(frozen=True, slots=True)
class ChronologicalValidationFold:
    name: str
    training_started_at_unix_ms: int
    training_ended_at_unix_ms: int
    validation_started_at_unix_ms: int
    validation_ended_at_unix_ms: int

    def __post_init__(self) -> None:
        _require_non_empty_string("name", self.name)
        _require_non_negative_int(
            "training_started_at_unix_ms", self.training_started_at_unix_ms
        )
        _require_non_negative_int(
            "training_ended_at_unix_ms", self.training_ended_at_unix_ms
        )
        _require_non_negative_int(
            "validation_started_at_unix_ms", self.validation_started_at_unix_ms
        )
        _require_non_negative_int(
            "validation_ended_at_unix_ms", self.validation_ended_at_unix_ms
        )
        if self.training_started_at_unix_ms >= self.training_ended_at_unix_ms:
            raise ValueError("training interval must be non-empty")
        if self.training_ended_at_unix_ms > self.validation_started_at_unix_ms:
            raise ValueError("training interval must end no later than validation start")
        if self.validation_started_at_unix_ms >= self.validation_ended_at_unix_ms:
            raise ValueError("validation interval must be non-empty")


@dataclass(frozen=True, slots=True)
class TimeAwareValidationPolicy:
    version: str
    folds: tuple[ChronologicalValidationFold, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        if not isinstance(self.folds, tuple) or not self.folds:
            raise ValueError("folds must be a non-empty tuple")
        if not all(type(value) is ChronologicalValidationFold for value in self.folds):
            raise ValueError("folds must contain exact ChronologicalValidationFold values")
        names = tuple(value.name for value in self.folds)
        if len(set(names)) != len(names):
            raise ValueError("fold names must be unique")
        ordered = sorted(self.folds, key=_fold_sort_key)
        for previous, current in zip(ordered, ordered[1:]):
            if (
                current.validation_started_at_unix_ms
                < previous.validation_ended_at_unix_ms
            ):
                raise ValueError("validation intervals cannot overlap")


@dataclass(frozen=True, slots=True)
class ValidationFoldResult:
    fold: ChronologicalValidationFold
    training_window_row_count: int
    training_mature_target_row_count: int
    training_target_unavailable_at_split_count: int
    validation_row_count: int
    model: TrainedLogisticRegressionModel
    predictions: tuple[ModelPrediction, ...]

    def __post_init__(self) -> None:
        if type(self.fold) is not ChronologicalValidationFold:
            raise ValueError("fold must be an exact ChronologicalValidationFold")
        _require_non_negative_int(
            "training_window_row_count", self.training_window_row_count
        )
        _require_non_negative_int(
            "training_mature_target_row_count", self.training_mature_target_row_count
        )
        _require_non_negative_int(
            "training_target_unavailable_at_split_count",
            self.training_target_unavailable_at_split_count,
        )
        _require_non_negative_int("validation_row_count", self.validation_row_count)
        if type(self.model) is not TrainedLogisticRegressionModel:
            raise ValueError("model must be an exact TrainedLogisticRegressionModel")
        if not isinstance(self.predictions, tuple):
            raise ValueError("predictions must be a tuple")
        if not all(type(value) is ModelPrediction for value in self.predictions):
            raise ValueError("predictions must contain exact ModelPrediction values")
        if self.training_mature_target_row_count != self.model.training_row_count:
            raise ValueError(
                "training_mature_target_row_count must equal model.training_row_count"
            )
        if self.training_window_row_count != (
            self.training_mature_target_row_count
            + self.training_target_unavailable_at_split_count
        ):
            raise ValueError("training window row counts must reconcile")
        if self.validation_row_count != len(self.predictions):
            raise ValueError("validation_row_count must equal prediction count")
        if any(
            value.model_version != self.model.model_version
            for value in self.predictions
        ):
            raise ValueError("prediction model versions must equal artifact model version")
        if self.predictions != tuple(sorted(self.predictions, key=_prediction_sort_key)):
            raise ValueError("predictions must be in canonical order")
        for prediction in self.predictions:
            if not (
                self.fold.validation_started_at_unix_ms
                <= prediction.as_of_unix_ms
                < self.fold.validation_ended_at_unix_ms
            ):
                raise ValueError("prediction timestamp must lie inside validation interval")


@dataclass(frozen=True, slots=True)
class TimeAwareValidationRun:
    schema_version: str
    validation_policy_version: str
    model_training_request: ModelTrainingRequest
    fold_results: tuple[ValidationFoldResult, ...]
    validation_run_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != TIME_AWARE_VALIDATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {TIME_AWARE_VALIDATION_SCHEMA_VERSION}"
            )
        _require_non_empty_string(
            "validation_policy_version", self.validation_policy_version
        )
        if type(self.model_training_request) is not ModelTrainingRequest:
            raise ValueError("model_training_request must be an exact ModelTrainingRequest")
        if not isinstance(self.fold_results, tuple) or not self.fold_results:
            raise ValueError("fold_results must be a non-empty tuple")
        if not all(type(value) is ValidationFoldResult for value in self.fold_results):
            raise ValueError("fold_results must contain exact ValidationFoldResult values")
        names = tuple(value.fold.name for value in self.fold_results)
        if len(set(names)) != len(names):
            raise ValueError("fold result names must be unique")
        if self.fold_results != tuple(
            sorted(self.fold_results, key=lambda value: _fold_sort_key(value.fold))
        ):
            raise ValueError("fold_results must be in canonical order")
        _require_sha256(
            "validation_run_fingerprint_sha256",
            self.validation_run_fingerprint_sha256,
        )


def _fold_sort_key(
    fold: ChronologicalValidationFold,
) -> tuple[int, int, str]:
    return (
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.name,
    )


def _prediction_sort_key(prediction: ModelPrediction) -> tuple[int, str]:
    return (prediction.as_of_unix_ms, prediction.candidate_mint)


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


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
