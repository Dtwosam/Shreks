from __future__ import annotations

from dataclasses import replace
import inspect
import sqlite3

import pytest

from shreks_brain.decision import DecisionPolicy, SetupDecisionRule
from shreks_brain.exits import ExitPolicy
from shreks_brain.features import FEATURE_SCHEMA_VERSION
from shreks_brain.observer_campaign.assembler import ObserverFreshLaunchPolicyBundle
from shreks_brain.observer_campaign.models import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverPaperRiskEnvironment,
    ObserverRegimeReadPolicy,
)
from shreks_brain.observer_campaign.runner import (
    ObserverPaperCampaignError,
    ObserverPaperCampaignRunner,
)
from shreks_brain.observer_market import ObserverMarketReadPolicy
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.paper import PaperExecutionState, PaperFillPolicy, create_paper_ledger
from shreks_brain.paper_evaluation import PaperEvaluationEvidenceStore
from shreks_brain.paper_loop import PaperLoopPolicy, create_paper_loop_state
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    PaperCheckpointError,
    load_latest_paper_checkpoint,
    validate_paper_accounting,
)
from shreks_brain.regime import RegimePolicy
from shreks_brain.registry import (
    CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
    RegistryCandidate,
    RegistryEvaluationEvidence,
    RegistryStatus,
)
from shreks_brain.risk import RiskPolicy
from shreks_brain.safety import SafetyPolicy
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import FRESH_LAUNCH_SETUP_NAME, FreshLaunchPolicy


AS_OF = 1_000_000
SECOND_AS_OF = 1_001_000
MINT = "MintRunner111"
QUOTE_ASSET = "QuoteRunner111"
TAKER = "TakerRunner111"
RUN_ID = "paper-run-e15-test"


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
        CREATE TABLE paper_loop_checkpoints (
            run_id TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            checkpoint_schema_version TEXT NOT NULL,
            state_as_of_unix_ms INTEGER NOT NULL CHECK (state_as_of_unix_ms >= 0),
            created_at_unix_ms INTEGER NOT NULL CHECK (created_at_unix_ms >= 0),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id, sequence)
        );
        """
    )
    return connection


def _seed(path) -> None:
    connection = _create_schema(path)
    connection.execute(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (1, ?, 'PairRunner', 'pump', 60000, 'pump_fun')""",
        (MINT,),
    )
    for values in (
        (1, 100_000, 0.20, 70.0, 30.0, 300.0, 30, 20, 300, 200),
        (2, 700_000, 0.22, 80.0, 35.0, 350.0, 35, 15, 320, 180),
        (3, 940_000, 0.24, 90.0, 40.0, 400.0, 40, 10, 340, 160),
        (4, 990_000, 0.25, 100.0, 50.0, 500.0, 45, 5, 360, 140),
        (5, SECOND_AS_OF + 100, 99.0, 9_999.0, 9_999.0, 9_999.0, 1, 99, 1, 999),
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
               VALUES (?, 1, ?, 'dexscreener', ?, 'pump_fun', 'PairRunner', ?, ?, ?, ?, ?, ?, ?, ?, 50000)""",
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
           VALUES (20, 1, 'entry', 'jupiter', 'probe-v2', ?, ?, ?, '100000000',
                   '400000000', '390000000', 75, 1, '0.1', '[\"Raydium\"]', 988000)""",
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
    connection.commit()
    connection.close()


def _bundle() -> ObserverFreshLaunchPolicyBundle:
    return ObserverFreshLaunchPolicyBundle(
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
            entry_input_amount=100_000_000,
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
            input_amount=100_000_000,
            slippage_bps=75,
        ),
        setup_name=FRESH_LAUNCH_SETUP_NAME,
    )


