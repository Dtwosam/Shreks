from __future__ import annotations

from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow_skip_source_publisher as publisher
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowExecutionInput,
    FastPaperShadowServiceExecutionBootstrap,
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
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()
    bootstrap = FastPaperShadowServiceExecutionBootstrap(
        binding=binding,
        execution_policy=policy,
        checkpoint=checkpoint,
        runtime_state=runtime,
        source_directory=source_directory.resolve(),
    )
    decision_directory = tmp_path / "decision-evidence"
    decision_directory.mkdir()
    return manifest, bootstrap, decision_directory


def _evidence(
    monkeypatch,
    manifest,
    *,
    action: str,
    sequence: int = 1,
):
    base = _record()
    record = __import__(
        "dataclasses",
        fromlist=["replace"],
    ).replace(
        base,
        decision_signature=f"skip-publisher-{sequence}",
        decision_sequence=sequence,
        decision_observed_at_unix_ms=20_000 + sequence,
        decision_source_observed_at_unix_ms=20_000 + sequence,
        decision_occurred_at_unix_ms=20_000 + sequence,
        decision_slot=base.decision_slot + sequence,
        snapshot_as_of_unix_ms=20_000 + sequence,
        snapshot_last_sequence=sequence,
    )
    return _evidence_for(
        monkeypatch,
        manifest,
        record,
        action=action,
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020 + sequence,
        entry_observed_at=20_010 + sequence,
        exit_observed_at=20_015 + sequence,
    )


def _persist_decision(directory: Path, evidence, suffix: str) -> Path:
    path = directory / (
        f"shadow-{evidence.source_sequence:020d}-{suffix}.json"
    )
    write_fast_paper_shadow_decision_evidence(evidence, path)
    return path


def test_skip_publisher_builds_exact_authority_free_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    evidence = _evidence(
        monkeypatch,
        manifest,
        action="SKIP",
    )
    _persist_decision(decision_directory, evidence, "skip")
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
        publisher.run_fast_paper_shadow_skip_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
        )
        == 1
    )

    source = captured["source"]
    assert type(source) is FastPaperShadowExecutionInput
    assert source.decision_evidence == evidence
    assert source.entry_authority is None
    assert source.risk_context is None
    assert source.market_regime is None
    assert source.quote_usd_evidence is None
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


def test_skip_publisher_does_not_leapfrog_oldest_non_skip(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    buy = _evidence(
        monkeypatch,
        manifest,
        action="BUY",
        sequence=1,
    )
    skip = _evidence(
        monkeypatch,
        manifest,
        action="SKIP",
        sequence=2,
    )
    _persist_decision(decision_directory, buy, "buy")
    _persist_decision(decision_directory, skip, "skip")

    monkeypatch.setattr(
        publisher,
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "publisher must not leapfrog non-SKIP authority"
        ),
    )
    monkeypatch.setattr(
        publisher,
        "write_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "publisher must not write past oldest non-SKIP decision"
        ),
    )

    assert (
        publisher.run_fast_paper_shadow_skip_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
        )
        == 0
    )


def test_skip_publisher_leaves_existing_source_untouched(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    evidence = _evidence(
        monkeypatch,
        manifest,
        action="SKIP",
    )
    _persist_decision(decision_directory, evidence, "skip")
    source_path = bootstrap.source_directory / (
        f"{evidence.evidence_fingerprint_sha256}.json"
    )
    source_path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        publisher,
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "existing source must remain producer-free"
        ),
    )

    assert (
        publisher.run_fast_paper_shadow_skip_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
        )
        == 0
    )


def test_skip_publisher_exact_write_collision_is_restart_safe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    evidence = _evidence(
        monkeypatch,
        manifest,
        action="SKIP",
    )
    _persist_decision(decision_directory, evidence, "skip")
    expected = object()

    monkeypatch.setattr(
        publisher,
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: expected,
    )
    monkeypatch.setattr(
        publisher,
        "write_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileExistsError("collision")
        ),
    )
    monkeypatch.setattr(
        publisher,
        "read_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: expected,
    )

    assert (
        publisher.run_fast_paper_shadow_skip_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
        )
        == 0
    )


def test_skip_publisher_rejects_conflicting_write_collision(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, bootstrap, decision_directory = _bootstrap(tmp_path)
    evidence = _evidence(
        monkeypatch,
        manifest,
        action="SKIP",
    )
    _persist_decision(decision_directory, evidence, "skip")
    expected = object()

    monkeypatch.setattr(
        publisher,
        "produce_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: expected,
    )
    monkeypatch.setattr(
        publisher,
        "write_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileExistsError("collision")
        ),
    )
    monkeypatch.setattr(
        publisher,
        "read_fast_paper_shadow_execution_input_source_record",
        lambda *_args, **_kwargs: object(),
    )

    with pytest.raises(ValueError, match="collision|read-back|source"):
        publisher.run_fast_paper_shadow_skip_source_publisher_cycle(
            manifest,
            bootstrap,
            decision_evidence_directory=decision_directory,
        )


def test_skip_publisher_source_has_skip_only_publication_authority() -> None:
    payload = Path(publisher.__file__).read_text(encoding="utf-8")

    for required in (
        "FastPaperShadowExecutionInput",
        "produce_fast_paper_shadow_execution_input_source_record",
        "write_fast_paper_shadow_execution_input_source_record",
        "read_fast_paper_shadow_execution_input_source_record",
    ):
        assert required in payload

    for forbidden in (
        "FastCampaignPaperEntryAuthority(",
        "RiskContext(",
        "MarketRegime.",
        "FastPaperShadowQuoteUsdEvidence(",
        "execute_fast_paper_shadow_decision(",
        "retry_fast_paper_shadow_pending_buy(",
        "commit_fast_paper_shadow_transition_atomically",
        "derive_paper_risk_accounting_facts",
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "RuntimeMode.LIVE",
        "shreks_brain.scoring",
        "score_candidate",
    ):
        assert forbidden not in payload
