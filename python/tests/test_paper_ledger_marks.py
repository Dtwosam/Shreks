import math

from shreks_brain.paper.engine import execute_paper_intent
from shreks_brain.paper.ledger import (
    apply_paper_execution,
    create_paper_ledger,
    mark_paper_position,
)
from shreks_brain.paper.ledger_models import (
    PaperLedgerReasonCode,
    PaperLedgerUpdateState,
    PaperPositionMark,
    PaperPositionState,
)
from shreks_brain.paper.models import (
    PaperExecutionContext,
    PaperFillPolicy,
    PaperQuote,
    PaperQuoteState,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


def _policy():
    return PaperFillPolicy(
        version="paper-mark-test",
        assumed_latency_ms=0,
        max_quote_lag_ms=1_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.01,
    )


def _intent(
    *,
    mint="Mint111",
    side=TradeSide.BUY,
    notional=500.0,
    key="intent-1",
    as_of=1_000_100,
):
    return TradeIntent(
        mint=mint,
        side=side,
        requested_notional_usd=notional,
        max_slippage_bps=300,
        strategy_name="fresh_launch_continuation",
        strategy_version="fresh-test",
        score_policy_version="score-test",
        decision_policy_version="decision-test",
        risk_policy_version="risk-test",
        reason="paper ledger mark test",
        idempotency_key=key,
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=as_of,
    )


def _execution(intent, *, price=1.0):
    quote = PaperQuote(
        provider="paper-mark-quote",
        mint=intent.mint,
        observed_at_unix_ms=intent.as_of_unix_ms + 100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=price,
        execution_price_usd=price,
        quoted_notional_usd=intent.requested_notional_usd,
        available_notional_usd=intent.requested_notional_usd,
    )
    return execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=quote.observed_at_unix_ms,
            processed_intent_keys=frozenset(),
            quote=quote,
        ),
        _policy(),
    )


def _apply(
    ledger,
    *,
    mint="Mint111",
    side=TradeSide.BUY,
    notional=500.0,
    key="intent-1",
    as_of=1_000_100,
    price=1.0,
):
    intent = _intent(
        mint=mint,
        side=side,
        notional=notional,
        key=key,
        as_of=as_of,
    )
    execution = _execution(intent, price=price)
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    return update


def _code(update):
    assert len(update.findings) == 1
    return update.findings[0].code


def _assert_rejected(update, ledger, code):
    assert update.state is PaperLedgerUpdateState.REJECTED
    assert update.ledger is ledger
    assert update.ledger == ledger
    assert update.cash_delta_usd == 0.0
    assert update.realized_pnl_delta_usd == 0.0
    assert update.cost_delta_usd == 0.0
    assert _code(update) is code


def test_mark_open_position_includes_incurred_entry_cost_in_unrealized_pnl():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    opened = _apply(ledger)
    position = opened.ledger.positions[0]

    high = mark_paper_position(
        opened.ledger,
        PaperPositionMark(
            position_id=position.position_id,
            mint=position.mint,
            observed_at_unix_ms=1_000_300,
            mark_price_usd=1.20,
        ),
    )
    assert high.state is PaperLedgerUpdateState.APPLIED
    assert _code(high) is PaperLedgerReasonCode.POSITION_MARKED
    assert high.position_id == position.position_id
    marked = high.ledger.positions[0]
    expected_high = marked.quantity * 1.20 - marked.open_cost_basis_usd
    assert math.isclose(marked.unrealized_pnl_usd, expected_high)
    assert math.isclose(high.ledger.unrealized_pnl_usd, expected_high)
    assert math.isclose(expected_high, 98.49)

    low = mark_paper_position(
        high.ledger,
        PaperPositionMark(
            position_id=position.position_id,
            mint=position.mint,
            observed_at_unix_ms=1_000_400,
            mark_price_usd=0.80,
        ),
    )
    marked_low = low.ledger.positions[0]
    expected_low = marked_low.quantity * 0.80 - marked_low.open_cost_basis_usd
    assert math.isclose(marked_low.unrealized_pnl_usd, expected_low)
    assert math.isclose(expected_low, -101.51)

    for update in (high, low):
        assert update.cash_delta_usd == 0.0
        assert update.realized_pnl_delta_usd == 0.0
        assert update.cost_delta_usd == 0.0


def test_mark_rejection_precedence_and_equal_timestamp_boundary():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    opened = _apply(ledger)
    position = opened.ledger.positions[0]
    current_time = opened.ledger.as_of_unix_ms

    stale = PaperPositionMark(
        position_id="missing-position",
        mint="WrongMint",
        observed_at_unix_ms=current_time - 1,
        mark_price_usd=1.0,
    )
    _assert_rejected(
        mark_paper_position(opened.ledger, stale),
        opened.ledger,
        PaperLedgerReasonCode.MARK_TIME_BEFORE_LEDGER,
    )

    missing = PaperPositionMark(
        position_id="missing-position",
        mint=position.mint,
        observed_at_unix_ms=current_time,
        mark_price_usd=1.0,
    )
    _assert_rejected(
        mark_paper_position(opened.ledger, missing),
        opened.ledger,
        PaperLedgerReasonCode.MARK_POSITION_NOT_FOUND,
    )

    wrong_mint = PaperPositionMark(
        position_id=position.position_id,
        mint="WrongMint",
        observed_at_unix_ms=current_time,
        mark_price_usd=1.0,
    )
    _assert_rejected(
        mark_paper_position(opened.ledger, wrong_mint),
        opened.ledger,
        PaperLedgerReasonCode.MARK_MINT_MISMATCH,
    )

    equal_time = PaperPositionMark(
        position_id=position.position_id,
        mint=position.mint,
        observed_at_unix_ms=current_time,
        mark_price_usd=1.0,
    )
    applied = mark_paper_position(opened.ledger, equal_time)
    assert applied.state is PaperLedgerUpdateState.APPLIED
    assert _code(applied) is PaperLedgerReasonCode.POSITION_MARKED
    assert applied.ledger.as_of_unix_ms == current_time


