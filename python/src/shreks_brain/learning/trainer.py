from __future__ import annotations

import math
import warnings

from shreks_brain.research import RESEARCH_DATASET_SCHEMA_VERSION

from .features import _prepare_training_data
from .models import (
    MODEL_TRAINING_SCHEMA_VERSION,
    ClassWeightMode,
    ModelFamily,
    ModelTrainingRequest,
    TrainedLogisticRegressionModel,
)


def train_logistic_regression(
    rows: tuple[dict[str, object], ...],
    request: ModelTrainingRequest,
) -> TrainedLogisticRegressionModel:
    prepared = _prepare_training_data(rows, request)
    training_row_count = len(prepared.targets)
    if training_row_count < 2:
        raise ValueError("training requires at least 2 target-eligible rows")

    positive_row_count = sum(prepared.targets)
    negative_row_count = training_row_count - positive_row_count
    if positive_row_count == 0 or negative_row_count == 0:
        raise ValueError("training requires both target classes")

    try:
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise RuntimeError(
            "scikit-learn is required for E3 training; install the learning extra"
        ) from exc

    policy = request.training_policy
    class_weight = (
        "balanced"
        if policy.class_weight_mode is ClassWeightMode.BALANCED
        else None
    )
    estimator = LogisticRegression(
        solver="lbfgs",
        C=policy.regularization_c,
        max_iter=policy.max_iterations,
        tol=policy.tolerance,
        class_weight=class_weight,
        fit_intercept=True,
    )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            estimator.fit(prepared.feature_matrix, prepared.targets)
    except ConvergenceWarning as exc:
        raise ValueError("logistic regression did not converge") from exc

    classes = tuple(int(value) for value in estimator.classes_.tolist())
    if classes != (0, 1):
        raise ValueError("fitted logistic regression must expose classes (0, 1)")

    coefficient_rows = estimator.coef_.tolist()
    intercept_values = estimator.intercept_.tolist()
    if (
        len(coefficient_rows) != 1
        or len(coefficient_rows[0]) != len(prepared.feature_transforms)
        or len(intercept_values) != 1
    ):
        raise ValueError("fitted logistic regression has unexpected dimensions")

    coefficients = tuple(float(value) for value in coefficient_rows[0])
    intercept = float(intercept_values[0])
    if not all(math.isfinite(value) for value in coefficients):
        raise ValueError("fitted logistic regression coefficients must be finite")
    if not math.isfinite(intercept):
        raise ValueError("fitted logistic regression intercept must be finite")

    return TrainedLogisticRegressionModel(
        schema_version=MODEL_TRAINING_SCHEMA_VERSION,
        model_version=request.model_version,
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        training_policy_version=policy.version,
        research_dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        target=request.target,
        feature_transforms=prepared.feature_transforms,
        coefficients=coefficients,
        intercept=intercept,
        training_row_count=training_row_count,
        positive_row_count=positive_row_count,
        negative_row_count=negative_row_count,
        target_unavailable_row_count=prepared.target_unavailable_row_count,
        min_training_as_of_unix_ms=prepared.min_training_as_of_unix_ms,
        max_training_as_of_unix_ms=prepared.max_training_as_of_unix_ms,
        training_fingerprint_sha256=prepared.training_fingerprint_sha256,
    )
