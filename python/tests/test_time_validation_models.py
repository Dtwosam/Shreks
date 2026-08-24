from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shreks_brain.learning import (
    MODEL_TRAINING_SCHEMA_VERSION,
    ClassWeightMode,
    FeatureTransform,
    LogisticRegressionTrainingPolicy,
    ModelFamily,
    ModelPrediction,
    ModelTrainingRequest,
    ResearchReturnTarget,
    TrainedLogisticRegressionModel,
)
from shreks_brain.research import RESEARCH_DATASET_SCHEMA_VERSION
from shreks_brain.validation import (
    TIME_AWARE_VALIDATION_SCHEMA_VERSION,
    ChronologicalValidationFold,
    TimeAwareValidationPolicy,
    TimeAwareValidationRun,
    ValidationFoldResult,
)


def _request() -> ModelTrainingRequest:
    return ModelTrainingRequest(
        model_version="model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_columns=("market_liquidity_usd",),
        target=ResearchReturnTarget(horizon_seconds=300, minimum_return_pct=5.0),
        training_policy=LogisticRegressionTrainingPolicy(
            version="policy-v1",
            regularization_c=1.0,
            max_iterations=500,
            tolerance=1e-6,
            class_weight_mode=ClassWeightMode.NONE,
        ),
    )


def _model() -> TrainedLogisticRegressionModel:
    return TrainedLogisticRegressionModel(
        schema_version=MODEL_TRAINING_SCHEMA_VERSION,
        model_version="model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        training_policy_version="policy-v1",
        research_dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        target=ResearchReturnTarget(horizon_seconds=300, minimum_return_pct=5.0),
        feature_transforms=(
            FeatureTransform(
                feature_name="market_liquidity_usd",
                imputation_median=100.0,
                mean=100.0,
                scale=1.0,
            ),
        ),
        coefficients=(0.5,),
        intercept=0.0,
        training_row_count=2,
        positive_row_count=1,
        negative_row_count=1,
        target_unavailable_row_count=0,
        min_training_as_of_unix_ms=1_000,
        max_training_as_of_unix_ms=1_500,
        training_fingerprint_sha256="a" * 64,
    )


def _fold(
    *,
    name: str = "fold-1",
    training_start: int = 1_000,
    training_end: int = 2_000,
    validation_start: int = 2_000,
    validation_end: int = 3_000,
) -> ChronologicalValidationFold:
    return ChronologicalValidationFold(
        name=name,
        training_started_at_unix_ms=training_start,
        training_ended_at_unix_ms=training_end,
        validation_started_at_unix_ms=validation_start,
        validation_ended_at_unix_ms=validation_end,
    )


def _predictions() -> tuple[ModelPrediction, ...]:
    return (
        ModelPrediction(
            model_version="model-v1",
            candidate_mint="mint-a",
            as_of_unix_ms=2_100,
            positive_probability=0.25,
        ),
        ModelPrediction(
            model_version="model-v1",
            candidate_mint="mint-b",
            as_of_unix_ms=2_200,
            positive_probability=0.75,
        ),
    )


def _result(
    *,
    fold: ChronologicalValidationFold | None = None,
    training_window_row_count: int = 3,
    training_mature_target_row_count: int = 2,
    training_target_unavailable_at_split_count: int = 1,
    validation_row_count: int = 2,
    predictions: tuple[ModelPrediction, ...] | None = None,
) -> ValidationFoldResult:
    return ValidationFoldResult(
        fold=_fold() if fold is None else fold,
        training_window_row_count=training_window_row_count,
        training_mature_target_row_count=training_mature_target_row_count,
        training_target_unavailable_at_split_count=(
            training_target_unavailable_at_split_count
        ),
        validation_row_count=validation_row_count,
        model=_model(),
        predictions=_predictions() if predictions is None else predictions,
    )


def test_schema_and_contract_models_are_frozen_and_slotted() -> None:
    assert TIME_AWARE_VALIDATION_SCHEMA_VERSION == "e4-time-validation-v1"
    fold = _fold()
    assert not hasattr(fold, "__dict__")
    with pytest.raises(FrozenInstanceError):
        fold.name = "changed"  # type: ignore[misc]


def test_fold_accepts_adjacent_training_validation_boundary() -> None:
    fold = _fold()
    assert fold.training_ended_at_unix_ms == fold.validation_started_at_unix_ms


