from __future__ import annotations

import sqlite3

import pytest

from shreks_brain.observer_campaign.coordinator import (
    ObserverCampaignCandidate,
    ObserverCampaignCandidateStore,
    ObserverCampaignCoordinatorError,
    ObserverPaperCampaignSelectionPolicy,
)


def _schema(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE token_candidates (
            id INTEGER PRIMARY KEY,
            mint TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            discovery_source TEXT NOT NULL,
            discovered_at_unix_ms INTEGER NOT NULL,
            venue TEXT
        );
        CREATE TABLE market_snapshots (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_observed_at_unix_ms INTEGER,
            venue TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            price_usd REAL,
            liquidity_usd REAL,
            volume_m5_usd REAL,
            volume_h1_usd REAL,
            buys_m5 INTEGER,
            sells_m5 INTEGER,
            buys_h1 INTEGER,
            sells_h1 INTEGER,
            pair_created_at_unix_ms INTEGER
        );
        """
    )
    return connection


def _seed(path) -> None:
    connection = _schema(path)
    connection.executemany(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (?, ?, ?, 'pump', ?, 'pump_fun')""",
        (
            (1, "MintOld", "PairOld", 10),
            (2, "MintRecentB", "PairB", 20),
            (3, "MintRecentA", "PairA", 30),
            (4, "MintFuture", "PairFuture", 2_000),
            (5, "MintRequired", "PairRequired", 5),
        ),
    )
    connection.executemany(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
            venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
            volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1,
            pair_created_at_unix_ms)
           VALUES (?, ?, ?, 'dexscreener', ?, 'pump_fun', ?, 1.0, 100.0,
                   10.0, 100.0, 10, 5, 100, 50, 1)""",
        (
            (1, 1, 100, 99, "PairOld"),
            (2, 2, 950, 949, "PairB"),
            (3, 2, 980, 979, "PairB"),
            (4, 3, 980, 978, "PairA"),
            (5, 4, 2_100, 2_099, "PairFuture"),
            (6, 5, 200, 199, "PairRequired"),
        ),
    )
    connection.commit()
    connection.close()


def test_selection_policy_requires_explicit_positive_bounds() -> None:
    policy = ObserverPaperCampaignSelectionPolicy(
        recent_lookback_ms=100,
        max_entry_candidates=2,
    )
    assert policy.recent_lookback_ms == 100
    assert policy.max_entry_candidates == 2

    for kwargs in (
        {"recent_lookback_ms": 0, "max_entry_candidates": 2},
        {"recent_lookback_ms": 100, "max_entry_candidates": 0},
        {"recent_lookback_ms": True, "max_entry_candidates": 2},
        {"recent_lookback_ms": 100, "max_entry_candidates": True},
    ):
        with pytest.raises(ValueError):
            ObserverPaperCampaignSelectionPolicy(**kwargs)


def test_recent_candidates_are_point_in_time_bounded_and_deterministic(tmp_path) -> None:
    database = tmp_path / "observer.sqlite"
    _seed(database)
    store = ObserverCampaignCandidateStore(database)

    candidates = store.recent_candidates(
        as_of_unix_ms=1_000,
        policy=ObserverPaperCampaignSelectionPolicy(
            recent_lookback_ms=100,
            max_entry_candidates=2,
        ),
    )

    assert candidates == (
        ObserverCampaignCandidate(
            candidate_id=2,
            mint="MintRecentB",
            latest_market_observed_at_unix_ms=980,
        ),
        ObserverCampaignCandidate(
            candidate_id=3,
            mint="MintRecentA",
            latest_market_observed_at_unix_ms=980,
        ),
    )
    assert all(value.mint != "MintFuture" for value in candidates)
    assert all(value.mint != "MintOld" for value in candidates)


def test_required_mints_resolve_outside_recent_window_without_future_data(tmp_path) -> None:
    database = tmp_path / "observer.sqlite"
    _seed(database)
    store = ObserverCampaignCandidateStore(database)

    assert store.resolve_required_mints(("MintRequired",), as_of_unix_ms=1_000) == (
        ObserverCampaignCandidate(
            candidate_id=5,
            mint="MintRequired",
            latest_market_observed_at_unix_ms=200,
        ),
    )

    with pytest.raises(ObserverCampaignCoordinatorError, match="not found"):
        store.resolve_required_mints(("MintFuture",), as_of_unix_ms=1_000)


def test_required_mint_identity_ambiguity_fails_closed(tmp_path) -> None:
    database = tmp_path / "observer.sqlite"
    _seed(database)
    connection = sqlite3.connect(database)
    connection.execute(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (6, 'MintRequired', 'OtherPair', 'pump', 6, 'pump_fun')"""
    )
    connection.execute(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
            venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
            volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1,
            pair_created_at_unix_ms)
           VALUES (7, 6, 300, 'dexscreener', 299, 'pump_fun', 'OtherPair', 1.0,
                   100.0, 10.0, 100.0, 10, 5, 100, 50, 1)"""
    )
    connection.commit()
    connection.close()

    store = ObserverCampaignCandidateStore(database)
    with pytest.raises(ObserverCampaignCoordinatorError, match="ambiguous"):
        store.resolve_required_mints(("MintRequired",), as_of_unix_ms=1_000)


def test_recent_duplicate_mint_identity_fails_closed_before_limit(tmp_path) -> None:
    database = tmp_path / "observer.sqlite"
    _seed(database)
    connection = sqlite3.connect(database)
    connection.execute(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (6, 'MintRecentB', 'OtherPair', 'pump', 40, 'pump_fun')"""
    )
    connection.execute(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
            venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
            volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1,
            pair_created_at_unix_ms)
           VALUES (7, 6, 970, 'dexscreener', 969, 'pump_fun', 'OtherPair', 1.0,
                   100.0, 10.0, 100.0, 10, 5, 100, 50, 1)"""
    )
    connection.commit()
    connection.close()

    store = ObserverCampaignCandidateStore(database)
    with pytest.raises(ObserverCampaignCoordinatorError, match="ambiguous"):
        store.recent_candidates(
            as_of_unix_ms=1_000,
            policy=ObserverPaperCampaignSelectionPolicy(
                recent_lookback_ms=100,
                max_entry_candidates=1,
            ),
        )


def test_candidate_store_is_read_only_and_does_not_create_missing_database(tmp_path) -> None:
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(ObserverCampaignCoordinatorError):
        ObserverCampaignCandidateStore(missing)
    assert not missing.exists()

    database = tmp_path / "observer.sqlite"
    _seed(database)
    store = ObserverCampaignCandidateStore(database)
    with pytest.raises(ObserverCampaignCoordinatorError):
        store.recent_candidates(
            as_of_unix_ms=-1,
            policy=ObserverPaperCampaignSelectionPolicy(
                recent_lookback_ms=100,
                max_entry_candidates=2,
            ),
        )
