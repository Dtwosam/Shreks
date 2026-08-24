from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
import sqlite3

import pytest

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
from shreks_brain.paper_loop import (
    ManagedPaperPosition,
    PaperLoopPolicy,
    PaperLoopState,
    PendingPaperEntry,
)
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    PaperCheckpointError,
    decode_paper_checkpoint,
    encode_paper_checkpoint,
    load_latest_paper_checkpoint,
    save_paper_checkpoint,
    validate_restart_equivalence,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


T0 = 2_000_000
CHECKPOINT_SCHEMA_VERSION = "c6-paper-state-v1"
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
        version="paper-c6-checkpoint",
        assumed_latency_ms=0,
        max_quote_lag_ms=5_000,
        swap_fee_bps=75,
        network_fee_usd=0.123456789,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.125,
    )


def _exit_policy() -> ExitPolicy:
    return ExitPolicy(
        version="exit-c6-checkpoint",
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=12.5,
        take_profit_levels=(
            TakeProfitLevel("tp1", 20.0, 0.5),
            TakeProfitLevel("tp2", 50.0, 1.0),
        ),
        trailing_activation_return_pct=17.5,
        trailing_stop_drawdown_pct=7.25,
        max_hold_seconds=3_600,
        flow_exit_max_buy_fraction_m5=0.35,
        flow_exit_max_buy_pressure_acceleration=-0.20,
        momentum_exit_max_return_1m_pct=-4.0,
        momentum_exit_max_return_5m_pct=-7.0,
        min_liquidity_usd=8_000.0,
        max_exit_price_impact_pct=6.5,
        min_exit_capacity_fraction=0.60,
        wallet_distribution_enabled=False,
    )


def _intent(mint: str, key: str, at: int) -> TradeIntent:
    return TradeIntent(
        mint=mint,
        side=TradeSide.BUY,
        requested_notional_usd=123.456789,
        max_slippage_bps=750,
        strategy_name="c6-checkpoint-fixture",
        strategy_version="fixture-v1",
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        risk_policy_version="risk-v1",
        reason="C6_CHECKPOINT_FIXTURE",
        idempotency_key=key,
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=at,
    )


def _state() -> PaperLoopState:
    fill_policy = _fill_policy()
    ledger = create_paper_ledger(10_000.0, T0)
    intent = _intent("MintPersistedA", "persisted-a-buy", T0 + 100)
    quote = PaperQuote(
        provider="c6-checkpoint",
        mint=intent.mint,
        observed_at_unix_ms=T0 + 100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=1.0,
        execution_price_usd=1.0,
        quoted_notional_usd=intent.requested_notional_usd,
        available_notional_usd=intent.requested_notional_usd,
    )
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=T0 + 100,
            processed_intent_keys=ledger.processed_intent_keys,
            quote=quote,
        ),
        fill_policy,
    )
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    position = update.ledger.positions[0]
    marked = mark_paper_position(
        update.ledger,
        PaperPositionMark(
            position.position_id,
            position.mint,
            T0 + 200,
            1.234567890123,
        ),
    )
    assert marked.state is PaperLedgerUpdateState.APPLIED
    position = marked.ledger.positions[0]

    exit_policy = _exit_policy()
    exit_state = replace(
        create_exit_state(position, exit_policy),
        completed_take_profit_levels=frozenset({"tp1"}),
    )
    managed = ManagedPaperPosition(
        position_id=position.position_id,
        exit_policy=exit_policy,
        exit_state=exit_state,
    )
    pending = PendingPaperEntry(
        intent=_intent("MintPendingB", "pending-b-buy", T0 + 150),
        exit_policy=exit_policy,
    )
    return PaperLoopState(
        ledger=marked.ledger,
        loop_policy=PaperLoopPolicy("loop-c6-checkpoint", 875),
        paper_fill_policy=fill_policy,
        managed_positions=(managed,),
        pending_entry=pending,
        last_cycle_at_unix_ms=T0 + 200,
    )


