from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow as shadow
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper import FastPaperBuyOutcome, FastPaperPositionOutcome
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION,
    FastPaperShadowExecutionInput,
    FastPaperShadowPendingBuy,
    FastPaperShadowReductionQuote,
    build_fast_paper_shadow_ledger_binding,
    build_fast_paper_shadow_runtime_state,
    build_fast_paper_shadow_runtime_state_from_transition,
    build_initial_fast_paper_shadow_ledger_state,
    execute_fast_paper_shadow_decision,
    initialize_fast_paper_shadow_ledger_database,
    load_latest_fast_paper_shadow_ledger_checkpoint,
    load_latest_fast_paper_shadow_runtime_state,
    retry_fast_paper_shadow_pending_buy,
    save_fast_paper_shadow_ledger_checkpoint,
    save_fast_paper_shadow_runtime_state,
)
from shreks_brain.fast_paper_runtime.shadow_executor import (
    FAST_PAPER_SHADOW_EXECUTOR_VERSION,
    FastPaperShadowPendingBuyRetryInput,
)
from shreks_brain.fast_paper_runtime.shadow_execution_input import (
    build_fast_paper_shadow_execution_policy,
)
from shreks_brain.paper import PaperPositionState
from shreks_brain.regime import MarketRegime

from test_fast_paper_shadow_decision import (
    _fake_champion,
    _manifest,
    _quote,
    _record,
)
from test_fast_paper_shadow_execution_input import (
    _decision,
    _entry,
    _execution_policy,
    _risk,
    _usd,
)


def _runtime_fixture(tmp_path: Path, *, zero_latency: bool = False):
    manifest = _manifest(tmp_path)
    policy = _execution_policy(manifest)
    if zero_latency:
        policy = build_fast_paper_shadow_execution_policy(
            manifest,
            risk_policy=policy.risk_policy,
            fill_policy=replace(
                policy.fill_policy,
                assumed_latency_ms=0,
            ),
            position_action_policy=policy.position_action_policy,
        )
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-executor-run",
        database_path=tmp_path / "shadow-ledger" / "runtime.sqlite3",
    )
    initialize_fast_paper_shadow_ledger_database(manifest, binding)
    paper = build_initial_fast_paper_shadow_ledger_state(
        manifest,
        binding,
        starting_cash_usd=20_000.0,
        as_of_unix_ms=19_000,
        fill_policy=policy.fill_policy,
        position_action_policy=policy.position_action_policy,
    )
    checkpoint = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        paper,
        sequence=0,
        created_at_unix_ms=19_000,
    )
    posture = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
        pending_buy=None,
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        posture,
        created_at_unix_ms=19_000,
    )
    return manifest, binding, policy, checkpoint, posture


def _record_at(base, *, signature: str, sequence: int, at: int):
    return replace(
        base,
        decision_signature=signature,
        decision_sequence=sequence,
        decision_observed_at_unix_ms=at,
        decision_source_observed_at_unix_ms=at,
        decision_occurred_at_unix_ms=at,
        decision_slot=base.decision_slot + sequence,
        snapshot_as_of_unix_ms=at,
    )


def _evidence_for(
    monkeypatch,
    manifest,
    record,
    *,
    action: str,
    position: FastCampaignDecisionPosition,
    evaluated_at: int,
    entry_observed_at: int,
    exit_observed_at: int,
    reduction_observed_at: int | None = None,
):
    monkeypatch.setattr(
        shadow,
        "read_fast_forecast_champion",
        lambda _path: _fake_champion(manifest),
    )
    monkeypatch.setattr(
        shadow,
        "evaluate_fast_campaign_decision_batch_offline",
        lambda *, binary_path, champion_path, batch, timeout_seconds=None: (
            _decision(manifest, batch.decisions[0], action=action)
        ),
    )
    ticks = iter((1_000, 1_250))
    monkeypatch.setattr(shadow.time, "monotonic_ns", lambda: next(ticks))

    reductions = ()
    if reduction_observed_at is not None:
        reductions = (
            FastPaperShadowReductionQuote(
                target_exposure_fraction=0.25,
                quote=_quote(
                    record,
                    observed_at=reduction_observed_at,
                    execution_price=0.985,
                ),
            ),
        )

    return shadow.evaluate_fast_paper_shadow_decision(
        manifest,
        record,
        position,
        evaluated_at_unix_ms=evaluated_at,
        max_exposure_fraction=0.75,
        entry_quote=_quote(
            record,
            observed_at=entry_observed_at,
            execution_price=1.01,
        ),
        exit_quote=_quote(
            record,
            observed_at=exit_observed_at,
            execution_price=0.98,
        ),
        reduction_quotes=reductions,
    )


