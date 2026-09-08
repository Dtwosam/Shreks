from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shreks_brain.observer_market.models import ObserverCandidateIdentity
from shreks_brain.observer_market.store import (
    ObserverMarketReadError,
    ObserverMarketStore,
)


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
    base_mint TEXT NOT NULL DEFAULT 'Mint111',
    quote_mint TEXT NOT NULL DEFAULT 'Quote111',
    price_usd REAL,
    liquidity_usd REAL,
    volume_m5_usd REAL,
    volume_h1_usd REAL,
    volume_h24_usd REAL,
    buys_m5 INTEGER,
    sells_m5 INTEGER,
    buys_h1 INTEGER,
    sells_h1 INTEGER,
    pair_created_at_unix_ms INTEGER
);
"""


def _create_database(path: Path, *, extra_columns: bool = False) -> None:
    connection = sqlite3.connect(path)
    try:
        candidate_schema = _CANDIDATE_SCHEMA
        market_schema = _MARKET_SCHEMA
        if extra_columns:
            candidate_schema = candidate_schema.replace(
                "venue TEXT\n", "venue TEXT,\n    future_candidate_field TEXT\n"
            )
            market_schema = market_schema.replace(
                "pair_created_at_unix_ms INTEGER\n",
                "pair_created_at_unix_ms INTEGER,\n    future_market_field TEXT\n",
            )
        connection.executescript(candidate_schema + market_schema)
        connection.commit()
    finally:
        connection.close()


def _insert_candidate(
    path: Path,
    *,
    mint: str = "Mint111",
    pair_address: str = "Pair111",
    discovery_source: str = "pump",
    discovered_at_unix_ms: int = 1_000,
    venue: str | None = "pump_fun",
) -> int:
    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute(
            """INSERT INTO token_candidates (
                   mint, pair_address, discovery_source, discovered_at_unix_ms, venue
               ) VALUES (?, ?, ?, ?, ?)""",
            (mint, pair_address, discovery_source, discovered_at_unix_ms, venue),
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
    source: str = "dexscreener",
    venue: str = "pump_swap",
    base_mint: str = "Mint111",
    quote_mint: str = "Quote111",
    pair_address: str = "Pair111",
    liquidity_usd: float = 5_000.0,
    volume_h24_usd: float = 2_000.0,
) -> int:
    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute(
            """INSERT INTO market_snapshots (
                   candidate_id,
                   observed_at_unix_ms,
                   source,
                   source_observed_at_unix_ms,
                   venue,
                   pair_address,
                   base_mint,
                   quote_mint,
                   liquidity_usd,
                   volume_h24_usd
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate_id,
                observed_at_unix_ms,
                source,
                observed_at_unix_ms,
                venue,
                pair_address,
                base_mint,
                quote_mint,
                liquidity_usd,
                volume_h24_usd,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def test_missing_database_fails_without_creating_file(tmp_path):
    path = tmp_path / "missing.sqlite3"

    with pytest.raises(ObserverMarketReadError, match="open"):
        ObserverMarketStore(path)

    assert not path.exists()


def test_missing_required_table_or_column_fails_closed(tmp_path):
    missing_table = tmp_path / "missing-table.sqlite3"
    connection = sqlite3.connect(missing_table)
    try:
        connection.executescript(_CANDIDATE_SCHEMA)
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ObserverMarketReadError, match="market_snapshots"):
        ObserverMarketStore(missing_table)

    missing_column = tmp_path / "missing-column.sqlite3"
    connection = sqlite3.connect(missing_column)
    try:
        connection.executescript(
            _CANDIDATE_SCHEMA
            + _MARKET_SCHEMA.replace("    venue TEXT NOT NULL DEFAULT 'other_solana',\n", "")
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ObserverMarketReadError, match="venue"):
        ObserverMarketStore(missing_column)


def test_additive_future_columns_are_allowed(tmp_path):
    path = tmp_path / "future.sqlite3"
    _create_database(path, extra_columns=True)

    store = ObserverMarketStore(path)

    assert isinstance(store, ObserverMarketStore)


