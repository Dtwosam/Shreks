from __future__ import annotations

import sys

import pytest

from fast_forecast_fixtures import training_bundle
from shreks_brain.fast_learning.models import (
    FAST_FORECAST_ARTIFACT_SCHEMA_NAME,
    FAST_FORECAST_ARTIFACT_SCHEMA_VERSION,
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_learning.trainer import train_fast_forecast_baseline


def policy_for(family: FastForecastModelFamily) -> FastForecastTrainingPolicy:
    if family is FastForecastModelFamily.RIDGE_REGRESSION:
        return FastForecastTrainingPolicy(version="ridge-v1", ridge_alpha=1.0)
    if family is FastForecastModelFamily.LOGISTIC_REGRESSION:
        return FastForecastTrainingPolicy(
            version="logit-v1",
            logistic_regularization_c=1.0,
            logistic_max_iterations=2_000,
            logistic_tolerance=1e-10,
            logistic_balanced_class_weight=False,
        )
    return FastForecastTrainingPolicy(version="naive-v1")


def request(
    family: FastForecastModelFamily,
    target: FastForecastTarget,
    *,
    horizon_ms: int = 250,
) -> FastForecastTrainingRequest:
    return FastForecastTrainingRequest(
        model_version=f"{family.value.lower()}-{target.value}-h{horizon_ms}",
        model_family=family,
        target=target,
        horizon_ms=horizon_ms,
        training_policy=policy_for(family),
    )


def test_artifact_constants_and_family_target_pairing_are_stable() -> None:
    assert FAST_FORECAST_ARTIFACT_SCHEMA_NAME == "shreks.fast_lane_forecast_baseline"
    assert FAST_FORECAST_ARTIFACT_SCHEMA_VERSION == 1
    with pytest.raises(ValueError, match="family|target"):
        request(
            FastForecastModelFamily.LOGISTIC_REGRESSION,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        )
    with pytest.raises(ValueError, match="family|target"):
        request(
            FastForecastModelFamily.RIDGE_REGRESSION,
            FastForecastTarget.REVERSAL_OCCURRED,
        )


def test_naive_regression_and_classifier_use_only_requested_complete_horizon() -> None:
    bundle = training_bundle()
    mean_model = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.MEAN_REGRESSOR, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    prior_model = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.PRIOR_CLASSIFIER, FastForecastTarget.REVERSAL_OCCURRED),
    )
    assert mean_model.training_row_count == 6
    assert mean_model.target_unavailable_row_count == 0
    assert mean_model.constant_prediction == pytest.approx(17.5)
    assert mean_model.coefficients == ()
    assert mean_model.feature_transforms == ()
    assert prior_model.training_row_count == 6
    assert prior_model.constant_prediction == pytest.approx(0.5)
    assert prior_model.positive_row_count == 3
    assert prior_model.negative_row_count == 3


def test_incomplete_and_null_targets_are_excluded_not_zero_filled() -> None:
    bundle = training_bundle()
    model = train_fast_forecast_baseline(
        bundle,
        request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
            horizon_ms=500,
        ),
    )
    assert model.training_row_count == 4
    assert model.target_unavailable_row_count == 2


def test_target_only_change_changes_training_and_artifact_fingerprints_not_features() -> None:
    original_bundle = training_bundle(target_shift=0.0)
    changed_bundle = training_bundle(target_shift=7.0)
    assert (
        original_bundle.manifest.feature_logical_fingerprint_sha256
        == changed_bundle.manifest.feature_logical_fingerprint_sha256
    )
    original = train_fast_forecast_baseline(
        original_bundle,
        request(FastForecastModelFamily.MEAN_REGRESSOR, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    changed = train_fast_forecast_baseline(
        changed_bundle,
        request(FastForecastModelFamily.MEAN_REGRESSOR, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    assert original.training_data_fingerprint_sha256 != changed.training_data_fingerprint_sha256
    assert original.artifact_fingerprint_sha256 != changed.artifact_fingerprint_sha256


def test_unknown_horizon_and_invalid_training_policy_fail_closed() -> None:
    with pytest.raises(ValueError, match="horizon|rows|label"):
        train_fast_forecast_baseline(
            training_bundle(),
            request(
                FastForecastModelFamily.MEAN_REGRESSOR,
                FastForecastTarget.ENDPOINT_RETURN_BPS,
                horizon_ms=999,
            ),
        )
    with pytest.raises(ValueError, match="ridge|policy|alpha"):
        FastForecastTrainingRequest(
            model_version="bad-ridge",
            model_family=FastForecastModelFamily.RIDGE_REGRESSION,
            target=FastForecastTarget.ENDPOINT_RETURN_BPS,
            horizon_ms=250,
            training_policy=FastForecastTrainingPolicy(version="bad"),
        )


def test_ridge_and_logistic_fit_standard_library_artifacts_with_lazy_sklearn() -> None:
    bundle = training_bundle()
    ridge = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.RIDGE_REGRESSION, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    logistic = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.LOGISTIC_REGRESSION, FastForecastTarget.REVERSAL_OCCURRED),
    )
    assert len(ridge.coefficients) == len(ridge.feature_transforms) > 10
    assert ridge.intercept is not None
    assert ridge.constant_prediction is None
    assert len(logistic.coefficients) == len(logistic.feature_transforms)
    assert logistic.intercept is not None
    assert logistic.constant_prediction is None
    assert not any(hasattr(value, "predict") for value in ridge.coefficients)


def test_importing_fast_learning_does_not_eagerly_import_sklearn() -> None:
    script = "import sys; import shreks_brain.fast_learning; assert not any(k == 'sklearn' or k.startswith('sklearn.') for k in sys.modules)"
    import subprocess

    subprocess.run([sys.executable, "-c", script], check=True)
