from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.fast_paper import (
    FAST_PAPER_BUY_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperBuyApproval,
    FastPaperBuyError,
    FastPaperBuyOutcome,
    FastPaperBuyQuote,
    execute_fast_paper_buy,
)
from shreks_brain.paper import (
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedgerUpdateState,
    PaperPositionState,
    PaperQuoteState,
    create_paper_ledger,
)
from shreks_brain.risk import (
    FastEntryRiskRequest,
    RiskContext,
    RiskPolicy,
    RiskReasonCode,
    RiskState,
    assess_fast_entry_risk,
)
from shreks_brain.runtime import RuntimeMode


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-v1",
        required_decision_policy_version="assessment-v1",
        required_feature_schema_version="state-v1",
        target_position_notional_usd=100.0,
        max_notional_per_position_usd=100.0,
        max_capital_fraction_per_position=1.0,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=1_000.0,
        max_daily_realized_loss_usd=1_000.0,
        max_rolling_drawdown_pct=100.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=0,
        min_liquidity_usd=0.0,
        max_expected_price_impact_pct=100.0,
        max_slippage_bps=1_000,
        max_market_data_age_ms=1_000,
    )


def _risk_context(as_of: int = 1_100) -> RiskContext:
    return RiskContext(
        as_of_unix_ms=as_of,
        trading_capital_usd=10_000.0,
        open_position_count=0,
        aggregate_open_risk_usd=0.0,
        daily_realized_pnl_usd=0.0,
        rolling_drawdown_pct=0.0,
        consecutive_losses=0,
        last_loss_at_unix_ms=None,
        liquidity_usd=10_000.0,
        expected_price_impact_pct=0.0,
        price_impact_notional_usd=1_000.0,
        market_data_age_ms=0,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _fast_risk_request(*, notional: float = 50.0) -> FastEntryRiskRequest:
    return FastEntryRiskRequest(
        mint="mint-a",
        source_event_id="event-1",
        decision_at_unix_ms=1_000,
        evaluated_at_unix_ms=1_100,
        strategy_name="impulse-scalp",
        strategy_version="1",
        action_assessment_version="assessment-v1",
        state_version="state-v1",
        requested_notional_usd=notional,
    )


def _assessment(action: FastPaperAction = FastPaperAction.BUY) -> FastPaperActionAssessment:
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id="event-1",
        market_key="pump:mint-a:quote-a",
        source_sequence=7,
        as_of_unix_ms=1_000,
        strategy_family="impulse-scalp",
        strategy_version="1",
        action=action,
        reasons=("all_conditions_met",),
    )


def _approval(
    *,
    decision_price: float = 1.0,
    maximum_price: float = 1.2,
    expected_variable_bps: int = 100,
    expected_fixed_quote: float = 0.0,
) -> FastPaperBuyApproval:
    return FastPaperBuyApproval(
        version=FAST_PAPER_BUY_VERSION,
        assessment=_assessment(),
        mint="mint-a",
        quote_mint="quote-a",
        state_version="state-v1",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=decision_price,
        maximum_acceptable_entry_price_quote=maximum_price,
        expected_entry_variable_cost_bps=expected_variable_bps,
        expected_entry_fixed_cost_quote=expected_fixed_quote,
    )


def _quote(
    *,
    observed_at: int = 1_100,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
    reference_price: float = 1.0,
    execution_price: float = 1.05,
    quoted_base: float = 10.0,
    available_base: float = 10.0,
    quote_to_usd: float = 1.0,
) -> FastPaperBuyQuote:
    return FastPaperBuyQuote(
        provider="fixture",
        mint="mint-a",
        quote_mint="quote-a",
        observed_at_unix_ms=observed_at,
        state=state,
        reference_price_quote=reference_price,
        execution_price_quote=execution_price,
        quoted_base_quantity=quoted_base,
        available_base_quantity=available_base,
        quote_to_usd_rate=quote_to_usd,
    )


