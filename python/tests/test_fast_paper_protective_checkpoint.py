from __future__ import annotations

from dataclasses import replace
import hashlib
import sqlite3

import pytest

from shreks_brain.exits import ExitExecutionContext, ExitPolicy, ExitRouteState
from shreks_brain.fast_paper import (
    FAST_PAPER_PROTECTIVE_EXIT_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperMaterialUpdate,
    FastPaperPositionActionApproval,
    FastPaperPositionActionPolicy,
    FastPaperProtectiveExitPolicy,
    create_fast_paper_loop_state,
    create_fast_paper_position_action_state,
    create_fast_paper_protective_exit_state,
    run_fast_paper_protective_event,
)
from shreks_brain.features import FEATURE_SCHEMA_VERSION, FeatureVector
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerUpdateState,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
)
from shreks_brain.paper_validation import (
    FAST_PAPER_CHECKPOINT_SCHEMA_VERSION,
    FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION,
    FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION,
    FAST_PAPER_RUNTIME_STATE_VERSION,
    FastPaperCheckpointError,
    FastPaperProtectedCheckpointRecord,
    FastPaperProtectedRuntimeState,
    FastPaperRuntimeState,
    decode_fast_paper_protected_checkpoint,
    encode_fast_paper_protected_checkpoint,
    load_latest_fast_paper_checkpoint,
    load_latest_fast_paper_protected_checkpoint,
    save_fast_paper_checkpoint,
    save_fast_paper_protected_checkpoint,
    validate_fast_paper_protected_restart_equivalence,
)
from shreks_brain.risk import FAST_LANE_SCORE_POLICY_SENTINEL, TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision


MINT = "mint-protected"
QUOTE_MINT = "quote-a"
MARKET_KEY = "pump:mint-protected:quote-a"
T0 = 10_000

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


def _migrate(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(CHECKPOINT_DDL)


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="fl7.6-fill-v1",
        assumed_latency_ms=0,
        max_quote_lag_ms=5_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
    )


def _position_policy() -> FastPaperPositionActionPolicy:
    return FastPaperPositionActionPolicy(
        version="fl7.6-position-v1",
        max_slippage_bps=500,
    )


def _open_ledger() -> PaperLedger:
    ledger = create_paper_ledger(10_000.0, T0)
    intent = TradeIntent(
        mint=MINT,
        side=TradeSide.BUY,
        requested_notional_usd=1_000.0,
        max_slippage_bps=500,
        strategy_name="fixture",
        strategy_version="1",
        score_policy_version=FAST_LANE_SCORE_POLICY_SENTINEL,
        decision_policy_version="assessment-v1",
        risk_policy_version="risk-v1",
        reason="open-protected-position",
        idempotency_key="open-protected-position",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=T0,
    )
    quote = PaperQuote(
        provider="fixture",
        mint=MINT,
        observed_at_unix_ms=T0 + 100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=10.0,
        execution_price_usd=10.0,
        quoted_notional_usd=1_000.0,
        available_notional_usd=1_000.0,
    )
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=T0 + 100,
            processed_intent_keys=ledger.processed_intent_keys,
            quote=quote,
        ),
        _fill_policy(),
    )
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    return update.ledger


def _position(ledger: PaperLedger):
    positions = tuple(
        position for position in ledger.positions if position.state is PaperPositionState.OPEN
    )
    assert len(positions) == 1
    return positions[0]


