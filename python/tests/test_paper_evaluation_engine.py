from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.decision import DecisionPolicy, SetupDecisionRule
from shreks_brain.exits import ExitPolicy, TakeProfitLevel
from shreks_brain.features import FeatureVector
from shreks_brain.paper import (
    PaperExecutionState,
    PaperFillPolicy,
    PaperQuote,
    PaperQuoteState,
    create_paper_ledger,
)
from shreks_brain.paper_evaluation.engine import extract_paper_evaluation_evidence
from shreks_brain.paper_loop import (
    FreshLaunchSetupInput,
    PaperCycleInput,
    PaperEntryCandidate,
    PaperLoopPolicy,
    create_paper_loop_state,
    run_paper_cycle,
)
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.registry import (
    CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
    RegistryCandidate,
    RegistryEvaluationEvidence,
    RegistryStatus,
)
from shreks_brain.risk import RiskContext, RiskPolicy
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import FRESH_LAUNCH_SETUP_NAME, FreshLaunchPolicy


AS_OF = 1_310_000
CANDIDATE_SHA = "a" * 64


def _features(**overrides: object) -> FeatureVector:
    values: dict[str, object] = dict(
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
    return FeatureVector(**values)  # type: ignore[arg-type]


def _regime(**overrides: object) -> RegimeAssessment:
    values: dict[str, object] = dict(
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
    return RegimeAssessment(**values)  # type: ignore[arg-type]


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
            SetupDecisionRule(FRESH_LAUNCH_SETUP_NAME, True, 70.0, 70.0, 80.0),
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


def _risk_context(**overrides: object) -> RiskContext:
    values: dict[str, object] = dict(
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
    return RiskContext(**values)  # type: ignore[arg-type]


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


def _entry_candidate(mint: str, **overrides: object) -> PaperEntryCandidate:
    values: dict[str, object] = dict(
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
    return PaperEntryCandidate(**values)  # type: ignore[arg-type]


def _quote(
    mint: str,
    *,
    observed_at: int = AS_OF,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
) -> PaperQuote:
    return PaperQuote(
        provider="paper-test",
        mint=mint,
        observed_at_unix_ms=observed_at,
        state=state,
        reference_price_usd=1.0,
        execution_price_usd=1.0,
        quoted_notional_usd=1_000.0,
        available_notional_usd=1_000.0,
    )


def _empty_state(*, latency_ms: int = 0):
    return create_paper_loop_state(
        create_paper_ledger(10_000.0, AS_OF - 1_000),
        PaperLoopPolicy("loop-v1-test", 250),
        _paper_policy(latency_ms=latency_ms),
    )


def _registry_candidate(*, strategy_version: str = "fresh-v1-test") -> RegistryCandidate:
    return RegistryCandidate(
        schema_version=CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
        candidate_version="candidate-v1",
        strategy_version=strategy_version,
        model_version=None,
        model_training_schema_version=None,
        model_training_fingerprint_sha256=None,
        feature_schema_version="b2-v1",
        feature_columns=("price_usd",),
        training_started_at_unix_ms=None,
        training_ended_at_unix_ms=None,
        validation_schema_version=None,
        validation_policy_version=None,
        validation_run_fingerprint_sha256=None,
        evaluation=RegistryEvaluationEvidence(
            schema_version="e5-trading-evaluation-v1",
            policy_version="eval-v1",
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
        candidate_fingerprint_sha256=CANDIDATE_SHA,
    )


def test_extract_immediate_fill_captures_entry_and_exact_fill_provenance() -> None:
    result = run_paper_cycle(
        _empty_state(),
        PaperCycleInput(
            AS_OF,
            (_entry_candidate("MintFilled"),),
            (),
            (_quote("MintFilled"),),
        ),
    )
    capture = extract_paper_evaluation_evidence("run-1", _registry_candidate(), result)

    assert len(capture.entry_provenance) == 1
    assert len(capture.executions) == 1
    assert capture.closures == ()
    assert capture.orphan_costs == ()

    provenance = capture.entry_provenance[0]
    execution = capture.executions[0]
    assert provenance.setup_name == FRESH_LAUNCH_SETUP_NAME
    assert provenance.market_regime is MarketRegime.NORMAL
    assert provenance.strategy_version == "fresh-v1-test"
    assert execution.position_id == result.entry_results[0].ledger_update.position_id
    assert execution.execution_state is PaperExecutionState.FILLED
    assert execution.reference_price_usd == pytest.approx(1.0)
    assert execution.execution_price_usd == pytest.approx(1.0)
    assert execution.signed_slippage_usd == pytest.approx(0.0)
    assert execution.quote_provider == "paper-test"
    assert execution.explicit_cost_usd == pytest.approx(
        result.entry_results[0].execution.explicit_cost_usd
    )


def test_extract_original_deferred_entry_captures_provenance_without_economics() -> None:
    result = run_paper_cycle(
        _empty_state(latency_ms=1_000),
        PaperCycleInput(AS_OF, (_entry_candidate("MintPending"),), (), ()),
    )
    assert result.entry_results[0].execution.state is PaperExecutionState.DEFERRED

    capture = extract_paper_evaluation_evidence("run-1", _registry_candidate(), result)
    assert len(capture.entry_provenance) == 1
    assert capture.executions == ()
    assert capture.closures == ()
    assert capture.orphan_costs == ()


def test_extract_later_pending_fill_does_not_invent_lost_setup_or_regime() -> None:
    first = run_paper_cycle(
        _empty_state(latency_ms=1_000),
        PaperCycleInput(AS_OF, (_entry_candidate("MintPending"),), (), ()),
    )
    retry_at = AS_OF + 1_000
    second = run_paper_cycle(
        first.next_state,
        PaperCycleInput(
            retry_at,
            (),
            (),
            (_quote("MintPending", observed_at=retry_at),),
        ),
    )
    assert second.pending_entry_result is not None
    assert second.pending_entry_result.execution.state is PaperExecutionState.FILLED

    capture = extract_paper_evaluation_evidence("run-1", _registry_candidate(), second)
    assert capture.entry_provenance == ()
    assert len(capture.executions) == 1
    assert capture.executions[0].intent_idempotency_key == (
        second.pending_entry_result.intent_idempotency_key
    )


def test_extract_failed_entry_submission_preserves_orphan_network_cost() -> None:
    result = run_paper_cycle(
        _empty_state(),
        PaperCycleInput(
            AS_OF,
            (_entry_candidate("MintFailed"),),
            (),
            (_quote("MintFailed", state=PaperQuoteState.FAILED_AFTER_SUBMISSION),),
        ),
    )
    entry = result.entry_results[0]
    assert entry.execution is not None
    assert entry.execution.state is PaperExecutionState.FAILED
    assert entry.execution.explicit_cost_usd == pytest.approx(0.01)

    capture = extract_paper_evaluation_evidence("run-1", _registry_candidate(), result)
    assert len(capture.entry_provenance) == 1
    assert capture.executions == ()
    assert capture.closures == ()
    assert len(capture.orphan_costs) == 1
    assert capture.orphan_costs[0].explicit_cost_usd == pytest.approx(0.01)


def test_extract_unselected_candidate_emits_no_entry_evidence() -> None:
    weak = _entry_candidate("MintWatch", features=_features(buy_fraction_m5=0.10))
    result = run_paper_cycle(
        _empty_state(),
        PaperCycleInput(AS_OF, (weak,), (), ()),
    )
    assert result.entry_results[0].selected_for_entry is False

    capture = extract_paper_evaluation_evidence("run-1", _registry_candidate(), result)
    assert capture.entry_provenance == ()
    assert capture.executions == ()
    assert capture.orphan_costs == ()


def test_extract_fails_closed_on_registry_strategy_mismatch() -> None:
    result = run_paper_cycle(
        _empty_state(),
        PaperCycleInput(
            AS_OF,
            (_entry_candidate("MintFilled"),),
            (),
            (_quote("MintFilled"),),
        ),
    )
    with pytest.raises(ValueError, match="strategy"):
        extract_paper_evaluation_evidence(
            "run-1",
            _registry_candidate(strategy_version="different-strategy"),
            result,
        )
