from __future__ import annotations

from shreks_brain.telemetry.g1c_v2_mint_state_acceptance import (
    MintStateAcceptanceSample,
    derive_mint_state_refresh_age_ms,
    evaluate_mint_state_acceptance_samples,
)


def _sample(
    *,
    candidate_id: int = 7,
    decision_at: int = 2_000_000,
    mint_at: int | None = 1_500_000,
    previous_mint_at: int | None = 900_000,
) -> MintStateAcceptanceSample:
    return MintStateAcceptanceSample(
        candidate_id=candidate_id,
        decision_as_of_unix_ms=decision_at,
        mint_observed_at_unix_ms=mint_at,
        previous_mint_observed_at_unix_ms=previous_mint_at,
    )


def test_refresh_age_matches_deployed_headroom_contract() -> None:
    assert derive_mint_state_refresh_age_ms(
        max_critical_data_age_ms=900_000,
        evidence_cycle_interval_ms=60_000,
    ) == 540_000


def test_qualifying_preexpiry_refresh_passes() -> None:
    result = evaluate_mint_state_acceptance_samples(
        (_sample(),),
        max_critical_data_age_ms=900_000,
        evidence_cycle_interval_ms=60_000,
    )

    assert result["status"] == "PASS"
    assert result["selected_observation_count"] == 1
    assert result["proactive_refresh_count"] == 1
    assert result["selected_missing_mint_count"] == 0
    assert result["selected_stale_mint_count"] == 0
    assert result["max_selected_mint_age_ms"] == 500_000
    assert result["mint_state_refresh_age_ms"] == 540_000


def test_clean_window_without_refresh_example_holds() -> None:
    result = evaluate_mint_state_acceptance_samples(
        (
            _sample(
                decision_at=1_700_000,
                mint_at=1_500_000,
                previous_mint_at=1_100_000,
            ),
        ),
        max_critical_data_age_ms=900_000,
        evidence_cycle_interval_ms=60_000,
    )

    assert result["status"] == "HOLD_INSUFFICIENT_EVIDENCE"
    assert result["proactive_refresh_count"] == 0
    assert result["selected_stale_mint_count"] == 0


def test_missing_or_b1_stale_selected_mint_fails() -> None:
    missing = evaluate_mint_state_acceptance_samples(
        (_sample(mint_at=None, previous_mint_at=None),),
        max_critical_data_age_ms=900_000,
        evidence_cycle_interval_ms=60_000,
    )
    stale = evaluate_mint_state_acceptance_samples(
        (
            _sample(
                decision_at=2_000_000,
                mint_at=1_099_999,
                previous_mint_at=500_000,
            ),
        ),
        max_critical_data_age_ms=900_000,
        evidence_cycle_interval_ms=60_000,
    )

    assert missing["status"] == "FAILED"
    assert missing["selected_missing_mint_count"] == 1
    assert stale["status"] == "FAILED"
    assert stale["selected_stale_mint_count"] == 1


def test_future_mint_row_never_satisfies_historical_selection() -> None:
    result = evaluate_mint_state_acceptance_samples(
        (
            _sample(
                decision_at=2_000_000,
                mint_at=2_000_001,
                previous_mint_at=1_400_000,
            ),
        ),
        max_critical_data_age_ms=900_000,
        evidence_cycle_interval_ms=60_000,
    )

    assert result["status"] == "FAILED"
    assert result["invalid_observation_count"] == 1


def test_refresh_transitions_are_counted_once_across_reused_decisions() -> None:
    first = _sample(decision_at=2_000_000)
    second = _sample(decision_at=2_030_000)

    result = evaluate_mint_state_acceptance_samples(
        (first, second),
        max_critical_data_age_ms=900_000,
        evidence_cycle_interval_ms=60_000,
    )

    assert result["selected_observation_count"] == 2
    assert result["proactive_refresh_count"] == 1
