from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path

from shreks_brain.paper import (
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperLedger,
    PaperLedgerEntry,
    PaperLedgerReasonCode,
    PaperPosition,
    PaperPositionState,
    PaperRiskAccountingFacts,
    derive_paper_risk_accounting_facts,
)
from shreks_brain.risk import TradeSide


TOKEN = "MintRiskFacts"


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
        strategy_name="risk-facts-fixture",
        strategy_version="fixture-v1",
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


def _ledger(*, marked: bool = True, second_close_realized: float = -12.0) -> PaperLedger:
    entries = (
        _entry(
            1,
            "buy-1",
            "p1",
            TradeSide.BUY,
            100,
            100.0,
            -101.0,
            1.0,
            0.0,
            PaperLedgerReasonCode.POSITION_OPENED,
        ),
        _entry(
            2,
            "sell-1",
            "p1",
            TradeSide.SELL,
            200,
            110.0,
            109.0,
            1.0,
            8.0,
            PaperLedgerReasonCode.POSITION_CLOSED,
        ),
        _entry(
            3,
            "buy-2",
            "p2",
            TradeSide.BUY,
            300,
            100.0,
            -101.0,
            1.0,
            0.0,
            PaperLedgerReasonCode.POSITION_OPENED,
        ),
        _entry(
            4,
            "sell-2",
            "p2",
            TradeSide.SELL,
            400,
            90.0,
            89.0,
            1.0,
            second_close_realized,
            PaperLedgerReasonCode.POSITION_CLOSED,
        ),
        _entry(
            5,
            "buy-3",
            "p3",
            TradeSide.BUY,
            450,
            100.0,
            -101.0,
            1.0,
            0.0,
            PaperLedgerReasonCode.POSITION_OPENED,
        ),
    )
    closed_1 = PaperPosition(
        position_id="p1",
        mint=TOKEN,
        state=PaperPositionState.CLOSED,
        quantity=0.0,
        weighted_entry_price_usd=1.0,
        open_cost_basis_usd=0.0,
        realized_pnl_usd=8.0,
        unrealized_pnl_usd=0.0,
        accumulated_costs_usd=2.0,
        opened_at_unix_ms=100,
        updated_at_unix_ms=200,
        closed_at_unix_ms=200,
        last_mark_price_usd=None,
        last_mark_at_unix_ms=None,
        buy_fill_count=1,
        sell_fill_count=1,
    )
    closed_2 = PaperPosition(
        position_id="p2",
        mint=TOKEN,
        state=PaperPositionState.CLOSED,
        quantity=0.0,
        weighted_entry_price_usd=1.0,
        open_cost_basis_usd=0.0,
        realized_pnl_usd=second_close_realized,
        unrealized_pnl_usd=0.0,
        accumulated_costs_usd=2.0,
        opened_at_unix_ms=300,
        updated_at_unix_ms=400,
        closed_at_unix_ms=400,
        last_mark_price_usd=None,
        last_mark_at_unix_ms=None,
        buy_fill_count=1,
        sell_fill_count=1,
    )
    open_3 = PaperPosition(
        position_id="p3",
        mint=TOKEN,
        state=PaperPositionState.OPEN,
        quantity=100.0,
        weighted_entry_price_usd=1.0,
        open_cost_basis_usd=101.0,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=-6.0 if marked else None,
        accumulated_costs_usd=1.0,
        opened_at_unix_ms=450,
        updated_at_unix_ms=500 if marked else 450,
        closed_at_unix_ms=None,
        last_mark_price_usd=0.95 if marked else None,
        last_mark_at_unix_ms=500 if marked else None,
        buy_fill_count=1,
        sell_fill_count=0,
    )
    realized = 8.0 + second_close_realized
    return PaperLedger(
        starting_cash_usd=1_000.0,
        cash_balance_usd=895.0,
        realized_pnl_usd=realized,
        unrealized_pnl_usd=-6.0 if marked else None,
        accumulated_costs_usd=5.0,
        as_of_unix_ms=500,
        positions=(closed_1, closed_2, open_3),
        entries=entries,
        processed_intent_keys=frozenset(
            entry.intent_idempotency_key for entry in entries
        ),
    )


def test_shared_risk_facts_match_existing_observer_accounting_semantics() -> None:
    facts = derive_paper_risk_accounting_facts(
        _ledger(),
        day_started_at_unix_ms=350,
    )

    assert type(facts) is PaperRiskAccountingFacts
    assert facts.open_position_count == 1
    assert facts.aggregate_open_risk_usd == 101.0
    assert facts.daily_realized_pnl_usd == -12.0
    assert math.isclose(
        facts.rolling_drawdown_pct,
        18.0 / 1008.0 * 100.0,
    )
    assert facts.consecutive_losses == 1
    assert facts.last_loss_at_unix_ms == 400
    assert facts == derive_paper_risk_accounting_facts(
        _ledger(),
        day_started_at_unix_ms=350,
    )


def test_unmarked_open_position_keeps_drawdown_unknown() -> None:
    facts = derive_paper_risk_accounting_facts(
        _ledger(marked=False),
        day_started_at_unix_ms=350,
    )

    assert facts.open_position_count == 1
    assert facts.aggregate_open_risk_usd == 101.0
    assert facts.rolling_drawdown_pct is None


def test_explicit_day_boundary_only_selects_daily_realized_journal_deltas() -> None:
    ledger = _ledger()

    since_150 = derive_paper_risk_accounting_facts(
        ledger,
        day_started_at_unix_ms=150,
    )
    since_401 = derive_paper_risk_accounting_facts(
        ledger,
        day_started_at_unix_ms=401,
    )

    assert since_150.daily_realized_pnl_usd == -4.0
    assert since_401.daily_realized_pnl_usd == 0.0
    assert since_150.open_position_count == since_401.open_position_count == 1
    assert since_150.aggregate_open_risk_usd == since_401.aggregate_open_risk_usd
    assert since_150.rolling_drawdown_pct == since_401.rolling_drawdown_pct


def test_newest_non_loss_close_resets_loss_streak() -> None:
    facts = derive_paper_risk_accounting_facts(
        _ledger(second_close_realized=1.0),
        day_started_at_unix_ms=0,
    )

    assert facts.consecutive_losses == 0
    assert facts.last_loss_at_unix_ms is None


def test_observer_risk_builder_delegates_accounting_to_shared_paper_helper() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "observer_campaign"
        / "risk_context.py"
    ).read_text(encoding="utf-8")

    assert "derive_paper_risk_accounting_facts(" in source
    assert "def _rolling_drawdown_pct(" not in source
    assert "def _loss_streak(" not in source


def test_shared_risk_facts_source_has_no_execution_or_external_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "paper"
        / "risk_facts.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "RiskPolicy",
        "execute_paper_intent",
        "execute_fast_paper_buy",
        "requests.",
        "sqlite3",
        "subprocess",
        "RuntimeMode",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source
