from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shreks_brain.features import MarketFeaturePoint
from shreks_brain.observer_market.models import ObserverMarketReadPolicy
from shreks_brain.observer_market.store import (
    ObserverMarketReadError,
    ObserverMarketStore,
    build_market_feature_points,
)


_AS_OF = 2_000_000

_CANDIDATE_SCHEMA = """
CREATE TABLE token_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    pair_address TEXT NOT NULL DEFAULT '',
    discovery_source TEXT NOT NULL,
    discovered_at_unix_ms INTEGER NOT NULL,
    venue TEXT
);
"""

_MARKET_SCHEMA = """
CREATE TABLE market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_observed_at_unix_ms INTEGER,
    venue TEXT NOT NULL DEFAULT 'other_solana',
    pair_address TEXT NOT NULL DEFAULT '',
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


def _policy(**changes) -> ObserverMarketReadPolicy:
    values = {
        "version": "e13-read-v1",
        "source_priority": ("alpha", "beta"),
        "max_current_age_ms": 20_000,
        "local_range_lookback_ms": 300_000,
    }
    values.update(changes)
    return ObserverMarketReadPolicy(**values)


def _database(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_CANDIDATE_SCHEMA + _MARKET_SCHEMA)
        cursor = connection.execute(
            """INSERT INTO token_candidates (
                   mint, pair_address, discovery_source, discovered_at_unix_ms, venue
               ) VALUES (?, ?, ?, ?, ?)""",
            ("Mint111", "DiscoveryPair", "pump", 100_000, "pump_fun"),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def _insert_snapshot(
    path: Path,
    candidate_id: int,
    *,
    observed_at_unix_ms: int,
    source: str = "alpha",
    pair_address: str = "PairA",
    source_observed_at_unix_ms: int | None = None,
    price_usd=2.0,
    liquidity_usd=50_000.0,
    volume_m5_usd=5_000.0,
    volume_h1_usd=40_000.0,
    buys_m5=60,
    sells_m5=40,
    buys_h1=500,
    sells_h1=300,
    pair_created_at_unix_ms=None,
) -> int:
    if source_observed_at_unix_ms is None:
        source_observed_at_unix_ms = observed_at_unix_ms
    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute(
            """INSERT INTO market_snapshots (
                   candidate_id, observed_at_unix_ms, source,
                   source_observed_at_unix_ms, venue, pair_address,
                   price_usd, liquidity_usd, volume_m5_usd, volume_h1_usd,
                   buys_m5, sells_m5, buys_h1, sells_h1,
                   pair_created_at_unix_ms
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate_id,
                observed_at_unix_ms,
                source,
                source_observed_at_unix_ms,
                "raydium",
                pair_address,
                price_usd,
                liquidity_usd,
                volume_m5_usd,
                volume_h1_usd,
                buys_m5,
                sells_m5,
                buys_h1,
                sells_h1,
                pair_created_at_unix_ms,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def _populate_replay_fixture(path: Path) -> tuple[int, int]:
    candidate_id = _database(path)

    # Preferred source wins even though beta is newer.
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_999_000,
        source="beta",
        pair_address="PairB",
        price_usd=90.0,
    )
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_995_000,
        source="alpha",
        pair_address="PairA",
        price_usd=2.0,
        pair_created_at_unix_ms=None,
    )

    # Pair-created fallback must come from the selected path and not replace current.
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_990_000,
        source="alpha",
        pair_address="PairA",
        price_usd=2.1,
        pair_created_at_unix_ms=500_000,
    )
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_900_000,
        source="alpha",
        pair_address="PairA",
        price_usd=1.8,
        pair_created_at_unix_ms=400_000,
    )

    # Exact 1m target with duplicate timestamp: lower row id must win.
    one_minute_row_id = _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_940_000,
        source="alpha",
        pair_address="PairA",
        price_usd=1.5,
    )
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_940_000,
        source="alpha",
        pair_address="PairA",
        price_usd=1.6,
    )
    # Too young for the 1m window, but still ordinary local-range evidence.
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_940_001,
        source="alpha",
        pair_address="PairA",
        price_usd=1.7,
    )

    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_700_000,
        source="alpha",
        pair_address="PairA",
        price_usd=1.0,
    )
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_100_000,
        source="alpha",
        pair_address="PairA",
        price_usd=0.5,
    )

    # Local range only: within 300s lookback but not selected as a time anchor.
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_800_000,
        source="alpha",
        pair_address="PairA",
        price_usd=3.0,
    )

    # Same source, wrong pair; must not leak into anchors or local range.
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_940_000,
        source="alpha",
        pair_address="OtherPair",
        price_usd=100.0,
        pair_created_at_unix_ms=10,
    )

    # Same pair, wrong source; must not leak either.
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_940_000,
        source="beta",
        pair_address="PairA",
        price_usd=101.0,
    )

    # Future evidence must be completely invisible.
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=2_001_000,
        source="alpha",
        pair_address="PairA",
        price_usd=999.0,
        pair_created_at_unix_ms=1_999_999,
    )
    return candidate_id, one_minute_row_id


