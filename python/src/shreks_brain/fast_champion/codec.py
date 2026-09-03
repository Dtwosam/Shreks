from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from shreks_brain.fast_learning.features import FastForecastFeatureTransform
from shreks_brain.fast_learning.models import (
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTargetKind,
    artifact_to_mapping,
    fast_forecast_artifact_fingerprint_sha256,
)

from .models import (
    FAST_FORECAST_CHAMPION_SCHEMA_NAME,
    FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
    FastForecastChampionArtifact,
    FastForecastChampionMember,
    FastForecastChampionSelection,
    fast_forecast_champion_fingerprint_sha256,
)


_CHAMPION_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "champion_version",
        "selection",
        "feature_schema_version",
        "training_bundle_fingerprint_sha256",
        "future_path_label_version",
        "members",
        "champion_fingerprint_sha256",
    }
)
_SELECTION_KEYS = frozenset(
    {"decision_reference", "decided_at_unix_ms", "reason"}
)
_MEMBER_KEYS = frozenset(
    {
        "member_key",
        "forecast_artifact",
        "validation_policy_version",
        "validation_run_fingerprint_sha256",
        "test_evaluation_policy_version",
        "test_evaluation_report_fingerprint_sha256",
        "test_scored_observation_count",
        "test_target_unavailable_count",
    }
)
_ARTIFACT_KEYS = frozenset(
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
_TRANSFORM_KEYS = frozenset(
    {"feature_name", "imputation_median", "mean", "scale"}
)


def write_fast_forecast_champion(
    champion: FastForecastChampionArtifact,
    path: str | Path,
) -> None:
    if type(champion) is not FastForecastChampionArtifact:
        raise ValueError("champion must be an exact FastForecastChampionArtifact")
    _verify_embedded_artifacts(champion)
    expected = fast_forecast_champion_fingerprint_sha256(champion)
    if expected != champion.champion_fingerprint_sha256:
        raise ValueError("forecast champion fingerprint is inconsistent before write")

    destination = Path(path)
    if destination.exists():
        raise FileExistsError("forecast champion destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            _champion_payload(champion),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def read_fast_forecast_champion(
    path: str | Path,
) -> FastForecastChampionArtifact:
    source = Path(path)
    if not source.is_file():
        raise ValueError("forecast champion source must be an existing file")
    try:
        raw = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("forecast champion JSON is unreadable or invalid") from exc

    mapping = _exact_mapping("forecast champion", raw, _CHAMPION_KEYS)
    selection = _selection_from_payload(mapping["selection"])
    raw_members = mapping["members"]
    if not isinstance(raw_members, list) or not raw_members:
        raise ValueError("forecast champion members must be a non-empty list")
    members = tuple(_member_from_payload(value) for value in raw_members)

    try:
        champion = FastForecastChampionArtifact(
            schema_name=mapping["schema_name"],  # type: ignore[arg-type]
            schema_version=mapping["schema_version"],  # type: ignore[arg-type]
            champion_version=mapping["champion_version"],  # type: ignore[arg-type]
            selection=selection,
            feature_schema_version=mapping["feature_schema_version"],  # type: ignore[arg-type]
            training_bundle_fingerprint_sha256=mapping[
                "training_bundle_fingerprint_sha256"
            ],  # type: ignore[arg-type]
            future_path_label_version=mapping["future_path_label_version"],  # type: ignore[arg-type]
            members=members,
            champion_fingerprint_sha256=mapping[
                "champion_fingerprint_sha256"
            ],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("forecast champion content is incompatible") from exc

    _verify_embedded_artifacts(champion)
    expected = fast_forecast_champion_fingerprint_sha256(champion)
    if expected != champion.champion_fingerprint_sha256:
        raise ValueError("forecast champion fingerprint is invalid or tampered")
    return champion


def _champion_payload(champion: FastForecastChampionArtifact) -> dict[str, object]:
    return {
        "schema_name": champion.schema_name,
        "schema_version": champion.schema_version,
        "champion_version": champion.champion_version,
        "selection": {
            "decision_reference": champion.selection.decision_reference,
            "decided_at_unix_ms": champion.selection.decided_at_unix_ms,
            "reason": champion.selection.reason,
        },
        "feature_schema_version": champion.feature_schema_version,
        "training_bundle_fingerprint_sha256": (
            champion.training_bundle_fingerprint_sha256
        ),
        "future_path_label_version": champion.future_path_label_version,
        "members": [_member_payload(value) for value in champion.members],
        "champion_fingerprint_sha256": champion.champion_fingerprint_sha256,
    }


def _member_payload(member: FastForecastChampionMember) -> dict[str, object]:
    return {
        "member_key": member.member_key,
        "forecast_artifact": artifact_to_mapping(member.forecast_artifact),
        "validation_policy_version": member.validation_policy_version,
        "validation_run_fingerprint_sha256": (
            member.validation_run_fingerprint_sha256
        ),
        "test_evaluation_policy_version": member.test_evaluation_policy_version,
        "test_evaluation_report_fingerprint_sha256": (
            member.test_evaluation_report_fingerprint_sha256
        ),
        "test_scored_observation_count": member.test_scored_observation_count,
        "test_target_unavailable_count": member.test_target_unavailable_count,
    }


def _selection_from_payload(value: object) -> FastForecastChampionSelection:
    mapping = _exact_mapping("forecast champion selection", value, _SELECTION_KEYS)
    try:
        return FastForecastChampionSelection(
            decision_reference=mapping["decision_reference"],  # type: ignore[arg-type]
            decided_at_unix_ms=mapping["decided_at_unix_ms"],  # type: ignore[arg-type]
            reason=mapping["reason"],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("forecast champion selection is incompatible") from exc


def _member_from_payload(value: object) -> FastForecastChampionMember:
    mapping = _exact_mapping("forecast champion member", value, _MEMBER_KEYS)
    artifact = _artifact_from_payload(mapping["forecast_artifact"])
    try:
        return FastForecastChampionMember(
            member_key=mapping["member_key"],  # type: ignore[arg-type]
            forecast_artifact=artifact,
            validation_policy_version=mapping[
                "validation_policy_version"
            ],  # type: ignore[arg-type]
            validation_run_fingerprint_sha256=mapping[
                "validation_run_fingerprint_sha256"
            ],  # type: ignore[arg-type]
            test_evaluation_policy_version=mapping[
                "test_evaluation_policy_version"
            ],  # type: ignore[arg-type]
            test_evaluation_report_fingerprint_sha256=mapping[
                "test_evaluation_report_fingerprint_sha256"
            ],  # type: ignore[arg-type]
            test_scored_observation_count=mapping[
                "test_scored_observation_count"
            ],  # type: ignore[arg-type]
            test_target_unavailable_count=mapping[
                "test_target_unavailable_count"
            ],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("forecast champion member is incompatible") from exc


def _artifact_from_payload(value: object) -> FastForecastBaselineArtifact:
    mapping = _exact_mapping("embedded forecast artifact", value, _ARTIFACT_KEYS)
    try:
        family = FastForecastModelFamily(mapping["model_family"])
        target = FastForecastTarget(mapping["target"])
        target_kind = FastForecastTargetKind(mapping["target_kind"])
    except (TypeError, ValueError) as exc:
        raise ValueError("embedded forecast artifact enum is incompatible") from exc

    raw_transforms = mapping["feature_transforms"]
    if not isinstance(raw_transforms, list):
        raise ValueError("embedded forecast artifact transforms must be a list")
    transforms: list[FastForecastFeatureTransform] = []
    for raw_transform in raw_transforms:
        transform = _exact_mapping(
            "embedded forecast feature transform",
            raw_transform,
            _TRANSFORM_KEYS,
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
            raise ValueError("embedded forecast feature transform is incompatible") from exc

    raw_coefficients = mapping["coefficients"]
    if not isinstance(raw_coefficients, list):
        raise ValueError("embedded forecast artifact coefficients must be a list")

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
        raise ValueError("embedded forecast artifact content is incompatible") from exc

    expected = fast_forecast_artifact_fingerprint_sha256(artifact)
    if expected != artifact.artifact_fingerprint_sha256:
        raise ValueError("embedded forecast artifact fingerprint is invalid or tampered")
    return artifact


def _verify_embedded_artifacts(champion: FastForecastChampionArtifact) -> None:
    for member in champion.members:
        artifact = member.forecast_artifact
        expected = fast_forecast_artifact_fingerprint_sha256(artifact)
        if expected != artifact.artifact_fingerprint_sha256:
            raise ValueError("embedded forecast artifact fingerprint is inconsistent")


def _exact_mapping(
    name: str,
    value: object,
    keys: frozenset[str],
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if frozenset(value) != keys or len(value) != len(keys):
        raise ValueError(f"{name} keys must match the sealed schema exactly")
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
