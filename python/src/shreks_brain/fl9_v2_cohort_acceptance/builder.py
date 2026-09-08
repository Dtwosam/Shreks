from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Protocol

from shreks_brain.fast_learning.features import FAST_FORECAST_FEATURE_NAMES
from shreks_brain.fast_validation_v2.firewall import (
    validate_fast_forecast_identity_firewall,
)
from shreks_brain.fl9_tradable_universe import (
    Fl9TradableUniverseAssessment,
    Fl9TradableUniversePolicy,
    fl9_tradable_universe_policy_fingerprint_sha256,
)

from .models import (
    Fl9V2AcceptedDecision,
    Fl9V2CohortAcceptancePolicy,
    Fl9V2CohortEvidenceFloorPolicy,
    Fl9V2ConcentrationSummary,
    Fl9V2QuarantinedDecision,
)
from .source import (
    Fl9V2CohortSource,
    Fl9V2SourceDecision,
    Fl9V2SourceSnapshot,
)


class _TradableUniverseAssessor(Protocol):
    def assess(self, **kwargs) -> Fl9TradableUniverseAssessment:
        ...


@dataclass(frozen=True, slots=True)
class _CohortCheckpoint:
    minimum_decision_observed_at_unix_ms: int
    test_end_unix_ms: int
    training_cut_unix_ms: int
    validation_cut_unix_ms: int
    expected_raw_row_count: int
    expected_cross_session_duplicate_count: int
    expected_raw_unique_mint_count: int
    expected_eligibility_reason_counts: tuple[tuple[str, int], ...]
    expected_eligible_row_count: int
    expected_eligible_unique_mint_count: int
    expected_training_raw_row_count: int
    expected_validation_raw_row_count: int
    expected_test_raw_row_count: int
    expected_shared_signature_count: int
    expected_training_quarantined_row_count: int
    expected_validation_quarantined_row_count: int
    expected_test_quarantined_row_count: int
    expected_validation_unseen_mint_rows: int
    expected_validation_unseen_mint_unique_mints: int
    expected_validation_seen_mint_rows: int
    expected_validation_seen_mint_unique_mints: int
    expected_validation_seen_actor_rows: int
    expected_validation_unseen_actor_rows: int
    expected_validation_null_actor_rows: int
    expected_test_unseen_mint_rows: int
    expected_test_unseen_mint_unique_mints: int
    expected_test_seen_mint_rows: int
    expected_test_seen_mint_unique_mints: int
    expected_test_seen_actor_rows: int
    expected_test_unseen_actor_rows: int
    expected_test_null_actor_rows: int
    minimum_total_eligible_rows: int
    minimum_training_rows: int
    minimum_validation_rows: int
    minimum_test_rows: int
    minimum_unseen_mint_validation_rows: int
    minimum_unseen_mint_validation_unique_mints: int
    minimum_unseen_mint_test_rows: int
    minimum_unseen_mint_test_unique_mints: int


@dataclass(frozen=True, slots=True)
class _BuiltCohortAcceptance:
    latest_session_id: int
    raw_row_count: int
    cross_session_duplicate_count: int
    raw_unique_mint_count: int
    eligibility_reason_counts: tuple[tuple[str, int], ...]
    eligible_row_count: int
    eligible_unique_mint_count: int
    training_cut_unix_ms: int
    validation_cut_unix_ms: int
    training_raw_row_count: int
    validation_raw_row_count: int
    test_raw_row_count: int
    shared_signature_count: int
    training_quarantined_row_count: int
    validation_quarantined_row_count: int
    test_quarantined_row_count: int
    training_row_count: int
    validation_row_count: int
    test_row_count: int
    validation_unseen_mint_row_count: int
    validation_unseen_mint_unique_mint_count: int
    validation_seen_mint_row_count: int
    validation_seen_mint_unique_mint_count: int
    validation_seen_actor_row_count: int
    validation_unseen_actor_row_count: int
    validation_null_actor_row_count: int
    test_unseen_mint_row_count: int
    test_unseen_mint_unique_mint_count: int
    test_seen_mint_row_count: int
    test_seen_mint_unique_mint_count: int
    test_seen_actor_row_count: int
    test_unseen_actor_row_count: int
    test_null_actor_row_count: int
    structural_floor_passed: bool
    accepted_decisions: tuple[Fl9V2AcceptedDecision, ...]
    quarantined_decisions: tuple[Fl9V2QuarantinedDecision, ...]
    concentration_summaries: tuple[
        tuple[str, Fl9V2ConcentrationSummary], ...
    ]
    accepted_identity_fingerprint_sha256: str
    training_identity_fingerprint_sha256: str
    validation_identity_fingerprint_sha256: str
    test_identity_fingerprint_sha256: str
    validation_unseen_mint_identity_fingerprint_sha256: str
    validation_seen_mint_identity_fingerprint_sha256: str
    test_unseen_mint_identity_fingerprint_sha256: str
    test_seen_mint_identity_fingerprint_sha256: str
    signature_quarantine_identity_fingerprint_sha256: str
    assessment_evidence_fingerprint_sha256: str


