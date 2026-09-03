from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .features import FastForecastFeatureTransform
from .models import (
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTargetKind,
    artifact_to_mapping,
    fast_forecast_artifact_fingerprint_sha256,
)


_ARTIFACT_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "model_version",
        "model_family",
        "target",
        "target_kind",
        "horizon_ms",
        "feature_schema_version",
        "training_policy_version",
        "training_bundle_fingerprint_sha256",
        "future_path_label_version",
        "training_row_count",
        "target_unavailable_row_count",
        "positive_row_count",
        "negative_row_count",
        "min_training_decision_observed_at_unix_ms",
        "max_training_decision_observed_at_unix_ms",
        "training_data_fingerprint_sha256",
        "feature_transforms",
        "coefficients",
        "intercept",
        "constant_prediction",
        "artifact_fingerprint_sha256",
    }
)
_TRANSFORM_FIELDS = frozenset(
    {"feature_name", "imputation_median", "mean", "scale"}
)


def write_fast_forecast_artifact(
    artifact: FastForecastBaselineArtifact,
    path: str | Path,
) -> None:
    if type(artifact) is not FastForecastBaselineArtifact:
        raise ValueError("artifact must be an exact FastForecastBaselineArtifact")
    expected = fast_forecast_artifact_fingerprint_sha256(artifact)
    if expected != artifact.artifact_fingerprint_sha256:
        raise ValueError("forecast artifact fingerprint does not match artifact content")
    destination = Path(path)
    if destination.exists():
        raise FileExistsError("forecast artifact destination already exists; artifacts are immutable")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        _canonical_json(artifact_to_mapping(artifact)) + "\n",
        encoding="utf-8",
    )


def read_fast_forecast_artifact(path: str | Path) -> FastForecastBaselineArtifact:
    source = Path(path)
    if not source.is_file():
        raise ValueError("forecast artifact path must be an existing file")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("forecast artifact is unreadable or invalid JSON") from exc
    mapping = _require_exact_mapping("forecast artifact", raw, _ARTIFACT_FIELDS)

    try:
        family = FastForecastModelFamily(mapping["model_family"])
        target = FastForecastTarget(mapping["target"])
        target_kind = FastForecastTargetKind(mapping["target_kind"])
    except (TypeError, ValueError) as exc:
        raise ValueError("forecast artifact enum value is incompatible") from exc

    raw_transforms = mapping["feature_transforms"]
    if not isinstance(raw_transforms, list):
        raise ValueError("forecast artifact feature_transforms must be a list")
    transforms: list[FastForecastFeatureTransform] = []
    for raw_transform in raw_transforms:
        transform = _require_exact_mapping(
            "forecast feature transform", raw_transform, _TRANSFORM_FIELDS
        )
        try:
            transforms.append(
                FastForecastFeatureTransform(
                    feature_name=transform["feature_name"],  # type: ignore[arg-type]
                    imputation_median=transform["imputation_median"],  # type: ignore[arg-type]
                    mean=transform["mean"],  # type: ignore[arg-type]
                    scale=transform["scale"],  # type: ignore[arg-type]
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("forecast feature transform is incompatible") from exc

    raw_coefficients = mapping["coefficients"]
    if not isinstance(raw_coefficients, list):
        raise ValueError("forecast artifact coefficients must be a list")

    try:
        artifact = FastForecastBaselineArtifact(
            schema_name=mapping["schema_name"],  # type: ignore[arg-type]
            schema_version=mapping["schema_version"],  # type: ignore[arg-type]
            model_version=mapping["model_version"],  # type: ignore[arg-type]
            model_family=family,
            target=target,
            target_kind=target_kind,
            horizon_ms=mapping["horizon_ms"],  # type: ignore[arg-type]
            feature_schema_version=mapping["feature_schema_version"],  # type: ignore[arg-type]
            training_policy_version=mapping["training_policy_version"],  # type: ignore[arg-type]
            training_bundle_fingerprint_sha256=mapping[
                "training_bundle_fingerprint_sha256"
            ],  # type: ignore[arg-type]
            future_path_label_version=mapping["future_path_label_version"],  # type: ignore[arg-type]
            training_row_count=mapping["training_row_count"],  # type: ignore[arg-type]
            target_unavailable_row_count=mapping[
                "target_unavailable_row_count"
            ],  # type: ignore[arg-type]
            positive_row_count=mapping["positive_row_count"],  # type: ignore[arg-type]
            negative_row_count=mapping["negative_row_count"],  # type: ignore[arg-type]
            min_training_decision_observed_at_unix_ms=mapping[
                "min_training_decision_observed_at_unix_ms"
            ],  # type: ignore[arg-type]
            max_training_decision_observed_at_unix_ms=mapping[
                "max_training_decision_observed_at_unix_ms"
            ],  # type: ignore[arg-type]
            training_data_fingerprint_sha256=mapping[
                "training_data_fingerprint_sha256"
            ],  # type: ignore[arg-type]
            feature_transforms=tuple(transforms),
            coefficients=tuple(raw_coefficients),  # type: ignore[arg-type]
            intercept=mapping["intercept"],  # type: ignore[arg-type]
            constant_prediction=mapping["constant_prediction"],  # type: ignore[arg-type]
            artifact_fingerprint_sha256=mapping[
                "artifact_fingerprint_sha256"
            ],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("forecast artifact content is incompatible") from exc

    expected = fast_forecast_artifact_fingerprint_sha256(artifact)
    if expected != artifact.artifact_fingerprint_sha256:
        raise ValueError("forecast artifact fingerprint does not match artifact content")
    return artifact


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("forecast artifact is not canonical-JSON serializable") from exc


def _require_exact_mapping(
    name: str,
    value: object,
    fields: frozenset[str],
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if frozenset(value) != fields or len(value) != len(fields):
        raise ValueError(f"{name} keys must match the sealed schema exactly")
    return value
