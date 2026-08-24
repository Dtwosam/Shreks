from dataclasses import replace

import pytest

from shreks_brain.decision import DecisionPolicy, SetupDecisionRule
from shreks_brain.exits import ExitPolicy, TakeProfitLevel, create_exit_state
from shreks_brain.features import FeatureVector
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedgerUpdateState,
    PaperQuote,
    PaperQuoteState,
    PaperPositionState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
)
from shreks_brain.paper_loop.engine import create_paper_loop_state, run_paper_cycle
from shreks_brain.paper_loop.models import (
    FirstPullbackSetupInput,
    FreshLaunchSetupInput,
    GraduationBreakoutSetupInput,
    ManagedPaperPosition,
    PaperCycleInput,
    PaperEntryCandidate,
    PaperLoopPolicy,
    PaperLoopReasonCode,
)
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.risk import (
    RiskContext,
    RiskPolicy,
    RiskState,
    TradeIntent,
    TradeSide,
)
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import (
    FIRST_PULLBACK_SETUP_NAME,
    FRESH_LAUNCH_SETUP_NAME,
    GRADUATION_BREAKOUT_SETUP_NAME,
    FirstPullbackAssessment,
    FirstPullbackPolicy,
    FreshLaunchAssessment,
    FreshLaunchPolicy,
    GraduationBreakoutAssessment,
    GraduationBreakoutPolicy,
    GraduationContext,
    PullbackContext,
    SetupState,
)


AS_OF = 1_310_000


