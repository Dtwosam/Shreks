from __future__ import annotations

from pathlib import Path

from fast_forecast_evaluation_fixtures import evaluation_contexts, evaluation_policy
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    evaluate_fast_forecasts,
    read_fast_forecast_evaluation_report,
    write_fast_forecast_evaluation_report,
)
from shreks_brain.fast_learning import FastForecastModelFamily, FastForecastTarget
from shreks_brain.fast_validation import run_fast_chronological_validation
from shreks_brain.research.fast_training_bundle import read_fast_training_bundle
from test_fast_chronological_integration import _policy, _request, _write_fl81_bundle


def test_real_fl81_fl83_pipeline_evaluates_all_four_model_families(tmp_path: Path) -> None:
    bundle = read_fast_training_bundle(_write_fl81_bundle(tmp_path / "source"))
    requests = (
        _request(FastForecastModelFamily.MEAN_REGRESSOR, FastForecastTarget.ENDPOINT_RETURN_BPS),
        _request(FastForecastModelFamily.RIDGE_REGRESSION, FastForecastTarget.ENDPOINT_RETURN_BPS),
        _request(FastForecastModelFamily.PRIOR_CLASSIFIER, FastForecastTarget.REVERSAL_OCCURRED),
        _request(FastForecastModelFamily.LOGISTIC_REGRESSION, FastForecastTarget.REVERSAL_OCCURRED),
    )
    for request in requests:
        run = run_fast_chronological_validation(bundle, request, _policy())
        report = evaluate_fast_forecasts(
            bundle,
            run,
            evaluation_contexts(run),
            evaluation_policy(FastForecastEvaluationPartition.TEST),
        )
        assert report.overall.prediction_count == 2
        # One surviving test row is a complete no-trade label with a null
        # selected path target, so it must remain explicitly unavailable.
        assert report.overall.scored_observation_count == 1
        assert report.overall.target_unavailable_count == 1
        output = tmp_path / f"{request.model_version}.evaluation.json"
        write_fast_forecast_evaluation_report(report, output)
        assert read_fast_forecast_evaluation_report(output) == report


def test_real_bundle_cost_adjusted_target_is_not_double_costed(tmp_path: Path) -> None:
    bundle = read_fast_training_bundle(_write_fl81_bundle(tmp_path / "cost-source"))
    request = _request(
        FastForecastModelFamily.MEAN_REGRESSOR,
        FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
    )
    run = run_fast_chronological_validation(bundle, request, _policy())
    report = evaluate_fast_forecasts(
        bundle,
        run,
        evaluation_contexts(run),
        evaluation_policy(FastForecastEvaluationPartition.TEST),
    )
    assert report.target_is_cost_adjusted is True
    metrics = report.overall.continuous_metrics
    assert metrics is not None
    assert metrics.observation_count == 1
    assert metrics.mean_actual_value == 160.0
