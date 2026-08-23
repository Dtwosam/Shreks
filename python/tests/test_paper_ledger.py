from dataclasses import replace
import math

import pytest

from shreks_brain.paper.engine import execute_paper_intent
from shreks_brain.paper.ledger import create_paper_ledger, apply_paper_execution
from shreks_brain.paper.ledger_models import (
    PaperLedgerReasonCode,
    PaperLedgerUpdateState,
    PaperPositionState,
)
from shreks_brain.paper.models import (
    PaperExecutionContext,
    PaperExecutionFinding,
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperFillPolicy,
    PaperQuote,
    PaperQuoteState,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


def _policy(**overrides):
    values = dict(
        version="paper-ledger-test",
        assumed_latency_ms=0,
        max_quote_lag_ms=1_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.01,
    )
    values.update(overrides)
    return PaperFillPolicy(**values)


def _intent(**overrides):
    values = dict(
        mint="Mint111",
        side=TradeSide.BUY,
        requested_notional_usd=500.0,
        max_slippage_bps=300,
        strategy_name="fresh_launch_continuation",
        strategy_version="fresh-test",
        score_policy_version="score-test",
        decision_policy_version="decision-test",
        risk_policy_version="risk-test",
        reason="ENTRY_APPROVED",
        idempotency_key="intent-1",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=1_000_100,
    )
    values.update(overrides)
    return TradeIntent(**values)


def _quote(intent, **overrides):
    values = dict(
        provider="paper-ledger-quote",
        mint=intent.mint,
        observed_at_unix_ms=intent.as_of_unix_ms + 100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=1.0,
        execution_price_usd=1.0,
        quoted_notional_usd=intent.requested_notional_usd,
        available_notional_usd=intent.requested_notional_usd,
    )
    values.update(overrides)
    return PaperQuote(**values)


def _execution(intent=None, *, policy=None, quote=None, evaluated_at_unix_ms=None):
    intent = intent or _intent()
    policy = policy or _policy()
    if quote is None:
        quote = _quote(intent)
    evaluated_at_unix_ms = (
        quote.observed_at_unix_ms
        if evaluated_at_unix_ms is None
        else evaluated_at_unix_ms
    )
    return execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=evaluated_at_unix_ms,
            processed_intent_keys=frozenset(),
            quote=quote,
        ),
        policy,
    )


def _failed_execution(intent, state, *, policy=None, evaluated_at_unix_ms=None):
    quote = _quote(
        intent,
        state=state,
        reference_price_usd=None,
        execution_price_usd=None,
        quoted_notional_usd=None,
        available_notional_usd=None,
    )
    return _execution(
        intent,
        policy=policy,
        quote=quote,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
    )


def _code(update):
    assert len(update.findings) == 1
    return update.findings[0].code


def _assert_rejected(update, ledger, code):
    assert update.state is PaperLedgerUpdateState.REJECTED
    assert update.ledger is ledger
    assert update.ledger == ledger
    assert update.position_id is None
    assert update.cash_delta_usd == 0.0
    assert update.realized_pnl_delta_usd == 0.0
    assert update.cost_delta_usd == 0.0
    assert _code(update) is code


def _apply_buy(ledger, *, key="buy-1", as_of=1_000_100, notional=500.0, price=1.0, policy=None):
    intent = _intent(
        side=TradeSide.BUY,
        requested_notional_usd=notional,
        idempotency_key=key,
        as_of_unix_ms=as_of,
    )
    execution = _execution(
        intent,
        policy=policy,
        quote=_quote(
            intent,
            reference_price_usd=price,
            execution_price_usd=price,
        ),
    )
    return intent, execution, apply_paper_execution(ledger, intent, execution)


def _apply_sell(ledger, *, key="sell-1", as_of=1_000_300, notional=250.0, price=1.0, policy=None):
    intent = _intent(
        side=TradeSide.SELL,
        requested_notional_usd=notional,
        idempotency_key=key,
        as_of_unix_ms=as_of,
    )
    execution = _execution(
        intent,
        policy=policy,
        quote=_quote(
            intent,
            reference_price_usd=price,
            execution_price_usd=price,
        ),
    )
    return intent, execution, apply_paper_execution(ledger, intent, execution)


