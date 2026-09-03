from __future__ import annotations

from dataclasses import replace
import math

import pytest

from fast_chronological_fixtures import chronological_bundle
from fast_forecast_evaluation_fixtures import (
    build_run,
    evaluation_contexts,
    evaluation_policy,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    evaluate_fast_forecasts,
)
from shreks_brain.fast_learning import FastForecastModelFamily, FastForecastTarget


def test_validation_continuous_mean_baseline_metrics_are_exact() -> None:
    bundle, run = build_run()
    report = evaluate_fast_forecasts(
        bundle,
        run,
        evaluation_contexts(run),
        evaluation_policy(FastForecastEvaluationPartition.VALIDATION),
    )
    assert report.evaluation_policy.partition is FastForecastEvaluationPartition.VALIDATION
    assert report.target is FastForecastTarget.ENDPOINT_RETURN_BPS
    assert report.target_is_cost_adjusted is False
    assert report.overall.name == "overall"
    assert report.overall.prediction_count == 3
    assert report.overall.scored_observation_count == 3
    assert report.overall.target_unavailable_count == 0
    metrics = report.overall.continuous_metrics
    assert metrics is not None
    assert report.overall.binary_metrics is None
    assert metrics.observation_count == 3
    assert metrics.mean_predicted_value == pytest.approx(-37.5)
    assert metrics.mean_actual_value == pytest.approx(75.0)
    assert metrics.mean_error == pytest.approx(-112.5)
    assert metrics.mean_absolute_error == pytest.approx(112.5)
    expected_rmse = math.sqrt(
        ((-37.5 - 50.0) ** 2 + (-37.5 - 75.0) ** 2 + (-37.5 - 100.0) ** 2)
        / 3.0
    )
    assert metrics.root_mean_squared_error == pytest.approx(expected_rmse)


def test_test_partition_is_independent_and_uses_only_test_predictions() -> None:
    bundle, run = build_run()
    report = evaluate_fast_forecasts(
        bundle,
        run,
        evaluation_contexts(run),
        evaluation_policy(FastForecastEvaluationPartition.TEST),
    )
    assert report.overall.prediction_count == 3
    metrics = report.overall.continuous_metrics
    assert metrics is not None
    assert metrics.mean_predicted_value == pytest.approx(-37.5)
    assert metrics.mean_actual_value == pytest.approx(150.0)
    assert metrics.mean_error == pytest.approx(-187.5)


def test_incomplete_validation_target_is_unavailable_not_zero_filled() -> None:
    bundle = chronological_bundle(incomplete_training_index=7)
    bundle, run = build_run(bundle=bundle)
    report = evaluate_fast_forecasts(
        bundle,
        run,
        evaluation_contexts(run),
        evaluation_policy(FastForecastEvaluationPartition.VALIDATION),
    )
    assert report.overall.prediction_count == 3
    assert report.overall.scored_observation_count == 2
    assert report.overall.target_unavailable_count == 1
    metrics = report.overall.continuous_metrics
    assert metrics is not None
    assert metrics.observation_count == 2
    assert metrics.mean_actual_value == pytest.approx(75.0)


def test_binary_prior_metrics_brier_log_loss_and_ece_are_exact() -> None:
    bundle, run = build_run(
        family=FastForecastModelFamily.PRIOR_CLASSIFIER,
        target=FastForecastTarget.REVERSAL_OCCURRED,
    )
    report = evaluate_fast_forecasts(
        bundle,
        run,
        evaluation_contexts(run),
        evaluation_policy(FastForecastEvaluationPartition.VALIDATION),
    )
    metrics = report.overall.binary_metrics
    assert metrics is not None
    assert report.overall.continuous_metrics is None
    assert metrics.observation_count == 3
    assert metrics.positive_count == 1
    assert metrics.mean_predicted_probability == pytest.approx(0.5)
    assert metrics.brier_score == pytest.approx(0.25)
    assert metrics.log_loss == pytest.approx(math.log(2.0))
    assert metrics.expected_calibration_error == pytest.approx(1.0 / 6.0)
    assert len(metrics.calibration_buckets) == 2
    assert metrics.calibration_buckets[0].observation_count == 0
    upper = metrics.calibration_buckets[1]
    assert upper.lower_probability == pytest.approx(0.5)
    assert upper.upper_probability == pytest.approx(1.0)
    assert upper.observation_count == 3
    assert upper.mean_predicted_probability == pytest.approx(0.5)
    assert upper.observed_positive_rate == pytest.approx(1.0 / 3.0)


def test_cost_adjusted_target_is_measured_without_second_cost_subtraction() -> None:
    bundle, run = build_run(
        family=FastForecastModelFamily.MEAN_REGRESSOR,
        target=FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
    )
    report = evaluate_fast_forecasts(
        bundle,
        run,
        evaluation_contexts(run),
        evaluation_policy(FastForecastEvaluationPartition.VALIDATION),
    )
    assert report.target_is_cost_adjusted is True
    metrics = report.overall.continuous_metrics
    assert metrics is not None
    assert metrics.mean_predicted_value == pytest.approx(-57.5)
    assert metrics.mean_actual_value == pytest.approx(55.0)


def test_bundle_run_fingerprint_mismatch_fails_closed() -> None:
    bundle, run = build_run()
    malformed = replace(
        run,
        training_bundle_fingerprint_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="bundle|fingerprint"):
        evaluate_fast_forecasts(
            bundle,
            malformed,
            evaluation_contexts(run),
            evaluation_policy(),
        )
