from __future__ import annotations

import inspect
import math

import pytest

from shreks_brain.learning import (
    FeatureTransform,
    MODEL_TRAINING_SCHEMA_VERSION,
    ModelFamily,
    ResearchReturnTarget,
    TrainedLogisticRegressionModel,
    predict_positive_probability,
)
from shreks_brain.learning import inference
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
)


def _model(
    *,
    coefficient: float = 2.0,
    intercept: float = 0.0,
) -> TrainedLogisticRegressionModel:
    return TrainedLogisticRegressionModel(
        schema_version=MODEL_TRAINING_SCHEMA_VERSION,
        model_version="challenger-e3-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        training_policy_version="logit-e3-test-v1",
        research_dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        target=ResearchReturnTarget(
            horizon_seconds=300,
            minimum_return_pct=5.0,
        ),
        feature_transforms=(
            FeatureTransform(
                feature_name="market_liquidity_usd",
                imputation_median=200.0,
                mean=200.0,
                scale=100.0,
            ),
        ),
        coefficients=(coefficient,),
        intercept=intercept,
        training_row_count=4,
        positive_row_count=2,
        negative_row_count=2,
        target_unavailable_row_count=1,
        min_training_as_of_unix_ms=1_000,
        max_training_as_of_unix_ms=4_000,
        training_fingerprint_sha256="a" * 64,
    )


def _row(
    *,
    liquidity: object = 300.0,
    mint: str = "mint-a",
    as_of: int = 5_000,
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
            "market_liquidity_usd": liquidity,
        }
    )
    return row


def test_prediction_preserves_identity_and_probability_bounds() -> None:
    prediction = predict_positive_probability(_model(), _row())
    assert prediction.model_version == "challenger-e3-v1"
    assert prediction.candidate_mint == "mint-a"
    assert prediction.as_of_unix_ms == 5_000
    assert 0.0 <= prediction.positive_probability <= 1.0


def test_missing_inference_feature_uses_stored_training_median() -> None:
    prediction = predict_positive_probability(_model(), _row(liquidity=None))
    assert prediction.positive_probability == pytest.approx(0.5)


def test_inference_rejects_unsupported_or_non_finite_feature_evidence() -> None:
    for invalid in ("300", float("nan"), float("inf")):
        with pytest.raises(ValueError, match="market_liquidity_usd"):
            predict_positive_probability(_model(), _row(liquidity=invalid))


def test_future_labels_cannot_change_prediction() -> None:
    base = _row()
    changed = dict(base)
    for column in RESEARCH_LABEL_COLUMNS:
        if column.endswith("_return_pct"):
            changed[column] = 999.0
        elif column.endswith("_rug_or_dead_pool"):
            changed[column] = True
        elif column.endswith("_exitability"):
            changed[column] = "NOT_EXITABLE"
    assert predict_positive_probability(_model(), base) == predict_positive_probability(
        _model(), changed
    )


def test_prediction_validates_sealed_d6_schema_and_physical_columns() -> None:
    wrong_schema = _row()
    wrong_schema["dataset_schema_version"] = "wrong"
    with pytest.raises(ValueError, match="schema"):
        predict_positive_probability(_model(), wrong_schema)

    missing_column = _row()
    missing_column.pop("market_liquidity_usd")
    with pytest.raises(ValueError, match="column"):
        predict_positive_probability(_model(), missing_column)


def test_stable_sigmoid_handles_extreme_logits_without_overflow() -> None:
    high = predict_positive_probability(
        _model(coefficient=1_000.0),
        _row(liquidity=300.0),
    )
    low = predict_positive_probability(
        _model(coefficient=-1_000.0),
        _row(liquidity=300.0),
    )
    assert math.isfinite(high.positive_probability)
    assert math.isfinite(low.positive_probability)
    assert high.positive_probability == pytest.approx(1.0)
    assert low.positive_probability == pytest.approx(0.0)


def test_inference_module_is_standard_library_only() -> None:
    source = inspect.getsource(inference)
    assert "sklearn" not in source
    assert "numpy" not in source