def _features(**overrides) -> FeatureVector:
    values = dict(
        schema_version="b2-v1",
        as_of_unix_ms=AS_OF,
        source_observed_at_unix_ms=AS_OF - 1_000,
        source_age_ms=1_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=300.0,
        price_usd=1.0,
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
    values.update(overrides)
    return FeatureVector(**values)


def _regime(**overrides) -> RegimeAssessment:
    values = dict(
        policy_version="regime-v1-test",
        as_of_unix_ms=AS_OF,
        source_observed_at_unix_ms=AS_OF - 1_000,
        window_started_at_unix_ms=AS_OF - 360_000,
        source_age_ms=1_000,
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
    values.update(overrides)
    return RegimeAssessment(**values)


def _fresh_policy() -> FreshLaunchPolicy:
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


def _graduation_policy() -> GraduationBreakoutPolicy:
    return GraduationBreakoutPolicy(
        version="graduation-v1-test",
        min_seconds_since_graduation=30.0,
        max_seconds_since_graduation=900.0,
        max_source_age_ms=30_000,
        min_liquidity_usd=50_000.0,
        max_exit_price_impact_pct=5.0,
        min_tx_count_m5=50,
        min_volume_velocity_ratio=1.2,
        min_buy_fraction_m5=0.60,
        min_buy_pressure_acceleration=0.05,
        min_return_1m_pct=1.0,
        max_return_1m_pct=40.0,
        min_liquidity_change_5m_pct=0.0,
        min_distance_from_local_high_pct=-15.0,
        min_range_position_pct=60.0,
    )


def _graduation(mint: str) -> GraduationContext:
    return GraduationContext(
        event_type="pump_graduation",
        provider="helius",
        mint=mint,
        quote_mint="So11111111111111111111111111111111111111112",
        from_venue="pump_fun_bonding_curve",
        to_venue="pump_swap",
        pool_address=f"pool-{mint}",
        signature=f"sig-{mint}",
        slot=123,
        detected_at_unix_ms=AS_OF - 100_000,
        occurred_at_unix_ms=AS_OF - 101_000,
    )


def _pullback_policy() -> FirstPullbackPolicy:
    return FirstPullbackPolicy(
        version="pullback-v1-test",
        min_seconds_since_trough=15.0,
        max_seconds_since_trough=600.0,
        max_source_age_ms=30_000,
        min_structure_samples=5,
        min_initial_impulse_pct=20.0,
        min_pullback_depth_pct=8.0,
        max_pullback_depth_pct=35.0,
        min_recovery_from_trough_pct=5.0,
        min_current_vs_peak_pct=-10.0,
        max_current_vs_peak_pct=10.0,
        min_liquidity_retention_pct=70.0,
        min_liquidity_usd=50_000.0,
        max_exit_price_impact_pct=5.0,
        min_tx_count_m5=50,
        min_volume_velocity_ratio=1.2,
        min_buy_fraction_m5=0.60,
        min_buy_fraction_improvement=0.10,
        min_buy_pressure_acceleration=0.05,
        min_return_1m_pct=1.0,
        max_return_1m_pct=30.0,
    )


def _pullback() -> PullbackContext:
    return PullbackContext(
        impulse_started_at_unix_ms=AS_OF - 310_000,
        peak_at_unix_ms=AS_OF - 190_000,
        trough_at_unix_ms=AS_OF - 70_000,
        impulse_start_price_usd=1.0,
        peak_price_usd=1.5,
        trough_price_usd=1.2,
        peak_liquidity_usd=100_000.0,
        trough_liquidity_usd=80_000.0,
        trough_buy_fraction_m5=0.40,
        sample_count=8,
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
            SetupDecisionRule(FRESH_LAUNCH_SETUP_NAME, True, 70.0, 70.0, 80.0),
            SetupDecisionRule(GRADUATION_BREAKOUT_SETUP_NAME, True, 70.0, 70.0, 80.0),
            SetupDecisionRule(FIRST_PULLBACK_SETUP_NAME, True, 70.0, 70.0, 80.0),
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


def _risk_context(**overrides) -> RiskContext:
    values = dict(
        as_of_unix_ms=AS_OF,
        trading_capital_usd=10_000.0,
        open_position_count=0,
        aggregate_open_risk_usd=0.0,
        daily_realized_pnl_usd=0.0,
        rolling_drawdown_pct=0.0,
        consecutive_losses=0,
        last_loss_at_unix_ms=None,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=2.0,
        price_impact_notional_usd=5_000.0,
        market_data_age_ms=1_000,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )
    values.update(overrides)
    return RiskContext(**values)


def _exit_policy() -> ExitPolicy:
    return ExitPolicy(
        version="exit-v1-test",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(TakeProfitLevel("tp1", 20.0, 0.5),),
        trailing_activation_return_pct=15.0,
        trailing_stop_drawdown_pct=8.0,
        max_hold_seconds=1_800,
        flow_exit_max_buy_fraction_m5=0.40,
        flow_exit_max_buy_pressure_acceleration=-0.10,
        momentum_exit_max_return_1m_pct=-5.0,
        momentum_exit_max_return_5m_pct=-8.0,
        min_liquidity_usd=10_000.0,
        max_exit_price_impact_pct=8.0,
        min_exit_capacity_fraction=0.50,
        wallet_distribution_enabled=False,
    )


def _paper_policy(*, latency_ms: int = 0) -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-v1-test",
        assumed_latency_ms=latency_ms,
        max_quote_lag_ms=5_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.10,
    )


def _setup(kind: str, mint: str):
    if kind == "fresh":
        return FreshLaunchSetupInput(_fresh_policy())
    if kind == "graduation":
        return GraduationBreakoutSetupInput(_graduation(mint), _graduation_policy())
    if kind == "pullback":
        return FirstPullbackSetupInput(_pullback(), _pullback_policy())
    raise AssertionError(kind)


def _features_for(kind: str, **overrides) -> FeatureVector:
    base = dict()
    if kind == "pullback":
        base.update(
            price_usd=1.44,
            liquidity_change_5m_pct=5.0,
            buy_fraction_m5=0.65,
            buy_fraction_h1=0.55,
            buy_sell_ratio_m5=1.857142857,
            buy_sell_ratio_h1=1.222222222,
            buy_pressure_acceleration=0.10,
            return_5m_pct=-5.0,
            momentum_acceleration_1m_vs_5m=5.0,
            distance_from_local_high_pct=-4.0,
            range_position_pct=80.0,
        )
    base.update(overrides)
    return _features(**base)


def _candidate(mint: str, kind: str = "fresh", **overrides) -> PaperEntryCandidate:
    values = dict(
        mint=mint,
        features=_features_for(kind),
        regime=_regime(),
        setup=_setup(kind, mint),
        score_policy=_score_policy(),
        decision_policy=_decision_policy(),
        risk_context=_risk_context(),
        risk_policy=_risk_policy(),
        exit_policy=_exit_policy(),
    )
    values.update(overrides)
    return PaperEntryCandidate(**values)


def _quote(mint: str, *, observed_at: int = AS_OF, price: float = 1.0) -> PaperQuote:
    return PaperQuote(
        provider="paper-test",
        mint=mint,
        observed_at_unix_ms=observed_at,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=price,
        execution_price_usd=price,
        quoted_notional_usd=1_000.0,
        available_notional_usd=1_000.0,
    )


def _empty_state(*, latency_ms: int = 0, at: int = AS_OF - 1_000):
    return create_paper_loop_state(
        create_paper_ledger(10_000.0, at),
        PaperLoopPolicy("loop-v1-test", 250),
        _paper_policy(latency_ms=latency_ms),
    )


def _open_state(mint: str = "MintOpen"):
    started = AS_OF - 10_000
    ledger = create_paper_ledger(10_000.0, started)
    intent = TradeIntent(
        mint=mint,
        side=TradeSide.BUY,
        requested_notional_usd=500.0,
        max_slippage_bps=300,
        strategy_name=FRESH_LAUNCH_SETUP_NAME,
        strategy_version="fresh-v1-test",
        score_policy_version="score-v1-test",
        decision_policy_version="decision-v1-test",
        risk_policy_version="risk-v1-test",
        reason="ENTRY_APPROVED",
        idempotency_key=f"open-{mint}",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=started,
    )
    quote = _quote(mint, observed_at=started, price=1.0)
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(started, ledger.processed_intent_keys, quote),
        _paper_policy(),
    )
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    position = next(p for p in update.ledger.positions if p.state is PaperPositionState.OPEN)
    managed = ManagedPaperPosition(
        position.position_id,
        _exit_policy(),
        create_exit_state(position, _exit_policy()),
    )
    return create_paper_loop_state(
        update.ledger,
        PaperLoopPolicy("loop-v1-test", 250),
        _paper_policy(),
        (managed,),
    )


def test_create_state_pins_policies_and_uses_latest_authoritative_time():
    state = _empty_state(at=AS_OF - 2_000)
    assert state.loop_policy.version == "loop-v1-test"
    assert state.paper_fill_policy.version == "paper-v1-test"
    assert state.last_cycle_at_unix_ms == AS_OF - 2_000
    assert state.pending_entry is None
    assert state.managed_positions == ()


def test_cycle_before_state_returns_exact_previous_state_without_processing():
    state = _empty_state(at=AS_OF)
    cycle = PaperCycleInput(AS_OF - 1, (), (), ())
    result = run_paper_cycle(state, cycle)
    assert result.next_state is state
    assert result.findings[0].code is PaperLoopReasonCode.CYCLE_BEFORE_STATE
    assert result.entry_results == ()
    assert result.exit_results == ()
    assert result.pending_entry_result is None


@pytest.mark.parametrize(
    ("kind", "assessment_type"),
    [
        ("fresh", FreshLaunchAssessment),
        ("graduation", GraduationBreakoutAssessment),
        ("pullback", FirstPullbackAssessment),
    ],
)
def test_all_three_setup_wrappers_dispatch_to_existing_setup_engines(kind, assessment_type):
    mint = f"Mint-{kind}"
    state = _empty_state()
    cycle = PaperCycleInput(AS_OF, (_candidate(mint, kind),), (), (_quote(mint),))
    result = run_paper_cycle(state, cycle)
    entry = result.entry_results[0]
    assert isinstance(entry.setup_assessment, assessment_type)
    assert entry.setup_assessment.state is SetupState.READY
    assert entry.selected_for_entry is True
    assert entry.risk_assessment is not None
    assert entry.risk_assessment.state is RiskState.APPROVED


def test_watch_candidate_never_creates_buy_intent_and_risk_rejects_it():
    state = _empty_state()
    candidate = _candidate(
        "MintWatch",
        features=_features(buy_fraction_m5=0.10),
    )
    result = run_paper_cycle(
        state,
        PaperCycleInput(AS_OF, (candidate,), (), (_quote("MintWatch"),)),
    )
    entry = result.entry_results[0]
    assert entry.setup_assessment.state is SetupState.WATCH
    assert entry.selected_for_entry is False
    assert entry.risk_assessment is not None
    assert entry.risk_assessment.state is RiskState.REJECTED
    assert entry.execution is None
    assert entry.reason is PaperLoopReasonCode.ENTRY_RISK_REJECTED


def test_risk_rejection_continues_to_next_candidate():
    first = _candidate(
        "MintKilled",
        risk_context=_risk_context(kill_switch_active=True),
    )
    second = _candidate("MintChosen")
    state = _empty_state()
    result = run_paper_cycle(
        state,
        PaperCycleInput(AS_OF, (first, second), (), (_quote("MintChosen"),)),
    )
    assert result.entry_results[0].reason is PaperLoopReasonCode.ENTRY_RISK_REJECTED
    assert result.entry_results[0].selected_for_entry is False
    assert result.entry_results[1].selected_for_entry is True
    assert result.entry_results[1].execution is not None


def test_first_risk_approved_candidate_consumes_only_entry_slot_but_later_is_audited():
    first = _candidate("MintFirst")
    second = _candidate("MintSecond")
    state = _empty_state()
    result = run_paper_cycle(
        state,
        PaperCycleInput(AS_OF, (first, second), (), (_quote("MintFirst"),)),
    )
    a, b = result.entry_results
    assert a.selected_for_entry is True
    assert a.risk_assessment is not None and a.risk_assessment.state is RiskState.APPROVED
    assert b.setup_assessment.state is SetupState.READY
    assert b.score_assessment.total_score is not None
    assert b.decision.action.value == "ENTER"
    assert b.risk_assessment is None
    assert b.selected_for_entry is False
    assert b.reason is PaperLoopReasonCode.ENTRY_NOT_SELECTED


def test_existing_open_mint_skips_risk_and_never_pyramids():
    state = _open_state("MintOpen")
    candidate = _candidate(
        "MintOpen",
        risk_context=_risk_context(open_position_count=1, aggregate_open_risk_usd=500.0),
    )
    result = run_paper_cycle(state, PaperCycleInput(AS_OF, (candidate,), (), ()))
    entry = result.entry_results[0]
    assert entry.risk_assessment is None
    assert entry.selected_for_entry is False
    assert entry.execution is None
    assert entry.reason is PaperLoopReasonCode.ENTRY_OPEN_POSITION_EXISTS
    open_position = next(p for p in result.next_state.ledger.positions if p.state is PaperPositionState.OPEN)
    assert open_position.quantity == pytest.approx(state.ledger.positions[0].quantity)


def test_nonempty_active_intent_context_is_rejected_by_c5_coherence_gate():
    candidate = _candidate(
        "MintContradictory",
        risk_context=_risk_context(active_intent_keys=frozenset({"not-owned-by-loop"})),
    )
    result = run_paper_cycle(
        _empty_state(),
        PaperCycleInput(AS_OF, (candidate,), (), ()),
    )
    entry = result.entry_results[0]
    assert entry.risk_assessment is None
    assert entry.selected_for_entry is False
    assert entry.reason is PaperLoopReasonCode.ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH


def test_immediate_terminal_buy_books_through_c1_c3_and_initializes_c4_state():
    state = _empty_state()
    result = run_paper_cycle(
        state,
        PaperCycleInput(
            AS_OF,
            (_candidate("MintFilled"),),
            (),
            (_quote("MintFilled"),),
        ),
    )
    entry = result.entry_results[0]
    assert entry.selected_for_entry is True
    assert entry.execution is not None
    assert entry.execution.state is PaperExecutionState.FILLED
    assert entry.ledger_update is not None
    assert entry.ledger_update.state is PaperLedgerUpdateState.APPLIED
    assert result.next_state.pending_entry is None
    assert len(result.next_state.managed_positions) == 1
    managed = result.next_state.managed_positions[0]
    position = next(
        p for p in result.next_state.ledger.positions if p.position_id == managed.position_id
    )
    assert position.state is PaperPositionState.OPEN
    assert managed.exit_state.position_id == position.position_id
    assert managed.exit_state.mint == position.mint
    assert managed.exit_state.initialized_at_unix_ms == position.opened_at_unix_ms
    assert result.exit_results == ()


def test_deferred_buy_is_persisted_with_its_exit_policy():
    state = _empty_state(latency_ms=1_000)
    result = run_paper_cycle(
        state,
        PaperCycleInput(AS_OF, (_candidate("MintPending"),), (), ()),
    )
    entry = result.entry_results[0]
    assert entry.selected_for_entry is True
    assert entry.execution is not None
    assert entry.execution.state is PaperExecutionState.DEFERRED
    assert entry.reason is PaperLoopReasonCode.ENTRY_EXECUTION_DEFERRED
    assert result.next_state.pending_entry is not None
    assert result.next_state.pending_entry.intent == entry.risk_assessment.intent
    assert result.next_state.pending_entry.exit_policy == _exit_policy()
    assert result.next_state.ledger is state.ledger


def test_pending_buy_retry_deferred_preserves_exact_intent():
    first = run_paper_cycle(
        _empty_state(latency_ms=1_000),
        PaperCycleInput(AS_OF, (_candidate("MintPending"),), (), ()),
    )
    pending = first.next_state.pending_entry
    assert pending is not None
    retry_at = AS_OF + 500
    second = run_paper_cycle(
        first.next_state,
        PaperCycleInput(retry_at, (), (), ()),
    )
    assert second.pending_entry_result is not None
    assert second.pending_entry_result.execution.state is PaperExecutionState.DEFERRED
    assert second.pending_entry_result.reason is PaperLoopReasonCode.PENDING_ENTRY_DEFERRED
    assert second.next_state.pending_entry == pending


def test_pending_buy_retry_terminal_books_and_consumes_cycle_entry_slot():
    first = run_paper_cycle(
        _empty_state(latency_ms=1_000),
        PaperCycleInput(AS_OF, (_candidate("MintPending"),), (), ()),
    )
    pending = first.next_state.pending_entry
    assert pending is not None
    retry_at = AS_OF + 1_000
    later_candidate = _candidate(
        "MintLater",
        features=_features(as_of_unix_ms=retry_at, source_observed_at_unix_ms=retry_at - 1_000),
        regime=_regime(
            as_of_unix_ms=retry_at,
            source_observed_at_unix_ms=retry_at - 1_000,
            window_started_at_unix_ms=retry_at - 360_000,
        ),
        risk_context=_risk_context(as_of_unix_ms=retry_at),
    )
    second = run_paper_cycle(
        first.next_state,
        PaperCycleInput(
            retry_at,
            (later_candidate,),
            (),
            (_quote("MintPending", observed_at=retry_at),),
        ),
    )
    assert second.pending_entry_result is not None
    assert second.pending_entry_result.reason is PaperLoopReasonCode.PENDING_ENTRY_TERMINAL
    assert second.pending_entry_result.execution.state is PaperExecutionState.FILLED
    assert second.pending_entry_result.ledger_update is not None
    assert second.next_state.pending_entry is None
    assert len(second.next_state.managed_positions) == 1
    assert second.entry_results[0].risk_assessment is None
    assert second.entry_results[0].reason is PaperLoopReasonCode.ENTRY_NOT_SELECTED


def test_newly_opened_position_is_not_monitored_in_same_cycle():
    result = run_paper_cycle(
        _empty_state(),
        PaperCycleInput(
            AS_OF,
            (_candidate("MintNew"),),
            (),
            (_quote("MintNew"),),
        ),
    )
    assert len(result.next_state.managed_positions) == 1
    assert result.exit_results == ()
    assert result.findings[0].code is PaperLoopReasonCode.CYCLE_APPLIED