def build_fl9_v2_cohort_acceptance(
    *,
    source: Fl9V2CohortSource,
    tradable_store: _TradableUniverseAssessor,
    policy: Fl9V2CohortAcceptancePolicy | None = None,
    floor_policy: Fl9V2CohortEvidenceFloorPolicy | None = None,
) -> _BuiltCohortAcceptance:
    active_policy = policy or Fl9V2CohortAcceptancePolicy()
    active_floors = floor_policy or Fl9V2CohortEvidenceFloorPolicy()
    if type(active_policy) is not Fl9V2CohortAcceptancePolicy:
        raise ValueError(
            "policy must be exact Fl9V2CohortAcceptancePolicy"
        )
    if type(active_floors) is not Fl9V2CohortEvidenceFloorPolicy:
        raise ValueError(
            "floor_policy must be exact Fl9V2CohortEvidenceFloorPolicy"
        )
    snapshot = source.load_source_snapshot(active_policy)
    checkpoint = _production_checkpoint(active_policy, active_floors)
    return _build_fl9_v2_cohort_acceptance_from_snapshot(
        snapshot=snapshot,
        tradable_store=tradable_store,
        policy=active_policy,
        checkpoint=checkpoint,
    )


def _build_fl9_v2_cohort_acceptance_from_snapshot(
    *,
    snapshot: Fl9V2SourceSnapshot,
    tradable_store: _TradableUniverseAssessor,
    policy: Fl9V2CohortAcceptancePolicy,
    checkpoint: _CohortCheckpoint,
) -> _BuiltCohortAcceptance:
    if type(snapshot) is not Fl9V2SourceSnapshot:
        raise ValueError("snapshot must be exact Fl9V2SourceSnapshot")
    if type(policy) is not Fl9V2CohortAcceptancePolicy:
        raise ValueError(
            "policy must be exact Fl9V2CohortAcceptancePolicy"
        )
    if type(checkpoint) is not _CohortCheckpoint:
        raise ValueError("checkpoint must be exact _CohortCheckpoint")
    if not hasattr(tradable_store, "assess"):
        raise ValueError("tradable_store must expose assess()")

    _authenticate_input_policies(policy)
    _require_checkpoint(
        "raw row count",
        len(snapshot.raw_decisions),
        checkpoint.expected_raw_row_count,
    )
    _require_checkpoint(
        "cross-session duplicate count",
        snapshot.cross_session_duplicate_count,
        checkpoint.expected_cross_session_duplicate_count,
    )
    _require_checkpoint(
        "raw unique mint count",
        snapshot.raw_unique_mint_count,
        checkpoint.expected_raw_unique_mint_count,
    )

    tradable_policy = Fl9TradableUniversePolicy()
    reason_counts: Counter[str] = Counter()
    eligible_rows: list[Fl9V2SourceDecision] = []
    eligible_assessment_fingerprints: dict[
        tuple[object, ...], str
    ] = {}
    all_assessment_material: list[dict[str, object]] = []

    for row in snapshot.raw_decisions:
        assessment = tradable_store.assess(
            mint=row.mint,
            quote_mint=row.quote_mint,
            decision_venue=row.venue,
            decision_observed_at_unix_ms=row.observed_at_unix_ms,
            policy=tradable_policy,
        )
        _validate_assessment(row, assessment, policy)
        reason_counts[assessment.reason] += 1
        material = _assessment_material(row, assessment)
        all_assessment_material.append(material)
        assessment_fingerprint = _sha256_canonical(material)
        if assessment.eligible:
            eligible_rows.append(row)
            eligible_assessment_fingerprints[
                row.decision_identity
            ] = assessment_fingerprint

    canonical_reason_counts = tuple(sorted(reason_counts.items()))
    _require_checkpoint(
        "eligibility reason counts",
        canonical_reason_counts,
        checkpoint.expected_eligibility_reason_counts,
    )

    eligible = tuple(sorted(eligible_rows, key=_row_sort_key))
    _require_checkpoint(
        "eligible row count",
        len(eligible),
        checkpoint.expected_eligible_row_count,
    )
    _require_checkpoint(
        "eligible unique mint count",
        len({row.mint for row in eligible}),
        checkpoint.expected_eligible_unique_mint_count,
    )

    preselection = tuple(
        row
        for row in eligible
        if (
            checkpoint.minimum_decision_observed_at_unix_ms
            <= row.observed_at_unix_ms
            < checkpoint.test_end_unix_ms
        )
    )
    if len(preselection) != len(eligible):
        raise ValueError(
            "eligible checkpoint contains decisions outside frozen cohort bounds"
        )

    training_cut, validation_cut = _choose_split(preselection)
    if training_cut != checkpoint.training_cut_unix_ms:
        raise ValueError(
            "recomputed training cut contradicts frozen cut checkpoint"
        )
    if validation_cut != checkpoint.validation_cut_unix_ms:
        raise ValueError(
            "recomputed validation cut contradicts frozen cut checkpoint"
        )

    training_raw = tuple(
        row for row in preselection
        if row.observed_at_unix_ms < training_cut
    )
    validation_raw = tuple(
        row for row in preselection
        if training_cut <= row.observed_at_unix_ms < validation_cut
    )
    test_raw = tuple(
        row for row in preselection
        if row.observed_at_unix_ms >= validation_cut
    )

    for label, actual, expected in (
        (
            "training raw row count",
            len(training_raw),
            checkpoint.expected_training_raw_row_count,
        ),
        (
            "validation raw row count",
            len(validation_raw),
            checkpoint.expected_validation_raw_row_count,
        ),
        (
            "TEST raw row count",
            len(test_raw),
            checkpoint.expected_test_raw_row_count,
        ),
    ):
        _require_checkpoint(label, actual, expected)

    shared_signatures = _shared_signatures(
        training_raw,
        validation_raw,
        test_raw,
    )
    _require_checkpoint(
        "shared signature count",
        len(shared_signatures),
        checkpoint.expected_shared_signature_count,
    )

    training, training_quarantine = _quarantine(
        training_raw,
        "training",
        shared_signatures,
    )
    validation, validation_quarantine = _quarantine(
        validation_raw,
        "validation",
        shared_signatures,
    )
    test, test_quarantine = _quarantine(
        test_raw,
        "test",
        shared_signatures,
    )

    for label, actual, expected in (
        (
            "training quarantined row count",
            len(training_quarantine),
            checkpoint.expected_training_quarantined_row_count,
        ),
        (
            "validation quarantined row count",
            len(validation_quarantine),
            checkpoint.expected_validation_quarantined_row_count,
        ),
        (
            "TEST quarantined row count",
            len(test_quarantine),
            checkpoint.expected_test_quarantined_row_count,
        ),
    ):
        _require_checkpoint(label, actual, expected)

    if _shared_signatures(training, validation, test):
        raise ValueError(
            "cross-partition signatures survive V2 quarantine"
        )

    training_mints = {row.mint for row in training_raw}
    training_actors = {
        row.actor for row in training_raw if row.actor is not None
    }

    validation_stats = _novelty_stats(
        validation,
        training_mints=training_mints,
        training_actors=training_actors,
    )
    test_stats = _novelty_stats(
        test,
        training_mints=training_mints,
        training_actors=training_actors,
    )
    _check_novelty_checkpoint(
        "validation",
        validation_stats,
        checkpoint,
    )
    _check_novelty_checkpoint(
        "test",
        test_stats,
        checkpoint,
    )

    _enforce_structural_floors(
        checkpoint,
        eligible_count=len(eligible),
        training_count=len(training),
        validation_count=len(validation),
        test_count=len(test),
        validation_stats=validation_stats,
        test_stats=test_stats,
    )

    accepted = _accepted_decisions(
        (
            ("training", training),
            ("validation", validation),
            ("test", test),
        ),
        assessment_fingerprints=eligible_assessment_fingerprints,
        training_mints=training_mints,
        training_actors=training_actors,
    )
    quarantined = tuple(
        sorted(
            (
                *training_quarantine,
                *validation_quarantine,
                *test_quarantine,
            ),
            key=lambda value: _identity_sort_key(value.decision_identity),
        )
    )

    validation_unseen_rows = tuple(
        row for row in validation if row.mint not in training_mints
    )
    validation_seen_rows = tuple(
        row for row in validation if row.mint in training_mints
    )
    test_unseen_rows = tuple(
        row for row in test if row.mint not in training_mints
    )
    test_seen_rows = tuple(
        row for row in test if row.mint in training_mints
    )

    concentrations = (
        ("full_eligible", _concentration(eligible)),
        ("raw_training", _concentration(training_raw)),
        ("raw_validation", _concentration(validation_raw)),
        ("raw_test", _concentration(test_raw)),
        ("post_signature_training", _concentration(training)),
        ("post_signature_validation", _concentration(validation)),
        ("post_signature_test", _concentration(test)),
        (
            "unseen_mint_validation",
            _concentration(validation_unseen_rows),
        ),
        ("unseen_mint_test", _concentration(test_unseen_rows)),
    )

    return _BuiltCohortAcceptance(
        latest_session_id=snapshot.latest_session_id,
        raw_row_count=len(snapshot.raw_decisions),
        cross_session_duplicate_count=(
            snapshot.cross_session_duplicate_count
        ),
        raw_unique_mint_count=snapshot.raw_unique_mint_count,
        eligibility_reason_counts=canonical_reason_counts,
        eligible_row_count=len(eligible),
        eligible_unique_mint_count=len({row.mint for row in eligible}),
        training_cut_unix_ms=training_cut,
        validation_cut_unix_ms=validation_cut,
        training_raw_row_count=len(training_raw),
        validation_raw_row_count=len(validation_raw),
        test_raw_row_count=len(test_raw),
        shared_signature_count=len(shared_signatures),
        training_quarantined_row_count=len(training_quarantine),
        validation_quarantined_row_count=len(validation_quarantine),
        test_quarantined_row_count=len(test_quarantine),
        training_row_count=len(training),
        validation_row_count=len(validation),
        test_row_count=len(test),
        validation_unseen_mint_row_count=validation_stats.unseen_mint_rows,
        validation_unseen_mint_unique_mint_count=(
            validation_stats.unseen_mint_unique_mints
        ),
        validation_seen_mint_row_count=validation_stats.seen_mint_rows,
        validation_seen_mint_unique_mint_count=(
            validation_stats.seen_mint_unique_mints
        ),
        validation_seen_actor_row_count=validation_stats.seen_actor_rows,
        validation_unseen_actor_row_count=validation_stats.unseen_actor_rows,
        validation_null_actor_row_count=validation_stats.null_actor_rows,
        test_unseen_mint_row_count=test_stats.unseen_mint_rows,
        test_unseen_mint_unique_mint_count=(
            test_stats.unseen_mint_unique_mints
        ),
        test_seen_mint_row_count=test_stats.seen_mint_rows,
        test_seen_mint_unique_mint_count=test_stats.seen_mint_unique_mints,
        test_seen_actor_row_count=test_stats.seen_actor_rows,
        test_unseen_actor_row_count=test_stats.unseen_actor_rows,
        test_null_actor_row_count=test_stats.null_actor_rows,
        structural_floor_passed=True,
        accepted_decisions=accepted,
        quarantined_decisions=quarantined,
        concentration_summaries=concentrations,
        accepted_identity_fingerprint_sha256=_identity_fingerprint(
            tuple(value.decision_identity for value in accepted)
        ),
        training_identity_fingerprint_sha256=_rows_identity_fingerprint(
            training
        ),
        validation_identity_fingerprint_sha256=_rows_identity_fingerprint(
            validation
        ),
        test_identity_fingerprint_sha256=_rows_identity_fingerprint(test),
        validation_unseen_mint_identity_fingerprint_sha256=(
            _rows_identity_fingerprint(validation_unseen_rows)
        ),
        validation_seen_mint_identity_fingerprint_sha256=(
            _rows_identity_fingerprint(validation_seen_rows)
        ),
        test_unseen_mint_identity_fingerprint_sha256=(
            _rows_identity_fingerprint(test_unseen_rows)
        ),
        test_seen_mint_identity_fingerprint_sha256=(
            _rows_identity_fingerprint(test_seen_rows)
        ),
        signature_quarantine_identity_fingerprint_sha256=(
            _identity_fingerprint(
                tuple(
                    value.decision_identity for value in quarantined
                )
            )
        ),
        assessment_evidence_fingerprint_sha256=_sha256_canonical(
            all_assessment_material
        ),
    )


