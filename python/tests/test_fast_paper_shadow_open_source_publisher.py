from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow_open_source_publisher as publisher
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowExecutionInput,
    FastPaperShadowQuoteUsdEvidence,
    FastPaperShadowServiceExecutionBootstrap,
    build_fast_paper_shadow_quote_usd_source_record,
    run_fast_paper_shadow_open_source_publisher_cycle,
    write_fast_paper_shadow_quote_usd_source_record,
)
from shreks_brain.fast_paper_runtime.shadow import (
    write_fast_paper_shadow_decision_evidence,
)

from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _runtime_fixture,
)


def _bootstrap(tmp_path: Path):
    manifest, binding, policy, checkpoint, runtime = _runtime_fixture(tmp_path)
    execution_directory = tmp_path / "execution-sources"
    execution_directory.mkdir()
    bootstrap = FastPaperShadowServiceExecutionBootstrap(
        binding=binding,
        execution_policy=policy,
        checkpoint=checkpoint,
        runtime_state=runtime,
        source_directory=execution_directory.resolve(),
    )
    decision_directory = tmp_path / "decision-evidence"
    decision_directory.mkdir()
    quote_usd_directory = tmp_path / "quote-usd-sources"
    quote_usd_directory.mkdir()
    return manifest, bootstrap, decision_directory, quote_usd_directory


def _evidence(
    monkeypatch,
    manifest,
    *,
    action: str,
    sequence: int = 1,
):
    base = _record()
    record = replace(
        base,
        decision_signature=f"open-source-{sequence}",
        decision_sequence=sequence,
        decision_observed_at_unix_ms=20_000 + sequence,
        decision_source_observed_at_unix_ms=20_000 + sequence,
        decision_occurred_at_unix_ms=20_000 + sequence,
        decision_slot=base.decision_slot + sequence,
        snapshot_as_of_unix_ms=20_000 + sequence,
        snapshot_last_sequence=sequence,
    )
    position = (
        FastCampaignDecisionPosition(kind="FLAT")
        if action in {"BUY", "SKIP"}
        else FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        )
    )
    return _evidence_for(
        monkeypatch,
        manifest,
        record,
        action=action,
        position=position,
        evaluated_at=20_020 + sequence,
        entry_observed_at=20_010 + sequence,
        exit_observed_at=20_015 + sequence,
        reduction_observed_at=(
            20_016 + sequence if action == "REDUCE" else None
        ),
    )


def _persist_decision(directory: Path, evidence, suffix: str) -> Path:
    path = directory / (
        f"shadow-{evidence.source_sequence:020d}-{suffix}.json"
    )
    write_fast_paper_shadow_decision_evidence(evidence, path)
    return path


def _persist_usd(manifest, evidence, directory: Path):
    usd = FastPaperShadowQuoteUsdEvidence(
        quote_mint=evidence.entry_quote.quote_mint,
        observed_at_unix_ms=evidence.evaluated_at_unix_ms - 1,
        quote_to_usd_rate=150.0,
        source_version="open-source-usd-v1",
        source_fingerprint_sha256="d" * 64,
    )
    record = build_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        usd,
    )
    write_fast_paper_shadow_quote_usd_source_record(record, directory)
    return usd


@pytest.mark.parametrize("action", ("HOLD", "REDUCE", "SELL"))
def test_open_publisher_builds_exact_source_from_authenticated_quote_usd(
    monkeypatch,
    tmp_path: Path,
    action: str,
) -> None:
    (
        manifest,
        bootstrap,
        decision_directory,
        quote_usd_directory,
    ) = _bootstrap(tmp_path)
    evidence = _evidence(
        monkeypatch,
        manifest,
        action=action,
    )
    _persist_decision(decision_directory, evidence, action.lower())
    usd = _persist_usd(
        manifest,
        evidence,
        quote_usd_directory,
    )
    captured: dict[str, object] = {}
    record = object()

    def produce(
        manifest_arg,
        binding,
        execution_policy,
        checkpoint,
        runtime_state,
        source,
        *,
        source_observed_at_unix_ms,
        risk_day_started_at_unix_ms,
    ):
        captured.update(
            manifest=manifest_arg,
            binding=binding,
            execution_policy=execution_policy,
            checkpoint=checkpoint,
            runtime_state=runtime_state,
            source=source,
            source_observed_at_unix_ms=source_observed_at_unix_ms,
            risk_day_started_at_unix_ms=risk_day_started_at_unix_ms,
        )
        return record

    monkeypatch.setattr(
        publisher,
        "produce_fast_paper_shadow_execution_input_source_record",
        produce,
    )
    monkeypatch.setattr(
        publisher,
        "write_fast_paper_shadow_execution_input_source_record",
        lambda supplied, directory: captured.update(
            written_record=supplied,
            written_directory=directory,
        ),
    )

    assert (
        run_fast_paper_shadow_open_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            quote_usd_source_directory=quote_usd_directory,
        )
        == 1
    )

    source = captured["source"]
    assert type(source) is FastPaperShadowExecutionInput
    assert source.decision_evidence == evidence
    assert source.entry_authority is None
    assert source.risk_context is None
    assert source.market_regime is None
    assert source.quote_usd_evidence == usd
    assert captured["manifest"] is manifest
    assert captured["binding"] == bootstrap.binding
    assert captured["execution_policy"] == bootstrap.execution_policy
    assert captured["checkpoint"] == bootstrap.checkpoint
    assert captured["runtime_state"] == bootstrap.runtime_state
    assert (
        captured["source_observed_at_unix_ms"]
        == evidence.evaluated_at_unix_ms
    )
    assert captured["risk_day_started_at_unix_ms"] is None
    assert captured["written_record"] is record
    assert captured["written_directory"] == bootstrap.source_directory


