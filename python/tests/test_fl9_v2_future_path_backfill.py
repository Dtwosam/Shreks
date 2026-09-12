from __future__ import annotations

from types import SimpleNamespace

import pytest

from shreks_brain.fast_first_champion_v2.models import FastFirstChampionV2Policy
from shreks_brain.fl9_v2_future_path_backfill import build_backfill_request_document


def _accepted(identity):
    return SimpleNamespace(decision_identity=identity)


def test_request_is_exactly_cohort_scoped_and_preserves_session_boundaries():
    policy = FastFirstChampionV2Policy()
    sessions = (
        SimpleNamespace(session_id=115, provider="solana_public", process_session_sequence=1,
                        first_notification_observed_at_unix_ms=1000,
                        last_notification_observed_at_unix_ms=40000, notification_count=10),
        SimpleNamespace(session_id=116, provider="solana_public", process_session_sequence=2,
                        first_notification_observed_at_unix_ms=50000,
                        last_notification_observed_at_unix_ms=70000, notification_count=10),
    )
    artifact = SimpleNamespace(
        manifest=SimpleNamespace(
            artifact_fingerprint_sha256=policy.expected_cohort_artifact_fingerprint_sha256,
            accepted_identity_fingerprint_sha256=policy.expected_accepted_identity_fingerprint_sha256,
            policy_version=policy.cohort_policy_version, horizon_ms=policy.horizon_ms,
            source_sessions=sessions,
        ),
        accepted_decisions=(
            _accepted(("sig-a", 0, 1, "mint-a", "quote", "pump_swap", 2000)),
            _accepted(("sig-b", 1, 2, "mint-b", "quote", "pump_swap", 69990)),
        ),
    )

    document = build_backfill_request_document(artifact, policy=policy)

    assert document["horizon_ms"] == 30000
    assert [row["signature"] for row in document["decisions"]] == ["sig-a", "sig-b"]
    assert document["decisions"][0]["coverage_session_id"] == 115
    assert document["decisions"][0]["coverage_complete_through_unix_ms"] == 40000
    assert document["decisions"][1]["coverage_session_id"] == 116
    assert document["decisions"][1]["coverage_complete_through_unix_ms"] == 70000


def test_request_rejects_cohort_fingerprint_drift():
    policy = FastFirstChampionV2Policy()
    artifact = SimpleNamespace(
        manifest=SimpleNamespace(
            artifact_fingerprint_sha256="0" * 64,
            accepted_identity_fingerprint_sha256=policy.expected_accepted_identity_fingerprint_sha256,
            policy_version=policy.cohort_policy_version, horizon_ms=policy.horizon_ms,
            source_sessions=(),
        ),
        accepted_decisions=(),
    )
    with pytest.raises(ValueError, match="cohort artifact fingerprint"):
        build_backfill_request_document(artifact, policy=policy)
