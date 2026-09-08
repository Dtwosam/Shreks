from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from fast_chronological_fixtures import forecast_request
from fast_chronological_v2_fixtures import v2_bundle, v2_policy
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
)
from shreks_brain.fast_validation import FastChronologicalFold
from shreks_brain.fast_validation_v2.engine import (
    run_fast_chronological_generalization,
)
from shreks_brain.fast_validation_v2 import (
    FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
    FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME,
    FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION,
    FastChronologicalGeneralizationPolicy,
    FastFutureNoveltySummary,
    FastSignatureQuarantineSummary,
)


def _fold(name: str = "v2-fold") -> FastChronologicalFold:
    return FastChronologicalFold(
        name=name,
        training_started_at_unix_ms=1_000,
        training_ended_at_unix_ms=2_000,
        validation_started_at_unix_ms=2_000,
        validation_ended_at_unix_ms=3_000,
        test_started_at_unix_ms=3_000,
        test_ended_at_unix_ms=4_000,
    )


def _policy(**overrides):
    values = dict(
        version=FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
        folds=(_fold(),),
        feature_identity_firewall_version="fl8.3-feature-identity-firewall-v1",
        feature_identity_firewall_fingerprint_sha256="a" * 64,
        minimum_unseen_mint_validation_rows=1,
        minimum_unseen_mint_validation_mints=1,
        minimum_unseen_mint_test_rows=1,
        minimum_unseen_mint_test_mints=1,
    )
    values.update(overrides)
    return FastChronologicalGeneralizationPolicy(**values)


def test_v2_schema_and_policy_versions_are_explicit() -> None:
    assert FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME == (
        "shreks.fast_lane_chronological_generalization"
    )
    assert FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION == 1
    assert FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION == (
        "fl8.3-chronological-generalization-v2"
    )


def test_v2_policy_is_frozen_and_requires_positive_novelty_floors() -> None:
    policy = _policy()
    with pytest.raises(FrozenInstanceError):
        policy.version = "changed"  # type: ignore[misc]

    for field in (
        "minimum_unseen_mint_validation_rows",
        "minimum_unseen_mint_validation_mints",
        "minimum_unseen_mint_test_rows",
        "minimum_unseen_mint_test_mints",
    ):
        with pytest.raises(ValueError, match="unseen|positive"):
            _policy(**{field: 0})


def test_v2_policy_rejects_wrong_version_and_bad_firewall_digest() -> None:
    with pytest.raises(ValueError, match="version"):
        _policy(version="wrong")
    with pytest.raises(ValueError, match="SHA-256|fingerprint"):
        _policy(feature_identity_firewall_fingerprint_sha256="bad")


def test_signature_quarantine_summary_validates_counts_and_digest() -> None:
    summary = FastSignatureQuarantineSummary(
        shared_signature_count=1,
        training_quarantined_row_count=2,
        validation_quarantined_row_count=3,
        test_quarantined_row_count=4,
        quarantine_fingerprint_sha256="b" * 64,
    )
    assert summary.shared_signature_count == 1

    with pytest.raises(ValueError, match="non-negative"):
        FastSignatureQuarantineSummary(
            shared_signature_count=-1,
            training_quarantined_row_count=0,
            validation_quarantined_row_count=0,
            test_quarantined_row_count=0,
            quarantine_fingerprint_sha256="b" * 64,
        )


def test_future_novelty_summary_reconciles_rows_and_actor_categories() -> None:
    unseen = (
        ("sig-u", 0, 1, "mint-u", "quote", "pump_swap", 2_100),
    )
    seen = (
        ("sig-s", 0, 2, "mint-s", "quote", "pump_swap", 2_200),
    )
    value = FastFutureNoveltySummary(
        partition="validation",
        prediction_count=2,
        unique_mint_count=2,
        unseen_mint_identities=unseen,
        seen_mint_identities=seen,
        unseen_mint_unique_mint_count=1,
        seen_actor_row_count=1,
        unseen_actor_row_count=1,
        null_actor_row_count=0,
        novelty_fingerprint_sha256="c" * 64,
    )
    assert value.prediction_count == 2

    with pytest.raises(ValueError, match="reconcile|actor"):
        FastFutureNoveltySummary(
            partition="validation",
            prediction_count=2,
            unique_mint_count=2,
            unseen_mint_identities=unseen,
            seen_mint_identities=seen,
            unseen_mint_unique_mint_count=1,
            seen_actor_row_count=2,
            unseen_actor_row_count=1,
            null_actor_row_count=0,
            novelty_fingerprint_sha256="c" * 64,
        )


