from __future__ import annotations

import math

import pytest

from shreks_brain.evaluation import build_probability_observations_from_e4
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
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
)
from shreks_brain.validation import (
    TIME_AWARE_VALIDATION_SCHEMA_VERSION,
    ChronologicalValidationFold,
    TimeAwareValidationRun,
    ValidationFoldResult,
)


TARGET_HORIZON = 300
TARGET_THRESHOLD = 5.0


def _request() -> ModelTrainingRequest:
    return ModelTrainingRequest(
        model_version="model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_columns=("market_liquidity_usd",),
        target=ResearchReturnTarget(
            horizon_seconds=TARGET_HORIZON,
            minimum_return_pct=TARGET_THRESHOLD,
        ),
        training_policy=LogisticRegressionTrainingPolicy(
            version="training-v1",
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
        training_policy_version="training-v1",
        research_dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        target=ResearchReturnTarget(
            horizon_seconds=TARGET_HORIZON,
            minimum_return_pct=TARGET_THRESHOLD,
        ),
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
        min_training_as_of_unix_ms=100_000,
        max_training_as_of_unix_ms=200_000,
        training_fingerprint_sha256="a" * 64,
    )


def _fold() -> ChronologicalValidationFold:
    return ChronologicalValidationFold(
        name="fold-1",
        training_started_at_unix_ms=0,
        training_ended_at_unix_ms=900_000,
        validation_started_at_unix_ms=1_000_000,
        validation_ended_at_unix_ms=1_100_000,
    )


def _predictions() -> tuple[ModelPrediction, ...]:
    return (
        ModelPrediction("model-v1", "mint-a", 1_000_000, 0.25),
        ModelPrediction("model-v1", "mint-b", 1_050_000, 0.75),
    )


def _run(
    predictions: tuple[ModelPrediction, ...] | None = None,
) -> TimeAwareValidationRun:
    values = _predictions() if predictions is None else predictions
    result = ValidationFoldResult(
        fold=_fold(),
        training_window_row_count=2,
        training_mature_target_row_count=2,
        training_target_unavailable_at_split_count=0,
        validation_row_count=len(values),
        model=_model(),
        predictions=values,
    )
    return TimeAwareValidationRun(
        schema_version=TIME_AWARE_VALIDATION_SCHEMA_VERSION,
        validation_policy_version="walk-v1",
        model_training_request=_request(),
        fold_results=(result,),
        validation_run_fingerprint_sha256="b" * 64,
    )


def _row(
    mint: str,
    as_of: int,
    target_return: float | None,
    *,
    target_status: str = "COMPLETED",
    setup_name: str = "fresh_launch_continuation",
    market_regime: str = "NORMAL",
) -> dict[str, object]:
    row = {
        column: None
        for column in RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
    }
    row.update(
        {
            "dataset_schema_version": RESEARCH_DATASET_SCHEMA_VERSION,
            "candidate_mint": mint,
            "as_of_unix_ms": as_of,
            "setup_name": setup_name,
            "market_regime": market_regime,
            "market_liquidity_usd": 100.0,
        }
    )
    for horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS:
        prefix = f"label_{horizon}s_"
        row[prefix + "status"] = "PENDING"
        row[prefix + "baseline_observed_at_unix_ms"] = as_of
        row[prefix + "due_at_unix_ms"] = as_of + horizon * 1_000

    prefix = f"label_{TARGET_HORIZON}s_"
    row[prefix + "status"] = target_status
    if target_status == "COMPLETED":
        due = as_of + TARGET_HORIZON * 1_000
        row[prefix + "checkpoint_observed_at_unix_ms"] = due
        row[prefix + "completed_at_unix_ms"] = due
        row[prefix + "return_pct"] = target_return
    return row


def _rows() -> tuple[dict[str, object], ...]:
    return (
        _row("mint-a", 1_000_000, 5.0),
        _row(
            "mint-b",
            1_050_000,
            -1.0,
            setup_name="graduation_breakout",
            market_regime="HOT",
        ),
    )


def test_adapter_joins_frozen_e4_predictions_to_completed_selected_target() -> None:
    observations = build_probability_observations_from_e4(
        tuple(reversed(_rows())), _run(), "challenger-v1"
    )

    assert tuple((value.as_of_unix_ms, value.candidate_mint) for value in observations) == (
        (1_000_000, "mint-a"),
        (1_050_000, "mint-b"),
    )
    assert observations[0].positive_probability == 0.25
    assert observations[0].target_positive is True
    assert observations[1].positive_probability == 0.75
    assert observations[1].target_positive is False
    assert observations[0].model_version == "model-v1"
    assert observations[0].fold_name == "fold-1"
    assert observations[0].setup_name == "fresh_launch_continuation"
    assert observations[1].market_regime == "HOT"


def test_target_completed_after_validation_start_can_score_frozen_prediction() -> None:
    row = _row("mint-a", 1_000_000, 10.0)
    prefix = f"label_{TARGET_HORIZON}s_"
    assert row[prefix + "completed_at_unix_ms"] > _fold().validation_started_at_unix_ms

    observations = build_probability_observations_from_e4(
        (row, _rows()[1]), _run(), "challenger-v1"
    )
    assert observations[0].positive_probability == _predictions()[0].positive_probability
    assert observations[0].target_positive is True


def test_non_selected_future_labels_do_not_change_probability_observations() -> None:
    rows = _rows()
    mutated = tuple(dict(value) for value in rows)
    mutated[0]["label_60s_status"] = "COMPLETED"
    mutated[0]["label_60s_return_pct"] = 999.0
    mutated[0]["label_60s_completed_at_unix_ms"] = 9_999_999

    assert build_probability_observations_from_e4(
        rows, _run(), "challenger-v1"
    ) == build_probability_observations_from_e4(
        mutated, _run(), "challenger-v1"
    )


def test_extra_rows_outside_e4_population_are_ignored() -> None:
    extra = _row("extra", 5_000_000, 100.0)
    result = build_probability_observations_from_e4(
        _rows() + (extra,), _run(), "challenger-v1"
    )
    assert len(result) == 2


def test_adapter_fails_closed_for_unavailable_or_invalid_selected_target() -> None:
    pending = (_row("mint-a", 1_000_000, None, target_status="PENDING"), _rows()[1])
    with pytest.raises(ValueError, match="mint-a"):
        build_probability_observations_from_e4(pending, _run(), "challenger-v1")

    missing_return = (_row("mint-a", 1_000_000, None), _rows()[1])
    with pytest.raises(ValueError, match="mint-a"):
        build_probability_observations_from_e4(
            missing_return, _run(), "challenger-v1"
        )

    nonfinite = (_row("mint-a", 1_000_000, math.inf), _rows()[1])
    with pytest.raises(ValueError, match="mint-a"):
        build_probability_observations_from_e4(nonfinite, _run(), "challenger-v1")


def test_adapter_fails_closed_for_identity_schema_and_type_contradictions() -> None:
    rows = _rows()

    with pytest.raises(ValueError, match="candidate_version"):
        build_probability_observations_from_e4(rows, _run(), "")
    with pytest.raises(ValueError, match="validation_run"):
        build_probability_observations_from_e4(rows, object(), "challenger-v1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="rows"):
        build_probability_observations_from_e4([], _run(), "challenger-v1")  # type: ignore[arg-type]

    malformed = dict(rows[0])
    malformed.pop("setup_name")
    with pytest.raises(ValueError, match="physical"):
        build_probability_observations_from_e4(
            (malformed, rows[1]), _run(), "challenger-v1"
        )

    with pytest.raises(ValueError, match="duplicate"):
        build_probability_observations_from_e4(
            (rows[0], dict(rows[0]), rows[1]), _run(), "challenger-v1"
        )

    with pytest.raises(ValueError, match="missing"):
        build_probability_observations_from_e4((rows[0],), _run(), "challenger-v1")

    duplicate_predictions = (
        ModelPrediction("model-v1", "mint-a", 1_000_000, 0.25),
        ModelPrediction("model-v1", "mint-a", 1_000_000, 0.30),
    )
    with pytest.raises(ValueError, match="duplicate"):
        build_probability_observations_from_e4(
            rows, _run(duplicate_predictions), "challenger-v1"
        )
