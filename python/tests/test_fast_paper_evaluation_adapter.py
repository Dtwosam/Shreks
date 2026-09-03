from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.fast_paper import (
    FAST_PAPER_BUY_VERSION,
    FAST_PAPER_POSITION_ACTION_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperBuyApproval,
    FastPaperBuyOutcome,
    FastPaperBuyQuote,
    FastPaperPositionActionApproval,
    FastPaperPositionActionPolicy,
    FastPaperPositionOutcome,
    FastPaperPositionQuote,
    apply_fast_paper_position_action,
    create_fast_paper_position_action_state,
    execute_fast_paper_buy,
)
from shreks_brain.paper import (
    PaperFillPolicy,
    PaperPositionState,
    PaperQuoteState,
    create_paper_ledger,
)
from shreks_brain.paper_evaluation import build_evaluated_trades
from shreks_brain.paper_evaluation.fast import (
    FAST_PAPER_EVALUATION_ADAPTER_VERSION,
    FAST_PAPER_SCORE_POLICY_SENTINEL,
    FastPaperEntryEvaluationContext,
    FastPaperEvaluationIdentity,
    FastPaperExecutionEvidenceInput,
    extract_fast_paper_evaluation_evidence,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext, RiskPolicy


T0 = 8_000_000
MINT = "mint-a"
QUOTE_MINT = "quote-a"
MARKET_KEY = "pump:mint-a:quote-a"
CANDIDATE = "fl9-learned-fixture"
CANDIDATE_SHA = "a" * 64
RUN_STRATEGY = "fl9-fixture-run-v1"


def _assessment(action: FastPaperAction, event_id: str, sequence: int, at: int):
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=event_id,
        market_key=MARKET_KEY,
        source_sequence=sequence,
        as_of_unix_ms=at,
        strategy_family="impulse-scalp" if action is FastPaperAction.BUY else "continuous-policy",
        strategy_version="1",
        action=action,
        reasons=(f"{action.value.lower()}_fixture",),
    )


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-fixture-v1",
        assumed_latency_ms=0,
        max_quote_lag_ms=2_000,
        swap_fee_bps=50,
        network_fee_usd=0.05,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
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


def _identity(**overrides):
    values = dict(
        version=FAST_PAPER_EVALUATION_ADAPTER_VERSION,
        paper_run_id="paper-run-1",
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=CANDIDATE_SHA,
        strategy_version=RUN_STRATEGY,
        allowed_assessment_strategy_versions=("1",),
    )
    values.update(overrides)
    return FastPaperEvaluationIdentity(**values)


def _buy_fixture(*, failed_after_submission: bool = False):
    assessment = _assessment(FastPaperAction.BUY, "event-buy", 1, T0 + 100)
    approval = FastPaperBuyApproval(
        version=FAST_PAPER_BUY_VERSION,
        assessment=assessment,
        mint=MINT,
        quote_mint=QUOTE_MINT,
        state_version="state-v1",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.10,
    )
    quote = FastPaperBuyQuote(
        provider="fixture",
        mint=MINT,
        quote_mint=QUOTE_MINT,
        observed_at_unix_ms=T0 + 200,
        state=(
            PaperQuoteState.FAILED_AFTER_SUBMISSION
            if failed_after_submission
            else PaperQuoteState.EXECUTABLE
        ),
        reference_price_quote=10.0,
        execution_price_quote=10.1,
        quoted_base_quantity=10.0,
        available_base_quantity=10.0,
        quote_to_usd_rate=1.0,
    )
    result = execute_fast_paper_buy(
        create_paper_ledger(20_000.0, T0),
        approval,
        _risk_context(T0 + 200),
        _risk_policy(),
        _fill_policy(),
        evaluated_at_unix_ms=T0 + 200,
        quote=quote,
    )
    assert result.execution is not None
    assert result.ledger_update is not None
    return assessment, result


def _closed_fixture():
    buy_assessment, buy = _buy_fixture()
    assert buy.outcome is FastPaperBuyOutcome.FILLED
    position = next(
        value for value in buy.next_ledger.positions if value.state is PaperPositionState.OPEN
    )
    sell_assessment = _assessment(FastPaperAction.SELL, "event-sell", 2, T0 + 300)
    approval = FastPaperPositionActionApproval(
        version=FAST_PAPER_POSITION_ACTION_VERSION,
        assessment=sell_assessment,
        position_id=position.position_id,
        mint=MINT,
        quote_mint=QUOTE_MINT,
        state_version="state-v1",
        target_base_quantity=position.quantity,
    )
    result = apply_fast_paper_position_action(
        state=create_fast_paper_position_action_state(
            position.position_id, buy.next_ledger.as_of_unix_ms
        ),
        approval=approval,
        ledger=buy.next_ledger,
        quote=FastPaperPositionQuote(
            provider="fixture",
            mint=MINT,
            quote_mint=QUOTE_MINT,
            observed_at_unix_ms=T0 + 400,
            state=PaperQuoteState.EXECUTABLE,
            reference_price_quote=11.0,
            execution_price_quote=10.9,
            quoted_base_quantity=position.quantity,
            available_base_quantity=position.quantity,
            quote_to_usd_rate=1.0,
        ),
        fill_policy=_fill_policy(),
        policy=FastPaperPositionActionPolicy(
            version="position-fixture-v1",
            max_slippage_bps=1_000,
        ),
        evaluated_at_unix_ms=T0 + 400,
    )
    assert result.outcome is FastPaperPositionOutcome.SOLD
    assert result.execution is not None
    assert result.execution_ledger_update is not None
    return (
        FastPaperExecutionEvidenceInput(
            assessment=buy_assessment,
            execution=buy.execution,
            ledger_update=buy.ledger_update,
        ),
        FastPaperExecutionEvidenceInput(
            assessment=sell_assessment,
            execution=result.execution,
            ledger_update=result.execution_ledger_update,
        ),
    )


