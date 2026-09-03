from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from fast_forecast_fixtures import feature_record, training_bundle
from shreks_brain.fast_learning.codec import (
    read_fast_forecast_artifact,
    write_fast_forecast_artifact,
)
from shreks_brain.fast_learning.inference import predict_fast_forecast
from shreks_brain.fast_learning.models import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_learning.trainer import train_fast_forecast_baseline


def request(
    family: FastForecastModelFamily,
    target: FastForecastTarget,
) -> FastForecastTrainingRequest:
    if family is FastForecastModelFamily.RIDGE_REGRESSION:
        policy = FastForecastTrainingPolicy(version="ridge-v1", ridge_alpha=1.0)
    elif family is FastForecastModelFamily.LOGISTIC_REGRESSION:
        policy = FastForecastTrainingPolicy(
            version="logit-v1",
            logistic_regularization_c=1.0,
            logistic_max_iterations=2_000,
            logistic_tolerance=1e-10,
            logistic_balanced_class_weight=False,
        )
    else:
        policy = FastForecastTrainingPolicy(version="naive-v1")
    return FastForecastTrainingRequest(
        model_version=f"{family.value.lower()}-{target.value}",
        model_family=family,
        target=target,
        horizon_ms=250,
        training_policy=policy,
    )


def test_naive_and_linear_reference_inference_is_finite_and_binary_is_probability() -> None:
    bundle = training_bundle()
    record = feature_record(3, 3.0)
    mean = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.MEAN_REGRESSOR, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    ridge = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.RIDGE_REGRESSION, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    prior = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.PRIOR_CLASSIFIER, FastForecastTarget.REVERSAL_OCCURRED),
    )
    logistic = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.LOGISTIC_REGRESSION, FastForecastTarget.REVERSAL_OCCURRED),
    )

    mean_prediction = predict_fast_forecast(mean, record)
    ridge_prediction = predict_fast_forecast(ridge, record)
    prior_prediction = predict_fast_forecast(prior, record)
    logistic_prediction = predict_fast_forecast(logistic, record)

    assert mean_prediction.predicted_value == pytest.approx(mean.constant_prediction)
    assert ridge_prediction.predicted_value == pytest.approx(ridge_prediction.predicted_value)
    assert prior_prediction.predicted_value == pytest.approx(0.5)
    assert 0.0 <= logistic_prediction.predicted_value <= 1.0
    assert logistic_prediction.decision_identity == record.decision_identity


def test_pure_python_inference_matches_manual_linear_and_sigmoid() -> None:
    import math

    bundle = training_bundle()
    record = feature_record(2, 2.0)
    ridge = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.RIDGE_REGRESSION, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    logistic = train_fast_forecast_baseline(
        bundle,
        request(FastForecastModelFamily.LOGISTIC_REGRESSION, FastForecastTarget.REVERSAL_OCCURRED),
    )
    from shreks_brain.fast_learning.features import (
        apply_feature_transforms,
        extract_fast_forecast_features,
    )

    raw = extract_fast_forecast_features(record)
    ridge_values = apply_feature_transforms(raw, ridge.feature_transforms)
    ridge_score = math.fsum(
        weight * value for weight, value in zip(ridge.coefficients, ridge_values, strict=True)
    ) + float(ridge.intercept)
    assert predict_fast_forecast(ridge, record).predicted_value == pytest.approx(ridge_score, abs=1e-12)

    logistic_values = apply_feature_transforms(raw, logistic.feature_transforms)
    score = math.fsum(
        weight * value for weight, value in zip(logistic.coefficients, logistic_values, strict=True)
    ) + float(logistic.intercept)
    expected = 1.0 / (1.0 + math.exp(-score))
    assert predict_fast_forecast(logistic, record).predicted_value == pytest.approx(expected, abs=1e-12)


def test_inference_module_imports_no_sklearn_or_numpy() -> None:
    script = (
        "import sys; import shreks_brain.fast_learning.inference; "
        "assert not any(k == 'sklearn' or k.startswith('sklearn.') for k in sys.modules); "
        "assert not any(k == 'numpy' or k.startswith('numpy.') for k in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


def test_artifact_codec_is_canonical_immutable_and_round_trips(tmp_path: Path) -> None:
    artifact = train_fast_forecast_baseline(
        training_bundle(),
        request(FastForecastModelFamily.RIDGE_REGRESSION, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_fast_forecast_artifact(artifact, first)
    write_fast_forecast_artifact(artifact, second)
    assert first.read_bytes() == second.read_bytes()
    assert read_fast_forecast_artifact(first) == artifact
    with pytest.raises(FileExistsError, match="exist|immutable|overwrite"):
        write_fast_forecast_artifact(artifact, first)

    payload = first.read_text(encoding="utf-8")
    assert payload.endswith("\n")
    for forbidden in ("pickle", "joblib", "sklearn.", "TradeIntent", "private_key", "enable_live"):
        assert forbidden not in payload


def test_codec_rejects_tampering_and_unknown_keys(tmp_path: Path) -> None:
    artifact = train_fast_forecast_baseline(
        training_bundle(),
        request(FastForecastModelFamily.MEAN_REGRESSOR, FastForecastTarget.ENDPOINT_RETURN_BPS),
    )
    path = tmp_path / "artifact.json"
    write_fast_forecast_artifact(artifact, path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["constant_prediction"] = float(value["constant_prediction"]) + 1.0
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint|artifact"):
        read_fast_forecast_artifact(path)

    value["unknown"] = 1
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="keys|schema|artifact"):
        read_fast_forecast_artifact(path)