def _source(record, evidence):
    action = evidence.decision.action
    return FastPaperShadowExecutionInput(
        decision_evidence=evidence,
        entry_authority=_entry(record) if action == "BUY" else None,
        risk_context=(
            _risk(evidence.evaluated_at_unix_ms)
            if action == "BUY"
            else None
        ),
        market_regime=(
            MarketRegime.NORMAL if action == "BUY" else None
        ),
        quote_usd_evidence=(
            None
            if action == "SKIP"
            else _usd(
                record,
                observed_at=evidence.evaluated_at_unix_ms - 1,
            )
        ),
    )


def _persist(
    manifest,
    binding,
    transition,
    *,
    sequence: int,
    created_at: int,
):
    checkpoint = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        transition.next_paper_state,
        sequence=sequence,
        created_at_unix_ms=created_at,
    )
    posture = build_fast_paper_shadow_runtime_state_from_transition(
        manifest,
        binding,
        checkpoint,
        transition,
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        posture,
        created_at_unix_ms=created_at,
    )
    return checkpoint, posture


def test_shadow_runtime_v2_binds_pending_buy_target_to_checkpoint(
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, _ = _runtime_fixture(tmp_path)
    assert FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION == 2

    # A companion pending target cannot exist without canonical pending BUY.
    pending = FastPaperShadowPendingBuy(
        market_key="pump:mint:quote",
        mint="mint",
        source_event_id="event:0",
        target_exposure_fraction=0.5,
    )
    with pytest.raises(ValueError, match="pending|BUY|checkpoint"):
        build_fast_paper_shadow_runtime_state(
            manifest,
            binding,
            checkpoint,
            market_positions=(),
            pending_buy=pending,
        )


def test_deferred_buy_survives_restart_fills_once_and_exact_replay_is_noop(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
    source = _source(record, evidence)

    deferred = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint,
        posture,
        source,
    )
    assert deferred.version == FAST_PAPER_SHADOW_EXECUTOR_VERSION
    assert deferred.buy_result is not None
    assert deferred.buy_result.outcome is FastPaperBuyOutcome.DEFERRED
    assert deferred.next_paper_state.pending_buy is not None
    assert deferred.next_pending_buy is not None
    assert deferred.next_pending_buy.target_exposure_fraction == pytest.approx(0.5)
    assert deferred.next_market_positions == ()

    checkpoint1, posture1 = _persist(
        manifest,
        binding,
        deferred,
        sequence=1,
        created_at=20_020,
    )
    restored_checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    restored_posture = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    assert restored_checkpoint == checkpoint1
    assert restored_posture == posture1
    assert restored_checkpoint is not None
    assert restored_checkpoint.state.pending_buy is not None
    assert restored_posture is not None
    assert restored_posture.pending_buy == deferred.next_pending_buy

    with pytest.raises(ValueError, match="pending BUY|resolve|retry"):
        execute_fast_paper_shadow_decision(
            manifest,
            policy,
            restored_checkpoint,
            restored_posture,
            source,
        )

    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=20_200,
        quote=replace(
            evidence.entry_quote,
            observed_at_unix_ms=20_150,
        ),
        risk_context=_risk(20_200),
        quote_usd_evidence=_usd(record, observed_at=20_190),
    )
    filled = retry_fast_paper_shadow_pending_buy(
        manifest,
        policy,
        binding,
        restored_checkpoint,
        restored_posture,
        retry,
    )
    assert filled.buy_result is not None
    assert filled.buy_result.outcome is FastPaperBuyOutcome.FILLED
    assert filled.next_paper_state.pending_buy is None
    assert filled.next_pending_buy is None
    assert len(filled.next_market_positions) == 1
    assert (
        filled.next_market_positions[0].current_exposure_fraction
        == pytest.approx(0.5)
    )
    assert len(filled.next_paper_state.position_action_states) == 1

    checkpoint2, posture2 = _persist(
        manifest,
        binding,
        filled,
        sequence=2,
        created_at=20_200,
    )
    replay = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint2,
        posture2,
        source,
    )
    assert replay.replayed is True
    assert replay.buy_result is None
    assert replay.position_result is None
    assert replay.next_paper_state == checkpoint2.state
    assert replay.next_market_positions == posture2.market_positions
    assert len(checkpoint2.state.ledger.processed_intent_keys) == 1


