from __future__ import annotations

from dataclasses import replace

from shreks_brain.fast_champion import (
    FAST_FORECAST_CHAMPION_SCHEMA_NAME,
    FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
    FastForecastChampionArtifact,
    FastForecastChampionMember,
    FastForecastChampionSelection,
    fast_forecast_champion_fingerprint_sha256,
    fast_forecast_champion_member_key,
)
from shreks_brain.fast_evaluation import FastForecastEvaluationReport
from shreks_brain.fast_learning import FastForecastBaselineArtifact
from shreks_brain.fast_validation_v2 import (
    FastChronologicalGeneralizationRun,
)

from .models import FastFirstChampionV2Policy


def build_fast_first_champion_v2_runtime_champion(
    *,
    policy: FastFirstChampionV2Policy,
    champion_version: str,
    decision_reference: str,
    reason: str,
    runtime_artifacts: tuple[FastForecastBaselineArtifact, ...],
    generalization_runs: tuple[FastChronologicalGeneralizationRun, ...],
    natural_test_reports: tuple[FastForecastEvaluationReport, ...],
) -> FastForecastChampionArtifact:
    if type(policy) is not FastFirstChampionV2Policy:
        raise ValueError("policy must be exact FastFirstChampionV2Policy")
    for name, value in (
        ("champion_version", champion_version),
        ("decision_reference", decision_reference),
        ("reason", reason),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty text")

    count = len(policy.required_members)
    for name, values, expected_type in (
        ("runtime_artifacts", runtime_artifacts, FastForecastBaselineArtifact),
        (
            "generalization_runs",
            generalization_runs,
            FastChronologicalGeneralizationRun,
        ),
        (
            "natural_test_reports",
            natural_test_reports,
            FastForecastEvaluationReport,
        ),
    ):
        if (
            not isinstance(values, tuple)
            or len(values) != count
            or not all(type(value) is expected_type for value in values)
        ):
            raise ValueError(
                f"{name} must contain the exact required member population"
            )

    members: list[FastForecastChampionMember] = []
    for expected, artifact, run, report in zip(
        policy.required_members,
        runtime_artifacts,
        generalization_runs,
        natural_test_reports,
        strict=True,
    ):
        target, family = expected
        if (
            artifact.target is not target
            or artifact.model_family is not family
            or artifact.horizon_ms != policy.horizon_ms
        ):
            raise ValueError(
                "runtime artifact does not match required V2 member"
            )
        request = run.training_request
        if (
            request.target is not target
            or request.model_family is not family
            or request.horizon_ms != policy.horizon_ms
        ):
            raise ValueError(
                "V2 generalization run does not match required member"
            )
        if (
            report.target is not target
            or report.model_family is not family
            or report.horizon_ms != policy.horizon_ms
            or report.validation_run_fingerprint_sha256
            != run.validation_run_fingerprint_sha256
        ):
            raise ValueError(
                "natural TEST report does not match V2 generalization run"
            )
        if (
            artifact.training_bundle_fingerprint_sha256
            != run.training_bundle_fingerprint_sha256
            or report.training_bundle_fingerprint_sha256
            != run.training_bundle_fingerprint_sha256
        ):
            raise ValueError(
                "V2 champion member bundle fingerprints do not reconcile"
            )
        members.append(
            FastForecastChampionMember(
                member_key=fast_forecast_champion_member_key(
                    target,
                    policy.horizon_ms,
                ),
                forecast_artifact=artifact,
                validation_policy_version=(
                    run.validation_policy_version
                ),
                validation_run_fingerprint_sha256=(
                    run.validation_run_fingerprint_sha256
                ),
                test_evaluation_policy_version=(
                    report.evaluation_policy.version
                ),
                test_evaluation_report_fingerprint_sha256=(
                    report.evaluation_report_fingerprint_sha256
                ),
                test_scored_observation_count=(
                    report.overall.scored_observation_count
                ),
                test_target_unavailable_count=(
                    report.overall.target_unavailable_count
                ),
            )
        )

    canonical_members = tuple(
        sorted(members, key=lambda value: value.member_key)
    )
    first = runtime_artifacts[0]
    if any(
        artifact.feature_schema_version != first.feature_schema_version
        or artifact.training_bundle_fingerprint_sha256
        != first.training_bundle_fingerprint_sha256
        or artifact.future_path_label_version
        != first.future_path_label_version
        for artifact in runtime_artifacts
    ):
        raise ValueError(
            "V2 runtime artifacts do not share one training provenance"
        )

    provisional = FastForecastChampionArtifact(
        schema_name=FAST_FORECAST_CHAMPION_SCHEMA_NAME,
        schema_version=FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
        champion_version=champion_version,
        selection=FastForecastChampionSelection(
            decision_reference=decision_reference,
            decided_at_unix_ms=policy.selection_at_unix_ms,
            reason=reason,
        ),
        feature_schema_version=first.feature_schema_version,
        training_bundle_fingerprint_sha256=(
            first.training_bundle_fingerprint_sha256
        ),
        future_path_label_version=first.future_path_label_version,
        members=canonical_members,
        champion_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        champion_fingerprint_sha256=(
            fast_forecast_champion_fingerprint_sha256(provisional)
        ),
    )
