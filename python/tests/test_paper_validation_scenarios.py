from __future__ import annotations

import sqlite3

import pytest

from shreks_brain.exits import ExitExecutionContext, ExitPolicy, ExitRouteState, create_exit_state
from shreks_brain.features import FeatureVector
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperFillPolicy,
    PaperLedgerReasonCode,
    PaperLedgerUpdateState,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
)
from shreks_brain.paper_loop import (
    ManagedPaperPosition,
    PaperCycleInput,
    PaperExitObservation,
    PaperLoopPolicy,
    create_paper_loop_state,
    run_paper_cycle,
)
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    load_latest_paper_checkpoint,
    save_paper_checkpoint,
    validate_paper_accounting,
    validate_restart_equivalence,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision


T0 = 3_000_000
CHECKPOINT_DDL = """
CREATE TABLE paper_loop_checkpoints (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    checkpoint_schema_version TEXT NOT NULL,
    state_as_of_unix_ms INTEGER NOT NULL CHECK (state_as_of_unix_ms >= 0),
    created_at_unix_ms INTEGER NOT NULL CHECK (created_at_unix_ms >= 0),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
);
CREATE INDEX idx_paper_loop_checkpoints_run_latest
    ON paper_loop_checkpoints (run_id, sequence DESC);
"""


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-c6-scenario",
        assumed_latency_ms=0,
        max_quote_lag_ms=5_000,
        swap_fee_bps=50,
        network_fee_usd=0.02,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.10,
    )


def _intent(mint: str, side: TradeSide, notional: float, key: str, at: int) -> TradeIntent:
    return TradeIntent(
        mint=mint,
        side=side,
        requested_notional_usd=notional,
        max_slippage_bps=500,
        strategy_name="c6-validation",
        strategy_version="scenario-v1",
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        risk_policy_version="risk-v1",
        reason="C6_VALIDATION_SCENARIO",
        idempotency_key=key,
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=at,
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
            provider="c6-validation",
            mint=mint,
            observed_at_unix_ms=at,
            state=state,
            reference_price_usd=price,
            execution_price_usd=price,
            quoted_notional_usd=50_000.0,
            available_notional_usd=50_000.0,
        )
    return PaperQuote(
        provider="c6-validation",
        mint=mint,
        observed_at_unix_ms=at,
        state=state,
        reference_price_usd=None,
        execution_price_usd=None,
        quoted_notional_usd=None,
        available_notional_usd=None,
    )


def _book(ledger, intent: TradeIntent, quote: PaperQuote):
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=quote.observed_at_unix_ms,
            processed_intent_keys=ledger.processed_intent_keys,
            quote=quote,
        ),
        _fill_policy(),
    )
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    return update.ledger, execution


def _exit_policy() -> ExitPolicy:
    return ExitPolicy(
        version="exit-c6-hold-only",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
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


def _features(at: int, price: float) -> FeatureVector:
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=at,
        source_observed_at_unix_ms=at,
        source_age_ms=0,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=600.0,
        price_usd=price,
        liquidity_usd=100_000.0,
        liquidity_change_5m_pct=0.0,
        exit_price_impact_pct=1.0,
        volume_m5_usd=10_000.0,
        volume_h1_usd=50_000.0,
        volume_velocity_ratio=1.0,
        tx_count_m5=50,
        tx_count_h1=250,
        buy_fraction_m5=0.50,
        buy_fraction_h1=0.50,
        buy_sell_ratio_m5=1.0,
        buy_sell_ratio_h1=1.0,
        buy_pressure_acceleration=0.0,
        return_1m_pct=0.0,
        return_5m_pct=0.0,
        return_15m_pct=0.0,
        momentum_acceleration_1m_vs_5m=0.0,
        distance_from_local_high_pct=-1.0,
        range_position_pct=50.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )


def _observation(managed: ManagedPaperPosition, at: int, price: float) -> PaperExitObservation:
    return PaperExitObservation(
        position_id=managed.position_id,
        features=_features(at, price),
        execution_context=ExitExecutionContext(
            as_of_unix_ms=at,
            observed_at_unix_ms=at,
            route_state=ExitRouteState.AVAILABLE,
            available_exit_notional_usd=None,
            expected_exit_price_impact_pct=None,
            price_impact_notional_usd=None,
            wallet_distribution_detected=None,
            global_halt_active=False,
        ),
    )


def _managed_open_positions(ledger):
    policy = _exit_policy()
    return tuple(
        ManagedPaperPosition(
            position_id=position.position_id,
            exit_policy=policy,
            exit_state=create_exit_state(position, policy),
        )
        for position in ledger.positions
        if position.state is PaperPositionState.OPEN
    )


