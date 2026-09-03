from __future__ import annotations

from dataclasses import dataclass, replace
import math

from shreks_brain.fast_learning.models import (
    FastForecastPrediction,
    FastForecastTarget,
    FastForecastTargetKind,
)
from shreks_brain.fast_validation.models import FastChronologicalValidationRun
from shreks_brain.research.fast_training_bundle import FastTrainingBundle

from .models import (
    FAST_FORECAST_EVALUATION_SCHEMA_NAME,
    FAST_FORECAST_EVALUATION_SCHEMA_VERSION,
    FastBinaryForecastMetrics,
    FastCalibrationBucket,
    FastContinuousForecastMetrics,
    FastForecastEvaluationContext,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
    FastForecastEvaluationReport,
    FastForecastMetricPopulation,
    fast_forecast_context_fingerprint_sha256,
    fast_forecast_evaluation_report_fingerprint_sha256,
)


_COST_ADJUSTED_TARGETS = frozenset(
    {
        FastForecastTarget.BEST_COST_ADJUSTED_RETURN_BPS,
        FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
    }
)


@dataclass(frozen=True, slots=True)
class _ScoredPrediction:
    fold_name: str
    prediction: FastForecastPrediction
    actual_value: float | None
    context: FastForecastEvaluationContext


def evaluate_fast_forecasts(
    bundle: FastTrainingBundle,
    validation_run: FastChronologicalValidationRun,
    contexts: tuple[FastForecastEvaluationContext, ...],
    policy: FastForecastEvaluationPolicy,
) -> FastForecastEvaluationReport:
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be an exact FastTrainingBundle")
    if type(validation_run) is not FastChronologicalValidationRun:
        raise ValueError("validation_run must be an exact FastChronologicalValidationRun")
    if type(policy) is not FastForecastEvaluationPolicy:
        raise ValueError("policy must be an exact FastForecastEvaluationPolicy")
    if bundle.manifest.bundle_fingerprint_sha256 != validation_run.training_bundle_fingerprint_sha256:
        raise ValueError("FL8.1 bundle fingerprint does not match FL8.3 validation run")
    request = validation_run.training_request
    _validate_fold_models(validation_run)

    canonical_contexts = _canonical_contexts(validation_run, contexts)
    context_by_identity = {value.decision_identity: value for value in canonical_contexts}
    observations = _selected_observations(
        bundle=bundle,
        validation_run=validation_run,
        context_by_identity=context_by_identity,
        policy=policy,
    )
    if not observations:
        raise ValueError("selected forecast evaluation partition contains no predictions")
    if not any(value.actual_value is not None for value in observations):
        raise ValueError("selected forecast evaluation partition contains zero scorable observations")

    overall = _population("overall", observations, request.target.kind, policy)
    fold_populations = _group_populations(
        observations,
        key_fn=lambda value: (f"fold:{value.fold_name}",),
        kind=request.target.kind,
        policy=policy,
    )
    regime_populations = _group_populations(
        observations,
        key_fn=lambda value: (f"regime:{value.context.market_regime}",),
        kind=request.target.kind,
        policy=policy,
    )
    strategy_populations = _group_populations(
        observations,
        key_fn=lambda value: tuple(
            f"strategy:{family}" for family in value.context.strategy_families
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
        validation_policy_version=validation_run.validation_policy_version,
        validation_run_fingerprint_sha256=validation_run.validation_run_fingerprint_sha256,
        training_bundle_fingerprint_sha256=bundle.manifest.bundle_fingerprint_sha256,
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
                for result in validation_run.fold_results
            )
        ),
        context_fingerprint_sha256=fast_forecast_context_fingerprint_sha256(
            canonical_contexts
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
        evaluation_report_fingerprint_sha256=fast_forecast_evaluation_report_fingerprint_sha256(
            provisional
        ),
    )


def _validate_fold_models(validation_run: FastChronologicalValidationRun) -> None:
    request = validation_run.training_request
    seen_folds: set[str] = set()
    for result in validation_run.fold_results:
        if result.fold.name in seen_folds:
            raise ValueError("FL8.3 validation run contains duplicate fold names")
        seen_folds.add(result.fold.name)
        model = result.model
        if (
            model.model_version != request.model_version
            or model.model_family is not request.model_family
            or model.target is not request.target
            or model.target_kind is not request.target.kind
            or model.horizon_ms != request.horizon_ms
        ):
            raise ValueError("FL8.3 fold model contradicts the training request")
        if model.training_bundle_fingerprint_sha256 != validation_run.training_bundle_fingerprint_sha256:
            raise ValueError("FL8.3 fold model bundle fingerprint contradicts validation run")