def test_pending_reduce_survives_restart_and_updates_exposure_from_actual_quantity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    base = _record()

    buy_evidence = _evidence_for(
        monkeypatch,
        manifest,
        base,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    bought = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint,
        posture,
        _source(base, buy_evidence),
    )
    assert bought.buy_result is not None
    assert bought.buy_result.outcome is FastPaperBuyOutcome.FILLED
    checkpoint1, posture1 = _persist(
        manifest,
        binding,
        bought,
        sequence=1,
        created_at=20_020,
    )

    record2 = _record_at(
        base,
        signature="shadow-event-2",
        sequence=2,
        at=20_300,
    )
    reduce_evidence = _evidence_for(
        monkeypatch,
        manifest,
        record2,
        action="REDUCE",
        position=FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        ),
        evaluated_at=20_320,
        entry_observed_at=20_310,
        exit_observed_at=20_315,
        reduction_observed_at=20_312,
    )
    # Restore latency for the exit so the selected REDUCE becomes pending.
    delayed_policy = build_fast_paper_shadow_execution_policy(
        manifest,
        risk_policy=policy.risk_policy,
        fill_policy=replace(policy.fill_policy, assumed_latency_ms=100),
        position_action_policy=policy.position_action_policy,
    )
    # Runtime checkpoint policies are pinned; use a checkpoint state with the
    # same manifest version and delayed policy value before this decision.
    delayed_state = replace(
        checkpoint1.state,
        fill_policy=delayed_policy.fill_policy,
    )
    checkpoint_delayed = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        delayed_state,
        sequence=2,
        created_at_unix_ms=20_021,
    )
    posture_delayed = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint_delayed,
        market_positions=posture1.market_positions,
        pending_buy=None,
        last_processed_source_sequence=posture1.last_processed_source_sequence,
        last_processed_source_event_id=posture1.last_processed_source_event_id,
        last_processed_decision_evidence_fingerprint_sha256=(
            posture1.last_processed_decision_evidence_fingerprint_sha256
        ),
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        posture_delayed,
        created_at_unix_ms=20_021,
    )

    reduced_pending = execute_fast_paper_shadow_decision(
        manifest,
        delayed_policy,
        binding,
        checkpoint_delayed,
        posture_delayed,
        _source(record2, reduce_evidence),
    )
    assert reduced_pending.position_result is not None
    assert (
        reduced_pending.position_result.outcome
        is FastPaperPositionOutcome.DEFERRED
    )
    action_state = reduced_pending.next_paper_state.position_action_states[0]
    assert action_state.pending_exit is not None
    checkpoint3, posture3 = _persist(
        manifest,
        binding,
        reduced_pending,
        sequence=3,
        created_at=20_320,
    )

    record3 = _record_at(
        base,
        signature="shadow-event-3",
        sequence=3,
        at=20_500,
    )
    hold_evidence = _evidence_for(
        monkeypatch,
        manifest,
        record3,
        action="HOLD",
        position=FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        ),
        evaluated_at=20_530,
        entry_observed_at=20_510,
        exit_observed_at=20_520,
    )
    resolved = execute_fast_paper_shadow_decision(
        manifest,
        delayed_policy,
        binding,
        checkpoint3,
        posture3,
        _source(record3, hold_evidence),
    )
    assert resolved.position_result is not None
    assert (
        resolved.position_result.outcome
        is FastPaperPositionOutcome.REDUCED
    )
    assert resolved.next_paper_state.position_action_states[0].pending_exit is None
    assert len(resolved.next_market_positions) == 1
    assert (
        resolved.next_market_positions[0].current_exposure_fraction
        == pytest.approx(0.25)
    )


def test_shadow_executor_source_uses_only_existing_paper_execution_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "shadow_executor.py"
    ).read_text(encoding="utf-8")

    for required in (
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "run_fast_paper_event",
        "fast_campaign_result_to_paper_assessment",
        "FastPaperRuntimeState",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.scoring",
        "ScorePolicy",
        "DecisionPolicy",
        "score_candidate",
        "decide_entry",
        "sqlite3",
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
