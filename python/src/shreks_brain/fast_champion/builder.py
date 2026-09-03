from __future__ import annotations

from dataclasses import replace

from shreks_brain.fast_evaluation.models import (
    FastForecastEvaluationPartition,
    FastForecastEvaluationReport,
    fast_forecast_evaluation_report_fingerprint_sha256,
)
from shreks_brain.fast_learning.models import (
    FastForecastBaselineArtifact,
    fast_forecast_artifact_fingerprint_sha256,
)
from shreks_brain.fast_validation.models import FastChronologicalValidationRun

from .models import (
    FAST_FORECAST_CHAMPION_SCHEMA_NAME,
    FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
    FastForecastChampionArtifact,
    FastForecastChampionMember,
    FastForecastChampionSelection,
    fast_forecast_champion_fingerprint_sha256,
    fast_forecast_champion_member_key,
)


def build_fast_forecast_champion(
    *,
    champion_version: str,
    decision_reference: str,
    decided_at_unix_ms: int,
    reason: str,
    member_sources: tuple[
        tuple[
            FastForecastBaselineArtifact,
            FastChronologicalValidationRun,
            FastForecastEvaluationReport,
        ],
        ...,
    ],
) -> FastForecastChampionArtifact:
    selection = FastForecastChampionSelection(
        decision_reference=decision_reference,
        decided_at_unix_ms=decided_at_unix_ms,
        reason=reason,
    )
    if not isinstance(member_sources, tuple) or not member_sources:
        raise ValueError("member_sources must be a non-empty tuple")

    members: list[FastForecastChampionMember] = []
    for index, source in enumerate(member_sources):
        if not isinstance(source, tuple) or len(source) != 3:
            raise ValueError(f"member source {index} must be a three-item tuple")
        artifact, validation_run, evaluation_report = source
        members.append(
            _build_member(
                artifact=artifact,
                validation_run=validation_run,
                evaluation_report=evaluation_report,
            )
        )

    canonical_members = tuple(sorted(members, key=lambda value: value.member_key))
    keys = tuple(value.member_key for value in canonical_members)
    if len(keys) != len(set(keys)):
        raise ValueError("member_sources contain a duplicate target/horizon")

    first_artifact = canonical_members[0].forecast_artifact
    provisional = FastForecastChampionArtifact(
        schema_name=FAST_FORECAST_CHAMPION_SCHEMA_NAME,
        schema_version=FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
        champion_version=champion_version,
        selection=selection,
        feature_schema_version=first_artifact.feature_schema_version,
        training_bundle_fingerprint_sha256=(
            first_artifact.training_bundle_fingerprint_sha256
        ),
        future_path_label_version=first_artifact.future_path_label_version,
        members=canonical_members,
        champion_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        champion_fingerprint_sha256=fast_forecast_champion_fingerprint_sha256(
            provisional
        ),
    )


def _build_member(
    *,
    artifact: FastForecastBaselineArtifact,
    validation_run: FastChronologicalValidationRun,
    evaluation_report: FastForecastEvaluationReport,
) -> FastForecastChampionMember:
    if type(artifact) is not FastForecastBaselineArtifact:
        raise ValueError("runtime forecast artifact must be an exact FastForecastBaselineArtifact")
    if type(validation_run) is not FastChronologicalValidationRun:
        raise ValueError("validation evidence must be an exact FastChronologicalValidationRun")
    if type(evaluation_report) is not FastForecastEvaluationReport:
        raise ValueError("evaluation evidence must be an exact FastForecastEvaluationReport")

    if evaluation_report.evaluation_policy.partition is not FastForecastEvaluationPartition.TEST:
        raise ValueError("forecast champion members require FL8.4 TEST evaluation evidence")

    expected_artifact = fast_forecast_artifact_fingerprint_sha256(artifact)
    if expected_artifact != artifact.artifact_fingerprint_sha256:
        raise ValueError("runtime forecast artifact fingerprint is inconsistent")
    expected_report = fast_forecast_evaluation_report_fingerprint_sha256(
        evaluation_report
    )
    if expected_report != evaluation_report.evaluation_report_fingerprint_sha256:
        raise ValueError("evaluation report fingerprint is inconsistent")

    request = validation_run.training_request
    if evaluation_report.validation_run_fingerprint_sha256 != (
        validation_run.validation_run_fingerprint_sha256
    ):
        raise ValueError("evaluation report does not reference the supplied validation run")
    if evaluation_report.validation_policy_version != validation_run.validation_policy_version:
        raise ValueError("evaluation and validation policy versions are inconsistent")

    source_fingerprints = {
        artifact.training_bundle_fingerprint_sha256,
        validation_run.training_bundle_fingerprint_sha256,
        evaluation_report.training_bundle_fingerprint_sha256,
    }
    if len(source_fingerprints) != 1:
        raise ValueError("artifact, validation, and evaluation source bundle fingerprints differ")

    if artifact.model_version != request.model_version:
        raise ValueError("runtime artifact model version does not match validation request")
    if artifact.model_family is not request.model_family:
        raise ValueError("runtime artifact model family does not match validation request")
    if artifact.target is not request.target:
        raise ValueError("runtime artifact target does not match validation request")
    if artifact.horizon_ms != request.horizon_ms:
        raise ValueError("runtime artifact horizon does not match validation request")
    if artifact.training_policy_version != request.training_policy.version:
        raise ValueError("runtime artifact training policy does not match validation request")

    if evaluation_report.model_version != artifact.model_version:
        raise ValueError("evaluation model version does not match runtime artifact")
    if evaluation_report.model_family is not artifact.model_family:
        raise ValueError("evaluation model family does not match runtime artifact")
    if evaluation_report.target is not artifact.target:
        raise ValueError("evaluation target does not match runtime artifact")
    if evaluation_report.horizon_ms != artifact.horizon_ms:
        raise ValueError("evaluation horizon does not match runtime artifact")

    if not validation_run.fold_results:
        raise ValueError("validation run must contain fold results")
    for fold_result in validation_run.fold_results:
        fold_artifact = fold_result.model
        if fold_artifact.model_version != artifact.model_version:
            raise ValueError("validation fold model version does not match runtime artifact")
        if fold_artifact.model_family is not artifact.model_family:
            raise ValueError("validation fold model family does not match runtime artifact")
        if fold_artifact.target is not artifact.target:
            raise ValueError("validation fold target does not match runtime artifact")
        if fold_artifact.horizon_ms != artifact.horizon_ms:
            raise ValueError("validation fold horizon does not match runtime artifact")
        if fold_artifact.training_policy_version != artifact.training_policy_version:
            raise ValueError("validation fold training policy does not match runtime artifact")
        if fold_artifact.feature_schema_version != artifact.feature_schema_version:
            raise ValueError("validation fold feature schema does not match runtime artifact")
        if fold_artifact.future_path_label_version != artifact.future_path_label_version:
            raise ValueError("validation fold label version does not match runtime artifact")

    return FastForecastChampionMember(
        member_key=fast_forecast_champion_member_key(
            artifact.target,
            artifact.horizon_ms,
        ),
        forecast_artifact=artifact,
        validation_policy_version=validation_run.validation_policy_version,
        validation_run_fingerprint_sha256=(
            validation_run.validation_run_fingerprint_sha256
        ),
        test_evaluation_policy_version=evaluation_report.evaluation_policy.version,
        test_evaluation_report_fingerprint_sha256=(
            evaluation_report.evaluation_report_fingerprint_sha256
        ),
        test_scored_observation_count=evaluation_report.overall.scored_observation_count,
        test_target_unavailable_count=evaluation_report.overall.target_unavailable_count,
    )
