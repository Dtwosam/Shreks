from __future__ import annotations

import hashlib
import json
import string
from typing import Mapping

from .models import (
    FeatureTransform,
    ModelFamily,
    ResearchReturnTarget,
    TrainedLogisticRegressionModel,
)


MODEL_ARTIFACT_STORE_SCHEMA_VERSION = "e9-model-artifacts-v1"

_DOCUMENT_FIELDS = frozenset({"schema_version", "artifacts"})
_ARTIFACT_FIELDS = frozenset({"artifact_fingerprint_sha256", "model"})
_MODEL_FIELDS = frozenset(
    {
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
)
_TARGET_FIELDS = frozenset({"horizon_seconds", "minimum_return_pct"})
_TRANSFORM_FIELDS = frozenset(
    {"feature_name", "imputation_median", "mean", "scale"}
)


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"value is not canonical-JSON serializable: {error}"
        ) from error


def model_to_dict(model: TrainedLogisticRegressionModel) -> dict[str, object]:
    if type(model) is not TrainedLogisticRegressionModel:
        raise ValueError("model must be an exact TrainedLogisticRegressionModel")
    return {
        "schema_version": model.schema_version,
        "model_version": model.model_version,
        "model_family": model.model_family.value,
        "training_policy_version": model.training_policy_version,
        "research_dataset_schema_version": model.research_dataset_schema_version,
        "target": {
            "horizon_seconds": model.target.horizon_seconds,
            "minimum_return_pct": model.target.minimum_return_pct,
        },
        "feature_transforms": [
            {
                "feature_name": transform.feature_name,
                "imputation_median": transform.imputation_median,
                "mean": transform.mean,
                "scale": transform.scale,
            }
            for transform in model.feature_transforms
        ],
        "coefficients": list(model.coefficients),
        "intercept": model.intercept,
        "training_row_count": model.training_row_count,
        "positive_row_count": model.positive_row_count,
        "negative_row_count": model.negative_row_count,
        "target_unavailable_row_count": model.target_unavailable_row_count,
        "min_training_as_of_unix_ms": model.min_training_as_of_unix_ms,
        "max_training_as_of_unix_ms": model.max_training_as_of_unix_ms,
        "training_fingerprint_sha256": model.training_fingerprint_sha256,
    }


