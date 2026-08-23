from dataclasses import FrozenInstanceError, fields, replace
import math

import pytest

from shreks_brain.paper import PaperExecutionReasonCode, PaperExecutionState
from shreks_brain.paper.ledger_models import (
    PaperLedger,
    PaperLedgerEntry,
    PaperLedgerFinding,
    PaperLedgerReasonCode,
    PaperLedgerUpdate,
    PaperLedgerUpdateState,
    PaperPosition,
    PaperPositionMark,
    PaperPositionState,
)
from shreks_brain.risk import TradeSide


def _position(**overrides):
    quantity = 500.0 / 1.01
    values = dict(
        position_id="position-1",
        mint="Mint111",
        state=PaperPositionState.OPEN,
        quantity=quantity,
        weighted_entry_price_usd=1.01,
        open_cost_basis_usd=501.51,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=None,
        accumulated_costs_usd=1.51,
        opened_at_unix_ms=1_000_500,
        updated_at_unix_ms=1_000_500,
        closed_at_unix_ms=None,
        last_mark_price_usd=None,
        last_mark_at_unix_ms=None,
        buy_fill_count=1,
        sell_fill_count=0,
    )
    values.update(overrides)
    return PaperPosition(**values)


def _entry(**overrides):
    quantity = 500.0 / 1.01
    values = dict(
        sequence=1,
        intent_idempotency_key="intent-1",
        position_id="position-1",
        mint="Mint111",
        side=TradeSide.BUY,
        execution_state=PaperExecutionState.FILLED,
        paper_execution_reason_code=PaperExecutionReasonCode.FILL_COMPLETE,
        ledger_reason_code=PaperLedgerReasonCode.POSITION_OPENED,
        strategy_name="fresh_launch_continuation",
        strategy_version="fresh-test",
        score_policy_version="score-test",
        decision_policy_version="decision-test",
        risk_policy_version="risk-test",
        paper_policy_version="paper-test",
        booked_at_unix_ms=1_000_500,
        filled_quantity=quantity,
        filled_notional_usd=500.0,
        cash_flow_usd=-501.51,
        explicit_cost_usd=1.51,
        realized_pnl_delta_usd=0.0,
    )
    values.update(overrides)
    return PaperLedgerEntry(**values)


def _ledger(**overrides):
    values = dict(
        starting_cash_usd=1_000.0,
        cash_balance_usd=498.49,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=None,
        accumulated_costs_usd=1.51,
        as_of_unix_ms=1_000_500,
        positions=(_position(),),
        entries=(_entry(),),
        processed_intent_keys=frozenset({"intent-1"}),
    )
    values.update(overrides)
    return PaperLedger(**values)


def _finding(code=PaperLedgerReasonCode.POSITION_OPENED):
    return PaperLedgerFinding(code=code, message="ledger finding")


def test_enum_orders_are_stable():
    assert tuple(item.value for item in PaperPositionState) == ("OPEN", "CLOSED")
    assert tuple(item.value for item in PaperLedgerUpdateState) == (
        "NOOP",
        "REJECTED",
        "APPLIED",
    )
    assert tuple(item.value for item in PaperLedgerReasonCode) == (
        "INTENT_MODE_NOT_PAPER",
        "INTENT_RESULT_KEY_MISMATCH",
        "INTENT_RESULT_MINT_MISMATCH",
        "INTENT_RESULT_SIDE_MISMATCH",
        "INTENT_RESULT_NOTIONAL_MISMATCH",
        "EXECUTION_REASON_STATE_MISMATCH",
        "DUPLICATE_TERMINAL_INTENT",
        "EXECUTION_TIME_BEFORE_LEDGER",
        "EXECUTION_DEFERRED_NOOP",
        "INSUFFICIENT_CASH",
        "SELL_WITHOUT_OPEN_POSITION",
        "SELL_QUANTITY_EXCEEDS_POSITION",
        "FAILED_EXECUTION_BOOKED",
        "POSITION_OPENED",
        "POSITION_INCREASED",
        "POSITION_REDUCED",
        "POSITION_CLOSED",
        "MARK_TIME_BEFORE_LEDGER",
        "MARK_POSITION_NOT_FOUND",
        "MARK_MINT_MISMATCH",
        "MARK_POSITION_CLOSED",
        "POSITION_MARKED",
    )


