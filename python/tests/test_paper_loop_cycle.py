import math

import pytest

from shreks_brain.decision import DecisionPolicy, SetupDecisionRule
from shreks_brain.exits import (
    ExitExecutionContext,
    ExitPolicy,
    ExitRouteState,
    TakeProfitLevel,
    create_exit_state,
)
from shreks_brain.features import FeatureVector
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedgerUpdateState,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
)
from shreks_brain.paper_loop.engine import create_paper_loop_state, run_paper_cycle
from shreks_brain.paper_loop.models import (
    FreshLaunchSetupInput,
    ManagedPaperPosition,
    PaperCycleInput,
    PaperEntryCandidate,
    PaperExitObservation,
    PaperLoopPolicy,
    PaperLoopReasonCode,
)
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.risk import RiskContext, RiskPolicy, TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import FRESH_LAUNCH_SETUP_NAME, FreshLaunchPolicy


T0 = 2_000_000
MINT = "MintLifecycle"


def _features(as_of: int, *, price: float = 1.0) -> FeatureVector:
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=as_of,
        source_age_ms=0,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=300.0,
        price_usd=price,
        liquidity_usd=100_000.0,
        liquidity_change_5m_pct=10.0,
        exit_price_impact_pct=2.0,
        volume_m5_usd=20_000.0,
        volume_h1_usd=100_000.0,
        volume_velocity_ratio=2.4,
        tx_count_m5=100,
        tx_count_h1=500,
        buy_fraction_m5=0.75,
        buy_fraction_h1=0.60,
        buy_sell_ratio_m5=3.0,
        buy_sell_ratio_h1=1.5,
        buy_pressure_acceleration=0.15,
        return_1m_pct=4.0,
        return_5m_pct=20.0,
        return_15m_pct=30.0,
        momentum_acceleration_1m_vs_5m=0.0,
        distance_from_local_high_pct=-5.0,
        range_position_pct=85.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )


def _regime(as_of: int) -> RegimeAssessment:
    return RegimeAssessment(
        policy_version="regime-v1-test",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=as_of,
        window_started_at_unix_ms=as_of - 360_000,
        source_age_ms=0,
        window_seconds=360.0,
        candidate_count=12,
        candidate_rate_per_hour=120.0,
        executable_fraction=0.75,
        median_liquidity_usd=80_000.0,
        median_volume_m5_usd=25_000.0,
        base_regime=MarketRegime.NORMAL,
        regime=MarketRegime.NORMAL,
        performance_sample_count=None,
        performance_net_expectancy_after_costs_pct=None,
        performance_applied=False,
        findings=(),
    )


def _setup_policy() -> FreshLaunchPolicy:
    return FreshLaunchPolicy(
        version="fresh-v1-test",
        min_age_seconds=60.0,
        max_age_seconds=900.0,
        max_source_age_ms=30_000,
        min_liquidity_usd=50_000.0,
        max_exit_price_impact_pct=5.0,
        max_return_5m_pct=80.0,
        min_tx_count_m5=50,
        min_volume_velocity_ratio=1.2,
        min_buy_fraction_m5=0.60,
        min_buy_pressure_acceleration=0.05,
        min_return_1m_pct=1.0,
        min_return_5m_pct=5.0,
        min_liquidity_change_5m_pct=0.0,
        min_distance_from_local_high_pct=-15.0,
        min_range_position_pct=60.0,
    )


def _score_policy() -> ScorePolicy:
    return ScorePolicy(
        version="score-v1-test",
        required_feature_schema_version="b2-v1",
        safety_weight=0.20,
        money_flow_weight=0.30,
        setup_quality_weight=0.30,
        liquidity_executability_weight=0.20,
        safety_liquidity_weak_penalty=20.0,
        safety_holder_concentration_elevated_penalty=25.0,
        safety_creator_concentration_elevated_penalty=15.0,
        safety_exit_price_impact_elevated_penalty=30.0,
        volume_velocity_zero=0.5,
        volume_velocity_full=2.0,
        buy_fraction_m5_zero=0.40,
        buy_fraction_m5_full=0.70,
        buy_pressure_acceleration_zero=-0.10,
        buy_pressure_acceleration_full=0.20,
        liquidity_usd_zero=10_000.0,
        liquidity_usd_full=100_000.0,
        exit_price_impact_full=1.0,
        exit_price_impact_zero=8.0,
    )


