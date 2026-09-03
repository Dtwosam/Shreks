from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import sqlite3

import pytest

from shreks_brain.fast_paper import (
    FAST_PAPER_BUY_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperBuyApproval,
    FastPaperMaterialUpdate,
    FastPaperPositionActionPolicy,
    create_fast_paper_loop_state,
    run_fast_paper_event,
)
from shreks_brain.paper import PaperFillPolicy, create_paper_ledger
from shreks_brain.paper_validation import (
    FAST_PAPER_CHECKPOINT_SCHEMA_VERSION,
    FAST_PAPER_RUNTIME_STATE_VERSION,
    FastPaperCheckpointError,
    FastPaperRuntimeState,
    decode_fast_paper_checkpoint,
    encode_fast_paper_checkpoint,
    load_latest_fast_paper_checkpoint,
    save_fast_paper_checkpoint,
    validate_fast_paper_restart_equivalence,
)


T0 = 5_000_000
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
        version="fl7.5-fill-v1",
        assumed_latency_ms=100,
        max_quote_lag_ms=2_000,
        swap_fee_bps=35,
        network_fee_usd=0.02,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
    )


def _position_policy() -> FastPaperPositionActionPolicy:
    return FastPaperPositionActionPolicy(
        version="fl7.5-position-v1",
        max_slippage_bps=600,
    )


def _assessment(
    action: FastPaperAction,
    *,
    event_id: str,
    sequence: int,
    at: int,
) -> FastPaperActionAssessment:
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=event_id,
        market_key="pump:mint-a:quote-a",
        source_sequence=sequence,
        as_of_unix_ms=at,
        strategy_family="impulse-scalp" if action is FastPaperAction.BUY else "longer-runner",
        strategy_version="1",
        action=action,
        reasons=(f"{action.value.lower()}_conditions_met",),
    )


def _record(loop_state, assessment: FastPaperActionAssessment):
    update = FastPaperMaterialUpdate(
        source_event_id=assessment.source_event_id,
        market_key=assessment.market_key,
        source_sequence=assessment.source_sequence,
        as_of_unix_ms=assessment.as_of_unix_ms,
        state_version="state-v1",
        is_material=True,
        material_reason="fl7.5-test",
    )
    return run_fast_paper_event(
        loop_state,
        update,
        lambda _update: assessment,
    ).next_state


def _buy_approval(assessment: FastPaperActionAssessment) -> FastPaperBuyApproval:
    return FastPaperBuyApproval(
        version=FAST_PAPER_BUY_VERSION,
        assessment=assessment,
        mint="mint-a",
        quote_mint="quote-a",
        state_version="state-v1",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=1.0,
        maximum_acceptable_entry_price_quote=1.2,
        expected_entry_variable_cost_bps=100,
        expected_entry_fixed_cost_quote=0.01,
    )


def _runtime_state() -> FastPaperRuntimeState:
    assessment = _assessment(
        FastPaperAction.BUY,
        event_id="event-buy-1",
        sequence=1,
        at=T0 + 100,
    )
    loop_state = _record(create_fast_paper_loop_state(), assessment)
    return FastPaperRuntimeState(
        version=FAST_PAPER_RUNTIME_STATE_VERSION,
        as_of_unix_ms=T0 + 100,
        event_loop_state=loop_state,
        ledger=create_paper_ledger(10_000.0, T0),
        fill_policy=_fill_policy(),
        position_action_policy=_position_policy(),
        pending_buy=_buy_approval(assessment),
        position_action_states=(),
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


def test_fl7_5_versions_are_stable() -> None:
    assert FAST_PAPER_RUNTIME_STATE_VERSION == "fl7.5-v1"
    assert FAST_PAPER_CHECKPOINT_SCHEMA_VERSION == "fl7.5-fast-paper-state-v1"


def test_fast_runtime_state_requires_recorded_pending_buy_authority() -> None:
    assessment = _assessment(
        FastPaperAction.BUY,
        event_id="unrecorded-buy",
        sequence=1,
        at=T0 + 100,
    )
    with pytest.raises(ValueError, match="record|authority|assessment"):
        FastPaperRuntimeState(
            version=FAST_PAPER_RUNTIME_STATE_VERSION,
            as_of_unix_ms=T0 + 100,
            event_loop_state=create_fast_paper_loop_state(),
            ledger=create_paper_ledger(10_000.0, T0),
            fill_policy=_fill_policy(),
            position_action_policy=_position_policy(),
            pending_buy=_buy_approval(assessment),
            position_action_states=(),
        )


def test_fast_runtime_state_rejects_clock_regression() -> None:
    state = _runtime_state()
    with pytest.raises(ValueError, match="as_of|clock|precede"):
        replace(state, as_of_unix_ms=T0 + 50)


def test_fast_checkpoint_payload_is_canonical_and_exactly_round_trips() -> None:
    state = _runtime_state()
    first = encode_fast_paper_checkpoint("fast-run", 7, state, T0 + 200)
    second = encode_fast_paper_checkpoint("fast-run", 7, state, T0 + 200)

    assert isinstance(first, bytes)
    assert first == second
    assert b" " not in first

    record = decode_fast_paper_checkpoint(first)
    assert record.run_id == "fast-run"
    assert record.sequence == 7
    assert record.checkpoint_schema_version == FAST_PAPER_CHECKPOINT_SCHEMA_VERSION
    assert record.state_as_of_unix_ms == state.as_of_unix_ms
    assert record.created_at_unix_ms == T0 + 200
    assert record.payload_sha256 == hashlib.sha256(first).hexdigest()
    assert record.state == state
    assert record.state.pending_buy == state.pending_buy
    assert record.state.ledger.processed_intent_keys == state.ledger.processed_intent_keys


def test_fast_checkpoint_codec_rejects_unknown_type_tags_and_raw_json_floats() -> None:
    payload = encode_fast_paper_checkpoint("fast-run", 1, _runtime_state(), T0 + 200)
    envelope = json.loads(payload)

    unknown = dict(envelope)
    unknown["state"] = {"$type": "UnknownFastPaperType", "fields": {}}
    with pytest.raises(FastPaperCheckpointError, match="unknown|type"):
        decode_fast_paper_checkpoint(_canonical_json(unknown))

    raw_float = dict(envelope)
    raw_float["state_as_of_unix_ms"] = 1.5
    with pytest.raises(FastPaperCheckpointError, match="integer|non-negative|malformed"):
        decode_fast_paper_checkpoint(_canonical_json(raw_float))


def test_fast_checkpoint_rejects_checksum_mismatch() -> None:
    payload = encode_fast_paper_checkpoint("fast-run", 1, _runtime_state(), T0 + 200)
    with pytest.raises(FastPaperCheckpointError, match="checksum"):
        decode_fast_paper_checkpoint(payload, expected_sha256="0" * 64)


def test_fast_checkpoint_save_load_is_append_only_and_idempotent(tmp_path) -> None:
    database = tmp_path / "fast-checkpoint.sqlite3"
    _migrate(database)
    state = _runtime_state()

    first = save_fast_paper_checkpoint(database, "fast-run", 1, state, T0 + 200)
    repeated = save_fast_paper_checkpoint(database, "fast-run", 1, state, T0 + 200)
    loaded = load_latest_fast_paper_checkpoint(database, "fast-run")

    assert repeated == first
    assert loaded == first
    assert loaded is not None
    assert loaded.state == state

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT COUNT(*) FROM paper_loop_checkpoints WHERE run_id = ?",
            ("fast-run",),
        ).fetchone()[0]
    assert rows == 1


