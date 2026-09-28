from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

import shreks_brain.fast_paper_runtime.authoritative_commit as commit
import shreks_brain.fast_paper_runtime.authoritative_runtime_state as runtime
from shreks_brain.paper import PaperPositionState
from shreks_brain.paper_validation import (
    FAST_PAPER_RUNTIME_STATE_VERSION,
    FastPaperRuntimeState,
    load_latest_fast_paper_checkpoint,
    validate_fast_paper_restart_equivalence,
)

from test_fast_paper_accounting_reconciliation import (
    MARKET_KEY,
    _open_fast_position,
)
from test_fast_paper_authoritative_handoff import (
    _initialize,
    _legacy_checkpoint,
)
from test_fast_paper_shadow_execution_input import _execution_policy


_DECISION_FP = "a" * 64


def _fixture(tmp_path: Path):
    manifest, database, source = _legacy_checkpoint(tmp_path)
    handoff = _initialize(manifest, database, source)
    policy = _execution_policy(manifest)
    state = runtime.load_latest_fast_paper_authoritative_runtime_state(
        manifest,
        handoff.binding,
    )
    return (
        manifest,
        database,
        policy,
        handoff.binding,
        handoff.checkpoint,
        state,
    )


def _open_next_state(manifest, policy):
    loop_state, ledger, action_state, _ = _open_fast_position()
    return FastPaperRuntimeState(
        version=FAST_PAPER_RUNTIME_STATE_VERSION,
        as_of_unix_ms=ledger.as_of_unix_ms,
        event_loop_state=loop_state,
        ledger=ledger,
        fill_policy=policy.fill_policy,
        position_action_policy=policy.position_action_policy,
        pending_buy=None,
        position_action_states=(action_state,),
    )


