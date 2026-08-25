from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from shreks_brain.learning import (
    MODEL_TRAINING_SCHEMA_VERSION,
    FeatureTransform,
    ModelFamily,
    ResearchReturnTarget,
    TrainedLogisticRegressionModel,
)
from shreks_brain.learning.codec import build_artifact_document, canonical_json
from shreks_brain.learning.store import ModelArtifactStore
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


def test_missing_store_loads_empty_and_get_returns_none(tmp_path: Path) -> None:
    store = ModelArtifactStore(tmp_path / "models.json")

    assert store.load() == ()
    assert store.get("missing") is None


def test_append_round_trips_after_restart_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    model = _model()

    first = ModelArtifactStore(path).append(model)
    second = ModelArtifactStore(path).append(model)

    assert first == (model,)
    assert second == (model,)
    assert ModelArtifactStore(path).load() == (model,)
    assert ModelArtifactStore(path).get(model.model_version) == model


def test_append_preserves_artifact_order_across_multiple_models(tmp_path: Path) -> None:
    store = ModelArtifactStore(tmp_path / "models.json")
    first = _model(model_version="challenger-v1")
    second = replace(
        _model(model_version="challenger-v2"),
        intercept=0.2,
        training_fingerprint_sha256="b" * 64,
    )

    assert store.append(first) == (first,)
    assert store.append(second) == (first, second)
    assert ModelArtifactStore(store.path).load() == (first, second)


def test_same_version_with_different_content_fails_closed(tmp_path: Path) -> None:
    store = ModelArtifactStore(tmp_path / "models.json")
    model = _model()
    store.append(model)

    with pytest.raises(ValueError, match="already stored with different content"):
        store.append(replace(model, intercept=model.intercept + 0.1))

    assert store.load() == (model,)


def test_store_writes_canonical_newline_and_leaves_no_tmp(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "models.json"
    model = _model()

    ModelArtifactStore(path).append(model)

    text = path.read_text(encoding="utf-8")
    assert text == canonical_json(build_artifact_document((model,))) + "\n"
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert not path.with_name(path.name + ".tmp").exists()


def test_load_wraps_malformed_json_as_invalid_artifact_file(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="model artifact file is invalid"):
        ModelArtifactStore(path).load()


def test_load_rejects_tampered_persisted_model(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    ModelArtifactStore(path).append(_model())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["artifacts"][0]["model"]["intercept"] = 999.0
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact fingerprint"):
        ModelArtifactStore(path).load()


def test_get_requires_non_empty_model_version(tmp_path: Path) -> None:
    store = ModelArtifactStore(tmp_path / "models.json")

    for invalid in ("", "   ", 123, None):
        with pytest.raises(ValueError, match="model_version"):
            store.get(invalid)  # type: ignore[arg-type]


def test_append_requires_exact_model_type(tmp_path: Path) -> None:
    store = ModelArtifactStore(tmp_path / "models.json")

    with pytest.raises(ValueError, match="TrainedLogisticRegressionModel"):
        store.append(object())  # type: ignore[arg-type]


def test_replace_failure_cleans_tmp_and_preserves_previous_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "models.json"
    store = ModelArtifactStore(path)
    first = _model(model_version="challenger-v1")
    second = replace(
        _model(model_version="challenger-v2"),
        intercept=0.2,
        training_fingerprint_sha256="b" * 64,
    )
    store.append(first)

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("shreks_brain.learning.store.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        store.append(second)

    assert not path.with_name(path.name + ".tmp").exists()
    assert ModelArtifactStore(path).load() == (first,)