def _fill_policy(
    *,
    latency_ms: int = 100,
    max_quote_lag_ms: int = 1_000,
    swap_fee_bps: int = 100,
    network_fee_usd: float = 0.0,
) -> PaperFillPolicy:
    return PaperFillPolicy(
        version="fill-v1",
        assumed_latency_ms=latency_ms,
        max_quote_lag_ms=max_quote_lag_ms,
        swap_fee_bps=swap_fee_bps,
        network_fee_usd=network_fee_usd,
        allow_partial_fills=False,
        min_partial_fill_fraction=1.0,
    )


def test_fast_entry_risk_approves_exact_requested_notional_without_resizing() -> None:
    assessment = assess_fast_entry_risk(
        _fast_risk_request(notional=50.0),
        _risk_context(),
        _risk_policy(),
        RuntimeMode.PAPER,
    )

    assert assessment.state is RiskState.APPROVED
    assert assessment.requested_notional_usd == 50.0
    assert assessment.approved_notional_usd == 50.0
    assert assessment.intent is not None
    assert assessment.intent.requested_notional_usd == 50.0
    assert assessment.intent.as_of_unix_ms == 1_000
    assert assessment.evaluated_at_unix_ms == 1_100
    assert assessment.intent.score_policy_version == "not-applicable:fast-lane"
    assert assessment.intent.decision_policy_version == "assessment-v1"
    assert assessment.intent.strategy_name == "impulse-scalp"
    assert assessment.intent.strategy_version == "1"


def test_fast_entry_risk_rejects_requested_notional_above_preserved_risk_cap() -> None:
    assessment = assess_fast_entry_risk(
        _fast_risk_request(notional=100.01),
        _risk_context(),
        _risk_policy(),
        RuntimeMode.PAPER,
    )

    assert assessment.state is RiskState.REJECTED
    assert assessment.requested_notional_usd == 100.01
    assert assessment.approved_notional_usd is None
    assert assessment.intent is None
    assert assessment.findings[0].code is RiskReasonCode.REQUESTED_NOTIONAL_EXCEEDS_RISK_CAP


def test_fast_entry_risk_reuses_kill_switch_and_health_guardrails() -> None:
    killed = assess_fast_entry_risk(
        _fast_risk_request(),
        replace(_risk_context(), kill_switch_active=True),
        _risk_policy(),
        RuntimeMode.PAPER,
    )
    degraded = assess_fast_entry_risk(
        _fast_risk_request(),
        replace(_risk_context(), execution_healthy=False),
        _risk_policy(),
        RuntimeMode.PAPER,
    )

    assert killed.state is RiskState.REJECTED
    assert killed.findings[0].code is RiskReasonCode.KILL_SWITCH_ACTIVE
    assert degraded.state is RiskState.REJECTED
    assert degraded.findings[0].code is RiskReasonCode.EXECUTION_HEALTH_DEGRADED


def test_fast_entry_risk_enforces_action_and_state_compatibility_versions() -> None:
    action_mismatch = assess_fast_entry_risk(
        replace(_fast_risk_request(), action_assessment_version="other"),
        _risk_context(),
        _risk_policy(),
        RuntimeMode.PAPER,
    )
    state_mismatch = assess_fast_entry_risk(
        replace(_fast_risk_request(), state_version="other"),
        _risk_context(),
        _risk_policy(),
        RuntimeMode.PAPER,
    )

    assert action_mismatch.findings[0].code is RiskReasonCode.DECISION_POLICY_MISMATCH
    assert state_mismatch.findings[0].code is RiskReasonCode.FEATURE_SCHEMA_UNSUPPORTED


def test_buy_defers_before_assumed_landing_latency_without_mutation() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    result = execute_fast_paper_buy(
        ledger,
        _approval(),
        _risk_context(as_of=1_050),
        _risk_policy(),
        _fill_policy(latency_ms=100),
        evaluated_at_unix_ms=1_050,
        quote=None,
    )

    assert result.outcome is FastPaperBuyOutcome.DEFERRED
    assert result.next_ledger == ledger
    assert result.risk_assessment is None
    assert result.execution is None
    assert result.ledger_update is None


