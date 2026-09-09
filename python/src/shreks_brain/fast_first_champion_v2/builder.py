from __future__ import annotations

from shreks_brain.fast_evaluation import (
    FastForecastEvaluationContext,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
    FastForecastEvaluationReport,
)
from shreks_brain.fast_learning import (
    FastForecastBaselineArtifact,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_learning.trainer import (
    train_fast_forecast_baseline_for_decision_identities,
)
from shreks_brain.fast_validation import FastChronologicalFold
from shreks_brain.fast_validation_v2 import (
    FastChronologicalGeneralizationPolicy,
    FastChronologicalGeneralizationRun,
    run_fast_chronological_generalization,
)
from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2CohortAcceptanceArtifact,
)
from shreks_brain.research.fast_training_bundle import FastTrainingBundle

from .bundle import _require_bundle_matches_cohort, _validate_cohort
from .champion import build_fast_first_champion_v2_runtime_champion
from .evaluation import evaluate_fast_first_champion_v2_test
from .models import (
    FAST_FIRST_CHAMPION_V2_POLICY_VERSION,
    FastFirstChampionV2BuildResult,
    FastFirstChampionV2MemberEvidence,
    FastFirstChampionV2Policy,
)


_FOLD_NAME = "fl9-v2-first-champion-v1"


