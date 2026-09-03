from __future__ import annotations

import math

from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord

from .features import apply_feature_transforms, extract_fast_forecast_features
from .models import (
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastPrediction,
    FastForecastTargetKind,
    fast_forecast_artifact_fingerprint_sha256,
)


def predict_fast_forecast(
    artifact: FastForecastBaselineArtifact,
    record: FastTrainingFeatureRecord,
) -> FastForecastPrediction:
    if type(artifact) is not FastForecastBaselineArtifact:
        raise ValueError("artifact must be an exact FastForecastBaselineArtifact")
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be an exact FastTrainingFeatureRecord")
    if (
        fast_forecast_artifact_fingerprint_sha256(artifact)
        != artifact.artifact_fingerprint_sha256
    ):
        raise ValueError("forecast artifact fingerprint does not match artifact content")

    if artifact.model_family in {
        FastForecastModelFamily.MEAN_REGRESSOR,
        FastForecastModelFamily.PRIOR_CLASSIFIER,
    }:
        if artifact.constant_prediction is None:
            raise ValueError("naive forecast artifact is missing its constant prediction")
        predicted = float(artifact.constant_prediction)
    else:
        if artifact.intercept is None:
            raise ValueError("trained forecast artifact is missing its intercept")
        raw = extract_fast_forecast_features(record)
        transformed = apply_feature_transforms(raw, artifact.feature_transforms)
        if len(artifact.coefficients) != len(transformed):
            raise ValueError("forecast artifact coefficient dimensions are incompatible")
        score = math.fsum(
            weight * value
            for weight, value in zip(
                artifact.coefficients, transformed, strict=True
            )
        ) + artifact.intercept
        if not math.isfinite(score):
            raise ValueError("forecast linear score is non-finite")
        if artifact.model_family is FastForecastModelFamily.LOGISTIC_REGRESSION:
            predicted = _stable_sigmoid(score)
        elif artifact.model_family is FastForecastModelFamily.RIDGE_REGRESSION:
            predicted = float(score)
        else:  # pragma: no cover - artifact validation keeps this unreachable.
            raise ValueError("forecast artifact model family is unsupported")

    if not math.isfinite(predicted):
        raise ValueError("forecast prediction must be finite")
    if artifact.target_kind is FastForecastTargetKind.BINARY and not (
        0.0 <= predicted <= 1.0
    ):
        raise ValueError("binary forecast prediction must be within [0, 1]")
    return FastForecastPrediction(
        model_version=artifact.model_version,
        target=artifact.target,
        horizon_ms=artifact.horizon_ms,
        decision_identity=record.decision_identity,
        predicted_value=float(predicted),
    )


def _stable_sigmoid(score: float) -> float:
    if score >= 0.0:
        z = math.exp(-score)
        return 1.0 / (1.0 + z)
    z = math.exp(score)
    return z / (1.0 + z)
