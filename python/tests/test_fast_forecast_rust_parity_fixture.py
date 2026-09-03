from __future__ import annotations

import json
import math
from pathlib import Path

from shreks_brain.fast_champion.codec import (
    read_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_champion.models import (
    FAST_FORECAST_CHAMPION_SCHEMA_NAME,
    FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
    FastForecastChampionArtifact,
    FastForecastChampionMember,
    FastForecastChampionSelection,
    fast_forecast_champion_fingerprint_sha256,
)
from shreks_brain.fast_learning.features import (
    FAST_FORECAST_FEATURE_NAMES,
    FastForecastFeatureTransform,
    apply_feature_transforms,
)
from shreks_brain.fast_learning.inference import _stable_sigmoid
from shreks_brain.fast_learning.models import (
    FAST_FORECAST_ARTIFACT_SCHEMA_NAME,
    FAST_FORECAST_ARTIFACT_SCHEMA_VERSION,
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTargetKind,
    fast_forecast_artifact_fingerprint_sha256,
)


_SPEC_PATH = (
    Path(__file__).resolve().parents[2]
    / "crates"
    / "shreks-core"
    / "tests"
    / "fixtures"
    / "fl8_6_parity_spec.json"
)


def _spec() -> dict[str, object]:
    return json.loads(_SPEC_PATH.read_text(encoding="utf-8"))


def _artifact(model: dict[str, object], common: dict[str, object]) -> FastForecastBaselineArtifact:
    family = FastForecastModelFamily(model["model_family"])
    target = FastForecastTarget(model["target"])
    target_kind = FastForecastTargetKind(model["target_kind"])
    trained = family in {
        FastForecastModelFamily.RIDGE_REGRESSION,
        FastForecastModelFamily.LOGISTIC_REGRESSION,
    }
    transforms: tuple[FastForecastFeatureTransform, ...] = ()
    coefficients: tuple[float, ...] = ()
    if trained:
        transform = common["transform"]
        assert isinstance(transform, dict)
        transforms = tuple(
            FastForecastFeatureTransform(
                feature_name=name,
                imputation_median=transform["imputation_median"],
                mean=transform["mean"],
                scale=transform["scale"],
            )
            for name in FAST_FORECAST_FEATURE_NAMES
        )
        values = [0.0] * len(FAST_FORECAST_FEATURE_NAMES)
        overrides = model["coefficient_overrides"]
        assert isinstance(overrides, list)
        for override in overrides:
            assert isinstance(override, dict)
            values[override["index"]] = override["value"]
        coefficients = tuple(values)

    artifact = FastForecastBaselineArtifact(
        schema_name=FAST_FORECAST_ARTIFACT_SCHEMA_NAME,
        schema_version=FAST_FORECAST_ARTIFACT_SCHEMA_VERSION,
        model_version=model["model_version"],
        model_family=family,
        target=target,
        target_kind=target_kind,
        horizon_ms=model["horizon_ms"],
        feature_schema_version=common["feature_schema_version"],
        training_policy_version=common["training_policy_version"],
        training_bundle_fingerprint_sha256=common[
            "training_bundle_fingerprint_sha256"
        ],
        future_path_label_version=common["future_path_label_version"],
        training_row_count=common["training_row_count"],
        target_unavailable_row_count=common["target_unavailable_row_count"],
        positive_row_count=model["positive_row_count"],
        negative_row_count=model["negative_row_count"],
        min_training_decision_observed_at_unix_ms=common[
            "min_training_decision_observed_at_unix_ms"
        ],
        max_training_decision_observed_at_unix_ms=common[
            "max_training_decision_observed_at_unix_ms"
        ],
        training_data_fingerprint_sha256=model[
            "training_data_fingerprint_sha256"
        ],
        feature_transforms=transforms,
        coefficients=coefficients,
        intercept=model["intercept"],
        constant_prediction=model["constant_prediction"],
        artifact_fingerprint_sha256=model["artifact_fingerprint_sha256"],
    )
    assert (
        fast_forecast_artifact_fingerprint_sha256(artifact)
        == model["artifact_fingerprint_sha256"]
    )
    return artifact


def _champion(spec: dict[str, object]) -> FastForecastChampionArtifact:
    common = spec["common"]
    models = spec["models"]
    assert isinstance(common, dict)
    assert isinstance(models, list)
    members = []
    for raw_model in models:
        assert isinstance(raw_model, dict)
        artifact = _artifact(raw_model, common)
        members.append(
            FastForecastChampionMember(
                member_key=raw_model["member_key"],
                forecast_artifact=artifact,
                validation_policy_version=common["validation_policy_version"],
                validation_run_fingerprint_sha256=raw_model[
                    "validation_run_fingerprint_sha256"
                ],
                test_evaluation_policy_version=common[
                    "test_evaluation_policy_version"
                ],
                test_evaluation_report_fingerprint_sha256=raw_model[
                    "test_evaluation_report_fingerprint_sha256"
                ],
                test_scored_observation_count=common[
                    "test_scored_observation_count"
                ],
                test_target_unavailable_count=common[
                    "test_target_unavailable_count"
                ],
            )
        )
    champion = FastForecastChampionArtifact(
        schema_name=FAST_FORECAST_CHAMPION_SCHEMA_NAME,
        schema_version=FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
        champion_version=common["champion_version"],
        selection=FastForecastChampionSelection(
            decision_reference=common["decision_reference"],
            decided_at_unix_ms=common["decided_at_unix_ms"],
            reason=common["reason"],
        ),
        feature_schema_version=common["feature_schema_version"],
        training_bundle_fingerprint_sha256=common[
            "training_bundle_fingerprint_sha256"
        ],
        future_path_label_version=common["future_path_label_version"],
        members=tuple(members),
        champion_fingerprint_sha256=common["champion_fingerprint_sha256"],
    )
    assert (
        fast_forecast_champion_fingerprint_sha256(champion)
        == common["champion_fingerprint_sha256"]
    )
    return champion


def _raw_features(raw_case: dict[str, object]) -> tuple[float | None, ...]:
    default = raw_case["default_value"]
    values: list[float | None] = [default] * len(FAST_FORECAST_FEATURE_NAMES)
    overrides = raw_case["overrides"]
    assert isinstance(overrides, list)
    for override in overrides:
        assert isinstance(override, dict)
        values[override["index"]] = override["value"]
    return tuple(values)


def _predict_raw(
    artifact: FastForecastBaselineArtifact,
    raw: tuple[float | None, ...],
) -> float:
    if artifact.model_family in {
        FastForecastModelFamily.MEAN_REGRESSOR,
        FastForecastModelFamily.PRIOR_CLASSIFIER,
    }:
        assert artifact.constant_prediction is not None
        return float(artifact.constant_prediction)
    assert artifact.intercept is not None
    transformed = apply_feature_transforms(raw, artifact.feature_transforms)
    score = math.fsum(
        coefficient * value
        for coefficient, value in zip(
            artifact.coefficients,
            transformed,
            strict=True,
        )
    ) + artifact.intercept
    if artifact.model_family is FastForecastModelFamily.LOGISTIC_REGRESSION:
        return _stable_sigmoid(score)
    return float(score)


def test_fl86_compact_fixture_is_valid_sealed_python_reference(tmp_path: Path) -> None:
    spec = _spec()
    assert spec["schema_name"] == "shreks.fast_lane_forecast_parity_spec"
    assert spec["schema_version"] == 1
    champion = _champion(spec)

    output = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, output)
    assert read_fast_forecast_champion(output) == champion

    by_key = {member.member_key: member for member in champion.members}
    absolute_tolerance = spec["absolute_tolerance"]
    relative_tolerance = spec["relative_tolerance"]
    cases = spec["cases"]
    assert isinstance(cases, list)
    for raw_case in cases:
        assert isinstance(raw_case, dict)
        raw = _raw_features(raw_case)
        expected_values = raw_case["expected"]
        assert isinstance(expected_values, list)
        for expected in expected_values:
            assert isinstance(expected, dict)
            member = by_key[expected["member_key"]]
            actual = _predict_raw(member.forecast_artifact, raw)
            expected_value = expected["predicted_value"]
            tolerance = absolute_tolerance + relative_tolerance * abs(expected_value)
            assert abs(actual - expected_value) <= tolerance
            diagnostic = expected["positive_at_half"]
            if diagnostic is not None:
                assert (actual >= 0.5) is diagnostic