def test_canonical_position_entry_and_ledger_reconcile():
    ledger = _ledger()
    assert ledger.cash_balance_usd == 498.49
    assert ledger.positions[0].open_cost_basis_usd == 501.51
    assert ledger.processed_intent_keys == frozenset({"intent-1"})


def test_empty_ledger_snapshot_can_have_zero_unrealized():
    ledger = PaperLedger(
        starting_cash_usd=1_000.0,
        cash_balance_usd=1_000.0,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=0.0,
        accumulated_costs_usd=0.0,
        as_of_unix_ms=1_000_000,
        positions=(),
        entries=(),
        processed_intent_keys=frozenset(),
    )
    assert ledger.unrealized_pnl_usd == 0.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"position_id": ""}, "position_id"),
        ({"mint": ""}, "mint"),
        ({"state": "OPEN"}, "state"),
        ({"quantity": -1.0}, "quantity"),
        ({"weighted_entry_price_usd": 0.0}, "weighted_entry_price_usd"),
        ({"open_cost_basis_usd": -1.0}, "open_cost_basis_usd"),
        ({"realized_pnl_usd": math.inf}, "realized_pnl_usd"),
        ({"accumulated_costs_usd": -1.0}, "accumulated_costs_usd"),
        ({"opened_at_unix_ms": -1}, "opened_at_unix_ms"),
        ({"updated_at_unix_ms": 1_000_499}, "updated_at_unix_ms"),
        ({"buy_fill_count": 0}, "buy_fill_count"),
        ({"sell_fill_count": -1}, "sell_fill_count"),
    ],
)
def test_position_rejects_invalid_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        _position(**overrides)


def test_open_position_requires_quantity_basis_and_no_close_time():
    with pytest.raises(ValueError, match="OPEN"):
        _position(quantity=0.0)
    with pytest.raises(ValueError, match="OPEN"):
        _position(open_cost_basis_usd=0.0)
    with pytest.raises(ValueError, match="OPEN"):
        _position(closed_at_unix_ms=1_000_600)


def test_closed_position_requires_zero_quantity_basis_and_zero_unrealized():
    closed = _position(
        state=PaperPositionState.CLOSED,
        quantity=0.0,
        open_cost_basis_usd=0.0,
        unrealized_pnl_usd=0.0,
        closed_at_unix_ms=1_001_000,
        updated_at_unix_ms=1_001_000,
    )
    assert closed.state is PaperPositionState.CLOSED
    with pytest.raises(ValueError, match="CLOSED"):
        replace(closed, quantity=1.0)
    with pytest.raises(ValueError, match="CLOSED"):
        replace(closed, open_cost_basis_usd=1.0)
    with pytest.raises(ValueError, match="CLOSED"):
        replace(closed, unrealized_pnl_usd=None)
    with pytest.raises(ValueError, match="closed_at_unix_ms"):
        replace(closed, closed_at_unix_ms=None)


