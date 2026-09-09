from __future__ import annotations

from dataclasses import replace
import math

from shreks_brain.fast_evaluation.engine import (
    _COST_ADJUSTED_TARGETS,
    _ScoredPrediction,
    _context_sort_key,
    _group_populations,
    _numeric_bucket_name,
    _observation_sort_key,
    _population,
    _selected_target_value,
)
from shreks_brain.fast_evaluation.models import (
    FAST_FORECAST_EVALUATION_SCHEMA_NAME,
    FAST_FORECAST_EVALUATION_SCHEMA_VERSION,
    FastForecastEvaluationContext,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
    FastForecastEvaluationReport,
    fast_forecast_context_fingerprint_sha256,
    fast_forecast_evaluation_report_fingerprint_sha256,
)
from shreks_brain.fast_learning import (
    FastForecastPrediction,
    FastForecastTargetKind,
)
from shreks_brain.fast_validation_v2 import (
    FastChronologicalGeneralizationRun,
)
from shreks_brain.research.fast_training_bundle import FastTrainingBundle


def evaluate_fast_first_champion_v2_test(
    bundle: FastTrainingBundle,
    generalization_run: FastChronologicalGeneralizationRun,
    contexts: tuple[FastForecastEvaluationContext, ...],
    policy: FastForecastEvaluationPolicy,
    *,
    unseen_mint_only: bool,
) -> FastForecastEvaluationReport:
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be exact FastTrainingBundle")
    if type(generalization_run) is not FastChronologicalGeneralizationRun:
        raise ValueError(
            "generalization_run must be exact "
            "FastChronologicalGeneralizationRun"
        )
    if type(policy) is not FastForecastEvaluationPolicy:
        raise ValueError(
            "policy must be exact FastForecastEvaluationPolicy"
        )
    if policy.partition is not FastForecastEvaluationPartition.TEST:
        raise ValueError("V2 first-champion evaluation requires TEST policy")
    if not isinstance(unseen_mint_only, bool):
        raise ValueError("unseen_mint_only must be bool")
    if (
        bundle.manifest.bundle_fingerprint_sha256
        != generalization_run.training_bundle_fingerprint_sha256
    ):
        raise ValueError(
            "FL8.1 bundle fingerprint does not match V2 generalization run"
        )

    _validate_v2_fold_models(generalization_run)
    canonical_contexts = _canonical_v2_contexts(
        generalization_run,
        contexts,
    )
    context_by_identity = {
        value.decision_identity: value for value in canonical_contexts
    }
    observations = _selected_v2_test_observations(
        bundle=bundle,
        generalization_run=generalization_run,
        context_by_identity=context_by_identity,
        unseen_mint_only=unseen_mint_only,
    )
    if not observations:
        raise ValueError("selected V2 TEST slice contains no predictions")
    if not any(value.actual_value is not None for value in observations):
        raise ValueError(
            "selected V2 TEST slice contains zero scorable observations"
        )

    request = generalization_run.training_request
    overall = _population(
        "overall",
        observations,
        request.target.kind,
        policy,
    )
    fold_populations = _group_populations(
        observations,
        key_fn=lambda value: (f"fold:{value.fold_name}",),
        kind=request.target.kind,
        policy=policy,
    )
    regime_populations = _group_populations(
        observations,
        key_fn=lambda value: (
            f"regime:{value.context.market_regime}",
        ),
        kind=request.target.kind,
        policy=policy,
    )
    strategy_populations = _group_populations(
        observations,
        key_fn=lambda value: tuple(
            f"strategy:{family}"
            for family in value.context.strategy_families
        ),
        kind=request.target.kind,
        policy=policy,
    )
    liquidity_populations = _group_populations(
        observations,
        key_fn=lambda value: (
            _numeric_bucket_name(
                "liquidity",
                value.context.executable_exit_capacity_quote,
                policy.liquidity_capacity_quote_boundaries,
            ),
        ),
        kind=request.target.kind,
        policy=policy,
    )
    cost_populations = _group_populations(
        observations,
        key_fn=lambda value: (
            _numeric_bucket_name(
                "cost",
                value.context.expected_round_trip_cost_bps,
                policy.round_trip_cost_bps_boundaries,
            ),
        ),
        kind=request.target.kind,
        policy=policy,
    )

    provisional = FastForecastEvaluationReport(
        schema_name=FAST_FORECAST_EVALUATION_SCHEMA_NAME,
        schema_version=FAST_FORECAST_EVALUATION_SCHEMA_VERSION,
        evaluation_policy=policy,
        validation_policy_version=(
            generalization_run.validation_policy_version
        ),
        validation_run_fingerprint_sha256=(
            generalization_run.validation_run_fingerprint_sha256
        ),
        training_bundle_fingerprint_sha256=(
            bundle.manifest.bundle_fingerprint_sha256
        ),
        model_version=request.model_version,
        model_family=request.model_family,
        target=request.target,
        target_kind=request.target.kind,
        horizon_ms=request.horizon_ms,
        target_is_cost_adjusted=request.target in _COST_ADJUSTED_TARGETS,
        fold_artifact_fingerprints=tuple(
            sorted(
                (
                    result.fold.name,
                    result.model.artifact_fingerprint_sha256,
                )
                for result in generalization_run.fold_results
            )
        ),
        context_fingerprint_sha256=(
            fast_forecast_context_fingerprint_sha256(canonical_contexts)
        ),
        overall=overall,
        fold_populations=fold_populations,
        regime_populations=regime_populations,
        strategy_family_populations=strategy_populations,
        liquidity_bucket_populations=liquidity_populations,
        cost_bucket_populations=cost_populations,
        evaluation_report_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        evaluation_report_fingerprint_sha256=(
            fast_forecast_evaluation_report_fingerprint_sha256(
                provisional
            )
        ),
    )


