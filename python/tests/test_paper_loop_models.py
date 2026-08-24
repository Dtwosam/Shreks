from dataclasses import fields, replace

import pytest

from shreks_brain.decision import DecisionPolicy, SetupDecisionRule
from shreks_brain.exits import ExitExecutionContext, ExitPolicy, ExitRouteState, TakeProfitLevel
from shreks_brain.features import FeatureVector
from shreks_brain.paper import PaperFillPolicy, PaperQuote, PaperQuoteState, create_paper_ledger
from shreks_brain.paper_loop.models import (
    FirstPullbackSetupInput,
    FreshLaunchSetupInput,
    GraduationBreakoutSetupInput,
    ManagedPaperPosition,
    PaperCycleInput,
    PaperEntryCandidate,
    PaperExitObservation,
    PaperLoopFinding,
    PaperLoopPolicy,
    PaperLoopReasonCode,
    PaperLoopState,
    PendingPaperEntry,
)
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.risk import RiskContext, RiskPolicy, TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import (
    FRESH_LAUNCH_SETUP_NAME,
    FirstPullbackPolicy,
    FreshLaunchPolicy,
    GraduationBreakoutPolicy,
)


AS_OF = 1_000_000


def _features(mint_seed: int = 1, **overrides) -> FeatureVector:
    values = dict(
        schema_version="b2-v1",
        as_of_unix_ms=AS_OF,
        source_observed_at_unix_ms=AS_OF - 1_000,
        source_age_ms=1_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=300.0,
        price_usd=1.0 + mint_seed * 0.01,
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
                setup_name=FRESH_LAUNCH_SETUP_NAME,
                enabled=True,
                hot_min_score=70.0,
                normal_min_score=70.0,
                weak_min_score=80.0,
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


def _candidate(mint: str = "Mint111", **overrides) -> PaperEntryCandidate:
    values = dict(
        mint=mint,
        features=_features(),
        regime=_regime(),
        setup=FreshLaunchSetupInput(_fresh_policy()),
        score_policy=_score_policy(),
        decision_policy=_decision_policy(),
        risk_context=_risk_context(),
        risk_policy=_risk_policy(),
        exit_policy=_exit_policy(),
    )
    values.update(overrides)
    return PaperEntryCandidate(**values)


def _quote(mint: str = "Mint111") -> PaperQuote:
    return PaperQuote(
        provider="paper-test",
        mint=mint,
        observed_at_unix_ms=AS_OF,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=1.0,
        execution_price_usd=1.0,
        quoted_notional_usd=1_000.0,
        available_notional_usd=1_000.0,
    )


def _exit_observation(position_id: str = "position-1") -> PaperExitObservation:
    return PaperExitObservation(
        position_id=position_id,
        features=_features(),
        execution_context=ExitExecutionContext(
            as_of_unix_ms=AS_OF,
            observed_at_unix_ms=AS_OF - 100,
            route_state=ExitRouteState.AVAILABLE,
            available_exit_notional_usd=1_000.0,
            expected_exit_price_impact_pct=2.0,
            price_impact_notional_usd=500.0,
            wallet_distribution_detected=None,
            global_halt_active=False,
        ),
    )


def _buy_intent(**overrides) -> TradeIntent:
    values = dict(
        mint="Mint111",
        side=TradeSide.BUY,
        requested_notional_usd=500.0,
        max_slippage_bps=300,
        strategy_name=FRESH_LAUNCH_SETUP_NAME,
        strategy_version="fresh-v1-test",
        score_policy_version="score-v1-test",
        decision_policy_version="decision-v1-test",
        risk_policy_version="risk-v1-test",
        reason="ENTRY_APPROVED",
        idempotency_key="entry-key",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=AS_OF,
    )
    values.update(overrides)
    return TradeIntent(**values)


def _paper_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-v1-test",
        assumed_latency_ms=0,
        max_quote_lag_ms=5_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.10,
    )


def test_reason_code_order_and_policy_has_no_defaults():
    assert [code.value for code in PaperLoopReasonCode] == [
        "CYCLE_APPLIED",
        "CYCLE_BEFORE_STATE",
        "PENDING_ENTRY_DEFERRED",
        "PENDING_ENTRY_TERMINAL",
        "ENTRY_NOT_SELECTED",
        "ENTRY_OPEN_POSITION_EXISTS",
        "ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH",
        "ENTRY_RISK_REJECTED",
        "ENTRY_EXECUTION_DEFERRED",
        "ENTRY_EXECUTION_TERMINAL",
        "EXIT_OBSERVATION_MISSING",
        "EXIT_HOLD",
        "EXIT_QUOTE_MISSING",
        "EXIT_QUOTE_AFTER_CYCLE",
        "EXIT_QUOTE_BEFORE_LATENCY",
        "EXIT_EXECUTION_PRICE_UNAVAILABLE",
        "EXIT_EXECUTION_TERMINAL",
        "EXIT_POSITION_CLOSED",
    ]
    with pytest.raises(TypeError):
        PaperLoopPolicy()
    assert PaperLoopPolicy("loop-v1-test", 250).exit_max_slippage_bps == 250


