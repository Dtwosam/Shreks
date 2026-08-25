from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from shreks_brain.decision import DecisionPolicy, SetupDecisionRule
from shreks_brain.exits import ExitPolicy
from shreks_brain.features import FEATURE_SCHEMA_VERSION
from shreks_brain.observer_campaign.assembler import (
    OBSERVER_PAPER_CYCLE_AUDIT_SCHEMA_VERSION,
    ObserverFreshLaunchPolicyBundle,
    ObserverPaperAssemblyError,
    assemble_observer_paper_cycle,
)
from shreks_brain.observer_campaign.models import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverPaperRiskEnvironment,
    ObserverRegimeReadPolicy,
)
from shreks_brain.observer_market import ObserverMarketReadPolicy
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.paper import PaperFillPolicy, PaperQuoteState, create_paper_ledger
from shreks_brain.paper_loop import (
    FreshLaunchSetupInput,
    PaperLoopPolicy,
    create_paper_loop_state,
)
from shreks_brain.regime import MarketRegime, RegimePolicy
from shreks_brain.risk import RiskPolicy
from shreks_brain.safety import SafetyDecision, SafetyPolicy
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import (
    FIRST_PULLBACK_SETUP_NAME,
    FRESH_LAUNCH_SETUP_NAME,
    GRADUATION_BREAKOUT_SETUP_NAME,
    FreshLaunchPolicy,
)


AS_OF = 1_000_000
MINT = "MintAssembler111"
QUOTE_ASSET = "QuoteAsset111"
TAKER = "Taker111"


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


