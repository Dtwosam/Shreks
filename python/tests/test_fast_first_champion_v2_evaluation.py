from __future__ import annotations

from fast_chronological_fixtures import (
    chronological_bundle,
    forecast_request,
)
from fast_chronological_v2_fixtures import v2_bundle, v2_policy
from fast_forecast_evaluation_fixtures import (
    chronological_policy,
    evaluation_contexts,
    evaluation_policy,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    evaluate_fast_forecasts,
)
from shreks_brain.fast_first_champion_v2.evaluation import (
    _selected_v2_test_predictions,
    evaluate_fast_first_champion_v2_test,
)
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
)
from shreks_brain.fast_validation import run_fast_chronological_validation
from shreks_brain.fast_validation_v2 import (
    run_fast_chronological_generalization,
)


def _request():
    return forecast_request(
        FastForecastModelFamily.MEAN_REGRESSOR,
        FastForecastTarget.ENDPOINT_RETURN_BPS,
    )


def test_natural_v2_test_metric_semantics_match_fl8_4() -> None:
    bundle = chronological_bundle()
    request = _request()
    v1_run = run_fast_chronological_validation(
        bundle,
        request,
        chronological_policy(),
    )
    v2_run = run_fast_chronological_generalization(
        bundle,
        request,
        v2_policy(),
    )
    policy = evaluation_policy(FastForecastEvaluationPartition.TEST)

    v1 = evaluate_fast_forecasts(
        bundle,
        v1_run,
        evaluation_contexts(v1_run),
        policy,
    )
    v2 = evaluate_fast_first_champion_v2_test(
        bundle,
        v2_run,
        evaluation_contexts(v2_run),
        policy,
        unseen_mint_only=False,
    )

    assert v2.overall == v1.overall
    assert v2.fold_populations[0].prediction_count == (
        v1.fold_populations[0].prediction_count
    )
    assert v2.regime_populations == v1.regime_populations
    assert v2.strategy_family_populations == (
        v1.strategy_family_populations
    )
    assert v2.liquidity_bucket_populations == (
        v1.liquidity_bucket_populations
    )
    assert v2.cost_bucket_populations == v1.cost_bucket_populations


def test_unseen_mint_test_reuses_exact_natural_prediction_objects() -> None:
    bundle = v2_bundle()
    run = run_fast_chronological_generalization(
        bundle,
        _request(),
        v2_policy(),
    )

    natural = _selected_v2_test_predictions(
        run,
        unseen_mint_only=False,
    )
    unseen = _selected_v2_test_predictions(
        run,
        unseen_mint_only=True,
    )
    natural_by_identity = {
        prediction.decision_identity: prediction
        for _, prediction in natural
    }

    expected = run.fold_results[0].test_novelty.unseen_mint_identities
    assert tuple(
        prediction.decision_identity for _, prediction in unseen
    ) == expected
    assert all(
        prediction is natural_by_identity[prediction.decision_identity]
        for _, prediction in unseen
    )


def test_natural_and_unseen_reports_use_expected_test_populations() -> None:
    bundle = v2_bundle()
    run = run_fast_chronological_generalization(
        bundle,
        _request(),
        v2_policy(),
    )
    contexts = evaluation_contexts(run)
    policy = evaluation_policy(FastForecastEvaluationPartition.TEST)

    natural = evaluate_fast_first_champion_v2_test(
        bundle,
        run,
        contexts,
        policy,
        unseen_mint_only=False,
    )
    unseen = evaluate_fast_first_champion_v2_test(
        bundle,
        run,
        contexts,
        policy,
        unseen_mint_only=True,
    )

    result = run.fold_results[0]
    assert natural.overall.prediction_count == len(result.test_predictions)
    assert unseen.overall.prediction_count == len(
        result.test_novelty.unseen_mint_identities
    )
    assert unseen.overall.prediction_count < natural.overall.prediction_count


def test_v2_evaluation_requires_exact_context_coverage() -> None:
    bundle = v2_bundle()
    run = run_fast_chronological_generalization(
        bundle,
        _request(),
        v2_policy(),
    )
    contexts = evaluation_contexts(run)
    policy = evaluation_policy(FastForecastEvaluationPartition.TEST)

    import pytest

    with pytest.raises(ValueError, match="context.*missing"):
        evaluate_fast_first_champion_v2_test(
            bundle,
            run,
            contexts[:-1],
            policy,
            unseen_mint_only=False,
        )
