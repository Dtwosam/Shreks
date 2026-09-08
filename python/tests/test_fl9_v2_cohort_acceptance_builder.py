from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.fl9_tradable_universe import (
    Fl9TradableUniverseAssessment,
)
from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2CohortAcceptancePolicy,
)
from shreks_brain.fl9_v2_cohort_acceptance.builder import (
    _CohortCheckpoint,
    _build_fl9_v2_cohort_acceptance_from_snapshot,
)
from shreks_brain.fl9_v2_cohort_acceptance.source import (
    Fl9V2SourceDecision,
    Fl9V2SourceSnapshot,
)


class RecordingStore:
    def __init__(self, assessments):
        self.assessments = list(assessments)
        self.calls = []

    def assess(self, **kwargs):
        self.calls.append(kwargs)
        return self.assessments[len(self.calls) - 1]


def _row(
    index: int,
    *,
    mint: str,
    actor: str | None,
    signature: str | None = None,
    ordinal: int = 0,
) -> Fl9V2SourceDecision:
    return Fl9V2SourceDecision(
        sequence=index,
        signature=signature or f"sig-{index}",
        ordinal=ordinal,
        provider="solana_public",
        observed_at_unix_ms=900 + (index * 100),
        mint=mint,
        quote_mint="quote-sol",
        venue="pump_swap",
        actor=actor,
    )


def _rows(*, shared_signature: bool = False):
    rows = [
        _row(1, mint="mint-a", actor="actor-1"),
        _row(2, mint="mint-b", actor="actor-2"),
        _row(3, mint="mint-c", actor="actor-3"),
        _row(4, mint="mint-d", actor="actor-4"),
        _row(5, mint="mint-a", actor="actor-1"),
        _row(
            6,
            mint="mint-b",
            actor="actor-5",
            signature="sig-shared" if shared_signature else None,
            ordinal=0,
        ),
        _row(
            7,
            mint="mint-e",
            actor="actor-1",
            signature="sig-shared" if shared_signature else None,
            ordinal=1 if shared_signature else 0,
        ),
        _row(8, mint="mint-f", actor="actor-6"),
        _row(9, mint="mint-e", actor="actor-6"),
        _row(10, mint="mint-a", actor="actor-7"),
    ]
    return tuple(rows)


def _snapshot(rows=None):
    policy = Fl9V2CohortAcceptancePolicy()
    values = rows or _rows()
    return Fl9V2SourceSnapshot(
        latest_session_id=123,
        source_sessions=policy.source_sessions,
        raw_decisions=values,
        cross_session_duplicate_count=0,
        raw_unique_mint_count=len({value.mint for value in values}),
    )


def _assessment(row, *, snapshot_row_id=1):
    policy = Fl9V2CohortAcceptancePolicy()
    return Fl9TradableUniverseAssessment(
        schema_name="shreks.fl9_tradable_universe_assessment",
        schema_version=1,
        policy_version=policy.tradable_universe_policy_version,
        policy_fingerprint_sha256=(
            policy.tradable_universe_policy_fingerprint_sha256
        ),
        mint=row.mint,
        quote_mint=row.quote_mint,
        decision_venue=row.venue,
        decision_observed_at_unix_ms=row.observed_at_unix_ms,
        eligible=True,
        reason="eligible",
        graduation_detected_at_unix_ms=900,
        candidate_id=1,
        snapshot_row_id=snapshot_row_id,
        snapshot_observed_at_unix_ms=row.observed_at_unix_ms - 1,
        snapshot_age_ms=1,
        selected_pair_address="pair",
        liquidity_usd=8_000.0,
        volume_h24_usd=25_000.0,
    )


def _checkpoint(**changes):
    values = dict(
        minimum_decision_observed_at_unix_ms=1_000,
        test_end_unix_ms=2_000,
        training_cut_unix_ms=1_600,
        validation_cut_unix_ms=1_800,
        expected_raw_row_count=10,
        expected_cross_session_duplicate_count=0,
        expected_raw_unique_mint_count=6,
        expected_eligibility_reason_counts=(("eligible", 10),),
        expected_eligible_row_count=10,
        expected_eligible_unique_mint_count=6,
        expected_training_raw_row_count=6,
        expected_validation_raw_row_count=2,
        expected_test_raw_row_count=2,
        expected_shared_signature_count=0,
        expected_training_quarantined_row_count=0,
        expected_validation_quarantined_row_count=0,
        expected_test_quarantined_row_count=0,
        expected_validation_unseen_mint_rows=2,
        expected_validation_unseen_mint_unique_mints=2,
        expected_validation_seen_mint_rows=0,
        expected_validation_seen_mint_unique_mints=0,
        expected_validation_seen_actor_rows=1,
        expected_validation_unseen_actor_rows=1,
        expected_validation_null_actor_rows=0,
        expected_test_unseen_mint_rows=1,
        expected_test_unseen_mint_unique_mints=1,
        expected_test_seen_mint_rows=1,
        expected_test_seen_mint_unique_mints=1,
        expected_test_seen_actor_rows=0,
        expected_test_unseen_actor_rows=2,
        expected_test_null_actor_rows=0,
        minimum_total_eligible_rows=1,
        minimum_training_rows=1,
        minimum_validation_rows=1,
        minimum_test_rows=1,
        minimum_unseen_mint_validation_rows=1,
        minimum_unseen_mint_validation_unique_mints=1,
        minimum_unseen_mint_test_rows=1,
        minimum_unseen_mint_test_unique_mints=1,
    )
    values.update(changes)
    return _CohortCheckpoint(**values)


