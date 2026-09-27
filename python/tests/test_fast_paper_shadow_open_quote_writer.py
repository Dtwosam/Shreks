from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_open_quote_writer as writer
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FastPaperRuntimeCursor,
    FastPaperShadowServiceExecutionBootstrap,
    build_fast_paper_runtime_state,
    execute_fast_paper_shadow_decision,
    read_fast_paper_shadow_reduction_source_record,
    run_fast_paper_shadow_open_quote_writer_cycle,
)
from shreks_brain.fast_paper_runtime.shadow_service import (
    FastPaperShadowServiceBootstrap,
)

from test_fast_paper_shadow_buy_authority_writer import _service_policy
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _persist,
    _record,
    _record_at,
    _runtime_fixture,
)
from test_fast_paper_shadow_raw_inventory import _matching_buy_source


def _open_bootstraps(monkeypatch, tmp_path: Path):
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    base = _record()
    buy = _evidence_for(
        monkeypatch,
        manifest,
        base,
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
        _matching_buy_source(base, buy),
    )
    checkpoint1, posture1 = _persist(
        manifest,
        binding,
        transition,
        sequence=1,
        created_at=20_020,
    )
    assert len(posture1.market_positions) == 1
    mapping = posture1.market_positions[0]
    assert mapping.current_base_quantity_raw == 2_000_000
    assert mapping.current_exposure_fraction == 0.5

    execution_sources = tmp_path / "execution-sources"
    execution_sources.mkdir()
    execution = FastPaperShadowServiceExecutionBootstrap(
        binding=binding,
        execution_policy=policy,
        checkpoint=checkpoint1,
        runtime_state=posture1,
        source_directory=execution_sources.resolve(),
    )
    cursor = FastPaperRuntimeCursor(
        decision_sequence=base.decision_sequence,
        decision_signature=base.decision_signature,
        decision_ordinal=base.decision_ordinal,
        decision_observed_at_unix_ms=base.decision_observed_at_unix_ms,
    )
    decision = FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=_service_policy(manifest),
        state=build_fast_paper_runtime_state(
            manifest,
            cursor=cursor,
        ),
    )
    next_record = _record_at(
        base,
        signature="open-quote-writer-next",
        sequence=base.decision_sequence + 1,
        at=20_300,
    )
    assert (
        f"{next_record.venue}:{next_record.mint}:{next_record.quote_mint}"
        == mapping.market_key
    )
    source_directory = tmp_path / "reduction-sources"
    source_directory.mkdir()
    return decision, execution, next_record, mapping, source_directory


def _wire_preview(
    monkeypatch,
    next_record,
    *,
    raw_inputs: tuple[int, ...] = (1_000_000, 2_000_000),
):
    captured: dict[str, object] = {}

    def preview(manifest, state, *, maximum_decisions):
        captured["preview"] = (manifest, state, maximum_decisions)
        return SimpleNamespace(records=(next_record,))

    monkeypatch.setattr(
        writer,
        "fetch_fast_paper_runtime_feature_batch",
        preview,
    )
    monkeypatch.setattr(
        writer,
        "_resolve_candidate_id",
        lambda *_args, **_kwargs: 7,
    )
    monkeypatch.setattr(
        writer,
        "_persisted_exit_input_amounts",
        lambda *_args, **_kwargs: raw_inputs,
    )

    def replay(
        _manifest,
        record,
        position,
        read_policy,
        *,
        evaluated_at_unix_ms,
        max_exposure_fraction,
        force_sell=False,
    ):
        captured.update(
            record=record,
            position=position,
            read_policy=read_policy,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
            max_exposure_fraction=max_exposure_fraction,
            force_sell=force_sell,
        )
        return SimpleNamespace(
            exit_quote=SimpleNamespace(
                input_amount_raw=read_policy.exit_input_amount_raw
            ),
            reduction_quotes=tuple(
                SimpleNamespace(
                    target_exposure_fraction=value.target_exposure_fraction,
                    quote=SimpleNamespace(
                        input_amount_raw=value.input_amount_raw
                    ),
                )
                for value in read_policy.reduction_reads
            ),
        )

    monkeypatch.setattr(
        writer,
        "resolve_fast_paper_shadow_cycle_input",
        replay,
    )
    return captured


