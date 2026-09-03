from __future__ import annotations

import pytest

from fast_chronological_fixtures import chronological_bundle
from fast_forecast_evaluation_fixtures import (
    build_run,
    evaluation_contexts,
    evaluation_policy,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationContext,
    FastForecastEvaluationPartition,
    evaluate_fast_forecasts,
)


def counts(populations) -> dict[str, int]:
    return {value.name: value.prediction_count for value in populations}


def test_required_segments_are_deterministic_and_reconcile() -> None:
    bundle, run = build_run()
    contexts = evaluation_contexts(run)
    report = evaluate_fast_forecasts(
        bundle,
        run,
        contexts,
        evaluation_policy(FastForecastEvaluationPartition.VALIDATION),
    )
    assert counts(report.fold_populations) == {"fold:fold-a": 3}
    assert counts(report.regime_populations) == {
        "regime:HOT": 2,
        "regime:NORMAL": 1,
    }
    # Strategy populations intentionally overlap. Three overall predictions
    # become four strategy memberships in this fixture.
    assert counts(report.strategy_family_populations) == {
        "strategy:impulse-scalp": 2,
        "strategy:micro-pullback": 2,
    }
    assert sum(counts(report.strategy_family_populations).values()) == 4
    assert report.overall.prediction_count == 3
    assert counts(report.liquidity_bucket_populations) == {
        "liquidity:0": 1,
        "liquidity:1": 1,
        "liquidity:2": 1,
    }
    assert counts(report.cost_bucket_populations) == {
        "cost:0": 1,
        "cost:1": 1,
        "cost:2": 1,
    }


def test_test_partition_exposes_unknown_context_bucket_instead_of_dropping_row() -> None:
    bundle, run = build_run()
    report = evaluate_fast_forecasts(
        bundle,
        run,
        evaluation_contexts(run),
        evaluation_policy(FastForecastEvaluationPartition.TEST),
    )
    assert counts(report.liquidity_bucket_populations) == {
        "liquidity:1": 1,
        "liquidity:2": 1,
        "liquidity:unknown": 1,
    }
    assert counts(report.cost_bucket_populations) == {
        "cost:1": 1,
        "cost:2": 1,
        "cost:unknown": 1,
    }


def test_context_must_cover_all_validation_and_test_predictions_exactly() -> None:
    bundle, run = build_run()
    contexts = evaluation_contexts(run)
    with pytest.raises(ValueError, match="context|missing|coverage"):
        evaluate_fast_forecasts(bundle, run, contexts[:-1], evaluation_policy())
    with pytest.raises(ValueError, match="context|duplicate|identity"):
        evaluate_fast_forecasts(
            bundle,
            run,
            (*contexts, contexts[0]),
            evaluation_policy(),
        )
    extra = FastForecastEvaluationContext(
        decision_identity=("extra", 0, 999, "mint", "quote", "venue", 9_999),
        as_of_unix_ms=9_999,
        market_regime="HOT",
        strategy_families=("impulse-scalp",),
        executable_exit_capacity_quote=1.0,
        expected_round_trip_cost_bps=1.0,
    )
    with pytest.raises(ValueError, match="context|extra|coverage"):
        evaluate_fast_forecasts(
            bundle,
            run,
            (*contexts, extra),
            evaluation_policy(),
        )


def test_context_input_order_is_non_semantic() -> None:
    bundle, run = build_run()
    contexts = evaluation_contexts(run)
    first = evaluate_fast_forecasts(bundle, run, contexts, evaluation_policy())
    second = evaluate_fast_forecasts(bundle, run, tuple(reversed(contexts)), evaluation_policy())
    assert first == second


def test_validation_label_only_change_cannot_change_test_metric_payloads() -> None:
    original_bundle = chronological_bundle()
    changed_bundle = chronological_bundle(validation_target_shift=9_999.0)
    original_bundle, original_run = build_run(bundle=original_bundle)
    changed_bundle, changed_run = build_run(bundle=changed_bundle)

    first = evaluate_fast_forecasts(
        original_bundle,
        original_run,
        evaluation_contexts(original_run),
        evaluation_policy(FastForecastEvaluationPartition.TEST),
    )
    second = evaluate_fast_forecasts(
        changed_bundle,
        changed_run,
        evaluation_contexts(changed_run),
        evaluation_policy(FastForecastEvaluationPartition.TEST),
    )
    assert first.overall == second.overall
    assert first.fold_populations == second.fold_populations
    assert first.regime_populations == second.regime_populations
    assert first.strategy_family_populations == second.strategy_family_populations
    assert first.liquidity_bucket_populations == second.liquidity_bucket_populations
    assert first.cost_bucket_populations == second.cost_bucket_populations
    # Whole-source provenance intentionally remains different.
    assert first.validation_run_fingerprint_sha256 != second.validation_run_fingerprint_sha256
    assert first.evaluation_report_fingerprint_sha256 != second.evaluation_report_fingerprint_sha256