@pytest.mark.parametrize(
    "kwargs",
    (
        {"name": ""},
        {"training_start": -1},
        {"training_start": True},
        {"training_start": 2_000, "training_end": 2_000},
        {"training_end": 2_001, "validation_start": 2_000},
        {"validation_start": 3_000, "validation_end": 3_000},
        {"validation_end": -1},
    ),
)
def test_fold_rejects_invalid_boundaries(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _fold(**kwargs)  # type: ignore[arg-type]


def test_policy_accepts_reordered_adjacent_folds() -> None:
    first = _fold(name="a", validation_start=2_000, validation_end=3_000)
    second = _fold(
        name="b",
        training_start=1_000,
        training_end=2_500,
        validation_start=3_000,
        validation_end=4_000,
    )
    policy = TimeAwareValidationPolicy(version="walk-v1", folds=(second, first))
    assert policy.folds == (second, first)


def test_policy_rejects_duplicate_names_and_overlapping_validation() -> None:
    first = _fold(name="same", validation_start=2_000, validation_end=3_000)
    duplicate = _fold(
        name="same",
        training_start=1_000,
        training_end=2_000,
        validation_start=3_000,
        validation_end=4_000,
    )
    with pytest.raises(ValueError, match="unique"):
        TimeAwareValidationPolicy(version="walk-v1", folds=(first, duplicate))

    overlap = _fold(
        name="overlap",
        training_start=1_000,
        training_end=2_100,
        validation_start=2_500,
        validation_end=3_500,
    )
    with pytest.raises(ValueError, match="overlap"):
        TimeAwareValidationPolicy(version="walk-v1", folds=(first, overlap))


def test_policy_rejects_empty_or_non_exact_fold_tuple() -> None:
    with pytest.raises(ValueError, match="folds"):
        TimeAwareValidationPolicy(version="walk-v1", folds=())
    with pytest.raises(ValueError, match="folds"):
        TimeAwareValidationPolicy(version="walk-v1", folds=[_fold()])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="version"):
        TimeAwareValidationPolicy(version="", folds=(_fold(),))


def test_fold_result_reconciles_counts_predictions_and_window() -> None:
    result = _result()
    assert result.training_window_row_count == 3
    assert result.training_mature_target_row_count == result.model.training_row_count
    assert result.validation_row_count == len(result.predictions)


@pytest.mark.parametrize(
    "factory",
    (
        lambda: _result(training_mature_target_row_count=1),
        lambda: _result(training_window_row_count=4),
        lambda: _result(validation_row_count=1),
        lambda: _result(
            predictions=(
                ModelPrediction("other", "mint-a", 2_100, 0.25),
                _predictions()[1],
            )
        ),
        lambda: _result(predictions=tuple(reversed(_predictions()))),
        lambda: _result(
            predictions=(
                ModelPrediction("model-v1", "mint-a", 1_999, 0.25),
                _predictions()[1],
            )
        ),
    ),
)
def test_fold_result_rejects_reconciliation_errors(factory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        factory()


def test_validation_run_accepts_canonical_results() -> None:
    run = TimeAwareValidationRun(
        schema_version=TIME_AWARE_VALIDATION_SCHEMA_VERSION,
        validation_policy_version="walk-v1",
        model_training_request=_request(),
        fold_results=(_result(),),
        validation_run_fingerprint_sha256="b" * 64,
    )
    assert run.fold_results[0].fold.name == "fold-1"


def test_validation_run_rejects_bad_schema_request_results_order_and_digest() -> None:
    result = _result()
    with pytest.raises(ValueError, match="schema"):
        TimeAwareValidationRun(
            schema_version="wrong",
            validation_policy_version="walk-v1",
            model_training_request=_request(),
            fold_results=(result,),
            validation_run_fingerprint_sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="policy"):
        TimeAwareValidationRun(
            schema_version=TIME_AWARE_VALIDATION_SCHEMA_VERSION,
            validation_policy_version="",
            model_training_request=_request(),
            fold_results=(result,),
            validation_run_fingerprint_sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="request"):
        TimeAwareValidationRun(
            schema_version=TIME_AWARE_VALIDATION_SCHEMA_VERSION,
            validation_policy_version="walk-v1",
            model_training_request=object(),  # type: ignore[arg-type]
            fold_results=(result,),
            validation_run_fingerprint_sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="fold_results"):
        TimeAwareValidationRun(
            schema_version=TIME_AWARE_VALIDATION_SCHEMA_VERSION,
            validation_policy_version="walk-v1",
            model_training_request=_request(),
            fold_results=(),
            validation_run_fingerprint_sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="SHA"):
        TimeAwareValidationRun(
            schema_version=TIME_AWARE_VALIDATION_SCHEMA_VERSION,
            validation_policy_version="walk-v1",
            model_training_request=_request(),
            fold_results=(result,),
            validation_run_fingerprint_sha256="not-a-digest",
        )

    later_fold = _fold(
        name="later",
        training_start=1_000,
        training_end=2_000,
        validation_start=4_000,
        validation_end=5_000,
    )
    later_predictions = (
        ModelPrediction("model-v1", "mint-z", 4_100, 0.5),
        ModelPrediction("model-v1", "mint-zz", 4_200, 0.6),
    )
    later_result = _result(fold=later_fold, predictions=later_predictions)
    with pytest.raises(ValueError, match="canonical"):
        TimeAwareValidationRun(
            schema_version=TIME_AWARE_VALIDATION_SCHEMA_VERSION,
            validation_policy_version="walk-v1",
            model_training_request=_request(),
            fold_results=(later_result, result),
            validation_run_fingerprint_sha256="b" * 64,
        )
