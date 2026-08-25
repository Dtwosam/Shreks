from __future__ import annotations

import sqlite3

import pytest

from shreks_brain.observer_campaign.models import (
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.observer_campaign.store import (
    ObserverCampaignReadError,
    ObserverCampaignStore,
)


QUOTE_ASSET = "So11111111111111111111111111111111111111112"


def _identity(**changes) -> ObserverPaperQuoteIdentity:
    values = {
        "candidate_id": 7,
        "purpose": ObserverPaperQuotePurpose.ENTRY,
        "provider": "jupiter",
        "probe_policy_version": "probe-v2",
        "input_mint": QUOTE_ASSET,
        "output_mint": "Mint111",
        "taker": "Taker111",
        "input_amount": 1_000_000_000,
        "slippage_bps": 75,
    }
    values.update(changes)
    return ObserverPaperQuoteIdentity(**values)


def _create_schema(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE token_candidates (
            id INTEGER PRIMARY KEY,
            mint TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            discovery_source TEXT NOT NULL,
            discovered_at_unix_ms INTEGER NOT NULL,
            venue TEXT,
            future_candidate_column TEXT
        );
        CREATE TABLE token_mint_states (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            decimals INTEGER NOT NULL,
            mint_authority TEXT,
            freeze_authority TEXT,
            slot TEXT NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL,
            future_mint_column TEXT
        );
        CREATE TABLE paper_quote_snapshots (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            provider TEXT NOT NULL,
            probe_policy_version TEXT NOT NULL,
            input_mint TEXT NOT NULL,
            output_mint TEXT NOT NULL,
            taker TEXT NOT NULL,
            input_amount TEXT NOT NULL,
            output_amount TEXT NOT NULL,
            minimum_output_amount TEXT NOT NULL,
            slippage_bps INTEGER NOT NULL,
            route_available INTEGER NOT NULL,
            price_impact_pct TEXT,
            route_labels_json TEXT NOT NULL,
            quoted_at_unix_ms INTEGER NOT NULL,
            future_quote_column TEXT
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
        CREATE TABLE token_holder_distributions (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            mint TEXT NOT NULL,
            last_indexed_slot TEXT NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL,
            complete INTEGER NOT NULL,
            top_holder_concentration_pct REAL
        );
        CREATE TABLE exit_quote_snapshots (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            probe_policy_version TEXT NOT NULL,
            input_mint TEXT NOT NULL,
            output_mint TEXT NOT NULL,
            taker TEXT NOT NULL,
            input_amount TEXT NOT NULL,
            output_amount TEXT NOT NULL,
            minimum_output_amount TEXT NOT NULL,
            slippage_bps INTEGER NOT NULL,
            route_available INTEGER NOT NULL,
            price_impact_pct TEXT,
            quoted_at_unix_ms INTEGER NOT NULL
        );
        """
    )
    return connection


def _seed_candidate(connection: sqlite3.Connection) -> None:
    connection.execute(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (7, 'Mint111', 'Pair111', 'pump', 100, 'pump_fun')"""
    )


def _insert_quote(
    connection: sqlite3.Connection,
    *,
    row_id: int,
    quoted_at: int,
    purpose: str = "entry",
    input_amount: str = "1000000000",
    output_amount: str = "18446744073709551615",
) -> None:
    connection.execute(
        """INSERT INTO paper_quote_snapshots (
               id, candidate_id, purpose, provider, probe_policy_version,
               input_mint, output_mint, taker, input_amount, output_amount,
               minimum_output_amount, slippage_bps, route_available,
               price_impact_pct, route_labels_json, quoted_at_unix_ms
           ) VALUES (?, 7, ?, 'jupiter', 'probe-v2', ?, 'Mint111', 'Taker111', ?, ?,
                     '490000000', 75, 1, '0.25', '[\"Raydium\",\"Meteora\"]', ?)""",
        (row_id, purpose, QUOTE_ASSET, input_amount, output_amount, quoted_at),
    )


def test_missing_database_is_not_created_and_required_schema_fails_closed(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(ObserverCampaignReadError):
        ObserverCampaignStore(missing)
    assert not missing.exists()

    partial = tmp_path / "partial.db"
    connection = sqlite3.connect(partial)
    connection.execute("CREATE TABLE token_candidates (id INTEGER PRIMARY KEY, mint TEXT)")
    connection.close()
    with pytest.raises(ObserverCampaignReadError, match="missing required"):
        ObserverCampaignStore(partial)


def test_additive_future_columns_are_allowed_and_latest_reads_never_cross_as_of(tmp_path):
    path = tmp_path / "observer.db"
    connection = _create_schema(path)
    _seed_candidate(connection)
    connection.execute(
        """INSERT INTO token_mint_states
           (id, candidate_id, provider, decimals, mint_authority, freeze_authority, slot, observed_at_unix_ms)
           VALUES (1, 7, 'helius', 6, NULL, NULL, '10', 900)"""
    )
    connection.execute(
        """INSERT INTO token_mint_states
           (id, candidate_id, provider, decimals, mint_authority, freeze_authority, slot, observed_at_unix_ms)
           VALUES (2, 7, 'helius', 8, NULL, NULL, '11', 1100)"""
    )
    _insert_quote(connection, row_id=1, quoted_at=950)
    _insert_quote(connection, row_id=2, quoted_at=1050, output_amount="500000001")
    connection.commit()
    connection.close()

    store = ObserverCampaignStore(path)
    assert store.latest_token_decimals(7, "Mint111", 1_000) == 6
    evidence = store.latest_paper_quote(_identity(), 1_000)
    assert evidence is not None
    assert evidence.quoted_at_unix_ms == 950
    assert evidence.output_amount == 2**64 - 1
    assert evidence.route_labels == ("Raydium", "Meteora")


def test_paper_quote_lookup_requires_exact_purpose_and_request_attribution(tmp_path):
    path = tmp_path / "observer.db"
    connection = _create_schema(path)
    _seed_candidate(connection)
    _insert_quote(connection, row_id=1, quoted_at=950)
    connection.commit()
    connection.close()

    store = ObserverCampaignStore(path)
    assert store.latest_paper_quote(_identity(), 1_000) is not None
    assert (
        store.latest_paper_quote(
            _identity(
                purpose=ObserverPaperQuotePurpose.EXIT,
                input_mint="Mint111",
                output_mint=QUOTE_ASSET,
            ),
            1_000,
        )
        is None
    )
    assert store.latest_paper_quote(_identity(input_amount=999_999_999), 1_000) is None
    assert (
        store.latest_paper_quote(
            _identity(probe_policy_version="other-probe"),
            1_000,
        )
        is None
    )


def test_candidate_mint_misattribution_and_noncanonical_quote_rows_fail_closed(tmp_path):
    path = tmp_path / "observer.db"
    connection = _create_schema(path)
    _seed_candidate(connection)
    _insert_quote(connection, row_id=1, quoted_at=950)
    connection.commit()
    connection.close()

    store = ObserverCampaignStore(path)
    with pytest.raises(ObserverCampaignReadError, match="candidate"):
        store.latest_token_decimals(7, "OtherMint", 1_000)

    wrong = _identity(output_mint="OtherMint")
    with pytest.raises(ObserverCampaignReadError, match="candidate"):
        store.latest_paper_quote(wrong, 1_000)

    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE paper_quote_snapshots SET route_labels_json = '[\"Raydium\", \"Meteora\"]' WHERE id = 1"
    )
    connection.commit()
    connection.close()
    with pytest.raises(ObserverCampaignReadError, match="canonical"):
        store.latest_paper_quote(_identity(), 1_000)