@dataclass(frozen=True, slots=True)
class _NoveltyStats:
    unseen_mint_rows: int
    unseen_mint_unique_mints: int
    seen_mint_rows: int
    seen_mint_unique_mints: int
    seen_actor_rows: int
    unseen_actor_rows: int
    null_actor_rows: int


def _production_checkpoint(
    policy: Fl9V2CohortAcceptancePolicy,
    floors: Fl9V2CohortEvidenceFloorPolicy,
) -> _CohortCheckpoint:
    return _CohortCheckpoint(
        minimum_decision_observed_at_unix_ms=(
            policy.minimum_decision_observed_at_unix_ms
        ),
        test_end_unix_ms=policy.test_end_unix_ms,
        training_cut_unix_ms=policy.training_cut_unix_ms,
        validation_cut_unix_ms=policy.validation_cut_unix_ms,
        expected_raw_row_count=policy.expected_raw_row_count,
        expected_cross_session_duplicate_count=(
            policy.expected_cross_session_duplicate_count
        ),
        expected_raw_unique_mint_count=(
            policy.expected_raw_unique_mint_count
        ),
        expected_eligibility_reason_counts=(
            policy.expected_eligibility_reason_counts
        ),
        expected_eligible_row_count=policy.expected_eligible_row_count,
        expected_eligible_unique_mint_count=(
            policy.expected_eligible_unique_mint_count
        ),
        expected_training_raw_row_count=(
            policy.expected_training_raw_row_count
        ),
        expected_validation_raw_row_count=(
            policy.expected_validation_raw_row_count
        ),
        expected_test_raw_row_count=policy.expected_test_raw_row_count,
        expected_shared_signature_count=(
            policy.expected_shared_signature_count
        ),
        expected_training_quarantined_row_count=(
            policy.expected_training_quarantined_row_count
        ),
        expected_validation_quarantined_row_count=(
            policy.expected_validation_quarantined_row_count
        ),
        expected_test_quarantined_row_count=(
            policy.expected_test_quarantined_row_count
        ),
        expected_validation_unseen_mint_rows=(
            policy.expected_validation_unseen_mint_rows
        ),
        expected_validation_unseen_mint_unique_mints=(
            policy.expected_validation_unseen_mint_unique_mints
        ),
        expected_validation_seen_mint_rows=(
            policy.expected_validation_seen_mint_rows
        ),
        expected_validation_seen_mint_unique_mints=(
            policy.expected_validation_seen_mint_unique_mints
        ),
        expected_validation_seen_actor_rows=(
            policy.expected_validation_seen_actor_rows
        ),
        expected_validation_unseen_actor_rows=(
            policy.expected_validation_unseen_actor_rows
        ),
        expected_validation_null_actor_rows=(
            policy.expected_validation_null_actor_rows
        ),
        expected_test_unseen_mint_rows=(
            policy.expected_test_unseen_mint_rows
        ),
        expected_test_unseen_mint_unique_mints=(
            policy.expected_test_unseen_mint_unique_mints
        ),
        expected_test_seen_mint_rows=policy.expected_test_seen_mint_rows,
        expected_test_seen_mint_unique_mints=(
            policy.expected_test_seen_mint_unique_mints
        ),
        expected_test_seen_actor_rows=policy.expected_test_seen_actor_rows,
        expected_test_unseen_actor_rows=(
            policy.expected_test_unseen_actor_rows
        ),
        expected_test_null_actor_rows=policy.expected_test_null_actor_rows,
        minimum_total_eligible_rows=floors.minimum_total_eligible_rows,
        minimum_training_rows=floors.minimum_training_rows,
        minimum_validation_rows=floors.minimum_validation_rows,
        minimum_test_rows=floors.minimum_test_rows,
        minimum_unseen_mint_validation_rows=(
            floors.minimum_unseen_mint_validation_rows
        ),
        minimum_unseen_mint_validation_unique_mints=(
            floors.minimum_unseen_mint_validation_unique_mints
        ),
        minimum_unseen_mint_test_rows=(
            floors.minimum_unseen_mint_test_rows
        ),
        minimum_unseen_mint_test_unique_mints=(
            floors.minimum_unseen_mint_test_unique_mints
        ),
    )