def test_open_quote_writer_previews_one_row_and_publishes_exact_persisted_raw_authority(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision, execution, next_record, mapping, directory = (
        _open_bootstraps(monkeypatch, tmp_path)
    )
    captured = _wire_preview(monkeypatch, next_record)

    written = run_fast_paper_shadow_open_quote_writer_cycle(
        decision,
        execution,
        reduction_source_directory=directory,
        clock_unix_ms=lambda: 20_320,
    )

    assert written == 1
    preview_manifest, preview_state, maximum = captured["preview"]
    assert preview_manifest is decision.manifest
    assert preview_state is decision.state
    assert maximum == 1
    assert captured["record"] is next_record
    assert captured["position"].kind == "OPEN"
    assert captured["position"].current_exposure_fraction == 0.5
    policy = captured["read_policy"]
    assert policy.candidate_id == 7
    assert policy.exit_input_amount_raw == mapping.current_base_quantity_raw
    assert len(policy.reduction_reads) == 1
    assert policy.reduction_reads[0].target_exposure_fraction == 0.25
    assert policy.reduction_reads[0].input_amount_raw == 1_000_000
    assert captured["evaluated_at_unix_ms"] == 20_320

    restored = read_fast_paper_shadow_reduction_source_record(
        decision.manifest,
        execution.binding,
        execution.checkpoint,
        execution.runtime_state,
        mapping.market_key,
        directory,
    )
    assert restored.current_base_quantity_raw == 2_000_000
    assert restored.exit_input_amount_raw == 2_000_000
    assert restored.reduction_reads == policy.reduction_reads

    monkeypatch.setattr(
        writer,
        "_persisted_exit_input_amounts",
        lambda *_args, **_kwargs: pytest.fail(
            "restart must authenticate existing source before rediscovery"
        ),
    )
    assert (
        run_fast_paper_shadow_open_quote_writer_cycle(
            decision,
            execution,
            reduction_source_directory=directory,
            clock_unix_ms=lambda: 20_320,
        )
        == 0
    )


def test_open_quote_writer_waits_when_persisted_target_request_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision, execution, next_record, _mapping, directory = (
        _open_bootstraps(monkeypatch, tmp_path)
    )
    _wire_preview(
        monkeypatch,
        next_record,
        raw_inputs=(2_000_000,),
    )
    monkeypatch.setattr(
        writer,
        "resolve_fast_paper_shadow_cycle_input",
        lambda *_args, **_kwargs: pytest.fail(
            "missing target authority must wait before quote replay"
        ),
    )

    assert (
        run_fast_paper_shadow_open_quote_writer_cycle(
            decision,
            execution,
            reduction_source_directory=directory,
            clock_unix_ms=lambda: 20_320,
        )
        == 0
    )
    assert list(directory.iterdir()) == []


def test_open_quote_writer_fails_closed_on_ambiguous_persisted_target_authority(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision, execution, next_record, _mapping, directory = (
        _open_bootstraps(monkeypatch, tmp_path)
    )
    _wire_preview(
        monkeypatch,
        next_record,
        raw_inputs=(900_000, 1_000_000, 2_000_000),
    )
    monkeypatch.setattr(
        writer,
        "_matches_reduction_target",
        lambda *, input_amount_raw, **_kwargs: (
            input_amount_raw in {900_000, 1_000_000}
        ),
    )

    with pytest.raises(ValueError, match="ambiguous|target|raw|persisted"):
        run_fast_paper_shadow_open_quote_writer_cycle(
            decision,
            execution,
            reduction_source_directory=directory,
            clock_unix_ms=lambda: 20_320,
        )


def test_open_quote_writer_matches_target_by_testing_observed_raw_candidate() -> None:
    assert writer._matches_reduction_target(
        input_amount_raw=1_000_000,
        current_base_quantity_raw=2_000_000,
        current_exposure_fraction=0.5,
        target_exposure_fraction=0.25,
    )
    assert not writer._matches_reduction_target(
        input_amount_raw=1_000_001,
        current_base_quantity_raw=2_000_000,
        current_exposure_fraction=0.5,
        target_exposure_fraction=0.25,
    )


def test_open_quote_writer_reads_only_matching_fresh_exit_raw_inputs(
    tmp_path: Path,
) -> None:
    database = tmp_path / "observer.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE paper_quote_snapshots (
                id INTEGER PRIMARY KEY,
                candidate_id INTEGER NOT NULL,
                purpose TEXT NOT NULL,
                provider TEXT NOT NULL,
                probe_policy_version TEXT NOT NULL,
                input_mint TEXT NOT NULL,
                output_mint TEXT NOT NULL,
                taker TEXT NOT NULL,
                input_amount TEXT NOT NULL,
                slippage_bps INTEGER NOT NULL,
                quoted_at_unix_ms INTEGER NOT NULL
            );
            """
        )
        rows = (
            (1, 7, "exit", "jupiter", "probe-v2", "mint", "quote", "Taker111", "1000000", 75, 20_310),
            (2, 7, "exit", "jupiter", "probe-v2", "mint", "quote", "Taker111", "2000000", 75, 20_315),
            (3, 7, "exit", "jupiter", "probe-v2", "mint", "quote", "Taker111", "500000", 75, 20_000),
            (4, 7, "entry", "jupiter", "probe-v2", "quote", "mint", "Taker111", "1000000000", 75, 20_315),
            (5, 7, "exit", "other", "probe-v2", "mint", "quote", "Taker111", "750000", 75, 20_315),
        )
        connection.executemany(
            """
            INSERT INTO paper_quote_snapshots
            (id, candidate_id, purpose, provider, probe_policy_version,
             input_mint, output_mint, taker, input_amount, slippage_bps,
             quoted_at_unix_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()

    before = database.read_bytes()
    values = writer._persisted_exit_input_amounts(
        database,
        candidate_id=7,
        mint="mint",
        quote_mint="quote",
        provider="jupiter",
        probe_policy_version="probe-v2",
        taker="Taker111",
        slippage_bps=75,
        minimum_observed_at_unix_ms=20_300,
        evaluated_at_unix_ms=20_320,
    )
    assert database.read_bytes() == before
    assert values == (1_000_000, 2_000_000)


def test_open_quote_writer_source_has_no_float_to_raw_execution_network_or_live_authority() -> None:
    payload = Path(writer.__file__).read_text(encoding="utf-8")

    for required in (
        "fetch_fast_paper_runtime_feature_batch",
        "_resolve_candidate_id",
        "resolve_fast_paper_shadow_cycle_input",
        "build_fast_paper_shadow_reduction_source_record",
        "write_fast_paper_shadow_reduction_source_record",
        "read_fast_paper_shadow_reduction_source_record",
        "mode=ro",
        "PRAGMA query_only = ON",
    ):
        assert required in payload

    for forbidden in (
        "decimal_quantity_to_raw",
        "float_to_raw",
        "round(",
        "int(mapping.current_exposure_fraction",
        "int(position.quantity",
        "position.quantity *",
        "execute_fast_paper_shadow_decision(",
        "commit_fast_paper_shadow_transition_atomically",
        "produce_fast_paper_shadow_execution_input_source_record",
        "requests.",
        "httpx",
        "aiohttp",
        "shreks_brain.scoring",
        "score_candidate",
        "shreks_brain.decision",
        "decide_entry",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in payload