def _migrate(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(CHECKPOINT_DDL)


def test_extended_accounting_history_survives_restart_and_c5_continues(tmp_path) -> None:
    ledger = create_paper_ledger(20_000.0, T0)

    # Winning lifecycle with a genuine partial reduction.
    win_buy = _intent("MintWin", TradeSide.BUY, 100.0, "win-buy", T0 + 100)
    ledger, _ = _book(ledger, win_buy, _quote("MintWin", T0 + 100, 1.0))
    ledger, _ = _book(
        ledger,
        _intent("MintWin", TradeSide.SELL, 50.0, "win-partial", T0 + 200),
        _quote("MintWin", T0 + 200, 1.25),
    )
    ledger, _ = _book(
        ledger,
        _intent("MintWin", TradeSide.SELL, 78.0, "win-close", T0 + 300),
        _quote("MintWin", T0 + 300, 1.30),
    )

    # Losing lifecycle, including a failed-after-submission cost before close.
    loss_buy = _intent("MintLoss", TradeSide.BUY, 100.0, "loss-buy", T0 + 400)
    ledger, _ = _book(ledger, loss_buy, _quote("MintLoss", T0 + 400, 1.0))
    ledger, failed_execution = _book(
        ledger,
        _intent("MintLoss", TradeSide.SELL, 100.0, "loss-failed", T0 + 500),
        _quote(
            "MintLoss",
            T0 + 500,
            1.0,
            state=PaperQuoteState.FAILED_AFTER_SUBMISSION,
        ),
    )
    assert failed_execution.fill is None
    ledger, _ = _book(
        ledger,
        _intent("MintLoss", TradeSide.SELL, 80.0, "loss-close", T0 + 600),
        _quote("MintLoss", T0 + 600, 0.80),
    )

    # Two simultaneous OPEN positions are then handed to C5 for marking.
    open_a = _intent("MintOpenA", TradeSide.BUY, 200.0, "open-a", T0 + 700)
    ledger, _ = _book(ledger, open_a, _quote("MintOpenA", T0 + 700, 1.0))
    open_b = _intent("MintOpenB", TradeSide.BUY, 300.0, "open-b", T0 + 800)
    ledger, open_b_execution = _book(
        ledger,
        open_b,
        _quote("MintOpenB", T0 + 800, 1.0),
    )
    state = create_paper_loop_state(
        ledger,
        PaperLoopPolicy("loop-c6-validation", 500),
        _fill_policy(),
        managed_positions=_managed_open_positions(ledger),
    )
    first_cycle_at = T0 + 900
    first_cycle = run_paper_cycle(
        state,
        PaperCycleInput(
            first_cycle_at,
            (),
            tuple(
                _observation(managed, first_cycle_at, 1.10)
                for managed in state.managed_positions
            ),
            (),
        ),
    )
    before_restart = first_cycle.next_state
    before_report = validate_paper_accounting(before_restart)
    assert before_report.status is AccountingValidationStatus.RECONCILED
    assert before_report.lifecycle_count == 4
    assert before_report.closed_position_count == 2
    assert before_report.open_position_count == 2
    assert before_report.partial_reduction_count == 1
    assert before_report.terminal_failure_count == 1
    assert before_report.winning_closed_count == 1
    assert before_report.losing_closed_count == 1
    assert before_report.open_market_value_usd == pytest.approx(550.0)
    assert before_report.equity_usd is not None

    database = tmp_path / "c6-restart.db"
    _migrate(database)
    save_paper_checkpoint(
        database,
        "extended-paper-run",
        1,
        before_restart,
        first_cycle_at + 50,
    )

    # A new SQLite connection restores exact immutable C5 state.
    restored_record = load_latest_paper_checkpoint(database, "extended-paper-run")
    assert restored_record is not None
    restored = restored_record.state
    restart_report = validate_restart_equivalence(before_restart, restored)
    assert restart_report.equivalent

    # Replaying an already terminal C3 intent cannot double-book after restart.
    duplicate = apply_paper_execution(restored.ledger, open_b, open_b_execution)
    assert duplicate.state is PaperLedgerUpdateState.REJECTED
    assert duplicate.ledger == restored.ledger
    assert duplicate.findings[0].code is PaperLedgerReasonCode.DUPLICATE_TERMINAL_INTENT

    # C5 continues from the restored state and advances both marks independently.
    second_cycle_at = T0 + 1_000
    continued = run_paper_cycle(
        restored,
        PaperCycleInput(
            second_cycle_at,
            (),
            tuple(
                _observation(managed, second_cycle_at, 1.15)
                for managed in restored.managed_positions
            ),
            (),
        ),
    )
    assert len(continued.next_state.managed_positions) == 2
    open_positions = tuple(
        position
        for position in continued.next_state.ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    assert len(open_positions) == 2
    assert all(position.last_mark_price_usd == pytest.approx(1.15) for position in open_positions)

    save_paper_checkpoint(
        database,
        "extended-paper-run",
        2,
        continued.next_state,
        second_cycle_at + 50,
    )
    final_record = load_latest_paper_checkpoint(database, "extended-paper-run")
    assert final_record is not None
    assert final_record.sequence == 2
    assert final_record.state == continued.next_state

    final_report = validate_paper_accounting(final_record.state)
    assert final_report.status is AccountingValidationStatus.RECONCILED
    assert final_report.lifecycle_count == 4
    assert final_report.partial_reduction_count == 1
    assert final_report.terminal_failure_count == 1
    assert final_report.winning_closed_count == 1
    assert final_report.losing_closed_count == 1
    assert final_report.open_position_count == 2
    assert final_report.equity_usd is not None
    assert final_report.net_pnl_usd == pytest.approx(
        final_report.realized_pnl_usd + (final_report.unrealized_pnl_usd or 0.0)
    )
