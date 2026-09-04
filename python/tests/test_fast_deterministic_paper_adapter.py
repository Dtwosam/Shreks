from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
    run_fast_deterministic_lifecycle_paper_candidate,
)
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicLifecycleDecision,
    FastDeterministicLifecyclePolicy,
    FastDeterministicLifecycleResults,
    decode_fast_deterministic_candidate_manifest,
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


T0 = 9_000_000
MINT = "mint-a"
QUOTE_MINT = "quote-a"
MARKET_KEY = "pump_fun_bonding_curve:mint-life:quote-life"
MANIFEST_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_candidate_manifest_v1.json"
)


def _manifest():
    return decode_fast_deterministic_candidate_manifest(
        MANIFEST_FIXTURE.read_text(encoding="utf-8")
    )


def _decision(
    event: str,
    sequence: int,
    at: int,
    *,
    posture: str,
    component_kind: str,
    action: str,
    current: float | None,
    target: float,
) -> FastDeterministicLifecycleDecision:
    return FastDeterministicLifecycleDecision(
        source_event_id=event,
        market_key=MARKET_KEY,
        source_sequence=sequence,
        as_of_unix_ms=at,
        posture=posture,
        component_kind=component_kind,
        component_version=1,
        action=action,
        current_exposure_fraction=current,
        target_exposure_fraction=target,
    )


def _results(*decisions: FastDeterministicLifecycleDecision):
    return FastDeterministicLifecycleResults(
        schema_name="shreks.fast_deterministic_lifecycle_results",
        schema_version=1,
        policy=FastDeterministicLifecyclePolicy(
            version=1,
            entry_baseline_kind="IMPULSE_SCALP",
            manager_baseline_kind="LONGER_RUNNER",
            entry_target_exposure_fraction=0.8,
            reduce_remaining_fraction=0.5,
        ),
        decisions=decisions,
        batch_fingerprint_sha256="d" * 64,
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


def _risk_context(at: int) -> RiskContext:
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
        kill_switch_active=False,
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


def _run(decisions, evidence, *, manifest=None):
    return run_fast_deterministic_lifecycle_paper_candidate(
        manifest=_manifest() if manifest is None else manifest,
        paper_run_id="paper-run-baseline",
        assessment_version="assessment-v1",
        decisions=_results(*decisions),
        evidence=tuple(evidence),
        starting_ledger=create_paper_ledger(20_000.0, T0),
        fill_policy=_fill_policy(),
        risk_policy=_risk_policy(),
        position_policy=_position_policy(),
        evaluation_policy=_evaluation_policy(),
    )


def test_deterministic_manifest_identity_flows_into_paper_and_run_evidence() -> None:
    decisions = (
        _decision(
            "event-buy",
            1,
            T0 + 100,
            posture="FLAT",
            component_kind="IMPULSE_SCALP",
            action="BUY",
            current=None,
            target=0.8,
        ),
        _decision(
            "event-reduce",
            2,
            T0 + 300,
            posture="OPEN",
            component_kind="LONGER_RUNNER",
            action="REDUCE",
            current=0.8,
            target=0.4,
        ),
        _decision(
            "event-sell",
            3,
            T0 + 500,
            posture="OPEN",
            component_kind="LONGER_RUNNER",
            action="SELL",
            current=0.4,
            target=0.0,
        ),
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
        _evidence(
            "event-sell",
            T0 + 600,
            quote=_quote(T0 + 600, reference=11.0, execution=10.9),
        ),
    )

    result = _run(decisions, evidence)

    assert result.identity.candidate_version == (
        "fl9-baseline-impulse-scalp-longer-runner-v1"
    )
    assert result.identity.candidate_fingerprint_sha256 == (
        "7377f016783f80c6d3935ff41efd7a66b8da280df13cd7be8d2e6c03146a8676"
    )
    assert result.identity.strategy_family == "fast_deterministic_lifecycle"
    assert result.identity.strategy_version == "impulse-scalp__longer-runner-v1"
    assert result.run_evidence.candidate_fingerprint_sha256 == (
        result.identity.candidate_fingerprint_sha256
    )

    assert result.buy_results[0].outcome is FastPaperBuyOutcome.FILLED
    assert len(result.position_results) == 2
    assert result.position_results[0].outcome is FastPaperPositionOutcome.REDUCED
    assert result.position_results[0].execution is not None
    assert result.position_results[0].execution.fill is not None
    assert result.position_results[0].execution.fill.quantity == pytest.approx(5.0)
    assert result.position_results[1].outcome is FastPaperPositionOutcome.SOLD
    assert result.final_ledger.positions[0].state is PaperPositionState.CLOSED
    assert len(result.trading_evaluation.trades) == 1


def test_skip_only_deterministic_campaign_is_repeatable() -> None:
    decisions = (
        _decision(
            "event-skip",
            1,
            T0 + 100,
            posture="FLAT",
            component_kind="IMPULSE_SCALP",
            action="SKIP",
            current=None,
            target=0.0,
        ),
    )
    evidence = (_evidence("event-skip", T0 + 100),)

    first = _run(decisions, evidence)
    second = _run(decisions, evidence)
    assert first == second
    assert first.buy_results == ()
    assert first.position_results == ()
    assert first.trading_evaluation.trades == ()


def test_manifest_and_decision_lifecycle_policy_mismatch_fails_before_execution() -> None:
    manifest = _manifest()
    mismatched = replace(
        manifest,
        lifecycle_policy=replace(
            manifest.lifecycle_policy,
            entry_target_exposure_fraction=0.7,
        ),
    )
    decision = _decision(
        "event-skip",
        1,
        T0 + 100,
        posture="FLAT",
        component_kind="IMPULSE_SCALP",
        action="SKIP",
        current=None,
        target=0.0,
    )

    with pytest.raises(ValueError, match="manifest|policy|lifecycle"):
        _run((decision,), (_evidence("event-skip", T0 + 100),), manifest=mismatched)


def test_unavailable_deterministic_buy_quote_never_becomes_synthetic_fill() -> None:
    decision = _decision(
        "event-buy",
        1,
        T0 + 100,
        posture="FLAT",
        component_kind="IMPULSE_SCALP",
        action="BUY",
        current=None,
        target=0.8,
    )
    result = _run(
        (decision,),
        (
            _evidence(
                "event-buy",
                T0 + 200,
                quote=_quote(T0 + 200, state=PaperQuoteState.UNAVAILABLE),
                risk=_risk_context(T0 + 200),
                entry=_entry(),
                regime=MarketRegime.NORMAL,
            ),
        ),
    )

    assert result.buy_results[0].outcome is FastPaperBuyOutcome.ABORTED_QUOTE_UNAVAILABLE
    assert result.buy_results[0].execution is None
    assert result.final_ledger.positions == ()


def test_learned_and_deterministic_runners_share_one_execution_core() -> None:
    engine = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_campaign_paper"
        / "engine.py"
    ).read_text(encoding="utf-8")

    assert "_run_fast_campaign_paper_decision_sequence" in engine
    assert engine.count("execute_fast_paper_buy(") == 1
    assert engine.count("apply_fast_paper_position_action(") == 1
