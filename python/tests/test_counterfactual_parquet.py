from __future__ import annotations

import builtins
import subprocess
import sys

import pytest

from shreks_brain.research.counterfactuals import (
    DelayedEntryAlternative,
    EntryCounterfactualContext,
    ExecutableTradeEvidence,
    ExecutionStatus,
    OpenPositionCounterfactualContext,
    TradeSide,
    label_entry_counterfactuals,
    label_open_position_counterfactuals,
)
from shreks_brain.research.counterfactual_parquet import (
    COUNTERFACTUAL_DATASET_COLUMNS,
    COUNTERFACTUAL_DATASET_SCHEMA_NAME,
    COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
    CounterfactualDatasetManifest,
    read_counterfactual_parquet,
    write_counterfactual_parquet,
)


def trade(
    evidence_id: str,
    *,
    observed_at_unix_ms: int,
    side: TradeSide,
    base_quantity: float,
    quote_amount: float,
    ordinal: int,
    source_suffix: str = "a",
) -> ExecutableTradeEvidence:
    return ExecutableTradeEvidence(
        evidence_id=evidence_id,
        source_event_signature=f"sig-{evidence_id}-{source_suffix}",
        source_event_ordinal=ordinal,
        observed_at_unix_ms=observed_at_unix_ms,
        side=side,
        base_quantity=base_quantity,
        status=ExecutionStatus.EXECUTABLE,
        quote_amount=quote_amount,
        evidence_version=f"proof-{source_suffix}-v1",
    )


def entry_set(*, source_suffix: str = "a"):
    return label_entry_counterfactuals(
        EntryCounterfactualContext(
            decision_id="decision-entry",
            mint="mint-1",
            quote_mint="quote-1",
            decision_observed_at_unix_ms=1_000,
            base_quantity=2.0,
            horizon_ms=1_000,
            horizon_complete=True,
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                base_quantity=2.0,
                quote_amount=0.11,
                ordinal=1,
                source_suffix=source_suffix,
            ),
            exit_at_horizon=trade(
                "entry-exit",
                observed_at_unix_ms=2_000,
                side=TradeSide.SELL,
                base_quantity=2.0,
                quote_amount=0.132,
                ordinal=2,
                source_suffix=source_suffix,
            ),
            delayed_entries=(
                DelayedEntryAlternative(
                    alternative_id="delay-250",
                    entry=trade(
                        "delayed-buy",
                        observed_at_unix_ms=1_250,
                        side=TradeSide.BUY,
                        base_quantity=2.0,
                        quote_amount=0.10,
                        ordinal=3,
                        source_suffix=source_suffix,
                    ),
                    exit=trade(
                        "delayed-exit",
                        observed_at_unix_ms=2_000,
                        side=TradeSide.SELL,
                        base_quantity=2.0,
                        quote_amount=0.132,
                        ordinal=4,
                        source_suffix=source_suffix,
                    ),
                ),
            ),
        )
    )


def position_set(*, source_suffix: str = "a"):
    return label_open_position_counterfactuals(
        OpenPositionCounterfactualContext(
            decision_id="decision-position",
            mint="mint-2",
            quote_mint="quote-1",
            action_observed_at_unix_ms=5_000,
            position_base_quantity=4.0,
            position_cost_basis_quote=0.20,
            horizon_ms=1_000,
            horizon_complete=True,
            sell_now=trade(
                "sell-now",
                observed_at_unix_ms=5_000,
                side=TradeSide.SELL,
                base_quantity=4.0,
                quote_amount=0.18,
                ordinal=5,
                source_suffix=source_suffix,
            ),
            hold_exit=trade(
                "hold-exit",
                observed_at_unix_ms=6_000,
                side=TradeSide.SELL,
                base_quantity=4.0,
                quote_amount=0.24,
                ordinal=6,
                source_suffix=source_suffix,
            ),
            reduce_quantity=1.0,
            reduce_now=trade(
                "reduce-now",
                observed_at_unix_ms=5_000,
                side=TradeSide.SELL,
                base_quantity=1.0,
                quote_amount=0.06,
                ordinal=7,
                source_suffix=source_suffix,
            ),
        )
    )


def test_importing_counterfactual_parquet_does_not_eagerly_import_pyarrow() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import shreks_brain.research.counterfactual_parquet; "
                "print(any(k == 'pyarrow' or k.startswith('pyarrow.') "
                "for k in sys.modules))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "False"


def test_writer_validates_before_creating_parent(tmp_path) -> None:
    destination = tmp_path / "missing" / "counterfactuals.parquet"
    with pytest.raises(ValueError, match="empty"):
        write_counterfactual_parquet((), destination)
    assert not destination.parent.exists()


def test_writer_requires_parquet_suffix(tmp_path) -> None:
    with pytest.raises(ValueError, match=r"\.parquet"):
        write_counterfactual_parquet((entry_set(),), tmp_path / "counterfactuals.bin")


