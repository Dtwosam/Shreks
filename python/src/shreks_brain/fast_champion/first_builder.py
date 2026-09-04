from __future__ import annotations

from dataclasses import dataclass

from shreks_brain.fast_evaluation import (
    FastForecastEvaluationContext,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
    FastForecastEvaluationReport,
    evaluate_fast_forecasts,
)
from shreks_brain.fast_learning import (
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_learning.trainer import (
    train_fast_forecast_baseline_for_decision_identities,
)
from shreks_brain.fast_validation import (
    FastChronologicalValidationPolicy,
    FastChronologicalValidationRun,
    run_fast_chronological_validation,
)
from shreks_brain.research.fast_training_bundle import FastTrainingBundle

from .builder import build_fast_forecast_champion
from .models import FastForecastChampionArtifact


FAST_FIRST_CHAMPION_BUILDER_VERSION = "fl9-first-champion-builder-v1"

_REQUIRED_MEMBERS = (
    (
        FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
        FastForecastModelFamily.MEAN_REGRESSOR,
    ),
    (
        FastForecastTarget.ENDPOINT_RETURN_BPS,
        FastForecastModelFamily.MEAN_REGRESSOR,
    ),
    (
        FastForecastTarget.MAE_BPS,
        FastForecastModelFamily.MEAN_REGRESSOR,
    ),
    (
        FastForecastTarget.REVERSAL_OCCURRED,
        FastForecastModelFamily.PRIOR_CLASSIFIER,
    ),
    (
        FastForecastTarget.ROUTE_UNAVAILABILITY_OBSERVED,
        FastForecastModelFamily.PRIOR_CLASSIFIER,
    ),
)


@dataclass(frozen=True, slots=True)
class FastFirstChampionBuildResult:
    version: str
    champion: FastForecastChampionArtifact
    runtime_artifacts: tuple[FastForecastBaselineArtifact, ...]
    validation_runs: tuple[FastChronologicalValidationRun, ...]
    evaluation_reports: tuple[FastForecastEvaluationReport, ...]

    def __post_init__(self) -> None:
        if self.version != FAST_FIRST_CHAMPION_BUILDER_VERSION:
            raise ValueError("unsupported first champion builder version")
        if type(self.champion) is not FastForecastChampionArtifact:
            raise ValueError("champion must be an exact FastForecastChampionArtifact")
        if (
            not isinstance(self.runtime_artifacts, tuple)
            or len(self.runtime_artifacts) != len(_REQUIRED_MEMBERS)
            or not all(
                type(value) is FastForecastBaselineArtifact
                for value in self.runtime_artifacts
            )
        ):
            raise ValueError(
                "runtime_artifacts must contain the exact required member population"
            )
        if (
            not isinstance(self.validation_runs, tuple)
            or len(self.validation_runs) != len(_REQUIRED_MEMBERS)
            or not all(
                type(value) is FastChronologicalValidationRun
                for value in self.validation_runs
            )
        ):
            raise ValueError(
                "validation_runs must contain the exact required member population"
            )
        if (
            not isinstance(self.evaluation_reports, tuple)
            or len(self.evaluation_reports) != len(_REQUIRED_MEMBERS)
            or not all(
                type(value) is FastForecastEvaluationReport
                for value in self.evaluation_reports
            )
        ):
            raise ValueError(
                "evaluation_reports must contain the exact required member population"
            )

        artifact_keys = tuple(
            (value.target, value.horizon_ms) for value in self.runtime_artifacts
        )
        run_keys = tuple(
            (
                value.training_request.target,
                value.training_request.horizon_ms,
            )
            for value in self.validation_runs
        )
        report_keys = tuple(
            (value.target, value.horizon_ms) for value in self.evaluation_reports
        )
        expected = tuple(
            (target, self.runtime_artifacts[0].horizon_ms)
            for target, _ in _REQUIRED_MEMBERS
        )
        if artifact_keys != expected or run_keys != expected or report_keys != expected:
            raise ValueError(
                "first champion evidence populations are not in canonical required order"
            )


def build_fast_first_champion(
    *,
    bundle: FastTrainingBundle,
    contexts: tuple[FastForecastEvaluationContext, ...],
    validation_policy: FastChronologicalValidationPolicy,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    decision_reference: str,
    decided_at_unix_ms: int,
    reason: str,
    horizon_ms: int,
    model_version_prefix: str,
    training_policy_version: str,
    minimum_test_scored_observations: int,
) -> FastFirstChampionBuildResult:
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be an exact FastTrainingBundle")
    if (
        not isinstance(contexts, tuple)
        or not contexts
        or not all(
            type(value) is FastForecastEvaluationContext for value in contexts
        )
    ):
        raise ValueError(
            "contexts must be a non-empty tuple of exact FastForecastEvaluationContext values"
        )
    if type(validation_policy) is not FastChronologicalValidationPolicy:
        raise ValueError(
            "validation_policy must be exact FastChronologicalValidationPolicy"
        )
    if type(evaluation_policy) is not FastForecastEvaluationPolicy:
        raise ValueError(
            "evaluation_policy must be exact FastForecastEvaluationPolicy"
        )
    if evaluation_policy.partition is not FastForecastEvaluationPartition.TEST:
        raise ValueError("first champion evidence requires TEST evaluation")
    _require_non_empty("champion_version", champion_version)
    _require_non_empty("decision_reference", decision_reference)
    _require_non_empty("reason", reason)
    _require_non_empty("model_version_prefix", model_version_prefix)
    _require_non_empty("training_policy_version", training_policy_version)
    _require_positive_int("horizon_ms", horizon_ms)
    _require_non_negative_int("decided_at_unix_ms", decided_at_unix_ms)
    _require_positive_int(
        "minimum_test_scored_observations",
        minimum_test_scored_observations,
    )
    _validate_selection_chronology(
        validation_policy,
        decided_at_unix_ms=decided_at_unix_ms,
        horizon_ms=horizon_ms,
    )

    mature_identities = tuple(
        record.decision_identity
        for record in bundle.features.records
        if (
            record.decision_observed_at_unix_ms < decided_at_unix_ms
            and record.decision_observed_at_unix_ms + horizon_ms
            <= decided_at_unix_ms
        )
    )
    if not mature_identities:
        raise ValueError(
            "first champion has no target-mature pre-selection decisions"
        )

    artifacts: list[FastForecastBaselineArtifact] = []
    runs: list[FastChronologicalValidationRun] = []
    reports: list[FastForecastEvaluationReport] = []
    member_sources = []

    for target, family in _REQUIRED_MEMBERS:
        request = FastForecastTrainingRequest(
            model_version=(
                f"{model_version_prefix}:{target.value}@{horizon_ms}ms"
            ),
            model_family=family,
            target=target,
            horizon_ms=horizon_ms,
            training_policy=FastForecastTrainingPolicy(
                version=training_policy_version,
            ),
        )
        validation_run = run_fast_chronological_validation(
            bundle,
            request,
            validation_policy,
        )
        report = evaluate_fast_forecasts(
            bundle,
            validation_run,
            contexts,
            evaluation_policy,
        )
        if (
            report.overall.scored_observation_count
            < minimum_test_scored_observations
        ):
            raise ValueError(
                "TEST scored evidence does not meet the explicit minimum"
            )

        artifact = train_fast_forecast_baseline_for_decision_identities(
            bundle,
            request,
            mature_identities,
        )
        if (
            artifact.max_training_decision_observed_at_unix_ms + horizon_ms
            > decided_at_unix_ms
        ):
            raise ValueError(
                "runtime artifact includes training evidence not mature at selection"
            )

        artifacts.append(artifact)
        runs.append(validation_run)
        reports.append(report)
        member_sources.append((artifact, validation_run, report))

    champion = build_fast_forecast_champion(
        champion_version=champion_version,
        decision_reference=decision_reference,
        decided_at_unix_ms=decided_at_unix_ms,
        reason=reason,
        member_sources=tuple(member_sources),
    )
    return FastFirstChampionBuildResult(
        version=FAST_FIRST_CHAMPION_BUILDER_VERSION,
        champion=champion,
        runtime_artifacts=tuple(artifacts),
        validation_runs=tuple(runs),
        evaluation_reports=tuple(reports),
    )


def _validate_selection_chronology(
    policy: FastChronologicalValidationPolicy,
    *,
    decided_at_unix_ms: int,
    horizon_ms: int,
) -> None:
    latest_test_end = max(
        fold.test_ended_at_unix_ms for fold in policy.folds
    )
    if latest_test_end + horizon_ms > decided_at_unix_ms:
        raise ValueError(
            "selection must follow the latest TEST interval plus target maturity horizon"
        )


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")
