from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from shreks_brain.fl9_v2_cohort_acceptance import (
    FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION,
    FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME,
    FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION,
    FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION,
    Fl9V2AcceptedDecision,
    Fl9V2CohortAcceptancePolicy,
    Fl9V2CohortEvidenceFloorPolicy,
    Fl9V2CoverageSessionCheckpoint,
)


def test_frozen_versions_and_numeric_contract_are_exact() -> None:
    floors = Fl9V2CohortEvidenceFloorPolicy()
    policy = Fl9V2CohortAcceptancePolicy()

    assert FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME == (
        "shreks.fl9_v2_cohort_acceptance"
    )
    assert FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION == 1
    assert FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION == (
        "fl9-v2-cohort-acceptance-v1"
    )
    assert FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION == (
        "fl9-v2-cohort-evidence-floor-v1"
    )

    assert policy.source_session_ids == tuple(range(115, 123))
    assert policy.required_latest_session_id == 123
    assert policy.minimum_decision_observed_at_unix_ms == 1_788_878_323_281
    assert policy.horizon_ms == 30_000
    assert policy.test_end_unix_ms == 1_788_902_289_835
    assert policy.selection_at_unix_ms == 1_788_902_319_835
    assert policy.training_cut_unix_ms == 1_788_892_302_791
    assert policy.validation_cut_unix_ms == 1_788_898_931_418

    assert floors.minimum_total_eligible_rows == 250_000
    assert floors.minimum_training_rows == 150_000
    assert floors.minimum_validation_rows == 50_000
    assert floors.minimum_test_rows == 50_000
    assert floors.minimum_unseen_mint_validation_rows == 40_000
    assert floors.minimum_unseen_mint_validation_unique_mints == 20
    assert floors.minimum_unseen_mint_test_rows == 40_000
    assert floors.minimum_unseen_mint_test_unique_mints == 25
    assert floors.minimum_natural_test_scored_observations == 40_000
    assert floors.minimum_unseen_mint_test_scored_observations == 35_000

    with pytest.raises(FrozenInstanceError):
        policy.horizon_ms = 60_000  # type: ignore[misc]

    with pytest.raises(ValueError, match="immutable|frozen|version"):
        replace(policy, horizon_ms=60_000)


def test_exact_session_checkpoint_metadata_is_frozen() -> None:
    policy = Fl9V2CohortAcceptancePolicy()

    assert policy.source_sessions == (
        Fl9V2CoverageSessionCheckpoint(
            session_id=115,
            provider="solana_public",
            process_session_sequence=1,
            first_notification_observed_at_unix_ms=1_788_878_323_281,
            last_notification_observed_at_unix_ms=1_788_878_840_118,
            notification_count=20_710,
        ),
        Fl9V2CoverageSessionCheckpoint(
            session_id=116,
            provider="solana_public",
            process_session_sequence=1,
            first_notification_observed_at_unix_ms=1_788_883_195_692,
            last_notification_observed_at_unix_ms=1_788_883_318_307,
            notification_count=269,
        ),
        Fl9V2CoverageSessionCheckpoint(
            session_id=117,
            provider="solana_public",
            process_session_sequence=2,
            first_notification_observed_at_unix_ms=1_788_883_321_082,
            last_notification_observed_at_unix_ms=1_788_886_814_126,
            notification_count=190_896,
        ),
        Fl9V2CoverageSessionCheckpoint(
            session_id=118,
            provider="solana_public",
            process_session_sequence=3,
            first_notification_observed_at_unix_ms=1_788_887_193_636,
            last_notification_observed_at_unix_ms=1_788_890_813_557,
            notification_count=196_433,
        ),
        Fl9V2CoverageSessionCheckpoint(
            session_id=119,
            provider="solana_public",
            process_session_sequence=4,
            first_notification_observed_at_unix_ms=1_788_890_820_688,
            last_notification_observed_at_unix_ms=1_788_891_310_394,
            notification_count=30_697,
        ),
        Fl9V2CoverageSessionCheckpoint(
            session_id=120,
            provider="solana_public",
            process_session_sequence=5,
            first_notification_observed_at_unix_ms=1_788_891_317_263,
            last_notification_observed_at_unix_ms=1_788_892_489_553,
            notification_count=62_883,
        ),
        Fl9V2CoverageSessionCheckpoint(
            session_id=121,
            provider="solana_public",
            process_session_sequence=6,
            first_notification_observed_at_unix_ms=1_788_895_790_049,
            last_notification_observed_at_unix_ms=1_788_900_928_410,
            notification_count=279_491,
        ),
        Fl9V2CoverageSessionCheckpoint(
            session_id=122,
            provider="solana_public",
            process_session_sequence=1,
            first_notification_observed_at_unix_ms=1_788_900_968_708,
            last_notification_observed_at_unix_ms=1_788_902_289_834,
            notification_count=64_497,
        ),
    )


