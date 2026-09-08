from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from shreks_brain.fl9_tradable_universe import (
    FL9_TRADABLE_UNIVERSE_POLICY_VERSION,
    Fl9TradableUniversePolicy,
    Fl9TradableUniverseStore,
    fl9_tradable_universe_policy_fingerprint_sha256,
)


_SCHEMA = """
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

CREATE TABLE pump_migration_signals (
    signature TEXT PRIMARY KEY,
    status TEXT NOT NULL
);

CREATE TABLE token_lifecycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_venue TEXT NOT NULL,
    to_venue TEXT NOT NULL,
    mint TEXT NOT NULL,
    quote_mint TEXT NOT NULL,
    pool_address TEXT NOT NULL,
    detected_at_unix_ms INTEGER NOT NULL
);
"""


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_SCHEMA)
        connection.commit()
    finally:
        connection.close()


def _candidate(
    path: Path,
    *,
    source: str = "dexscreener",
    mint: str = "Mint111",
    venue: str = "pump_swap",
) -> int:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            """INSERT INTO token_candidates (
                   mint,
                   pair_address,
                   discovery_source,
                   discovered_at_unix_ms,
                   venue
               ) VALUES (?, '', ?, 100, ?)""",
            (mint, source, venue),
        )
        connection.commit()
        return int(row.lastrowid)
    finally:
        connection.close()