def _canonical_contexts(
    validation_run: FastChronologicalValidationRun,
    contexts: tuple[FastForecastEvaluationContext, ...],
) -> tuple[FastForecastEvaluationContext, ...]:
    if not isinstance(contexts, tuple):
        raise ValueError("contexts must be a tuple")
    if not all(type(value) is FastForecastEvaluationContext for value in contexts):
        raise ValueError("contexts must contain exact FastForecastEvaluationContext values")
    expected: set[tuple[object, ...]] = set()
    for result in validation_run.fold_results:
        for prediction in (*result.validation_predictions, *result.test_predictions):
            identity = prediction.decision_identity
            if identity in expected:
                raise ValueError("FL8.3 validation/test predictions contain a duplicate identity")
            expected.add(identity)
    actual: set[tuple[object, ...]] = set()
    for value in contexts:
        if value.decision_identity in actual:
            raise ValueError("evaluation contexts contain a duplicate decision identity")
        actual.add(value.decision_identity)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        detail = "missing" if missing else "extra"
        raise ValueError(f"evaluation context coverage is incompatible: {detail} identities")
    return tuple(sorted(contexts, key=_context_sort_key))


def _selected_observations(
    *,
    bundle: FastTrainingBundle,
    validation_run: FastChronologicalValidationRun,
    context_by_identity: dict[tuple[object, ...], FastForecastEvaluationContext],
    policy: FastForecastEvaluationPolicy,
) -> tuple[_ScoredPrediction, ...]:
    request = validation_run.training_request
    label_version = bundle.manifest.future_path_label_version
    labels: dict[tuple[tuple[object, ...], int, int], object] = {}
    for label in bundle.future_path_labels.labels:
        key = (label.decision_identity, label.horizon_ms, label.label_version)
        if key in labels:
            raise ValueError("FL4 bundle contains duplicate decision/horizon/label-version rows")
        labels[key] = label

    values: list[_ScoredPrediction] = []
    seen_selected: set[tuple[object, ...]] = set()
    for result in validation_run.fold_results:
        predictions = (
            result.validation_predictions
            if policy.partition is FastForecastEvaluationPartition.VALIDATION
            else result.test_predictions
        )
        for prediction in predictions:
            if type(prediction) is not FastForecastPrediction:
                raise ValueError("selected predictions must be exact FastForecastPrediction values")
            identity = prediction.decision_identity
            if identity in seen_selected:
                raise ValueError("selected partition contains duplicate prediction identities")
            seen_selected.add(identity)
            if (
                prediction.model_version != request.model_version
                or prediction.target is not request.target
                or prediction.horizon_ms != request.horizon_ms
            ):
                raise ValueError("selected prediction contradicts validation training request")
            predicted = float(prediction.predicted_value)
            if not math.isfinite(predicted):
                raise ValueError("forecast prediction must be finite")
            if request.target.kind is FastForecastTargetKind.BINARY and not 0.0 <= predicted <= 1.0:
                raise ValueError("binary forecast prediction must lie within [0, 1]")
            key = (identity, request.horizon_ms, label_version)
            label = labels.get(key)
            if label is None:
                raise ValueError("selected prediction has no exact FL4 identity/horizon/label row")
            actual = _selected_target_value(label, request.target)
            context = context_by_identity.get(identity)
            if context is None:  # coverage validation should make this unreachable.
                raise ValueError("selected prediction is missing evaluation context")
            values.append(
                _ScoredPrediction(
                    fold_name=result.fold.name,
                    prediction=prediction,
                    actual_value=actual,
                    context=context,
                )
            )
    values.sort(key=_observation_sort_key)
    return tuple(values)