def test_create_empty_paper_ledger_has_no_hidden_capital_or_state():
    ledger = create_paper_ledger(1_000.0, 1_000_000)

    assert ledger.starting_cash_usd == 1_000.0
    assert ledger.cash_balance_usd == 1_000.0
    assert ledger.realized_pnl_usd == 0.0
    assert ledger.unrealized_pnl_usd == 0.0
    assert ledger.accumulated_costs_usd == 0.0
    assert ledger.as_of_unix_ms == 1_000_000
    assert ledger.positions == ()
    assert ledger.entries == ()
    assert ledger.processed_intent_keys == frozenset()


@pytest.mark.parametrize("starting_cash", [-1.0, math.inf, -math.inf, math.nan])
def test_create_paper_ledger_rejects_invalid_starting_cash(starting_cash):
    with pytest.raises(ValueError):
        create_paper_ledger(starting_cash, 1_000_000)


def test_create_paper_ledger_rejects_invalid_timestamp():
    with pytest.raises(ValueError):
        create_paper_ledger(1_000.0, -1)


def test_linkage_and_reason_state_precedence_are_fail_closed():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    intent = _intent()
    execution = _execution(intent)

    cases = [
        (
            replace(intent, execution_mode=RuntimeMode.SHADOW),
            execution,
            PaperLedgerReasonCode.INTENT_MODE_NOT_PAPER,
        ),
        (
            replace(intent, idempotency_key="other-key"),
            execution,
            PaperLedgerReasonCode.INTENT_RESULT_KEY_MISMATCH,
        ),
        (
            replace(intent, mint="OtherMint"),
            execution,
            PaperLedgerReasonCode.INTENT_RESULT_MINT_MISMATCH,
        ),
        (
            replace(intent, side=TradeSide.SELL),
            execution,
            PaperLedgerReasonCode.INTENT_RESULT_SIDE_MISMATCH,
        ),
        (
            replace(intent, requested_notional_usd=499.0),
            execution,
            PaperLedgerReasonCode.INTENT_RESULT_NOTIONAL_MISMATCH,
        ),
    ]
    for alternate_intent, result, expected in cases:
        _assert_rejected(
            apply_paper_execution(ledger, alternate_intent, result),
            ledger,
            expected,
        )

    contradictory = replace(
        execution,
        findings=(
            PaperExecutionFinding(
                PaperExecutionReasonCode.ROUTE_UNAVAILABLE,
                "contradictory non-fill reason",
            ),
        ),
    )
    _assert_rejected(
        apply_paper_execution(ledger, intent, contradictory),
        ledger,
        PaperLedgerReasonCode.EXECUTION_REASON_STATE_MISMATCH,
    )


def test_duplicate_terminal_precedes_time_reversal_and_deferred_is_noop():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    intent, execution, first = _apply_buy(ledger)
    assert first.state is PaperLedgerUpdateState.APPLIED

    replay = apply_paper_execution(first.ledger, intent, execution)
    _assert_rejected(
        replay,
        first.ledger,
        PaperLedgerReasonCode.DUPLICATE_TERMINAL_INTENT,
    )

    old_intent = _intent(idempotency_key="old", as_of_unix_ms=999_000)
    old_execution = _execution(
        old_intent,
        quote=_quote(old_intent, observed_at_unix_ms=999_100),
        evaluated_at_unix_ms=999_100,
    )
    _assert_rejected(
        apply_paper_execution(first.ledger, old_intent, old_execution),
        first.ledger,
        PaperLedgerReasonCode.EXECUTION_TIME_BEFORE_LEDGER,
    )

    deferred_intent = _intent(idempotency_key="deferred", as_of_unix_ms=1_000_300)
    deferred_policy = _policy(assumed_latency_ms=1_000)
    deferred_execution = _execution(
        deferred_intent,
        policy=deferred_policy,
        quote=_quote(deferred_intent, observed_at_unix_ms=1_000_400),
        evaluated_at_unix_ms=1_000_400,
    )
    assert deferred_execution.state is PaperExecutionState.DEFERRED
    noop = apply_paper_execution(first.ledger, deferred_intent, deferred_execution)
    assert noop.state is PaperLedgerUpdateState.NOOP
    assert noop.ledger is first.ledger
    assert noop.ledger == first.ledger
    assert noop.ledger.as_of_unix_ms == first.ledger.as_of_unix_ms
    assert "deferred" not in noop.ledger.processed_intent_keys
    assert _code(noop) is PaperLedgerReasonCode.EXECUTION_DEFERRED_NOOP


