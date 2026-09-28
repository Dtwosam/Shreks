from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper import FastPaperBuyOutcome
from shreks_brain.fast_paper_runtime.authoritative_release_handoff import (
    FastPaperAuthoritativeReleaseHandoffError,
    initialize_fast_paper_authoritative_release_handoff,
    load_fast_paper_authoritative_release_handoff,
)
from shreks_brain.fast_paper_runtime.authoritative_runner import (
    run_fast_paper_authoritative_execution,
)
from shreks_brain.fast_paper_runtime.codec import (
    build_fast_paper_runtime_manifest,
    build_fast_paper_runtime_state,
)
from shreks_brain.fast_paper_runtime.models import FastPaperRuntimeCursor
from shreks_brain.paper import PaperPositionState

from test_fast_paper_authoritative_handoff import (
    _initialize,
    _legacy_checkpoint,
)
from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_execution_input import _execution_policy
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _record_at,
    _source,
)


_TARGET_RELEASE_SHA = "b" * 40
_TARGET_RUN_ID = "fast-paper-release-successor"


def _target_manifest(source, *, action_policy=None):
    return build_fast_paper_runtime_manifest(
        release_source_sha=_TARGET_RELEASE_SHA,
        champion_path=source.champion_path,
        decision_binary_path=source.decision_binary_path,
        feature_feed_binary_path=source.feature_feed_binary_path,
        action_policy=(
            source.action_policy
            if action_policy is None
            else action_policy
        ),
        state_version=source.state_version,
        risk_policy_version=source.risk_policy_version,
        fill_policy_version=source.fill_policy_version,
        position_action_policy_version=(
            source.position_action_policy_version
        ),
        strategy_family=source.strategy_family,
        strategy_version=source.strategy_version,
        assessment_version=source.assessment_version,
        observer_database_path=source.observer_database_path,
        paper_evidence_path=source.paper_evidence_path,
        checkpoint_path=source.checkpoint_path,
        quote_provider=source.quote_provider,
        quote_mint=source.quote_mint,
        quote_decimals=source.quote_decimals,
        route_evidence_version=source.route_evidence_version,
    )


def _cursor(record):
    return FastPaperRuntimeCursor(
        decision_sequence=record.decision_sequence,
        decision_signature=record.decision_signature,
        decision_ordinal=record.decision_ordinal,
        decision_observed_at_unix_ms=(
            record.decision_observed_at_unix_ms
        ),
    )


def _decision_record(checkpoint, *, sequence: int, signature: str):
    at = checkpoint.state.as_of_unix_ms + 1_000 * sequence
    return _record_at(
        _record(),
        signature=signature,
        sequence=sequence,
        at=at,
    )