def _state():
    return create_paper_loop_state(
        create_paper_ledger(1_000.0, 900_000),
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


def _candidate(**overrides) -> RegistryCandidate:
    values = dict(
        schema_version=CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
        candidate_version="candidate-v1",
        strategy_version="fresh-v1",
        model_version=None,
        model_training_schema_version=None,
        model_training_fingerprint_sha256=None,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_columns=("price_usd",),
        training_started_at_unix_ms=None,
        training_ended_at_unix_ms=None,
        validation_schema_version=None,
        validation_policy_version=None,
        validation_run_fingerprint_sha256=None,
        evaluation=RegistryEvaluationEvidence(
            schema_version="evaluation-v1",
            policy_version="evaluation-policy-v1",
            evaluation_fingerprint_sha256="b" * 64,
            trade_count=0,
            net_pnl_usd=0.0,
            net_expectancy_usd=None,
            net_expectancy_pct=None,
            profit_factor=None,
            maximum_drawdown_usd=0.0,
            maximum_drawdown_pct=0.0,
            win_rate=None,
            turnover_usd=0.0,
            total_cost_usd=0.0,
            brier_score=None,
            expected_calibration_error=None,
        ),
        registered_at_unix_ms=0,
        initial_status=RegistryStatus.CHALLENGER,
        candidate_fingerprint_sha256="a" * 64,
    )
    values.update(overrides)
    return RegistryCandidate(**values)


def _runner(db_path, evidence_path, *, candidate=None):
    return ObserverPaperCampaignRunner(
        db_path,
        evidence_path,
        _candidate() if candidate is None else candidate,
        RUN_ID,
        _state(),
        _bundle(),
        _environment(),
        global_risk_halt=False,
    )


def test_first_cycle_records_e11_then_saves_c6_checkpoint(tmp_path):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed(db_path)
    runner = _runner(db_path, evidence_path)

    assert runner.load_state() == _state()
    result = runner.run_cycle(AS_OF, AS_OF)

    assert result.as_of_unix_ms == AS_OF
    assert result.next_state.last_cycle_at_unix_ms == AS_OF
    assert len(result.entry_results) == 1
    entry = result.entry_results[0]
    assert entry.selected_for_entry is True
    assert entry.execution is not None
    assert entry.execution.state is PaperExecutionState.FILLED

    checkpoint = load_latest_paper_checkpoint(db_path, RUN_ID)
    assert checkpoint is not None
    assert checkpoint.sequence == 1
    assert checkpoint.state == result.next_state

    accounting = validate_paper_accounting(result.next_state)
    assert accounting.status is not AccountingValidationStatus.INVALID

    evidence = PaperEvaluationEvidenceStore(evidence_path).load()
    assert len(evidence.entry_provenance) == 1
    assert len(evidence.executions) == 1
    assert evidence.entry_provenance[0].candidate_version == "candidate-v1"
    assert evidence.entry_provenance[0].paper_run_id == RUN_ID
    assert runner.evaluated_trades() == ()


def test_completed_cycle_replay_is_idempotent_without_duplicate_evidence_or_checkpoint(tmp_path):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed(db_path)
    runner = _runner(db_path, evidence_path)
    first = runner.run_cycle(AS_OF, AS_OF)
    before = PaperEvaluationEvidenceStore(evidence_path).load()

    replay = runner.run_cycle(AS_OF, AS_OF)
    after = PaperEvaluationEvidenceStore(evidence_path).load()
    checkpoint = load_latest_paper_checkpoint(db_path, RUN_ID)

    assert replay.next_state == first.next_state
    assert replay.entry_results == ()
    assert replay.exit_results == ()
    assert after.document_fingerprint_sha256 == before.document_fingerprint_sha256
    assert checkpoint is not None
    assert checkpoint.sequence == 1


def test_restart_matches_uninterrupted_state_accounting_evidence_and_trades(tmp_path):
    uninterrupted_db = tmp_path / "uninterrupted.db"
    restarted_db = tmp_path / "restarted.db"
    uninterrupted_evidence = tmp_path / "uninterrupted-e11.json"
    restarted_evidence = tmp_path / "restarted-e11.json"
    _seed(uninterrupted_db)
    _seed(restarted_db)

    uninterrupted = _runner(uninterrupted_db, uninterrupted_evidence)
    uninterrupted.run_cycle(AS_OF, AS_OF)
    uninterrupted_second = uninterrupted.run_cycle(SECOND_AS_OF, SECOND_AS_OF)

    before_restart = _runner(restarted_db, restarted_evidence)
    before_restart.run_cycle(AS_OF, AS_OF)
    after_restart = _runner(restarted_db, restarted_evidence)
    restarted_second = after_restart.run_cycle(SECOND_AS_OF, SECOND_AS_OF)

    assert restarted_second.next_state == uninterrupted_second.next_state
    assert validate_paper_accounting(restarted_second.next_state) == validate_paper_accounting(
        uninterrupted_second.next_state
    )
    restarted_ledger = PaperEvaluationEvidenceStore(restarted_evidence).load()
    uninterrupted_ledger = PaperEvaluationEvidenceStore(uninterrupted_evidence).load()
    assert (
        restarted_ledger.document_fingerprint_sha256
        == uninterrupted_ledger.document_fingerprint_sha256
    )
    assert after_restart.evaluated_trades() == uninterrupted.evaluated_trades()

    restarted_checkpoint = load_latest_paper_checkpoint(restarted_db, RUN_ID)
    uninterrupted_checkpoint = load_latest_paper_checkpoint(uninterrupted_db, RUN_ID)
    assert restarted_checkpoint is not None
    assert uninterrupted_checkpoint is not None
    assert restarted_checkpoint.sequence == uninterrupted_checkpoint.sequence == 2


def test_paper_run_reuse_with_different_registry_candidate_fails_closed(tmp_path):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed(db_path)
    _runner(db_path, evidence_path).run_cycle(AS_OF, AS_OF)

    changed = _candidate(
        candidate_version="candidate-v2",
        candidate_fingerprint_sha256="c" * 64,
    )
    with pytest.raises(ObserverPaperCampaignError, match="attribution"):
        _runner(db_path, evidence_path, candidate=changed).load_state()


def test_e11_corruption_and_checkpoint_collision_fail_closed(tmp_path, monkeypatch):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed(db_path)
    runner = _runner(db_path, evidence_path)
    runner.run_cycle(AS_OF, AS_OF)
    evidence_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ObserverPaperCampaignError, match="evidence"):
        runner.evaluated_trades()

    collision_db = tmp_path / "collision.db"
    collision_evidence = tmp_path / "collision-e11.json"
    _seed(collision_db)
    collision_runner = _runner(collision_db, collision_evidence)

    import shreks_brain.observer_campaign.runner as runner_module

    def _collision(*args, **kwargs):
        raise PaperCheckpointError("checkpoint sequence collision")

    monkeypatch.setattr(runner_module, "save_paper_checkpoint", _collision)
    with pytest.raises(ObserverPaperCampaignError, match="checkpoint"):
        collision_runner.run_cycle(AS_OF, AS_OF)


def test_runner_has_no_proof_promotion_or_live_execution_authority():
    import shreks_brain.observer_campaign.runner as runner_module

    source = inspect.getsource(runner_module)
    for forbidden in (
        "shreks_brain.proof",
        "shreks_brain.promotion",
        "record_status",
        "promote",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
    ):
        assert forbidden not in source