def test_buy_defers_when_only_quote_precedes_landing_eligibility() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    result = execute_fast_paper_buy(
        ledger,
        _approval(),
        _risk_context(as_of=1_150),
        _risk_policy(),
        _fill_policy(latency_ms=100),
        evaluated_at_unix_ms=1_150,
        quote=_quote(observed_at=1_050),
    )

    assert result.outcome is FastPaperBuyOutcome.DEFERRED
    assert result.next_ledger == ledger


def test_buy_aborts_when_native_execution_price_exceeds_rust_maximum() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    result = execute_fast_paper_buy(
        ledger,
        _approval(maximum_price=1.2),
        _risk_context(),
        _risk_policy(),
        _fill_policy(),
        evaluated_at_unix_ms=1_100,
        quote=_quote(execution_price=1.200001),
    )

    assert result.outcome is FastPaperBuyOutcome.ABORTED_PRICE_ABOVE_MAXIMUM
    assert result.next_ledger == ledger
    assert result.risk_assessment is None
    assert result.execution is None


def test_buy_aborts_when_full_rust_assessed_base_quantity_is_not_executable() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    quoted_short = execute_fast_paper_buy(
        ledger,
        _approval(),
        _risk_context(),
        _risk_policy(),
        _fill_policy(),
        evaluated_at_unix_ms=1_100,
        quote=_quote(quoted_base=9.9),
    )
    available_short = execute_fast_paper_buy(
        ledger,
        _approval(),
        _risk_context(),
        _risk_policy(),
        _fill_policy(),
        evaluated_at_unix_ms=1_100,
        quote=_quote(available_base=9.9),
    )

    assert quoted_short.outcome is FastPaperBuyOutcome.ABORTED_INSUFFICIENT_CAPACITY
    assert available_short.outcome is FastPaperBuyOutcome.ABORTED_INSUFFICIENT_CAPACITY
    assert quoted_short.next_ledger == ledger
    assert available_short.next_ledger == ledger


def test_buy_opens_exact_quantity_position_through_preserved_fill_and_ledger() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    result = execute_fast_paper_buy(
        ledger,
        _approval(maximum_price=1.2, expected_variable_bps=100),
        _risk_context(),
        _risk_policy(),
        _fill_policy(swap_fee_bps=100),
        evaluated_at_unix_ms=1_100,
        quote=_quote(execution_price=1.05),
    )

    assert result.outcome is FastPaperBuyOutcome.FILLED
    assert result.risk_assessment is not None
    assert result.risk_assessment.state is RiskState.APPROVED
    assert result.execution is not None
    assert result.execution.state is PaperExecutionState.FILLED
    assert result.execution.fill is not None
    assert result.execution.fill.quantity == pytest.approx(10.0)
    assert result.ledger_update is not None
    assert result.ledger_update.state is PaperLedgerUpdateState.APPLIED
    open_positions = [
        position
        for position in result.next_ledger.positions
        if position.state is PaperPositionState.OPEN
    ]
    assert len(open_positions) == 1
    assert open_positions[0].mint == "mint-a"
    assert open_positions[0].quantity == pytest.approx(10.0)


def test_buy_aborts_before_ledger_when_actual_total_spend_exceeds_approved_envelope() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    result = execute_fast_paper_buy(
        ledger,
        _approval(
            decision_price=0.99,
            maximum_price=1.0,
            expected_variable_bps=0,
            expected_fixed_quote=0.0,
        ),
        _risk_context(),
        _risk_policy(),
        _fill_policy(swap_fee_bps=100),
        evaluated_at_unix_ms=1_100,
        quote=_quote(reference_price=1.0, execution_price=1.0),
    )

    assert result.execution is not None
    assert result.execution.state is PaperExecutionState.FILLED
    assert result.outcome is FastPaperBuyOutcome.ABORTED_TOTAL_COST_ABOVE_MAXIMUM
    assert result.actual_entry_total_quote is not None
    assert result.actual_entry_total_quote > result.maximum_entry_total_quote
    assert result.next_ledger == ledger
    assert result.ledger_update is None


