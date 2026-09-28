from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.authoritative_coordinator as coordinator
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper import FastPaperBuyOutcome
from shreks_brain.fast_paper_runtime.authoritative_coordinator import (
    FastPaperAuthoritativeCoordinatorResult,
    run_fast_paper_authoritative_coordinated_cycle,
)
from shreks_brain.fast_paper_runtime.authoritative_service_execution import (
    FastPaperAuthoritativeServiceExecutionConfig,
    bootstrap_fast_paper_authoritative_service_execution,
    produce_fast_paper_authoritative_execution_input_source_record,
    run_fast_paper_authoritative_service_execution,
)
from shreks_brain.fast_paper_runtime.shadow import (
    write_fast_paper_shadow_decision_evidence,
)
from shreks_brain.fast_paper_runtime.shadow_execution_input import (
    write_fast_paper_shadow_execution_policy,
)
from shreks_brain.fast_paper_runtime.shadow_execution_source import (
    write_fast_paper_shadow_execution_input_source_record,
)
from shreks_brain.fast_paper_runtime.shadow_executor import (
    FastPaperShadowPendingBuyRetryInput,
)
from shreks_brain.fast_paper_runtime.shadow_service import (
    FastPaperShadowServiceBootstrap,
    FastPaperShadowServiceConfig,
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
    policy_path = (tmp_path / "authority" / "execution-policy.json").resolve()
    policy_path.parent.mkdir()
    write_fast_paper_shadow_execution_policy(policy, policy_path)
    source_directory = (tmp_path / "execution-sources").resolve()
    source_directory.mkdir()
    evidence_directory = (tmp_path / "decision-evidence").resolve()
    evidence_directory.mkdir()
    execution_config = FastPaperAuthoritativeServiceExecutionConfig(
        execution_policy_path=policy_path,
        source_directory=source_directory,
        database_path=database.resolve(),
        run_id=handoff.binding.fast_run_id,
    )
    decision_config = FastPaperShadowServiceConfig(
        manifest_path=(tmp_path / "manifest.json").resolve(),
        policy_path=(tmp_path / "decision-policy.json").resolve(),
        evidence_directory=evidence_directory,
        cycle_interval_seconds=1.0,
        maximum_decisions=8,
    )
    return (
        manifest,
        policy,
        handoff,
        execution_config,
        decision_config,
    )


def _decision_bootstrap(manifest, sequence: int | None):
    cursor = (
        None
        if sequence is None
        else SimpleNamespace(decision_sequence=sequence)
    )
    return FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=object(),
        state=SimpleNamespace(cursor=cursor),
    )


def _decision_record(checkpoint, *, sequence: int, signature: str):
    at = checkpoint.state.as_of_unix_ms + 1_000 * sequence
    return _record_at(
        _record(),
        signature=signature,
        sequence=sequence,
        at=at,
    )


def _evidence_path(directory: Path, sequence: int) -> Path:
    return directory / f"shadow-{sequence:020d}.json"


def test_authoritative_execution_source_bridge_commits_skip_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        _policy,
        handoff,
        execution_config,
        _decision_config,
    ) = _fixture(tmp_path)
    bootstrap = bootstrap_fast_paper_authoritative_service_execution(
        manifest,
        execution_config,
    )
    record = _decision_record(
        handoff.checkpoint,
        sequence=1,
        signature="authoritative-service-skip",
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

    result = run_fast_paper_authoritative_service_execution(
        manifest,
        bootstrap,
        source,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
        risk_day_started_at_unix_ms=None,
        committed_at_unix_ms=evidence.evaluated_at_unix_ms,
    )

    assert result.committed is True
    assert result.replayed is False
    assert result.checkpoint.sequence == 1
    source_path = bootstrap.source_directory / (
        f"{evidence.evidence_fingerprint_sha256}.json"
    )
    assert source_path.is_file()
    restored = bootstrap_fast_paper_authoritative_service_execution(
        manifest,
        execution_config,
    )
    assert restored.checkpoint.sequence == 1
    assert restored.runtime_state.last_processed_source_sequence == 1


def test_published_source_survives_restart_before_authoritative_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        _policy,
        handoff,
        execution_config,
        decision_config,
    ) = _fixture(tmp_path)
    bootstrap = bootstrap_fast_paper_authoritative_service_execution(
        manifest,
        execution_config,
    )
    record = _decision_record(
        handoff.checkpoint,
        sequence=1,
        signature="authoritative-source-restart",
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
    source_record = (
        produce_fast_paper_authoritative_execution_input_source_record(
            manifest,
            bootstrap.binding,
            bootstrap.execution_policy,
            bootstrap.checkpoint,
            bootstrap.runtime_state,
            source,
            source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
            risk_day_started_at_unix_ms=None,
        )
    )
    write_fast_paper_shadow_execution_input_source_record(
        source_record,
        bootstrap.source_directory,
    )
    write_fast_paper_shadow_decision_evidence(
        evidence,
        _evidence_path(decision_config.evidence_directory, 1),
    )

    decision_bootstrap = _decision_bootstrap(manifest, 1)
    result = run_fast_paper_authoritative_coordinated_cycle(
        decision_bootstrap,
        decision_config,
        execution_config,
        committed_at_unix_ms=evidence.evaluated_at_unix_ms,
    )

    assert type(result) is FastPaperAuthoritativeCoordinatorResult
    assert result.decisions_produced == 0
    assert result.executions_committed == 1
    assert result.execution_bootstrap.checkpoint.sequence == 1
    assert (
        result.execution_bootstrap.runtime_state.last_processed_source_sequence
        == 1
    )


def test_equal_cursors_produce_only_one_decision_from_authoritative_posture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        _policy,
        _handoff,
        execution_config,
        decision_config,
    ) = _fixture(tmp_path)
    decision_bootstrap = _decision_bootstrap(manifest, None)
    captured: dict[str, object] = {}
    updated = _decision_bootstrap(manifest, 1)
    row = SimpleNamespace(
        venue="pump_fun_bonding_curve",
        mint="Mint111",
        quote_mint="Quote111",
    )

    def run_decision(
        supplied_bootstrap,
        supplied_config,
        *,
        clock_unix_ms,
        position_resolver,
    ):
        captured.update(
            bootstrap=supplied_bootstrap,
            maximum_decisions=supplied_config.maximum_decisions,
            clock=clock_unix_ms,
            position=position_resolver(row),
        )
        return updated, 1

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        run_decision,
    )
    clock = lambda: 12_345
    result = run_fast_paper_authoritative_coordinated_cycle(
        decision_bootstrap,
        decision_config,
        execution_config,
        clock_unix_ms=clock,
        committed_at_unix_ms=20_000,
    )

    assert result.decision_bootstrap is updated
    assert result.decisions_produced == 1
    assert result.executions_committed == 0
    assert captured["maximum_decisions"] == 1
    assert captured["clock"] is clock
    assert captured["position"].kind == "FLAT"


