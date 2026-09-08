from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from shreks_brain.fast_validation.models import FastChronologicalFold
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
)

from .models import (
    FastChronologicalGeneralizationPolicy,
    FastFutureNoveltySummary,
    FastSignatureQuarantineSummary,
)


@dataclass(frozen=True, slots=True)
class _PreparedGeneralizationFoldPopulation:
    fold: FastChronologicalFold
    training_raw: tuple[FastTrainingFeatureRecord, ...]
    validation_raw: tuple[FastTrainingFeatureRecord, ...]
    test_raw: tuple[FastTrainingFeatureRecord, ...]
    training: tuple[FastTrainingFeatureRecord, ...]
    validation: tuple[FastTrainingFeatureRecord, ...]
    test: tuple[FastTrainingFeatureRecord, ...]
    signature_quarantine: FastSignatureQuarantineSummary
    validation_novelty: FastFutureNoveltySummary
    test_novelty: FastFutureNoveltySummary


def prepare_fast_chronological_generalization_populations(
    records: tuple[FastTrainingFeatureRecord, ...],
    policy: FastChronologicalGeneralizationPolicy,
) -> tuple[_PreparedGeneralizationFoldPopulation, ...]:
    if not isinstance(records, tuple) or not records:
        raise ValueError("feature records must be a non-empty tuple")
    if not all(type(value) is FastTrainingFeatureRecord for value in records):
        raise ValueError(
            "feature records must contain exact FastTrainingFeatureRecord values"
        )
    if type(policy) is not FastChronologicalGeneralizationPolicy:
        raise ValueError(
            "policy must be exact FastChronologicalGeneralizationPolicy"
        )

    identities = tuple(record.decision_identity for record in records)
    if len(set(identities)) != len(identities):
        raise ValueError("feature records contain duplicate decision identities")

    canonical_records = tuple(sorted(records, key=_record_sort_key))
    ordered_folds = tuple(sorted(policy.folds, key=_fold_sort_key))
    prepared: list[_PreparedGeneralizationFoldPopulation] = []

    for fold in ordered_folds:
        training_raw = tuple(
            record
            for record in canonical_records
            if fold.training_started_at_unix_ms
            <= record.decision_observed_at_unix_ms
            < fold.training_ended_at_unix_ms
        )
        validation_raw = tuple(
            record
            for record in canonical_records
            if fold.validation_started_at_unix_ms
            <= record.decision_observed_at_unix_ms
            < fold.validation_ended_at_unix_ms
        )
        test_raw = tuple(
            record
            for record in canonical_records
            if fold.test_started_at_unix_ms
            <= record.decision_observed_at_unix_ms
            < fold.test_ended_at_unix_ms
        )

        for role, rows in (
            ("training", training_raw),
            ("validation", validation_raw),
            ("test", test_raw),
        ):
            if not rows:
                raise ValueError(
                    f"{role} raw chronological population cannot be empty"
                )

        shared_signatures = _shared_signatures(
            training_raw,
            validation_raw,
            test_raw,
        )
        training = tuple(
            record
            for record in training_raw
            if record.decision_signature not in shared_signatures
        )
        validation = tuple(
            record
            for record in validation_raw
            if record.decision_signature not in shared_signatures
        )
        test = tuple(
            record
            for record in test_raw
            if record.decision_signature not in shared_signatures
        )

        for role, rows in (
            ("training", training),
            ("validation", validation),
            ("test", test),
        ):
            if not rows:
                raise ValueError(
                    f"{role} post-signature-quarantine population cannot be empty"
                )

        quarantine = _signature_quarantine_summary(
            shared_signatures=shared_signatures,
            training_raw=training_raw,
            validation_raw=validation_raw,
            test_raw=test_raw,
        )

        training_mints = {record.mint for record in training_raw}
        training_actors = {
            record.decision_actor
            for record in training_raw
            if record.decision_actor is not None
        }

        validation_novelty = _novelty_summary(
            partition="validation",
            rows=validation,
            training_mints=training_mints,
            training_actors=training_actors,
        )
        test_novelty = _novelty_summary(
            partition="test",
            rows=test,
            training_mints=training_mints,
            training_actors=training_actors,
        )

        _enforce_novelty_floors(
            policy,
            validation_novelty=validation_novelty,
            test_novelty=test_novelty,
        )

        prepared.append(
            _PreparedGeneralizationFoldPopulation(
                fold=fold,
                training_raw=training_raw,
                validation_raw=validation_raw,
                test_raw=test_raw,
                training=training,
                validation=validation,
                test=test,
                signature_quarantine=quarantine,
                validation_novelty=validation_novelty,
                test_novelty=test_novelty,
            )
        )

    return tuple(prepared)


def _shared_signatures(
    training: tuple[FastTrainingFeatureRecord, ...],
    validation: tuple[FastTrainingFeatureRecord, ...],
    test: tuple[FastTrainingFeatureRecord, ...],
) -> frozenset[str]:
    membership: dict[str, set[str]] = {}
    for role, rows in (
        ("training", training),
        ("validation", validation),
        ("test", test),
    ):
        for record in rows:
            membership.setdefault(
                record.decision_signature,
                set(),
            ).add(role)
    return frozenset(
        signature
        for signature, roles in membership.items()
        if len(roles) > 1
    )