def test_zero_cost_failed_attempt_is_terminal_and_consumes_key():
    ledger = create_paper_ledger(1_000.0, 1_000_000)
    intent = _intent(idempotency_key="route-fail")
    execution = _failed_execution(intent, PaperQuoteState.UNAVAILABLE)
    assert execution.state is PaperExecutionState.FAILED
    assert execution.explicit_cost_usd == 0.0

    update = apply_paper_execution(ledger, intent, execution)

    assert update.state is PaperLedgerUpdateState.APPLIED
    assert _code(update) is PaperLedgerReasonCode.FAILED_EXECUTION_BOOKED
    assert update.position_id is None
    assert update.cash_delta_usd == 0.0
    assert update.realized_pnl_delta_usd == 0.0
    assert update.cost_delta_usd == 0.0
    assert len(update.ledger.entries) == 1
    assert update.ledger.entries[0].execution_state is PaperExecutionState.FAILED
    assert update.ledger.positions == ()
    assert update.ledger.processed_intent_keys == frozenset({"route-fail"})


def test_failed_submission_cost_is_realized_and_links_to_open_position_when_present():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    failed_intent = _intent(idempotency_key="failed-entry")
    failed_execution = _failed_execution(
        failed_intent,
        PaperQuoteState.FAILED_AFTER_SUBMISSION,
        policy=_policy(network_fee_usd=0.02),
    )
    failed = apply_paper_execution(ledger, failed_intent, failed_execution)

    assert failed.state is PaperLedgerUpdateState.APPLIED
    assert failed.position_id is None
    assert math.isclose(failed.cash_delta_usd, -0.02)
    assert math.isclose(failed.realized_pnl_delta_usd, -0.02)
    assert math.isclose(failed.cost_delta_usd, 0.02)
    assert math.isclose(failed.ledger.cash_balance_usd, 1_999.98)
    assert math.isclose(failed.ledger.realized_pnl_usd, -0.02)
    assert math.isclose(failed.ledger.accumulated_costs_usd, 0.02)

    _, _, opened = _apply_buy(
        failed.ledger,
        key="buy-after-fail",
        as_of=1_000_300,
    )
    position = opened.ledger.positions[0]
    exit_attempt = _intent(
        side=TradeSide.SELL,
        requested_notional_usd=100.0,
        idempotency_key="failed-exit",
        as_of_unix_ms=1_000_500,
    )
    exit_failure = _failed_execution(
        exit_attempt,
        PaperQuoteState.FAILED_AFTER_SUBMISSION,
        policy=_policy(network_fee_usd=0.02),
    )
    booked = apply_paper_execution(opened.ledger, exit_attempt, exit_failure)

    assert booked.state is PaperLedgerUpdateState.APPLIED
    assert booked.position_id == position.position_id
    linked = next(p for p in booked.ledger.positions if p.position_id == position.position_id)
    assert linked.quantity == position.quantity
    assert linked.open_cost_basis_usd == position.open_cost_basis_usd
    assert math.isclose(linked.realized_pnl_usd, -0.02)
    assert math.isclose(linked.accumulated_costs_usd, position.accumulated_costs_usd + 0.02)


