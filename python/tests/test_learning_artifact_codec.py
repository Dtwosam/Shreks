from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math

import pytest

from shreks_brain.learning import (
    MODEL_TRAINING_SCHEMA_VERSION,
    FeatureTransform,
    ModelFamily,
    ResearchReturnTarget,
    TrainedLogisticRegressionModel,
)
from shreks_brain.learning.codec import (
    MODEL_ARTIFACT_STORE_SCHEMA_VERSION,
    build_artifact_document,
    canonical_json,
    compute_artifact_fingerprint,
    decode_artifact_document,
    model_to_dict,
)
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
)


def _model(*, model_version: str = "challenger-v1") -> TrainedLogisticRegressionModel:
    return TrainedLogisticRegressionModel(
        schema_version=MODEL_TRAINING_SCHEMA_VERSION,
        model_version=model_version,
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        training_policy_version="training-policy-v1",
        research_dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        target=ResearchReturnTarget(
            horizon_seconds=RESEARCH_OUTCOME_HORIZONS_SECONDS[0],
            minimum_return_pct=5.0,
        ),
        feature_transforms=(
            FeatureTransform(
                feature_name="total_score",
                imputation_median=50.0,
                mean=52.0,
                scale=10.0,
            ),
            FeatureTransform(
                feature_name="liquidity_usd",
                imputation_median=10_000.0,
                mean=12_000.0,
                scale=3_000.0,
            ),
        ),
        coefficients=(0.75, -0.25),
        intercept=0.1,
        training_row_count=20,
        positive_row_count=8,
        negative_row_count=12,
        target_unavailable_row_count=3,
        min_training_as_of_unix_ms=1_000,
        max_training_as_of_unix_ms=2_000,
        training_fingerprint_sha256="a" * 64,
    )


def _document() -> dict[str, object]:
    return build_artifact_document((_model(),))


def _artifact(document: dict[str, object]) -> dict[str, object]:
    artifacts = document["artifacts"]
    assert isinstance(artifacts, list)
    artifact = artifacts[0]
    assert isinstance(artifact, dict)
    return artifact


def _model_mapping(document: dict[str, object]) -> dict[str, object]:
    model = _artifact(document)["model"]
    assert isinstance(model, dict)
    return model


def test_model_artifact_document_round_trips_exact_model() -> None:
    model = _model()

    document = build_artifact_document((model,))

    assert document["schema_version"] == MODEL_ARTIFACT_STORE_SCHEMA_VERSION
    assert decode_artifact_document(document) == (model,)


def test_model_to_dict_contains_exact_e3_portable_fields() -> None:
    mapping = model_to_dict(_model())

    assert set(mapping) == {
        "schema_version",
        "model_version",
        "model_family",
        "training_policy_version",
        "research_dataset_schema_version",
        "target",
        "feature_transforms",
        "coefficients",
        "intercept",
        "training_row_count",
        "positive_row_count",
        "negative_row_count",
        "target_unavailable_row_count",
        "min_training_as_of_unix_ms",
        "max_training_as_of_unix_ms",
        "training_fingerprint_sha256",
    }
    assert mapping["model_family"] == ModelFamily.LOGISTIC_REGRESSION.value
    assert mapping["coefficients"] == [0.75, -0.25]
    assert mapping["target"] == {
        "horizon_seconds": RESEARCH_OUTCOME_HORIZONS_SECONDS[0],
        "minimum_return_pct": 5.0,
    }


def test_artifact_fingerprint_covers_fitted_model_content() -> None:
    model = _model()

    changed_intercept = replace(model, intercept=model.intercept + 0.25)
    changed_coefficient = replace(model, coefficients=(0.76, -0.25))
    changed_transform = replace(
        model,
        feature_transforms=(
            replace(model.feature_transforms[0], mean=53.0),
            model.feature_transforms[1],
        ),
    )

    original = compute_artifact_fingerprint(model)
    assert compute_artifact_fingerprint(changed_intercept) != original
    assert compute_artifact_fingerprint(changed_coefficient) != original
    assert compute_artifact_fingerprint(changed_transform) != original


