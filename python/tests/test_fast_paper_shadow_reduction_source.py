from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_NAME,
    FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_VERSION,
    FastPaperShadowMarketPosition,
    FastPaperShadowReductionRead,
    FastPaperShadowReductionSourceRecord,
    build_fast_paper_shadow_reduction_source_record,
    build_fast_paper_shadow_runtime_state,
    read_fast_paper_shadow_reduction_source_record,
    save_fast_paper_shadow_ledger_checkpoint,
    save_fast_paper_shadow_runtime_state,
    write_fast_paper_shadow_reduction_source_record,
)

from test_fast_paper_accounting_reconciliation import MARKET_KEY
from test_fast_paper_shadow_runtime_state import _database_fixture


EXECUTION_POLICY_FINGERPRINT = "e" * 64


def _fixture(tmp_path: Path):
    manifest, binding, checkpoint = _database_fixture(
        tmp_path,
        open_position=True,
    )
    open_positions = tuple(
        position
        for position in checkpoint.state.ledger.positions
        if position.state.value == "OPEN"
    )
    assert len(open_positions) == 1
    position = open_positions[0]
    mapping = FastPaperShadowMarketPosition(
        market_key=MARKET_KEY,
        position_id=position.position_id,
        mint=position.mint,
        current_exposure_fraction=0.5,
        current_base_quantity_raw=10_000_000,
    )
    runtime_state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(mapping,),
        execution_policy_fingerprint_sha256=EXECUTION_POLICY_FINGERPRINT,
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        runtime_state,
        created_at_unix_ms=checkpoint.created_at_unix_ms,
    )
    return manifest, binding, checkpoint, runtime_state, mapping


def _read(amount: int = 5_000_000) -> FastPaperShadowReductionRead:
    return FastPaperShadowReductionRead(
        target_exposure_fraction=0.25,
        input_amount_raw=amount,
    )


def test_reduction_source_binds_exact_open_state_and_complete_target_set(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, runtime_state, mapping = _fixture(tmp_path)

    record = build_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        MARKET_KEY,
        (_read(),),
    )

    assert type(record) is FastPaperShadowReductionSourceRecord
    assert (
        record.schema_name
        == FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_NAME
    )
    assert (
        record.schema_version
        == FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_VERSION
    )
    assert (
        record.manifest_fingerprint_sha256
        == manifest.manifest_fingerprint_sha256
    )
    assert (
        record.binding_fingerprint_sha256
        == binding.binding_fingerprint_sha256
    )
    assert record.paper_checkpoint_sequence == checkpoint.sequence
    assert (
        record.paper_checkpoint_payload_sha256
        == checkpoint.payload_sha256
    )
    assert (
        record.shadow_runtime_state_fingerprint_sha256
        == runtime_state.state_fingerprint_sha256
    )
    assert record.market_key == MARKET_KEY
    assert record.position_id == mapping.position_id
    assert record.mint == mapping.mint
    assert record.current_exposure_fraction == 0.5
    assert record.reduction_reads == (_read(),)
    assert len(record.record_fingerprint_sha256) == 64


@pytest.mark.parametrize(
    "reads",
    (
        (),
        (
            FastPaperShadowReductionRead(
                target_exposure_fraction=0.10,
                input_amount_raw=1_000_000,
            ),
        ),
        (
            FastPaperShadowReductionRead(
                target_exposure_fraction=0.25,
                input_amount_raw=5_000_000,
            ),
            FastPaperShadowReductionRead(
                target_exposure_fraction=0.30,
                input_amount_raw=4_000_000,
            ),
        ),
    ),
)
def test_reduction_source_requires_exact_complete_policy_targets(
    tmp_path: Path,
    reads: tuple[FastPaperShadowReductionRead, ...],
) -> None:
    manifest, binding, checkpoint, runtime_state, _mapping = _fixture(tmp_path)

    with pytest.raises(ValueError, match="target|policy|complete|eligible"):
        build_fast_paper_shadow_reduction_source_record(
            manifest,
            binding,
            checkpoint,
            runtime_state,
            MARKET_KEY,
            reads,
        )


def test_reduction_source_round_trip_is_private_write_once_and_canonical(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, runtime_state, _mapping = _fixture(tmp_path)
    record = build_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        MARKET_KEY,
        (_read(),),
    )
    directory = tmp_path / "reduction-sources"
    directory.mkdir(mode=0o700)

    path = write_fast_paper_shadow_reduction_source_record(
        record,
        directory,
    )
    restored = read_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        MARKET_KEY,
        directory,
    )

    assert restored == record
    assert path.parent == directory
    assert path.suffix == ".json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = path.read_text(encoding="utf-8")
    assert payload.endswith("\n")
    assert not payload.endswith("\n\n")

    with pytest.raises(FileExistsError):
        write_fast_paper_shadow_reduction_source_record(
            record,
            directory,
        )


def test_reduction_source_fails_closed_after_durable_state_advances(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, runtime_state, mapping = _fixture(tmp_path)
    directory = tmp_path / "reduction-sources"
    directory.mkdir()
    record = build_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        MARKET_KEY,
        (_read(),),
    )
    write_fast_paper_shadow_reduction_source_record(record, directory)

    advanced = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        checkpoint.state,
        sequence=checkpoint.sequence + 1,
        created_at_unix_ms=checkpoint.created_at_unix_ms + 1,
    )
    advanced_runtime = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        advanced,
        market_positions=(mapping,),
        execution_policy_fingerprint_sha256=EXECUTION_POLICY_FINGERPRINT,
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        advanced_runtime,
        created_at_unix_ms=advanced.created_at_unix_ms,
    )

    with pytest.raises(ValueError, match="source|missing|state|record"):
        read_fast_paper_shadow_reduction_source_record(
            manifest,
            binding,
            advanced,
            advanced_runtime,
            MARKET_KEY,
            directory,
        )


def test_reduction_source_detects_payload_tamper_and_unknown_fields(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, runtime_state, _mapping = _fixture(tmp_path)
    directory = tmp_path / "reduction-sources"
    directory.mkdir()
    record = build_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        MARKET_KEY,
        (_read(),),
    )
    path = write_fast_paper_shadow_reduction_source_record(
        record,
        directory,
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["unexpected"] = True
    path.write_text(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown|field|fingerprint|canonical"):
        read_fast_paper_shadow_reduction_source_record(
            manifest,
            binding,
            checkpoint,
            runtime_state,
            MARKET_KEY,
            directory,
        )


def test_reduction_source_rejects_symlink_record(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint, runtime_state, _mapping = _fixture(tmp_path)
    directory = tmp_path / "reduction-sources"
    directory.mkdir()
    record = build_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        MARKET_KEY,
        (_read(),),
    )
    path = write_fast_paper_shadow_reduction_source_record(
        record,
        directory,
    )
    real = path.with_suffix(".real")
    path.rename(real)
    path.symlink_to(real.name)

    with pytest.raises(ValueError, match="symlink|regular"):
        read_fast_paper_shadow_reduction_source_record(
            manifest,
            binding,
            checkpoint,
            runtime_state,
            MARKET_KEY,
            directory,
        )


def test_reduction_source_never_derives_raw_token_amounts() -> None:
    import shreks_brain.fast_paper_runtime.shadow_reduction_source as source

    payload = Path(source.__file__).read_text(encoding="utf-8")
    forbidden = (
        "decimal_quantity_to_raw",
        "counterfactual_base_quantity",
        "round(",
        "execute_fast_paper_shadow_decision",
        "commit_fast_paper_shadow_transition_atomically",
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "RuntimeMode.LIVE",
    )
    for marker in forbidden:
        assert marker not in payload