def build_fast_first_champion_v2(
    *,
    cohort: Fl9V2CohortAcceptanceArtifact,
    bundle: FastTrainingBundle,
    contexts: tuple[FastForecastEvaluationContext, ...],
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    decision_reference: str,
    reason: str,
    model_version_prefix: str,
    training_policy_version: str,
    policy: FastFirstChampionV2Policy | None = None,
) -> FastFirstChampionV2BuildResult:
    active_policy = policy or FastFirstChampionV2Policy()
    if type(active_policy) is not FastFirstChampionV2Policy:
        raise ValueError(
            "policy must be exact FastFirstChampionV2Policy"
        )
    _validate_cohort(cohort, active_policy)
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be exact FastTrainingBundle")
    _require_bundle_matches_cohort(cohort, bundle, active_policy)
    if (
        not isinstance(contexts, tuple)
        or not contexts
        or not all(
            type(value) is FastForecastEvaluationContext
            for value in contexts
        )
    ):
        raise ValueError(
            "contexts must be a non-empty tuple of exact "
            "FastForecastEvaluationContext values"
        )
    if type(evaluation_policy) is not FastForecastEvaluationPolicy:
        raise ValueError(
            "evaluation_policy must be exact FastForecastEvaluationPolicy"
        )
    if evaluation_policy.partition is not FastForecastEvaluationPartition.TEST:
        raise ValueError(
            "V2 first-champion evidence requires TEST evaluation"
        )
    for name, value in (
        ("champion_version", champion_version),
        ("decision_reference", decision_reference),
        ("reason", reason),
        ("model_version_prefix", model_version_prefix),
        ("training_policy_version", training_policy_version),
    ):
        _non_empty(name, value)

    generalization_policy = _generalization_policy(active_policy)
    requests: list[FastForecastTrainingRequest] = []
    runs: list[FastChronologicalGeneralizationRun] = []
    natural_reports: list[FastForecastEvaluationReport] = []
    unseen_reports: list[FastForecastEvaluationReport] = []

    # No final runtime refit happens in this loop. All five required members
    # must first pass both precommitted TEST evidence floors.
    for target, family in active_policy.required_members:
        request = FastForecastTrainingRequest(
            model_version=(
                f"{model_version_prefix}:{target.value}"
                f"@{active_policy.horizon_ms}ms"
            ),
            model_family=family,
            target=target,
            horizon_ms=active_policy.horizon_ms,
            training_policy=FastForecastTrainingPolicy(
                version=training_policy_version,
            ),
        )
        run = run_fast_chronological_generalization(
            bundle,
            request,
            generalization_policy,
        )
        _reconcile_run_to_cohort(
            cohort,
            run,
            active_policy,
        )
        natural = evaluate_fast_first_champion_v2_test(
            bundle,
            run,
            contexts,
            evaluation_policy,
            unseen_mint_only=False,
        )
        unseen = evaluate_fast_first_champion_v2_test(
            bundle,
            run,
            contexts,
            evaluation_policy,
            unseen_mint_only=True,
        )
        _require_scoring_floors(
            natural,
            unseen,
            active_policy,
        )
        requests.append(request)
        runs.append(run)
        natural_reports.append(natural)
        unseen_reports.append(unseen)

    mature_identities = _target_mature_accepted_identities(
        cohort,
        bundle,
        active_policy,
    )
    artifacts: list[FastForecastBaselineArtifact] = []
    for request in requests:
        artifact = train_fast_forecast_baseline_for_decision_identities(
            bundle,
            request,
            mature_identities,
        )
        if (
            artifact.min_training_decision_observed_at_unix_ms
            < active_policy.training_started_at_unix_ms
            or (
                artifact.max_training_decision_observed_at_unix_ms
                + active_policy.horizon_ms
                > active_policy.selection_at_unix_ms
            )
        ):
            raise ValueError(
                "V2 runtime refit includes evidence outside the frozen "
                "target-mature accepted cohort"
            )
        artifacts.append(artifact)

    runtime_artifacts = tuple(artifacts)
    generalization_runs = tuple(runs)
    natural_test_reports = tuple(natural_reports)
    unseen_mint_test_reports = tuple(unseen_reports)
    champion = build_fast_first_champion_v2_runtime_champion(
        policy=active_policy,
        champion_version=champion_version,
        decision_reference=decision_reference,
        reason=reason,
        runtime_artifacts=runtime_artifacts,
        generalization_runs=generalization_runs,
        natural_test_reports=natural_test_reports,
    )

    member_evidence = tuple(
        FastFirstChampionV2MemberEvidence(
            target=artifact.target,
            model_family=artifact.model_family,
            horizon_ms=active_policy.horizon_ms,
            runtime_artifact_fingerprint_sha256=(
                artifact.artifact_fingerprint_sha256
            ),
            generalization_run_fingerprint_sha256=(
                run.validation_run_fingerprint_sha256
            ),
            natural_test_report_fingerprint_sha256=(
                natural.evaluation_report_fingerprint_sha256
            ),
            natural_test_scored_observation_count=(
                natural.overall.scored_observation_count
            ),
            natural_test_target_unavailable_count=(
                natural.overall.target_unavailable_count
            ),
            unseen_mint_test_report_fingerprint_sha256=(
                unseen.evaluation_report_fingerprint_sha256
            ),
            unseen_mint_test_scored_observation_count=(
                unseen.overall.scored_observation_count
            ),
            unseen_mint_test_target_unavailable_count=(
                unseen.overall.target_unavailable_count
            ),
            unseen_mint_test_identity_fingerprint_sha256=(
                cohort.manifest.test_unseen_mint_identity_fingerprint_sha256
            ),
        )
        for artifact, run, natural, unseen in zip(
            runtime_artifacts,
            generalization_runs,
            natural_test_reports,
            unseen_mint_test_reports,
            strict=True,
        )
    )

    return FastFirstChampionV2BuildResult(
        policy_version=FAST_FIRST_CHAMPION_V2_POLICY_VERSION,
        cohort_artifact_fingerprint_sha256=(
            cohort.manifest.artifact_fingerprint_sha256
        ),
        accepted_identity_fingerprint_sha256=(
            cohort.manifest.accepted_identity_fingerprint_sha256
        ),
        training_bundle_fingerprint_sha256=(
            bundle.manifest.bundle_fingerprint_sha256
        ),
        champion=champion,
        runtime_artifacts=runtime_artifacts,
        generalization_runs=generalization_runs,
        natural_test_reports=natural_test_reports,
        unseen_mint_test_reports=unseen_mint_test_reports,
        member_evidence=member_evidence,
    )


