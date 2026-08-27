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


def _set_pair_created_at(database, candidate_id: int, created_at_unix_ms: int) -> None:
    connection = sqlite3.connect(database)
    connection.execute(
        """UPDATE market_snapshots
           SET pair_created_at_unix_ms =
               CASE
                   WHEN observed_at_unix_ms >= ? THEN ?
                   ELSE NULL
               END
           WHERE candidate_id = ?""",
        (created_at_unix_ms, created_at_unix_ms, candidate_id),
    )
    connection.commit()
    connection.close()


def _make_candidate_two_most_recent(database, pair_created_at_unix_ms: int) -> None:
    connection = sqlite3.connect(database)
    connection.execute(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
            venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
            volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1,
            pair_created_at_unix_ms)
           SELECT 999, candidate_id, ?, source, ? - 1,
                  venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
                  volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1, ?
           FROM market_snapshots
           WHERE candidate_id = 2
             AND observed_at_unix_ms <= ?
           ORDER BY observed_at_unix_ms DESC, id DESC
           LIMIT 1""",
        (
            AS_OF - 100,
            AS_OF - 100,
            pair_created_at_unix_ms,
            AS_OF,
        ),
    )
    connection.commit()
    connection.close()


def _make_candidate_two_market_stale(database) -> None:
    connection = sqlite3.connect(database)
    connection.execute(
        """DELETE FROM market_snapshots
           WHERE candidate_id = 2
             AND observed_at_unix_ms >= ?""",
        (AS_OF - 60_000,),
    )
    connection.commit()
    connection.close()


def _fresh_launch_template():
    template = _bundle()
    return replace(
        template,
        fresh_launch_policy=replace(
            template.fresh_launch_policy,
            min_age_seconds=60.0,
            max_age_seconds=900.0,
        ),
    )


def _assemble_one(database):
    return assemble_observer_paper_campaign_cycle(
        database,
        _state(),
        AS_OF,
        _fresh_launch_template(),
        _environment(),
        ObserverPaperCampaignSelectionPolicy(
            recent_lookback_ms=100_000,
            max_entry_candidates=1,
        ),
        global_risk_halt=False,
    )


def test_fresh_launch_entry_slot_skips_expired_recently_active_candidate(tmp_path) -> None:
    database = tmp_path / "observer.db"
    _seed_two_candidates(database)

    _set_pair_created_at(database, 1, AS_OF - 800_000)
    _set_pair_created_at(database, 2, AS_OF - 1_000_000)
    _make_candidate_two_most_recent(database, AS_OF - 1_000_000)

    cycle, audit = _assemble_one(database)

    assert audit.selected_candidate_ids == (1,)
    assert audit.selected_mints == (MINT,)
    assert audit.ranked_entry_mints == (MINT,)
    assert tuple(item.mint for item in cycle.entry_candidates) == (MINT,)
    assert SECOND_MINT not in audit.selected_mints


def test_fresh_launch_entry_slot_prefers_in_window_candidate_over_too_young(tmp_path) -> None:
    database = tmp_path / "observer.db"
    _seed_two_candidates(database)

    _set_pair_created_at(database, 1, AS_OF - 800_000)
    _set_pair_created_at(database, 2, AS_OF - 30_000)
    _make_candidate_two_most_recent(database, AS_OF - 30_000)

    cycle, audit = _assemble_one(database)

    assert audit.selected_candidate_ids == (1,)
    assert audit.selected_mints == (MINT,)
    assert tuple(item.mint for item in cycle.entry_candidates) == (MINT,)


def test_fresh_launch_entry_slot_uses_too_young_candidate_when_no_in_window_exists(tmp_path) -> None:
    database = tmp_path / "observer.db"
    _seed_two_candidates(database)

    _set_pair_created_at(database, 1, AS_OF - 1_000_000)
    _set_pair_created_at(database, 2, AS_OF - 30_000)
    _make_candidate_two_most_recent(database, AS_OF - 30_000)

    cycle, audit = _assemble_one(database)

    assert audit.selected_candidate_ids == (2,)
    assert audit.selected_mints == (SECOND_MINT,)
    assert tuple(item.mint for item in cycle.entry_candidates) == (SECOND_MINT,)


def test_fresh_launch_selection_skips_candidate_without_current_market_snapshot(tmp_path) -> None:
    database = tmp_path / "observer.db"
    _seed_two_candidates(database)

    _set_pair_created_at(database, 1, AS_OF - 800_000)
    _set_pair_created_at(database, 2, AS_OF - 700_000)
    _make_candidate_two_market_stale(database)

    cycle, audit = assemble_observer_paper_campaign_cycle(
        database,
        _state(),
        AS_OF,
        _fresh_launch_template(),
        _environment(),
        ObserverPaperCampaignSelectionPolicy(
            recent_lookback_ms=100_000,
            max_entry_candidates=2,
        ),
        global_risk_halt=False,
    )

    assert audit.selected_candidate_ids == (1,)
    assert audit.selected_mints == (MINT,)
    assert tuple(item.mint for item in cycle.entry_candidates) == (MINT,)
    assert SECOND_MINT not in audit.selected_mints