def test_setup_wrappers_require_exact_existing_policy_types():
    assert FreshLaunchSetupInput(_fresh_policy()).policy.version == "fresh-v1-test"
    with pytest.raises(ValueError):
        FreshLaunchSetupInput("bad")
    with pytest.raises(ValueError):
        GraduationBreakoutSetupInput(None, "bad")
    with pytest.raises(ValueError):
        FirstPullbackSetupInput(None, "bad")


def test_entry_candidate_requires_cycle_domain_types():
    candidate = _candidate()
    assert candidate.mint == "Mint111"
    with pytest.raises(ValueError):
        replace(candidate, mint="")
    with pytest.raises(ValueError):
        replace(candidate, setup="bad")


def test_cycle_input_requires_unique_candidate_quote_and_exit_ids():
    candidate = _candidate()
    quote = _quote()
    observation = _exit_observation()

    with pytest.raises(ValueError, match="candidate"):
        PaperCycleInput(AS_OF, (candidate, candidate), (), ())
    with pytest.raises(ValueError, match="quote"):
        PaperCycleInput(AS_OF, (), (), (quote, quote))
    with pytest.raises(ValueError, match="exit observation"):
        PaperCycleInput(AS_OF, (), (observation, observation), ())


def test_cycle_input_requires_entry_evidence_at_cycle_timestamp():
    stale = _candidate(features=_features(as_of_unix_ms=AS_OF - 1))
    with pytest.raises(ValueError, match="candidate feature"):
        PaperCycleInput(AS_OF, (stale,), (), ())
    stale_regime = _candidate(regime=_regime(as_of_unix_ms=AS_OF - 1))
    with pytest.raises(ValueError, match="candidate regime"):
        PaperCycleInput(AS_OF, (stale_regime,), (), ())
    stale_risk = _candidate(risk_context=_risk_context(as_of_unix_ms=AS_OF - 1))
    with pytest.raises(ValueError, match="candidate risk"):
        PaperCycleInput(AS_OF, (stale_risk,), (), ())


def test_pending_entry_requires_paper_buy_intent():
    pending = PendingPaperEntry(_buy_intent(), _exit_policy())
    assert pending.intent.execution_mode is RuntimeMode.PAPER

    with pytest.raises(ValueError, match="PAPER BUY"):
        PendingPaperEntry(replace(_buy_intent(), side=TradeSide.SELL), _exit_policy())
    with pytest.raises(ValueError, match="PAPER BUY"):
        PendingPaperEntry(
            replace(_buy_intent(), execution_mode=RuntimeMode.SHADOW),
            _exit_policy(),
        )


def test_loop_state_requires_pinned_paper_mode_policies_and_exact_empty_coverage():
    ledger = create_paper_ledger(10_000.0, AS_OF)
    state = PaperLoopState(
        ledger=ledger,
        loop_policy=PaperLoopPolicy("loop-v1-test", 250),
        paper_fill_policy=_paper_policy(),
        managed_positions=(),
        pending_entry=None,
        last_cycle_at_unix_ms=AS_OF,
    )
    assert state.ledger is ledger

    with pytest.raises(ValueError, match="managed"):
        replace(
            state,
            managed_positions=(
                ManagedPaperPosition(
                    position_id="ghost",
                    exit_policy=_exit_policy(),
                    exit_state=None,
                ),
            ),
        )


def test_loop_finding_is_stable_and_public_models_have_no_live_authority_fields():
    finding = PaperLoopFinding(PaperLoopReasonCode.CYCLE_APPLIED, "cycle applied")
    assert finding.code is PaperLoopReasonCode.CYCLE_APPLIED

    public_models = (
        PaperLoopPolicy,
        FreshLaunchSetupInput,
        GraduationBreakoutSetupInput,
        FirstPullbackSetupInput,
        PaperEntryCandidate,
        PaperExitObservation,
        ManagedPaperPosition,
        PendingPaperEntry,
        PaperCycleInput,
        PaperLoopState,
    )
    forbidden = (
        "signer",
        "secret",
        "private_key",
        "transaction",
        "signature",
        "sqlite",
        "live_execution",
    )
    for model in public_models:
        names = " ".join(field.name for field in fields(model)).lower()
        assert not any(fragment in names for fragment in forbidden)