def test_mark_fields_are_paired_and_open_unrealized_reconciles():
    quantity = _position().quantity
    mark_price = 1.10
    unrealized = quantity * mark_price - 501.51
    marked = _position(
        unrealized_pnl_usd=unrealized,
        last_mark_price_usd=mark_price,
        last_mark_at_unix_ms=1_000_700,
        updated_at_unix_ms=1_000_700,
    )
    assert math.isclose(marked.unrealized_pnl_usd, unrealized)
    with pytest.raises(ValueError, match="last_mark"):
        _position(last_mark_price_usd=1.1)
    with pytest.raises(ValueError, match="unrealized_pnl_usd"):
        replace(marked, unrealized_pnl_usd=123.0)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sequence": 0}, "sequence"),
        ({"intent_idempotency_key": ""}, "intent_idempotency_key"),
        ({"mint": ""}, "mint"),
        ({"side": "BUY"}, "side"),
        ({"execution_state": PaperExecutionState.DEFERRED}, "terminal"),
        ({"paper_execution_reason_code": "FILL_COMPLETE"}, "paper_execution_reason_code"),
        ({"ledger_reason_code": "POSITION_OPENED"}, "ledger_reason_code"),
        ({"strategy_name": ""}, "strategy_name"),
        ({"booked_at_unix_ms": -1}, "booked_at_unix_ms"),
        ({"filled_quantity": -1.0}, "filled_quantity"),
        ({"filled_notional_usd": -1.0}, "filled_notional_usd"),
        ({"explicit_cost_usd": -1.0}, "explicit_cost_usd"),
        ({"realized_pnl_delta_usd": math.inf}, "realized_pnl_delta_usd"),
    ],
)
def test_entry_rejects_invalid_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        _entry(**overrides)


def test_failed_entry_requires_zero_fill_values():
    failed = _entry(
        position_id=None,
        execution_state=PaperExecutionState.FAILED,
        paper_execution_reason_code=PaperExecutionReasonCode.ROUTE_UNAVAILABLE,
        ledger_reason_code=PaperLedgerReasonCode.FAILED_EXECUTION_BOOKED,
        filled_quantity=0.0,
        filled_notional_usd=0.0,
        cash_flow_usd=0.0,
        explicit_cost_usd=0.0,
        realized_pnl_delta_usd=0.0,
    )
    assert failed.position_id is None
    with pytest.raises(ValueError, match="FAILED"):
        replace(failed, filled_quantity=1.0)


def test_fill_entry_requires_positive_fill_values():
    with pytest.raises(ValueError, match="PARTIAL/FILLED"):
        _entry(filled_quantity=0.0)
    with pytest.raises(ValueError, match="PARTIAL/FILLED"):
        _entry(filled_notional_usd=0.0)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"starting_cash_usd": -1.0}, "starting_cash_usd"),
        ({"cash_balance_usd": -1.0}, "cash_balance_usd"),
        ({"realized_pnl_usd": math.inf}, "realized_pnl_usd"),
        ({"accumulated_costs_usd": -1.0}, "accumulated_costs_usd"),
        ({"as_of_unix_ms": -1}, "as_of_unix_ms"),
        ({"positions": [_position()]}, "positions"),
        ({"entries": [_entry()]}, "entries"),
        ({"processed_intent_keys": {"intent-1"}}, "processed_intent_keys"),
    ],
)
def test_ledger_rejects_invalid_container_or_numeric_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        _ledger(**overrides)


def test_ledger_reconciliation_rejects_cash_realized_and_cost_drift():
    with pytest.raises(ValueError, match="cash_balance_usd"):
        _ledger(cash_balance_usd=500.0)
    with pytest.raises(ValueError, match="realized_pnl_usd"):
        _ledger(realized_pnl_usd=1.0)
    with pytest.raises(ValueError, match="accumulated_costs_usd"):
        _ledger(accumulated_costs_usd=2.0)


def test_ledger_rejects_duplicate_positions_or_multiple_open_positions_per_mint():
    with pytest.raises(ValueError, match="position_id"):
        _ledger(positions=(_position(), _position()))
    second = _position(position_id="position-2")
    with pytest.raises(ValueError, match="OPEN position"):
        _ledger(positions=(_position(), second))


