from __future__ import annotations

from dataclasses import replace

import pytest

from fast_chronological_v2_fixtures import v2_policy, v2_records
from shreks_brain.fast_validation_v2.population import (
    prepare_fast_chronological_generalization_populations,
)


def _prepared(**kwargs):
    return prepare_fast_chronological_generalization_populations(
        v2_records(**kwargs),
        v2_policy(),
    )[0]


def test_repeated_mint_and_actor_are_retained_in_natural_future_populations() -> None:
    prepared = _prepared()

    training_mints = {record.mint for record in prepared.training_raw}
    training_actors = {
        record.decision_actor
        for record in prepared.training_raw
        if record.decision_actor is not None
    }

    assert prepared.validation
    assert prepared.test
    assert any(record.mint in training_mints for record in prepared.validation)
    assert any(record.mint in training_mints for record in prepared.test)
    assert any(
        record.decision_actor in training_actors
        for record in prepared.validation
        if record.decision_actor is not None
    )
    assert any(
        record.decision_actor in training_actors
        for record in prepared.test
        if record.decision_actor is not None
    )


def test_shared_transaction_signature_is_quarantined_from_every_affected_partition() -> None:
    records = v2_records(shared_signature=True)
    shared = records[2].decision_signature
    prepared = prepare_fast_chronological_generalization_populations(
        records,
        v2_policy(),
    )[0]

    assert prepared.signature_quarantine.shared_signature_count == 1
    signatures = {
        record.decision_signature
        for record in (
            *prepared.training,
            *prepared.validation,
            *prepared.test,
        )
    }
    assert shared not in signatures
    assert prepared.signature_quarantine.training_quarantined_row_count == 1
    assert prepared.signature_quarantine.validation_quarantined_row_count == 1
    assert prepared.signature_quarantine.test_quarantined_row_count == 0


def test_unseen_mint_is_defined_against_raw_training_only() -> None:
    prepared = _prepared()
    training_mints = {record.mint for record in prepared.training_raw}

    validation_unseen = {
        identity[3]
        for identity in prepared.validation_novelty.unseen_mint_identities
    }
    test_unseen = {
        identity[3]
        for identity in prepared.test_novelty.unseen_mint_identities
    }

    assert "mint-v2-validation-first" not in training_mints
    assert "mint-v2-validation-first" in validation_unseen
    assert "mint-v2-validation-first" in test_unseen


def test_seen_and_unseen_identity_sets_exactly_partition_future_rows() -> None:
    prepared = _prepared()

    for rows, novelty in (
        (prepared.validation, prepared.validation_novelty),
        (prepared.test, prepared.test_novelty),
    ):
        future = tuple(record.decision_identity for record in rows)
        classified = tuple(
            sorted(
                (
                    *novelty.unseen_mint_identities,
                    *novelty.seen_mint_identities,
                ),
                key=lambda identity: (
                    identity[6],
                    identity[2],
                    identity[0],
                    identity[1],
                ),
            )
        )
        assert classified == future
        assert (
            novelty.seen_actor_row_count
            + novelty.unseen_actor_row_count
            + novelty.null_actor_row_count
            == len(rows)
        )


def test_novelty_floor_shortfall_fails_before_model_or_target_code() -> None:
    with pytest.raises(ValueError, match="unseen.*validation|validation.*unseen"):
        prepare_fast_chronological_generalization_populations(
            v2_records(),
            v2_policy(minimum_unseen_mint_validation_rows=99),
        )


def test_fold_input_order_is_canonical_and_deterministic() -> None:
    base = v2_policy()
    late = base.folds[0]
    early = type(late)(
        name="v2-fold-early",
        training_started_at_unix_ms=1_000,
        training_ended_at_unix_ms=1_300,
        validation_started_at_unix_ms=1_300,
        validation_ended_at_unix_ms=1_500,
        test_started_at_unix_ms=1_500,
        test_ended_at_unix_ms=1_600,
    )
    ordered_policy = replace(base, folds=(early, late))
    reversed_policy = replace(base, folds=(late, early))

    ordered = prepare_fast_chronological_generalization_populations(
        v2_records(),
        ordered_policy,
    )
    reversed_result = prepare_fast_chronological_generalization_populations(
        v2_records(),
        reversed_policy,
    )

    assert ordered == reversed_result
    assert tuple(value.fold.name for value in ordered) == (
        "v2-fold-early",
        "v2-fold",
    )


def test_giant_mint_actor_connectivity_no_longer_empties_evaluation() -> None:
    prepared = _prepared(giant_entity_component=True)

    assert prepared.training
    assert prepared.validation
    assert prepared.test
    assert prepared.signature_quarantine.shared_signature_count == 0
    assert prepared.validation_novelty.unseen_mint_identities
    assert prepared.test_novelty.unseen_mint_identities
