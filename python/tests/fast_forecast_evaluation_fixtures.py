from __future__ import annotations

from fast_chronological_fixtures import (
    TEST_END,
    TEST_START,
    TRAINING_END,
    TRAINING_START,
    VALIDATION_END,
    VALIDATION_START,
    chronological_bundle,
    forecast_request,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationContext,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
)
from shreks_brain.fast_learning import FastForecastModelFamily, FastForecastTarget
from shreks_brain.fast_validation import (
    FastChronologicalFold,
    FastChronologicalValidationPolicy,
    run_fast_chronological_validation,
)
from shreks_brain.research.fast_training_bundle import FastTrainingBundle


def chronological_policy() -> FastChronologicalValidationPolicy:
    return FastChronologicalValidationPolicy(
        version="fl8-4-source-v1",
        folds=(
            FastChronologicalFold(
                name="fold-a",
                training_started_at_unix_ms=TRAINING_START,
                training_ended_at_unix_ms=TRAINING_END,
                validation_started_at_unix_ms=VALIDATION_START,
                validation_ended_at_unix_ms=VALIDATION_END,
                test_started_at_unix_ms=TEST_START,
                test_ended_at_unix_ms=TEST_END,
            ),
        ),
    )


def evaluation_policy(
    partition: FastForecastEvaluationPartition = FastForecastEvaluationPartition.VALIDATION,
) -> FastForecastEvaluationPolicy:
    return FastForecastEvaluationPolicy(
        version="fl8-4-eval-v1",
        partition=partition,
        probability_bucket_count=2,
        liquidity_capacity_quote_boundaries=(10.0, 100.0),
        round_trip_cost_bps_boundaries=(5.0, 10.0),
        binary_log_loss_clip_epsilon=1e-12,
    )


def build_run(
    *,
    family: FastForecastModelFamily = FastForecastModelFamily.MEAN_REGRESSOR,
    target: FastForecastTarget = FastForecastTarget.ENDPOINT_RETURN_BPS,
    bundle: FastTrainingBundle | None = None,
):
    source = chronological_bundle() if bundle is None else bundle
    request = forecast_request(family, target)
    return source, run_fast_chronological_validation(
        source,
        request,
        chronological_policy(),
    )


def evaluation_contexts(run) -> tuple[FastForecastEvaluationContext, ...]:
    predictions = tuple(
        prediction
        for result in run.fold_results
        for prediction in (*result.validation_predictions, *result.test_predictions)
    )
    predictions = tuple(
        sorted(
            predictions,
            key=lambda value: (
                value.decision_identity[6],
                value.decision_identity[2],
                value.decision_identity[0],
                value.decision_identity[1],
            ),
        )
    )
    liquidity = (5.0, 10.0, 100.0, None, 50.0, 150.0)
    costs = (0.0, 5.0, 10.0, None, 7.5, 25.0)
    contexts: list[FastForecastEvaluationContext] = []
    for index, prediction in enumerate(predictions):
        if index % 3 == 0:
            families = ("impulse-scalp",)
        elif index % 3 == 1:
            families = ("impulse-scalp", "micro-pullback")
        else:
            families = ("micro-pullback",)
        contexts.append(
            FastForecastEvaluationContext(
                decision_identity=prediction.decision_identity,
                as_of_unix_ms=prediction.decision_identity[6],
                market_regime="HOT" if index % 2 == 0 else "NORMAL",
                strategy_families=families,
                executable_exit_capacity_quote=liquidity[index],
                expected_round_trip_cost_bps=costs[index],
            )
        )
    return tuple(contexts)