def _seed(path) -> None:
    connection = _create_schema(path)
    connection.execute(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (1, ?, 'PairAssembler', 'pump', 60000, 'pump_fun')""",
        (MINT,),
    )
    for values in (
        (1, 100_000, 0.20, 70.0, 30.0, 300.0, 30, 20, 300, 200),
        (2, 700_000, 0.22, 80.0, 35.0, 350.0, 35, 15, 320, 180),
        (3, 940_000, 0.24, 90.0, 40.0, 400.0, 40, 10, 340, 160),
        (4, 990_000, 0.25, 100.0, 50.0, 500.0, 45, 5, 360, 140),
        (5, AS_OF + 100, 99.0, 9_999.0, 9_999.0, 9_999.0, 1, 99, 1, 999),
    ):
        (
            row_id,
            observed_at,
            price,
            liquidity,
            volume_m5,
            volume_h1,
            buys_m5,
            sells_m5,
            buys_h1,
            sells_h1,
        ) = values
        connection.execute(
            """INSERT INTO market_snapshots
               (id, candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
                venue, pair_address, price_usd, liquidity_usd, volume_m5_usd,
                volume_h1_usd, buys_m5, sells_m5, buys_h1, sells_h1,
                pair_created_at_unix_ms)
               VALUES (?, 1, ?, 'dexscreener', ?, 'pump_fun', 'PairAssembler', ?, ?, ?, ?, ?, ?, ?, ?, 50000)""",
            (
                row_id,
                observed_at,
                observed_at - 1,
                price,
                liquidity,
                volume_m5,
                volume_h1,
                buys_m5,
                sells_m5,
                buys_h1,
                sells_h1,
            ),
        )

    connection.execute(
        """INSERT INTO token_mint_states
           (id, candidate_id, provider, decimals, mint_authority, freeze_authority,
            slot, observed_at_unix_ms)
           VALUES (10, 1, 'helius', 6, NULL, NULL, '100', 985000)"""
    )
    connection.execute(
        """INSERT INTO token_holder_distributions
           (id, candidate_id, provider, mint, last_indexed_slot,
            observed_at_unix_ms, complete, top_holder_concentration_pct)
           VALUES (11, 1, 'helius', ?, '101', 986000, 1, 10.0)""",
        (MINT,),
    )
    connection.execute(
        """INSERT INTO exit_quote_snapshots
           (id, candidate_id, provider, probe_policy_version, input_mint,
            output_mint, taker, input_amount, output_amount, minimum_output_amount,
            slippage_bps, route_available, price_impact_pct, quoted_at_unix_ms)
           VALUES (12, 1, 'jupiter', 'probe-v2', ?, ?, ?, '1000000',
                   '245000', '240000', 75, 1, '0.2', 987000)""",
        (MINT, QUOTE_ASSET, TAKER),
    )
    connection.execute(
        """INSERT INTO paper_quote_snapshots
           (id, candidate_id, purpose, provider, probe_policy_version, input_mint,
            output_mint, taker, input_amount, output_amount, minimum_output_amount,
            slippage_bps, route_available, price_impact_pct, route_labels_json,
            quoted_at_unix_ms)
           VALUES (20, 1, 'entry', 'jupiter', 'probe-v2', ?, ?, ?, '1000000',
                   '4000000', '3900000', 75, 1, '0.1', '[\"Raydium\"]', 988000)""",
        (QUOTE_ASSET, MINT, TAKER),
    )
    connection.execute(
        """INSERT INTO paper_quote_snapshots
           (id, candidate_id, purpose, provider, probe_policy_version, input_mint,
            output_mint, taker, input_amount, output_amount, minimum_output_amount,
            slippage_bps, route_available, price_impact_pct, route_labels_json,
            quoted_at_unix_ms)
           VALUES (21, 1, 'exit', 'jupiter', 'probe-v2', ?, ?, ?, '1000000',
                   '250000', '245000', 75, 1, '0.2', '[\"Raydium\"]', 989000)""",
        (MINT, QUOTE_ASSET, TAKER),
    )
    connection.execute(
        """INSERT INTO paper_quote_snapshots
           (id, candidate_id, purpose, provider, probe_policy_version, input_mint,
            output_mint, taker, input_amount, output_amount, minimum_output_amount,
            slippage_bps, route_available, price_impact_pct, route_labels_json,
            quoted_at_unix_ms)
           VALUES (22, 1, 'entry', 'jupiter', 'probe-v2', ?, ?, ?, '1000000',
                   '1', '1', 75, 1, '99', '[\"Future\"]', ?)""",
        (QUOTE_ASSET, MINT, TAKER, AS_OF + 100),
    )
    connection.commit()
    connection.close()


def _bundle(**overrides) -> ObserverFreshLaunchPolicyBundle:
    values = dict(
        market_read_policy=ObserverMarketReadPolicy(
            version="market-read-v1",
            source_priority=("dexscreener",),
            max_current_age_ms=60_000,
            local_range_lookback_ms=1_000_000,
        ),
        safety_policy=SafetyPolicy(
            version="safety-v1",
            min_liquidity_usd=25.0,
            soft_min_liquidity_usd=40.0,
            max_top_holder_concentration_pct=50.0,
            soft_max_top_holder_concentration_pct=40.0,
            soft_max_creator_concentration_pct=40.0,
            soft_max_exit_price_impact_pct=5.0,
            max_critical_data_age_ms=100_000,
        ),
        safety_probe_identity=ObserverSafetyProbeIdentity(
            probe_policy_version="probe-v2",
            output_mint=QUOTE_ASSET,
            input_amount=1_000_000,
            taker=TAKER,
            slippage_bps=75,
        ),
        regime_read_policy=ObserverRegimeReadPolicy(
            version="regime-read-v1",
            window_ms=600_000,
            max_snapshot_age_ms=60_000,
            source_priority=("dexscreener",),
            entry_probe_policy_version="probe-v2",
            quote_asset_mint=QUOTE_ASSET,
            entry_input_amount=1_000_000,
            taker=TAKER,
            slippage_bps=75,
        ),
        regime_policy=RegimePolicy(
            version="regime-v1",
            max_source_age_ms=100_000,
            min_window_seconds=60.0,
            min_candidate_samples=1,
            dead_max_candidate_rate_per_hour=0.1,
            weak_min_candidate_rate_per_hour=0.2,
            hot_min_candidate_rate_per_hour=1.0,
            dead_max_executable_fraction=0.0,
            weak_min_executable_fraction=0.2,
            hot_min_executable_fraction=0.5,
            weak_min_median_liquidity_usd=25.0,
            hot_min_median_liquidity_usd=50.0,
            weak_min_median_volume_m5_usd=10.0,
            hot_min_median_volume_m5_usd=20.0,
            min_performance_sample_count=5,
            dead_performance_expectancy_pct=-10.0,
            weak_performance_expectancy_pct=0.0,
        ),
        fresh_launch_policy=FreshLaunchPolicy(
            version="fresh-v1",
            min_age_seconds=1.0,
            max_age_seconds=10_000.0,
            max_source_age_ms=100_000,
            min_liquidity_usd=1.0,
            max_exit_price_impact_pct=100.0,
            max_return_5m_pct=1_000.0,
            min_tx_count_m5=1,
            min_volume_velocity_ratio=0.0,
            min_buy_fraction_m5=0.0,
            min_buy_pressure_acceleration=-1.0,
            min_return_1m_pct=-100.0,
            min_return_5m_pct=-100.0,
            min_liquidity_change_5m_pct=-100.0,
            min_distance_from_local_high_pct=-100.0,
            min_range_position_pct=0.0,
        ),
        score_policy=ScorePolicy(
            version="score-v1",
            required_feature_schema_version=FEATURE_SCHEMA_VERSION,
            safety_weight=0.25,
            money_flow_weight=0.25,
            setup_quality_weight=0.25,
            liquidity_executability_weight=0.25,
            safety_liquidity_weak_penalty=5.0,
            safety_holder_concentration_elevated_penalty=5.0,
            safety_creator_concentration_elevated_penalty=5.0,
            safety_exit_price_impact_elevated_penalty=5.0,
            volume_velocity_zero=0.0,
            volume_velocity_full=2.0,
            buy_fraction_m5_zero=0.0,
            buy_fraction_m5_full=1.0,
            buy_pressure_acceleration_zero=-1.0,
            buy_pressure_acceleration_full=1.0,
            liquidity_usd_zero=0.0,
            liquidity_usd_full=1_000.0,
            exit_price_impact_full=0.0,
            exit_price_impact_zero=100.0,
        ),
        decision_policy=DecisionPolicy(
            version="decision-v1",
            required_score_policy_version="score-v1",
            setup_rules=(
                SetupDecisionRule(
                    setup_name=FRESH_LAUNCH_SETUP_NAME,
                    enabled=True,
                    hot_min_score=0.0,
                    normal_min_score=0.0,
                    weak_min_score=0.0,
                ),
            ),
        ),
        risk_policy=RiskPolicy(
            version="risk-v1",
            required_decision_policy_version="decision-v1",
            required_feature_schema_version=FEATURE_SCHEMA_VERSION,
            target_position_notional_usd=100.0,
            max_notional_per_position_usd=200.0,
            max_capital_fraction_per_position=1.0,
            max_simultaneous_positions=10,
            max_aggregate_open_risk_usd=1_000.0,
            max_daily_realized_loss_usd=1_000.0,
            max_rolling_drawdown_pct=100.0,
            cooldown_after_consecutive_losses=10,
            cooldown_seconds=0,
            min_liquidity_usd=0.0,
            max_expected_price_impact_pct=100.0,
            max_slippage_bps=10_000,
            max_market_data_age_ms=100_000,
        ),
        exit_policy=ExitPolicy(
            version="exit-v1",
            required_feature_schema_version=FEATURE_SCHEMA_VERSION,
            max_market_data_age_ms=100_000,
            max_execution_evidence_age_ms=100_000,
            hard_stop_loss_pct=None,
            take_profit_levels=(),
            trailing_activation_return_pct=None,
            trailing_stop_drawdown_pct=None,
            max_hold_seconds=None,
            flow_exit_max_buy_fraction_m5=None,
            flow_exit_max_buy_pressure_acceleration=None,
            momentum_exit_max_return_1m_pct=None,
            momentum_exit_max_return_5m_pct=None,
            min_liquidity_usd=None,
            max_exit_price_impact_pct=None,
            min_exit_capacity_fraction=None,
            wallet_distribution_enabled=False,
        ),
        quote_asset=ObserverPaperQuoteAsset(
            mint=QUOTE_ASSET,
            decimals=6,
            usd_per_token=1.0,
        ),
        entry_quote_identity=ObserverPaperQuoteIdentity(
            candidate_id=1,
            purpose=ObserverPaperQuotePurpose.ENTRY,
            provider="jupiter",
            probe_policy_version="probe-v2",
            input_mint=QUOTE_ASSET,
            output_mint=MINT,
            taker=TAKER,
            input_amount=1_000_000,
            slippage_bps=75,
        ),
        setup_name=FRESH_LAUNCH_SETUP_NAME,
    )
    values.update(overrides)
    return ObserverFreshLaunchPolicyBundle(**values)


def _state():
    ledger = create_paper_ledger(1_000.0, 900_000)
    return create_paper_loop_state(
        ledger,
        PaperLoopPolicy(version="loop-v1", exit_max_slippage_bps=75),
        PaperFillPolicy(
            version="fill-v1",
            assumed_latency_ms=0,
            max_quote_lag_ms=60_000,
            swap_fee_bps=30,
            network_fee_usd=0.01,
            allow_partial_fills=True,
            min_partial_fill_fraction=0.1,
        ),
    )


def _environment() -> ObserverPaperRiskEnvironment:
    return ObserverPaperRiskEnvironment(
        trading_capital_usd=1_000.0,
        day_started_at_unix_ms=0,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
    )


def test_clean_fresh_launch_cycle_is_composed_from_point_in_time_evidence(tmp_path):
    path = tmp_path / "observer.db"
    _seed(path)

    cycle, audit = assemble_observer_paper_cycle(
        path,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        global_risk_halt=False,
    )

    assert cycle.as_of_unix_ms == AS_OF
    assert len(cycle.entry_candidates) == 1
    candidate = cycle.entry_candidates[0]
    assert candidate.mint == MINT
    assert candidate.features.as_of_unix_ms == AS_OF
    assert candidate.features.source_observed_at_unix_ms == 990_000
    assert candidate.features.price_usd == 0.25
    assert candidate.features.safety_decision is SafetyDecision.PASS
    assert candidate.regime.regime is MarketRegime.HOT
    assert isinstance(candidate.setup, FreshLaunchSetupInput)
    assert candidate.setup.policy == _bundle().fresh_launch_policy
    assert candidate.risk_context.trading_capital_usd == 1_000.0
    assert candidate.risk_context.expected_price_impact_pct == 0.1
    assert candidate.risk_context.price_impact_notional_usd == 1.0

    assert cycle.exit_observations == ()
    assert len(cycle.quotes) == 1
    entry_quote = cycle.quotes[0]
    assert entry_quote.mint == MINT
    assert entry_quote.state is PaperQuoteState.EXECUTABLE
    assert entry_quote.observed_at_unix_ms == 988_000
    assert entry_quote.reference_price_usd == 0.25
    assert entry_quote.execution_price_usd == 0.25
    assert entry_quote.quoted_notional_usd == 1.0

    assert audit.schema_version == OBSERVER_PAPER_CYCLE_AUDIT_SCHEMA_VERSION
    assert audit.candidate_id == 1
    assert audit.mint == MINT
    assert audit.as_of_unix_ms == AS_OF
    assert audit.market_current_observed_at_unix_ms == 990_000
    assert audit.entry_quote_observed_at_unix_ms == 988_000
    assert audit.exit_quote_observed_at_unix_ms == 989_000
    for fingerprint in (
        audit.market_fingerprint,
        audit.safety_fingerprint,
        audit.feature_fingerprint,
        audit.regime_fingerprint,
        audit.risk_context_fingerprint,
        audit.entry_quote_identity_fingerprint,
        audit.exit_quote_identity_fingerprint,
        audit.paper_cycle_fingerprint,
    ):
        assert len(fingerprint) == 64
        int(fingerprint, 16)


def test_future_rows_are_invisible_and_missing_entry_quote_never_becomes_fill(tmp_path):
    path = tmp_path / "observer.db"
    _seed(path)
    connection = sqlite3.connect(path)
    connection.execute("DELETE FROM paper_quote_snapshots WHERE purpose = 'entry' AND quoted_at_unix_ms <= ?", (AS_OF,))
    connection.commit()
    connection.close()

    cycle, audit = assemble_observer_paper_cycle(
        path,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        global_risk_halt=False,
    )

    candidate = cycle.entry_candidates[0]
    assert candidate.features.price_usd == 0.25
    assert candidate.features.source_observed_at_unix_ms == 990_000
    assert candidate.risk_context.expected_price_impact_pct is None
    assert candidate.risk_context.price_impact_notional_usd is None
    assert cycle.quotes == ()
    assert audit.entry_quote_observed_at_unix_ms is None


def test_incomplete_and_rejected_safety_are_preserved_for_sealed_decision_path(tmp_path):
    incomplete_path = tmp_path / "incomplete.db"
    _seed(incomplete_path)
    connection = sqlite3.connect(incomplete_path)
    connection.execute("DELETE FROM token_holder_distributions")
    connection.commit()
    connection.close()

    incomplete_cycle, _ = assemble_observer_paper_cycle(
        incomplete_path,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        global_risk_halt=False,
    )
    assert incomplete_cycle.entry_candidates[0].features.safety_decision is SafetyDecision.INCOMPLETE

    rejected_path = tmp_path / "rejected.db"
    _seed(rejected_path)
    connection = sqlite3.connect(rejected_path)
    connection.execute("UPDATE token_mint_states SET mint_authority = 'ActiveAuthority'")
    connection.commit()
    connection.close()

    rejected_cycle, _ = assemble_observer_paper_cycle(
        rejected_path,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        global_risk_halt=False,
    )
    assert rejected_cycle.entry_candidates[0].features.safety_decision is SafetyDecision.REJECT


def test_dead_regime_passes_through_unchanged(tmp_path):
    path = tmp_path / "observer.db"
    _seed(path)
    bundle = _bundle()
    dead_policy = replace(
        bundle.regime_policy,
        dead_max_candidate_rate_per_hour=10.0,
        weak_min_candidate_rate_per_hour=10.0,
        hot_min_candidate_rate_per_hour=100.0,
    )

    cycle, _ = assemble_observer_paper_cycle(
        path,
        _state(),
        AS_OF,
        replace(bundle, regime_policy=dead_policy),
        _environment(),
        global_risk_halt=False,
    )
    assert cycle.entry_candidates[0].regime.regime is MarketRegime.DEAD


def test_wrong_candidate_or_cross_policy_quote_attribution_fails_closed(tmp_path):
    path = tmp_path / "observer.db"
    _seed(path)
    bundle = _bundle()

    wrong_candidate = replace(
        bundle.entry_quote_identity,
        candidate_id=2,
        output_mint="OtherMint",
    )
    with pytest.raises(ObserverPaperAssemblyError):
        assemble_observer_paper_cycle(
            path,
            _state(),
            AS_OF,
            replace(bundle, entry_quote_identity=wrong_candidate),
            _environment(),
            global_risk_halt=False,
        )

    mismatched_regime_read = replace(
        bundle.regime_read_policy,
        entry_probe_policy_version="other-probe",
    )
    with pytest.raises(ObserverPaperAssemblyError, match="regime read"):
        replace(bundle, regime_read_policy=mismatched_regime_read)


@pytest.mark.parametrize(
    "setup_name",
    (GRADUATION_BREAKOUT_SETUP_NAME, FIRST_PULLBACK_SETUP_NAME),
)
def test_v1_rejects_unsupported_setup_contexts(setup_name):
    with pytest.raises(ObserverPaperAssemblyError, match="Fresh Launch"):
        _bundle(setup_name=setup_name)
