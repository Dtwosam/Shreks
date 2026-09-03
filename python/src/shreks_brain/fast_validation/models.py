from __future__ import annotations

from dataclasses import dataclass
import string

from shreks_brain.fast_learning.models import (
    FastForecastBaselineArtifact,
    FastForecastPrediction,
    FastForecastTrainingRequest,
)


FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME = "shreks.fast_lane_chronological_validation"
FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class FastChronologicalFold:
    name: str
    training_started_at_unix_ms: int
    training_ended_at_unix_ms: int
    validation_started_at_unix_ms: int
    validation_ended_at_unix_ms: int
    test_started_at_unix_ms: int
    test_ended_at_unix_ms: int

    def __post_init__(self) -> None:
        _non_empty("name", self.name)
        for name in (
            "training_started_at_unix_ms",
            "training_ended_at_unix_ms",
            "validation_started_at_unix_ms",
            "validation_ended_at_unix_ms",
            "test_started_at_unix_ms",
            "test_ended_at_unix_ms",
        ):
            _non_negative_int(name, getattr(self, name))
        if self.training_started_at_unix_ms >= self.training_ended_at_unix_ms:
            raise ValueError("training interval must be non-empty")
        if self.training_ended_at_unix_ms > self.validation_started_at_unix_ms:
            raise ValueError("training/validation order is incompatible")
        if self.validation_started_at_unix_ms >= self.validation_ended_at_unix_ms:
            raise ValueError("validation interval must be non-empty")
        if self.validation_ended_at_unix_ms > self.test_started_at_unix_ms:
            raise ValueError("validation/test order is incompatible")
        if self.test_started_at_unix_ms >= self.test_ended_at_unix_ms:
            raise ValueError("test interval must be non-empty")


@dataclass(frozen=True, slots=True)
class FastChronologicalValidationPolicy:
    version: str
    folds: tuple[FastChronologicalFold, ...]

    def __post_init__(self) -> None:
        _non_empty("version", self.version)
        if not isinstance(self.folds, tuple) or not self.folds:
            raise ValueError("folds must be a non-empty tuple")
        if not all(type(value) is FastChronologicalFold for value in self.folds):
            raise ValueError("folds must contain exact FastChronologicalFold values")
        names = tuple(value.name for value in self.folds)
        if len(set(names)) != len(names):
            raise ValueError("fold names must be unique")

        intervals: list[tuple[int, int, str]] = []
        for fold in self.folds:
            intervals.append(
                (
                    fold.validation_started_at_unix_ms,
                    fold.validation_ended_at_unix_ms,
                    f"{fold.name}:validation",
                )
            )
            intervals.append(
                (
                    fold.test_started_at_unix_ms,
                    fold.test_ended_at_unix_ms,
                    f"{fold.name}:test",
                )
            )
        intervals.sort()
        for previous, current in zip(intervals, intervals[1:]):
            if current[0] < previous[1]:
                raise ValueError("evaluation intervals cannot overlap")


@dataclass(frozen=True, slots=True)
class FastLeakageQuarantineSummary:
    shared_mint_count: int
    shared_actor_count: int
    shared_signature_count: int
    training_quarantined_row_count: int
    validation_quarantined_row_count: int
    test_quarantined_row_count: int
    quarantine_fingerprint_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "shared_mint_count",
            "shared_actor_count",
            "shared_signature_count",
            "training_quarantined_row_count",
            "validation_quarantined_row_count",
            "test_quarantined_row_count",
        ):
            _non_negative_int(name, getattr(self, name))
        _sha256("quarantine_fingerprint_sha256", self.quarantine_fingerprint_sha256)