def test_deferred_buy_retry_after_restart_does_not_advance_learned_cursor_twice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        _policy,
        handoff,
        execution_config,
        decision_config,
    ) = _fixture(tmp_path)
    bootstrap = bootstrap_fast_paper_authoritative_service_execution(
        manifest,
        execution_config,
    )
    record = _decision_record(
        handoff.checkpoint,
        sequence=1,
        signature="authoritative-coordinator-buy",
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
    write_fast_paper_shadow_decision_evidence(
        evidence,
        _evidence_path(decision_config.evidence_directory, 1),
    )
    source = _source(record, evidence)
    source = replace(
        source,
        entry_authority=replace(
            source.entry_authority,
            intended_base_quantity=1.0,
        ),
        risk_context=replace(
            source.risk_context,
            trading_capital_usd=(
                bootstrap.checkpoint.state.ledger.starting_cash_usd
            ),
        ),
    )
    deferred = run_fast_paper_authoritative_service_execution(
        manifest,
        bootstrap,
        source,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
        risk_day_started_at_unix_ms=0,
        committed_at_unix_ms=evidence.evaluated_at_unix_ms,
    )
    assert deferred.buy_result is not None
    assert deferred.buy_result.outcome is FastPaperBuyOutcome.DEFERRED
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
        risk_context=replace(
            _risk(retry_at),
            trading_capital_usd=(
                deferred.checkpoint.state.ledger.starting_cash_usd
            ),
        ),
        quote_usd_evidence=_usd(
            record,
            observed_at=at + 190,
        ),
    )

    decision_bootstrap = _decision_bootstrap(manifest, 1)
    calls: list[str] = []

    def retry_resolver(restored, original):
        calls.append(original.evidence_fingerprint_sha256)
        assert restored.runtime_state.last_processed_source_sequence == 1
        return retry

    result = run_fast_paper_authoritative_coordinated_cycle(
        decision_bootstrap,
        decision_config,
        execution_config,
        pending_buy_retry_resolver=retry_resolver,
        committed_at_unix_ms=retry_at,
    )

    assert result.executions_committed == 1
    assert result.execution_bootstrap.checkpoint.sequence == 2
    assert result.execution_bootstrap.checkpoint.state.pending_buy is None
    assert (
        result.execution_bootstrap.runtime_state.last_processed_source_sequence
        == 1
    )
    assert calls == [evidence.evidence_fingerprint_sha256]

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda supplied, *_args, **_kwargs: (supplied, 0),
    )
    second = run_fast_paper_authoritative_coordinated_cycle(
        decision_bootstrap,
        decision_config,
        execution_config,
        pending_buy_retry_resolver=lambda *_args: pytest.fail(
            "resolved retry must not execute twice"
        ),
        committed_at_unix_ms=retry_at + 1,
    )
    assert second.executions_committed == 0
    assert second.decisions_produced == 0


def test_authoritative_coordinator_source_has_no_control_or_shadow_ledger_writes() -> None:
    package = Path(__file__).resolve().parents[1] / "src" / "shreks_brain" / "fast_paper_runtime"
    payload = "\n".join(
        (package / name).read_text(encoding="utf-8")
        for name in (
            "authoritative_service_execution.py",
            "authoritative_coordinator.py",
        )
    )
    required = (
        "run_fast_paper_authoritative_execution",
        "run_fast_paper_authoritative_pending_buy_retry",
        "write_fast_paper_shadow_execution_input_source_record",
        "run_fast_paper_shadow_service_cycle",
    )
    forbidden = (
        "save_fast_paper_shadow_ledger_checkpoint",
        "save_fast_paper_shadow_runtime_state",
        "commit_fast_paper_shadow_transition_atomically",
        "initialize_fast_paper_shadow_ledger_database",
        "systemctl",
        "subprocess",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "required_score_threshold",
    )
    for token in required:
        assert token in payload
    for token in forbidden:
        assert token not in payload