def _validate_v2_fold_models(
    run: FastChronologicalGeneralizationRun,
) -> None:
    request = run.training_request
    seen: set[str] = set()
    for result in run.fold_results:
        if result.fold.name in seen:
            raise ValueError(
                "V2 generalization run contains duplicate fold names"
            )
        seen.add(result.fold.name)
        model = result.model
        if (
            model.model_version != request.model_version
            or model.model_family is not request.model_family
            or model.target is not request.target
            or model.target_kind is not request.target.kind
            or model.horizon_ms != request.horizon_ms
        ):
            raise ValueError(
                "V2 fold model contradicts the training request"
            )
        if (
            model.training_bundle_fingerprint_sha256
            != run.training_bundle_fingerprint_sha256
        ):
            raise ValueError(
                "V2 fold model bundle fingerprint contradicts run"
            )


def _canonical_v2_contexts(
    run: FastChronologicalGeneralizationRun,
    contexts: tuple[FastForecastEvaluationContext, ...],
) -> tuple[FastForecastEvaluationContext, ...]:
    if not isinstance(contexts, tuple):
        raise ValueError("contexts must be a tuple")
    if not all(
        type(value) is FastForecastEvaluationContext
        for value in contexts
    ):
        raise ValueError(
            "contexts must contain exact FastForecastEvaluationContext values"
        )

    expected: set[tuple[object, ...]] = set()
    for result in run.fold_results:
        for prediction in (
            *result.validation_predictions,
            *result.test_predictions,
        ):
            identity = prediction.decision_identity
            if identity in expected:
                raise ValueError(
                    "V2 validation/TEST predictions contain duplicate identity"
                )
            expected.add(identity)

    actual: set[tuple[object, ...]] = set()
    for value in contexts:
        if value.decision_identity in actual:
            raise ValueError(
                "evaluation contexts contain duplicate decision identity"
            )
        actual.add(value.decision_identity)

    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        detail = "missing" if missing else "extra"
        raise ValueError(
            f"V2 evaluation context coverage is incompatible: "
            f"{detail} identities"
        )
    return tuple(sorted(contexts, key=_context_sort_key))


def _selected_v2_test_predictions(
    run: FastChronologicalGeneralizationRun,
    *,
    unseen_mint_only: bool,
) -> tuple[tuple[str, FastForecastPrediction], ...]:
    values: list[tuple[str, FastForecastPrediction]] = []
    seen: set[tuple[object, ...]] = set()

    for result in run.fold_results:
        unseen = set(result.test_novelty.unseen_mint_identities)
        found_unseen: set[tuple[object, ...]] = set()
        for prediction in result.test_predictions:
            if type(prediction) is not FastForecastPrediction:
                raise ValueError(
                    "V2 TEST predictions must be exact FastForecastPrediction values"
                )
            identity = prediction.decision_identity
            if identity in seen:
                raise ValueError(
                    "V2 TEST contains duplicate prediction identity"
                )
            seen.add(identity)
            if identity in unseen:
                found_unseen.add(identity)
            if unseen_mint_only and identity not in unseen:
                continue
            values.append((result.fold.name, prediction))
        if found_unseen != unseen:
            raise ValueError(
                "V2 unseen-mint TEST identities do not reconcile "
                "to natural TEST predictions"
            )

    values.sort(
        key=lambda item: (
            item[1].decision_identity[6],
            item[1].decision_identity[2],
            item[1].decision_identity[0],
            item[1].decision_identity[1],
            item[0],
        )
    )
    return tuple(values)


def _selected_v2_test_observations(
    *,
    bundle: FastTrainingBundle,
    generalization_run: FastChronologicalGeneralizationRun,
    context_by_identity: dict[
        tuple[object, ...], FastForecastEvaluationContext
    ],
    unseen_mint_only: bool,
) -> tuple[_ScoredPrediction, ...]:
    request = generalization_run.training_request
    label_version = bundle.manifest.future_path_label_version
    labels: dict[tuple[tuple[object, ...], int, int], object] = {}
    for label in bundle.future_path_labels.labels:
        key = (
            label.decision_identity,
            label.horizon_ms,
            label.label_version,
        )
        if key in labels:
            raise ValueError(
                "FL4 bundle contains duplicate decision/horizon/version row"
            )
        labels[key] = label

    observations: list[_ScoredPrediction] = []
    for fold_name, prediction in _selected_v2_test_predictions(
        generalization_run,
        unseen_mint_only=unseen_mint_only,
    ):
        if (
            prediction.model_version != request.model_version
            or prediction.target is not request.target
            or prediction.horizon_ms != request.horizon_ms
        ):
            raise ValueError(
                "V2 TEST prediction contradicts training request"
            )
        predicted = float(prediction.predicted_value)
        if not math.isfinite(predicted):
            raise ValueError("V2 TEST prediction must be finite")
        if (
            request.target.kind is FastForecastTargetKind.BINARY
            and not 0.0 <= predicted <= 1.0
        ):
            raise ValueError(
                "binary V2 TEST prediction must lie within [0, 1]"
            )

        identity = prediction.decision_identity
        label = labels.get(
            (identity, request.horizon_ms, label_version)
        )
        if label is None:
            raise ValueError(
                "V2 TEST prediction has no exact FL4 target row"
            )
        context = context_by_identity.get(identity)
        if context is None:
            raise ValueError(
                "V2 TEST prediction is missing evaluation context"
            )
        observations.append(
            _ScoredPrediction(
                fold_name=fold_name,
                prediction=prediction,
                actual_value=_selected_target_value(
                    label,
                    request.target,
                ),
                context=context,
            )
        )

    observations.sort(key=_observation_sort_key)
    return tuple(observations)