def _migrate(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(CHECKPOINT_DDL)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def test_canonical_payload_is_byte_stable_and_round_trips_exact_state() -> None:
    state = _state()
    first = encode_paper_checkpoint("run-alpha", 7, state, T0 + 300)
    second = encode_paper_checkpoint("run-alpha", 7, state, T0 + 300)
    assert isinstance(first, bytes)
    assert first == second
    assert b" " not in first

    record = decode_paper_checkpoint(first)
    assert record.run_id == "run-alpha"
    assert record.sequence == 7
    assert record.checkpoint_schema_version == CHECKPOINT_SCHEMA_VERSION
    assert record.state_as_of_unix_ms == state.last_cycle_at_unix_ms
    assert record.created_at_unix_ms == T0 + 300
    assert record.payload_sha256 == hashlib.sha256(first).hexdigest()
    assert record.state == state
    assert record.state.paper_fill_policy.network_fee_usd.hex() == (
        state.paper_fill_policy.network_fee_usd.hex()
    )
    assert record.state.managed_positions[0].exit_state.completed_take_profit_levels == (
        frozenset({"tp1"})
    )
    assert record.state.pending_entry == state.pending_entry


def test_codec_rejects_unknown_or_malformed_type_tags() -> None:
    payload = encode_paper_checkpoint("run-alpha", 1, _state(), T0 + 300)
    envelope = json.loads(payload)
    envelope["state"]["$type"] = "os.system"
    with pytest.raises(PaperCheckpointError, match="unknown"):
        decode_paper_checkpoint(_canonical_json(envelope))

    envelope = json.loads(payload)
    envelope["state"]["unexpected"] = "not-allowed"
    with pytest.raises(PaperCheckpointError, match="malformed"):
        decode_paper_checkpoint(_canonical_json(envelope))


def test_decode_verifies_checksum_before_state_decode() -> None:
    payload = encode_paper_checkpoint("run-alpha", 1, _state(), T0 + 300)
    with pytest.raises(PaperCheckpointError, match="checksum"):
        decode_paper_checkpoint(payload, expected_sha256="0" * 64)


def test_checkpoint_time_cannot_precede_loop_state() -> None:
    state = _state()
    with pytest.raises(PaperCheckpointError, match="precede"):
        encode_paper_checkpoint(
            "run-alpha",
            1,
            state,
            state.last_cycle_at_unix_ms - 1,
        )


def test_save_requires_rust_owned_migration_table(tmp_path) -> None:
    database = tmp_path / "unmigrated.db"
    sqlite3.connect(database).close()
    with pytest.raises(PaperCheckpointError, match="migration"):
        save_paper_checkpoint(database, "run-alpha", 1, _state(), T0 + 300)


def test_save_is_atomic_idempotent_monotonic_and_collision_safe(tmp_path) -> None:
    database = tmp_path / "paper.db"
    _migrate(database)
    state = _state()

    first = save_paper_checkpoint(database, "run-alpha", 3, state, T0 + 300)
    duplicate = save_paper_checkpoint(database, "run-alpha", 3, state, T0 + 300)
    assert duplicate == first

    with sqlite3.connect(database) as connection:
        row_count = connection.execute(
            "SELECT COUNT(*) FROM paper_loop_checkpoints WHERE run_id = ?",
            ("run-alpha",),
        ).fetchone()[0]
    assert row_count == 1

    changed = replace(state, loop_policy=PaperLoopPolicy("loop-c6-other", 875))
    with pytest.raises(PaperCheckpointError, match="collision"):
        save_paper_checkpoint(database, "run-alpha", 3, changed, T0 + 300)

    later = replace(state, last_cycle_at_unix_ms=T0 + 400)
    saved_later = save_paper_checkpoint(database, "run-alpha", 5, later, T0 + 500)
    assert saved_later.sequence == 5
    with pytest.raises(PaperCheckpointError, match="monotonic"):
        save_paper_checkpoint(database, "run-alpha", 4, later, T0 + 500)


def test_latest_load_rejects_row_envelope_mismatch_and_checksum_corruption(tmp_path) -> None:
    database = tmp_path / "paper.db"
    _migrate(database)
    state = _state()
    save_paper_checkpoint(database, "run-alpha", 1, state, T0 + 300)
    save_paper_checkpoint(database, "run-alpha", 2, state, T0 + 300)

    latest = load_latest_paper_checkpoint(database, "run-alpha")
    assert latest is not None
    assert latest.sequence == 2
    assert latest.state == state
    assert load_latest_paper_checkpoint(database, "missing-run") is None

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE paper_loop_checkpoints SET state_as_of_unix_ms = state_as_of_unix_ms + 1 WHERE run_id = ? AND sequence = 2",
            ("run-alpha",),
        )
        connection.commit()
    with pytest.raises(PaperCheckpointError, match="metadata"):
        load_latest_paper_checkpoint(database, "run-alpha")

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE paper_loop_checkpoints SET state_as_of_unix_ms = ? WHERE run_id = ? AND sequence = 2",
            (state.last_cycle_at_unix_ms, "run-alpha"),
        )
        connection.execute(
            "UPDATE paper_loop_checkpoints SET payload_sha256 = ? WHERE run_id = ? AND sequence = 2",
            ("f" * 64, "run-alpha"),
        )
        connection.commit()
    with pytest.raises(PaperCheckpointError, match="checksum"):
        load_latest_paper_checkpoint(database, "run-alpha")


def test_file_backed_close_reopen_restores_exact_state_and_restart_report(tmp_path) -> None:
    database = tmp_path / "restart.db"
    _migrate(database)
    expected = _state()
    saved = save_paper_checkpoint(database, "paper-run", 11, expected, T0 + 300)
    del saved

    restored_record = load_latest_paper_checkpoint(database, "paper-run")
    assert restored_record is not None
    restored = restored_record.state
    assert restored == expected

    report = validate_restart_equivalence(expected, restored)
    assert report.equivalent
    assert report.differences == ()
    assert report.expected_state_sha256 == report.restored_state_sha256
    assert report.expected_accounting.status is AccountingValidationStatus.RECONCILED
    assert report.restored_accounting == report.expected_accounting
    assert math.isclose(
        report.restored_accounting.net_pnl_usd or 0.0,
        report.expected_accounting.net_pnl_usd or 0.0,
        rel_tol=1e-12,
        abs_tol=1e-9,
    )


def test_restart_report_detects_any_exact_state_change() -> None:
    expected = _state()
    restored = replace(
        expected,
        loop_policy=PaperLoopPolicy("loop-c6-changed", 875),
    )
    report = validate_restart_equivalence(expected, restored)
    assert not report.equivalent
    assert "STATE_MISMATCH" in report.differences
    assert report.expected_state_sha256 != report.restored_state_sha256
