from __future__ import annotations

from dataclasses import replace
import math

import pytest

from shreks_brain.exits import ExitPolicy, ExitState
from shreks_brain.observer_campaign.models import (
    ObserverPaperQuoteEvidence,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverPaperRiskEnvironment,
)
from shreks_brain.observer_campaign.risk_context import (
    ObserverPaperRiskContextError,
    build_observer_risk_context,
)
from shreks_brain.observer_market.models import (
    OBSERVER_MARKET_SCHEMA_VERSION,
    ObservedMarketWindow,
    ObserverCandidateIdentity,
    ObserverMarketSnapshot,
)
from shreks_brain.paper import (
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerEntry,
    PaperLedgerReasonCode,
    PaperPosition,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
)
from shreks_brain.paper_loop import (
    ManagedPaperPosition,
    PaperLoopPolicy,
    PaperLoopState,
    PendingPaperEntry,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


TOKEN = "Mint111"
QUOTE_ASSET = "QuoteAsset111"


def _entry(
    sequence: int,
    key: str,
    position_id: str,
    side: TradeSide,
    booked_at: int,
    notional: float,
    cash_flow: float,
    cost: float,
    realized: float,
    reason: PaperLedgerReasonCode,
) -> PaperLedgerEntry:
    return PaperLedgerEntry(
        sequence=sequence,
        intent_idempotency_key=key,
        position_id=position_id,
        mint=TOKEN,
        side=side,
        execution_state=PaperExecutionState.FILLED,
        paper_execution_reason_code=PaperExecutionReasonCode.FILL_COMPLETE,
        ledger_reason_code=reason,
        strategy_name="fresh_launch_continuation",
        strategy_version="fresh-v1",
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        risk_policy_version="risk-v1",
        paper_policy_version="paper-v1",
        booked_at_unix_ms=booked_at,
        filled_quantity=100.0,
        filled_notional_usd=notional,
        cash_flow_usd=cash_flow,
        explicit_cost_usd=cost,
        realized_pnl_delta_usd=realized,
    )


def _exit_policy() -> ExitPolicy:
    return ExitPolicy(
        version="exit-v1",
        required_feature_schema_version="feature-v1",
        max_market_data_age_ms=10_000,
        max_execution_evidence_age_ms=10_000,
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
    )


def _ledger(*, marked: bool = True) -> PaperLedger:
    entries = (
        _entry(1, "buy-1", "p1", TradeSide.BUY, 100, 100.0, -101.0, 1.0, 0.0, PaperLedgerReasonCode.POSITION_OPENED),
        _entry(2, "sell-1", "p1", TradeSide.SELL, 200, 110.0, 109.0, 1.0, 8.0, PaperLedgerReasonCode.POSITION_CLOSED),
        _entry(3, "buy-2", "p2", TradeSide.BUY, 300, 100.0, -101.0, 1.0, 0.0, PaperLedgerReasonCode.POSITION_OPENED),
        _entry(4, "sell-2", "p2", TradeSide.SELL, 400, 90.0, 89.0, 1.0, -12.0, PaperLedgerReasonCode.POSITION_CLOSED),
        _entry(5, "buy-3", "p3", TradeSide.BUY, 450, 100.0, -101.0, 1.0, 0.0, PaperLedgerReasonCode.POSITION_OPENED),
    )
    closed_1 = PaperPosition(
        position_id="p1", mint=TOKEN, state=PaperPositionState.CLOSED,
        quantity=0.0, weighted_entry_price_usd=1.0, open_cost_basis_usd=0.0,
        realized_pnl_usd=8.0, unrealized_pnl_usd=0.0, accumulated_costs_usd=2.0,
        opened_at_unix_ms=100, updated_at_unix_ms=200, closed_at_unix_ms=200,
        last_mark_price_usd=None, last_mark_at_unix_ms=None,
        buy_fill_count=1, sell_fill_count=1,
    )
    closed_2 = PaperPosition(
        position_id="p2", mint=TOKEN, state=PaperPositionState.CLOSED,
        quantity=0.0, weighted_entry_price_usd=1.0, open_cost_basis_usd=0.0,
        realized_pnl_usd=-12.0, unrealized_pnl_usd=0.0, accumulated_costs_usd=2.0,
        opened_at_unix_ms=300, updated_at_unix_ms=400, closed_at_unix_ms=400,
        last_mark_price_usd=None, last_mark_at_unix_ms=None,
        buy_fill_count=1, sell_fill_count=1,
    )
    open_3 = PaperPosition(
        position_id="p3", mint=TOKEN, state=PaperPositionState.OPEN,
        quantity=100.0, weighted_entry_price_usd=1.0, open_cost_basis_usd=101.0,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=-6.0 if marked else None,
        accumulated_costs_usd=1.0,
        opened_at_unix_ms=450, updated_at_unix_ms=500 if marked else 450,
        closed_at_unix_ms=None,
        last_mark_price_usd=0.95 if marked else None,
        last_mark_at_unix_ms=500 if marked else None,
        buy_fill_count=1, sell_fill_count=0,
    )
    return PaperLedger(
        starting_cash_usd=1_000.0,
        cash_balance_usd=895.0,
        realized_pnl_usd=-4.0,
        unrealized_pnl_usd=-6.0 if marked else None,
        accumulated_costs_usd=5.0,
        as_of_unix_ms=500,
        positions=(closed_1, closed_2, open_3),
        entries=entries,
        processed_intent_keys=frozenset(entry.intent_idempotency_key for entry in entries),
    )


def _state(*, marked: bool = True, pending: bool = False) -> PaperLoopState:
    exit_policy = _exit_policy()
    managed = ManagedPaperPosition(
        position_id="p3",
        exit_policy=exit_policy,
        exit_state=ExitState(
            policy_version=exit_policy.version,
            position_id="p3",
            mint=TOKEN,
            initialized_at_unix_ms=450,
            last_evaluated_at_unix_ms=500 if marked else 450,
            high_water_price_usd=1.0,
            high_water_at_unix_ms=450,
            completed_take_profit_levels=frozenset(),
        ),
    )
    pending_entry = None
    if pending:
        pending_entry = PendingPaperEntry(
            intent=TradeIntent(
                mint="OtherMint",
                side=TradeSide.BUY,
                requested_notional_usd=50.0,
                max_slippage_bps=100,
                strategy_name="fresh_launch_continuation",
                strategy_version="fresh-v1",
                score_policy_version="score-v1",
                decision_policy_version="decision-v1",
                risk_policy_version="risk-v1",
                reason="ENTRY_APPROVED",
                idempotency_key="pending-key",
                execution_mode=RuntimeMode.PAPER,
                as_of_unix_ms=500,
            ),
            exit_policy=exit_policy,
        )
    return PaperLoopState(
        ledger=_ledger(marked=marked),
        loop_policy=PaperLoopPolicy(version="loop-v1", exit_max_slippage_bps=100),
        paper_fill_policy=PaperFillPolicy(
            version="paper-v1", assumed_latency_ms=0, max_quote_lag_ms=1_000,
            swap_fee_bps=30, network_fee_usd=0.01,
            allow_partial_fills=True, min_partial_fill_fraction=0.25,
        ),
        managed_positions=(managed,),
        pending_entry=pending_entry,
        last_cycle_at_unix_ms=500,
    )


def _window() -> ObservedMarketWindow:
    candidate = ObserverCandidateIdentity(
        candidate_id=7, mint=TOKEN, pair_address="Pair111",
        discovery_source="pump", discovered_at_unix_ms=100, venue="pump_fun",
    )
    current = ObserverMarketSnapshot(
        row_id=11, candidate_id=7, observed_at_unix_ms=480, source="dexscreener",
        source_observed_at_unix_ms=479, venue="pump_fun", pair_address="Pair111",
        price_usd=2.0, liquidity_usd=200.0, volume_m5_usd=20.0,
        volume_h1_usd=100.0, buys_m5=10, sells_m5=5, buys_h1=100, sells_h1=50,
        pair_created_at_unix_ms=100,
    )
    return ObservedMarketWindow(
        schema_version=OBSERVER_MARKET_SCHEMA_VERSION,
        policy_version="market-v1", candidate=candidate, as_of_unix_ms=500,
        selected_source="dexscreener", selected_pair_address="Pair111", current=current,
        one_minute_ago=None, five_minutes_ago=None, fifteen_minutes_ago=None,
        pair_created_at_unix_ms=100, local_high_price_usd=2.0, local_low_price_usd=2.0,
    )


def _entry_quote_pair():
    evidence = ObserverPaperQuoteEvidence(
        identity=ObserverPaperQuoteIdentity(
            candidate_id=7, purpose=ObserverPaperQuotePurpose.ENTRY,
            provider="jupiter", probe_policy_version="probe-v2",
            input_mint=QUOTE_ASSET, output_mint=TOKEN, taker="Taker111",
            input_amount=50_000_000, slippage_bps=75,
        ),
        output_amount=25_000_000, minimum_output_amount=24_000_000,
        route_available=True, price_impact_pct="1.25", route_labels=("Raydium",),
        quoted_at_unix_ms=490,
    )
    paper_quote = PaperQuote(
        provider="jupiter", mint=TOKEN, observed_at_unix_ms=490,
        state=PaperQuoteState.EXECUTABLE, reference_price_usd=2.0,
        execution_price_usd=2.02, quoted_notional_usd=50.0,
        available_notional_usd=50.0,
    )
    return evidence, paper_quote


def _environment(**changes) -> ObserverPaperRiskEnvironment:
    values = {
        "trading_capital_usd": 1_000.0,
        "day_started_at_unix_ms": 350,
        "data_healthy": True,
        "execution_healthy": False,
        "kill_switch_active": False,
    }
    values.update(changes)
    return ObserverPaperRiskEnvironment(**values)


def test_risk_context_derives_authoritative_ledger_market_and_entry_quote_facts():
    context = build_observer_risk_context(
        _state(), _window(), _entry_quote_pair(), _environment()
    )

    assert context.as_of_unix_ms == 500
    assert context.trading_capital_usd == 1_000.0
    assert context.open_position_count == 1
    assert context.aggregate_open_risk_usd == 101.0
    assert context.daily_realized_pnl_usd == -12.0
    assert math.isclose(context.rolling_drawdown_pct, 18.0 / 1008.0 * 100.0)
    assert context.consecutive_losses == 1
    assert context.last_loss_at_unix_ms == 400
    assert context.liquidity_usd == 200.0
    assert context.expected_price_impact_pct == 1.25
    assert context.price_impact_notional_usd == 50.0
    assert context.market_data_age_ms == 20
    assert context.data_healthy is True
    assert context.execution_healthy is False
    assert context.kill_switch_active is False
    assert context.active_intent_keys == frozenset()


def test_pending_intent_is_active_but_terminal_journal_keys_are_not():
    context = build_observer_risk_context(
        _state(pending=True), _window(), _entry_quote_pair(), _environment()
    )
    assert context.active_intent_keys == frozenset({"pending-key"})
    assert "sell-2" not in context.active_intent_keys


def test_unmarked_open_position_makes_drawdown_unknown_instead_of_optimistic():
    context = build_observer_risk_context(
        _state(marked=False), _window(), _entry_quote_pair(), _environment()
    )
    assert context.rolling_drawdown_pct is None
    assert context.open_position_count == 1
    assert context.aggregate_open_risk_usd == 101.0


def test_missing_or_unavailable_entry_quote_keeps_price_impact_unknown():
    context = build_observer_risk_context(_state(), _window(), None, _environment())
    assert context.expected_price_impact_pct is None
    assert context.price_impact_notional_usd is None

    evidence, quote = _entry_quote_pair()
    unavailable = replace(
        evidence,
        output_amount=0,
        minimum_output_amount=0,
        route_available=False,
        price_impact_pct=None,
        route_labels=(),
    )
    unavailable_quote = replace(
        quote,
        state=PaperQuoteState.UNAVAILABLE,
        reference_price_usd=None,
        execution_price_usd=None,
        quoted_notional_usd=None,
        available_notional_usd=None,
    )
    context = build_observer_risk_context(
        _state(), _window(), (unavailable, unavailable_quote), _environment()
    )
    assert context.expected_price_impact_pct is None
    assert context.price_impact_notional_usd is None


def test_risk_context_rejects_cross_candidate_or_future_entry_evidence():
    evidence, quote = _entry_quote_pair()
    wrong = replace(evidence, identity=replace(evidence.identity, candidate_id=8))
    with pytest.raises(ObserverPaperRiskContextError, match="candidate"):
        build_observer_risk_context(
            _state(), _window(), (wrong, quote), _environment()
        )

    future = replace(evidence, quoted_at_unix_ms=501)
    future_quote = replace(quote, observed_at_unix_ms=501)
    with pytest.raises(ObserverPaperRiskContextError, match="future"):
        build_observer_risk_context(
            _state(), _window(), (future, future_quote), _environment()
        )