def test_unique_candidate_resolves_to_exact_e13_identity(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    candidate_id = _insert_candidate(path)
    store = ObserverMarketStore(path)

    candidate = store.resolve_candidate("Mint111")

    assert type(candidate) is ObserverCandidateIdentity
    assert candidate == ObserverCandidateIdentity(
        candidate_id=candidate_id,
        mint="Mint111",
        pair_address="Pair111",
        discovery_source="pump",
        discovered_at_unix_ms=1_000,
        venue="pump_fun",
    )


def test_absent_candidate_fails_closed(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    store = ObserverMarketStore(path)

    with pytest.raises(ObserverMarketReadError, match="not found"):
        store.resolve_candidate("MissingMint")


def test_duplicate_mint_fails_until_pair_or_discovery_filter_disambiguates(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    first_id = _insert_candidate(path, pair_address="Pair111", discovery_source="pump")
    second_id = _insert_candidate(
        path,
        pair_address="Pair222",
        discovery_source="dexscreener",
        venue="raydium",
    )
    store = ObserverMarketStore(path)

    with pytest.raises(ObserverMarketReadError, match="ambiguous"):
        store.resolve_candidate("Mint111")

    by_pair = store.resolve_candidate("Mint111", pair_address="Pair111")
    by_source = store.resolve_candidate("Mint111", discovery_source="dexscreener")

    assert by_pair.candidate_id == first_id
    assert by_source.candidate_id == second_id
    assert by_source.pair_address == "Pair222"


def test_filters_are_exact_and_empty_pair_sentinel_is_supported(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    empty_pair_id = _insert_candidate(path, pair_address="", discovery_source="pump")
    _insert_candidate(path, pair_address="Pair111", discovery_source="pump")
    store = ObserverMarketStore(path)

    candidate = store.resolve_candidate(
        "Mint111", pair_address="", discovery_source="pump"
    )

    assert candidate.candidate_id == empty_pair_id
    assert candidate.pair_address == ""


def test_invalid_query_arguments_fail_before_sql(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    store = ObserverMarketStore(path)

    with pytest.raises(ValueError, match="mint"):
        store.resolve_candidate("")
    with pytest.raises(ValueError, match="discovery_source"):
        store.resolve_candidate("Mint111", pair_address=None, discovery_source="")


def test_point_in_time_candidate_resolution_ignores_future_snapshot_ownership(
    tmp_path,
):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    chain_id = _insert_candidate(
        path,
        discovery_source="helius",
        pair_address="",
        discovered_at_unix_ms=50,
        venue="pump_fun_bonding_curve",
    )
    dex_id = _insert_candidate(
        path,
        discovery_source="dexscreener",
        pair_address="",
        discovered_at_unix_ms=60,
        venue="pump_swap",
    )
    _insert_snapshot(
        path,
        chain_id,
        observed_at_unix_ms=100,
    )
    _insert_snapshot(
        path,
        dex_id,
        observed_at_unix_ms=200,
    )

    store = ObserverMarketStore(path)

    before_dex_ownership = store.resolve_candidate_at(
        "Mint111",
        150,
        preferred_discovery_source="dexscreener",
    )
    after_dex_ownership = store.resolve_candidate_at(
        "Mint111",
        250,
        preferred_discovery_source="dexscreener",
    )

    assert before_dex_ownership.candidate_id == chain_id
    assert after_dex_ownership.candidate_id == dex_id


def test_point_in_time_candidate_resolution_rejects_multiple_preferred_owners(
    tmp_path,
):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    first = _insert_candidate(
        path,
        discovery_source="dexscreener",
        pair_address="",
        discovered_at_unix_ms=50,
        venue="pump_swap",
    )
    second = _insert_candidate(
        path,
        discovery_source="dexscreener",
        pair_address="Pair222",
        discovered_at_unix_ms=60,
        venue="pump_swap",
    )
    _insert_snapshot(path, first, observed_at_unix_ms=100)
    _insert_snapshot(
        path,
        second,
        observed_at_unix_ms=110,
        pair_address="Pair222",
    )

    with pytest.raises(ObserverMarketReadError, match="ambiguous"):
        ObserverMarketStore(path).resolve_candidate_at(
            "Mint111",
            200,
            preferred_discovery_source="dexscreener",
        )


def test_point_in_time_candidate_resolution_prefers_unique_ownerless_source(
    tmp_path,
):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    _insert_candidate(
        path,
        discovery_source="helius",
        pair_address="",
        discovered_at_unix_ms=50,
        venue="pump_fun_bonding_curve",
    )
    dex_id = _insert_candidate(
        path,
        discovery_source="dexscreener",
        pair_address="",
        discovered_at_unix_ms=60,
        venue="pump_swap",
    )

    resolved = ObserverMarketStore(path).resolve_candidate_at(
        "Mint111",
        200,
        preferred_discovery_source="dexscreener",
    )

    assert resolved.candidate_id == dex_id


def test_legacy_e13_schema_remains_supported_for_general_store_reads(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            _CANDIDATE_SCHEMA
            + _MARKET_SCHEMA
                .replace(
                    "    base_mint TEXT NOT NULL DEFAULT 'Mint111',\n",
                    "",
                )
                .replace(
                    "    quote_mint TEXT NOT NULL DEFAULT 'Quote111',\n",
                    "",
                )
                .replace(
                    "    volume_h24_usd REAL,\n",
                    "",
                )
        )
        cursor = connection.execute(
            """INSERT INTO token_candidates (
                   mint, pair_address, discovery_source,
                   discovered_at_unix_ms, venue
               ) VALUES ('Mint111', 'Pair111', 'pump', 1000, 'pump_fun')"""
        )
        candidate_id = int(cursor.lastrowid)
        connection.execute(
            """INSERT INTO market_snapshots (
                   candidate_id, observed_at_unix_ms, source,
                   source_observed_at_unix_ms, venue, pair_address,
                   price_usd, liquidity_usd, volume_m5_usd, volume_h1_usd,
                   buys_m5, sells_m5, buys_h1, sells_h1,
                   pair_created_at_unix_ms
               ) VALUES (
                   ?, 1995000, 'dexscreener', 1995000, 'raydium', 'Pair111',
                   1.0, 5000.0, 1000.0, 5000.0,
                   1, 1, 10, 10, 500000
               )""",
            (candidate_id,),
        )
        connection.commit()
    finally:
        connection.close()

    store = ObserverMarketStore(path)
    candidate = store.resolve_candidate("Mint111")
    assert candidate.candidate_id == candidate_id


def test_exact_market_read_requires_additive_fl9_columns_only_when_called(tmp_path):
    path = tmp_path / "legacy-exact.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            _CANDIDATE_SCHEMA
            + _MARKET_SCHEMA
                .replace(
                    "    base_mint TEXT NOT NULL DEFAULT 'Mint111',\n",
                    "",
                )
                .replace(
                    "    quote_mint TEXT NOT NULL DEFAULT 'Quote111',\n",
                    "",
                )
                .replace(
                    "    volume_h24_usd REAL,\n",
                    "",
                )
        )
        cursor = connection.execute(
            """INSERT INTO token_candidates (
                   mint, pair_address, discovery_source,
                   discovered_at_unix_ms, venue
               ) VALUES ('Mint111', '', 'dexscreener', 100, 'pump_swap')"""
        )
        candidate_id = int(cursor.lastrowid)
        connection.commit()
    finally:
        connection.close()

    store = ObserverMarketStore(path)

    with pytest.raises(
        ObserverMarketReadError,
        match="exact-market columns.*base_mint.*quote_mint.*volume_h24_usd",
    ):
        store.load_current_exact_market(
            candidate_id,
            2_000,
            source="dexscreener",
            venue="pump_swap",
            base_mint="Mint111",
            quote_mint="QuoteSOL",
            max_age_ms=60_000,
        )


def test_point_in_time_candidate_resolution_ignores_future_candidate_discovery(
    tmp_path,
):
    path = tmp_path / "observer.sqlite3"
    _create_database(path)
    chain_id = _insert_candidate(
        path,
        discovery_source="helius",
        pair_address="",
        discovered_at_unix_ms=100,
        venue="pump_fun_bonding_curve",
    )
    _insert_snapshot(
        path,
        chain_id,
        observed_at_unix_ms=120,
    )
    _insert_candidate(
        path,
        discovery_source="dexscreener",
        pair_address="",
        discovered_at_unix_ms=300,
        venue="pump_swap",
    )

    resolved = ObserverMarketStore(path).resolve_candidate_at(
        "Mint111",
        200,
        preferred_discovery_source="dexscreener",
    )

    assert resolved.candidate_id == chain_id