def _decision_policy() -> DecisionPolicy:
    return DecisionPolicy(
        version="decision-v1-test",
        required_score_policy_version="score-v1-test",
        setup_rules=(
            SetupDecisionRule(
                FRESH_LAUNCH_SETUP_NAME,
                True,
                70.0,
                70.0,
                80.0,
            ),
        ),
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-v1-test",
        required_decision_policy_version="decision-v1-test",
        required_feature_schema_version="b2-v1",
        target_position_notional_usd=500.0,
        max_notional_per_position_usd=1_000.0,
        max_capital_fraction_per_position=0.10,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=3_000.0,
        max_daily_realized_loss_usd=500.0,
        max_rolling_drawdown_pct=20.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=300,
        min_liquidity_usd=50_000.0,
        max_expected_price_impact_pct=5.0,
        max_slippage_bps=300,
        max_market_data_age_ms=30_000,
    )


def _risk_context(as_of: int, *, open_count: int = 0, open_risk: float = 0.0) -> RiskContext:
    return RiskContext(
        as_of_unix_ms=as_of,
        trading_capital_usd=10_000.0,
        open_position_count=open_count,
        aggregate_open_risk_usd=open_risk,
        daily_realized_pnl_usd=0.0,
        rolling_drawdown_pct=0.0,
        consecutive_losses=0,
        last_loss_at_unix_ms=None,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=2.0,
        price_impact_notional_usd=5_000.0,
        market_data_age_ms=0,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _exit_policy() -> ExitPolicy:
    return ExitPolicy(
        version="exit-v1-test",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(TakeProfitLevel("tp1", 20.0, 0.5),),
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
    )


def _paper_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-v1-test",
        assumed_latency_ms=1_000,
        max_quote_lag_ms=5_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.10,
    )


def _candidate(as_of: int, mint: str = MINT) -> PaperEntryCandidate:
    return PaperEntryCandidate(
        mint=mint,
        features=_features(as_of),
        regime=_regime(as_of),
        setup=FreshLaunchSetupInput(_setup_policy()),
        score_policy=_score_policy(),
        decision_policy=_decision_policy(),
        risk_context=_risk_context(as_of),
        risk_policy=_risk_policy(),
        exit_policy=_exit_policy(),
    )


def _quote(
    mint: str,
    at: int,
    *,
    price: float = 1.0,
    quoted: float = 10_000.0,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
) -> PaperQuote:
    return PaperQuote(
        provider="paper-test",
        mint=mint,
        observed_at_unix_ms=at,
        state=state,
        reference_price_usd=price,
        execution_price_usd=price,
        quoted_notional_usd=quoted,
        available_notional_usd=10_000.0,
    )


def _observation(state, at: int, *, price: float, global_halt: bool = False):
    managed = state.managed_positions[0]
    return PaperExitObservation(
        position_id=managed.position_id,
        features=_features(at, price=price),
        execution_context=ExitExecutionContext(
            as_of_unix_ms=at,
            observed_at_unix_ms=at,
            route_state=ExitRouteState.AVAILABLE,
            available_exit_notional_usd=None,
            expected_exit_price_impact_pct=None,
            price_impact_notional_usd=None,
            wallet_distribution_detected=None,
            global_halt_active=global_halt,
        ),
    )


def _run(state, at: int, *, candidates=(), observations=(), quotes=()):
    return run_paper_cycle(
        state,
        PaperCycleInput(at, tuple(candidates), tuple(observations), tuple(quotes)),
    )


def _open_position(state):
    return next(p for p in state.ledger.positions if p.state is PaperPositionState.OPEN)


