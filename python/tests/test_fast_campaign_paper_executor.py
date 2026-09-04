from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_campaign.models import (
    FastCampaignActionCandidate,
    FastCampaignDecisionResult,
    FastCampaignDecisionResults,
)
from shreks_brain.fast_campaign_paper import (
    FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
    FastCampaignPaperCandidateIdentity,
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
    run_fast_campaign_paper_candidate,
)
from shreks_brain.fast_paper import (
    FastPaperBuyOutcome,
    FastPaperPositionActionPolicy,
    FastPaperPositionOutcome,
)
from shreks_brain.paper import (
    PaperFillPolicy,
    PaperPositionState,
    PaperQuoteState,
    create_paper_ledger,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext, RiskPolicy


T0 = 8_000_000
MINT = "mint-a"
QUOTE_MINT = "quote-a"
MARKET_KEY = "pump:mint-a:quote-a"


def _identity() -> FastCampaignPaperCandidateIdentity:
    return FastCampaignPaperCandidateIdentity(
        version=FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
        paper_run_id="paper-run-learned",
        candidate_version="learned-v1",
        candidate_fingerprint_sha256="a" * 64,
        strategy_family="fl9-continuous-action",
        strategy_version="fl9-v1",
        assessment_version="assessment-v1",
    )


def _candidate(action: str, horizon: int | None, target: float, value: float):
    return FastCampaignActionCandidate(
        action=action,
        horizon_ms=horizon,
        target_exposure_fraction=target,
        reward_bps=max(value, 0.0),
        risk_bps=0.0,
        execution_cost_penalty_bps=0.0,
        comparison_value_bps=value,
        eligible=True,
    )


def _decision(
    event: str,
    sequence: int,
    at: int,
    action: str,
    current: float,
    target: float,
) -> FastCampaignDecisionResult:
    return FastCampaignDecisionResult(
        source_event_id=event,
        market_key=MARKET_KEY,
        source_sequence=sequence,
        as_of_unix_ms=at,
        policy_version=1,
        action=action,
        reason=f"{action}_SELECTED",
        selected_horizon_ms=None if action in {"SKIP", "HOLD"} else 1_000,
        current_exposure_fraction=current,
        target_exposure_fraction=target,
        selected_reward_bps=100.0 if action == "BUY" else 0.0,
        selected_risk_bps=10.0 if action == "BUY" else 0.0,
        selected_execution_cost_bps=0.0,
        selected_value_bps=50.0 if action == "BUY" else 0.0,
        horizon_evidence=(),
        candidates=(_candidate(action, None, target, 0.0),),
    )


def _results(*decisions: FastCampaignDecisionResult) -> FastCampaignDecisionResults:
    return FastCampaignDecisionResults(
        schema_name="shreks.fast_campaign_decision_results",
        schema_version=1,
        champion_version="champion-v1",
        champion_fingerprint_sha256="b" * 64,
        decisions=decisions,
        batch_fingerprint_sha256="c" * 64,
    )


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-fixture-v1",
        assumed_latency_ms=0,
        max_quote_lag_ms=2_000,
        swap_fee_bps=50,
        network_fee_usd=0.05,
        allow_partial_fills=False,
        min_partial_fill_fraction=1.0,
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-fixture-v1",
        required_decision_policy_version="assessment-v1",
        required_feature_schema_version="state-v1",
        target_position_notional_usd=500.0,
        max_notional_per_position_usd=500.0,
        max_capital_fraction_per_position=1.0,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=5_000.0,
        max_daily_realized_loss_usd=5_000.0,
        max_rolling_drawdown_pct=100.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=0,
        min_liquidity_usd=0.0,
        max_expected_price_impact_pct=100.0,
        max_slippage_bps=1_000,
        max_market_data_age_ms=2_000,
    )


def _risk_context(at: int, *, kill: bool = False) -> RiskContext:
    return RiskContext(
        as_of_unix_ms=at,
        trading_capital_usd=20_000.0,
        open_position_count=0,
        aggregate_open_risk_usd=0.0,
        daily_realized_pnl_usd=0.0,
        rolling_drawdown_pct=0.0,
        consecutive_losses=0,
        last_loss_at_unix_ms=None,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=0.0,
        price_impact_notional_usd=10_000.0,
        market_data_age_ms=0,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=kill,
        active_intent_keys=frozenset(),
    )


def _evaluation_policy() -> TradingEvaluationPolicy:
    return TradingEvaluationPolicy(
        version="paper-eval-v1",
        starting_equity_usd=20_000.0,
        calibration_bucket_count=10,
    )