def _selected_target_value(label: object, target: FastForecastTarget) -> float | None:
    completeness = getattr(label, "completeness", None)
    value = getattr(label, target.value, None)
    if completeness != "complete" or value is None:
        return None
    if target.kind is FastForecastTargetKind.BINARY:
        if type(value) is not bool:
            raise ValueError("binary FL4 evaluation target must be an exact bool")
        return 1.0 if value else 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("continuous FL4 evaluation target must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("continuous FL4 evaluation target must be finite")
    return result


def _population(
    name: str,
    observations: tuple[_ScoredPrediction, ...],
    kind: FastForecastTargetKind,
    policy: FastForecastEvaluationPolicy,
) -> FastForecastMetricPopulation:
    scored = tuple(value for value in observations if value.actual_value is not None)
    prediction_count = len(observations)
    unavailable = prediction_count - len(scored)
    if not scored:
        return FastForecastMetricPopulation(
            name=name,
            prediction_count=prediction_count,
            scored_observation_count=0,
            target_unavailable_count=unavailable,
            continuous_metrics=None,
            binary_metrics=None,
        )
    if kind is FastForecastTargetKind.CONTINUOUS:
        continuous = _continuous_metrics(scored)
        binary = None
    else:
        continuous = None
        binary = _binary_metrics(scored, policy)
    return FastForecastMetricPopulation(
        name=name,
        prediction_count=prediction_count,
        scored_observation_count=len(scored),
        target_unavailable_count=unavailable,
        continuous_metrics=continuous,
        binary_metrics=binary,
    )


def _continuous_metrics(
    observations: tuple[_ScoredPrediction, ...],
) -> FastContinuousForecastMetrics:
    predicted = tuple(float(value.prediction.predicted_value) for value in observations)
    actual = tuple(float(value.actual_value) for value in observations)
    errors = tuple(p - a for p, a in zip(predicted, actual, strict=True))
    count = len(errors)
    mean_predicted = math.fsum(predicted) / count
    mean_actual = math.fsum(actual) / count
    return FastContinuousForecastMetrics(
        observation_count=count,
        mean_predicted_value=mean_predicted,
        mean_actual_value=mean_actual,
        mean_error=math.fsum(errors) / count,
        mean_absolute_error=math.fsum(abs(value) for value in errors) / count,
        root_mean_squared_error=math.sqrt(
            math.fsum(value * value for value in errors) / count
        ),
    )


def _binary_metrics(
    observations: tuple[_ScoredPrediction, ...],
    policy: FastForecastEvaluationPolicy,
) -> FastBinaryForecastMetrics:
    probabilities = tuple(float(value.prediction.predicted_value) for value in observations)
    actual = tuple(int(float(value.actual_value)) for value in observations)
    count = len(actual)
    bucket_values: list[list[tuple[float, int]]] = [
        [] for _ in range(policy.probability_bucket_count)
    ]
    for probability, outcome in zip(probabilities, actual, strict=True):
        index = min(
            int(probability * policy.probability_bucket_count),
            policy.probability_bucket_count - 1,
        )
        bucket_values[index].append((probability, outcome))
    buckets: list[FastCalibrationBucket] = []
    for index, values in enumerate(bucket_values):
        lower = index / policy.probability_bucket_count
        upper = (index + 1) / policy.probability_bucket_count
        if not values:
            buckets.append(
                FastCalibrationBucket(
                    bucket_index=index,
                    lower_probability=lower,
                    upper_probability=upper,
                    observation_count=0,
                    mean_predicted_probability=None,
                    observed_positive_rate=None,
                    absolute_calibration_gap=None,
                )
            )
            continue
        mean_probability = math.fsum(value[0] for value in values) / len(values)
        observed_rate = sum(value[1] for value in values) / len(values)
        buckets.append(
            FastCalibrationBucket(
                bucket_index=index,
                lower_probability=lower,
                upper_probability=upper,
                observation_count=len(values),
                mean_predicted_probability=mean_probability,
                observed_positive_rate=observed_rate,
                absolute_calibration_gap=abs(mean_probability - observed_rate),
            )
        )
    epsilon = policy.binary_log_loss_clip_epsilon
    clipped = tuple(min(max(value, epsilon), 1.0 - epsilon) for value in probabilities)
    return FastBinaryForecastMetrics(
        observation_count=count,
        positive_count=sum(actual),
        mean_predicted_probability=math.fsum(probabilities) / count,
        brier_score=math.fsum(
            (probability - outcome) ** 2
            for probability, outcome in zip(probabilities, actual, strict=True)
        )
        / count,
        log_loss=math.fsum(
            -(
                outcome * math.log(probability)
                + (1 - outcome) * math.log(1.0 - probability)
            )
            for probability, outcome in zip(clipped, actual, strict=True)
        )
        / count,
        expected_calibration_error=math.fsum(
            (bucket.absolute_calibration_gap or 0.0)
            * bucket.observation_count
            / count
            for bucket in buckets
        ),
        calibration_buckets=tuple(buckets),
    )


def _group_populations(
    observations: tuple[_ScoredPrediction, ...],
    *,
    key_fn,
    kind: FastForecastTargetKind,
    policy: FastForecastEvaluationPolicy,
) -> tuple[FastForecastMetricPopulation, ...]:
    groups: dict[str, list[_ScoredPrediction]] = {}
    for observation in observations:
        keys = key_fn(observation)
        if not isinstance(keys, tuple) or not keys:
            raise ValueError("evaluation segment key function returned no keys")
        if len(set(keys)) != len(keys):
            raise ValueError("one observation cannot repeat the same segment membership")
        for key in keys:
            groups.setdefault(key, []).append(observation)
    return tuple(
        _population(name, tuple(groups[name]), kind, policy)
        for name in sorted(groups)
    )


def _numeric_bucket_name(
    prefix: str,
    value: float | None,
    boundaries: tuple[float, ...],
) -> str:
    if value is None:
        return f"{prefix}:unknown"
    for index, boundary in enumerate(boundaries):
        if value < boundary:
            return f"{prefix}:{index}"
    return f"{prefix}:{len(boundaries)}"


def _context_sort_key(value: FastForecastEvaluationContext) -> tuple[object, ...]:
    identity = value.decision_identity
    return (identity[6], identity[2], identity[0], identity[1])


def _observation_sort_key(value: _ScoredPrediction) -> tuple[object, ...]:
    identity = value.prediction.decision_identity
    return (identity[6], identity[2], identity[0], identity[1], value.fold_name)