def test_ledger_rejects_bad_journal_sequence_duplicate_keys_and_processed_mismatch():
    with pytest.raises(ValueError, match="sequence"):
        _ledger(entries=(replace(_entry(), sequence=2),))
    second = replace(_entry(), sequence=2)
    with pytest.raises(ValueError, match="intent"):
        _ledger(entries=(_entry(), second))
    with pytest.raises(ValueError, match="processed_intent_keys"):
        _ledger(processed_intent_keys=frozenset())


def test_ledger_rejects_position_realized_or_cost_totals_not_backed_by_entries():
    with pytest.raises(ValueError, match="position realized_pnl_usd"):
        _ledger(positions=(replace(_position(), realized_pnl_usd=-1.0),))
    with pytest.raises(ValueError, match="position accumulated_costs_usd"):
        _ledger(positions=(replace(_position(), accumulated_costs_usd=2.0),))


def test_ledger_rejects_time_before_entry_or_position_update():
    with pytest.raises(ValueError, match="as_of_unix_ms"):
        _ledger(as_of_unix_ms=1_000_499)


def test_ledger_unrealized_is_none_when_any_open_position_is_unmarked():
    with pytest.raises(ValueError, match="unrealized_pnl_usd"):
        _ledger(unrealized_pnl_usd=0.0)


def test_mark_model_validates_identity_time_and_price():
    mark = PaperPositionMark("position-1", "Mint111", 1_000_700, 1.1)
    assert mark.mark_price_usd == 1.1
    with pytest.raises(ValueError, match="position_id"):
        PaperPositionMark("", "Mint111", 0, 1.0)
    with pytest.raises(ValueError, match="mint"):
        PaperPositionMark("p", "", 0, 1.0)
    with pytest.raises(ValueError, match="observed_at_unix_ms"):
        PaperPositionMark("p", "m", -1, 1.0)
    with pytest.raises(ValueError, match="mark_price_usd"):
        PaperPositionMark("p", "m", 0, 0.0)


def test_finding_and_update_invariants():
    finding = _finding()
    assert finding.code is PaperLedgerReasonCode.POSITION_OPENED
    with pytest.raises(ValueError, match="code"):
        PaperLedgerFinding("POSITION_OPENED", "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="message"):
        PaperLedgerFinding(PaperLedgerReasonCode.POSITION_OPENED, "")

    rejected = PaperLedgerUpdate(
        state=PaperLedgerUpdateState.REJECTED,
        ledger=_ledger(),
        position_id=None,
        cash_delta_usd=0.0,
        realized_pnl_delta_usd=0.0,
        cost_delta_usd=0.0,
        findings=(_finding(PaperLedgerReasonCode.INSUFFICIENT_CASH),),
    )
    assert rejected.cash_delta_usd == 0.0
    with pytest.raises(ValueError, match="zero"):
        replace(rejected, cash_delta_usd=1.0)
    with pytest.raises(ValueError, match="findings"):
        replace(rejected, findings=())

    applied_mark = PaperLedgerUpdate(
        state=PaperLedgerUpdateState.APPLIED,
        ledger=_ledger(),
        position_id="position-1",
        cash_delta_usd=0.0,
        realized_pnl_delta_usd=0.0,
        cost_delta_usd=0.0,
        findings=(_finding(PaperLedgerReasonCode.POSITION_MARKED),),
    )
    assert applied_mark.state is PaperLedgerUpdateState.APPLIED


def test_models_are_frozen_and_expose_no_live_authority():
    with pytest.raises(FrozenInstanceError):
        _position().quantity = 1.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        _ledger().cash_balance_usd = 1.0  # type: ignore[misc]

    forbidden = {
        "private_key",
        "secret",
        "wallet_secret",
        "transaction",
        "signature",
        "live_executor",
        "stop_loss",
        "take_profit",
        "trailing_stop",
    }
    for model in (
        PaperPositionMark,
        PaperPosition,
        PaperLedgerEntry,
        PaperLedger,
        PaperLedgerFinding,
        PaperLedgerUpdate,
    ):
        assert forbidden.isdisjoint(field.name for field in fields(model))
