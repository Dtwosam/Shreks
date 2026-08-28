from __future__ import annotations

import sqlite3

from shreks_brain.observer_campaign.coordinator import (
    ObserverCampaignCandidateStore,
    ObserverPaperCampaignSelectionPolicy,
)
from shreks_brain.observer_market import ObserverMarketReadPolicy


AS_OF = 2_000_000


def _create_schema(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE token_candidates (
            id INTEGER PRIMARY KEY,
            mint TEXT NOT NULL,
            discovered_at_unix_ms INTEGER NOT NULL
        );
        CREATE TABLE market_snapshots (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL,
            source TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            pair_created_at_unix_ms INTEGER
        );
        """
    )
    connection.execute(
        "INSERT INTO token_candidates (id, mint, discovered_at_unix_ms) VALUES (1, 'MintCanonical111', 1000000)"
    )
    return connection


def _policy() -> ObserverMarketReadPolicy:
    return ObserverMarketReadPolicy(
        version="market-read-v1",
        source_priority=("dexscreener", "meteora"),
        max_current_age_ms=120_000,
        local_range_lookback_ms=1_000_000,
    )


def _selection() -> ObserverPaperCampaignSelectionPolicy:
    return ObserverPaperCampaignSelectionPolicy(
        recent_lookback_ms=1_800_000,
        max_entry_candidates=2,
    )


def test_selector_uses_canonical_current_pair_age_when_other_pairs_disagree(tmp_path):
    database = tmp_path / "observer.db"
    connection = _create_schema(database)
    connection.executemany(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, pair_address, pair_created_at_unix_ms)
           VALUES (?, 1, ?, 'dexscreener', ?, ?)""",
        (
            (1, AS_OF - 10_000, "PairCanonicalFresh", AS_OF - 100_000),
            (2, AS_OF - 10_000, "PairOtherOld", AS_OF - 1_900_000),
        ),
    )
    connection.commit()
    connection.close()

    store = ObserverCampaignCandidateStore(database)
    selected = store.recent_candidates(
        as_of_unix_ms=AS_OF,
        policy=_selection(),
        pair_age_window_ms=(60_000, 1_800_000),
        market_read_policy=_policy(),
    )

    assert tuple(candidate.candidate_id for candidate in selected) == (1,)
    assert tuple(candidate.mint for candidate in selected) == ("MintCanonical111",)


def test_selector_does_not_promote_fresh_secondary_pair_when_canonical_pair_is_expired(tmp_path):
    database = tmp_path / "observer.db"
    connection = _create_schema(database)
    connection.executemany(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, pair_address, pair_created_at_unix_ms)
           VALUES (?, 1, ?, 'dexscreener', ?, ?)""",
        (
            (1, AS_OF - 10_000, "PairCanonicalOld", AS_OF - 1_900_000),
            (2, AS_OF - 10_000, "PairSecondaryFresh", AS_OF - 100_000),
        ),
    )
    connection.commit()
    connection.close()

    store = ObserverCampaignCandidateStore(database)
    selected = store.recent_candidates(
        as_of_unix_ms=AS_OF,
        policy=_selection(),
        pair_age_window_ms=(60_000, 1_800_000),
        market_read_policy=_policy(),
    )

    assert selected == ()
