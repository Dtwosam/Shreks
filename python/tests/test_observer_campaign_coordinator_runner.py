from __future__ import annotations

from types import SimpleNamespace

import pytest

from shreks_brain.exits import create_exit_state
from shreks_brain.observer_campaign.coordinator import (
    ObserverCampaignCoordinatorError,
    ObserverPaperCampaignCoordinatorRunner,
    ObserverPaperCampaignSelectionPolicy,
)
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionState,
    PaperLedgerUpdateState,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
)
from shreks_brain.paper_evaluation import PaperEvaluationEvidenceStore
from shreks_brain.paper_loop import ManagedPaperPosition, create_paper_loop_state
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    PaperCheckpointError,
    load_latest_paper_checkpoint,
    validate_paper_accounting,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode

from test_observer_campaign_coordinator_assembly import SECOND_MINT, _seed_two_candidates
from test_observer_campaign_runner import (
    AS_OF,
    MINT,
    RUN_ID,
    _bundle,
    _candidate,
    _environment,
    _state,
)


SELECTION = ObserverPaperCampaignSelectionPolicy(
    recent_lookback_ms=100_000,
    max_entry_candidates=2,
)


def _runner(db_path, evidence_path, *, initial_state=None, candidate=None):
    return ObserverPaperCampaignCoordinatorRunner(
        db_path,
        evidence_path,
        _candidate() if candidate is None else candidate,
        RUN_ID,
        _state() if initial_state is None else initial_state,
        _bundle(),
        _environment(),
        SELECTION,
        global_risk_halt=False,
    )


def _two_open_position_state():
    base = _state()
    fill_policy = base.paper_fill_policy
    ledger = create_paper_ledger(1_000.0, 900_000)
    bundle = _bundle()

    for index, mint in enumerate((MINT, SECOND_MINT), start=1):
        intent = TradeIntent(
            mint=mint,
            side=TradeSide.BUY,
            requested_notional_usd=100.0,
            max_slippage_bps=75,
            strategy_name="fresh_launch_continuation",
            strategy_version=bundle.fresh_launch_policy.version,
            score_policy_version=bundle.score_policy.version,
            decision_policy_version=bundle.decision_policy.version,
            risk_policy_version=bundle.risk_policy.version,
            reason="ENTRY_APPROVED",
            idempotency_key=f"g1b-open-{index}",
            execution_mode=RuntimeMode.PAPER,
            as_of_unix_ms=900_000,
        )
        execution = execute_paper_intent(
            intent,
            PaperExecutionContext(
                evaluated_at_unix_ms=900_000,
                processed_intent_keys=ledger.processed_intent_keys,
                quote=PaperQuote(
                    provider="paper-test",
                    mint=mint,
                    observed_at_unix_ms=900_000,
                    state=PaperQuoteState.EXECUTABLE,
                    reference_price_usd=1.0,
                    execution_price_usd=1.0,
                    quoted_notional_usd=1_000.0,
                    available_notional_usd=1_000.0,
                ),
            ),
            fill_policy,
        )
        assert execution.state is PaperExecutionState.FILLED
        update = apply_paper_execution(ledger, intent, execution)
        assert update.state is PaperLedgerUpdateState.APPLIED
        ledger = update.ledger

    open_positions = tuple(
        position for position in ledger.positions if position.state is PaperPositionState.OPEN
    )
    assert {position.mint for position in open_positions} == {MINT, SECOND_MINT}
    managed = tuple(
        ManagedPaperPosition(
            position.position_id,
            bundle.exit_policy,
            create_exit_state(position, bundle.exit_policy),
        )
        for position in open_positions
    )
    return create_paper_loop_state(
        ledger,
        base.loop_policy,
        fill_policy,
        managed_positions=managed,
    )


def test_first_aggregate_cycle_runs_c5_once_records_e11_once_and_saves_one_checkpoint(tmp_path):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed_two_candidates(db_path)
    runner = _runner(db_path, evidence_path)

    result = runner.run_cycle(AS_OF, AS_OF)

    assert result.as_of_unix_ms == AS_OF
    assert result.next_state.last_cycle_at_unix_ms == AS_OF
    assert len(result.entry_results) == 2
    selected = tuple(item for item in result.entry_results if item.selected_for_entry)
    assert len(selected) == 1
    assert selected[0].mint == SECOND_MINT
    assert selected[0].execution is not None
    assert selected[0].execution.state is PaperExecutionState.DEFERRED
    assert result.next_state.pending_entry is not None
    assert result.next_state.pending_entry.intent.mint == SECOND_MINT

    checkpoint = load_latest_paper_checkpoint(db_path, RUN_ID)
    assert checkpoint is not None
    assert checkpoint.sequence == 1
    assert checkpoint.state == result.next_state

    accounting = validate_paper_accounting(result.next_state)
    assert accounting.status is not AccountingValidationStatus.INVALID

    evidence = PaperEvaluationEvidenceStore(evidence_path).load()
    assert len(evidence.entry_provenance) == 1
    assert evidence.executions == ()
    assert evidence.entry_provenance[0].paper_run_id == RUN_ID
    assert evidence.entry_provenance[0].mint == SECOND_MINT