def _generalization_policy(
    policy: FastFirstChampionV2Policy,
) -> FastChronologicalGeneralizationPolicy:
    return FastChronologicalGeneralizationPolicy(
        version=policy.generalization_policy_version,
        folds=(
            FastChronologicalFold(
                name=_FOLD_NAME,
                training_started_at_unix_ms=(
                    policy.training_started_at_unix_ms
                ),
                training_ended_at_unix_ms=(
                    policy.training_ended_at_unix_ms
                ),
                validation_started_at_unix_ms=(
                    policy.validation_started_at_unix_ms
                ),
                validation_ended_at_unix_ms=(
                    policy.validation_ended_at_unix_ms
                ),
                test_started_at_unix_ms=(
                    policy.test_started_at_unix_ms
                ),
                test_ended_at_unix_ms=(
                    policy.test_ended_at_unix_ms
                ),
            ),
        ),
        feature_identity_firewall_version=(
            policy.feature_identity_firewall_version
        ),
        feature_identity_firewall_fingerprint_sha256=(
            policy.feature_identity_firewall_fingerprint_sha256
        ),
        minimum_unseen_mint_validation_rows=(
            policy.minimum_unseen_mint_validation_rows
        ),
        minimum_unseen_mint_validation_mints=(
            policy.minimum_unseen_mint_validation_mints
        ),
        minimum_unseen_mint_test_rows=(
            policy.minimum_unseen_mint_test_rows
        ),
        minimum_unseen_mint_test_mints=(
            policy.minimum_unseen_mint_test_mints
        ),
    )


def _reconcile_run_to_cohort(
    cohort: Fl9V2CohortAcceptanceArtifact,
    run: FastChronologicalGeneralizationRun,
    policy: FastFirstChampionV2Policy,
) -> None:
    if type(run) is not FastChronologicalGeneralizationRun:
        raise ValueError(
            "run must be exact FastChronologicalGeneralizationRun"
        )
    if (
        run.validation_policy_version
        != policy.generalization_policy_version
        or run.feature_identity_firewall_version
        != policy.feature_identity_firewall_version
        or run.feature_identity_firewall_fingerprint_sha256
        != policy.feature_identity_firewall_fingerprint_sha256
    ):
        raise ValueError("V2 generalization policy/firewall identity mismatch")
    if len(run.fold_results) != 1:
        raise ValueError(
            "FL9 V2 first champion requires exactly one frozen fold"
        )

    result = run.fold_results[0]
    manifest = cohort.manifest
    fold = result.fold
    expected_fold = (
        policy.training_started_at_unix_ms,
        policy.training_ended_at_unix_ms,
        policy.validation_started_at_unix_ms,
        policy.validation_ended_at_unix_ms,
        policy.test_started_at_unix_ms,
        policy.test_ended_at_unix_ms,
    )
    actual_fold = (
        fold.training_started_at_unix_ms,
        fold.training_ended_at_unix_ms,
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.test_started_at_unix_ms,
        fold.test_ended_at_unix_ms,
    )
    if actual_fold != expected_fold:
        raise ValueError("V2 generalization fold contradicts frozen cohort")

    expected_counts = (
        manifest.training_raw_row_count,
        manifest.training_row_count,
        manifest.validation_raw_row_count,
        manifest.validation_row_count,
        manifest.test_raw_row_count,
        manifest.test_row_count,
        manifest.shared_signature_count,
        manifest.training_quarantined_row_count,
        manifest.validation_quarantined_row_count,
        manifest.test_quarantined_row_count,
    )
    actual_counts = (
        result.training_raw_row_count,
        result.training_row_count,
        result.validation_raw_row_count,
        result.validation_row_count,
        result.test_raw_row_count,
        result.test_row_count,
        result.signature_quarantine.shared_signature_count,
        result.signature_quarantine.training_quarantined_row_count,
        result.signature_quarantine.validation_quarantined_row_count,
        result.signature_quarantine.test_quarantined_row_count,
    )
    if actual_counts != expected_counts:
        raise ValueError(
            "V2 generalization partition/quarantine counts "
            "do not reconcile to cohort"
        )

    accepted_by_partition = {
        role: tuple(
            value.decision_identity
            for value in cohort.accepted_decisions
            if value.partition == role
        )
        for role in ("training", "validation", "test")
    }
    validation_predictions = tuple(
        value.decision_identity
        for value in result.validation_predictions
    )
    test_predictions = tuple(
        value.decision_identity for value in result.test_predictions
    )
    if validation_predictions != accepted_by_partition["validation"]:
        raise ValueError(
            "V2 validation prediction identities do not equal cohort"
        )
    if test_predictions != accepted_by_partition["test"]:
        raise ValueError(
            "V2 TEST prediction identities do not equal cohort"
        )

    expected_validation_unseen = tuple(
        value.decision_identity
        for value in cohort.accepted_decisions
        if (
            value.partition == "validation"
            and value.mint_novelty == "unseen"
        )
    )
    expected_validation_seen = tuple(
        value.decision_identity
        for value in cohort.accepted_decisions
        if (
            value.partition == "validation"
            and value.mint_novelty == "seen"
        )
    )
    expected_test_unseen = tuple(
        value.decision_identity
        for value in cohort.accepted_decisions
        if value.partition == "test" and value.mint_novelty == "unseen"
    )
    expected_test_seen = tuple(
        value.decision_identity
        for value in cohort.accepted_decisions
        if value.partition == "test" and value.mint_novelty == "seen"
    )
    if (
        result.validation_novelty.unseen_mint_identities
        != expected_validation_unseen
        or result.validation_novelty.seen_mint_identities
        != expected_validation_seen
        or result.test_novelty.unseen_mint_identities
        != expected_test_unseen
        or result.test_novelty.seen_mint_identities
        != expected_test_seen
    ):
        raise ValueError(
            "V2 generalization novelty identities do not reconcile to cohort"
        )

    novelty_counts = (
        len(result.validation_novelty.unseen_mint_identities),
        result.validation_novelty.unseen_mint_unique_mint_count,
        len(result.test_novelty.unseen_mint_identities),
        result.test_novelty.unseen_mint_unique_mint_count,
        result.validation_novelty.seen_actor_row_count,
        result.validation_novelty.unseen_actor_row_count,
        result.validation_novelty.null_actor_row_count,
        result.test_novelty.seen_actor_row_count,
        result.test_novelty.unseen_actor_row_count,
        result.test_novelty.null_actor_row_count,
    )
    expected_novelty_counts = (
        manifest.validation_unseen_mint_row_count,
        manifest.validation_unseen_mint_unique_mint_count,
        manifest.test_unseen_mint_row_count,
        manifest.test_unseen_mint_unique_mint_count,
        manifest.validation_seen_actor_row_count,
        manifest.validation_unseen_actor_row_count,
        manifest.validation_null_actor_row_count,
        manifest.test_seen_actor_row_count,
        manifest.test_unseen_actor_row_count,
        manifest.test_null_actor_row_count,
    )
    if novelty_counts != expected_novelty_counts:
        raise ValueError(
            "V2 generalization novelty counts do not reconcile to cohort"
        )