def _authenticate_input_policies(
    policy: Fl9V2CohortAcceptancePolicy,
) -> None:
    tradable = Fl9TradableUniversePolicy()
    actual_policy_fingerprint = (
        fl9_tradable_universe_policy_fingerprint_sha256(tradable)
    )
    if (
        tradable.version != policy.tradable_universe_policy_version
        or actual_policy_fingerprint
        != policy.tradable_universe_policy_fingerprint_sha256
    ):
        raise ValueError(
            "FL9 tradable-universe policy fingerprint contradicts cohort policy"
        )

    validate_fast_forecast_identity_firewall(
        feature_names=FAST_FORECAST_FEATURE_NAMES,
        expected_version=policy.feature_identity_firewall_version,
        expected_fingerprint_sha256=(
            policy.feature_identity_firewall_fingerprint_sha256
        ),
    )


def _validate_assessment(
    row: Fl9V2SourceDecision,
    assessment: object,
    policy: Fl9V2CohortAcceptancePolicy,
) -> None:
    if type(assessment) is not Fl9TradableUniverseAssessment:
        raise ValueError(
            "tradable universe assessor returned wrong assessment type"
        )
    if (
        assessment.policy_version
        != policy.tradable_universe_policy_version
        or assessment.policy_fingerprint_sha256
        != policy.tradable_universe_policy_fingerprint_sha256
    ):
        raise ValueError(
            "tradable universe assessment policy fingerprint mismatch"
        )
    if (
        assessment.mint != row.mint
        or assessment.quote_mint != row.quote_mint
        or assessment.decision_venue != row.venue
        or assessment.decision_observed_at_unix_ms
        != row.observed_at_unix_ms
    ):
        raise ValueError(
            "tradable universe assessment contradicts decision identity"
        )


