from __future__ import annotations

from dataclasses import replace
import sqlite3

from shreks_brain.observer_campaign.coordinator import (
    ObserverPaperCampaignSelectionPolicy,
    assemble_observer_paper_campaign_cycle,
)

from test_observer_campaign_coordinator_assembly import (
    SECOND_MINT,
    _seed_two_candidates,
)
from test_observer_campaign_runner import (
    AS_OF,
    MINT,
    _bundle,
    _environment,
    _state,
)


def test_fresh_launch_entry_slot_skips_expired_recently_active_candidate(tmp_path) -> None:
    database = tmp_path / "observer.db"
    _seed_two_candidates(database)

    connection = sqlite3.connect(database)
    connection.execute(
        """UPDATE market_snapshots
           SET pair_created_at_unix_ms = 200000
           WHERE candidate_id = 1"""
    )
    connection.execute(
        """UPDATE market_snapshots
           SET pair_created_at_unix_ms = 0
           WHERE candidate_id = 2"""
    )
    connection.execute(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
            venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
            volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1,
            pair_created_at_unix_ms)
           SELECT 999, candidate_id, ?, source, ? - 1,
                  venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
                  volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1,
                  0
           FROM market_snapshots
           WHERE candidate_id = 2
             AND observed_at_unix_ms <= ?
           ORDER BY observed_at_unix_ms DESC, id DESC
           LIMIT 1""",
        (AS_OF - 100, AS_OF - 100, AS_OF),
    )
    connection.commit()
    connection.close()

    template = _bundle()
    template = replace(
        template,
        fresh_launch_policy=replace(
            template.fresh_launch_policy,
            min_age_seconds=60.0,
            max_age_seconds=900.0,
        ),
    )

    cycle, audit = assemble_observer_paper_campaign_cycle(
        database,
        _state(),
        AS_OF,
        template,
        _environment(),
        ObserverPaperCampaignSelectionPolicy(
            recent_lookback_ms=100_000,
            max_entry_candidates=1,
        ),
        global_risk_halt=False,
    )

    assert audit.selected_candidate_ids == (1,)
    assert audit.selected_mints == (MINT,)
    assert audit.ranked_entry_mints == (MINT,)
    assert tuple(item.mint for item in cycle.entry_candidates) == (MINT,)
    assert SECOND_MINT not in audit.selected_mints
