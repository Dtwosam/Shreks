from __future__ import annotations

from dataclasses import replace

import pytest

from fast_chronological_fixtures import (
    VALIDATION_END,
    forecast_request,
)
from fast_chronological_v2_fixtures import v2_bundle, v2_policy
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
)
from shreks_brain.fast_validation_v2.engine import (
    run_fast_chronological_generalization,
)


def test_clean_v2_run_trains_mature_rows_and_predicts_natural_future() -> None:
    run = run_fast_chronological_generalization(
        v2_bundle(),
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        v2_policy(),
    )
    result = run.fold_results[0]

    assert result.training_raw_row_count == 6
    assert result.training_row_count == 6
    assert result.training_target_unavailable_at_split_count == 0
    assert result.validation_raw_row_count == 3
    assert result.validation_row_count == 3
    assert result.test_raw_row_count == 3
    assert result.test_row_count == 3
    assert result.model.training_row_count == 6
    assert len(result.validation_predictions) == 3
    assert len(result.test_predictions) == 3


def test_recurring_mint_and_actor_remain_in_future_predictions() -> None:
    bundle = v2_bundle()
    run = run_fast_chronological_generalization(
        bundle,
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        v2_policy(),
    )
    result = run.fold_results[0]
    training = tuple(
        record
        for record in bundle.features.records
        if record.decision_observed_at_unix_ms
        < result.fold.training_ended_at_unix_ms
    )
    training_mints = {record.mint for record in training}
    training_actors = {
        record.decision_actor
        for record in training
        if record.decision_actor is not None
    }
    by_identity = {
        record.decision_identity: record
        for record in bundle.features.records
    }

    assert any(
        by_identity[prediction.decision_identity].mint in training_mints
        for prediction in result.validation_predictions
    )
    assert any(
        by_identity[prediction.decision_identity].decision_actor
        in training_actors
        for prediction in result.test_predictions
        if by_identity[prediction.decision_identity].decision_actor
        is not None
    )


def test_shared_signature_is_absent_from_all_v2_predictions_and_fit() -> None:
    bundle = v2_bundle(shared_signature=True)
    shared = bundle.features.records[2].decision_signature
    run = run_fast_chronological_generalization(
        bundle,
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        v2_policy(),
    )
    result = run.fold_results[0]

    assert result.signature_quarantine.shared_signature_count == 1
    assert all(
        prediction.decision_identity[0] != shared
        for prediction in (
            *result.validation_predictions,
            *result.test_predictions,
        )
    )
    assert result.model.training_row_count == 5


def test_validation_and_test_target_mutations_do_not_change_fit_or_predictions() -> None:
    request = forecast_request(
        FastForecastModelFamily.RIDGE_REGRESSION,
        FastForecastTarget.ENDPOINT_RETURN_BPS,
    )
    original = run_fast_chronological_generalization(
        v2_bundle(),
        request,
        v2_policy(),
    )
    changed = run_fast_chronological_generalization(
        v2_bundle(
            validation_target_shift=9_999.0,
            test_target_shift=-9_999.0,
        ),
        request,
        v2_policy(),
    )

    first = original.fold_results[0]
    second = changed.fold_results[0]

    assert first.fold == second.fold
    assert first.signature_quarantine == second.signature_quarantine
    assert first.validation_novelty == second.validation_novelty
    assert first.test_novelty == second.test_novelty
    assert first.model.feature_transforms == second.model.feature_transforms
    assert first.model.coefficients == second.model.coefficients
    assert first.model.intercept == second.model.intercept
    assert first.validation_predictions == second.validation_predictions
    assert first.test_predictions == second.test_predictions


def test_training_horizon_maturity_remains_enforced() -> None:
    policy = v2_policy()
    fold = replace(
        policy.folds[0],
        validation_started_at_unix_ms=1_700,
        validation_ended_at_unix_ms=VALIDATION_END,
    )
    policy = replace(policy, folds=(fold,))

    run = run_fast_chronological_generalization(
        v2_bundle(),
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        policy,
    )
    result = run.fold_results[0]

    assert result.training_row_count == 6
    assert result.model.training_row_count == 5
    assert result.training_target_unavailable_at_split_count == 1


def test_incomplete_training_target_is_excluded_not_zero_filled() -> None:
    run = run_fast_chronological_generalization(
        v2_bundle(incomplete_training_index=5),
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        v2_policy(),
    )
    result = run.fold_results[0]

    assert result.training_row_count == 6
    assert result.model.training_row_count == 5
    assert result.training_target_unavailable_at_split_count == 1


def test_unseen_mint_identities_reference_same_natural_predictions() -> None:
    run = run_fast_chronological_generalization(
        v2_bundle(),
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        v2_policy(),
    )
    result = run.fold_results[0]

    validation_unseen = set(
        result.validation_novelty.unseen_mint_identities
    )
    test_unseen = set(result.test_novelty.unseen_mint_identities)

    assert tuple(
        prediction.decision_identity
        for prediction in result.validation_predictions
        if prediction.decision_identity in validation_unseen
    ) == result.validation_novelty.unseen_mint_identities
    assert tuple(
        prediction.decision_identity
        for prediction in result.test_predictions
        if prediction.decision_identity in test_unseen
    ) == result.test_novelty.unseen_mint_identities


@pytest.mark.parametrize(
    ("family", "target"),
    (
        (
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        (
            FastForecastModelFamily.RIDGE_REGRESSION,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        (
            FastForecastModelFamily.PRIOR_CLASSIFIER,
            FastForecastTarget.REVERSAL_OCCURRED,
        ),
        (
            FastForecastModelFamily.LOGISTIC_REGRESSION,
            FastForecastTarget.REVERSAL_OCCURRED,
        ),
    ),
)
def test_all_four_fl8_2_model_families_run_through_v2(
    family: FastForecastModelFamily,
    target: FastForecastTarget,
) -> None:
    run = run_fast_chronological_generalization(
        v2_bundle(),
        forecast_request(family, target),
        v2_policy(),
    )
    result = run.fold_results[0]
    assert result.validation_predictions
    assert result.test_predictions


def test_fold_input_order_produces_canonical_run_order() -> None:
    policy = v2_policy()
    run = run_fast_chronological_generalization(
        v2_bundle(),
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        policy,
    )
    assert run.fold_results[0].fold == policy.folds[0]