def test_public_contract_versions_and_identity_validation() -> None:
    assert FAST_PAPER_EVALUATION_ADAPTER_VERSION == "fl9-fast-paper-evaluation-v1"
    assert FAST_PAPER_SCORE_POLICY_SENTINEL == "not-applicable:fast-lane-score"
    assert _identity().allowed_assessment_strategy_versions == ("1",)

    with pytest.raises(ValueError):
        _identity(candidate_fingerprint_sha256="ABC")
    with pytest.raises(ValueError):
        _identity(allowed_assessment_strategy_versions=("2", "1"))
    with pytest.raises(ValueError):
        _identity(allowed_assessment_strategy_versions=("1", "1"))


def test_real_fast_paper_buy_and_sell_normalize_through_sealed_e11() -> None:
    executions = _closed_fixture()
    capture = extract_fast_paper_evaluation_evidence(
        _identity(),
        (
            FastPaperEntryEvaluationContext(
                source_event_id="event-buy",
                market_regime=MarketRegime.NORMAL,
            ),
        ),
        executions,
    )

    assert capture.paper_run_id == "paper-run-1"
    assert capture.candidate_version == CANDIDATE
    assert capture.candidate_fingerprint_sha256 == CANDIDATE_SHA
    assert capture.strategy_version == RUN_STRATEGY
    assert len(capture.entry_provenance) == 1
    assert len(capture.executions) == 2
    assert len(capture.closures) == 1
    assert capture.orphan_costs == ()

    entry = capture.entry_provenance[0]
    assert entry.setup_name == "impulse-scalp"
    assert entry.market_regime is MarketRegime.NORMAL
    assert entry.score_policy_version == FAST_PAPER_SCORE_POLICY_SENTINEL
    assert entry.decision_policy_version == "1"
    assert entry.strategy_version == RUN_STRATEGY

    trades = build_evaluated_trades(
        capture.paper_run_id,
        capture.candidate_version,
        capture.entry_provenance,
        capture.executions,
        capture.closures,
        capture.orphan_costs,
    )
    assert len(trades) == 1
    assert trades[0].candidate_version == CANDIDATE
    assert trades[0].setup_name == "impulse-scalp"
    assert trades[0].market_regime == MarketRegime.NORMAL.value
    assert trades[0].net_pnl_usd == pytest.approx(capture.closures[0].realized_pnl_usd)
    assert trades[0].explicit_cost_usd == pytest.approx(
        capture.closures[0].accumulated_costs_usd
    )


def test_adapter_rejects_missing_context_duplicate_sequence_and_wrong_authority() -> None:
    executions = _closed_fixture()

    with pytest.raises(ValueError, match="context|provenance"):
        extract_fast_paper_evaluation_evidence(_identity(), (), executions)

    with pytest.raises(ValueError, match="sequence|duplicate"):
        extract_fast_paper_evaluation_evidence(
            _identity(),
            (
                FastPaperEntryEvaluationContext(
                    source_event_id="event-buy",
                    market_regime=MarketRegime.NORMAL,
                ),
            ),
            (executions[0], executions[0]),
        )

    wrong = replace(
        executions[1],
        assessment=replace(
            executions[1].assessment,
            strategy_version="unapproved-component",
        ),
    )
    with pytest.raises(ValueError, match="strategy"):
        extract_fast_paper_evaluation_evidence(
            _identity(),
            (
                FastPaperEntryEvaluationContext(
                    source_event_id="event-buy",
                    market_regime=MarketRegime.NORMAL,
                ),
            ),
            (executions[0], wrong),
        )


def test_booked_failed_buy_cost_becomes_orphan_and_blocks_trade_normalization() -> None:
    assessment, failed = _buy_fixture(failed_after_submission=True)
    assert failed.execution is not None
    assert failed.ledger_update is not None
    capture = extract_fast_paper_evaluation_evidence(
        _identity(),
        (),
        (
            FastPaperExecutionEvidenceInput(
                assessment=assessment,
                execution=failed.execution,
                ledger_update=failed.ledger_update,
            ),
        ),
    )
    assert capture.entry_provenance == ()
    assert capture.executions == ()
    assert len(capture.orphan_costs) == 1
    assert capture.orphan_costs[0].explicit_cost_usd > 0.0
    with pytest.raises(ValueError, match="orphan"):
        build_evaluated_trades(
            capture.paper_run_id,
            capture.candidate_version,
            capture.entry_provenance,
            capture.executions,
            capture.closures,
            capture.orphan_costs,
        )
