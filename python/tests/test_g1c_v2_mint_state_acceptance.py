from __future__ import annotations

import sqlite3

from shreks_brain.observer_campaign.runtime import (
    bootstrap_observer_paper_campaign_runtime,
)
from shreks_brain.telemetry.g1c_v2_mint_state_acceptance import (
    analyze_mint_state_acceptance,
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


def test_historical_analyzer_replays_selected_candidates_without_mutating_database(
    tmp_path,
) -> None:
    from test_observer_campaign_runner import AS_OF
    from test_observer_campaign_runtime import _runtime_config

    config = _runtime_config(tmp_path, max_cycles=1)
    with sqlite3.connect(config.observer_database_path) as connection:
        connection.execute("DELETE FROM token_mint_states")
        for candidate_id in (1, 2):
            current = AS_OF - 10_000
            # The shared fixture's B1 max age is 100_000 ms. With a 60 s
            # evidence interval the half-age cap derives a 50_000 ms refresh age,
            # so a 60_000 ms row-to-row gap is a valid pre-expiry refresh.
            previous = current - 60_000
            connection.execute(
                """INSERT INTO token_mint_states
                   (candidate_id, provider, decimals, mint_authority, freeze_authority,
                    slot, observed_at_unix_ms)
                   VALUES (?, 'helius', 6, NULL, NULL, ?, ?)""",
                (candidate_id, str(candidate_id * 1000 + 1), previous),
            )
            connection.execute(
                """INSERT INTO token_mint_states
                   (candidate_id, provider, decimals, mint_authority, freeze_authority,
                    slot, observed_at_unix_ms)
                   VALUES (?, 'helius', 6, NULL, NULL, ?, ?)""",
                (candidate_id, str(candidate_id * 1000 + 2), current),
            )
        connection.commit()

    runner = bootstrap_observer_paper_campaign_runtime(config).runner
    runner.run_cycle(AS_OF, AS_OF)
    before_mtime = config.observer_database_path.stat().st_mtime_ns

    result = analyze_mint_state_acceptance(
        config.observer_database_path,
        config.manifest_path,
        window_start_unix_ms=AS_OF - 1,
        window_end_unix_ms=AS_OF,
        evidence_cycle_interval_ms=60_000,
    )

    assert result["status"] == "PASS"
    assert result["reconstructed_checkpoint_count"] == 1
    assert result["selected_observation_count"] == 2
    assert result["proactive_refresh_count"] == 2
    assert result["selected_missing_mint_count"] == 0
    assert result["selected_stale_mint_count"] == 0
    assert config.observer_database_path.stat().st_mtime_ns == before_mtime
