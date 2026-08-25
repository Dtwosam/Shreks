from __future__ import annotations

from dataclasses import replace
import sqlite3

from shreks_brain.observer_campaign.coordinator import (
    OBSERVER_PAPER_CAMPAIGN_CYCLE_AUDIT_SCHEMA_VERSION,
    ObserverPaperCampaignSelectionPolicy,
    assemble_observer_paper_campaign_cycle,
)
from shreks_brain.scoring import score_candidate
from shreks_brain.setups import assess_fresh_launch

from test_observer_campaign_runner import (
    AS_OF,
    MINT,
    QUOTE_ASSET,
    TAKER,
    _bundle,
    _environment,
    _seed,
    _state,
)


SECOND_MINT = "MintRunner222"


def _seed_two_candidates(path) -> None:
    _seed(path)
    connection = sqlite3.connect(path)
    connection.execute(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (2, ?, 'PairRunner222', 'pump', 61000, 'pump_fun')""",
        (SECOND_MINT,),
    )
    connection.execute(
        """INSERT INTO market_snapshots
           (id, candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
            venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
            volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1,
            pair_created_at_unix_ms)
           SELECT id + 100, 2, observed_at_unix_ms - 500, source,
                  source_observed_at_unix_ms - 500, venue, 'PairRunner222',
                  price_usd, liquidity_usd * 8.0, volume_m5_usd * 6.0,
                  volume_h1_usd * 4.0, buys_m5 * 2, 1, buys_h1 * 2, 10,
                  pair_created_at_unix_ms
           FROM market_snapshots
           WHERE candidate_id = 1"""
    )
    connection.execute(
        """INSERT INTO token_mint_states
           (id, candidate_id, provider, decimals, mint_authority, freeze_authority,
            slot, observed_at_unix_ms)
           VALUES (110, 2, 'helius', 6, NULL, NULL, '200', 984500)"""
    )
    connection.execute(
        """INSERT INTO token_holder_distributions
           (id, candidate_id, provider, mint, last_indexed_slot,
            observed_at_unix_ms, complete, top_holder_concentration_pct)
           VALUES (111, 2, 'helius', ?, '201', 985500, 1, 5.0)""",
        (SECOND_MINT,),
    )
    connection.execute(
        """INSERT INTO exit_quote_snapshots
           (id, candidate_id, provider, probe_policy_version, input_mint,
            output_mint, taker, input_amount, output_amount, minimum_output_amount,
            slippage_bps, route_available, price_impact_pct, quoted_at_unix_ms)
           VALUES (112, 2, 'jupiter', 'probe-v2', ?, ?, ?, '1000000',
                   '300000', '295000', 75, 1, '0.05', 986500)""",
        (SECOND_MINT, QUOTE_ASSET, TAKER),
    )
    connection.execute(
        """INSERT INTO paper_quote_snapshots
           (id, candidate_id, purpose, provider, probe_policy_version, input_mint,
            output_mint, taker, input_amount, output_amount, minimum_output_amount,
            slippage_bps, route_available, price_impact_pct, route_labels_json,
            quoted_at_unix_ms)
           VALUES (120, 2, 'entry', 'jupiter', 'probe-v2', ?, ?, ?, '100000000',
                   '500000000', '495000000', 75, 1, '0.05', '[\"Raydium\"]', 999500)""",
        (QUOTE_ASSET, SECOND_MINT, TAKER),
    )
    connection.execute(
        """INSERT INTO paper_quote_snapshots
           (id, candidate_id, purpose, provider, probe_policy_version, input_mint,
            output_mint, taker, input_amount, output_amount, minimum_output_amount,
            slippage_bps, route_available, price_impact_pct, route_labels_json,
            quoted_at_unix_ms)
           VALUES (121, 2, 'exit', 'jupiter', 'probe-v2', ?, ?, ?, '1000000',
                   '300000', '295000', 75, 1, '0.05', '[\"Raydium\"]', 988500)""",
        (SECOND_MINT, QUOTE_ASSET, TAKER),
    )
    connection.commit()
    connection.close()


def test_aggregate_cycle_uses_one_point_in_time_state_and_ranks_by_sealed_score(tmp_path) -> None:
    database = tmp_path / "observer.db"
    _seed_two_candidates(database)
    state = _state()
    template = _bundle()

    cycle, audit = assemble_observer_paper_campaign_cycle(
        database,
        state,
        AS_OF,
        template,
        _environment(),
        ObserverPaperCampaignSelectionPolicy(
            recent_lookback_ms=100_000,
            max_entry_candidates=2,
        ),
        global_risk_halt=False,
    )

    assert cycle.as_of_unix_ms == AS_OF
    assert len(cycle.entry_candidates) == 2
    assert all(item.features.as_of_unix_ms == AS_OF for item in cycle.entry_candidates)
    assert all(item.regime.as_of_unix_ms == AS_OF for item in cycle.entry_candidates)
    assert all(item.risk_context.as_of_unix_ms == AS_OF for item in cycle.entry_candidates)

    scored = []
    for item in cycle.entry_candidates:
        setup = assess_fresh_launch(item.features, item.setup.policy)
        score = score_candidate(item.features, setup, item.regime, item.score_policy)
        assert score.total_score is not None
        scored.append((score.total_score, item.mint))

    assert scored[0][0] > scored[1][0]
    assert tuple(item.mint for item in cycle.entry_candidates) == (SECOND_MINT, MINT)
    assert tuple(quote.mint for quote in cycle.quotes) == (SECOND_MINT, MINT)

    assert audit.schema_version == OBSERVER_PAPER_CAMPAIGN_CYCLE_AUDIT_SCHEMA_VERSION
    assert audit.as_of_unix_ms == AS_OF
    assert audit.selected_candidate_ids == (1, 2)
    assert audit.selected_mints == (MINT, SECOND_MINT)
    assert audit.ranked_entry_mints == (SECOND_MINT, MINT)
    assert len(audit.component_paper_cycle_fingerprints) == 2
    assert all(len(value) == 64 for value in audit.component_paper_cycle_fingerprints)
    assert len(audit.aggregate_cycle_fingerprint) == 64

    assert template == _bundle()


def test_candidate_specific_identity_changes_only_candidate_attribution(tmp_path) -> None:
    database = tmp_path / "observer.db"
    _seed_two_candidates(database)
    template = _bundle()

    cycle, _ = assemble_observer_paper_campaign_cycle(
        database,
        _state(),
        AS_OF,
        template,
        _environment(),
        ObserverPaperCampaignSelectionPolicy(
            recent_lookback_ms=100_000,
            max_entry_candidates=2,
        ),
        global_risk_halt=False,
    )

    assert {item.mint for item in cycle.entry_candidates} == {MINT, SECOND_MINT}
    assert all(item.score_policy == template.score_policy for item in cycle.entry_candidates)
    assert all(item.decision_policy == template.decision_policy for item in cycle.entry_candidates)
    assert all(item.risk_policy == template.risk_policy for item in cycle.entry_candidates)
    assert all(item.exit_policy == template.exit_policy for item in cycle.entry_candidates)
    assert template.entry_quote_identity == replace(
        template.entry_quote_identity,
        candidate_id=1,
        output_mint=MINT,
    )
