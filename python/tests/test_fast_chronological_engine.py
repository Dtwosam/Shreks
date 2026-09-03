from __future__ import annotations

from dataclasses import replace

import pytest

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
from shreks_brain.fast_validation import (
    FastChronologicalFold,
    FastChronologicalValidationPolicy,
    run_fast_chronological_validation,
)


def fold(
    name: str = "fold-a",
    *,
    validation_start: int = VALIDATION_START,
    validation_end: int = VALIDATION_END,
    test_start: int = TEST_START,
    test_end: int = TEST_END,
) -> FastChronologicalFold:
    return FastChronologicalFold(
        name=name,
        training_started_at_unix_ms=TRAINING_START,
        training_ended_at_unix_ms=TRAINING_END,
        validation_started_at_unix_ms=validation_start,
        validation_ended_at_unix_ms=validation_end,
        test_started_at_unix_ms=test_start,
        test_ended_at_unix_ms=test_end,
    )


def policy(*folds: FastChronologicalFold) -> FastChronologicalValidationPolicy:
    return FastChronologicalValidationPolicy(version="fl8-3-test-v1", folds=folds or (fold(),))


def test_clean_fold_trains_only_training_rows_and_predicts_validation_and_test() -> None:
    run = run_fast_chronological_validation(chronological_bundle(), forecast_request(), policy())
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
    assert result.quarantine.shared_mint_count == 0
    assert result.quarantine.shared_actor_count == 0
    assert result.quarantine.shared_signature_count == 0


def test_training_horizon_must_have_elapsed_by_validation_start() -> None:
    early_validation = fold(validation_start=1_700, validation_end=VALIDATION_END)
    run = run_fast_chronological_validation(
        chronological_bundle(), forecast_request(), policy(early_validation)
    )
    result = run.fold_results[0]
    assert result.training_row_count == 6
    assert result.model.training_row_count == 5
    assert result.training_target_unavailable_at_split_count == 1


def test_incomplete_training_target_is_excluded_not_zero_filled() -> None:
    run = run_fast_chronological_validation(
        chronological_bundle(incomplete_training_index=5),
        forecast_request(),
        policy(),
    )
    result = run.fold_results[0]
    assert result.training_row_count == 6
    assert result.model.training_row_count == 5
    assert result.training_target_unavailable_at_split_count == 1


@pytest.mark.parametrize(
    ("kwargs", "field", "expected_counts"),
    (
        ({"shared_mint": True}, "shared_mint_count", (5, 2, 3)),
        ({"shared_actor": True}, "shared_actor_count", (5, 3, 2)),
        ({"shared_signature": True}, "shared_signature_count", (5, 2, 3)),
    ),
)
def test_shared_group_keys_quarantine_every_affected_row(
    kwargs: dict[str, bool], field: str, expected_counts: tuple[int, int, int]
) -> None:
    run = run_fast_chronological_validation(
        chronological_bundle(**kwargs), forecast_request(), policy()
    )
    result = run.fold_results[0]
    assert getattr(result.quarantine, field) == 1
    assert (
        result.training_row_count,
        result.validation_row_count,
        result.test_row_count,
    ) == expected_counts


def test_union_of_shared_mint_actor_and_signature_is_quarantined() -> None:
    run = run_fast_chronological_validation(
        chronological_bundle(shared_mint=True, shared_actor=True, shared_signature=True),
        forecast_request(),
        policy(),
    )
    result = run.fold_results[0]
    assert result.quarantine.shared_mint_count == 1
    assert result.quarantine.shared_actor_count == 1
    assert result.quarantine.shared_signature_count == 1
    assert result.training_row_count == 3
    assert result.validation_row_count == 1
    assert result.test_row_count == 2


def test_validation_and_test_target_changes_do_not_change_training_fit_or_predictions() -> None:
    original = run_fast_chronological_validation(
        chronological_bundle(), forecast_request(), policy()
    )
    changed = run_fast_chronological_validation(
        chronological_bundle(validation_target_shift=9_999.0, test_target_shift=-9_999.0),
        forecast_request(),
        policy(),
    )
    first = original.fold_results[0]
    second = changed.fold_results[0]
    assert first.model.feature_transforms == second.model.feature_transforms
    assert first.model.coefficients == second.model.coefficients
    assert first.model.intercept == second.model.intercept
    assert first.model.constant_prediction == second.model.constant_prediction
    assert first.validation_predictions == second.validation_predictions
    assert first.test_predictions == second.test_predictions
    # Sealed FL8.2 fingerprints intentionally retain the whole source-bundle
    # provenance, so source-only target mutations remain auditable even though
    # they cannot alter the fitted parameters or predictions for this fold.
    assert original.training_bundle_fingerprint_sha256 != changed.training_bundle_fingerprint_sha256
    assert first.model.training_data_fingerprint_sha256 != second.model.training_data_fingerprint_sha256
    assert first.model.artifact_fingerprint_sha256 != second.model.artifact_fingerprint_sha256
    assert original.validation_run_fingerprint_sha256 != changed.validation_run_fingerprint_sha256


def test_fold_input_order_does_not_change_canonical_result() -> None:
    first = FastChronologicalFold(
        name="first",
        training_started_at_unix_ms=TRAINING_START,
        training_ended_at_unix_ms=TRAINING_END,
        validation_started_at_unix_ms=2_000,
        validation_ended_at_unix_ms=2_100,
        test_started_at_unix_ms=3_000,
        test_ended_at_unix_ms=3_100,
    )
    second = FastChronologicalFold(
        name="second",
        training_started_at_unix_ms=TRAINING_START,
        training_ended_at_unix_ms=TRAINING_END,
        validation_started_at_unix_ms=2_100,
        validation_ended_at_unix_ms=2_300,
        test_started_at_unix_ms=3_100,
        test_ended_at_unix_ms=3_300,
    )
    bundle = chronological_bundle()
    request = forecast_request()
    ordered = run_fast_chronological_validation(bundle, request, policy(first, second))
    reversed_run = run_fast_chronological_validation(bundle, request, policy(second, first))
    assert ordered == reversed_run


def test_post_quarantine_empty_partition_fails_closed() -> None:
    bundle = chronological_bundle(shared_mint=True)
    shared = bundle.features.records[0].mint
    records = tuple(
        replace(record, mint=shared)
        if VALIDATION_START <= record.decision_observed_at_unix_ms < VALIDATION_END
        else record
        for record in bundle.features.records
    )
    # The exact bundle has already been validated by FL8.1 construction in normal use;
    # this direct mutation is only a malformed-input probe and must fail closed somewhere.
    malformed = replace(bundle, features=replace(bundle.features, records=records))
    with pytest.raises(ValueError, match="fingerprint|quarantine|empty|bundle"):
        run_fast_chronological_validation(malformed, forecast_request(), policy())
