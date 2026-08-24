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


def _target() -> ResearchReturnTarget:
    return ResearchReturnTarget(horizon_seconds=300, minimum_return_pct=5.0)


def _policy() -> LogisticRegressionTrainingPolicy:
    return LogisticRegressionTrainingPolicy(
        version="logit-policy-v1",
        regularization_c=1.0,
        max_iterations=500,
        tolerance=1e-6,
        class_weight_mode=ClassWeightMode.NONE,
    )


def _transform(name: str = "market_liquidity_usd") -> FeatureTransform:
    return FeatureTransform(
        feature_name=name,
        imputation_median=100_000.0,
        mean=100_000.0,
        scale=10_000.0,
    )


def _model() -> TrainedLogisticRegressionModel:
    return TrainedLogisticRegressionModel(
        schema_version=MODEL_TRAINING_SCHEMA_VERSION,
        model_version="model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        training_policy_version="logit-policy-v1",
        research_dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        target=_target(),
        feature_transforms=(_transform(),),
        coefficients=(0.5,),
        intercept=-0.25,
        training_row_count=10,
        positive_row_count=4,
        negative_row_count=6,
        target_unavailable_row_count=2,
        min_training_as_of_unix_ms=1_000,
        max_training_as_of_unix_ms=10_000,
        training_fingerprint_sha256="a" * 64,
    )


def test_schema_and_enum_values_are_sealed() -> None:
    assert MODEL_TRAINING_SCHEMA_VERSION == "e3-training-v1"
    assert tuple(ModelFamily) == (ModelFamily.LOGISTIC_REGRESSION,)
    assert ModelFamily.LOGISTIC_REGRESSION.value == "LOGISTIC_REGRESSION"
    assert tuple(ClassWeightMode) == (
        ClassWeightMode.NONE,
        ClassWeightMode.BALANCED,
    )


def test_return_target_requires_approved_horizon_and_finite_threshold() -> None:
    assert _target().horizon_seconds == 300
    for invalid in (0, 61, 86_401, True):
        with pytest.raises(ValueError, match="horizon"):
            ResearchReturnTarget(horizon_seconds=invalid, minimum_return_pct=0.0)
    for invalid in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError, match="minimum_return_pct"):
            ResearchReturnTarget(horizon_seconds=300, minimum_return_pct=invalid)


def test_training_policy_is_explicit_and_validated() -> None:
    assert _policy().class_weight_mode is ClassWeightMode.NONE
    with pytest.raises(ValueError, match="version"):
        LogisticRegressionTrainingPolicy("", 1.0, 100, 1e-4, ClassWeightMode.NONE)
    for invalid in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="regularization_c"):
            LogisticRegressionTrainingPolicy("v", invalid, 100, 1e-4, ClassWeightMode.NONE)
    for invalid in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match="max_iterations"):
            LogisticRegressionTrainingPolicy("v", 1.0, invalid, 1e-4, ClassWeightMode.NONE)
    for invalid in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="tolerance"):
            LogisticRegressionTrainingPolicy("v", 1.0, 100, invalid, ClassWeightMode.NONE)
    with pytest.raises(ValueError, match="class_weight_mode"):
        LogisticRegressionTrainingPolicy("v", 1.0, 100, 1e-4, "NONE")  # type: ignore[arg-type]


def test_training_request_requires_exact_types_and_unique_features() -> None:
    request = ModelTrainingRequest(
        model_version="model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_columns=("market_liquidity_usd", "market_volume_m5_usd"),
        target=_target(),
        training_policy=_policy(),
    )
    assert request.feature_columns[0] == "market_liquidity_usd"

    with pytest.raises(ValueError, match="model_version"):
        ModelTrainingRequest("", ModelFamily.LOGISTIC_REGRESSION, ("a",), _target(), _policy())
    with pytest.raises(ValueError, match="model_family"):
        ModelTrainingRequest("v", "LOGISTIC_REGRESSION", ("a",), _target(), _policy())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="feature_columns"):
        ModelTrainingRequest("v", ModelFamily.LOGISTIC_REGRESSION, (), _target(), _policy())
    with pytest.raises(ValueError, match="duplicate"):
        ModelTrainingRequest("v", ModelFamily.LOGISTIC_REGRESSION, ("a", "a"), _target(), _policy())
    with pytest.raises(ValueError, match="feature_columns"):
        ModelTrainingRequest("v", ModelFamily.LOGISTIC_REGRESSION, ["a"], _target(), _policy())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="target"):
        ModelTrainingRequest("v", ModelFamily.LOGISTIC_REGRESSION, ("a",), object(), _policy())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="training_policy"):
        ModelTrainingRequest("v", ModelFamily.LOGISTIC_REGRESSION, ("a",), _target(), object())  # type: ignore[arg-type]


