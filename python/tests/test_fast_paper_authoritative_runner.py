from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper import FastPaperBuyOutcome
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowPendingBuyRetryInput,
    run_fast_paper_authoritative_execution,
    run_fast_paper_authoritative_pending_buy_retry,
)
from shreks_brain.paper import PaperPositionState
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    validate_fast_paper_accounting,
)

from test_fast_paper_authoritative_handoff import (
    _initialize,
    _legacy_checkpoint,
)
from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_execution_input import (
    _execution_policy,
    _risk,
    _usd,
)
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _record_at,
    _source,
)


def _fixture(tmp_path: Path):
    manifest, database, legacy = _legacy_checkpoint(tmp_path)
    handoff = _initialize(manifest, database, legacy)
    policy = _execution_policy(manifest)
    return manifest, database, policy, handoff


def _decision_record(checkpoint, *, sequence: int, signature: str):
    at = checkpoint.state.as_of_unix_ms + 1_000 * sequence
    return _record_at(
        _record(),
        signature=signature,
        sequence=sequence,
        at=at,
    )


def test_fresh_skip_commits_once_and_exact_replay_is_storage_noop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest, database, policy, handoff = _fixture(tmp_path)
    record = _decision_record(
        handoff.checkpoint,
        sequence=1,
        signature="authoritative-skip",
    )
    at = record.decision_observed_at_unix_ms
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="SKIP",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=at + 20,
        entry_observed_at=at + 10,
        exit_observed_at=at + 15,
    )
    source = _source(record, evidence)

    first = run_fast_paper_authoritative_execution(
        manifest,
        handoff.binding,
        policy,
        source,
        committed_at_unix_ms=at + 20,
    )

    assert first.committed is True
    assert first.replayed is False
    assert first.checkpoint.sequence == 1
    assert first.runtime_state.paper_checkpoint_sequence == 1
    assert first.runtime_state.last_processed_source_sequence == 1
    assert (
        first.runtime_state.last_processed_decision_evidence_fingerprint_sha256
        == evidence.evidence_fingerprint_sha256
    )
    assert first.checkpoint.state.ledger == handoff.checkpoint.state.ledger
    assert (
        validate_fast_paper_accounting(first.checkpoint.state).status
        is AccountingValidationStatus.RECONCILED
    )

    replay = run_fast_paper_authoritative_execution(
        manifest,
        handoff.binding,
        policy,
        source,
        committed_at_unix_ms=at + 30,
    )

    assert replay.replayed is True
    assert replay.committed is False
    assert replay.checkpoint == first.checkpoint
    assert replay.runtime_state == first.runtime_state

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM paper_loop_checkpoints
            WHERE run_id = ?
            """,
            (handoff.binding.fast_run_id,),
        ).fetchone() == (2,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_runtime_states
            WHERE fast_run_id = ?
            """,
            (handoff.binding.fast_run_id,),
        ).fetchone() == (2,)