def test_buy_risk_rejection_never_creates_exposure() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    result = execute_fast_paper_buy(
        ledger,
        _approval(),
        replace(_risk_context(), kill_switch_active=True),
        _risk_policy(),
        _fill_policy(),
        evaluated_at_unix_ms=1_100,
        quote=_quote(),
    )

    assert result.outcome is FastPaperBuyOutcome.RISK_REJECTED
    assert result.risk_assessment is not None
    assert result.risk_assessment.findings[0].code is RiskReasonCode.KILL_SWITCH_ACTIVE
    assert result.execution is None
    assert result.next_ledger == ledger


def test_terminal_fill_replay_is_idempotent_against_authoritative_ledger() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    first = execute_fast_paper_buy(
        ledger,
        _approval(),
        _risk_context(),
        _risk_policy(),
        _fill_policy(),
        evaluated_at_unix_ms=1_100,
        quote=_quote(),
    )
    assert first.outcome is FastPaperBuyOutcome.FILLED

    replay = execute_fast_paper_buy(
        first.next_ledger,
        _approval(),
        _risk_context(),
        _risk_policy(),
        _fill_policy(),
        evaluated_at_unix_ms=1_100,
        quote=_quote(),
    )

    assert replay.outcome is FastPaperBuyOutcome.ALREADY_PROCESSED
    assert replay.next_ledger == first.next_ledger
    assert replay.execution is None
    assert len(replay.next_ledger.positions) == len(first.next_ledger.positions)


def test_failed_after_submission_books_preserved_network_cost() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)
    result = execute_fast_paper_buy(
        ledger,
        _approval(maximum_price=1.2),
        _risk_context(),
        _risk_policy(),
        _fill_policy(network_fee_usd=0.25),
        evaluated_at_unix_ms=1_100,
        quote=_quote(state=PaperQuoteState.FAILED_AFTER_SUBMISSION),
    )

    assert result.outcome is FastPaperBuyOutcome.EXECUTION_FAILED
    assert result.execution is not None
    assert result.execution.state is PaperExecutionState.FAILED
    assert result.execution.network_fee_usd == pytest.approx(0.25)
    assert result.ledger_update is not None
    assert result.ledger_update.state is PaperLedgerUpdateState.APPLIED
    assert result.next_ledger.cash_balance_usd == pytest.approx(999.75)
    assert not result.next_ledger.positions


def test_non_buy_approval_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="BUY"):
        FastPaperBuyApproval(
            version=FAST_PAPER_BUY_VERSION,
            assessment=_assessment(FastPaperAction.SKIP),
            mint="mint-a",
            quote_mint="quote-a",
            state_version="state-v1",
            intended_base_quantity=10.0,
            decision_executable_entry_price_quote=1.0,
            maximum_acceptable_entry_price_quote=1.2,
            expected_entry_variable_cost_bps=100,
            expected_entry_fixed_cost_quote=0.0,
        )


def test_buy_identity_and_point_in_time_contradictions_fail_closed() -> None:
    ledger = create_paper_ledger(1_000.0, 1_000)

    with pytest.raises(FastPaperBuyError):
        execute_fast_paper_buy(
            ledger,
            _approval(),
            _risk_context(),
            _risk_policy(),
            _fill_policy(),
            evaluated_at_unix_ms=1_100,
            quote=replace(_quote(), mint="other"),
        )

    with pytest.raises(FastPaperBuyError):
        execute_fast_paper_buy(
            ledger,
            _approval(),
            _risk_context(),
            _risk_policy(),
            _fill_policy(),
            evaluated_at_unix_ms=1_100,
            quote=_quote(observed_at=1_101),
        )

    with pytest.raises(ValueError):
        replace(_quote(), quote_to_usd_rate=0.0)