def _assessment_material(
    row: Fl9V2SourceDecision,
    assessment: Fl9TradableUniverseAssessment,
) -> dict[str, object]:
    return {
        "decision_identity": list(row.decision_identity),
        "tradable_universe_policy_version": assessment.policy_version,
        "tradable_universe_policy_fingerprint_sha256": (
            assessment.policy_fingerprint_sha256
        ),
        "graduation_detected_at_unix_ms": (
            assessment.graduation_detected_at_unix_ms
        ),
        "candidate_id": assessment.candidate_id,
        "snapshot_row_id": assessment.snapshot_row_id,
        "snapshot_observed_at_unix_ms": (
            assessment.snapshot_observed_at_unix_ms
        ),
        "snapshot_age_ms": assessment.snapshot_age_ms,
        "selected_pair_address": assessment.selected_pair_address,
        "liquidity_usd": _float_hex_or_none(assessment.liquidity_usd),
        "volume_h24_usd": _float_hex_or_none(assessment.volume_h24_usd),
        "reason": assessment.reason,
        "eligible": assessment.eligible,
    }


def _choose_split(
    rows: tuple[Fl9V2SourceDecision, ...],
) -> tuple[int, int]:
    counts = Counter(row.observed_at_unix_ms for row in rows)
    buckets = tuple(sorted(counts.items()))
    if len(buckets) < 3:
        raise ValueError(
            "eligible cohort has fewer than three distinct timestamps"
        )
    total = len(rows)

    cumulative = 0
    training_candidates: list[tuple[int, int, int]] = []
    for index in range(1, len(buckets) - 1):
        cumulative += buckets[index - 1][1]
        remaining = total - cumulative
        if cumulative < 1 or remaining < 2:
            continue
        training_candidates.append(
            (
                abs(5 * cumulative - 3 * total),
                cumulative,
                index,
            )
        )
    if not training_candidates:
        raise ValueError("cannot form deterministic training cut")
    cut_one_index = min(training_candidates)[2]
    training_count = sum(
        count for _, count in buckets[:cut_one_index]
    )

    cumulative = training_count
    validation_candidates: list[tuple[int, int, int]] = []
    for index in range(cut_one_index + 1, len(buckets)):
        cumulative += buckets[index - 1][1]
        validation_count = cumulative - training_count
        test_count = total - cumulative
        if validation_count < 1 or test_count < 1:
            continue
        validation_candidates.append(
            (
                abs(5 * cumulative - 4 * total),
                cumulative,
                index,
            )
        )
    if not validation_candidates:
        raise ValueError("cannot form deterministic validation cut")
    cut_two_index = min(validation_candidates)[2]
    return (
        buckets[cut_one_index][0],
        buckets[cut_two_index][0],
    )