def test_load_window_uses_priority_same_path_exact_anchors_and_no_future_data(tmp_path):
    path = tmp_path / "observer.sqlite3"
    candidate_id, one_minute_row_id = _populate_replay_fixture(path)
    store = ObserverMarketStore(path)

    window = store.load_window(candidate_id, _AS_OF, _policy())

    assert window.candidate.candidate_id == candidate_id
    assert window.selected_source == "alpha"
    assert window.selected_pair_address == "PairA"
    assert window.current.observed_at_unix_ms == 1_995_000
    assert window.current.price_usd == 2.0
    assert window.one_minute_ago is not None
    assert window.one_minute_ago.row_id == one_minute_row_id
    assert window.one_minute_ago.observed_at_unix_ms == 1_940_000
    assert window.one_minute_ago.price_usd == 1.5
    assert window.five_minutes_ago is not None
    assert window.five_minutes_ago.observed_at_unix_ms == 1_700_000
    assert window.fifteen_minutes_ago is not None
    assert window.fifteen_minutes_ago.observed_at_unix_ms == 1_100_000
    assert window.pair_created_at_unix_ms == 500_000
    assert window.local_high_price_usd == 3.0
    assert window.local_low_price_usd == 1.0
    assert all(
        snapshot.observed_at_unix_ms <= _AS_OF
        for snapshot in (
            window.current,
            window.one_minute_ago,
            window.five_minutes_ago,
            window.fifteen_minutes_ago,
        )
        if snapshot is not None
    )


def test_source_priority_falls_through_when_higher_priority_source_has_no_fresh_row(tmp_path):
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_900_000,
        source="alpha",
        pair_address="PairA",
    )
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_999_000,
        source="beta",
        pair_address="PairB",
        price_usd=4.0,
    )

    window = ObserverMarketStore(path).load_window(candidate_id, _AS_OF, _policy())

    assert window.selected_source == "beta"
    assert window.selected_pair_address == "PairB"
    assert window.current.price_usd == 4.0


def test_stale_or_absent_current_snapshot_fails_closed_using_caller_policy(tmp_path):
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_979_999,
        source="alpha",
        pair_address="PairA",
    )
    store = ObserverMarketStore(path)

    with pytest.raises(ObserverMarketReadError, match="fresh"):
        store.load_window(candidate_id, _AS_OF, _policy(max_current_age_ms=20_000))


def test_missing_anchors_remain_none_and_zero_prices_do_not_define_local_range(tmp_path):
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_995_000,
        source="alpha",
        pair_address="PairA",
        price_usd=0.0,
    )
    store = ObserverMarketStore(path)

    window = store.load_window(candidate_id, _AS_OF, _policy())

    assert window.one_minute_ago is None
    assert window.five_minutes_ago is None
    assert window.fifteen_minutes_ago is None
    assert window.local_high_price_usd is None
    assert window.local_low_price_usd is None


def test_current_pair_creation_value_is_authoritative_over_history(tmp_path):
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_990_000,
        source="alpha",
        pair_address="PairA",
        pair_created_at_unix_ms=400_000,
    )
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_995_000,
        source="alpha",
        pair_address="PairA",
        pair_created_at_unix_ms=600_000,
    )

    window = ObserverMarketStore(path).load_window(candidate_id, _AS_OF, _policy())

    assert window.pair_created_at_unix_ms == 600_000


def test_malformed_persisted_market_value_fails_at_e13_boundary(tmp_path):
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    _insert_snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=1_995_000,
        source="alpha",
        pair_address="PairA",
        price_usd="not-a-number",
    )

    with pytest.raises(ObserverMarketReadError, match="invalid"):
        ObserverMarketStore(path).load_window(candidate_id, _AS_OF, _policy())


def test_build_market_feature_points_preserves_exact_observed_values(tmp_path):
    path = tmp_path / "observer.sqlite3"
    candidate_id, _ = _populate_replay_fixture(path)
    window = ObserverMarketStore(path).load_window(candidate_id, _AS_OF, _policy())

    current, one_minute, five_minutes, fifteen_minutes = build_market_feature_points(
        window
    )

    assert type(current) is MarketFeaturePoint
    assert current == MarketFeaturePoint(
        observed_at_unix_ms=1_995_000,
        price_usd=2.0,
        liquidity_usd=50_000.0,
        volume_m5_usd=5_000.0,
        volume_h1_usd=40_000.0,
        buys_m5=60,
        sells_m5=40,
        buys_h1=500,
        sells_h1=300,
    )
    assert one_minute is not None and one_minute.price_usd == 1.5
    assert five_minutes is not None and five_minutes.price_usd == 1.0
    assert fifteen_minutes is not None and fifteen_minutes.price_usd == 0.5


def test_load_window_rejects_invalid_identity_and_timestamp_arguments(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _database(path)
    store = ObserverMarketStore(path)

    with pytest.raises(ValueError, match="candidate_id"):
        store.load_window(0, _AS_OF, _policy())
    with pytest.raises(ValueError, match="as_of_unix_ms"):
        store.load_window(1, -1, _policy())
    with pytest.raises(ValueError, match="policy"):
        store.load_window(1, _AS_OF, object())