def test_deferred_buy_to_partial_tp_failed_exit_and_final_close_reconciles() -> None:
    state = create_paper_loop_state(
        create_paper_ledger(10_000.0, T0 - 1),
        PaperLoopPolicy("loop-v1-test", 300),
        _paper_policy(),
    )

    # N: B9 BUY is approved but C1 latency makes it pending.
    n = _run(state, T0, candidates=(_candidate(T0),))
    assert n.next_state.pending_entry is not None
    assert n.entry_results[0].reason is PaperLoopReasonCode.ENTRY_EXECUTION_DEFERRED
    assert n.entry_results[0].execution.state is PaperExecutionState.DEFERRED

    # N+1: exact pending BUY fills and opens C3/C4 lifecycle.
    n1 = _run(n.next_state, T0 + 1_000, quotes=(_quote(MINT, T0 + 1_000),))
    assert n1.pending_entry_result is not None
    assert n1.pending_entry_result.execution.state is PaperExecutionState.FILLED
    assert n1.next_state.pending_entry is None
    assert len(n1.next_state.managed_positions) == 1
    assert _open_position(n1.next_state).quantity == pytest.approx(500.0)

    # N+2: monitor/mark only; no exit.
    n2 = _run(
        n1.next_state,
        T0 + 2_000,
        observations=(_observation(n1.next_state, T0 + 2_000, price=1.10),),
    )
    assert n2.exit_results[0].reason is PaperLoopReasonCode.EXIT_HOLD
    assert _open_position(n2.next_state).last_mark_price_usd == pytest.approx(1.10)

    # N+3: TP is authorized but held pending for latency/quote.
    n3 = _run(
        n2.next_state,
        T0 + 3_000,
        observations=(_observation(n2.next_state, T0 + 3_000, price=1.20),),
    )
    assert n3.next_state.managed_positions[0].pending_exit is not None

    # N+4: quote-limited partial sell books 100 tokens, below TP target.
    n4 = _run(
        n3.next_state,
        T0 + 4_000,
        observations=(_observation(n3.next_state, T0 + 4_000, price=1.20),),
        quotes=(_quote(MINT, T0 + 4_000, quoted=100.0),),
    )
    assert n4.exit_results[0].execution.state is PaperExecutionState.PARTIAL
    assert _open_position(n4.next_state).quantity == pytest.approx(400.0)
    assert "tp1" not in n4.next_state.managed_positions[0].exit_state.completed_take_profit_levels

    # N+5/N+6: fresh TP decision targets half of remaining 400 and completes after booking.
    n5 = _run(
        n4.next_state,
        T0 + 5_000,
        observations=(_observation(n4.next_state, T0 + 5_000, price=1.20),),
    )
    pending_tp = n5.next_state.managed_positions[0].pending_exit
    assert pending_tp is not None
    assert pending_tp.target_quantity == pytest.approx(200.0)
    n6 = _run(
        n5.next_state,
        T0 + 6_000,
        observations=(_observation(n5.next_state, T0 + 6_000, price=1.20),),
        quotes=(_quote(MINT, T0 + 6_000),),
    )
    assert "tp1" in n6.next_state.managed_positions[0].exit_state.completed_take_profit_levels
    assert _open_position(n6.next_state).quantity == pytest.approx(200.0)

    # N+7/N+8: global halt exit attempt fails after submission and books network cost.
    n7 = _run(
        n6.next_state,
        T0 + 7_000,
        observations=(_observation(n6.next_state, T0 + 7_000, price=1.15, global_halt=True),),
    )
    cash_before_fail = n7.next_state.ledger.cash_balance_usd
    n8 = _run(
        n7.next_state,
        T0 + 8_000,
        observations=(_observation(n7.next_state, T0 + 8_000, price=1.15),),
        quotes=(
            _quote(
                MINT,
                T0 + 8_000,
                state=PaperQuoteState.FAILED_AFTER_SUBMISSION,
            ),
        ),
    )
    assert n8.exit_results[0].execution.findings[0].code is PaperExecutionReasonCode.SIMULATED_SUBMISSION_FAILED
    assert n8.next_state.ledger.cash_balance_usd == pytest.approx(
        cash_before_fail - _paper_policy().network_fee_usd
    )
    assert n8.next_state.managed_positions[0].pending_exit is None

    # N+9/N+10: fresh emergency decision gets its own latency clock, then closes.
    n9 = _run(
        n8.next_state,
        T0 + 9_000,
        observations=(_observation(n8.next_state, T0 + 9_000, price=1.15, global_halt=True),),
    )
    n10 = _run(
        n9.next_state,
        T0 + 10_000,
        quotes=(_quote(MINT, T0 + 10_000, price=1.10),),
    )
    assert n10.exit_results[0].reason is PaperLoopReasonCode.EXIT_POSITION_CLOSED
    assert not n10.next_state.managed_positions
    assert n10.next_state.ledger.unrealized_pnl_usd == pytest.approx(0.0)
    assert all(p.state is PaperPositionState.CLOSED for p in n10.next_state.ledger.positions)
    assert n10.next_state.ledger.processed_intent_keys == frozenset(
        entry.intent_idempotency_key for entry in n10.next_state.ledger.entries
    )
    assert math.isfinite(n10.next_state.ledger.realized_pnl_usd)
    assert math.isfinite(n10.next_state.ledger.accumulated_costs_usd)
    assert all(
        entry.side in (TradeSide.BUY, TradeSide.SELL)
        for entry in n10.next_state.ledger.entries
    )


