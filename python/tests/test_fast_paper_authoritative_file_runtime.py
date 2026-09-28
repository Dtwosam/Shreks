from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.authoritative_runtime as runtime
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper import FastPaperBuyOutcome
from shreks_brain.fast_paper_runtime.authoritative_file_authority import (
    FastPaperAuthoritativeAuthorityUnavailable,
    build_fast_paper_authoritative_buy_authority_source_record,
    build_fast_paper_authoritative_pending_buy_retry_source_record,
    read_fast_paper_authoritative_buy_authority_source_record,
    read_fast_paper_authoritative_pending_buy_retry_source_record,
    resolve_fast_paper_authoritative_execution_authority,
    resolve_fast_paper_authoritative_pending_buy_retry,
    write_fast_paper_authoritative_buy_authority_source_record,
    write_fast_paper_authoritative_pending_buy_retry_source_record,
)
from shreks_brain.fast_paper_runtime.authoritative_runtime import (
    FastPaperAuthoritativeRuntimeBootstrap,
    FastPaperAuthoritativeRuntimeConfig,
    run_fast_paper_authoritative_runtime_cycle,
)
from shreks_brain.fast_paper_runtime.authoritative_service_execution import (
    FastPaperAuthoritativeServiceExecutionConfig,
    bootstrap_fast_paper_authoritative_service_execution,
    run_fast_paper_authoritative_service_execution,
)
from shreks_brain.fast_paper_runtime.shadow import (
    write_fast_paper_shadow_decision_evidence,
)
from shreks_brain.fast_paper_runtime.shadow_execution_input import (
    write_fast_paper_shadow_execution_policy,
)
from shreks_brain.fast_paper_runtime.shadow_executor import (
    FastPaperShadowPendingBuyRetryInput,
)
from shreks_brain.fast_paper_runtime.shadow_quote_usd_source import (
    build_fast_paper_shadow_quote_usd_source_record,
    write_fast_paper_shadow_quote_usd_source_record,
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
from test_fast_paper_shadow_buy_writer_supervisor_policy import (
    _policy_fixture,
)


def _fixture(tmp_path: Path):
    manifest, database, legacy = _legacy_checkpoint(tmp_path)
    handoff = _initialize(manifest, database, legacy)
    policy = _execution_policy(manifest)
    authority = tmp_path / "authority"
    authority.mkdir()
    policy_path = (authority / "execution-policy.json").resolve()
    write_fast_paper_shadow_execution_policy(policy, policy_path)

    roots = {}
    for name in (
        "execution",
        "decisions",
        "buy",
        "quote-usd",
        "reductions",
        "retries",
    ):
        path = (tmp_path / name).resolve()
        path.mkdir()
        roots[name] = path

    execution_config = FastPaperAuthoritativeServiceExecutionConfig(
        execution_policy_path=policy_path,
        source_directory=roots["execution"],
        database_path=database.resolve(),
        run_id=handoff.binding.fast_run_id,
    )
    execution_bootstrap = (
        bootstrap_fast_paper_authoritative_service_execution(
            manifest,
            execution_config,
        )
    )
    decision_config = FastPaperShadowServiceConfig(
        manifest_path=(tmp_path / "manifest.json").resolve(),
        policy_path=(tmp_path / "service-policy.json").resolve(),
        evidence_directory=roots["decisions"],
        cycle_interval_seconds=1.0,
        maximum_decisions=1,
    )
    writer_root = tmp_path / "writer-policy-fixture"
    writer_root.mkdir()
    _writer_manifest, _writer_service, writer_policy, _operator, _binary = (
        _policy_fixture(writer_root)
    )
    config = FastPaperAuthoritativeRuntimeConfig(
        decision_config=decision_config,
        execution_config=execution_config,
        buy_authority_source_directory=roots["buy"],
        quote_usd_source_directory=roots["quote-usd"],
        reduction_source_directory=roots["reductions"],
        pending_buy_retry_source_directory=roots["retries"],
        buy_writer_policy_path=(writer_root / "buy-writer-policy.json").resolve(),
    )
    return manifest, handoff, execution_bootstrap, config, writer_policy


def _decision_record(checkpoint, *, sequence: int, signature: str):
    at = checkpoint.state.as_of_unix_ms + 1_000 * sequence
    return _record_at(
        _record(),
        signature=signature,
        sequence=sequence,
        at=at,
    )


def _buy_source(monkeypatch, manifest, bootstrap, *, signature: str):
    record = _decision_record(
        bootstrap.checkpoint,
        sequence=1,
        signature=signature,
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
    source = replace(
        source,
        risk_context=replace(
            source.risk_context,
            trading_capital_usd=(
                bootstrap.checkpoint.state.ledger.starting_cash_usd
            ),
        ),
        quote_usd_evidence=replace(
            source.quote_usd_evidence,
            quote_to_usd_rate=100.0,
        ),
    )
    return record, evidence, source


def test_authoritative_buy_authority_round_trip_and_resolver(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest, _handoff, bootstrap, config, _writer_policy = _fixture(tmp_path)
    _record_value, evidence, source = _buy_source(
        monkeypatch,
        manifest,
        bootstrap,
        signature="authoritative-file-buy",
    )
    buy = build_fast_paper_authoritative_buy_authority_source_record(
        manifest,
        bootstrap,
        evidence,
        source.entry_authority,
        source.risk_context,
        source.market_regime,
        risk_day_started_at_unix_ms=0,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
        source_version="authoritative-test-source-v1",
        source_fingerprint_sha256="9" * 64,
    )
    write_fast_paper_authoritative_buy_authority_source_record(
        buy,
        config.buy_authority_source_directory,
    )
    quote = build_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        source.quote_usd_evidence,
    )
    write_fast_paper_shadow_quote_usd_source_record(
        quote,
        config.quote_usd_source_directory,
    )

    restored = read_fast_paper_authoritative_buy_authority_source_record(
        manifest,
        bootstrap,
        evidence,
        config.buy_authority_source_directory,
    )
    authority = resolve_fast_paper_authoritative_execution_authority(
        manifest,
        bootstrap,
        evidence,
        buy_authority_source_directory=(
            config.buy_authority_source_directory
        ),
        quote_usd_source_directory=config.quote_usd_source_directory,
    )

    assert restored == buy
    assert authority is not None
    assert authority.source.entry_authority == source.entry_authority
    assert authority.source.risk_context == source.risk_context
    assert (
        authority.source.quote_usd_evidence
        == source.quote_usd_evidence
    )
    assert authority.risk_day_started_at_unix_ms == 0


def test_authoritative_buy_authority_stale_after_checkpoint_advance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest, _handoff, bootstrap, config, _writer_policy = _fixture(tmp_path)
    _record_value, evidence, source = _buy_source(
        monkeypatch,
        manifest,
        bootstrap,
        signature="authoritative-file-stale",
    )
    buy = build_fast_paper_authoritative_buy_authority_source_record(
        manifest,
        bootstrap,
        evidence,
        source.entry_authority,
        source.risk_context,
        source.market_regime,
        risk_day_started_at_unix_ms=0,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
        source_version="authoritative-test-source-v1",
        source_fingerprint_sha256="8" * 64,
    )
    write_fast_paper_authoritative_buy_authority_source_record(
        buy,
        config.buy_authority_source_directory,
    )

    skip_record = _decision_record(
        bootstrap.checkpoint,
        sequence=1,
        signature="authoritative-file-stale-advance",
    )
    skip_at = skip_record.decision_observed_at_unix_ms
    skip_evidence = _evidence_for(
        monkeypatch,
        manifest,
        skip_record,
        action="SKIP",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=skip_at + 20,
        entry_observed_at=skip_at + 10,
        exit_observed_at=skip_at + 15,
    )
    result = run_fast_paper_authoritative_service_execution(
        manifest,
        bootstrap,
        _source(skip_record, skip_evidence),
        source_observed_at_unix_ms=skip_evidence.evaluated_at_unix_ms,
        risk_day_started_at_unix_ms=None,
        committed_at_unix_ms=skip_evidence.evaluated_at_unix_ms,
    )
    assert result.checkpoint.sequence == 1
    refreshed = bootstrap_fast_paper_authoritative_service_execution(
        manifest,
        config.execution_config,
    )
    with pytest.raises(ValueError, match="latest|state|checkpoint"):
        read_fast_paper_authoritative_buy_authority_source_record(
            manifest,
            refreshed,
            evidence,
            config.buy_authority_source_directory,
        )


def test_authoritative_pending_buy_retry_file_survives_restart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest, _handoff, bootstrap, config, _writer_policy = _fixture(tmp_path)
    record, evidence, source = _buy_source(
        monkeypatch,
        manifest,
        bootstrap,
        signature="authoritative-file-retry",
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

    restored_bootstrap = (
        bootstrap_fast_paper_authoritative_service_execution(
            manifest,
            config.execution_config,
        )
    )
    retry_at = evidence.evaluated_at_unix_ms + 200
    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=retry_at,
        quote=replace(
            evidence.entry_quote,
            observed_at_unix_ms=retry_at - 50,
            reference_price_quote=1.02,
            execution_price_quote=1.03,
        ),
        risk_context=replace(
            _risk(retry_at),
            trading_capital_usd=(
                restored_bootstrap.checkpoint.state.ledger.starting_cash_usd
            ),
        ),
        quote_usd_evidence=replace(
            _usd(record, observed_at=retry_at - 10),
            quote_to_usd_rate=100.0,
        ),
    )
    retry_record = (
        build_fast_paper_authoritative_pending_buy_retry_source_record(
            manifest,
            restored_bootstrap,
            evidence,
            retry,
            risk_day_started_at_unix_ms=0,
            source_observed_at_unix_ms=retry_at - 5,
        )
    )
    write_fast_paper_authoritative_pending_buy_retry_source_record(
        retry_record,
        config.pending_buy_retry_source_directory,
    )

    after_restart = bootstrap_fast_paper_authoritative_service_execution(
        manifest,
        config.execution_config,
    )
    restored = (
        read_fast_paper_authoritative_pending_buy_retry_source_record(
            manifest,
            after_restart,
            evidence,
            config.pending_buy_retry_source_directory,
        )
    )
    resolved = resolve_fast_paper_authoritative_pending_buy_retry(
        manifest,
        after_restart,
        evidence,
        pending_buy_retry_source_directory=(
            config.pending_buy_retry_source_directory
        ),
    )
    assert restored == retry_record
    assert resolved == retry


def test_runtime_missing_open_reduction_source_backpressures_without_decision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest, _handoff, execution_bootstrap, config, writer_policy = _fixture(tmp_path)
    decision_bootstrap = FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=object(),
        state=SimpleNamespace(cursor=None),
    )
    bootstrap = FastPaperAuthoritativeRuntimeBootstrap(
        decision_bootstrap=decision_bootstrap,
        execution_bootstrap=execution_bootstrap,
        buy_writer_policy=writer_policy,
    )
    monkeypatch.setattr(
        runtime,
        "run_fast_paper_authoritative_source_writer_cycle",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        runtime,
        "run_fast_paper_authoritative_coordinated_cycle",
        "run_fast_paper_authoritative_source_writer_cycle",
        lambda *_args, **kwargs: (
            kwargs["reduction_read_resolver"](
                SimpleNamespace(
                    venue="pump_fun_bonding_curve",
                    mint="Mint111",
                    quote_mint="So11111111111111111111111111111111111111112",
                ),
                FastCampaignDecisionPosition(
                    kind="OPEN",
                    current_exposure_fraction=0.5,
                ),
            )
        ),
    )
    monkeypatch.setattr(
        runtime,
        "require_fast_paper_authoritative_reduction_source",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FastPaperAuthoritativeAuthorityUnavailable("not ready")
        ),
    )

    restored, produced, committed = (
        run_fast_paper_authoritative_runtime_cycle(
            bootstrap,
            config,
            clock_unix_ms=lambda: 123_456,
        )
    )
    assert restored is bootstrap
    assert produced == 0
    assert committed == 0


def test_runtime_entrypoint_source_is_score_free_and_has_no_service_or_live_authority() -> None:
    package = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
    )
    payload = "\n".join(
        (package / name).read_text(encoding="utf-8")
        for name in (
            "authoritative_file_authority.py",
            "authoritative_source_writer.py",
            "authoritative_runtime.py",
        )
    )
    required = (
        "run_fast_paper_authoritative_coordinated_cycle",
        "resolve_fast_paper_authoritative_execution_authority",
        "resolve_fast_paper_authoritative_pending_buy_retry",
        "require_fast_paper_authoritative_reduction_source",
        '"production_paper_cutover": "NOT_GRANTED"',
        '"live": "DISABLED"',
    )
    forbidden = (
        "commit_fast_paper_shadow_transition_atomically",
        "initialize_fast_paper_shadow_ledger_database",
        "save_fast_paper_shadow_runtime_state",
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        "load_latest_fast_paper_shadow_runtime_state",
        "requests.",
        "httpx",
        "aiohttp",
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
