from __future__ import annotations

from dataclasses import replace

from fast_forecast_fixtures import training_bundle
from shreks_brain.fast_champion import FastForecastChampionArtifact
from shreks_brain.fast_evaluation import (
    FAST_FORECAST_EVALUATION_SCHEMA_NAME,
    FAST_FORECAST_EVALUATION_SCHEMA_VERSION,
    FastBinaryForecastMetrics,
    FastCalibrationBucket,
    FastContinuousForecastMetrics,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
    FastForecastEvaluationReport,
    FastForecastMetricPopulation,
    fast_forecast_evaluation_report_fingerprint_sha256,
)
from shreks_brain.fast_first_champion_v2.champion import (
    build_fast_first_champion_v2_runtime_champion,
)
from shreks_brain.fast_first_champion_v2.models import (
    FastFirstChampionV2BuildResult,
    FastFirstChampionV2MemberEvidence,
    FastFirstChampionV2Policy,
)
from shreks_brain.fast_learning import (
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTargetKind,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
    fast_forecast_artifact_fingerprint_sha256,
    train_fast_forecast_baseline,
)
from shreks_brain.fast_validation_v2 import (
    FastChronologicalGeneralizationRun,
)


def synthetic_v2_build_result() -> FastFirstChampionV2BuildResult:
    policy = FastFirstChampionV2Policy()
    bundle = training_bundle()
    artifacts = tuple(
        _runtime_artifact(bundle, target, family, policy.horizon_ms)
        for target, family in policy.required_members
    )
    runs = tuple(
        _run_shell(
            target=target,
            family=family,
            horizon_ms=policy.horizon_ms,
            bundle_fingerprint=bundle.manifest.bundle_fingerprint_sha256,
            index=index,
        )
        for index, (target, family) in enumerate(policy.required_members)
    )
    natural = tuple(
        _report(
            target=target,
            family=family,
            horizon_ms=policy.horizon_ms,
            bundle_fingerprint=bundle.manifest.bundle_fingerprint_sha256,
            run_fingerprint=run.validation_run_fingerprint_sha256,
            artifact_fingerprint=artifact.artifact_fingerprint_sha256,
            count=policy.minimum_natural_test_scored_observations,
            index=index,
        )
        for index, ((target, family), run, artifact) in enumerate(
            zip(policy.required_members, runs, artifacts, strict=True)
        )
    )
    unseen = tuple(
        _report(
            target=target,
            family=family,
            horizon_ms=policy.horizon_ms,
            bundle_fingerprint=bundle.manifest.bundle_fingerprint_sha256,
            run_fingerprint=run.validation_run_fingerprint_sha256,
            artifact_fingerprint=artifact.artifact_fingerprint_sha256,
            count=policy.minimum_unseen_mint_test_scored_observations,
            index=index + 10,
        )
        for index, ((target, family), run, artifact) in enumerate(
            zip(policy.required_members, runs, artifacts, strict=True)
        )
    )
    champion = build_fast_first_champion_v2_runtime_champion(
        policy=policy,
        champion_version="fl9-v2-fixture-champion-v1",
        decision_reference="fixture-only",
        reason="synthetic schema evidence only",
        runtime_artifacts=artifacts,
        generalization_runs=runs,
        natural_test_reports=natural,
    )
    evidence = tuple(
        FastFirstChampionV2MemberEvidence(
            target=artifact.target,
            model_family=artifact.model_family,
            horizon_ms=policy.horizon_ms,
            runtime_artifact_fingerprint_sha256=(
                artifact.artifact_fingerprint_sha256
            ),
            generalization_run_fingerprint_sha256=(
                run.validation_run_fingerprint_sha256
            ),
            natural_test_report_fingerprint_sha256=(
                natural_report.evaluation_report_fingerprint_sha256
            ),
            natural_test_scored_observation_count=(
                natural_report.overall.scored_observation_count
            ),
            natural_test_target_unavailable_count=0,
            unseen_mint_test_report_fingerprint_sha256=(
                unseen_report.evaluation_report_fingerprint_sha256
            ),
            unseen_mint_test_scored_observation_count=(
                unseen_report.overall.scored_observation_count
            ),
            unseen_mint_test_target_unavailable_count=0,
            unseen_mint_test_identity_fingerprint_sha256=(
                f"{index + 40:064x}"
            ),
        )
        for index, (
            artifact,
            run,
            natural_report,
            unseen_report,
        ) in enumerate(
            zip(artifacts, runs, natural, unseen, strict=True)
        )
    )
    return FastFirstChampionV2BuildResult(
        policy_version=policy.version,
        cohort_artifact_fingerprint_sha256=(
            policy.expected_cohort_artifact_fingerprint_sha256
        ),
        accepted_identity_fingerprint_sha256=(
            policy.expected_accepted_identity_fingerprint_sha256
        ),
        training_bundle_fingerprint_sha256=(
            bundle.manifest.bundle_fingerprint_sha256
        ),
        champion=champion,
        runtime_artifacts=artifacts,
        generalization_runs=runs,
        natural_test_reports=natural,
        unseen_mint_test_reports=unseen,
        member_evidence=evidence,
    )