def _migration(
    path: Path,
    *,
    detected_at: int = 1_000,
    pool: str = "Pool111",
    signature: str = "Sig111",
    status: str = "verified",
    mint: str = "Mint111",
    quote_mint: str = "QuoteSOL",
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO pump_migration_signals (signature, status) VALUES (?, ?)",
            (signature, status),
        )
        connection.execute(
            """INSERT INTO token_lifecycle_events (
                   signature,
                   event_type,
                   from_venue,
                   to_venue,
                   mint,
                   quote_mint,
                   pool_address,
                   detected_at_unix_ms
               ) VALUES (
                   ?,
                   'pump_graduation',
                   'pump_fun_bonding_curve',
                   'pump_swap',
                   ?,
                   ?,
                   ?,
                   ?
               )""",
            (
                signature,
                mint,
                quote_mint,
                pool,
                detected_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _snapshot(
    path: Path,
    candidate_id: int,
    *,
    observed_at: int = 1_950,
    source: str = "dexscreener",
    venue: str = "pump_swap",
    mint: str = "Mint111",
    quote_mint: str = "QuoteSOL",
    pair: str = "PumpPair",
    liquidity: float | None = 8_000.0,
    volume_h24: float | None = 25_000.0,
) -> int:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            """INSERT INTO market_snapshots (
                   candidate_id,
                   observed_at_unix_ms,
                   source,
                   source_observed_at_unix_ms,
                   venue,
                   pair_address,
                   base_mint,
                   quote_mint,
                   price_usd,
                   liquidity_usd,
                   volume_h24_usd,
                   pair_created_at_unix_ms
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, 500)""",
            (
                candidate_id,
                observed_at,
                source,
                observed_at,
                venue,
                pair,
                mint,
                quote_mint,
                liquidity,
                volume_h24,
            ),
        )
        connection.commit()
        return int(row.lastrowid)
    finally:
        connection.close()


def _assess(path: Path, **changes):
    values = dict(
        mint="Mint111",
        quote_mint="QuoteSOL",
        decision_venue="pump_swap",
        decision_observed_at_unix_ms=2_000,
        policy=Fl9TradableUniversePolicy(),
    )
    values.update(changes)
    return Fl9TradableUniverseStore(path).assess(**values)


def test_v1_policy_is_frozen_and_fingerprinted():
    policy = Fl9TradableUniversePolicy()

    assert policy.version == FL9_TRADABLE_UNIVERSE_POLICY_VERSION
    assert policy.maximum_snapshot_age_ms == 60_000
    assert policy.minimum_liquidity_usd == 3_000.0
    assert policy.minimum_volume_h24_usd == 1_000.0
    assert len(fl9_tradable_universe_policy_fingerprint_sha256(policy)) == 64

    with pytest.raises(ValueError, match="immutable|new policy"):
        replace(policy, minimum_liquidity_usd=2_999.0)


def test_exact_verified_fresh_liquid_pumpswap_market_is_eligible(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _database(path)
    _migration(path)
    candidate_id = _candidate(path)
    snapshot_id = _snapshot(path, candidate_id)

    assessment = _assess(path)

    assert assessment.eligible is True
    assert assessment.reason == "eligible"
    assert assessment.graduation_detected_at_unix_ms == 1_000
    assert assessment.candidate_id == candidate_id
    assert assessment.snapshot_row_id == snapshot_id
    assert assessment.snapshot_age_ms == 50
    assert assessment.selected_pair_address == "PumpPair"
    assert assessment.liquidity_usd == 8_000.0
    assert assessment.volume_h24_usd == 25_000.0


def test_bonding_curve_decision_is_rejected_before_market_reads(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _database(path)
    _migration(path)
    candidate_id = _candidate(path)
    _snapshot(path, candidate_id)

    assessment = _assess(
        path,
        decision_venue="pump_fun_bonding_curve",
    )

    assert assessment.eligible is False
    assert assessment.reason == "wrong_decision_venue"
    assert assessment.candidate_id is None
    assert assessment.snapshot_row_id is None


def test_migration_must_be_verified_and_known_by_decision_time(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _database(path)
    _migration(path, detected_at=2_001)
    candidate_id = _candidate(path)
    _snapshot(path, candidate_id)

    assessment = _assess(path)

    assert assessment.eligible is False
    assert assessment.reason == "missing_verified_migration"


def test_contradictory_verified_migration_pools_fail_closed(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _database(path)
    _migration(path, pool="PoolA", signature="SigA")
    _migration(path, pool="PoolB", signature="SigB")
    candidate_id = _candidate(path)
    _snapshot(path, candidate_id)

    assessment = _assess(path)

    assert assessment.eligible is False
    assert assessment.reason == "contradictory_verified_migration"


def test_exact_market_read_cannot_be_rescued_by_wrong_quote_or_stale_row(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _database(path)
    _migration(path)
    candidate_id = _candidate(path)
    _snapshot(
        path,
        candidate_id,
        observed_at=2_000,
        quote_mint="WrongQuote",
        liquidity=99_000.0,
        volume_h24=99_000.0,
    )
    _snapshot(
        path,
        candidate_id,
        observed_at=0,
        quote_mint="QuoteSOL",
        liquidity=99_000.0,
        volume_h24=99_000.0,
    )

    assessment = _assess(
        path,
        decision_observed_at_unix_ms=70_001,
    )

    assert assessment.eligible is False
    assert assessment.reason == "missing_fresh_exact_market_snapshot"


@pytest.mark.parametrize(
    ("liquidity", "volume_h24", "reason"),
    (
        (None, 25_000.0, "missing_liquidity_usd"),
        (8_000.0, None, "missing_volume_h24_usd"),
        (2_999.99, 25_000.0, "below_minimum_liquidity_usd"),
        (8_000.0, 999.99, "below_minimum_volume_h24_usd"),
    ),
)
def test_market_quality_thresholds_fail_closed(
    tmp_path,
    liquidity,
    volume_h24,
    reason,
):
    path = tmp_path / "observer.sqlite3"
    _database(path)
    _migration(path)
    candidate_id = _candidate(path)
    _snapshot(
        path,
        candidate_id,
        liquidity=liquidity,
        volume_h24=volume_h24,
    )

    assessment = _assess(path)

    assert assessment.eligible is False
    assert assessment.reason == reason


def test_assessment_is_read_only(tmp_path):
    path = tmp_path / "observer.sqlite3"
    _database(path)
    _migration(path)
    candidate_id = _candidate(path)
    _snapshot(path, candidate_id)

    connection = sqlite3.connect(path)
    try:
        before = tuple(
            connection.execute(
                "SELECT COUNT(*) FROM " + table
            ).fetchone()[0]
            for table in (
                "token_candidates",
                "market_snapshots",
                "pump_migration_signals",
                "token_lifecycle_events",
            )
        )
    finally:
        connection.close()

    _assess(path)

    connection = sqlite3.connect(path)
    try:
        after = tuple(
            connection.execute(
                "SELECT COUNT(*) FROM " + table
            ).fetchone()[0]
            for table in (
                "token_candidates",
                "market_snapshots",
                "pump_migration_signals",
                "token_lifecycle_events",
            )
        )
    finally:
        connection.close()

    assert after == before


def test_source_has_no_network_target_model_or_execution_authority():
    source = Path(__file__).resolve().parents[1] / "src" / "shreks_brain" / (
        "fl9_tradable_universe.py"
    )
    text = source.read_text(encoding="utf-8")

    for forbidden in (
        "requests.",
        "httpx",
        "future_return",
        "target_value",
        "model_performance",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
    ):
        assert forbidden not in text