def _exit_policy() -> ExitPolicy:
    return ExitPolicy(
        version="c4-protected-v1",
        required_feature_schema_version=FEATURE_SCHEMA_VERSION,
        max_market_data_age_ms=1_000,
        max_execution_evidence_age_ms=1_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(),
        trailing_activation_return_pct=20.0,
        trailing_stop_drawdown_pct=5.0,
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


def _protective_policy() -> FastPaperProtectiveExitPolicy:
    return FastPaperProtectiveExitPolicy(
        version="protective-v1",
        exit_policy=_exit_policy(),
    )


def _features(*, at: int, price: float) -> FeatureVector:
    return FeatureVector(
        schema_version=FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=at,
        source_observed_at_unix_ms=at,
        source_age_ms=0,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=10.0,
        price_usd=price,
        liquidity_usd=10_000.0,
        liquidity_change_5m_pct=None,
        exit_price_impact_pct=None,
        volume_m5_usd=None,
        volume_h1_usd=None,
        volume_velocity_ratio=None,
        tx_count_m5=None,
        tx_count_h1=None,
        buy_fraction_m5=None,
        buy_fraction_h1=None,
        buy_sell_ratio_m5=None,
        buy_sell_ratio_h1=None,
        buy_pressure_acceleration=None,
        return_1m_pct=None,
        return_5m_pct=None,
        return_15m_pct=None,
        momentum_acceleration_1m_vs_5m=None,
        distance_from_local_high_pct=None,
        range_position_pct=None,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )


def _context(*, at: int, market_value: float) -> ExitExecutionContext:
    return ExitExecutionContext(
        as_of_unix_ms=at,
        observed_at_unix_ms=at,
        route_state=ExitRouteState.AVAILABLE,
        available_exit_notional_usd=market_value,
        expected_exit_price_impact_pct=1.0,
        price_impact_notional_usd=market_value,
        wallet_distribution_detected=None,
        global_halt_active=False,
    )


def _update(*, event_id: str, sequence: int, at: int) -> FastPaperMaterialUpdate:
    return FastPaperMaterialUpdate(
        source_event_id=event_id,
        market_key=MARKET_KEY,
        source_sequence=sequence,
        as_of_unix_ms=at,
        state_version="fast-state-v1",
        is_material=True,
        material_reason="protective-state-change",
    )


def _hold_approval(
    ledger: PaperLedger,
    update: FastPaperMaterialUpdate,
) -> FastPaperPositionActionApproval:
    position = _position(ledger)
    return FastPaperPositionActionApproval(
        version="fl7.4-v1",
        assessment=FastPaperActionAssessment(
            version="assessment-v1",
            source_event_id=update.source_event_id,
            market_key=update.market_key,
            source_sequence=update.source_sequence,
            as_of_unix_ms=update.as_of_unix_ms,
            strategy_family="longer-runner",
            strategy_version="1",
            action=FastPaperAction.HOLD,
            reasons=("continue-holding",),
        ),
        position_id=position.position_id,
        mint=position.mint,
        quote_mint=QUOTE_MINT,
        state_version=update.state_version,
        target_base_quantity=None,
    )


def _base_runtime(
    *,
    ledger: PaperLedger,
    event_loop_state=None,
    at: int | None = None,
) -> FastPaperRuntimeState:
    position = _position(ledger)
    if event_loop_state is None:
        event_loop_state = create_fast_paper_loop_state()
    if at is None:
        at = ledger.as_of_unix_ms
    return FastPaperRuntimeState(
        version=FAST_PAPER_RUNTIME_STATE_VERSION,
        as_of_unix_ms=at,
        event_loop_state=event_loop_state,
        ledger=ledger,
        fill_policy=_fill_policy(),
        position_action_policy=_position_policy(),
        pending_buy=None,
        position_action_states=(
            create_fast_paper_position_action_state(position.position_id, at),
        ),
    )


def _protected_runtime() -> FastPaperProtectedRuntimeState:
    ledger = _open_ledger()
    position = _position(ledger)
    policy = _protective_policy()
    protective_state = create_fast_paper_protective_exit_state(position, policy)
    return FastPaperProtectedRuntimeState(
        version=FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION,
        base_runtime_state=_base_runtime(ledger=ledger),
        protective_policy=policy,
        protective_states=(protective_state,),
    )


def test_fl7_6_protected_checkpoint_versions_are_stable_without_changing_fl7_5() -> None:
    assert FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION == "fl7.6-v1"
    assert (
        FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION
        == "fl7.6-fast-paper-protected-state-v1"
    )
    assert FAST_PAPER_RUNTIME_STATE_VERSION == "fl7.5-v1"
    assert FAST_PAPER_CHECKPOINT_SCHEMA_VERSION == "fl7.5-fast-paper-state-v1"
    assert FAST_PAPER_PROTECTIVE_EXIT_VERSION == "fl7.6-v1"


def test_protected_runtime_requires_exact_open_position_state_coverage() -> None:
    state = _protected_runtime()
    protective = state.protective_states[0]

    with pytest.raises(ValueError, match="cover|OPEN|position"):
        replace(state, protective_states=())
    with pytest.raises(ValueError, match="unique|duplicate|position"):
        replace(state, protective_states=(protective, protective))


def test_protected_runtime_rejects_state_identity_policy_time_and_high_water_conflicts() -> None:
    state = _protected_runtime()
    protective = state.protective_states[0]
    entry = state.base_runtime_state.ledger.positions[0].weighted_entry_price_usd
    shifted_time = protective.initialized_at_unix_ms + 1

    invalid_states = (
        replace(protective, mint="other-mint"),
        replace(protective, policy_version="other-policy"),
        replace(
            protective,
            initialized_at_unix_ms=shifted_time,
            last_evaluated_at_unix_ms=shifted_time,
            high_water_at_unix_ms=shifted_time,
        ),
        replace(
            protective,
            last_evaluated_at_unix_ms=state.base_runtime_state.as_of_unix_ms + 1,
        ),
        replace(
            protective,
            high_water_price_usd=entry - 1.0,
        ),
    )
    for invalid in invalid_states:
        with pytest.raises(ValueError, match="mint|policy|initialized|time|high.water|entry"):
            replace(state, protective_states=(invalid,))


def test_protected_checkpoint_payload_is_canonical_and_round_trips_high_water_exactly() -> None:
    state = _protected_runtime()
    protective = state.protective_states[0]
    raised = replace(
        protective,
        last_evaluated_at_unix_ms=state.base_runtime_state.as_of_unix_ms,
        high_water_price_usd=12.3456789012345,
        high_water_at_unix_ms=state.base_runtime_state.as_of_unix_ms,
    )
    state = replace(state, protective_states=(raised,))

    first = encode_fast_paper_protected_checkpoint(
        "protected-run",
        7,
        state,
        state.base_runtime_state.as_of_unix_ms + 100,
    )
    second = encode_fast_paper_protected_checkpoint(
        "protected-run",
        7,
        state,
        state.base_runtime_state.as_of_unix_ms + 100,
    )

    assert first == second
    assert b" " not in first
    record = decode_fast_paper_protected_checkpoint(first)
    assert isinstance(record, FastPaperProtectedCheckpointRecord)
    assert record.checkpoint_schema_version == FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION
    assert record.payload_sha256 == hashlib.sha256(first).hexdigest()
    assert record.state == state
    assert record.state.protective_states[0].high_water_price_usd.hex() == raised.high_water_price_usd.hex()


def test_protected_checkpoint_schema_namespace_cannot_mix_with_fl7_5_or_legacy(tmp_path) -> None:
    database = tmp_path / "protected-schema.sqlite3"
    _migrate(database)
    protected = _protected_runtime()
    base = protected.base_runtime_state
    created_at = protected.base_runtime_state.as_of_unix_ms + 100

    save_fast_paper_checkpoint(database, "fast-run", 1, base, created_at)
    with pytest.raises(FastPaperCheckpointError, match="schema|namespace|run_id"):
        save_fast_paper_protected_checkpoint(
            database,
            "fast-run",
            2,
            protected,
            created_at,
        )
    with pytest.raises(FastPaperCheckpointError, match="schema|namespace|run_id"):
        load_latest_fast_paper_protected_checkpoint(database, "fast-run")

    save_fast_paper_protected_checkpoint(
        database,
        "protected-run",
        1,
        protected,
        created_at,
    )
    with pytest.raises(FastPaperCheckpointError, match="schema|namespace|run_id"):
        load_latest_fast_paper_checkpoint(database, "protected-run")
    with pytest.raises(FastPaperCheckpointError, match="schema|namespace|run_id"):
        save_fast_paper_checkpoint(database, "protected-run", 2, base, created_at)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO paper_loop_checkpoints (
                   run_id, sequence, checkpoint_schema_version,
                   state_as_of_unix_ms, created_at_unix_ms,
                   payload_sha256, payload_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "legacy-run",
                1,
                "c6-paper-state-v1",
                T0,
                T0,
                "0" * 64,
                "{}",
            ),
        )
    with pytest.raises(FastPaperCheckpointError, match="schema|namespace|run_id"):
        load_latest_fast_paper_protected_checkpoint(database, "legacy-run")
    with pytest.raises(FastPaperCheckpointError, match="schema|namespace|run_id"):
        save_fast_paper_protected_checkpoint(
            database,
            "legacy-run",
            2,
            protected,
            created_at,
        )


