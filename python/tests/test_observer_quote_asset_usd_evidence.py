from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from shreks_brain.observer_market.store import (
    ObserverMarketReadError,
    ObserverMarketStore,
)


AS_OF = 2_000_000
TOKEN = "Token111"
WSOL = "So11111111111111111111111111111111111111112"


def _database(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE token_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mint TEXT NOT NULL,
                pair_address TEXT NOT NULL DEFAULT '',
                discovery_source TEXT NOT NULL,
                discovered_at_unix_ms INTEGER NOT NULL,
                venue TEXT
            );
            CREATE TABLE market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                observed_at_unix_ms INTEGER NOT NULL,
                source TEXT NOT NULL,
                source_observed_at_unix_ms INTEGER,
                venue TEXT NOT NULL DEFAULT 'other_solana',
                pair_address TEXT NOT NULL DEFAULT '',
                base_mint TEXT NOT NULL,
                quote_mint TEXT NOT NULL,
                price_native TEXT,
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
        )
        cursor = connection.execute(
            """INSERT INTO token_candidates (
                   mint, pair_address, discovery_source,
                   discovered_at_unix_ms, venue
               ) VALUES (?, ?, 'pump', 1000, 'pump_swap')""",
            (TOKEN, "Pair111"),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def _snapshot(
    path: Path,
    candidate_id: int,
    *,
    observed_at_unix_ms: int = AS_OF - 1_000,
    quote_mint: str = WSOL,
    venue: str = "pump_swap",
    price_native: str | None = "0.002",
    price_usd: object = 0.33,
) -> int:
    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute(
            """INSERT INTO market_snapshots (
                   candidate_id, observed_at_unix_ms, source,
                   source_observed_at_unix_ms, venue, pair_address,
                   base_mint, quote_mint, price_native, price_usd,
                   liquidity_usd, volume_h24_usd
               ) VALUES (?, ?, 'dexscreener', ?, ?, 'Pair111',
                         ?, ?, ?, ?, 10000.0, 50000.0)""",
            (
                candidate_id,
                observed_at_unix_ms,
                observed_at_unix_ms,
                venue,
                TOKEN,
                quote_mint,
                price_native,
                price_usd,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def test_exact_market_preserves_native_quote_price_text(tmp_path: Path) -> None:
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    row_id = _snapshot(path, candidate_id)

    snapshot = ObserverMarketStore(path).load_current_exact_market(
        candidate_id,
        AS_OF,
        source="dexscreener",
        venue="pump_swap",
        base_mint=TOKEN,
        quote_mint=WSOL,
        max_age_ms=60_000,
    )

    assert snapshot.row_id == row_id
    assert snapshot.price_native == "0.002"
    assert snapshot.price_usd == 0.33


def test_quote_asset_usd_evidence_derives_rate_from_same_exact_market(
    tmp_path: Path,
) -> None:
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    row_id = _snapshot(path, candidate_id)

    evidence = ObserverMarketStore(path).quote_asset_usd_evidence(
        candidate_id,
        AS_OF,
        source="dexscreener",
        venue="pump_swap",
        base_mint=TOKEN,
        quote_mint=WSOL,
        max_age_ms=60_000,
    )

    assert type(evidence).__name__ == "ObserverQuoteAssetUsdEvidence"
    assert evidence.market_row_id == row_id
    assert evidence.candidate_id == candidate_id
    assert evidence.source == "dexscreener"
    assert evidence.venue == "pump_swap"
    assert evidence.pair_address == "Pair111"
    assert evidence.base_mint == TOKEN
    assert evidence.quote_mint == WSOL
    assert evidence.observed_at_unix_ms == AS_OF - 1_000
    assert evidence.base_price_quote == "0.002"
    assert evidence.base_price_usd == 0.33
    assert math.isclose(
        evidence.quote_asset_usd_per_token,
        165.0,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


@pytest.mark.parametrize(
    ("price_native", "price_usd"),
    (
        (None, 0.33),
        ("0", 0.33),
        ("-0.002", 0.33),
        ("not-a-number", 0.33),
        ("0.002", None),
        ("0.002", 0.0),
    ),
)
def test_quote_asset_usd_evidence_fails_closed_without_positive_price_pair(
    tmp_path: Path,
    price_native: str | None,
    price_usd: object,
) -> None:
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    _snapshot(
        path,
        candidate_id,
        price_native=price_native,
        price_usd=price_usd,
    )

    with pytest.raises(
        ObserverMarketReadError,
        match="native|USD|price|quote asset",
    ):
        ObserverMarketStore(path).quote_asset_usd_evidence(
            candidate_id,
            AS_OF,
            source="dexscreener",
            venue="pump_swap",
            base_mint=TOKEN,
            quote_mint=WSOL,
            max_age_ms=60_000,
        )


def test_quote_asset_usd_evidence_keeps_exact_market_identity_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    _snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=AS_OF - 500,
        quote_mint="WrongQuote",
    )
    _snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=AS_OF - 400,
        quote_mint=WSOL,
        venue="raydium",
    )

    with pytest.raises(ObserverMarketReadError, match="fresh exact"):
        ObserverMarketStore(path).quote_asset_usd_evidence(
            candidate_id,
            AS_OF,
            source="dexscreener",
            venue="pump_swap",
            base_mint=TOKEN,
            quote_mint=WSOL,
            max_age_ms=60_000,
        )


def test_quote_asset_usd_evidence_can_be_bound_to_exact_cycle_market_row(
    tmp_path: Path,
) -> None:
    path = tmp_path / "observer.sqlite3"
    candidate_id = _database(path)
    older_row_id = _snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=AS_OF - 1_000,
    )
    current_row_id = _snapshot(
        path,
        candidate_id,
        observed_at_unix_ms=AS_OF - 500,
    )

    store = ObserverMarketStore(path)
    evidence = store.quote_asset_usd_evidence(
        candidate_id,
        AS_OF,
        source="dexscreener",
        venue="pump_swap",
        base_mint=TOKEN,
        quote_mint=WSOL,
        max_age_ms=60_000,
        expected_market_row_id=current_row_id,
    )
    assert evidence.market_row_id == current_row_id

    with pytest.raises(ObserverMarketReadError, match="row|market"):
        store.quote_asset_usd_evidence(
            candidate_id,
            AS_OF,
            source="dexscreener",
            venue="pump_swap",
            base_mint=TOKEN,
            quote_mint=WSOL,
            max_age_ms=60_000,
            expected_market_row_id=older_row_id,
        )