def test_nonnegative_cash_guard_applies_to_buy_failure_fee_and_negative_sell_cashflow():
    buy_ledger = create_paper_ledger(100.0, 1_000_000)
    buy_intent = _intent(requested_notional_usd=100.0, idempotency_key="too-large")
    buy_execution = _execution(buy_intent)
    _assert_rejected(
        apply_paper_execution(buy_ledger, buy_intent, buy_execution),
        buy_ledger,
        PaperLedgerReasonCode.INSUFFICIENT_CASH,
    )

    fee_ledger = create_paper_ledger(0.01, 1_000_000)
    fee_intent = _intent(idempotency_key="fee-too-large")
    fee_execution = _failed_execution(
        fee_intent,
        PaperQuoteState.FAILED_AFTER_SUBMISSION,
        policy=_policy(network_fee_usd=0.02),
    )
    _assert_rejected(
        apply_paper_execution(fee_ledger, fee_intent, fee_execution),
        fee_ledger,
        PaperLedgerReasonCode.INSUFFICIENT_CASH,
    )

    tiny_policy = _policy(swap_fee_bps=0, network_fee_usd=0.01)
    zero_cash_ledger = create_paper_ledger(1.01, 1_000_000)
    _, _, opened = _apply_buy(
        zero_cash_ledger,
        key="consume-cash",
        notional=1.0,
        policy=tiny_policy,
    )
    assert math.isclose(opened.ledger.cash_balance_usd, 0.0, abs_tol=1e-12)
    tiny_sell = _intent(
        side=TradeSide.SELL,
        requested_notional_usd=0.005,
        idempotency_key="negative-sale",
        as_of_unix_ms=1_000_300,
    )
    tiny_sell_execution = _execution(
        tiny_sell,
        policy=tiny_policy,
        quote=_quote(tiny_sell),
    )
    assert tiny_sell_execution.net_cash_flow_usd < 0.0
    _assert_rejected(
        apply_paper_execution(opened.ledger, tiny_sell, tiny_sell_execution),
        opened.ledger,
        PaperLedgerReasonCode.INSUFFICIENT_CASH,
    )

    exact_cash = create_paper_ledger(100.31, 1_000_000)
    exact_intent = _intent(requested_notional_usd=100.0, idempotency_key="exact-cash")
    exact_execution = _execution(exact_intent)
    exact = apply_paper_execution(exact_cash, exact_intent, exact_execution)
    assert exact.state is PaperLedgerUpdateState.APPLIED
    assert math.isclose(exact.ledger.cash_balance_usd, 0.0, abs_tol=1e-12)


def test_first_buy_opens_deterministic_lifecycle_with_all_in_basis_and_provenance():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    intent, execution, update = _apply_buy(ledger)

    assert update.state is PaperLedgerUpdateState.APPLIED
    assert _code(update) is PaperLedgerReasonCode.POSITION_OPENED
    position = update.ledger.positions[0]
    fill = execution.fill
    assert fill is not None
    assert update.position_id == position.position_id
    assert position.state is PaperPositionState.OPEN
    assert math.isclose(position.quantity, fill.quantity)
    assert position.weighted_entry_price_usd == 1.0
    assert math.isclose(position.open_cost_basis_usd, 501.51)
    assert position.realized_pnl_usd == 0.0
    assert position.unrealized_pnl_usd is None
    assert math.isclose(position.accumulated_costs_usd, 1.51)
    assert position.buy_fill_count == 1
    assert position.sell_fill_count == 0
    assert update.ledger.unrealized_pnl_usd is None
    assert math.isclose(update.ledger.cash_balance_usd, 1_498.49)

    entry = update.ledger.entries[0]
    assert entry.strategy_name == intent.strategy_name
    assert entry.strategy_version == intent.strategy_version
    assert entry.score_policy_version == intent.score_policy_version
    assert entry.decision_policy_version == intent.decision_policy_version
    assert entry.risk_policy_version == intent.risk_policy_version
    assert entry.paper_policy_version == execution.policy_version

    _, _, repeated = _apply_buy(create_paper_ledger(2_000.0, 1_000_000))
    assert repeated.position_id == update.position_id