def test_file_backed_restart_preserves_trailing_high_water_and_still_triggers_sell(tmp_path) -> None:
    database = tmp_path / "protected-restart.sqlite3"
    _migrate(database)
    ledger = _open_ledger()
    position = _position(ledger)
    policy = _protective_policy()
    initial_protective = create_fast_paper_protective_exit_state(position, policy)

    high_update = _update(event_id="event-high", sequence=1, at=T0 + 200)
    high = run_fast_paper_protective_event(
        state=create_fast_paper_loop_state(),
        update=high_update,
        position=position,
        features=_features(at=T0 + 200, price=12.5),
        context=_context(at=T0 + 200, market_value=1_250.0),
        protective_state=initial_protective,
        protective_policy=policy,
        strategy_evaluator=lambda update: _hold_approval(ledger, update),
    )
    assert high.protective_triggered is False
    assert high.next_protective_state.high_water_price_usd == 12.5

    base = _base_runtime(
        ledger=ledger,
        event_loop_state=high.event_result.next_state,
        at=T0 + 200,
    )
    expected = FastPaperProtectedRuntimeState(
        version=FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION,
        base_runtime_state=base,
        protective_policy=policy,
        protective_states=(high.next_protective_state,),
    )
    save_fast_paper_protected_checkpoint(
        database,
        "restart-run",
        1,
        expected,
        T0 + 300,
    )

    restored_record = load_latest_fast_paper_protected_checkpoint(database, "restart-run")
    assert restored_record is not None
    restored = restored_record.state
    report = validate_fast_paper_protected_restart_equivalence(expected, restored)
    assert report.equivalent
    assert report.expected_state_sha256 == report.restored_state_sha256
    assert restored.protective_states[0].high_water_price_usd == 12.5

    drawdown_update = _update(event_id="event-drawdown", sequence=2, at=T0 + 400)
    result = run_fast_paper_protective_event(
        state=restored.base_runtime_state.event_loop_state,
        update=drawdown_update,
        position=position,
        features=_features(at=T0 + 400, price=11.5),
        context=_context(at=T0 + 400, market_value=1_150.0),
        protective_state=restored.protective_states[0],
        protective_policy=restored.protective_policy,
        strategy_evaluator=lambda update: _hold_approval(ledger, update),
    )

    assert result.protective_triggered is True
    assert result.applied_approval is not None
    assert result.applied_approval.assessment.action is FastPaperAction.SELL
    assert result.applied_approval.assessment.reasons[0] == "protective:TRAILING_STOP_TRIGGERED"
    assert result.applied_approval.target_base_quantity == position.quantity
