from __future__ import annotations

import sqlite3

from shreks_brain.observer_campaign.models import ObserverRegimeReadPolicy
from shreks_brain.observer_campaign.store import ObserverCampaignStore
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.safety import SafetyPolicy


AS_OF = 1_000_000
QUOTE_ASSET = "So11111111111111111111111111111111111111112"


def test_regime_window_does_not_consume_auxiliary_evidence_from_before_window(tmp_path):
    path = tmp_path / "observer.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE token_candidates (
            id INTEGER PRIMARY KEY, mint TEXT NOT NULL, pair_address TEXT NOT NULL,
            discovery_source TEXT NOT NULL, discovered_at_unix_ms INTEGER NOT NULL,
            venue TEXT
        );
        CREATE TABLE token_mint_states (
            id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, provider TEXT NOT NULL,
            decimals INTEGER NOT NULL, mint_authority TEXT, freeze_authority TEXT,
            slot TEXT NOT NULL, observed_at_unix_ms INTEGER NOT NULL
        );
        CREATE TABLE paper_quote_snapshots (
            id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, purpose TEXT NOT NULL,
            provider TEXT NOT NULL, probe_policy_version TEXT NOT NULL,
            input_mint TEXT NOT NULL, output_mint TEXT NOT NULL, taker TEXT NOT NULL,
            input_amount TEXT NOT NULL, output_amount TEXT NOT NULL,
            minimum_output_amount TEXT NOT NULL, slippage_bps INTEGER NOT NULL,
            route_available INTEGER NOT NULL, price_impact_pct TEXT,
            route_labels_json TEXT NOT NULL, quoted_at_unix_ms INTEGER NOT NULL
        );
        CREATE TABLE market_snapshots (
            id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL, source TEXT NOT NULL,
            source_observed_at_unix_ms INTEGER, venue TEXT NOT NULL,
            pair_address TEXT NOT NULL, price_usd REAL, liquidity_usd REAL,
            volume_m5_usd REAL, volume_h1_usd REAL, buys_m5 INTEGER,
            sells_m5 INTEGER, buys_h1 INTEGER, sells_h1 INTEGER,
            pair_created_at_unix_ms INTEGER
        );
        CREATE TABLE token_holder_distributions (
            id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, provider TEXT NOT NULL,
            mint TEXT NOT NULL, last_indexed_slot TEXT NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL, complete INTEGER NOT NULL,
            top_holder_concentration_pct REAL
        );
        CREATE TABLE exit_quote_snapshots (
            id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, provider TEXT NOT NULL,
            probe_policy_version TEXT NOT NULL, input_mint TEXT NOT NULL,
            output_mint TEXT NOT NULL, taker TEXT NOT NULL, input_amount TEXT NOT NULL,
            output_amount TEXT NOT NULL, minimum_output_amount TEXT NOT NULL,
            slippage_bps INTEGER NOT NULL, route_available INTEGER NOT NULL,
            price_impact_pct TEXT, quoted_at_unix_ms INTEGER NOT NULL
        );

        INSERT INTO token_candidates
            (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
        VALUES (1, 'MintA', 'Pair1', 'pump', 100, 'pump_fun');

        INSERT INTO market_snapshots
            (id, candidate_id, observed_at_unix_ms, source,
             source_observed_at_unix_ms, venue, pair_address, price_usd,
             liquidity_usd, volume_m5_usd, volume_h1_usd, buys_m5, sells_m5,
             buys_h1, sells_h1, pair_created_at_unix_ms)
        VALUES
            (1, 1, 950000, 'dexscreener', 949999, 'pump_fun', 'Pair1', 0.25,
             50000.0, 10000.0, 100000.0, 20, 10, 200, 100, 100);

        INSERT INTO token_mint_states
            (id, candidate_id, provider, decimals, mint_authority, freeze_authority,
             slot, observed_at_unix_ms)
        VALUES (1, 1, 'helius', 6, NULL, NULL, '1', 300000);

        INSERT INTO token_holder_distributions
            (id, candidate_id, provider, mint, last_indexed_slot,
             observed_at_unix_ms, complete, top_holder_concentration_pct)
        VALUES (1, 1, 'helius', 'MintA', '1', 300001, 1, 10.0);

        INSERT INTO exit_quote_snapshots
            (id, candidate_id, provider, probe_policy_version, input_mint,
             output_mint, taker, input_amount, output_amount,
             minimum_output_amount, slippage_bps, route_available,
             price_impact_pct, quoted_at_unix_ms)
        VALUES
            (1, 1, 'jupiter', 'probe-v2', 'MintA',
             'So11111111111111111111111111111111111111112', 'Taker111',
             '1000000', '900000', '890000', 75, 1, '0.2', 300002);

        INSERT INTO paper_quote_snapshots
            (id, candidate_id, purpose, provider, probe_policy_version,
             input_mint, output_mint, taker, input_amount, output_amount,
             minimum_output_amount, slippage_bps, route_available,
             price_impact_pct, route_labels_json, quoted_at_unix_ms)
        VALUES
            (1, 1, 'entry', 'jupiter', 'probe-v2',
             'So11111111111111111111111111111111111111112', 'MintA', 'Taker111',
             '1000000000', '500000000', '490000000', 75, 1, '0.2',
             '["Raydium"]', 300003);
        """
    )
    connection.commit()
    connection.close()

    window = ObserverCampaignStore(path).build_regime_market_window(
        AS_OF,
        ObserverRegimeReadPolicy(
            version="e15-regime-read-v1",
            window_ms=600_000,
            max_snapshot_age_ms=60_000,
            source_priority=("dexscreener", "meteora"),
            entry_probe_policy_version="probe-v2",
            quote_asset_mint=QUOTE_ASSET,
            entry_input_amount=1_000_000_000,
            taker="Taker111",
            slippage_bps=75,
        ),
        SafetyPolicy(
            version="safety-v1",
            min_liquidity_usd=25.0,
            soft_min_liquidity_usd=40.0,
            max_top_holder_concentration_pct=50.0,
            soft_max_top_holder_concentration_pct=40.0,
            soft_max_creator_concentration_pct=40.0,
            soft_max_exit_price_impact_pct=5.0,
            max_critical_data_age_ms=100_000,
        ),
        ObserverSafetyProbeIdentity(
            probe_policy_version="probe-v2",
            output_mint=QUOTE_ASSET,
            input_amount=1_000_000,
            taker="Taker111",
            slippage_bps=75,
        ),
        global_risk_halt=False,
    )

    assert window.window_started_at_unix_ms == 400_000
    assert window.candidate_count == 1
    assert window.executable_candidate_count == 0
    assert window.source_observed_at_unix_ms == 950_000