def test_second_buy_keeps_lifecycle_and_updates_weighted_entry_and_basis():
    ledger = create_paper_ledger(3_000.0, 1_000_000)
    _, first_execution, first = _apply_buy(ledger, key="buy-1", price=1.0)
    _, second_execution, second = _apply_buy(
        first.ledger,
        key="buy-2",
        as_of=1_000_300,
        price=2.0,
    )

    old = first.ledger.positions[0]
    new = second.ledger.positions[0]
    second_fill = second_execution.fill
    assert second_fill is not None
    expected_weighted = (
        old.quantity * old.weighted_entry_price_usd
        + second_fill.filled_notional_usd
    ) / (old.quantity + second_fill.quantity)

    assert _code(second) is PaperLedgerReasonCode.POSITION_INCREASED
    assert new.position_id == old.position_id
    assert math.isclose(new.quantity, old.quantity + second_fill.quantity)
    assert math.isclose(new.weighted_entry_price_usd, expected_weighted)
    assert math.isclose(new.open_cost_basis_usd, old.open_cost_basis_usd + 501.51)
    assert new.realized_pnl_usd == old.realized_pnl_usd
    assert math.isclose(new.accumulated_costs_usd, old.accumulated_costs_usd + 1.51)
    assert new.unrealized_pnl_usd is None
    assert new.last_mark_price_usd is None
    assert new.last_mark_at_unix_ms is None
    assert new.buy_fill_count == 2
    assert second.ledger.unrealized_pnl_usd is None
    assert first_execution.fill is not None


def test_sell_without_position_and_oversell_reject_without_consuming_key():
    empty = create_paper_ledger(2_000.0, 1_000_000)
    sell_intent = _intent(
        side=TradeSide.SELL,
        requested_notional_usd=100.0,
        idempotency_key="sell-empty",
    )
    sell_execution = _execution(sell_intent)
    _assert_rejected(
        apply_paper_execution(empty, sell_intent, sell_execution),
        empty,
        PaperLedgerReasonCode.SELL_WITHOUT_OPEN_POSITION,
    )
    assert "sell-empty" not in empty.processed_intent_keys

    _, _, opened = _apply_buy(empty, key="buy-before-oversell")
    oversell = _intent(
        side=TradeSide.SELL,
        requested_notional_usd=501.0,
        idempotency_key="oversell",
        as_of_unix_ms=1_000_300,
    )
    oversell_execution = _execution(oversell)
    _assert_rejected(
        apply_paper_execution(opened.ledger, oversell, oversell_execution),
        opened.ledger,
        PaperLedgerReasonCode.SELL_QUANTITY_EXCEEDS_POSITION,
    )
    assert "oversell" not in opened.ledger.processed_intent_keys


def test_partial_sell_releases_proportional_all_in_basis_without_double_counting_costs():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    _, _, opened = _apply_buy(ledger, key="buy-flat")
    old = opened.ledger.positions[0]
    _, sell_execution, reduced = _apply_sell(opened.ledger, key="sell-half")

    fill = sell_execution.fill
    assert fill is not None
    fraction = fill.quantity / old.quantity
    released_basis = old.open_cost_basis_usd * fraction
    expected_realized = sell_execution.net_cash_flow_usd - released_basis

    assert _code(reduced) is PaperLedgerReasonCode.POSITION_REDUCED
    new = reduced.ledger.positions[0]
    assert new.state is PaperPositionState.OPEN
    assert math.isclose(new.quantity, old.quantity - fill.quantity)
    assert math.isclose(new.open_cost_basis_usd, old.open_cost_basis_usd - released_basis)
    assert new.weighted_entry_price_usd == old.weighted_entry_price_usd
    assert math.isclose(new.realized_pnl_usd, expected_realized)
    assert math.isclose(reduced.realized_pnl_delta_usd, expected_realized)
    assert math.isclose(new.accumulated_costs_usd, old.accumulated_costs_usd + 0.76)
    assert new.sell_fill_count == 1
    assert new.unrealized_pnl_usd is None
    assert new.last_mark_price_usd is None
    assert new.last_mark_at_unix_ms is None
    assert math.isclose(expected_realized, -(1.51 / 2.0 + 0.76))