def _position_policy() -> FastPaperPositionActionPolicy:
    return FastPaperPositionActionPolicy(
        version="position-fixture-v1",
        max_slippage_bps=1_000,
    )


def _entry() -> FastCampaignPaperEntryAuthority:
    return FastCampaignPaperEntryAuthority(
        mint=MINT,
        quote_mint=QUOTE_MINT,
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.10,
    )


def _quote(
    at: int,
    *,
    reference: float = 10.0,
    execution: float = 10.1,
    quantity: float = 10.0,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
) -> FastCampaignPaperQuoteEvidence:
    unavailable = state is PaperQuoteState.UNAVAILABLE
    return FastCampaignPaperQuoteEvidence(
        provider="fixture",
        mint=MINT,
        quote_mint=QUOTE_MINT,
        observed_at_unix_ms=at,
        state=state,
        reference_price_quote=None if unavailable else reference,
        execution_price_quote=None if unavailable else execution,
        quoted_base_quantity=None if unavailable else quantity,
        available_base_quantity=None if unavailable else quantity,
        quote_to_usd_rate=1.0,
    )


def _evidence(
    event: str,
    evaluated_at: int,
    *,
    quote: FastCampaignPaperQuoteEvidence | None = None,
    risk: RiskContext | None = None,
    entry: FastCampaignPaperEntryAuthority | None = None,
    regime: MarketRegime | None = None,
) -> FastCampaignPaperDecisionEvidence:
    return FastCampaignPaperDecisionEvidence(
        source_event_id=event,
        state_version="state-v1",
        evaluated_at_unix_ms=evaluated_at,
        quote=quote,
        risk_context=risk,
        entry_authority=entry,
        market_regime=regime,
    )


def _run(decisions, evidence):
    return run_fast_campaign_paper_candidate(
        identity=_identity(),
        decisions=_results(*decisions),
        evidence=tuple(evidence),
        starting_ledger=create_paper_ledger(20_000.0, T0),
        fill_policy=_fill_policy(),
        risk_policy=_risk_policy(),
        position_policy=_position_policy(),
        evaluation_policy=_evaluation_policy(),
    )


def test_skip_only_campaign_is_deterministic_and_has_zero_trades() -> None:
    decisions = (_decision("event-skip", 1, T0 + 100, "SKIP", 0.0, 0.0),)
    evidence = (_evidence("event-skip", T0 + 100),)

    first = _run(decisions, evidence)
    second = _run(decisions, evidence)

    assert first == second
    assert len(first.event_loop_state.records) == 1
    assert first.buy_results == ()
    assert first.position_results == ()
    assert first.final_ledger == create_paper_ledger(20_000.0, T0)
    assert first.evaluation_capture.entry_provenance == ()
    assert first.trading_evaluation.trades == ()
    assert first.run_evidence.decision_count == 1
    assert first.run_evidence.run_evidence_fingerprint_sha256 == (
        second.run_evidence.run_evidence_fingerprint_sha256
    )


def test_buy_hold_sell_normalizes_one_real_closed_trade() -> None:
    decisions = (
        _decision("event-buy", 1, T0 + 100, "BUY", 0.0, 1.0),
        _decision("event-hold", 2, T0 + 300, "HOLD", 1.0, 1.0),
        _decision("event-sell", 3, T0 + 500, "SELL", 1.0, 0.0),
    )
    evidence = (
        _evidence(
            "event-buy",
            T0 + 200,
            quote=_quote(T0 + 200),
            risk=_risk_context(T0 + 200),
            entry=_entry(),
            regime=MarketRegime.NORMAL,
        ),
        _evidence(
            "event-hold",
            T0 + 400,
            quote=_quote(T0 + 400, reference=10.5, execution=10.5),
        ),
        _evidence(
            "event-sell",
            T0 + 600,
            quote=_quote(T0 + 600, reference=11.0, execution=10.9),
        ),
    )

    result = _run(decisions, evidence)

    assert len(result.event_loop_state.records) == 3
    assert len(result.buy_results) == 1
    assert result.buy_results[0].outcome is FastPaperBuyOutcome.FILLED
    assert len(result.position_results) == 2
    assert result.position_results[0].outcome is FastPaperPositionOutcome.HOLD_MARKED
    assert result.position_results[1].outcome is FastPaperPositionOutcome.SOLD
    assert len(result.final_ledger.positions) == 1
    assert result.final_ledger.positions[0].state is PaperPositionState.CLOSED
    assert len(result.evaluation_capture.entry_provenance) == 1
    assert len(result.evaluation_capture.executions) == 2
    assert len(result.evaluation_capture.closures) == 1
    assert len(result.trading_evaluation.trades) == 1
    trade = result.trading_evaluation.trades[0]
    assert trade.net_pnl_usd == pytest.approx(
        result.evaluation_capture.closures[0].realized_pnl_usd
    )
    assert trade.explicit_cost_usd == pytest.approx(
        result.evaluation_capture.closures[0].accumulated_costs_usd
    )
    assert result.run_evidence.decision_count == 3