def _shared_signatures(
    training: tuple[Fl9V2SourceDecision, ...],
    validation: tuple[Fl9V2SourceDecision, ...],
    test: tuple[Fl9V2SourceDecision, ...],
) -> frozenset[str]:
    membership: dict[str, set[str]] = defaultdict(set)
    for role, rows in (
        ("training", training),
        ("validation", validation),
        ("test", test),
    ):
        for row in rows:
            membership[row.signature].add(role)
    return frozenset(
        signature
        for signature, roles in membership.items()
        if len(roles) > 1
    )


def _quarantine(
    rows: tuple[Fl9V2SourceDecision, ...],
    partition: str,
    shared_signatures: frozenset[str],
) -> tuple[
    tuple[Fl9V2SourceDecision, ...],
    tuple[Fl9V2QuarantinedDecision, ...],
]:
    kept = tuple(
        row for row in rows if row.signature not in shared_signatures
    )
    quarantined = tuple(
        Fl9V2QuarantinedDecision(
            decision_identity=row.decision_identity,
            partition=partition,
            shared_signature=row.signature,
        )
        for row in rows
        if row.signature in shared_signatures
    )
    return kept, quarantined


def _novelty_stats(
    rows: tuple[Fl9V2SourceDecision, ...],
    *,
    training_mints: set[str],
    training_actors: set[str],
) -> _NoveltyStats:
    unseen = tuple(row for row in rows if row.mint not in training_mints)
    seen = tuple(row for row in rows if row.mint in training_mints)
    seen_actor = 0
    unseen_actor = 0
    null_actor = 0
    for row in rows:
        if row.actor is None:
            null_actor += 1
        elif row.actor in training_actors:
            seen_actor += 1
        else:
            unseen_actor += 1
    return _NoveltyStats(
        unseen_mint_rows=len(unseen),
        unseen_mint_unique_mints=len({row.mint for row in unseen}),
        seen_mint_rows=len(seen),
        seen_mint_unique_mints=len({row.mint for row in seen}),
        seen_actor_rows=seen_actor,
        unseen_actor_rows=unseen_actor,
        null_actor_rows=null_actor,
    )