def test_release_handoff_appends_exact_successor_without_mutating_source(
    tmp_path: Path,
) -> None:
    source_manifest, database, legacy = _legacy_checkpoint(tmp_path)
    source = _initialize(source_manifest, database, legacy)
    target_manifest = _target_manifest(source_manifest)
    source_decision = build_fast_paper_runtime_state(
        source_manifest,
        cursor=None,
    )

    result = initialize_fast_paper_authoritative_release_handoff(
        source_manifest,
        target_manifest,
        source.binding,
        _execution_policy(target_manifest),
        source_decision,
        target_fast_run_id=_TARGET_RUN_ID,
        database_path=database,
        created_at_unix_ms=legacy.state.last_cycle_at_unix_ms + 1,
    )

    assert result.handoff.source_run_id == source.binding.fast_run_id
    assert result.handoff.target_run_id == _TARGET_RUN_ID
    assert (
        result.handoff.source_checkpoint_payload_sha256
        == source.checkpoint.payload_sha256
    )
    assert result.binding.release_source_sha == _TARGET_RELEASE_SHA
    assert result.checkpoint.run_id == _TARGET_RUN_ID
    assert result.checkpoint.sequence == 0
    assert result.checkpoint.state == source.checkpoint.state
    assert result.runtime_state.market_positions == ()
    assert result.runtime_state.last_processed_source_sequence is None
    assert result.decision_state.cursor is None
    assert (
        result.decision_state.release_source_sha
        == _TARGET_RELEASE_SHA
    )

    restored = load_fast_paper_authoritative_release_handoff(
        database,
        target_fast_run_id=_TARGET_RUN_ID,
    )
    assert restored == result.handoff

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM paper_loop_checkpoints
            WHERE run_id = ?
            """,
            (source.binding.fast_run_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_runtime_states
            WHERE fast_run_id = ?
            """,
            (source.binding.fast_run_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_release_handoffs
            WHERE target_run_id = ?
            """,
            (_TARGET_RUN_ID,),
        ).fetchone() == (1,)


def test_exact_release_handoff_repeat_is_idempotent(
    tmp_path: Path,
) -> None:
    source_manifest, database, legacy = _legacy_checkpoint(tmp_path)
    source = _initialize(source_manifest, database, legacy)
    target_manifest = _target_manifest(source_manifest)
    source_decision = build_fast_paper_runtime_state(
        source_manifest,
        cursor=None,
    )
    kwargs = dict(
        target_fast_run_id=_TARGET_RUN_ID,
        database_path=database,
        created_at_unix_ms=legacy.state.last_cycle_at_unix_ms + 1,
    )

    first = initialize_fast_paper_authoritative_release_handoff(
        source_manifest,
        target_manifest,
        source.binding,
        _execution_policy(target_manifest),
        source_decision,
        **kwargs,
    )
    second = initialize_fast_paper_authoritative_release_handoff(
        source_manifest,
        target_manifest,
        source.binding,
        _execution_policy(target_manifest),
        source_decision,
        **kwargs,
    )

    assert second == first
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM paper_loop_checkpoints
            WHERE run_id = ?
            """,
            (_TARGET_RUN_ID,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_runtime_states
            WHERE fast_run_id = ?
            """,
            (_TARGET_RUN_ID,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_authoritative_release_handoffs
            WHERE target_run_id = ?
            """,
            (_TARGET_RUN_ID,),
        ).fetchone() == (1,)


def test_release_handoff_rejects_unexecuted_learned_decision(
    tmp_path: Path,
) -> None:
    source_manifest, database, legacy = _legacy_checkpoint(tmp_path)
    source = _initialize(source_manifest, database, legacy)
    target_manifest = _target_manifest(source_manifest)
    record = _decision_record(
        source.checkpoint,
        sequence=1,
        signature="release-gap",
    )
    source_decision = build_fast_paper_runtime_state(
        source_manifest,
        cursor=_cursor(record),
    )

    with pytest.raises(
        FastPaperAuthoritativeReleaseHandoffError,
        match="equal decision and execution cursors",
    ):
        initialize_fast_paper_authoritative_release_handoff(
            source_manifest,
            target_manifest,
            source.binding,
            _execution_policy(target_manifest),
            source_decision,
            target_fast_run_id=_TARGET_RUN_ID,
            database_path=database,
            created_at_unix_ms=record.decision_observed_at_unix_ms,
        )


def test_release_handoff_rejects_strategy_or_policy_drift(
    tmp_path: Path,
) -> None:
    source_manifest, database, legacy = _legacy_checkpoint(tmp_path)
    source = _initialize(source_manifest, database, legacy)
    changed_policy = replace(
        source_manifest.action_policy,
        minimum_buy_value_bps=(
            source_manifest.action_policy.minimum_buy_value_bps + 1.0
        ),
    )
    target_manifest = _target_manifest(
        source_manifest,
        action_policy=changed_policy,
    )
    source_decision = build_fast_paper_runtime_state(
        source_manifest,
        cursor=None,
    )

    with pytest.raises(
        FastPaperAuthoritativeReleaseHandoffError,
        match="action_policy drift",
    ):
        initialize_fast_paper_authoritative_release_handoff(
            source_manifest,
            target_manifest,
            source.binding,
            _execution_policy(target_manifest),
            source_decision,
            target_fast_run_id=_TARGET_RUN_ID,
            database_path=database,
            created_at_unix_ms=legacy.state.last_cycle_at_unix_ms + 1,
        )


def test_release_handoff_carries_open_position_mapping_and_learned_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_manifest, database, legacy = _legacy_checkpoint(tmp_path)
    source = _initialize(source_manifest, database, legacy)
    source_policy = _execution_policy(source_manifest)
    record = _decision_record(
        source.checkpoint,
        sequence=1,
        signature="release-open-buy",
    )
    at = record.decision_observed_at_unix_ms
    evidence = _evidence_for(
        monkeypatch,
        source_manifest,
        record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=at + 200,
        entry_observed_at=at + 150,
        exit_observed_at=at + 155,
    )
    bought = run_fast_paper_authoritative_execution(
        source_manifest,
        source.binding,
        source_policy,
        _source(record, evidence),
        committed_at_unix_ms=at + 200,
    )
    assert bought.buy_result is not None
    assert bought.buy_result.outcome is FastPaperBuyOutcome.FILLED
    assert bought.checkpoint.state.pending_buy is None
    assert len(bought.runtime_state.market_positions) == 1
    assert len(
        tuple(
            position
            for position in bought.checkpoint.state.ledger.positions
            if position.state is PaperPositionState.OPEN
        )
    ) == 1

    source_decision = build_fast_paper_runtime_state(
        source_manifest,
        cursor=_cursor(record),
    )
    target_manifest = _target_manifest(source_manifest)

    result = initialize_fast_paper_authoritative_release_handoff(
        source_manifest,
        target_manifest,
        source.binding,
        _execution_policy(target_manifest),
        source_decision,
        target_fast_run_id=_TARGET_RUN_ID,
        database_path=database,
        created_at_unix_ms=at + 201,
    )

    assert result.checkpoint.state == bought.checkpoint.state
    assert (
        result.runtime_state.market_positions
        == bought.runtime_state.market_positions
    )
    assert (
        result.runtime_state.last_processed_source_sequence
        == bought.runtime_state.last_processed_source_sequence
        == 1
    )
    assert (
        result.runtime_state.last_processed_source_event_id
        == bought.runtime_state.last_processed_source_event_id
    )
    assert (
        result.runtime_state
        .last_processed_decision_evidence_fingerprint_sha256
        == bought.runtime_state
        .last_processed_decision_evidence_fingerprint_sha256
    )
    assert result.decision_state.cursor == source_decision.cursor


def test_release_handoff_rejects_pending_buy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_manifest, database, legacy = _legacy_checkpoint(tmp_path)
    source = _initialize(source_manifest, database, legacy)
    record = _decision_record(
        source.checkpoint,
        sequence=1,
        signature="release-pending-buy",
    )
    at = record.decision_observed_at_unix_ms
    evidence = _evidence_for(
        monkeypatch,
        source_manifest,
        record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=at + 20,
        entry_observed_at=at + 10,
        exit_observed_at=at + 15,
    )
    deferred = run_fast_paper_authoritative_execution(
        source_manifest,
        source.binding,
        _execution_policy(source_manifest),
        _source(record, evidence),
        committed_at_unix_ms=at + 20,
    )
    assert deferred.buy_result is not None
    assert deferred.buy_result.outcome is FastPaperBuyOutcome.DEFERRED
    assert deferred.checkpoint.state.pending_buy is not None

    source_decision = build_fast_paper_runtime_state(
        source_manifest,
        cursor=_cursor(record),
    )
    target_manifest = _target_manifest(source_manifest)

    with pytest.raises(
        FastPaperAuthoritativeReleaseHandoffError,
        match="pending BUY",
    ):
        initialize_fast_paper_authoritative_release_handoff(
            source_manifest,
            target_manifest,
            source.binding,
            _execution_policy(target_manifest),
            source_decision,
            target_fast_run_id=_TARGET_RUN_ID,
            database_path=database,
            created_at_unix_ms=at + 21,
        )


def test_release_handoff_source_has_no_service_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "authoritative_release_handoff.py"
    ).read_text(encoding="utf-8")

    for required in (
        "BEGIN IMMEDIATE",
        "build_fast_paper_authoritative_binding",
        "build_fast_paper_authoritative_runtime_state",
        "build_fast_paper_runtime_state",
        "source_checkpoint.state",
        "source_runtime_state.market_positions",
    ):
        assert required in source

    for forbidden in (
        "systemctl",
        "subprocess",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "LIVE_ENABLED",
        "score_candidate",
        "decide_entry",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
    ):
        assert forbidden not in source