def test_exact_input_only_checkpoint_counts_are_frozen() -> None:
    policy = Fl9V2CohortAcceptancePolicy()

    assert policy.expected_raw_row_count == 504_716
    assert policy.expected_cross_session_duplicate_count == 0
    assert policy.expected_raw_unique_mint_count == 394
    assert policy.expected_eligible_row_count == 274_334
    assert policy.expected_eligible_unique_mint_count == 146
    assert dict(policy.expected_eligibility_reason_counts) == {
        "below_minimum_liquidity_usd": 52_974,
        "below_minimum_volume_h24_usd": 1_109,
        "eligible": 274_334,
        "missing_fresh_exact_market_snapshot": 176_299,
    }
    assert policy.expected_training_raw_row_count == 164_645
    assert policy.expected_validation_raw_row_count == 54_858
    assert policy.expected_test_raw_row_count == 54_831
    assert policy.expected_shared_signature_count == 0
    assert policy.expected_training_quarantined_row_count == 0
    assert policy.expected_validation_quarantined_row_count == 0
    assert policy.expected_test_quarantined_row_count == 0

    assert policy.expected_validation_unseen_mint_rows == 49_754
    assert policy.expected_validation_unseen_mint_unique_mints == 24
    assert policy.expected_validation_seen_mint_rows == 5_104
    assert policy.expected_validation_seen_mint_unique_mints == 10
    assert policy.expected_validation_seen_actor_rows == 23_416
    assert policy.expected_validation_unseen_actor_rows == 31_442
    assert policy.expected_validation_null_actor_rows == 0

    assert policy.expected_test_unseen_mint_rows == 54_828
    assert policy.expected_test_unseen_mint_unique_mints == 31
    assert policy.expected_test_seen_mint_rows == 3
    assert policy.expected_test_seen_mint_unique_mints == 3
    assert policy.expected_test_seen_actor_rows == 11_841
    assert policy.expected_test_unseen_actor_rows == 42_990
    assert policy.expected_test_null_actor_rows == 0


def test_selection_clock_relationship_and_policy_fingerprints_are_exact() -> None:
    policy = Fl9V2CohortAcceptancePolicy()

    assert policy.selection_at_unix_ms - policy.horizon_ms == (
        policy.test_end_unix_ms
    )
    assert policy.tradable_universe_policy_version == (
        "fl9-tradable-universe-v1"
    )
    assert policy.tradable_universe_policy_fingerprint_sha256 == (
        "abfc6d21eb27d722956fbd267a10f352c887a909b3865a7a295eff95631777e4"
    )
    assert policy.feature_identity_firewall_version == (
        "fl8.3-feature-identity-firewall-v1"
    )
    assert policy.feature_identity_firewall_fingerprint_sha256 == (
        "e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0"
    )


def test_accepted_decision_requires_exact_identity_partition_and_novelty_values() -> None:
    identity = (
        "sig-1",
        0,
        1,
        "mint-1",
        "quote-1",
        "pump_swap",
        1_788_878_323_281,
    )
    value = Fl9V2AcceptedDecision(
        decision_identity=identity,
        partition="validation",
        assessment_fingerprint_sha256="a" * 64,
        mint_novelty="unseen",
        actor_novelty="seen",
    )
    assert value.decision_identity == identity

    with pytest.raises(ValueError, match="partition"):
        replace(value, partition="holdout")
    with pytest.raises(ValueError, match="mint.*novelty"):
        replace(value, mint_novelty="newish")
    with pytest.raises(ValueError, match="actor.*novelty"):
        replace(value, actor_novelty="missing")
    with pytest.raises(ValueError, match="SHA-256|fingerprint"):
        replace(value, assessment_fingerprint_sha256="bad")
