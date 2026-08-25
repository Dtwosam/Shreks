from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.paper import PaperExecutionState, PaperLedgerReasonCode
from shreks_brain.paper_evaluation.engine import build_evaluated_trades
from shreks_brain.paper_evaluation.models import (
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperOrphanCostEvidence,
    PaperPositionExecutionEvidence,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import TradeSide


RUN = "run-1"
CANDIDATE = "candidate-v1"
SHA = "a" * 64
STRATEGY = "fresh-v1"
MINT = "MintA"
POSITION = "position-a"


def _entry(**overrides: object) -> PaperEntryProvenance:
    values: dict[str, object] = dict(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        intent_idempotency_key="buy-1",
        mint=MINT,
        decision_as_of_unix_ms=900,
        setup_name="fresh_launch_continuation",
        market_regime=MarketRegime.NORMAL,
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        paper_execution_policy_version="paper-v1",
    )
    values.update(overrides)
    return PaperEntryProvenance(**values)  # type: ignore[arg-type]


def _execution(
    *,
    sequence: int,
    side: TradeSide,
    intent_key: str,
    filled_notional: float,
    signed_slippage: float,
    explicit_cost: float,
    state: PaperExecutionState = PaperExecutionState.FILLED,
    position_id: str = POSITION,
    mint: str = MINT,
    **overrides: object,
) -> PaperPositionExecutionEvidence:
    values: dict[str, object] = dict(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        position_id=position_id,
        ledger_sequence=sequence,
        intent_idempotency_key=intent_key,
        mint=mint,
        side=side,
        execution_state=state,
        ledger_reason_code=(
            PaperLedgerReasonCode.POSITION_OPENED
            if side is TradeSide.BUY
            else PaperLedgerReasonCode.POSITION_CLOSED
        ),
        booked_at_unix_ms=1_000 + sequence,
        evaluated_at_unix_ms=1_000 + sequence,
        requested_notional_usd=filled_notional,
        explicit_cost_usd=explicit_cost,
        filled_notional_usd=filled_notional,
        filled_quantity=filled_notional,
        reference_price_usd=1.0,
        execution_price_usd=1.0,
        signed_slippage_usd=signed_slippage,
        quote_provider="paper-test",
        executed_at_unix_ms=1_000 + sequence,
    )
    values.update(overrides)
    return PaperPositionExecutionEvidence(**values)  # type: ignore[arg-type]


def _failed(
    *,
    sequence: int,
    intent_key: str,
    explicit_cost: float,
    side: TradeSide = TradeSide.SELL,
    position_id: str = POSITION,
    **overrides: object,
) -> PaperPositionExecutionEvidence:
    values: dict[str, object] = dict(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        position_id=position_id,
        ledger_sequence=sequence,
        intent_idempotency_key=intent_key,
        mint=MINT,
        side=side,
        execution_state=PaperExecutionState.FAILED,
        ledger_reason_code=PaperLedgerReasonCode.FAILED_EXECUTION_BOOKED,
        booked_at_unix_ms=1_000 + sequence,
        evaluated_at_unix_ms=1_000 + sequence,
        requested_notional_usd=50.0,
        explicit_cost_usd=explicit_cost,
        filled_notional_usd=None,
        filled_quantity=None,
        reference_price_usd=None,
        execution_price_usd=None,
        signed_slippage_usd=None,
        quote_provider=None,
        executed_at_unix_ms=None,
    )
    values.update(overrides)
    return PaperPositionExecutionEvidence(**values)  # type: ignore[arg-type]


def _closure(**overrides: object) -> PaperClosedPositionEvidence:
    values: dict[str, object] = dict(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        position_id=POSITION,
        mint=MINT,
        opened_at_unix_ms=1_001,
        closed_at_unix_ms=2_000,
        realized_pnl_usd=25.0,
        accumulated_costs_usd=2.0,
        buy_fill_count=1,
        sell_fill_count=1,
        closing_ledger_sequence=2,
    )
    values.update(overrides)
    return PaperClosedPositionEvidence(**values)  # type: ignore[arg-type]


def _base_evidence():
    entry = _entry()
    buy = _execution(
        sequence=1,
        side=TradeSide.BUY,
        intent_key="buy-1",
        filled_notional=100.0,
        signed_slippage=5.0,
        explicit_cost=1.0,
    )
    sell = _execution(
        sequence=2,
        side=TradeSide.SELL,
        intent_key="sell-1",
        filled_notional=130.0,
        signed_slippage=-1.0,
        explicit_cost=1.0,
    )
    return (entry,), (buy, sell), (_closure(),), ()


def _build(entry_provenance, executions, closures, orphan_costs=()):
    return build_evaluated_trades(
        RUN,
        CANDIDATE,
        tuple(entry_provenance),
        tuple(executions),
        tuple(closures),
        tuple(orphan_costs),
    )


def test_profitable_trade_uses_exact_e5_economics() -> None:
    entries, executions, closures, orphan = _base_evidence()
    trades = _build(entries, executions, closures, orphan)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.position_id == POSITION
    assert trade.candidate_mint == MINT
    assert trade.setup_name == "fresh_launch_continuation"
    assert trade.market_regime == MarketRegime.NORMAL.value
    assert trade.entry_notional_usd == pytest.approx(100.0)
    assert trade.turnover_usd == pytest.approx(230.0)
    assert trade.execution_friction_usd == pytest.approx(5.0)
    assert trade.explicit_cost_usd == pytest.approx(2.0)
    assert trade.net_pnl_usd == pytest.approx(25.0)
    assert trade.gross_pnl_usd == pytest.approx(32.0)


def test_losing_trade_preserves_negative_net_pnl() -> None:
    entries, executions, closures, orphan = _base_evidence()
    closures = (replace(closures[0], realized_pnl_usd=-12.0),)
    trade = _build(entries, executions, closures, orphan)[0]
    assert trade.net_pnl_usd == pytest.approx(-12.0)
    assert trade.gross_pnl_usd == pytest.approx(-5.0)


def test_partial_buy_and_multiple_sells_reconcile_fill_counts_and_turnover() -> None:
    entry = _entry()
    buy = _execution(
        sequence=1,
        side=TradeSide.BUY,
        intent_key="buy-1",
        filled_notional=80.0,
        signed_slippage=2.0,
        explicit_cost=0.5,
        state=PaperExecutionState.PARTIAL,
    )
    sell_a = _execution(
        sequence=2,
        side=TradeSide.SELL,
        intent_key="sell-a",
        filled_notional=30.0,
        signed_slippage=1.0,
        explicit_cost=0.25,
        state=PaperExecutionState.PARTIAL,
        ledger_reason_code=PaperLedgerReasonCode.POSITION_REDUCED,
    )
    sell_b = _execution(
        sequence=3,
        side=TradeSide.SELL,
        intent_key="sell-b",
        filled_notional=60.0,
        signed_slippage=-2.0,
        explicit_cost=0.25,
        ledger_reason_code=PaperLedgerReasonCode.POSITION_CLOSED,
    )
    closure = _closure(
        realized_pnl_usd=8.0,
        accumulated_costs_usd=1.0,
        buy_fill_count=1,
        sell_fill_count=2,
        closing_ledger_sequence=3,
    )
    trade = _build((entry,), (buy, sell_a, sell_b), (closure,))[0]
    assert trade.entry_notional_usd == pytest.approx(80.0)
    assert trade.turnover_usd == pytest.approx(170.0)
    assert trade.execution_friction_usd == pytest.approx(3.0)
    assert trade.explicit_cost_usd == pytest.approx(1.0)
    assert trade.gross_pnl_usd == pytest.approx(12.0)


def test_favorable_slippage_never_becomes_negative_friction() -> None:
    entries, executions, closures, orphan = _base_evidence()
    executions = tuple(
        replace(value, signed_slippage_usd=-4.0)
        for value in executions
    )
    trade = _build(entries, executions, closures, orphan)[0]
    assert trade.execution_friction_usd == pytest.approx(0.0)
    assert trade.gross_pnl_usd == pytest.approx(27.0)


def test_failed_linked_execution_cost_is_included_in_explicit_costs() -> None:
    entry = _entry()
    buy = _execution(
        sequence=1,
        side=TradeSide.BUY,
        intent_key="buy-1",
        filled_notional=100.0,
        signed_slippage=0.0,
        explicit_cost=1.0,
    )
    failed = _failed(sequence=2, intent_key="sell-failed", explicit_cost=0.5)
    sell = _execution(
        sequence=3,
        side=TradeSide.SELL,
        intent_key="sell-ok",
        filled_notional=110.0,
        signed_slippage=0.0,
        explicit_cost=1.0,
    )
    closure = _closure(
        realized_pnl_usd=7.5,
        accumulated_costs_usd=2.5,
        closing_ledger_sequence=3,
    )
    trade = _build((entry,), (buy, failed, sell), (closure,))[0]
    assert trade.explicit_cost_usd == pytest.approx(2.5)
    assert trade.net_pnl_usd == pytest.approx(7.5)
    assert trade.gross_pnl_usd == pytest.approx(10.0)


def test_incomplete_open_position_is_ignored_until_closure_exists() -> None:
    entries, executions, _, orphan = _base_evidence()
    assert _build(entries, executions[:1], (), orphan) == ()


def test_missing_entry_provenance_fails_closed() -> None:
    _, executions, closures, orphan = _base_evidence()
    with pytest.raises(ValueError, match="provenance"):
        _build((), executions, closures, orphan)


@pytest.mark.parametrize(
    "mutator",
    (
        lambda e, x, c: (e, (replace(x[0], mint="OtherMint"), x[1]), c),
        lambda e, x, c: (e, (replace(x[0], candidate_fingerprint_sha256="b" * 64), x[1]), c),
        lambda e, x, c: (e, x, (replace(c[0], strategy_version="other-strategy"),)),
        lambda e, x, c: ((replace(e[0], candidate_version="other-candidate"),), x, c),
    ),
)
def test_attribution_mismatch_fails_closed(mutator) -> None:
    entries, executions, closures, orphan = _base_evidence()
    entries, executions, closures = mutator(entries, executions, closures)
    with pytest.raises(ValueError):
        _build(entries, executions, closures, orphan)


def test_buy_opener_must_match_entry_provenance_intent_key() -> None:
    entries, executions, closures, orphan = _base_evidence()
    entries = (replace(entries[0], intent_idempotency_key="different-buy"),)
    with pytest.raises(ValueError, match="intent"):
        _build(entries, executions, closures, orphan)


def test_duplicate_or_non_increasing_journal_sequence_fails_closed() -> None:
    entries, executions, closures, orphan = _base_evidence()
    duplicate = (executions[0], replace(executions[1], ledger_sequence=1))
    with pytest.raises(ValueError, match="sequence"):
        _build(entries, duplicate, closures, orphan)
    with pytest.raises(ValueError, match="sequence"):
        _build(entries, tuple(reversed(executions)), closures, orphan)


def test_fill_count_mismatch_fails_closed() -> None:
    entries, executions, closures, orphan = _base_evidence()
    closures = (replace(closures[0], sell_fill_count=2),)
    with pytest.raises(ValueError, match="fill"):
        _build(entries, executions, closures, orphan)


def test_closure_accumulated_cost_must_equal_all_linked_booked_costs() -> None:
    entries, executions, closures, orphan = _base_evidence()
    closures = (replace(closures[0], accumulated_costs_usd=1.5),)
    with pytest.raises(ValueError, match="cost"):
        _build(entries, executions, closures, orphan)


def test_closing_sequence_must_match_final_successful_close() -> None:
    entries, executions, closures, orphan = _base_evidence()
    closures = (replace(closures[0], closing_ledger_sequence=1),)
    with pytest.raises(ValueError, match="closing"):
        _build(entries, executions, closures, orphan)


def test_positive_orphan_cost_blocks_candidate_run_normalization() -> None:
    entries, executions, closures, _ = _base_evidence()
    orphan = PaperOrphanCostEvidence(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        intent_idempotency_key="failed-entry",
        mint="MintFailed",
        explicit_cost_usd=0.01,
        evaluated_at_unix_ms=800,
    )
    with pytest.raises(ValueError, match="orphan"):
        _build(entries, executions, closures, (orphan,))


def test_multiple_closed_trades_emit_in_canonical_closure_order() -> None:
    entries, executions, closures, orphan = _base_evidence()
    entry_b = replace(
        entries[0],
        intent_idempotency_key="buy-b",
        mint="MintB",
        decision_as_of_unix_ms=1_100,
    )
    buy_b = replace(
        executions[0],
        position_id="position-b",
        ledger_sequence=3,
        intent_idempotency_key="buy-b",
        mint="MintB",
        booked_at_unix_ms=1_103,
        evaluated_at_unix_ms=1_103,
        executed_at_unix_ms=1_103,
    )
    sell_b = replace(
        executions[1],
        position_id="position-b",
        ledger_sequence=4,
        intent_idempotency_key="sell-b",
        mint="MintB",
        booked_at_unix_ms=1_104,
        evaluated_at_unix_ms=1_104,
        executed_at_unix_ms=1_104,
    )
    closure_b = replace(
        closures[0],
        position_id="position-b",
        mint="MintB",
        opened_at_unix_ms=1_103,
        closed_at_unix_ms=3_000,
        closing_ledger_sequence=4,
    )
    trades = _build(
        (entries[0], entry_b),
        (executions[0], executions[1], buy_b, sell_b),
        (closures[0], closure_b),
        orphan,
    )
    assert tuple(trade.position_id for trade in trades) == (POSITION, "position-b")


def test_noncanonical_closure_order_fails_closed() -> None:
    entries, executions, closures, orphan = _base_evidence()
    entry_b = replace(
        entries[0],
        intent_idempotency_key="buy-b",
        mint="MintB",
        decision_as_of_unix_ms=1_100,
    )
    buy_b = replace(
        executions[0],
        position_id="position-b",
        ledger_sequence=3,
        intent_idempotency_key="buy-b",
        mint="MintB",
    )
    sell_b = replace(
        executions[1],
        position_id="position-b",
        ledger_sequence=4,
        intent_idempotency_key="sell-b",
        mint="MintB",
    )
    closure_b = replace(
        closures[0],
        position_id="position-b",
        mint="MintB",
        opened_at_unix_ms=1_003,
        closed_at_unix_ms=3_000,
        closing_ledger_sequence=4,
    )
    with pytest.raises(ValueError, match="closure"):
        _build(
            (entries[0], entry_b),
            (executions[0], executions[1], buy_b, sell_b),
            (closure_b, closures[0]),
            orphan,
        )