def test_feature_transform_requires_finite_values_and_positive_scale() -> None:
    assert _transform().scale == 10_000.0
    with pytest.raises(ValueError, match="feature_name"):
        FeatureTransform("", 1.0, 1.0, 1.0)
    for field in ("imputation_median", "mean"):
        kwargs = dict(feature_name="a", imputation_median=1.0, mean=1.0, scale=1.0)
        kwargs[field] = float("nan")
        with pytest.raises(ValueError, match=field):
            FeatureTransform(**kwargs)
    for invalid in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="scale"):
            FeatureTransform("a", 1.0, 1.0, invalid)


def test_trained_model_reconciles_dimensions_counts_provenance_and_bounds() -> None:
    model = _model()
    assert model.positive_row_count + model.negative_row_count == model.training_row_count

    values = dict(
        schema_version=MODEL_TRAINING_SCHEMA_VERSION,
        model_version="model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        training_policy_version="logit-policy-v1",
        research_dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        target=_target(),
        feature_transforms=(_transform(),),
        coefficients=(0.5,),
        intercept=-0.25,
        training_row_count=10,
        positive_row_count=4,
        negative_row_count=6,
        target_unavailable_row_count=2,
        min_training_as_of_unix_ms=1_000,
        max_training_as_of_unix_ms=10_000,
        training_fingerprint_sha256="a" * 64,
    )

    bad = dict(values, schema_version="wrong")
    with pytest.raises(ValueError, match="schema_version"):
        TrainedLogisticRegressionModel(**bad)
    bad = dict(values, research_dataset_schema_version="wrong")
    with pytest.raises(ValueError, match="research_dataset_schema_version"):
        TrainedLogisticRegressionModel(**bad)
    bad = dict(values, coefficients=(0.5, 0.2))
    with pytest.raises(ValueError, match="coefficient"):
        TrainedLogisticRegressionModel(**bad)
    bad = dict(values, feature_transforms=(_transform("x"), _transform("x")), coefficients=(0.1, 0.2))
    with pytest.raises(ValueError, match="unique"):
        TrainedLogisticRegressionModel(**bad)
    bad = dict(values, training_row_count=9)
    with pytest.raises(ValueError, match="positive.*negative|row counts"):
        TrainedLogisticRegressionModel(**bad)
    bad = dict(values, min_training_as_of_unix_ms=11_000)
    with pytest.raises(ValueError, match="min.*max"):
        TrainedLogisticRegressionModel(**bad)
    for digest in ("A" * 64, "a" * 63, "g" * 64):
        bad = dict(values, training_fingerprint_sha256=digest)
        with pytest.raises(ValueError, match="fingerprint"):
            TrainedLogisticRegressionModel(**bad)


def test_prediction_requires_bounded_probability_and_identity() -> None:
    value = ModelPrediction(
        model_version="model-v1",
        candidate_mint="mint-a",
        as_of_unix_ms=100,
        positive_probability=0.75,
    )
    assert value.positive_probability == 0.75
    for probability in (-0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="positive_probability"):
            ModelPrediction("model-v1", "mint-a", 100, probability)
    with pytest.raises(ValueError, match="candidate_mint"):
        ModelPrediction("model-v1", "", 100, 0.5)
    with pytest.raises(ValueError, match="as_of_unix_ms"):
        ModelPrediction("model-v1", "mint-a", -1, 0.5)


def test_public_contracts_are_frozen() -> None:
    values = (
        _target(),
        _policy(),
        ModelTrainingRequest("m", ModelFamily.LOGISTIC_REGRESSION, ("a",), _target(), _policy()),
        _transform(),
        _model(),
        ModelPrediction("m", "mint", 1, 0.5),
    )
    for value in values:
        with pytest.raises(FrozenInstanceError):
            value.__setattr__(next(iter(value.__dataclass_fields__)), object())