def test_decode_rejects_tampered_model_with_stale_artifact_fingerprint() -> None:
    document = _document()
    model = _model_mapping(document)
    model["intercept"] = 999.0

    with pytest.raises(ValueError, match="artifact fingerprint"):
        decode_artifact_document(document)


def test_decode_rejects_unknown_top_level_fields() -> None:
    document = _document()
    document["unknown"] = True

    with pytest.raises(ValueError, match="fields"):
        decode_artifact_document(document)


def test_decode_rejects_unknown_artifact_wrapper_fields() -> None:
    document = _document()
    _artifact(document)["unknown"] = True

    with pytest.raises(ValueError, match="fields"):
        decode_artifact_document(document)


def test_decode_rejects_unknown_model_fields() -> None:
    document = _document()
    _model_mapping(document)["unknown"] = True

    with pytest.raises(ValueError, match="fields"):
        decode_artifact_document(document)


def test_decode_rejects_unknown_target_fields() -> None:
    document = _document()
    target = _model_mapping(document)["target"]
    assert isinstance(target, dict)
    target["unknown"] = True

    with pytest.raises(ValueError, match="fields"):
        decode_artifact_document(document)


def test_decode_rejects_unknown_transform_fields() -> None:
    document = _document()
    transforms = _model_mapping(document)["feature_transforms"]
    assert isinstance(transforms, list)
    transform = transforms[0]
    assert isinstance(transform, dict)
    transform["unknown"] = True

    with pytest.raises(ValueError, match="fields"):
        decode_artifact_document(document)


def test_decode_rejects_wrong_store_schema_version() -> None:
    document = _document()
    document["schema_version"] = "wrong"

    with pytest.raises(ValueError, match="schema"):
        decode_artifact_document(document)


def test_decode_rejects_unsupported_model_family() -> None:
    document = _document()
    _model_mapping(document)["model_family"] = "RANDOM_FOREST"

    with pytest.raises(ValueError, match="enum|model_family|LOGISTIC"):
        decode_artifact_document(document)


def test_decode_rejects_wrong_container_types() -> None:
    document = _document()
    document["artifacts"] = {}
    with pytest.raises(ValueError, match="artifacts"):
        decode_artifact_document(document)

    document = _document()
    _model_mapping(document)["coefficients"] = {"0": 0.75}
    with pytest.raises(ValueError, match="coefficients"):
        decode_artifact_document(document)

    document = _document()
    _model_mapping(document)["feature_transforms"] = {}
    with pytest.raises(ValueError, match="feature_transforms"):
        decode_artifact_document(document)


def test_decode_rejects_non_finite_model_values() -> None:
    for value in (math.nan, math.inf, -math.inf):
        document = _document()
        _model_mapping(document)["intercept"] = value
        with pytest.raises(ValueError, match="finite"):
            decode_artifact_document(document)


def test_decode_rejects_invalid_artifact_fingerprint_shape() -> None:
    document = _document()
    _artifact(document)["artifact_fingerprint_sha256"] = "not-a-sha"

    with pytest.raises(ValueError, match="SHA-256|fingerprint"):
        decode_artifact_document(document)


def test_decode_rejects_duplicate_model_versions() -> None:
    first = _document()
    second = build_artifact_document((replace(_model(), intercept=0.2),))
    first_artifacts = first["artifacts"]
    second_artifacts = second["artifacts"]
    assert isinstance(first_artifacts, list)
    assert isinstance(second_artifacts, list)
    first_artifacts.extend(deepcopy(second_artifacts))

    with pytest.raises(ValueError, match="duplicate|model_version"):
        decode_artifact_document(first)


def test_empty_artifact_document_round_trips() -> None:
    document = build_artifact_document(())

    assert document == {
        "schema_version": MODEL_ARTIFACT_STORE_SCHEMA_VERSION,
        "artifacts": [],
    }
    assert decode_artifact_document(document) == ()


def test_canonical_json_is_compact_sorted_utf8_and_rejects_nan() -> None:
    assert canonical_json({"b": 2, "a": "é"}) == '{"a":"é","b":2}'

    with pytest.raises(ValueError, match="canonical-JSON"):
        canonical_json({"x": math.nan})
