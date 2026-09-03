from __future__ import annotations

import pytest
from sklearn.linear_model import LogisticRegression, Ridge

from fast_forecast_fixtures import training_bundle
from shreks_brain.fast_learning.features import (
    apply_feature_transforms,
    extract_fast_forecast_features,
)
from shreks_brain.fast_learning.inference import predict_fast_forecast
from shreks_brain.fast_learning.models import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_learning.trainer import train_fast_forecast_baseline


def test_ridge_reference_inference_matches_sklearn_prediction() -> None:
    bundle = training_bundle()
    request = FastForecastTrainingRequest(
        model_version="ridge-reference-parity",
        model_family=FastForecastModelFamily.RIDGE_REGRESSION,
        target=FastForecastTarget.ENDPOINT_RETURN_BPS,
        horizon_ms=250,
        training_policy=FastForecastTrainingPolicy(version="ridge-v1", ridge_alpha=1.0),
    )
    artifact = train_fast_forecast_baseline(bundle, request)
    feature_by_identity = {
        record.decision_identity: record for record in bundle.features.records
    }
    labels = tuple(
        label
        for label in bundle.future_path_labels.labels
        if label.horizon_ms == 250
        and label.completeness == "complete"
        and label.endpoint_return_bps is not None
    )
    matrix = tuple(
        apply_feature_transforms(
            extract_fast_forecast_features(feature_by_identity[label.decision_identity]),
            artifact.feature_transforms,
        )
        for label in labels
    )
    targets = tuple(float(label.endpoint_return_bps) for label in labels)
    estimator = Ridge(alpha=1.0, fit_intercept=True)
    estimator.fit(matrix, targets)

    record = bundle.features.records[3]
    transformed = apply_feature_transforms(
        extract_fast_forecast_features(record), artifact.feature_transforms
    )
    expected = float(estimator.predict([transformed])[0])
    actual = predict_fast_forecast(artifact, record).predicted_value
    assert actual == pytest.approx(expected, abs=1e-10)


def test_logistic_reference_inference_matches_sklearn_probability() -> None:
    bundle = training_bundle()
    request = FastForecastTrainingRequest(
        model_version="logistic-reference-parity",
        model_family=FastForecastModelFamily.LOGISTIC_REGRESSION,
        target=FastForecastTarget.REVERSAL_OCCURRED,
        horizon_ms=250,
        training_policy=FastForecastTrainingPolicy(
            version="logit-v1",
            logistic_regularization_c=1.0,
            logistic_max_iterations=2_000,
            logistic_tolerance=1e-10,
            logistic_balanced_class_weight=False,
        ),
    )
    artifact = train_fast_forecast_baseline(bundle, request)
    feature_by_identity = {
        record.decision_identity: record for record in bundle.features.records
    }
    labels = tuple(
        label
        for label in bundle.future_path_labels.labels
        if label.horizon_ms == 250
        and label.completeness == "complete"
        and label.reversal_occurred is not None
    )
    matrix = tuple(
        apply_feature_transforms(
            extract_fast_forecast_features(feature_by_identity[label.decision_identity]),
            artifact.feature_transforms,
        )
        for label in labels
    )
    targets = tuple(int(bool(label.reversal_occurred)) for label in labels)
    estimator = LogisticRegression(
        solver="lbfgs",
        C=1.0,
        max_iter=2_000,
        tol=1e-10,
        class_weight=None,
        fit_intercept=True,
    )
    estimator.fit(matrix, targets)

    record = bundle.features.records[4]
    transformed = apply_feature_transforms(
        extract_fast_forecast_features(record), artifact.feature_transforms
    )
    expected = float(estimator.predict_proba([transformed])[0][1])
    actual = predict_fast_forecast(artifact, record).predicted_value
    assert actual == pytest.approx(expected, abs=1e-10)
