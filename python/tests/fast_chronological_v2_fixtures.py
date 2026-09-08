from __future__ import annotations

from dataclasses import replace

from fast_chronological_fixtures import (
    TEST_END,
    TEST_START,
    TRAINING_END,
    TRAINING_START,
    VALIDATION_END,
    VALIDATION_START,
    chronological_bundle,
)
from shreks_brain.fast_learning.features import FAST_FORECAST_FEATURE_NAMES
from shreks_brain.fast_validation import FastChronologicalFold
from shreks_brain.fast_validation_v2.firewall import (
    FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
    fast_forecast_identity_firewall_fingerprint_sha256,
)
from shreks_brain.fast_validation_v2.models import (
    FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
    FastChronologicalGeneralizationPolicy,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
)


def v2_policy(
    *,
    minimum_unseen_mint_validation_rows: int = 1,
    minimum_unseen_mint_validation_mints: int = 1,
    minimum_unseen_mint_test_rows: int = 1,
    minimum_unseen_mint_test_mints: int = 1,
) -> FastChronologicalGeneralizationPolicy:
    return FastChronologicalGeneralizationPolicy(
        version=FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
        folds=(
            FastChronologicalFold(
                name="v2-fold",
                training_started_at_unix_ms=TRAINING_START,
                training_ended_at_unix_ms=TRAINING_END,
                validation_started_at_unix_ms=VALIDATION_START,
                validation_ended_at_unix_ms=VALIDATION_END,
                test_started_at_unix_ms=TEST_START,
                test_ended_at_unix_ms=TEST_END,
            ),
        ),
        feature_identity_firewall_version=(
            FAST_FORECAST_IDENTITY_FIREWALL_VERSION
        ),
        feature_identity_firewall_fingerprint_sha256=(
            fast_forecast_identity_firewall_fingerprint_sha256(
                FAST_FORECAST_FEATURE_NAMES
            )
        ),
        minimum_unseen_mint_validation_rows=(
            minimum_unseen_mint_validation_rows
        ),
        minimum_unseen_mint_validation_mints=(
            minimum_unseen_mint_validation_mints
        ),
        minimum_unseen_mint_test_rows=minimum_unseen_mint_test_rows,
        minimum_unseen_mint_test_mints=minimum_unseen_mint_test_mints,
    )


def v2_records(
    *,
    shared_signature: bool = False,
    giant_entity_component: bool = False,
) -> tuple[FastTrainingFeatureRecord, ...]:
    records = list(chronological_bundle().features.records)

    # A recurring mint is legitimate production recurrence and must survive V2.
    shared_mint = records[0].mint
    records[6] = replace(records[6], mint=shared_mint)
    records[9] = replace(records[9], mint=shared_mint)

    # A recurring actor is diagnostic in V2, not a deletion rule.
    shared_actor = records[1].decision_actor
    records[7] = replace(records[7], decision_actor=shared_actor)
    records[10] = replace(records[10], decision_actor=shared_actor)

    # This mint is first observed in validation, then recurs in TEST. It remains
    # unseen relative to training in both future partitions.
    validation_first_mint = "mint-v2-validation-first"
    records[8] = replace(records[8], mint=validation_first_mint)
    records[11] = replace(records[11], mint=validation_first_mint)

    if giant_entity_component:
        bridge_actor = records[0].decision_actor
        for index in range(len(records)):
            records[index] = replace(
                records[index],
                decision_actor=bridge_actor,
            )
        # Keep future-only mints so novelty floors still exercise V2 while every
        # row remains connected through the same recurring actor.
        records[8] = replace(
            records[8],
            mint="mint-v2-giant-validation-only",
        )
        records[11] = replace(
            records[11],
            mint="mint-v2-giant-validation-only",
        )
        records[10] = replace(
            records[10],
            mint="mint-v2-giant-test-only",
        )

    if shared_signature:
        records[7] = replace(
            records[7],
            decision_signature=records[2].decision_signature,
            decision_ordinal=1,
        )

    return tuple(records)