@pytest.mark.parametrize("action", ("BUY", "SKIP"))
def test_open_publisher_never_leapfrogs_oldest_non_open_source_action(
    monkeypatch,
    tmp_path: Path,
    action: str,
) -> None:
    (
        manifest,
        bootstrap,
        decision_directory,
        quote_usd_directory,
    ) = _bootstrap(tmp_path)
    oldest = _evidence(
        monkeypatch,
        manifest,
        action=action,
        sequence=1,
    )
    later = _evidence(
        monkeypatch,
        manifest,
        action="HOLD",
        sequence=2,
    )
    _persist_decision(decision_directory, oldest, action.lower())
    _persist_decision(decision_directory, later, "hold")
    _persist_usd(manifest, later, quote_usd_directory)

    monkeypatch.setattr(
        publisher,
        "read_fast_paper_shadow_quote_usd_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "publisher must not leapfrog oldest BUY/SKIP"
        ),
        raising=False,
    )
    monkeypatch.setattr(
        publisher,
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "publisher must not create source past oldest BUY/SKIP"
        ),
        raising=False,
    )

    assert (
        run_fast_paper_shadow_open_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            quote_usd_source_directory=quote_usd_directory,
        )
        == 0
    )


def test_open_publisher_missing_exact_quote_usd_is_backpressure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        bootstrap,
        decision_directory,
        quote_usd_directory,
    ) = _bootstrap(tmp_path)
    evidence = _evidence(
        monkeypatch,
        manifest,
        action="HOLD",
    )
    _persist_decision(decision_directory, evidence, "hold")

    monkeypatch.setattr(
        publisher,
        "read_fast_paper_shadow_quote_usd_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "missing exact quote/USD source must backpressure before read"
        ),
        raising=False,
    )
    monkeypatch.setattr(
        publisher,
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "missing quote/USD authority must not produce execution source"
        ),
        raising=False,
    )

    assert (
        run_fast_paper_shadow_open_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            quote_usd_source_directory=quote_usd_directory,
        )
        == 0
    )


def test_open_publisher_exact_write_collision_is_restart_safe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        bootstrap,
        decision_directory,
        quote_usd_directory,
    ) = _bootstrap(tmp_path)
    evidence = _evidence(
        monkeypatch,
        manifest,
        action="SELL",
    )
    _persist_decision(decision_directory, evidence, "sell")
    _persist_usd(manifest, evidence, quote_usd_directory)
    expected = object()

    monkeypatch.setattr(
        publisher,
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: expected,
        raising=False,
    )
    monkeypatch.setattr(
        publisher,
        "write_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileExistsError("collision")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        publisher,
        "read_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: expected,
        raising=False,
    )

    assert (
        run_fast_paper_shadow_open_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
            quote_usd_source_directory=quote_usd_directory,
        )
        == 0
    )


def test_open_publisher_source_has_bounded_authority() -> None:
    payload = Path(publisher.__file__).read_text(encoding="utf-8")

    for required in (
        "FastPaperShadowExecutionInput",
        "read_fast_paper_shadow_quote_usd_source_record",
        "produce_fast_paper_shadow_execution_input_source_record",
        "write_fast_paper_shadow_execution_input_source_record",
        "read_fast_paper_shadow_execution_input_source_record",
    ):
        assert required in payload

    for forbidden in (
        "FastCampaignPaperEntryAuthority(",
        "RiskContext(",
        "MarketRegime.",
        "ObserverMarketStore",
        "quote_asset_usd_evidence",
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "execute_fast_paper_shadow_decision(",
        "retry_fast_paper_shadow_pending_buy(",
        "commit_fast_paper_shadow_transition_atomically",
        "derive_paper_risk_accounting_facts",
        "RuntimeMode.LIVE",
        "shreks_brain.scoring",
        "score_candidate",
        "sign_transaction",
        "submit_transaction",
    ):
        assert forbidden not in payload