def test_replaying_terminal_entry_cycle_against_next_state_cannot_double_book() -> None:
    state = create_paper_loop_state(
        create_paper_ledger(10_000.0, T0),
        PaperLoopPolicy("loop-v1-test", 300),
        PaperFillPolicy("paper-zero", 0, 5_000, 30, 0.01, True, 0.10),
    )
    candidate = _candidate(T0)
    quote = _quote(MINT, T0)
    first = _run(state, T0, candidates=(candidate,), quotes=(quote,))
    entries_after_first = len(first.next_state.ledger.entries)
    assert entries_after_first == 1

    replay = _run(first.next_state, T0, candidates=(candidate,), quotes=(quote,))
    assert len(replay.next_state.ledger.entries) == entries_after_first
    assert replay.entry_results[0].reason is PaperLoopReasonCode.ENTRY_OPEN_POSITION_EXISTS


def _manual_buy(ledger, mint: str, at: int):
    intent = TradeIntent(
        mint=mint,
        side=TradeSide.BUY,
        requested_notional_usd=200.0,
        max_slippage_bps=300,
        strategy_name=FRESH_LAUNCH_SETUP_NAME,
        strategy_version="fresh-v1-test",
        score_policy_version="score-v1-test",
        decision_policy_version="decision-v1-test",
        risk_policy_version="risk-v1-test",
        reason="ENTRY_APPROVED",
        idempotency_key=f"open-{mint}",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=at,
    )
    policy = PaperFillPolicy("manual-paper", 0, 5_000, 0, 0.0, True, 0.10)
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(at, ledger.processed_intent_keys, _quote(mint, at)),
        policy,
    )
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    return update.ledger


def test_two_open_positions_are_both_monitored_and_marked_in_one_cycle() -> None:
    ledger = create_paper_ledger(10_000.0, T0 - 10_000)
    ledger = _manual_buy(ledger, "MintA", T0 - 9_000)
    ledger = _manual_buy(ledger, "MintB", T0 - 8_000)
    policy = _exit_policy()
    managed = tuple(
        ManagedPaperPosition(
            position.position_id,
            policy,
            create_exit_state(position, policy),
        )
        for position in ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    state = create_paper_loop_state(
        ledger,
        PaperLoopPolicy("loop-v1-test", 300),
        PaperFillPolicy("manual-paper", 0, 5_000, 0, 0.0, True, 0.10),
        managed_positions=managed,
    )
    observations = tuple(
        PaperExitObservation(
            m.position_id,
            _features(T0, price=1.10),
            ExitExecutionContext(
                T0,
                T0,
                ExitRouteState.AVAILABLE,
                None,
                None,
                None,
                None,
                False,
            ),
        )
        for m in state.managed_positions
    )
    result = _run(state, T0, observations=observations)
    assert len(result.exit_results) == 2
    assert all(item.reason is PaperLoopReasonCode.EXIT_HOLD for item in result.exit_results)
    open_positions = [p for p in result.next_state.ledger.positions if p.state is PaperPositionState.OPEN]
    assert len(open_positions) == 2
    assert all(p.last_mark_price_usd == pytest.approx(1.10) for p in open_positions)
