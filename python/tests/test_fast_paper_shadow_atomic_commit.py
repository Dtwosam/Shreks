from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow as shadow
import shreks_brain.fast_paper_runtime.shadow_commit as shadow_commit
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper import FastPaperBuyOutcome
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_COMMIT_VERSION,
    commit_fast_paper_shadow_transition_atomically,
    execute_fast_paper_shadow_decision,
    load_latest_fast_paper_shadow_ledger_checkpoint,
    load_latest_fast_paper_shadow_runtime_state,
)

from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _runtime_fixture,
    _source,
)


def _deferred_buy_transition(monkeypatch, tmp_path: Path):
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(tmp_path)
    record = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    transition = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint,
        posture,
        _source(record, evidence),
    )
    assert transition.buy_result is not None
    assert transition.buy_result.outcome is FastPaperBuyOutcome.DEFERRED
    return manifest, binding, checkpoint, posture, transition


def test_atomic_shadow_commit_persists_exact_checkpoint_and_posture_pair(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, posture, transition = (
        _deferred_buy_transition(monkeypatch, tmp_path)
    )

    committed = commit_fast_paper_shadow_transition_atomically(
        manifest,
        binding,
        checkpoint,
        posture,
        transition,
        sequence=1,
        created_at_unix_ms=20_020,
    )

    assert committed.version == FAST_PAPER_SHADOW_COMMIT_VERSION
    assert committed.checkpoint.sequence == 1
    assert committed.checkpoint.state == transition.next_paper_state
    assert committed.runtime_state.paper_checkpoint_sequence == 1
    assert (
        committed.runtime_state.paper_checkpoint_payload_sha256
        == committed.checkpoint.payload_sha256
    )
    assert (
        committed.runtime_state.execution_policy_fingerprint_sha256
        == transition.execution_policy_fingerprint_sha256
    )
    assert committed.runtime_state.pending_buy == transition.next_pending_buy

    assert (
        load_latest_fast_paper_shadow_ledger_checkpoint(manifest, binding)
        == committed.checkpoint
    )
    assert (
        load_latest_fast_paper_shadow_runtime_state(manifest, binding)
        == committed.runtime_state
    )


def test_atomic_shadow_commit_rolls_back_both_rows_on_companion_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, posture, transition = (
        _deferred_buy_transition(monkeypatch, tmp_path)
    )

    monkeypatch.setattr(
        shadow_commit,
        "_insert_shadow_runtime_state_row",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("injected companion failure")
        ),
    )

    with pytest.raises(RuntimeError, match="injected companion failure"):
        commit_fast_paper_shadow_transition_atomically(
            manifest,
            binding,
            checkpoint,
            posture,
            transition,
            sequence=1,
            created_at_unix_ms=20_020,
        )

    assert (
        load_latest_fast_paper_shadow_ledger_checkpoint(manifest, binding)
        == checkpoint
    )
    assert (
        load_latest_fast_paper_shadow_runtime_state(manifest, binding)
        == posture
    )


def test_atomic_shadow_commit_rejects_stale_writer_after_success(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, posture, transition = (
        _deferred_buy_transition(monkeypatch, tmp_path)
    )
    commit_fast_paper_shadow_transition_atomically(
        manifest,
        binding,
        checkpoint,
        posture,
        transition,
        sequence=1,
        created_at_unix_ms=20_020,
    )

    with pytest.raises(ValueError, match="latest|stale|durable"):
        commit_fast_paper_shadow_transition_atomically(
            manifest,
            binding,
            checkpoint,
            posture,
            transition,
            sequence=1,
            created_at_unix_ms=20_020,
        )


def test_atomic_shadow_commit_rejects_sequence_gap_and_policy_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, posture, transition = (
        _deferred_buy_transition(monkeypatch, tmp_path)
    )

    with pytest.raises(ValueError, match="sequence|next"):
        commit_fast_paper_shadow_transition_atomically(
            manifest,
            binding,
            checkpoint,
            posture,
            transition,
            sequence=2,
            created_at_unix_ms=20_020,
        )

    drifted = replace(
        transition,
        execution_policy_fingerprint_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="execution policy|fingerprint"):
        commit_fast_paper_shadow_transition_atomically(
            manifest,
            binding,
            checkpoint,
            posture,
            drifted,
            sequence=1,
            created_at_unix_ms=20_020,
        )


def test_atomic_shadow_commit_source_owns_persistence_only() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "shadow_commit.py"
    ).read_text(encoding="utf-8")

    for required in (
        "BEGIN IMMEDIATE",
        "encode_fast_paper_checkpoint",
        "decode_fast_paper_checkpoint",
        "FastPaperShadowExecutionTransition",
        "FastPaperShadowRuntimeState",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.scoring",
        "ScorePolicy",
        "DecisionPolicy",
        "score_candidate",
        "decide_entry",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in source