def test_reduce_derives_exit_quantity_from_exposure_fraction() -> None:
    decisions = (
        _decision("event-buy", 1, T0 + 100, "BUY", 0.0, 1.0),
        _decision("event-reduce", 2, T0 + 300, "REDUCE", 1.0, 0.4),
    )
    evidence = (
        _evidence(
            "event-buy",
            T0 + 200,
            quote=_quote(T0 + 200),
            risk=_risk_context(T0 + 200),
            entry=_entry(),
            regime=MarketRegime.NORMAL,
        ),
        _evidence(
            "event-reduce",
            T0 + 400,
            quote=_quote(T0 + 400, reference=10.5, execution=10.4),
        ),
    )

    result = _run(decisions, evidence)
    assert result.position_results[0].outcome is FastPaperPositionOutcome.REDUCED
    assert result.position_results[0].execution is not None
    assert result.position_results[0].execution.fill is not None
    assert result.position_results[0].execution.fill.quantity == pytest.approx(6.0)
    open_position = next(
        position
        for position in result.final_ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    assert open_position.quantity == pytest.approx(4.0)


def test_unavailable_quote_never_becomes_a_synthetic_fill() -> None:
    decisions = (_decision("event-buy", 1, T0 + 100, "BUY", 0.0, 1.0),)
    evidence = (
        _evidence(
            "event-buy",
            T0 + 200,
            quote=_quote(T0 + 200, state=PaperQuoteState.UNAVAILABLE),
            risk=_risk_context(T0 + 200),
            entry=_entry(),
            regime=MarketRegime.NORMAL,
        ),
    )
    result = _run(decisions, evidence)
    assert result.buy_results[0].outcome is FastPaperBuyOutcome.ABORTED_QUOTE_UNAVAILABLE
    assert result.buy_results[0].execution is None
    assert result.final_ledger.positions == ()


def test_risk_rejection_remains_evidence_and_does_not_open_position() -> None:
    decisions = (_decision("event-buy", 1, T0 + 100, "BUY", 0.0, 1.0),)
    evidence = (
        _evidence(
            "event-buy",
            T0 + 200,
            quote=_quote(T0 + 200),
            risk=_risk_context(T0 + 200, kill=True),
            entry=_entry(),
            regime=MarketRegime.NORMAL,
        ),
    )
    result = _run(decisions, evidence)
    assert result.buy_results[0].outcome is FastPaperBuyOutcome.RISK_REJECTED
    assert result.final_ledger.positions == ()
    assert result.run_evidence.decision_count == 1


def test_structural_posture_and_evidence_mismatches_fail_closed() -> None:
    buy = _decision("event-buy", 1, T0 + 100, "BUY", 0.0, 1.0)
    hold_while_flat = _decision("event-hold", 1, T0 + 100, "HOLD", 1.0, 1.0)

    with pytest.raises(ValueError, match="quote|BUY"):
        _run(
            (buy,),
            (
                _evidence(
                    "event-buy",
                    T0 + 200,
                    risk=_risk_context(T0 + 200),
                    entry=_entry(),
                    regime=MarketRegime.NORMAL,
                ),
            ),
        )

    with pytest.raises(ValueError, match="OPEN|flat|position"):
        _run(
            (hold_while_flat,),
            (_evidence("event-hold", T0 + 200, quote=_quote(T0 + 200)),),
        )

    with pytest.raises(ValueError, match="source_event_id|evidence"):
        _run(
            (_decision("event-skip", 1, T0 + 100, "SKIP", 0.0, 0.0),),
            (_evidence("wrong-event", T0 + 100),),
        )

    with pytest.raises(ValueError, match="SELL|target"):
        _run(
            (_decision("event-sell", 1, T0 + 100, "SELL", 1.0, 0.2),),
            (_evidence("event-sell", T0 + 200, quote=_quote(T0 + 200)),),
        )