def test_future_novelty_summary_requires_canonical_unique_identities() -> None:
    identity = ("sig", 0, 1, "mint", "quote", "pump_swap", 2_100)
    with pytest.raises(ValueError, match="unique|disjoint"):
        FastFutureNoveltySummary(
            partition="test",
            prediction_count=2,
            unique_mint_count=1,
            unseen_mint_identities=(identity,),
            seen_mint_identities=(identity,),
            unseen_mint_unique_mint_count=1,
            seen_actor_row_count=0,
            unseen_actor_row_count=2,
            null_actor_row_count=0,
            novelty_fingerprint_sha256="d" * 64,
        )


def test_future_novelty_summary_reconciles_unique_mint_counts() -> None:
    unseen = (
        ("sig-u", 0, 1, "mint-u", "quote", "pump_swap", 2_100),
    )
    seen = (
        ("sig-s", 0, 2, "mint-s", "quote", "pump_swap", 2_200),
    )
    with pytest.raises(ValueError, match="mint.*reconcile|unique mint"):
        FastFutureNoveltySummary(
            partition="validation",
            prediction_count=2,
            unique_mint_count=1,
            unseen_mint_identities=unseen,
            seen_mint_identities=seen,
            unseen_mint_unique_mint_count=1,
            seen_actor_row_count=1,
            unseen_actor_row_count=1,
            null_actor_row_count=0,
            novelty_fingerprint_sha256="e" * 64,
        )

    with pytest.raises(ValueError, match="unseen.*mint"):
        FastFutureNoveltySummary(
            partition="validation",
            prediction_count=2,
            unique_mint_count=2,
            unseen_mint_identities=unseen,
            seen_mint_identities=seen,
            unseen_mint_unique_mint_count=2,
            seen_actor_row_count=1,
            unseen_actor_row_count=1,
            null_actor_row_count=0,
            novelty_fingerprint_sha256="e" * 64,
        )


def _valid_fold_result():
    run = run_fast_chronological_generalization(
        v2_bundle(),
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        v2_policy(),
    )
    return run.fold_results[0]


def test_fold_result_rejects_novelty_identities_not_equal_to_predictions() -> None:
    result = _valid_fold_result()
    original = result.validation_novelty
    unseen = list(original.unseen_mint_identities)
    seen = list(original.seen_mint_identities)

    source = unseen[0] if unseen else seen[0]
    changed = (
        source[0] + "-different",
        *source[1:],
    )
    if unseen:
        unseen[0] = changed
    else:
        seen[0] = changed

    bad_novelty = replace(
        original,
        unseen_mint_identities=tuple(unseen),
        seen_mint_identities=tuple(seen),
        novelty_fingerprint_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="novelty.*prediction|prediction.*novelty"):
        replace(result, validation_novelty=bad_novelty)


def test_fold_result_rejects_prediction_metadata_that_contradicts_model() -> None:
    result = _valid_fold_result()
    first = result.validation_predictions[0]
    bad_prediction = replace(
        first,
        model_version=first.model_version + ":wrong",
    )

    with pytest.raises(ValueError, match="model|prediction"):
        replace(
            result,
            validation_predictions=(
                bad_prediction,
                *result.validation_predictions[1:],
            ),
        )


def test_fold_result_rejects_prediction_outside_declared_partition_interval() -> None:
    result = _valid_fold_result()
    first = result.validation_predictions[-1]
    identity = first.decision_identity
    moved_identity = (
        *identity[:6],
        result.fold.test_started_at_unix_ms,
    )
    moved_prediction = replace(
        first,
        decision_identity=moved_identity,
    )

    original = result.validation_novelty
    unseen = tuple(
        moved_identity if value == identity else value
        for value in original.unseen_mint_identities
    )
    seen = tuple(
        moved_identity if value == identity else value
        for value in original.seen_mint_identities
    )
    moved_novelty = replace(
        original,
        unseen_mint_identities=unseen,
        seen_mint_identities=seen,
        novelty_fingerprint_sha256="e" * 64,
    )

    with pytest.raises(ValueError, match="validation.*interval|timestamp"):
        replace(
            result,
            validation_predictions=(
                *result.validation_predictions[:-1],
                moved_prediction,
            ),
            validation_novelty=moved_novelty,
        )
