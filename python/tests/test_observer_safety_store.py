from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shreks_brain.observer_safety.models import ObserverSafetyProbeIdentity
from shreks_brain.observer_safety.store import (
    ObserverSafetyEvidenceStore,
    ObserverSafetyReadError,
)


_SCHEMA = """
CREATE TABLE token_candidates (
    id INTEGER PRIMARY KEY,
    mint TEXT NOT NULL,
    future_candidate_field TEXT
);
CREATE TABLE token_mint_states (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    owner_program TEXT NOT NULL,
    supply TEXT NOT NULL,
    decimals INTEGER NOT NULL,
    mint_authority TEXT,
    freeze_authority TEXT,
    slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    future_mint_field TEXT
);
CREATE TABLE token_holder_distributions (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    mint TEXT NOT NULL,
    last_indexed_slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    reported_total_accounts TEXT NOT NULL,
    accounts_scanned INTEGER NOT NULL,
    unique_owners INTEGER NOT NULL,
    pages_scanned INTEGER NOT NULL,
    complete INTEGER NOT NULL,
    total_balance_raw TEXT NOT NULL,
    largest_owner TEXT,
    largest_owner_balance_raw TEXT,
    top_holder_concentration_pct REAL,
    future_holder_field TEXT
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
    route_labels_json TEXT NOT NULL,
    quoted_at_unix_ms INTEGER NOT NULL,
    future_quote_field TEXT
);
"""


def _create_database(path: Path, schema: str = _SCHEMA) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(schema)
        connection.commit()
    finally:
        connection.close()


def _insert_candidate(path: Path, candidate_id: int = 7, mint: str = "Mint111") -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO token_candidates (id, mint) VALUES (?, ?)",
            (candidate_id, mint),
        )
        connection.commit()
    finally:
        connection.close()


def _probe() -> ObserverSafetyProbeIdentity:
    return ObserverSafetyProbeIdentity(
        probe_policy_version="probe-v1",
        output_mint="So11111111111111111111111111111111111111112",
        input_amount=1_000,
        taker="Taker111",
        slippage_bps=75,
    )


def test_missing_database_fails_without_creating_file(tmp_path):
    path = tmp_path / "missing.sqlite3"

    with pytest.raises(ObserverSafetyReadError, match="open"):
        ObserverSafetyEvidenceStore(path)

    assert not path.exists()


def test_missing_required_table_or_column_fails_closed(tmp_path):
    missing_table = tmp_path / "missing-table.sqlite3"
    _create_database(
        missing_table,
        _SCHEMA.replace(
            _SCHEMA[_SCHEMA.index("CREATE TABLE exit_quote_snapshots"):], ""
        ),
    )
    with pytest.raises(ObserverSafetyReadError, match="exit_quote_snapshots"):
        ObserverSafetyEvidenceStore(missing_table)

    missing_column = tmp_path / "missing-column.sqlite3"
    _create_database(
        missing_column,
        _SCHEMA.replace("    top_holder_concentration_pct REAL,\n", ""),
    )
    with pytest.raises(ObserverSafetyReadError, match="top_holder_concentration_pct"):
        ObserverSafetyEvidenceStore(missing_column)


def test_additive_future_columns_are_allowed(tmp_path):
    path = tmp_path / "future.sqlite3"
    _create_database(path)

    assert isinstance(ObserverSafetyEvidenceStore(path), ObserverSafetyEvidenceStore)