def test_deferred_buy_survives_restart_retry_and_fills_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest, _database, policy, handoff = _fixture(tmp_path)
    record = _decision_record(
        handoff.checkpoint,
        sequence=1,
        signature="authoritative-buy",
    )
    at = record.decision_observed_at_unix_ms
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=at + 20,
        entry_observed_at=at + 10,
        exit_observed_at=at + 15,
    )
    source = _source(record, evidence)

    deferred = run_fast_paper_authoritative_execution(
        manifest,
        handoff.binding,
        policy,
        source,
        committed_at_unix_ms=at + 20,
    )

    assert deferred.committed is True
    assert deferred.buy_result is not None
    assert deferred.buy_result.outcome is FastPaperBuyOutcome.DEFERRED
    assert deferred.checkpoint.sequence == 1
    assert deferred.checkpoint.state.pending_buy is not None
    assert deferred.runtime_state.market_positions == ()
    assert deferred.runtime_state.last_processed_source_sequence == 1

    retry_at = at + 200
    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=retry_at,
        quote=replace(
            evidence.entry_quote,
            observed_at_unix_ms=at + 150,
            reference_price_quote=1.02,
            execution_price_quote=1.03,
        ),
        risk_context=_risk(retry_at),
        quote_usd_evidence=_usd(
            record,
            observed_at=at + 190,
        ),
    )

    filled = run_fast_paper_authoritative_pending_buy_retry(
        manifest,
        handoff.binding,
        policy,
        retry,
        evidence,
        committed_at_unix_ms=retry_at,
    )

    assert filled.committed is True
    assert filled.buy_result is not None
    assert filled.buy_result.outcome is FastPaperBuyOutcome.FILLED
    assert filled.checkpoint.sequence == 2
    assert filled.checkpoint.state.pending_buy is None
    assert len(filled.runtime_state.market_positions) == 1
    assert len(filled.checkpoint.state.position_action_states) == 1
    assert len(filled.checkpoint.state.ledger.processed_intent_keys) == 1
    open_positions = tuple(
        position
        for position in filled.checkpoint.state.ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    assert len(open_positions) == 1
    mapping = filled.runtime_state.market_positions[0]
    assert mapping.position_id == open_positions[0].position_id
    assert mapping.mint == open_positions[0].mint
    assert mapping.current_exposure_fraction == pytest.approx(0.5)
    assert (
        validate_fast_paper_accounting(filled.checkpoint.state).status
        is AccountingValidationStatus.RECONCILED
    )

    with pytest.raises(ValueError, match="pending approval|pending BUY"):
        run_fast_paper_authoritative_pending_buy_retry(
            manifest,
            handoff.binding,
            policy,
            retry,
            evidence,
            committed_at_unix_ms=retry_at + 1,
        )

    replay = run_fast_paper_authoritative_execution(
        manifest,
        handoff.binding,
        policy,
        source,
        committed_at_unix_ms=retry_at + 2,
    )
    assert replay.replayed is True
    assert replay.checkpoint.sequence == 2
    assert len(replay.checkpoint.state.ledger.processed_intent_keys) == 1


def test_pending_buy_retry_rejects_changed_original_decision_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest, _database, policy, handoff = _fixture(tmp_path)
    record = _decision_record(
        handoff.checkpoint,
        sequence=1,
        signature="authoritative-buy-tamper",
    )
    at = record.decision_observed_at_unix_ms
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=at + 20,
        entry_observed_at=at + 10,
        exit_observed_at=at + 15,
    )
    source = _source(record, evidence)
    deferred = run_fast_paper_authoritative_execution(
        manifest,
        handoff.binding,
        policy,
        source,
        committed_at_unix_ms=at + 20,
    )
    assert deferred.checkpoint.state.pending_buy is not None

    retry_at = at + 200
    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=retry_at,
        quote=replace(
            evidence.entry_quote,
            observed_at_unix_ms=at + 150,
            reference_price_quote=1.02,
            execution_price_quote=1.03,
        ),
        risk_context=_risk(retry_at),
        quote_usd_evidence=_usd(
            record,
            observed_at=at + 190,
        ),
    )
    tampered = replace(
        evidence,
        decision_latency_ns=evidence.decision_latency_ns + 1,
    )

    with pytest.raises(ValueError, match="fingerprint|identity"):
        run_fast_paper_authoritative_pending_buy_retry(
            manifest,
            handoff.binding,
            policy,
            retry,
            tampered,
            committed_at_unix_ms=retry_at,
        )


def test_authoritative_runner_has_no_shadow_storage_or_control_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "authoritative_runner.py"
    ).read_text(encoding="utf-8")

    required = (
        "reconstruct_fast_paper_shadow_decision",
        "reconstruct_fast_paper_shadow_pending_buy_retry",
        "commit_fast_paper_authoritative_transition_atomically",
        "load_latest_fast_paper_authoritative_checkpoint",
        "load_latest_fast_paper_authoritative_runtime_state",
    )
    forbidden = (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "required_score_threshold",
        "save_fast_paper_shadow_ledger_checkpoint",
        "save_fast_paper_shadow_runtime_state",
        "commit_fast_paper_shadow_transition_atomically",
        "initialize_fast_paper_shadow_ledger_database",
        "requests.",
        "httpx",
        "aiohttp",
        "systemctl",
        "subprocess",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "LIVE_ENABLED",
    )
    for token in required:
        assert token in source
    for token in forbidden:
        assert token not in source