def test_two_half_exits_close_position_and_total_flat_price_loss_equals_costs_once():
    ledger = create_paper_ledger(2_000.0, 1_000_000)
    _, _, opened = _apply_buy(ledger, key="buy-flat")
    _, _, half = _apply_sell(opened.ledger, key="sell-half-1", as_of=1_000_300)
    _, _, closed = _apply_sell(
        half.ledger,
        key="sell-half-2",
        as_of=1_000_500,
        notional=250.0,
    )

    position = closed.ledger.positions[0]
    assert _code(closed) is PaperLedgerReasonCode.POSITION_CLOSED
    assert position.state is PaperPositionState.CLOSED
    assert math.isclose(position.quantity, 0.0, abs_tol=1e-12)
    assert math.isclose(position.open_cost_basis_usd, 0.0, abs_tol=1e-12)
    assert position.weighted_entry_price_usd == 1.0
    assert position.closed_at_unix_ms is not None
    assert position.unrealized_pnl_usd == 0.0
    assert position.sell_fill_count == 2
    assert math.isclose(position.accumulated_costs_usd, 3.03)
    assert math.isclose(position.realized_pnl_usd, -3.03)
    assert math.isclose(closed.ledger.realized_pnl_usd, -3.03)
    assert math.isclose(closed.ledger.accumulated_costs_usd, 3.03)
    assert closed.ledger.unrealized_pnl_usd == 0.0


def test_reentry_after_close_appends_new_lifecycle_and_preserves_history():
    ledger = create_paper_ledger(3_000.0, 1_000_000)
    _, _, opened = _apply_buy(ledger, key="buy-life-1")
    _, _, closed = _apply_sell(
        opened.ledger,
        key="sell-life-1",
        as_of=1_000_300,
        notional=500.0,
    )
    first_snapshot = closed.ledger.positions[0]
    assert first_snapshot.state is PaperPositionState.CLOSED

    _, _, reopened = _apply_buy(
        closed.ledger,
        key="buy-life-2",
        as_of=1_000_500,
        notional=300.0,
    )

    assert len(reopened.ledger.positions) == 2
    assert reopened.ledger.positions[0] == first_snapshot
    second = reopened.ledger.positions[1]
    assert second.state is PaperPositionState.OPEN
    assert second.position_id != first_snapshot.position_id
    assert second.mint == first_snapshot.mint
    assert reopened.position_id == second.position_id


def test_mixed_terminal_sequence_reconciles_cash_realized_costs_and_keys():
    ledger = create_paper_ledger(5_000.0, 1_000_000)

    failed_entry_intent = _intent(idempotency_key="failed-entry")
    failed_entry_execution = _failed_execution(
        failed_entry_intent,
        PaperQuoteState.FAILED_AFTER_SUBMISSION,
        policy=_policy(network_fee_usd=0.02),
    )
    ledger = apply_paper_execution(
        ledger, failed_entry_intent, failed_entry_execution
    ).ledger

    _, _, buy = _apply_buy(ledger, key="buy", as_of=1_000_300)
    ledger = buy.ledger

    failed_exit_intent = _intent(
        side=TradeSide.SELL,
        requested_notional_usd=100.0,
        idempotency_key="failed-exit",
        as_of_unix_ms=1_000_500,
    )
    failed_exit_execution = _failed_execution(
        failed_exit_intent,
        PaperQuoteState.FAILED_AFTER_SUBMISSION,
        policy=_policy(network_fee_usd=0.02),
    )
    ledger = apply_paper_execution(
        ledger, failed_exit_intent, failed_exit_execution
    ).ledger

    _, _, partial = _apply_sell(
        ledger,
        key="partial",
        as_of=1_000_700,
        notional=200.0,
    )
    ledger = partial.ledger

    _, _, final = _apply_sell(
        ledger,
        key="final",
        as_of=1_000_900,
        notional=300.0,
    )
    ledger = final.ledger

    _, _, new_buy = _apply_buy(
        ledger,
        key="new-position",
        as_of=1_001_100,
        notional=250.0,
    )
    ledger = new_buy.ledger

    assert math.isclose(
        ledger.cash_balance_usd,
        ledger.starting_cash_usd + sum(entry.cash_flow_usd for entry in ledger.entries),
    )
    assert math.isclose(
        ledger.realized_pnl_usd,
        sum(entry.realized_pnl_delta_usd for entry in ledger.entries),
    )
    assert math.isclose(
        ledger.accumulated_costs_usd,
        sum(entry.explicit_cost_usd for entry in ledger.entries),
    )
    assert ledger.processed_intent_keys == frozenset(
        entry.intent_idempotency_key for entry in ledger.entries
    )
    assert tuple(entry.sequence for entry in ledger.entries) == tuple(
        range(1, len(ledger.entries) + 1)
    )
