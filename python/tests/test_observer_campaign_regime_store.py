from __future__ import annotations

import sqlite3

from shreks_brain.observer_campaign.models import ObserverRegimeReadPolicy
from shreks_brain.observer_campaign.store import ObserverCampaignStore
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.safety import SafetyPolicy


QUOTE_ASSET = "So11111111111111111111111111111111111111112"
AS_OF = 1_000_000


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
            venue TEXT
        );
        CREATE TABLE token_mint_states (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            decimals INTEGER NOT NULL,
            mint_authority TEXT,
            freeze_authority TEXT,
            slot TEXT NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL
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
            quoted_at_unix_ms INTEGER NOT NULL
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


def _regime_policy() -> ObserverRegimeReadPolicy:
    return ObserverRegimeReadPolicy(
        version="e15-regime-read-v1",
        window_ms=600_000,
        max_snapshot_age_ms=60_000,
        source_priority=("dexscreener", "meteora"),
        entry_probe_policy_version="probe-v2",
        quote_asset_mint=QUOTE_ASSET,
        entry_input_amount=1_000_000_000,
        taker="Taker111",
        slippage_bps=75,
    )


def _safety_policy() -> SafetyPolicy:
    return SafetyPolicy(
        version="safety-v1",
        min_liquidity_usd=25.0,
        soft_min_liquidity_usd=40.0,
        max_top_holder_concentration_pct=50.0,
        soft_max_top_holder_concentration_pct=40.0,
        soft_max_creator_concentration_pct=40.0,
        soft_max_exit_price_impact_pct=5.0,
        max_critical_data_age_ms=100_000,
    )


def _safety_probe() -> ObserverSafetyProbeIdentity:
    return ObserverSafetyProbeIdentity(
        probe_policy_version="probe-v2",
        output_mint=QUOTE_ASSET,
        input_amount=1_000_000,
        taker="Taker111",
        slippage_bps=75,
    )


def _candidate(connection, candidate_id: int, mint: str, discovered_at: int) -> None:
    connection.execute(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (?, ?, ?, 'pump', ?, 'pump_fun')""",
        (candidate_id, mint, f"Pair{candidate_id}", discovered_at),
    )


def _market(
    connection,
    row_id: int,
    candidate_id: int,
    observed_at: int,
    source: str,
    liquidity: float | None,
    volume_m5: float | None,
) -> None:
    connection.execute(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
            venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
            volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1, pair_created_at_unix_ms)
           VALUES (?, ?, ?, ?, ?, 'pump_fun', ?, 0.25, ?, ?, 100.0, 10, 5, 100, 50, 100)""",
        (
            row_id,
            candidate_id,
            observed_at,
            source,
            observed_at - 1,
            f"Pair{candidate_id}",
            liquidity,
            volume_m5,
        ),
    )


def _safety_evidence(
    connection,
    candidate_id: int,
    mint: str,
    *,
    base_id: int,
    observed_at: int,
    mint_authority: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO token_mint_states
           (id, candidate_id, provider, decimals, mint_authority, freeze_authority, slot, observed_at_unix_ms)
           VALUES (?, ?, 'helius', 6, ?, NULL, ?, ?)""",
        (base_id, candidate_id, mint_authority, str(base_id), observed_at),
    )
    connection.execute(
        """INSERT INTO token_holder_distributions
           (id, candidate_id, provider, mint, last_indexed_slot, observed_at_unix_ms,
            complete, top_holder_concentration_pct)
           VALUES (?, ?, 'helius', ?, ?, ?, 1, 10.0)""",
        (base_id, candidate_id, mint, str(base_id), observed_at + 1),
    )
    connection.execute(
        """INSERT INTO exit_quote_snapshots
           (id, candidate_id, provider, probe_policy_version, input_mint, output_mint,
            taker, input_amount, output_amount, minimum_output_amount, slippage_bps,
            route_available, price_impact_pct, quoted_at_unix_ms)
           VALUES (?, ?, 'jupiter', 'probe-v2', ?, ?, 'Taker111', '1000000',
                   '900000', '890000', 75, 1, '0.2', ?)""",
        (base_id, candidate_id, mint, QUOTE_ASSET, observed_at + 2),
    )


def _entry_quote(
    connection,
    row_id: int,
    candidate_id: int,
    mint: str,
    quoted_at: int,
    *,
    route_available: bool = True,
) -> None:
    output = "500000000" if route_available else "0"
    minimum = "490000000" if route_available else "0"
    impact = "'0.2'" if route_available else "NULL"
    labels = "'[\"Raydium\"]'" if route_available else "'[]'"
    connection.execute(
        f"""INSERT INTO paper_quote_snapshots
            (id, candidate_id, purpose, provider, probe_policy_version, input_mint,
             output_mint, taker, input_amount, output_amount, minimum_output_amount,
             slippage_bps, route_available, price_impact_pct, route_labels_json,
             quoted_at_unix_ms)
            VALUES (?, ?, 'entry', 'jupiter', 'probe-v2', ?, ?, 'Taker111',
                    '1000000000', ?, ?, 75, ?, {impact}, {labels}, ?)""",
        (
            row_id,
            candidate_id,
            QUOTE_ASSET,
            mint,
            output,
            minimum,
            1 if route_available else 0,
            quoted_at,
        ),
    )


def _seed_regime_fixture(path) -> None:
    connection = _create_schema(path)
    for candidate_id, mint, discovered_at in (
        (1, "MintA", 100),
        (2, "MintB", 200),
        (3, "MintC", 300),
        (4, "MintFuture", AS_OF + 1),
        (5, "MintStale", 400),
    ):
        _candidate(connection, candidate_id, mint, discovered_at)

    _market(connection, 1, 1, 950_000, "dexscreener", 50.0, 5.0)
    _market(connection, 2, 1, 990_000, "meteora", 1_000.0, 100.0)
    _market(connection, 3, 1, AS_OF + 100, "dexscreener", 9_999.0, 999.0)
    _market(connection, 4, 2, 970_000, "dexscreener", 100.0, 10.0)
    _market(connection, 5, 3, 980_000, "dexscreener", 150.0, 15.0)
    _market(connection, 6, 4, 990_000, "dexscreener", 200.0, 20.0)
    _market(connection, 7, 5, 900_000, "dexscreener", 250.0, 25.0)

    _safety_evidence(connection, 1, "MintA", base_id=101, observed_at=945_000)
    _safety_evidence(
        connection,
        2,
        "MintB",
        base_id=102,
        observed_at=960_000,
        mint_authority="ActiveAuthority",
    )
    _safety_evidence(connection, 3, "MintC", base_id=103, observed_at=970_000)

    _entry_quote(connection, 201, 1, "MintA", 948_000, route_available=True)
    _entry_quote(connection, 202, 2, "MintB", 963_000, route_available=True)
    _entry_quote(connection, 203, 3, "MintC", 973_000, route_available=False)
    _entry_quote(connection, 204, 1, "MintA", AS_OF + 100, route_available=False)
    connection.commit()
    connection.close()


def test_regime_window_is_point_in_time_source_prioritized_and_b1_gated(tmp_path):
    path = tmp_path / "observer.db"
    _seed_regime_fixture(path)
    store = ObserverCampaignStore(path)

    window = store.build_regime_market_window(
        AS_OF,
        _regime_policy(),
        _safety_policy(),
        _safety_probe(),
        global_risk_halt=False,
    )

    assert window.as_of_unix_ms == AS_OF
    assert window.window_started_at_unix_ms == 400_000
    assert window.candidate_count == 3
    assert window.executable_candidate_count == 1
    assert window.median_liquidity_usd == 100.0
    assert window.median_volume_m5_usd == 10.0
    assert window.source_observed_at_unix_ms == 945_000


def test_regime_medians_remain_unknown_if_any_selected_candidate_is_missing_field(tmp_path):
    path = tmp_path / "observer.db"
    _seed_regime_fixture(path)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE market_snapshots SET liquidity_usd = NULL WHERE id = 4")
    connection.execute("UPDATE market_snapshots SET volume_m5_usd = NULL WHERE id = 5")
    connection.commit()
    connection.close()

    window = ObserverCampaignStore(path).build_regime_market_window(
        AS_OF,
        _regime_policy(),
        _safety_policy(),
        _safety_probe(),
        global_risk_halt=False,
    )
    assert window.candidate_count == 3
    assert window.median_liquidity_usd is None
    assert window.median_volume_m5_usd is None
