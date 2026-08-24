from __future__ import annotations

import math

from shreks_brain.exits import ExitPolicy, TakeProfitLevel, create_exit_state
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperFillPolicy,
    PaperLedgerUpdateState,
    PaperPositionMark,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
    mark_paper_position,
)
from shreks_brain.paper_loop import ManagedPaperPosition, PaperLoopPolicy, create_paper_loop_state
from shreks_brain.paper_validation import (
    AccountingFindingCode,
    AccountingValidationStatus,
    validate_paper_accounting,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


T0 = 1_000_000


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-c6-test",
        assumed_latency_ms=0,
        max_quote_lag_ms=5_000,
        swap_fee_bps=100,
        network_fee_usd=0.10,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.10,
    )


def _exit_policy() -> ExitPolicy:
    return ExitPolicy(
        version="exit-c6-test",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(TakeProfitLevel("tp1", 20.0, 0.5),),
        trailing_activation_return_pct=15.0,
        trailing_stop_drawdown_pct=8.0,
        max_hold_seconds=3_600,
        flow_exit_max_buy_fraction_m5=0.40,
        flow_exit_max_buy_pressure_acceleration=-0.10,
        momentum_exit_max_return_1m_pct=-5.0,
        momentum_exit_max_return_5m_pct=-8.0,
        min_liquidity_usd=10_000.0,
        max_exit_price_impact_pct=8.0,
        min_exit_capacity_fraction=0.50,
        wallet_distribution_enabled=False,
    )


def _intent(mint: str, side: TradeSide, notional: float, key: str, as_of: int) -> TradeIntent:
    return TradeIntent(
        mint=mint,
        side=side,
        requested_notional_usd=notional,
        max_slippage_bps=1_000,
        strategy_name="c6-fixture",
        strategy_version="fixture-v1",
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        risk_policy_version="risk-v1",
        reason="C6_ACCOUNTING_FIXTURE",
        idempotency_key=key,
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=as_of,
    )


def _quote(
    mint: str,
    at: int,
    price: float,
    *,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
) -> PaperQuote:
    if state is PaperQuoteState.EXECUTABLE:
        return PaperQuote(
            provider="c6-test",
            mint=mint,
            observed_at_unix_ms=at,
            state=state,
            reference_price_usd=price,
            execution_price_usd=price,
            quoted_notional_usd=10_000.0,
            available_notional_usd=10_000.0,
        )
    return PaperQuote(
        provider="c6-test",
        mint=mint,
        observed_at_unix_ms=at,
        state=state,
        reference_price_usd=None,
        execution_price_usd=None,
        quoted_notional_usd=None,
        available_notional_usd=None,
    )


def _book(ledger, intent: TradeIntent, quote: PaperQuote, policy: PaperFillPolicy):
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=quote.observed_at_unix_ms,
            processed_intent_keys=ledger.processed_intent_keys,
            quote=quote,
        ),
        policy,
    )
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    return update.ledger, execution


def _loop_state(ledger, policy: PaperFillPolicy):
    exit_policy = _exit_policy()
    managed = tuple(
        ManagedPaperPosition(
            position_id=position.position_id,
            exit_policy=exit_policy,
            exit_state=create_exit_state(position, exit_policy),
        )
        for position in ledger.positions
        if position.state.value == "OPEN"
    )
    return create_paper_loop_state(
        ledger,
        PaperLoopPolicy("loop-c6-test", 1_000),
        policy,
        managed_positions=managed,
    )


def test_empty_portfolio_reconciles_without_inventing_activity() -> None:
    policy = _fill_policy()
    state = _loop_state(create_paper_ledger(10_000.0, T0), policy)
    report = validate_paper_accounting(state)
    assert report.status is AccountingValidationStatus.RECONCILED
    assert report.findings == ()
    assert report.cash_balance_usd == 10_000.0
    assert report.expected_cash_balance_usd == 10_000.0
    assert report.equity_usd == 10_000.0
    assert report.net_pnl_usd == 0.0
    assert report.expected_net_pnl_usd == 0.0
    assert report.journal_entry_count == 0
    assert report.lifecycle_count == 0
    assert report.partial_reduction_count == 0
    assert report.terminal_failure_count == 0