def _open_mapping(state: FastPaperRuntimeState):
    positions = tuple(
        position
        for position in state.ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    assert len(positions) == 1
    position = positions[0]
    return runtime.FastPaperAuthoritativeMarketPosition(
        market_key=MARKET_KEY,
        position_id=position.position_id,
        mint=position.mint,
        current_exposure_fraction=0.5,
        current_base_quantity_raw=10_000_000,
    )


def _transition(
    state: FastPaperRuntimeState,
    policy,
    *,
    market_positions=(),
    sequence: int | None = 1,
    event_id: str | None = "event-buy",
    evidence_fp: str | None = _DECISION_FP,
):
    return commit.FastPaperAuthoritativeTransition(
        next_paper_state=state,
        next_market_positions=tuple(market_positions),
        execution_policy_fingerprint_sha256=(
            policy.policy_fingerprint_sha256
        ),
        last_processed_source_sequence=sequence,
        last_processed_source_event_id=event_id,
        last_processed_decision_evidence_fingerprint_sha256=evidence_fp,
    )


def test_handoff_seeds_initial_authoritative_runtime_state_atomically(
    tmp_path: Path,
) -> None:
    (
        manifest,
        database,
        policy,
        binding,
        checkpoint,
        state,
    ) = _fixture(tmp_path)

    assert state.schema_name == (
        "shreks.fast_paper_authoritative_runtime_state"
    )
    assert state.schema_version == 1
    assert state.binding_fingerprint_sha256 == (
        binding.binding_fingerprint_sha256
    )
    assert state.execution_policy_fingerprint_sha256 == (
        policy.policy_fingerprint_sha256
    )
    assert state.paper_checkpoint_sequence == 0
    assert state.paper_checkpoint_payload_sha256 == checkpoint.payload_sha256
    assert state.market_positions == ()
    assert state.last_processed_source_sequence is None
    assert state.last_processed_source_event_id is None
    assert (
        state.last_processed_decision_evidence_fingerprint_sha256
        is None
    )

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_bindings
            WHERE fast_run_id = ?
            """,
            (binding.fast_run_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM paper_loop_checkpoints
            WHERE run_id = ?
            """,
            (binding.fast_run_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_runtime_states
            WHERE fast_run_id = ?
            """,
            (binding.fast_run_id,),
        ).fetchone() == (1,)


def test_runtime_state_fingerprint_is_deterministic(
    tmp_path: Path,
) -> None:
    manifest, _database, policy, binding, checkpoint, _state = _fixture(
        tmp_path
    )

    first = runtime.build_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
        execution_policy_fingerprint_sha256=(
            policy.policy_fingerprint_sha256
        ),
        last_processed_source_sequence=8,
        last_processed_source_event_id="event-8",
        last_processed_decision_evidence_fingerprint_sha256="8" * 64,
    )
    second = runtime.build_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
        execution_policy_fingerprint_sha256=(
            policy.policy_fingerprint_sha256
        ),
        last_processed_source_sequence=8,
        last_processed_source_event_id="event-8",
        last_processed_decision_evidence_fingerprint_sha256="8" * 64,
    )

    assert first == second
    assert len(first.state_fingerprint_sha256) == 64


def test_runtime_state_requires_exact_open_position_mapping(
    tmp_path: Path,
) -> None:
    manifest, _database, policy, binding, _checkpoint, _state = _fixture(
        tmp_path
    )
    open_state = _open_next_state(manifest, policy)
    from shreks_brain.paper_validation import decode_fast_paper_checkpoint
    from shreks_brain.paper_validation import encode_fast_paper_checkpoint

    checkpoint = decode_fast_paper_checkpoint(
        encode_fast_paper_checkpoint(
            binding.fast_run_id,
            1,
            open_state,
            open_state.as_of_unix_ms,
        )
    )
    mapping = _open_mapping(open_state)

    built = runtime.build_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(mapping,),
        execution_policy_fingerprint_sha256=(
            policy.policy_fingerprint_sha256
        ),
    )
    assert built.market_positions == (mapping,)

    with pytest.raises(ValueError, match="OPEN|mapping|position"):
        runtime.build_fast_paper_authoritative_runtime_state(
            manifest,
            binding,
            checkpoint,
            market_positions=(),
            execution_policy_fingerprint_sha256=(
                policy.policy_fingerprint_sha256
            ),
        )

    wrong = replace(mapping, position_id="wrong-position")
    with pytest.raises(ValueError, match="OPEN|mapping|position"):
        runtime.build_fast_paper_authoritative_runtime_state(
            manifest,
            binding,
            checkpoint,
            market_positions=(wrong,),
            execution_policy_fingerprint_sha256=(
                policy.policy_fingerprint_sha256
            ),
        )


def test_atomic_commit_writes_exact_checkpoint_runtime_pair(
    tmp_path: Path,
) -> None:
    manifest, database, policy, binding, checkpoint, state = _fixture(
        tmp_path
    )
    next_state = _open_next_state(manifest, policy)
    mapping = _open_mapping(next_state)

    result = commit.commit_fast_paper_authoritative_transition_atomically(
        manifest,
        binding,
        checkpoint,
        state,
        _transition(
            next_state,
            policy,
            market_positions=(mapping,),
        ),
        sequence=1,
        created_at_unix_ms=next_state.as_of_unix_ms,
    )

    assert result.checkpoint.sequence == 1
    assert result.runtime_state.paper_checkpoint_sequence == 1
    assert (
        result.runtime_state.paper_checkpoint_payload_sha256
        == result.checkpoint.payload_sha256
    )
    assert result.runtime_state.market_positions == (mapping,)
    assert result.runtime_state.last_processed_source_sequence == 1
    assert result.runtime_state.last_processed_source_event_id == "event-buy"

    restored_checkpoint = load_latest_fast_paper_checkpoint(
        database,
        binding.fast_run_id,
    )
    restored_runtime = (
        runtime.load_latest_fast_paper_authoritative_runtime_state(
            manifest,
            binding,
        )
    )
    assert restored_checkpoint == result.checkpoint
    assert restored_runtime == result.runtime_state
    assert validate_fast_paper_restart_equivalence(
        result.checkpoint.state,
        restored_checkpoint.state,
    ).equivalent


def test_atomic_commit_rejects_stale_checkpoint_or_runtime(
    tmp_path: Path,
) -> None:
    manifest, _database, policy, binding, checkpoint, state = _fixture(
        tmp_path
    )
    first = commit.commit_fast_paper_authoritative_transition_atomically(
        manifest,
        binding,
        checkpoint,
        state,
        _transition(
            replace(
                checkpoint.state,
                as_of_unix_ms=checkpoint.state.as_of_unix_ms + 1,
            ),
            policy,
        ),
        sequence=1,
        created_at_unix_ms=checkpoint.state.as_of_unix_ms + 1,
    )

    with pytest.raises(ValueError, match="latest|stale|checkpoint"):
        commit.commit_fast_paper_authoritative_transition_atomically(
            manifest,
            binding,
            checkpoint,
            first.runtime_state,
            _transition(
                first.checkpoint.state,
                policy,
                sequence=2,
                event_id="event-2",
                evidence_fp="b" * 64,
            ),
            sequence=1,
            created_at_unix_ms=first.checkpoint.state.as_of_unix_ms,
        )

    with pytest.raises(ValueError, match="latest|stale|runtime"):
        commit.commit_fast_paper_authoritative_transition_atomically(
            manifest,
            binding,
            first.checkpoint,
            state,
            _transition(
                first.checkpoint.state,
                policy,
                sequence=2,
                event_id="event-2",
                evidence_fp="b" * 64,
            ),
            sequence=2,
            created_at_unix_ms=first.checkpoint.state.as_of_unix_ms,
        )


def test_deferred_execution_commit_may_preserve_learned_identity(
    tmp_path: Path,
) -> None:
    manifest, _database, policy, binding, checkpoint, state = _fixture(
        tmp_path
    )
    first_state = replace(
        checkpoint.state,
        as_of_unix_ms=checkpoint.state.as_of_unix_ms + 1,
    )
    first = commit.commit_fast_paper_authoritative_transition_atomically(
        manifest,
        binding,
        checkpoint,
        state,
        _transition(first_state, policy),
        sequence=1,
        created_at_unix_ms=first_state.as_of_unix_ms,
    )
    retry_state = replace(
        first.checkpoint.state,
        as_of_unix_ms=first.checkpoint.state.as_of_unix_ms + 1,
    )

    retry = commit.commit_fast_paper_authoritative_transition_atomically(
        manifest,
        binding,
        first.checkpoint,
        first.runtime_state,
        _transition(retry_state, policy),
        sequence=2,
        created_at_unix_ms=retry_state.as_of_unix_ms,
    )

    assert retry.runtime_state.last_processed_source_sequence == 1
    assert retry.runtime_state.last_processed_source_event_id == "event-buy"
    assert (
        retry.runtime_state.last_processed_decision_evidence_fingerprint_sha256
        == _DECISION_FP
    )


@pytest.mark.parametrize(
    ("sequence", "event_id", "evidence_fp", "match"),
    (
        (0, "event-0", "9" * 64, "sequence"),
        (1, "changed-event", _DECISION_FP, "identity|event"),
        (1, "event-buy", "b" * 64, "identity|fingerprint"),
    ),
)
def test_learned_identity_cannot_regress_or_mutate_in_place(
    tmp_path: Path,
    sequence,
    event_id,
    evidence_fp,
    match: str,
) -> None:
    manifest, _database, policy, binding, checkpoint, state = _fixture(
        tmp_path
    )
    first_state = replace(
        checkpoint.state,
        as_of_unix_ms=checkpoint.state.as_of_unix_ms + 1,
    )
    first = commit.commit_fast_paper_authoritative_transition_atomically(
        manifest,
        binding,
        checkpoint,
        state,
        _transition(first_state, policy),
        sequence=1,
        created_at_unix_ms=first_state.as_of_unix_ms,
    )
    next_state = replace(
        first.checkpoint.state,
        as_of_unix_ms=first.checkpoint.state.as_of_unix_ms + 1,
    )

    with pytest.raises(ValueError, match=match):
        commit.commit_fast_paper_authoritative_transition_atomically(
            manifest,
            binding,
            first.checkpoint,
            first.runtime_state,
            _transition(
                next_state,
                policy,
                sequence=sequence,
                event_id=event_id,
                evidence_fp=evidence_fp,
            ),
            sequence=2,
            created_at_unix_ms=next_state.as_of_unix_ms,
        )


def test_execution_policy_fingerprint_cannot_drift(
    tmp_path: Path,
) -> None:
    manifest, _database, policy, binding, checkpoint, state = _fixture(
        tmp_path
    )
    transition = replace(
        _transition(
            replace(
                checkpoint.state,
                as_of_unix_ms=checkpoint.state.as_of_unix_ms + 1,
            ),
            policy,
        ),
        execution_policy_fingerprint_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="execution policy|fingerprint"):
        commit.commit_fast_paper_authoritative_transition_atomically(
            manifest,
            binding,
            checkpoint,
            state,
            transition,
            sequence=1,
            created_at_unix_ms=checkpoint.state.as_of_unix_ms + 1,
        )


def test_atomic_insert_failure_leaves_no_torn_target_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, database, policy, binding, checkpoint, state = _fixture(
        tmp_path
    )
    next_state = replace(
        checkpoint.state,
        as_of_unix_ms=checkpoint.state.as_of_unix_ms + 1,
    )

    monkeypatch.setattr(
        commit,
        "_insert_runtime_state_row",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("injected runtime insert failure")
        ),
    )
    with pytest.raises(RuntimeError, match="injected runtime insert failure"):
        commit.commit_fast_paper_authoritative_transition_atomically(
            manifest,
            binding,
            checkpoint,
            state,
            _transition(next_state, policy),
            sequence=1,
            created_at_unix_ms=next_state.as_of_unix_ms,
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM paper_loop_checkpoints
            WHERE run_id = ? AND sequence = 1
            """,
            (binding.fast_run_id,),
        ).fetchone() == (0,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_runtime_states
            WHERE fast_run_id = ? AND paper_checkpoint_sequence = 1
            """,
            (binding.fast_run_id,),
        ).fetchone() == (0,)


def test_runtime_payload_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    manifest, database, _policy, binding, _checkpoint, _state = _fixture(
        tmp_path
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE fast_paper_authoritative_runtime_states
            SET payload_sha256 = ?
            WHERE fast_run_id = ? AND paper_checkpoint_sequence = 0
            """,
            ("0" * 64, binding.fast_run_id),
        )
        connection.commit()

    with pytest.raises(ValueError, match="payload|fingerprint|checksum"):
        runtime.load_latest_fast_paper_authoritative_runtime_state(
            manifest,
            binding,
        )


def test_authoritative_runtime_and_commit_have_no_control_authority() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "shreks_brain"
    sources = (
        root / "fast_paper_runtime" / "authoritative_runtime_state.py",
        root / "fast_paper_runtime" / "authoritative_commit.py",
    )
    required = (
        "FastPaperRuntimeState",
        "paper_checkpoint_sequence",
        "binding_fingerprint_sha256",
    )
    forbidden = (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "evaluate_fast_campaign_decision",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "requests.",
        "httpx",
        "aiohttp",
        "systemctl",
        "subprocess",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "LIVE_ENABLED",
        "fast_future_path_labels",
        "counterfactual",
    )
    for path in sources:
        source = path.read_text(encoding="utf-8")
        for token in required:
            assert token in source
        for token in forbidden:
            assert token not in source
