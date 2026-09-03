from __future__ import annotations

from dataclasses import replace

from fast_forecast_evaluation_fixtures import (
    chronological_policy,
    evaluation_contexts,
    evaluation_policy,
)
from fast_chronological_fixtures import chronological_bundle, forecast_request
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    evaluate_fast_forecasts,
)
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
    train_fast_forecast_baseline,
)
from shreks_brain.fast_learning.models import fast_forecast_artifact_fingerprint_sha256
from shreks_brain.fast_validation import run_fast_chronological_validation


def champion_source(
    family: FastForecastModelFamily = FastForecastModelFamily.MEAN_REGRESSOR,
    target: FastForecastTarget = FastForecastTarget.ENDPOINT_RETURN_BPS,
):
    bundle = chronological_bundle()
    request = forecast_request(family, target)
    runtime_artifact = train_fast_forecast_baseline(bundle, request)
    validation_run = run_fast_chronological_validation(
        bundle,
        request,
        chronological_policy(),
    )
    test_report = evaluate_fast_forecasts(
        bundle,
        validation_run,
        evaluation_contexts(validation_run),
        evaluation_policy(FastForecastEvaluationPartition.TEST),
    )
    return bundle, runtime_artifact, validation_run, test_report


def continuous_and_binary_sources():
    continuous = champion_source(
        FastForecastModelFamily.RIDGE_REGRESSION,
        FastForecastTarget.ENDPOINT_RETURN_BPS,
    )
    binary = champion_source(
        FastForecastModelFamily.LOGISTIC_REGRESSION,
        FastForecastTarget.REVERSAL_OCCURRED,
    )
    assert continuous[0].manifest.bundle_fingerprint_sha256 == binary[0].manifest.bundle_fingerprint_sha256
    return continuous, binary


def artifact_with_horizon(artifact, horizon_ms: int):
    provisional = replace(
        artifact,
        horizon_ms=horizon_ms,
        artifact_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        artifact_fingerprint_sha256=fast_forecast_artifact_fingerprint_sha256(provisional),
    )