def test_latest_mint_state_is_exact_candidate_helius_and_point_in_time(tmp_path):
    path = tmp_path / "mint.sqlite3"
    _create_database(path)
    _insert_candidate(path)
    connection = sqlite3.connect(path)
    try:
        connection.executemany(
            """INSERT INTO token_mint_states (
                   id, candidate_id, provider, owner_program, supply, decimals,
                   mint_authority, freeze_authority, slot, observed_at_unix_ms
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (1, 7, "helius", "Token", "1000", 6, None, None, "10", 1_000),
                (2, 7, "other", "Token", "1000", 6, "Wrong", None, "11", 1_200),
                (3, 7, "helius", "Token", "1000", 6, "Future", None, "12", 2_000),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    store = ObserverSafetyEvidenceStore(path)
    row = store.latest_mint_state(7, "Mint111", 1_500)

    assert row is not None
    assert row.provider == "helius"
    assert row.mint == "Mint111"
    assert row.mint_authority is None
    assert row.freeze_authority is None
    assert row.slot == 10
    assert row.observed_at_unix_ms == 1_000


def test_candidate_id_and_mint_attribution_must_match(tmp_path):
    path = tmp_path / "candidate.sqlite3"
    _create_database(path)
    _insert_candidate(path, candidate_id=7, mint="Mint111")
    store = ObserverSafetyEvidenceStore(path)

    with pytest.raises(ObserverSafetyReadError, match="candidate"):
        store.latest_mint_state(7, "OtherMint", 1_500)


def test_holder_selection_never_looks_ahead_and_incomplete_hides_concentration(tmp_path):
    path = tmp_path / "holder.sqlite3"
    _create_database(path)
    _insert_candidate(path)
    connection = sqlite3.connect(path)
    try:
        connection.executemany(
            """INSERT INTO token_holder_distributions (
                   id, candidate_id, provider, mint, last_indexed_slot,
                   observed_at_unix_ms, reported_total_accounts, accounts_scanned,
                   unique_owners, pages_scanned, complete, total_balance_raw,
                   largest_owner, largest_owner_balance_raw, top_holder_concentration_pct
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (1, 7, "helius", "Mint111", "10", 1_000, "2", 2, 2, 1, 1, "1000", "Owner", "600", 60.0),
                (2, 7, "helius", "Mint111", "11", 1_200, "3", 2, 2, 1, 0, "900", "Owner", "500", 88.0),
                (3, 7, "helius", "Mint111", "12", 2_000, "2", 2, 2, 1, 1, "1000", "Owner", "700", 70.0),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    store = ObserverSafetyEvidenceStore(path)
    row = store.latest_holder_distribution(7, "Mint111", 1_500)

    assert row is not None
    assert row.observed_at_unix_ms == 1_200
    assert row.complete is False
    assert row.top_holder_concentration_pct is None


def test_quote_lookup_requires_exact_probe_identity_and_never_looks_ahead(tmp_path):
    path = tmp_path / "quote.sqlite3"
    _create_database(path)
    _insert_candidate(path)
    connection = sqlite3.connect(path)
    try:
        connection.executemany(
            """INSERT INTO exit_quote_snapshots (
                   id, candidate_id, provider, probe_policy_version, input_mint,
                   output_mint, taker, input_amount, output_amount,
                   minimum_output_amount, slippage_bps, route_available,
                   price_impact_pct, route_labels_json, quoted_at_unix_ms
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (1, 7, "jupiter", "probe-v1", "Mint111", "So11111111111111111111111111111111111111112", "Taker111", "1000", "900", "850", 75, 1, "0.25", "[]", 1_100),
                (2, 7, "jupiter", "probe-v1", "Mint111", "So11111111111111111111111111111111111111112", "WrongTaker", "1000", "999", "900", 75, 1, "0.01", "[]", 1_300),
                (3, 7, "jupiter", "probe-v1", "Mint111", "So11111111111111111111111111111111111111112", "Taker111", "1000", "950", "900", 75, 1, "0.10", "[]", 2_000),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    store = ObserverSafetyEvidenceStore(path)
    row = store.latest_exit_quote(7, "Mint111", _probe(), 1_500)

    assert row is not None
    assert row.quoted_at_unix_ms == 1_100
    assert row.taker == "Taker111"
    assert row.output_amount == 900
    assert row.price_impact_pct == "0.25"

    missing_identity = ObserverSafetyProbeIdentity(
        probe_policy_version="probe-v2",
        output_mint=_probe().output_mint,
        input_amount=1_000,
        taker="Taker111",
        slippage_bps=75,
    )
    assert store.latest_exit_quote(7, "Mint111", missing_identity, 1_500) is None
