from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_coordinator as coordinator
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowServiceCoordinatorResult,
    FastPaperShadowServiceExecutionConfig,
    run_fast_paper_shadow_service_coordinated_cycle,
)
from shreks_brain.fast_paper_runtime.shadow_service import (
    FastPaperShadowServiceBootstrap,
    FastPaperShadowServiceConfig,
)


def _cursor(sequence: int | None):
    if sequence is None:
        return None
    return SimpleNamespace(decision_sequence=sequence)


def _decision_bootstrap(sequence: int | None = None):
    manifest = SimpleNamespace(
        manifest_fingerprint_sha256="a" * 64,
    )
    return FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=object(),
        state=SimpleNamespace(cursor=_cursor(sequence)),
    )


def _decision_config(tmp_path: Path, *, maximum_decisions: int = 8):
    return FastPaperShadowServiceConfig(
        manifest_path=tmp_path / "manifest.json",
        policy_path=tmp_path / "policy.json",
        evidence_directory=tmp_path / "decision-evidence",
        cycle_interval_seconds=1.0,
        maximum_decisions=maximum_decisions,
    )


def _execution_config(tmp_path: Path):
    return FastPaperShadowServiceExecutionConfig(
        execution_policy_path=(tmp_path / "execution-policy.json").resolve(),
        source_directory=(tmp_path / "execution-sources").resolve(),
        ledger_database_path=(tmp_path / "ledger.sqlite3").resolve(),
        run_id="shadow-run-1",
    )


def _execution_bootstrap(
    sequence: int | None,
    *,
    pending_buy=None,
    market_positions=(),
):
    return SimpleNamespace(
        binding=object(),
        execution_policy=object(),
        checkpoint=object(),
        source_directory=Path("/tmp/execution-sources"),
        runtime_state=SimpleNamespace(
            last_processed_source_sequence=sequence,
            pending_buy=pending_buy,
            market_positions=market_positions,
        ),
    )


def test_coordinator_produces_at_most_one_flat_decision_when_cursors_equal(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap()
    decision_config = _decision_config(tmp_path, maximum_decisions=8)
    execution_config = _execution_config(tmp_path)
    execution_bootstrap = _execution_bootstrap(None)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda manifest, config: (
            captured.update(
                bootstrap_manifest=manifest,
                execution_config=config,
            )
            or execution_bootstrap
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_execution_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "equal cursors must produce a decision, not execute"
        ),
    )

    record = SimpleNamespace(
        venue="pump_fun_bonding_curve",
        mint="Mint111",
        quote_mint="Quote111",
    )
    flat = FastCampaignDecisionPosition(kind="FLAT")

    def position(state, market_key):
        captured.update(
            posture_state=state,
            market_key=market_key,
        )
        return flat

    monkeypatch.setattr(
        coordinator,
        "fast_paper_shadow_decision_position",
        position,
    )

    updated = FastPaperShadowServiceBootstrap(
        manifest=decision_bootstrap.manifest,
        policy=decision_bootstrap.policy,
        state=SimpleNamespace(cursor=_cursor(1)),
    )

    def run_decision(
        supplied_bootstrap,
        supplied_config,
        *,
        clock_unix_ms,
        position_resolver,
    ):
        captured.update(
            decision_bootstrap=supplied_bootstrap,
            decision_config=supplied_config,
            clock=clock_unix_ms,
            resolved_position=position_resolver(record),
        )
        return updated, 1

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        run_decision,
    )
    clock = lambda: 12_345

    result = run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        decision_config,
        execution_config,
        clock_unix_ms=clock,
        committed_at_unix_ms=20_000,
    )

    assert type(result) is FastPaperShadowServiceCoordinatorResult
    assert result.decision_bootstrap is updated
    assert result.execution_bootstrap is execution_bootstrap
    assert result.decisions_produced == 1
    assert result.executions_committed == 0
    assert captured["decision_config"].maximum_decisions == 1
    assert captured["clock"] is clock
    assert captured["resolved_position"] == flat
    assert captured["posture_state"] is execution_bootstrap.runtime_state
    assert captured["market_key"] == (
        "pump_fun_bonding_curve:Mint111:Quote111"
    )


def test_coordinator_pending_decision_waits_without_producing_more(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    decision_config = _decision_config(tmp_path)
    execution_config = _execution_config(tmp_path)
    execution_bootstrap = _execution_bootstrap(None)

    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_execution_cycle",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "pending execution must block another learned decision"
        ),
    )

    result = run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        decision_config,
        execution_config,
        committed_at_unix_ms=20_000,
    )

    assert result.decision_bootstrap is decision_bootstrap
    assert result.execution_bootstrap is execution_bootstrap
    assert result.decisions_produced == 0
    assert result.executions_committed == 0


