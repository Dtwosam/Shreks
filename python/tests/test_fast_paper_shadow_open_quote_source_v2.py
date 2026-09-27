from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_VERSION,
    build_fast_paper_shadow_reduction_source_record,
    read_fast_paper_shadow_reduction_source_record,
    write_fast_paper_shadow_reduction_source_record,
)

from test_fast_paper_shadow_reduction_source import _fixture, _read


def test_open_quote_source_v2_binds_exact_raw_inventory_and_full_exit(
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        checkpoint,
        runtime_state,
        mapping,
    ) = _fixture(tmp_path)

    record = build_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        mapping.market_key,
        (_read(),),
    )

    assert FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_VERSION == 2
    assert record.schema_version == 2
    assert (
        record.current_base_quantity_raw
        == mapping.current_base_quantity_raw
    )
    assert (
        record.exit_input_amount_raw
        == mapping.current_base_quantity_raw
    )


def test_open_quote_source_v2_round_trips_canonical_raw_fields_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        checkpoint,
        runtime_state,
        mapping,
    ) = _fixture(tmp_path)
    directory = tmp_path / "open-quote-sources"
    directory.mkdir()

    record = build_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        mapping.market_key,
        (_read(),),
    )
    path = write_fast_paper_shadow_reduction_source_record(
        record,
        directory,
    )
    restored = read_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        mapping.market_key,
        directory,
    )

    assert restored == record
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["current_base_quantity_raw"] == str(
        mapping.current_base_quantity_raw
    )
    assert document["exit_input_amount_raw"] == str(
        mapping.current_base_quantity_raw
    )

    document["exit_input_amount_raw"] = str(
        mapping.current_base_quantity_raw - 1
    )
    document["record_fingerprint_sha256"] = record.record_fingerprint_sha256
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="raw|inventory|exit|fingerprint|record",
    ):
        read_fast_paper_shadow_reduction_source_record(
            manifest,
            binding,
            checkpoint,
            runtime_state,
            mapping.market_key,
            directory,
        )


def test_open_quote_source_v2_does_not_derive_raw_amounts_from_floats() -> None:
    import shreks_brain.fast_paper_runtime.shadow_reduction_source as source

    payload = Path(source.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "decimal_quantity_to_raw",
        "float_to_raw",
        "round(mapping.current_exposure_fraction",
        "int(mapping.current_exposure_fraction",
        "position.quantity *",
        "round(position.quantity",
        "int(position.quantity",
        "requests.",
        "httpx",
        "aiohttp",
        "execute_fast_paper_shadow_decision(",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in payload