def _signature_quarantine_summary(
    *,
    shared_signatures: frozenset[str],
    training_raw: tuple[FastTrainingFeatureRecord, ...],
    validation_raw: tuple[FastTrainingFeatureRecord, ...],
    test_raw: tuple[FastTrainingFeatureRecord, ...],
) -> FastSignatureQuarantineSummary:
    def affected(
        rows: tuple[FastTrainingFeatureRecord, ...],
    ) -> tuple[tuple[object, ...], ...]:
        return tuple(
            record.decision_identity
            for record in rows
            if record.decision_signature in shared_signatures
        )

    training_affected = affected(training_raw)
    validation_affected = affected(validation_raw)
    test_affected = affected(test_raw)
    material = {
        "shared_signatures": sorted(shared_signatures),
        "training_quarantined_identities": [
            _canonical_identity(identity)
            for identity in training_affected
        ],
        "validation_quarantined_identities": [
            _canonical_identity(identity)
            for identity in validation_affected
        ],
        "test_quarantined_identities": [
            _canonical_identity(identity)
            for identity in test_affected
        ],
    }
    return FastSignatureQuarantineSummary(
        shared_signature_count=len(shared_signatures),
        training_quarantined_row_count=len(training_affected),
        validation_quarantined_row_count=len(validation_affected),
        test_quarantined_row_count=len(test_affected),
        quarantine_fingerprint_sha256=_sha256_canonical(material),
    )


def _novelty_summary(
    *,
    partition: str,
    rows: tuple[FastTrainingFeatureRecord, ...],
    training_mints: set[str],
    training_actors: set[str],
) -> FastFutureNoveltySummary:
    unseen = tuple(
        record.decision_identity
        for record in rows
        if record.mint not in training_mints
    )
    seen = tuple(
        record.decision_identity
        for record in rows
        if record.mint in training_mints
    )

    seen_actor_row_count = 0
    unseen_actor_row_count = 0
    null_actor_row_count = 0
    for record in rows:
        actor = record.decision_actor
        if actor is None:
            null_actor_row_count += 1
        elif actor in training_actors:
            seen_actor_row_count += 1
        else:
            unseen_actor_row_count += 1

    unique_mints = {record.mint for record in rows}
    unseen_unique_mints = {
        record.mint
        for record in rows
        if record.mint not in training_mints
    }
    material = {
        "partition": partition,
        "prediction_identities": [
            _canonical_identity(record.decision_identity)
            for record in rows
        ],
        "unseen_mint_identities": [
            _canonical_identity(identity)
            for identity in unseen
        ],
        "seen_mint_identities": [
            _canonical_identity(identity)
            for identity in seen
        ],
        "unique_mint_count": len(unique_mints),
        "unseen_mint_unique_mint_count": len(unseen_unique_mints),
        "seen_actor_row_count": seen_actor_row_count,
        "unseen_actor_row_count": unseen_actor_row_count,
        "null_actor_row_count": null_actor_row_count,
    }
    return FastFutureNoveltySummary(
        partition=partition,
        prediction_count=len(rows),
        unique_mint_count=len(unique_mints),
        unseen_mint_identities=unseen,
        seen_mint_identities=seen,
        unseen_mint_unique_mint_count=len(unseen_unique_mints),
        seen_actor_row_count=seen_actor_row_count,
        unseen_actor_row_count=unseen_actor_row_count,
        null_actor_row_count=null_actor_row_count,
        novelty_fingerprint_sha256=_sha256_canonical(material),
    )


def _enforce_novelty_floors(
    policy: FastChronologicalGeneralizationPolicy,
    *,
    validation_novelty: FastFutureNoveltySummary,
    test_novelty: FastFutureNoveltySummary,
) -> None:
    validation_unseen_rows = len(
        validation_novelty.unseen_mint_identities
    )
    if (
        validation_unseen_rows
        < policy.minimum_unseen_mint_validation_rows
        or validation_novelty.unseen_mint_unique_mint_count
        < policy.minimum_unseen_mint_validation_mints
    ):
        raise ValueError(
            "unseen-mint validation evidence is below the explicit floor"
        )

    test_unseen_rows = len(test_novelty.unseen_mint_identities)
    if (
        test_unseen_rows < policy.minimum_unseen_mint_test_rows
        or test_novelty.unseen_mint_unique_mint_count
        < policy.minimum_unseen_mint_test_mints
    ):
        raise ValueError(
            "unseen-mint test evidence is below the explicit floor"
        )


def _record_sort_key(
    record: FastTrainingFeatureRecord,
) -> tuple[object, ...]:
    return (
        record.decision_observed_at_unix_ms,
        record.decision_sequence,
        record.decision_signature,
        record.decision_ordinal,
    )


def _fold_sort_key(
    fold: FastChronologicalFold,
) -> tuple[int, int, int, int, str]:
    return (
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.test_started_at_unix_ms,
        fold.test_ended_at_unix_ms,
        fold.name,
    )


def _canonical_identity(
    identity: tuple[object, ...],
) -> list[object]:
    return list(identity)


def _sha256_canonical(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