def test_fast_checkpoint_rejects_sequence_collision_and_regression(tmp_path) -> None:
    database = tmp_path / "fast-collision.sqlite3"
    _migrate(database)
    state = _runtime_state()

    save_fast_paper_checkpoint(database, "fast-run", 5, state, T0 + 200)
    with pytest.raises(FastPaperCheckpointError, match="collision"):
        save_fast_paper_checkpoint(
            database,
            "fast-run",
            5,
            replace(state, as_of_unix_ms=T0 + 101),
            T0 + 200,
        )
    with pytest.raises(FastPaperCheckpointError, match="monotonic|sequence"):
        save_fast_paper_checkpoint(database, "fast-run", 4, state, T0 + 200)


def test_fast_checkpoint_run_id_cannot_mix_legacy_and_fast_schemas(tmp_path) -> None:
    database = tmp_path / "fast-schema-isolation.sqlite3"
    _migrate(database)
    state = _runtime_state()

    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO paper_loop_checkpoints (
                   run_id, sequence, checkpoint_schema_version,
                   state_as_of_unix_ms, created_at_unix_ms,
                   payload_sha256, payload_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "mixed-run",
                1,
                "c6-paper-state-v1",
                T0,
                T0,
                "0" * 64,
                "{}",
            ),
        )

    with pytest.raises(FastPaperCheckpointError, match="schema|namespace|run_id"):
        save_fast_paper_checkpoint(database, "mixed-run", 2, state, T0 + 200)
    with pytest.raises(FastPaperCheckpointError, match="schema|namespace|run_id"):
        load_latest_fast_paper_checkpoint(database, "mixed-run")


def test_fast_checkpoint_detects_file_backed_payload_corruption(tmp_path) -> None:
    database = tmp_path / "fast-corruption.sqlite3"
    _migrate(database)
    save_fast_paper_checkpoint(database, "fast-run", 1, _runtime_state(), T0 + 200)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE paper_loop_checkpoints SET payload_json = ? WHERE run_id = ?",
            ("{}", "fast-run"),
        )

    with pytest.raises(FastPaperCheckpointError, match="checksum|payload|canonical|malformed"):
        load_latest_fast_paper_checkpoint(database, "fast-run")


def test_fast_restart_equivalence_uses_exact_state_and_accounting() -> None:
    state = _runtime_state()
    payload = encode_fast_paper_checkpoint("fast-run", 1, state, T0 + 200)
    restored = decode_fast_paper_checkpoint(payload).state

    report = validate_fast_paper_restart_equivalence(state, restored)
    assert report.equivalent
    assert report.expected_state_sha256 == report.restored_state_sha256
    assert report.expected_accounting == report.restored_accounting
    assert report.differences == ()

    changed = replace(restored, as_of_unix_ms=restored.as_of_unix_ms + 1)
    mismatch = validate_fast_paper_restart_equivalence(state, changed)
    assert not mismatch.equivalent
    assert "STATE_MISMATCH" in mismatch.differences