@dataclass(frozen=True, slots=True)
class FastChronologicalFoldResult:
    fold: FastChronologicalFold
    training_raw_row_count: int
    training_row_count: int
    training_target_unavailable_at_split_count: int
    validation_raw_row_count: int
    validation_row_count: int
    test_raw_row_count: int
    test_row_count: int
    quarantine: FastLeakageQuarantineSummary
    model: FastForecastBaselineArtifact
    validation_predictions: tuple[FastForecastPrediction, ...]
    test_predictions: tuple[FastForecastPrediction, ...]

    def __post_init__(self) -> None:
        if type(self.fold) is not FastChronologicalFold:
            raise ValueError("fold must be an exact FastChronologicalFold")
        for name in (
            "training_raw_row_count",
            "training_row_count",
            "training_target_unavailable_at_split_count",
            "validation_raw_row_count",
            "validation_row_count",
            "test_raw_row_count",
            "test_row_count",
        ):
            _non_negative_int(name, getattr(self, name))
        if type(self.quarantine) is not FastLeakageQuarantineSummary:
            raise ValueError("quarantine must be an exact FastLeakageQuarantineSummary")
        if type(self.model) is not FastForecastBaselineArtifact:
            raise ValueError("model must be an exact FastForecastBaselineArtifact")
        if not isinstance(self.validation_predictions, tuple) or not all(
            type(value) is FastForecastPrediction for value in self.validation_predictions
        ):
            raise ValueError("validation_predictions must contain exact FastForecastPrediction values")
        if not isinstance(self.test_predictions, tuple) or not all(
            type(value) is FastForecastPrediction for value in self.test_predictions
        ):
            raise ValueError("test_predictions must contain exact FastForecastPrediction values")

        if self.training_row_count > self.training_raw_row_count:
            raise ValueError("training post-quarantine row count exceeds raw count")
        if self.validation_row_count > self.validation_raw_row_count:
            raise ValueError("validation post-quarantine row count exceeds raw count")
        if self.test_row_count > self.test_raw_row_count:
            raise ValueError("test post-quarantine row count exceeds raw count")
        if self.training_raw_row_count - self.training_row_count != self.quarantine.training_quarantined_row_count:
            raise ValueError("training quarantine counts do not reconcile")
        if self.validation_raw_row_count - self.validation_row_count != self.quarantine.validation_quarantined_row_count:
            raise ValueError("validation quarantine counts do not reconcile")
        if self.test_raw_row_count - self.test_row_count != self.quarantine.test_quarantined_row_count:
            raise ValueError("test quarantine counts do not reconcile")
        if self.model.training_row_count + self.training_target_unavailable_at_split_count != self.training_row_count:
            raise ValueError("training target availability counts do not reconcile")
        if len(self.validation_predictions) != self.validation_row_count:
            raise ValueError("validation prediction count does not reconcile")
        if len(self.test_predictions) != self.test_row_count:
            raise ValueError("test prediction count does not reconcile")

        _validate_predictions(
            self.validation_predictions,
            self.model,
            start=self.fold.validation_started_at_unix_ms,
            end=self.fold.validation_ended_at_unix_ms,
            role="validation",
        )
        _validate_predictions(
            self.test_predictions,
            self.model,
            start=self.fold.test_started_at_unix_ms,
            end=self.fold.test_ended_at_unix_ms,
            role="test",
        )


@dataclass(frozen=True, slots=True)
class FastChronologicalValidationRun:
    schema_name: str
    schema_version: int
    validation_policy_version: str
    training_request: FastForecastTrainingRequest
    training_bundle_fingerprint_sha256: str
    fold_results: tuple[FastChronologicalFoldResult, ...]
    validation_run_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME:
            raise ValueError("chronological validation schema name is incompatible")
        if self.schema_version != FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION:
            raise ValueError("chronological validation schema version is incompatible")
        _non_empty("validation_policy_version", self.validation_policy_version)
        if type(self.training_request) is not FastForecastTrainingRequest:
            raise ValueError("training_request must be an exact FastForecastTrainingRequest")
        _sha256(
            "training_bundle_fingerprint_sha256",
            self.training_bundle_fingerprint_sha256,
        )
        if not isinstance(self.fold_results, tuple) or not self.fold_results:
            raise ValueError("fold_results must be a non-empty tuple")
        if not all(type(value) is FastChronologicalFoldResult for value in self.fold_results):
            raise ValueError("fold_results must contain exact FastChronologicalFoldResult values")
        if self.fold_results != tuple(sorted(self.fold_results, key=lambda value: _fold_sort_key(value.fold))):
            raise ValueError("fold_results must be in canonical order")
        names = tuple(value.fold.name for value in self.fold_results)
        if len(set(names)) != len(names):
            raise ValueError("fold result names must be unique")
        _sha256(
            "validation_run_fingerprint_sha256",
            self.validation_run_fingerprint_sha256,
        )


def _validate_predictions(
    predictions: tuple[FastForecastPrediction, ...],
    model: FastForecastBaselineArtifact,
    *,
    start: int,
    end: int,
    role: str,
) -> None:
    if predictions != tuple(sorted(predictions, key=_prediction_sort_key)):
        raise ValueError(f"{role} predictions must be in canonical order")
    identities = tuple(value.decision_identity for value in predictions)
    if len(set(identities)) != len(identities):
        raise ValueError(f"{role} prediction identities must be unique")
    for prediction in predictions:
        if prediction.model_version != model.model_version:
            raise ValueError(f"{role} prediction model version is incompatible")
        if prediction.target is not model.target or prediction.horizon_ms != model.horizon_ms:
            raise ValueError(f"{role} prediction target/horizon is incompatible")
        observed = _prediction_observed_at(prediction)
        if not start <= observed < end:
            raise ValueError(f"{role} prediction timestamp lies outside its fold interval")


def _prediction_observed_at(prediction: FastForecastPrediction) -> int:
    identity = prediction.decision_identity
    if len(identity) != 7:
        raise ValueError("prediction decision identity must use the FL8.1 seven-field shape")
    observed = identity[6]
    _non_negative_int("prediction decision observed_at_unix_ms", observed)
    return observed


def _prediction_sort_key(prediction: FastForecastPrediction) -> tuple[object, ...]:
    identity = prediction.decision_identity
    observed = _prediction_observed_at(prediction)
    return (observed, identity[2], identity[0], identity[1])


def _fold_sort_key(fold: FastChronologicalFold) -> tuple[int, int, int, int, str]:
    return (
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.test_started_at_unix_ms,
        fold.test_ended_at_unix_ms,
        fold.name,
    )


def _non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


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