def _check_novelty_checkpoint(
    partition: str,
    stats: _NoveltyStats,
    checkpoint: _CohortCheckpoint,
) -> None:
    prefix = "validation" if partition == "validation" else "test"
    expected_values = (
        getattr(checkpoint, f"expected_{prefix}_unseen_mint_rows"),
        getattr(
            checkpoint,
            f"expected_{prefix}_unseen_mint_unique_mints",
        ),
        getattr(checkpoint, f"expected_{prefix}_seen_mint_rows"),
        getattr(
            checkpoint,
            f"expected_{prefix}_seen_mint_unique_mints",
        ),
        getattr(checkpoint, f"expected_{prefix}_seen_actor_rows"),
        getattr(checkpoint, f"expected_{prefix}_unseen_actor_rows"),
        getattr(checkpoint, f"expected_{prefix}_null_actor_rows"),
    )
    actual_values = (
        stats.unseen_mint_rows,
        stats.unseen_mint_unique_mints,
        stats.seen_mint_rows,
        stats.seen_mint_unique_mints,
        stats.seen_actor_rows,
        stats.unseen_actor_rows,
        stats.null_actor_rows,
    )
    if actual_values != expected_values:
        raise ValueError(
            f"{partition} novelty checkpoint contradicts frozen evidence"
        )


def _enforce_structural_floors(
    checkpoint: _CohortCheckpoint,
    *,
    eligible_count: int,
    training_count: int,
    validation_count: int,
    test_count: int,
    validation_stats: _NoveltyStats,
    test_stats: _NoveltyStats,
) -> None:
    checks = (
        ("total eligible", eligible_count, checkpoint.minimum_total_eligible_rows),
        ("training", training_count, checkpoint.minimum_training_rows),
        ("validation", validation_count, checkpoint.minimum_validation_rows),
        ("TEST", test_count, checkpoint.minimum_test_rows),
        (
            "unseen-mint validation rows",
            validation_stats.unseen_mint_rows,
            checkpoint.minimum_unseen_mint_validation_rows,
        ),
        (
            "unseen-mint validation unique mints",
            validation_stats.unseen_mint_unique_mints,
            checkpoint.minimum_unseen_mint_validation_unique_mints,
        ),
        (
            "unseen-mint TEST rows",
            test_stats.unseen_mint_rows,
            checkpoint.minimum_unseen_mint_test_rows,
        ),
        (
            "unseen-mint TEST unique mints",
            test_stats.unseen_mint_unique_mints,
            checkpoint.minimum_unseen_mint_test_unique_mints,
        ),
    )
    for label, actual, minimum in checks:
        if actual < minimum:
            raise ValueError(
                f"structural floor failed for {label}: "
                f"{actual} < {minimum}"
            )