def test_writer_reports_research_extra_when_pyarrow_is_unavailable(
    monkeypatch, tmp_path
) -> None:
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "pyarrow" or name.startswith("pyarrow."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(RuntimeError, match=r"shreks-brain\[research\]"):
        write_counterfactual_parquet(
            (entry_set(),), tmp_path / "counterfactuals.parquet"
        )


def test_parquet_v1_round_trip_preserves_exact_rows_metadata_nulls_and_provenance(
    tmp_path,
) -> None:
    path = tmp_path / "nested" / "counterfactuals.parquet"
    manifest = write_counterfactual_parquet(
        (position_set(), entry_set()),
        path,
    )

    assert isinstance(manifest, CounterfactualDatasetManifest)
    assert manifest.schema_name == COUNTERFACTUAL_DATASET_SCHEMA_NAME
    assert manifest.schema_version == COUNTERFACTUAL_DATASET_SCHEMA_VERSION
    assert manifest.label_version == 1
    assert manifest.row_count == 6
    assert manifest.min_action_observed_at_unix_ms == 1_000
    assert manifest.max_action_observed_at_unix_ms == 5_000
    assert len(manifest.dataset_fingerprint_sha256) == 64

    import pyarrow.parquet as pq

    table = pq.read_table(path)
    assert tuple(table.column_names) == COUNTERFACTUAL_DATASET_COLUMNS
    metadata = table.schema.metadata
    assert metadata is not None
    assert metadata[b"shreks_schema_name"] == b"shreks.counterfactual_action_labels"
    assert metadata[b"shreks_schema_version"] == b"1"
    assert metadata[b"shreks_counterfactual_label_version"] == b"1"
    assert metadata[b"shreks_row_count"] == b"6"
    assert (
        metadata[b"shreks_logical_sha256"]
        == manifest.dataset_fingerprint_sha256.encode()
    )

    rows, loaded_manifest = read_counterfactual_parquet(path)
    assert loaded_manifest == manifest
    assert tuple(row["action"] for row in rows) == (
        "BUY_NOW",
        "SKIP",
        "DELAY_ENTRY",
        "HOLD",
        "REDUCE_NOW",
        "SELL_NOW",
    )
    buy = rows[0]
    skip = rows[1]
    reduce_now = rows[4]
    assert buy["entry_source_event_signature"] == "sig-buy-now-a"
    assert buy["entry_source_event_ordinal"] == 1
    assert buy["entry_evidence_observed_at_unix_ms"] == 1_000
    assert buy["entry_evidence_version"] == "proof-a-v1"
    assert buy["exit_source_event_signature"] == "sig-entry-exit-a"
    assert buy["exit_source_event_ordinal"] == 2
    assert skip["entry_source_event_signature"] is None
    assert skip["exit_source_event_signature"] is None
    assert reduce_now["realized_cost_basis_quote"] == pytest.approx(0.05)
    assert reduce_now["remaining_base_quantity"] == pytest.approx(3.0)


def test_logical_fingerprint_and_rows_are_path_and_input_order_independent(
    tmp_path,
) -> None:
    first_path = tmp_path / "first.parquet"
    second_path = tmp_path / "other" / "second.parquet"
    first = write_counterfactual_parquet(
        (position_set(), entry_set()),
        first_path,
    )
    second = write_counterfactual_parquet(
        (entry_set(), position_set()),
        second_path,
    )
    first_rows, _ = read_counterfactual_parquet(first_path)
    second_rows, _ = read_counterfactual_parquet(second_path)
    assert first == second
    assert first_rows == second_rows


def test_logical_fingerprint_changes_when_execution_provenance_changes(tmp_path) -> None:
    first = write_counterfactual_parquet(
        (entry_set(source_suffix="a"),),
        tmp_path / "a.parquet",
    )
    second = write_counterfactual_parquet(
        (entry_set(source_suffix="b"),),
        tmp_path / "b.parquet",
    )
    assert first.dataset_fingerprint_sha256 != second.dataset_fingerprint_sha256


def test_duplicate_logical_action_rows_fail_closed(tmp_path) -> None:
    item = entry_set()
    destination = tmp_path / "duplicate.parquet"
    with pytest.raises(ValueError, match="duplicate"):
        write_counterfactual_parquet((item, item), destination)
    assert not destination.exists()


def test_reader_rejects_incompatible_or_missing_metadata(tmp_path) -> None:
    path = tmp_path / "valid.parquet"
    write_counterfactual_parquet((entry_set(),), path)

    import pyarrow.parquet as pq

    table = pq.read_table(path)
    metadata = dict(table.schema.metadata or {})
    metadata[b"shreks_schema_version"] = b"999"
    bad_version = tmp_path / "bad-version.parquet"
    pq.write_table(table.replace_schema_metadata(metadata), bad_version)
    with pytest.raises(ValueError, match="metadata"):
        read_counterfactual_parquet(bad_version)

    metadata = dict(table.schema.metadata or {})
    metadata.pop(b"shreks_logical_sha256", None)
    missing_digest = tmp_path / "missing-digest.parquet"
    pq.write_table(table.replace_schema_metadata(metadata), missing_digest)
    with pytest.raises(ValueError, match="metadata"):
        read_counterfactual_parquet(missing_digest)