def test_closed_position_cannot_be_marked():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    opened = _apply(ledger, key="buy", as_of=1_000_100)
    closed = _apply(
        opened.ledger,
        side=TradeSide.SELL,
        notional=500.0,
        key="sell",
        as_of=1_000_300,
    )
    position = closed.ledger.positions[0]
    assert position.state is PaperPositionState.CLOSED

    update = mark_paper_position(
        closed.ledger,
        PaperPositionMark(
            position_id=position.position_id,
            mint=position.mint,
            observed_at_unix_ms=closed.ledger.as_of_unix_ms,
            mark_price_usd=1.0,
        ),
    )
    _assert_rejected(
        update,
        closed.ledger,
        PaperLedgerReasonCode.MARK_POSITION_CLOSED,
    )


def test_aggregate_unrealized_requires_marks_for_every_open_position_and_fill_clears_mark():
    ledger = create_paper_ledger(5_000.0, 1_000_000)
    first = _apply(
        ledger,
        mint="Mint111",
        notional=500.0,
        key="buy-a",
        as_of=1_000_100,
    )
    second = _apply(
        first.ledger,
        mint="Mint222",
        notional=300.0,
        key="buy-b",
        as_of=1_000_300,
    )
    ledger = second.ledger
    assert ledger.unrealized_pnl_usd is None
    pos_a = next(p for p in ledger.positions if p.mint == "Mint111")
    pos_b = next(p for p in ledger.positions if p.mint == "Mint222")

    mark_a = mark_paper_position(
        ledger,
        PaperPositionMark(
            position_id=pos_a.position_id,
            mint=pos_a.mint,
            observed_at_unix_ms=1_000_500,
            mark_price_usd=1.10,
        ),
    )
    assert mark_a.ledger.unrealized_pnl_usd is None

    mark_b = mark_paper_position(
        mark_a.ledger,
        PaperPositionMark(
            position_id=pos_b.position_id,
            mint=pos_b.mint,
            observed_at_unix_ms=1_000_600,
            mark_price_usd=0.90,
        ),
    )
    a_after = next(p for p in mark_b.ledger.positions if p.mint == "Mint111")
    b_after = next(p for p in mark_b.ledger.positions if p.mint == "Mint222")
    expected_sum = (a_after.unrealized_pnl_usd or 0.0) + (
        b_after.unrealized_pnl_usd or 0.0
    )
    assert math.isclose(mark_b.ledger.unrealized_pnl_usd, expected_sum)

    cash_before = mark_b.ledger.cash_balance_usd
    realized_before = mark_b.ledger.realized_pnl_usd
    costs_before = mark_b.ledger.accumulated_costs_usd
    entries_before = mark_b.ledger.entries
    keys_before = mark_b.ledger.processed_intent_keys

    increased = _apply(
        mark_b.ledger,
        mint="Mint111",
        notional=100.0,
        key="buy-a-more",
        as_of=1_000_700,
    )
    a_increased = next(p for p in increased.ledger.positions if p.mint == "Mint111")
    assert a_increased.unrealized_pnl_usd is None
    assert a_increased.last_mark_price_usd is None
    assert a_increased.last_mark_at_unix_ms is None
    assert increased.ledger.unrealized_pnl_usd is None

    remarked = mark_paper_position(
        increased.ledger,
        PaperPositionMark(
            position_id=a_increased.position_id,
            mint=a_increased.mint,
            observed_at_unix_ms=1_000_900,
            mark_price_usd=1.0,
        ),
    )
    assert remarked.ledger.unrealized_pnl_usd is not None

    a_live = next(p for p in remarked.ledger.positions if p.mint == "Mint111")
    close_a_notional = a_live.quantity * 1.0
    closed_a = _apply(
        remarked.ledger,
        mint="Mint111",
        side=TradeSide.SELL,
        notional=close_a_notional,
        key="sell-a",
        as_of=1_001_000,
    )
    b_live = next(p for p in closed_a.ledger.positions if p.mint == "Mint222")
    assert b_live.state is PaperPositionState.OPEN
    assert b_live.unrealized_pnl_usd is not None
    assert math.isclose(
        closed_a.ledger.unrealized_pnl_usd,
        b_live.unrealized_pnl_usd,
    )

    close_b_notional = b_live.quantity * 1.0
    closed_b = _apply(
        closed_a.ledger,
        mint="Mint222",
        side=TradeSide.SELL,
        notional=close_b_notional,
        key="sell-b",
        as_of=1_001_200,
    )
    assert all(p.state is PaperPositionState.CLOSED for p in closed_b.ledger.positions)
    assert closed_b.ledger.unrealized_pnl_usd == 0.0

    # Marking itself changed no economic or execution-journal state before the later fills.
    assert mark_b.ledger.cash_balance_usd == cash_before
    assert mark_b.ledger.realized_pnl_usd == realized_before
    assert mark_b.ledger.accumulated_costs_usd == costs_before
    assert mark_b.ledger.entries == entries_before
    assert mark_b.ledger.processed_intent_keys == keys_before