def _accepted_decisions(
    populations: tuple[
        tuple[str, tuple[Fl9V2SourceDecision, ...]], ...
    ],
    *,
    assessment_fingerprints: dict[tuple[object, ...], str],
    training_mints: set[str],
    training_actors: set[str],
) -> tuple[Fl9V2AcceptedDecision, ...]:
    values: list[Fl9V2AcceptedDecision] = []
    for partition, rows in populations:
        for row in rows:
            if partition == "training":
                mint_novelty = "not_applicable"
                actor_novelty = "not_applicable"
            else:
                mint_novelty = (
                    "seen" if row.mint in training_mints else "unseen"
                )
                if row.actor is None:
                    actor_novelty = "null"
                else:
                    actor_novelty = (
                        "seen"
                        if row.actor in training_actors
                        else "unseen"
                    )
            try:
                assessment_fingerprint = assessment_fingerprints[
                    row.decision_identity
                ]
            except KeyError as exc:
                raise ValueError(
                    "accepted decision missing assessment fingerprint"
                ) from exc
            values.append(
                Fl9V2AcceptedDecision(
                    decision_identity=row.decision_identity,
                    partition=partition,
                    assessment_fingerprint_sha256=assessment_fingerprint,
                    mint_novelty=mint_novelty,
                    actor_novelty=actor_novelty,
                )
            )
    return tuple(
        sorted(
            values,
            key=lambda value: _identity_sort_key(value.decision_identity),
        )
    )


def _concentration(
    rows: tuple[Fl9V2SourceDecision, ...],
) -> Fl9V2ConcentrationSummary:
    counts = Counter(row.mint for row in rows)
    total = len(rows)
    if total == 0:
        return Fl9V2ConcentrationSummary(
            row_count=0,
            unique_mint_count=0,
            top1_share=0.0,
            top3_share=0.0,
            top5_share=0.0,
            top10_share=0.0,
            hhi=0.0,
            effective_mint_count=0.0,
        )
    ordered = sorted(counts.values(), reverse=True)
    shares = tuple(count / total for count in ordered)
    hhi = sum(value * value for value in shares)
    return Fl9V2ConcentrationSummary(
        row_count=total,
        unique_mint_count=len(counts),
        top1_share=sum(shares[:1]),
        top3_share=sum(shares[:3]),
        top5_share=sum(shares[:5]),
        top10_share=sum(shares[:10]),
        hhi=hhi,
        effective_mint_count=1.0 / hhi,
    )


def _rows_identity_fingerprint(
    rows: tuple[Fl9V2SourceDecision, ...],
) -> str:
    return _identity_fingerprint(
        tuple(row.decision_identity for row in rows)
    )


def _identity_fingerprint(
    identities: tuple[tuple[object, ...], ...],
) -> str:
    canonical = tuple(sorted(identities, key=_identity_sort_key))
    return _sha256_canonical(
        [list(identity) for identity in canonical]
    )


def _identity_sort_key(
    identity: tuple[object, ...],
) -> tuple[object, ...]:
    return (identity[6], identity[2], identity[0], identity[1])


def _row_sort_key(
    row: Fl9V2SourceDecision,
) -> tuple[object, ...]:
    return (
        row.observed_at_unix_ms,
        row.sequence,
        row.signature,
        row.ordinal,
    )


def _float_hex_or_none(value: float | None) -> object:
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError("assessment contains non-finite float")
    return {"__float_hex__": value.hex()}


def _require_checkpoint(
    label: str,
    actual: object,
    expected: object,
) -> None:
    if actual != expected:
        raise ValueError(
            f"{label} contradicts frozen cohort checkpoint: "
            f"{actual!r} != {expected!r}"
        )


def _canonical_value(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical fingerprint rejects non-finite float")
        return {"__float_hex__": value.hex()}
    if isinstance(value, dict):
        return {
            key: _canonical_value(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _sha256_canonical(value: object) -> str:
    encoded = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