def _build(*, rows=None, checkpoint=None, assessments=None):
    snapshot = _snapshot(rows)
    assessments = assessments or [
        _assessment(row) for row in snapshot.raw_decisions
    ]
    store = RecordingStore(assessments)
    result = _build_fl9_v2_cohort_acceptance_from_snapshot(
        snapshot=snapshot,
        tradable_store=store,
        policy=Fl9V2CohortAcceptancePolicy(),
        checkpoint=checkpoint or _checkpoint(),
    )
    return result, store


def test_builder_uses_authenticated_assessor_for_every_raw_row() -> None:
    result, store = _build()

    assert len(store.calls) == 10
    assert result.eligible_row_count == 10
    assert all(
        call["decision_venue"] == "pump_swap"
        for call in store.calls
    )


def test_builder_recomputes_exact_60_20_20_cuts_and_novelty() -> None:
    result, _ = _build()

    assert result.training_cut_unix_ms == 1_600
    assert result.validation_cut_unix_ms == 1_800
    assert result.training_raw_row_count == 6
    assert result.validation_raw_row_count == 2
    assert result.test_raw_row_count == 2
    assert result.validation_unseen_mint_row_count == 2
    assert result.validation_unseen_mint_unique_mint_count == 2
    assert result.test_unseen_mint_row_count == 1
    assert result.test_unseen_mint_unique_mint_count == 1

    validation = [
        value for value in result.accepted_decisions
        if value.partition == "validation"
    ]
    test = [
        value for value in result.accepted_decisions
        if value.partition == "test"
    ]
    assert {value.mint_novelty for value in validation} == {"unseen"}
    assert {
        value.decision_identity[3]: value.mint_novelty
        for value in test
    } == {
        "mint-e": "unseen",
        "mint-a": "seen",
    }


def test_repeated_mint_and_actor_survive_v2_population() -> None:
    result, _ = _build()
    identities = {
        value.decision_identity for value in result.accepted_decisions
    }

    assert _rows()[6].decision_identity in identities
    assert _rows()[8].decision_identity in identities
    assert result.shared_signature_count == 0


def test_shared_signature_is_quarantined_but_novelty_uses_raw_training() -> None:
    rows = _rows(shared_signature=True)
    checkpoint = _checkpoint(
        expected_shared_signature_count=1,
        expected_training_quarantined_row_count=1,
        expected_validation_quarantined_row_count=1,
        expected_validation_unseen_mint_rows=1,
        expected_validation_unseen_mint_unique_mints=1,
        expected_validation_seen_actor_rows=0,
        expected_validation_unseen_actor_rows=1,
    )
    result, _ = _build(rows=rows, checkpoint=checkpoint)

    assert result.shared_signature_count == 1
    assert result.training_row_count == 5
    assert result.validation_row_count == 1
    assert result.test_row_count == 2
    assert all(
        value.decision_identity[0] != "sig-shared"
        for value in result.accepted_decisions
    )


def test_checkpoint_drift_fails_closed_without_searching_another_split() -> None:
    with pytest.raises(ValueError, match="raw.*count|checkpoint"):
        _build(checkpoint=_checkpoint(expected_raw_row_count=11))

    with pytest.raises(ValueError, match="training cut|frozen cut|checkpoint"):
        _build(checkpoint=_checkpoint(training_cut_unix_ms=1_500))


def test_structural_floor_failure_fails_closed() -> None:
    with pytest.raises(ValueError, match="unseen.*TEST|structural floor"):
        _build(
            checkpoint=_checkpoint(
                minimum_unseen_mint_test_rows=2,
            )
        )


def test_assessment_evidence_fingerprint_changes_with_authenticated_snapshot() -> None:
    rows = _rows()
    first, _ = _build(
        assessments=[_assessment(row, snapshot_row_id=1) for row in rows]
    )
    second, _ = _build(
        assessments=[_assessment(row, snapshot_row_id=2) for row in rows]
    )

    assert (
        first.assessment_evidence_fingerprint_sha256
        != second.assessment_evidence_fingerprint_sha256
    )
    assert (
        first.accepted_identity_fingerprint_sha256
        == second.accepted_identity_fingerprint_sha256
    )


def test_concentration_is_diagnostic_not_an_admission_threshold() -> None:
    result, _ = _build()

    summaries = dict(result.concentration_summaries)
    assert summaries["full_eligible"].row_count == 10
    assert summaries["raw_training"].top1_share > 0
    assert result.structural_floor_passed is True