def test_marked_open_position_reconciles_equity_and_cost_inclusive_pnl() -> None:
    policy = _fill_policy()
    ledger = create_paper_ledger(10_000.0, T0)
    ledger, _ = _book(
        ledger,
        _intent("MintA", TradeSide.BUY, 100.0, "a-buy", T0 + 100),
        _quote("MintA", T0 + 100, 1.0),
        policy,
    )
    position = ledger.positions[0]
    marked = mark_paper_position(
        ledger,
        PaperPositionMark(position.position_id, "MintA", T0 + 200, 1.20),
    )
    assert marked.state is PaperLedgerUpdateState.APPLIED
    report = validate_paper_accounting(_loop_state(marked.ledger, policy))
    assert report.status is AccountingValidationStatus.RECONCILED
    assert report.open_position_count == 1
    assert report.closed_position_count == 0
    assert report.open_market_value_usd == 120.0
    assert report.equity_usd == 10_018.9
    assert report.net_pnl_usd == 18.9
    assert report.expected_net_pnl_usd == 18.9
    assert report.accumulated_costs_usd == 1.1
    assert report.expected_accumulated_costs_usd == 1.1
    assert report.findings == ()


def test_unmarked_open_position_is_incomplete_not_zero_filled() -> None:
    policy = _fill_policy()
    ledger = create_paper_ledger(10_000.0, T0)
    ledger, _ = _book(
        ledger,
        _intent("MintA", TradeSide.BUY, 100.0, "a-buy", T0 + 100),
        _quote("MintA", T0 + 100, 1.0),
        policy,
    )
    report = validate_paper_accounting(_loop_state(ledger, policy))
    assert report.status is AccountingValidationStatus.INCOMPLETE
    assert report.unrealized_pnl_usd is None
    assert report.open_market_value_usd is None
    assert report.equity_usd is None
    assert report.net_pnl_usd is None
    assert report.expected_net_pnl_usd is None
    assert tuple(finding.code for finding in report.findings) == (
        AccountingFindingCode.UNMARKED_OPEN_POSITION,
    )


def test_partial_multiple_win_loss_and_failed_fill_counts_reconcile() -> None:
    policy = _fill_policy()
    ledger = create_paper_ledger(10_000.0, T0)
    ledger, _ = _book(ledger, _intent("MintA", TradeSide.BUY, 100.0, "a-buy", T0 + 100), _quote("MintA", T0 + 100, 1.0), policy)
    ledger, _ = _book(ledger, _intent("MintA", TradeSide.SELL, 50.0, "a-partial", T0 + 200), _quote("MintA", T0 + 200, 1.25), policy)
    ledger, _ = _book(ledger, _intent("MintA", TradeSide.SELL, 78.0, "a-close", T0 + 300), _quote("MintA", T0 + 300, 1.30), policy)
    ledger, _ = _book(ledger, _intent("MintB", TradeSide.BUY, 100.0, "b-buy", T0 + 400), _quote("MintB", T0 + 400, 1.0), policy)
    ledger, failed = _book(
        ledger,
        _intent("MintB", TradeSide.SELL, 100.0, "b-failed", T0 + 500),
        _quote("MintB", T0 + 500, 1.0, state=PaperQuoteState.FAILED_AFTER_SUBMISSION),
        policy,
    )
    assert failed.fill is None
    ledger, _ = _book(ledger, _intent("MintB", TradeSide.SELL, 80.0, "b-close", T0 + 600), _quote("MintB", T0 + 600, 0.80), policy)
    report = validate_paper_accounting(_loop_state(ledger, policy))
    assert report.status is AccountingValidationStatus.RECONCILED
    assert report.lifecycle_count == 2
    assert report.open_position_count == 0
    assert report.closed_position_count == 2
    assert report.partial_reduction_count == 1
    assert report.terminal_failure_count == 1
    assert report.winning_closed_count == 1
    assert report.losing_closed_count == 1
    assert report.flat_closed_count == 0
    assert math.isclose(
        report.cash_balance_usd - report.starting_cash_usd,
        report.realized_pnl_usd,
        rel_tol=1e-12,
        abs_tol=1e-9,
    )
    assert report.net_pnl_usd == report.realized_pnl_usd
    assert report.findings == ()


def test_validator_detects_tampered_cash_without_repairing_state() -> None:
    policy = _fill_policy()
    state = _loop_state(create_paper_ledger(10_000.0, T0), policy)
    original = state.ledger.cash_balance_usd
    object.__setattr__(state.ledger, "cash_balance_usd", original - 1.0)
    report = validate_paper_accounting(state)
    assert report.status is AccountingValidationStatus.INVALID
    assert report.cash_balance_usd == 9_999.0
    assert report.expected_cash_balance_usd == 10_000.0
    assert tuple(finding.code for finding in report.findings) == (
        AccountingFindingCode.CASH_BALANCE_MISMATCH,
    )
    assert state.ledger.cash_balance_usd == 9_999.0