def test_coordinator_successful_execution_reloads_and_requires_cursor_catchup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    decision_config = _decision_config(tmp_path)
    execution_config = _execution_config(tmp_path)
    before = _execution_bootstrap(None)
    after = _execution_bootstrap(1)
    bootstraps = iter((before, after))
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: next(bootstraps),
    )

    def execute(
        manifest,
        supplied_bootstrap,
        *,
        decision_evidence_directory,
        committed_at_unix_ms,
    ):
        captured.update(
            manifest=manifest,
            bootstrap=supplied_bootstrap,
            evidence_directory=decision_evidence_directory,
            committed_at_unix_ms=committed_at_unix_ms,
        )
        return 1

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_execution_cycle",
        execute,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "execution catch-up invocation must not also produce a decision"
        ),
    )

    result = run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        decision_config,
        execution_config,
        committed_at_unix_ms=20_000,
    )

    assert result.execution_bootstrap is after
    assert result.executions_committed == 1
    assert result.decisions_produced == 0
    assert captured["bootstrap"] is before
    assert captured["evidence_directory"] == (
        decision_config.evidence_directory
    )
    assert captured["committed_at_unix_ms"] == 20_000


def test_coordinator_rejects_execution_success_without_durable_cursor_catchup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    execution_config = _execution_config(tmp_path)
    stalled = _execution_bootstrap(None)

    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: stalled,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_execution_cycle",
        lambda *_args, **_kwargs: 1,
    )

    with pytest.raises(ValueError, match="catch up|cursor|durable"):
        run_fast_paper_shadow_service_coordinated_cycle(
            decision_bootstrap,
            _decision_config(tmp_path),
            execution_config,
            committed_at_unix_ms=20_000,
        )


@pytest.mark.parametrize(
    ("decision_sequence", "execution_sequence"),
    (
        (0, 1),
        (3, 1),
    ),
)
def test_coordinator_rejects_invalid_cursor_order_or_gap(
    monkeypatch,
    tmp_path: Path,
    decision_sequence: int,
    execution_sequence: int,
) -> None:
    decision_bootstrap = _decision_bootstrap(
        None if decision_sequence == 0 else decision_sequence
    )
    execution_bootstrap = _execution_bootstrap(execution_sequence)
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid cursor relationship must fail before decisions"
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_execution_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid cursor relationship must fail before execution"
        ),
    )

    with pytest.raises(ValueError, match="cursor|sequence|gap|ahead"):
        run_fast_paper_shadow_service_coordinated_cycle(
            decision_bootstrap,
            _decision_config(tmp_path),
            _execution_config(tmp_path),
            committed_at_unix_ms=20_000,
        )


@pytest.mark.parametrize(
    ("pending_buy", "market_positions", "match"),
    (
        (object(), (), "pending BUY"),
        (
            None,
            (SimpleNamespace(market_key="market-open"),),
            "OPEN|reduction",
        ),
    ),
)
def test_coordinator_blocks_new_decision_for_unresolved_economic_posture(
    monkeypatch,
    tmp_path: Path,
    pending_buy,
    market_positions,
    match: str,
) -> None:
    decision_bootstrap = _decision_bootstrap()
    execution_bootstrap = _execution_bootstrap(
        None,
        pending_buy=pending_buy,
        market_positions=market_positions,
    )
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "blocked economic posture must fail before decision production"
        ),
    )

    with pytest.raises(ValueError, match=match):
        run_fast_paper_shadow_service_coordinated_cycle(
            decision_bootstrap,
            _decision_config(tmp_path),
            _execution_config(tmp_path),
            committed_at_unix_ms=20_000,
        )


def test_coordinator_source_has_orchestration_authority_only() -> None:
    source = Path(coordinator.__file__).read_text(encoding="utf-8")
    required = (
        "bootstrap_fast_paper_shadow_service_execution",
        "run_fast_paper_shadow_service_cycle",
        "run_fast_paper_shadow_service_execution_cycle",
        "fast_paper_shadow_decision_position",
    )
    for marker in required:
        assert marker in source

    forbidden = (
        "produce_fast_paper_shadow_execution_input_source_record",
        "write_fast_paper_shadow_execution_input_source_record",
        "execute_fast_paper_shadow_decision",
        "commit_fast_paper_shadow_transition_atomically",
        "initialize_fast_paper_shadow_ledger_database",
        "shreks_brain.scoring",
        "score_candidate",
        "requests",
        "httpx",
        "urllib",
        "sqlite3",
        "RuntimeMode.LIVE",
    )
    for marker in forbidden:
        assert marker not in source