def _require_scoring_floors(
    natural: FastForecastEvaluationReport,
    unseen: FastForecastEvaluationReport,
    policy: FastFirstChampionV2Policy,
) -> None:
    if (
        natural.overall.scored_observation_count
        < policy.minimum_natural_test_scored_observations
    ):
        raise ValueError(
            "natural TEST scored evidence is below the frozen minimum"
        )
    if (
        unseen.overall.scored_observation_count
        < policy.minimum_unseen_mint_test_scored_observations
    ):
        raise ValueError(
            "unseen-mint TEST scored evidence is below the frozen minimum"
        )


def _target_mature_accepted_identities(
    cohort: Fl9V2CohortAcceptanceArtifact,
    bundle: FastTrainingBundle,
    policy: FastFirstChampionV2Policy,
) -> tuple[tuple[object, ...], ...]:
    accepted = {
        value.decision_identity for value in cohort.accepted_decisions
    }
    values = tuple(
        record.decision_identity
        for record in bundle.features.records
        if (
            record.decision_identity in accepted
            and record.decision_observed_at_unix_ms
            >= policy.training_started_at_unix_ms
            and record.decision_observed_at_unix_ms
            < policy.selection_at_unix_ms
            and (
                record.decision_observed_at_unix_ms + policy.horizon_ms
                <= policy.selection_at_unix_ms
            )
        )
    )
    if len(values) != len(accepted):
        raise ValueError(
            "not every accepted V2 cohort identity is target-mature "
            "at the frozen selection timestamp"
        )
    if set(values) != accepted:
        raise ValueError(
            "V2 runtime refit identity population does not equal cohort"
        )
    return values


def _non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