def _runtime_artifact(
    bundle,
    target: FastForecastTarget,
    family: FastForecastModelFamily,
    horizon_ms: int,
) -> FastForecastBaselineArtifact:
    source_request = FastForecastTrainingRequest(
        model_version=f"fixture:{target.value}@250ms",
        model_family=family,
        target=target,
        horizon_ms=250,
        training_policy=FastForecastTrainingPolicy(
            version="fixture-training-v1"
        ),
    )
    source = train_fast_forecast_baseline(bundle, source_request)
    provisional = replace(
        source,
        model_version=f"fixture:{target.value}@{horizon_ms}ms",
        horizon_ms=horizon_ms,
        artifact_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        artifact_fingerprint_sha256=(
            fast_forecast_artifact_fingerprint_sha256(provisional)
        ),
    )


def _run_shell(
    *,
    target: FastForecastTarget,
    family: FastForecastModelFamily,
    horizon_ms: int,
    bundle_fingerprint: str,
    index: int,
) -> FastChronologicalGeneralizationRun:
    request = FastForecastTrainingRequest(
        model_version=f"fixture:{target.value}@{horizon_ms}ms",
        model_family=family,
        target=target,
        horizon_ms=horizon_ms,
        training_policy=FastForecastTrainingPolicy(
            version="fixture-training-v1"
        ),
    )
    value = object.__new__(FastChronologicalGeneralizationRun)
    object.__setattr__(value, "training_request", request)
    object.__setattr__(
        value,
        "training_bundle_fingerprint_sha256",
        bundle_fingerprint,
    )
    object.__setattr__(
        value,
        "validation_policy_version",
        "fl8.3-chronological-generalization-v2",
    )
    object.__setattr__(
        value,
        "validation_run_fingerprint_sha256",
        f"{index + 1:064x}",
    )
    return value


def _report(
    *,
    target: FastForecastTarget,
    family: FastForecastModelFamily,
    horizon_ms: int,
    bundle_fingerprint: str,
    run_fingerprint: str,
    artifact_fingerprint: str,
    count: int,
    index: int,
) -> FastForecastEvaluationReport:
    policy = FastForecastEvaluationPolicy(
        version="fl9-v2-fixture-eval-v1",
        partition=FastForecastEvaluationPartition.TEST,
        probability_bucket_count=2,
        liquidity_capacity_quote_boundaries=(10.0,),
        round_trip_cost_bps_boundaries=(10.0,),
        binary_log_loss_clip_epsilon=1e-12,
    )
    overall = _population("overall", target.kind, count)
    provisional = FastForecastEvaluationReport(
        schema_name=FAST_FORECAST_EVALUATION_SCHEMA_NAME,
        schema_version=FAST_FORECAST_EVALUATION_SCHEMA_VERSION,
        evaluation_policy=policy,
        validation_policy_version="fl8.3-chronological-generalization-v2",
        validation_run_fingerprint_sha256=run_fingerprint,
        training_bundle_fingerprint_sha256=bundle_fingerprint,
        model_version=f"fixture:{target.value}@{horizon_ms}ms",
        model_family=family,
        target=target,
        target_kind=target.kind,
        horizon_ms=horizon_ms,
        target_is_cost_adjusted=target is (
            FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS
        ),
        fold_artifact_fingerprints=(("fixture-fold", artifact_fingerprint),),
        context_fingerprint_sha256=f"{index + 100:064x}",
        overall=overall,
        fold_populations=(_population("fold:fixture-fold", target.kind, count),),
        regime_populations=(_population("regime:FIXTURE", target.kind, count),),
        strategy_family_populations=(
            _population("strategy:fixture", target.kind, count),
        ),
        liquidity_bucket_populations=(
            _population("liquidity:0", target.kind, count),
        ),
        cost_bucket_populations=(
            _population("cost:0", target.kind, count),
        ),
        evaluation_report_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        evaluation_report_fingerprint_sha256=(
            fast_forecast_evaluation_report_fingerprint_sha256(provisional)
        ),
    )


def _population(
    name: str,
    kind: FastForecastTargetKind,
    count: int,
) -> FastForecastMetricPopulation:
    if kind is FastForecastTargetKind.CONTINUOUS:
        continuous = FastContinuousForecastMetrics(
            observation_count=count,
            mean_predicted_value=0.0,
            mean_actual_value=0.0,
            mean_error=0.0,
            mean_absolute_error=0.0,
            root_mean_squared_error=0.0,
        )
        binary = None
    else:
        continuous = None
        binary = FastBinaryForecastMetrics(
            observation_count=count,
            positive_count=0,
            mean_predicted_probability=0.0,
            brier_score=0.0,
            log_loss=0.0,
            expected_calibration_error=0.0,
            calibration_buckets=(
                FastCalibrationBucket(
                    bucket_index=0,
                    lower_probability=0.0,
                    upper_probability=0.5,
                    observation_count=count,
                    mean_predicted_probability=0.0,
                    observed_positive_rate=0.0,
                    absolute_calibration_gap=0.0,
                ),
                FastCalibrationBucket(
                    bucket_index=1,
                    lower_probability=0.5,
                    upper_probability=1.0,
                    observation_count=0,
                    mean_predicted_probability=None,
                    observed_positive_rate=None,
                    absolute_calibration_gap=None,
                ),
            ),
        )
    return FastForecastMetricPopulation(
        name=name,
        prediction_count=count,
        scored_observation_count=count,
        target_unavailable_count=0,
        continuous_metrics=continuous,
        binary_metrics=binary,
    )