def compute_artifact_fingerprint(model: TrainedLogisticRegressionModel) -> str:
    payload = canonical_json(model_to_dict(model)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_artifact_document(
    models: tuple[TrainedLogisticRegressionModel, ...],
) -> dict[str, object]:
    if not isinstance(models, tuple):
        raise ValueError("models must be a tuple")
    seen_versions: set[str] = set()
    artifacts: list[dict[str, object]] = []
    for model in models:
        if type(model) is not TrainedLogisticRegressionModel:
            raise ValueError(
                "models must contain exact TrainedLogisticRegressionModel values"
            )
        if model.model_version in seen_versions:
            raise ValueError("model artifact catalog contains duplicate model_version")
        seen_versions.add(model.model_version)
        artifacts.append(
            {
                "artifact_fingerprint_sha256": compute_artifact_fingerprint(model),
                "model": model_to_dict(model),
            }
        )
    return {
        "schema_version": MODEL_ARTIFACT_STORE_SCHEMA_VERSION,
        "artifacts": artifacts,
    }


def decode_artifact_document(
    document: object,
) -> tuple[TrainedLogisticRegressionModel, ...]:
    mapping = _require_exact_mapping(
        "model artifact document", document, _DOCUMENT_FIELDS
    )
    if mapping["schema_version"] != MODEL_ARTIFACT_STORE_SCHEMA_VERSION:
        raise ValueError(
            "model artifact document schema_version must equal "
            f"{MODEL_ARTIFACT_STORE_SCHEMA_VERSION}"
        )
    raw_artifacts = mapping["artifacts"]
    if not isinstance(raw_artifacts, list):
        raise ValueError("artifacts must be a list")

    models: list[TrainedLogisticRegressionModel] = []
    seen_versions: set[str] = set()
    for raw_artifact in raw_artifacts:
        artifact = _require_exact_mapping(
            "model artifact", raw_artifact, _ARTIFACT_FIELDS
        )
        stored_fingerprint = artifact["artifact_fingerprint_sha256"]
        _require_sha256("artifact_fingerprint_sha256", stored_fingerprint)
        model = _decode_model(artifact["model"])
        if model.model_version in seen_versions:
            raise ValueError("model artifact catalog contains duplicate model_version")
        seen_versions.add(model.model_version)
        expected_fingerprint = compute_artifact_fingerprint(model)
        if stored_fingerprint != expected_fingerprint:
            raise ValueError(
                "artifact fingerprint does not match persisted model content"
            )
        models.append(model)
    return tuple(models)


def _decode_model(value: object) -> TrainedLogisticRegressionModel:
    mapping = _require_exact_mapping("model", value, _MODEL_FIELDS)

    try:
        model_family = ModelFamily(mapping["model_family"])
    except (TypeError, ValueError) as error:
        raise ValueError("model_family contains an unsupported enum value") from error

    target_mapping = _require_exact_mapping(
        "target", mapping["target"], _TARGET_FIELDS
    )
    target = ResearchReturnTarget(
        horizon_seconds=target_mapping["horizon_seconds"],  # type: ignore[arg-type]
        minimum_return_pct=target_mapping["minimum_return_pct"],  # type: ignore[arg-type]
    )

    raw_transforms = mapping["feature_transforms"]
    if not isinstance(raw_transforms, list):
        raise ValueError("feature_transforms must be a list")
    transforms: list[FeatureTransform] = []
    for raw_transform in raw_transforms:
        transform_mapping = _require_exact_mapping(
            "feature transform", raw_transform, _TRANSFORM_FIELDS
        )
        transforms.append(
            FeatureTransform(
                feature_name=transform_mapping["feature_name"],  # type: ignore[arg-type]
                imputation_median=transform_mapping["imputation_median"],  # type: ignore[arg-type]
                mean=transform_mapping["mean"],  # type: ignore[arg-type]
                scale=transform_mapping["scale"],  # type: ignore[arg-type]
            )
        )

    raw_coefficients = mapping["coefficients"]
    if not isinstance(raw_coefficients, list):
        raise ValueError("coefficients must be a list")

    return TrainedLogisticRegressionModel(
        schema_version=mapping["schema_version"],  # type: ignore[arg-type]
        model_version=mapping["model_version"],  # type: ignore[arg-type]
        model_family=model_family,
        training_policy_version=mapping["training_policy_version"],  # type: ignore[arg-type]
        research_dataset_schema_version=mapping[
            "research_dataset_schema_version"
        ],  # type: ignore[arg-type]
        target=target,
        feature_transforms=tuple(transforms),
        coefficients=tuple(raw_coefficients),  # type: ignore[arg-type]
        intercept=mapping["intercept"],  # type: ignore[arg-type]
        training_row_count=mapping["training_row_count"],  # type: ignore[arg-type]
        positive_row_count=mapping["positive_row_count"],  # type: ignore[arg-type]
        negative_row_count=mapping["negative_row_count"],  # type: ignore[arg-type]
        target_unavailable_row_count=mapping[
            "target_unavailable_row_count"
        ],  # type: ignore[arg-type]
        min_training_as_of_unix_ms=mapping[
            "min_training_as_of_unix_ms"
        ],  # type: ignore[arg-type]
        max_training_as_of_unix_ms=mapping[
            "max_training_as_of_unix_ms"
        ],  # type: ignore[arg-type]
        training_fingerprint_sha256=mapping[
            "training_fingerprint_sha256"
        ],  # type: ignore[arg-type]
    )


def _require_exact_mapping(
    name: str,
    value: object,
    expected_fields: frozenset[str],
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if frozenset(value) != expected_fields or len(value) != len(expected_fields):
        raise ValueError(f"{name} fields must match the sealed schema exactly")
    return value


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(
            f"{name} must be a 64-character lowercase SHA-256 hex digest"
        )
