from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fast_chronological_fixtures import (
    TEST_END,
    TEST_START,
    TRAINING_END,
    TRAINING_START,
    VALIDATION_END,
    VALIDATION_START,
    forecast_request,
)
from shreks_brain.fast_validation.models import (
    FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME,
    FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION,
    FastChronologicalFold,
    FastChronologicalValidationPolicy,
    FastLeakageQuarantineSummary,
)


def fold(name: str = "fold-a") -> FastChronologicalFold:
    return FastChronologicalFold(
        name=name,
        training_started_at_unix_ms=TRAINING_START,
        training_ended_at_unix_ms=TRAINING_END,
        validation_started_at_unix_ms=VALIDATION_START,
        validation_ended_at_unix_ms=VALIDATION_END,
        test_started_at_unix_ms=TEST_START,
        test_ended_at_unix_ms=TEST_END,
    )


def test_schema_constants_are_stable() -> None:
    assert FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME == "shreks.fast_lane_chronological_validation"
    assert FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION == 1


def test_fold_is_frozen_and_requires_strict_train_validation_test_order() -> None:
    value = fold()
    with pytest.raises(FrozenInstanceError):
        value.name = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="training|validation|order"):
        FastChronologicalFold(
            name="bad",
            training_started_at_unix_ms=1_000,
            training_ended_at_unix_ms=2_100,
            validation_started_at_unix_ms=2_000,
            validation_ended_at_unix_ms=2_500,
            test_started_at_unix_ms=3_000,
            test_ended_at_unix_ms=3_500,
        )
    with pytest.raises(ValueError, match="validation|test|order"):
        FastChronologicalFold(
            name="bad",
            training_started_at_unix_ms=1_000,
            training_ended_at_unix_ms=1_500,
            validation_started_at_unix_ms=2_000,
            validation_ended_at_unix_ms=3_100,
            test_started_at_unix_ms=3_000,
            test_ended_at_unix_ms=3_500,
        )


def test_policy_rejects_duplicate_names_and_overlapping_evaluation_intervals() -> None:
    with pytest.raises(ValueError, match="unique"):
        FastChronologicalValidationPolicy(version="v1", folds=(fold(), fold()))

    second = FastChronologicalFold(
        name="fold-b",
        training_started_at_unix_ms=1_000,
        training_ended_at_unix_ms=1_400,
        validation_started_at_unix_ms=2_250,
        validation_ended_at_unix_ms=2_600,
        test_started_at_unix_ms=3_500,
        test_ended_at_unix_ms=3_900,
    )
    with pytest.raises(ValueError, match="overlap|evaluation"):
        FastChronologicalValidationPolicy(version="v1", folds=(fold(), second))


def test_quarantine_summary_requires_non_negative_counts_and_sha256() -> None:
    summary = FastLeakageQuarantineSummary(
        shared_mint_count=1,
        shared_actor_count=2,
        shared_signature_count=3,
        training_quarantined_row_count=4,
        validation_quarantined_row_count=5,
        test_quarantined_row_count=6,
        quarantine_fingerprint_sha256="a" * 64,
    )
    assert summary.shared_actor_count == 2
    with pytest.raises(ValueError, match="non-negative"):
        FastLeakageQuarantineSummary(
            shared_mint_count=-1,
            shared_actor_count=0,
            shared_signature_count=0,
            training_quarantined_row_count=0,
            validation_quarantined_row_count=0,
            test_quarantined_row_count=0,
            quarantine_fingerprint_sha256="a" * 64,
        )
    with pytest.raises(ValueError, match="SHA-256"):
        FastLeakageQuarantineSummary(
            shared_mint_count=0,
            shared_actor_count=0,
            shared_signature_count=0,
            training_quarantined_row_count=0,
            validation_quarantined_row_count=0,
            test_quarantined_row_count=0,
            quarantine_fingerprint_sha256="bad",
        )


def test_policy_request_fixture_remains_exact_fl8_2_type() -> None:
    request = forecast_request()
    assert request.horizon_ms == 250