def test_two_open_positions_receive_same_timestamp_exit_observations(tmp_path):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed_two_candidates(db_path)
    initial = _two_open_position_state()

    result = _runner(db_path, evidence_path, initial_state=initial).run_cycle(AS_OF, AS_OF)

    assert len(result.exit_results) == 2
    assert {item.mint for item in result.exit_results} == {MINT, SECOND_MINT}
    assert all(item.exit_assessment is not None for item in result.exit_results)
    checkpoint = load_latest_paper_checkpoint(db_path, RUN_ID)
    assert checkpoint is not None and checkpoint.sequence == 1


def test_restart_and_exact_timestamp_replay_are_idempotent(tmp_path):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed_two_candidates(db_path)

    first_runner = _runner(db_path, evidence_path)
    first = first_runner.run_cycle(AS_OF, AS_OF)
    before = PaperEvaluationEvidenceStore(evidence_path).load()

    restarted = _runner(db_path, evidence_path)
    assert restarted.load_state() == first.next_state
    replay = restarted.run_cycle(AS_OF, AS_OF)
    after = PaperEvaluationEvidenceStore(evidence_path).load()
    checkpoint = load_latest_paper_checkpoint(db_path, RUN_ID)

    assert replay.next_state == first.next_state
    assert replay.entry_results == ()
    assert replay.exit_results == ()
    assert after.document_fingerprint_sha256 == before.document_fingerprint_sha256
    assert checkpoint is not None and checkpoint.sequence == 1


def test_time_reversal_and_candidate_attribution_conflict_fail_closed(tmp_path):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed_two_candidates(db_path)
    runner = _runner(db_path, evidence_path)
    runner.run_cycle(AS_OF, AS_OF)

    with pytest.raises(ObserverCampaignCoordinatorError, match="precede"):
        runner.run_cycle(AS_OF - 1, AS_OF)

    changed = _candidate(
        candidate_version="candidate-v2",
        candidate_fingerprint_sha256="c" * 64,
    )
    with pytest.raises(ObserverCampaignCoordinatorError, match="attribution"):
        _runner(db_path, evidence_path, candidate=changed).load_state()


def test_e11_corruption_checkpoint_collision_reload_mismatch_and_restart_mismatch_fail_closed(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "observer.db"
    evidence_path = tmp_path / "e11.json"
    _seed_two_candidates(db_path)
    runner = _runner(db_path, evidence_path)
    runner.run_cycle(AS_OF, AS_OF)
    evidence_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ObserverCampaignCoordinatorError, match="evidence"):
        runner.evaluated_trades()

    collision_db = tmp_path / "collision.db"
    collision_evidence = tmp_path / "collision-e11.json"
    _seed_two_candidates(collision_db)
    collision_runner = _runner(collision_db, collision_evidence)

    import shreks_brain.observer_campaign.coordinator as coordinator_module

    def _collision(*args, **kwargs):
        raise PaperCheckpointError("checkpoint sequence collision")

    monkeypatch.setattr(coordinator_module, "save_paper_checkpoint", _collision)
    with pytest.raises(ObserverCampaignCoordinatorError, match="checkpoint"):
        collision_runner.run_cycle(AS_OF, AS_OF)

    monkeypatch.undo()
    reload_db = tmp_path / "reload.db"
    reload_evidence = tmp_path / "reload-e11.json"
    _seed_two_candidates(reload_db)
    reload_runner = _runner(reload_db, reload_evidence)
    real_load = coordinator_module.load_latest_paper_checkpoint
    calls = 0

    def _missing_reload(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_load(*args, **kwargs)
        return None

    monkeypatch.setattr(coordinator_module, "load_latest_paper_checkpoint", _missing_reload)
    with pytest.raises(ObserverCampaignCoordinatorError, match="reload"):
        reload_runner.run_cycle(AS_OF, AS_OF)

    monkeypatch.undo()
    mismatch_db = tmp_path / "mismatch.db"
    mismatch_evidence = tmp_path / "mismatch-e11.json"
    _seed_two_candidates(mismatch_db)
    mismatch_runner = _runner(mismatch_db, mismatch_evidence)
    monkeypatch.setattr(
        coordinator_module,
        "validate_restart_equivalence",
        lambda *_args, **_kwargs: SimpleNamespace(equivalent=False),
    )
    with pytest.raises(ObserverCampaignCoordinatorError, match="restart equivalence"):
        mismatch_runner.run_cycle(AS_OF, AS_OF)
