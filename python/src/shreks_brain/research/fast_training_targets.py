from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from urllib.parse import quote


FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME = "shreks.fast_future_path_training_labels"
FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION = 1

_COLUMNS = (
    "decision_signature",
    "decision_ordinal",
    "decision_sequence",
    "decision_mint",
    "decision_quote_mint",
    "decision_venue",
    "decision_observed_at_unix_ms",
    "decision_entry_price_quote",
    "decision_entry_total_quote",
    "coverage_complete_through_unix_ms",
    "coverage_contiguous",
    "horizon_ms",
    "label_version",
    "completeness",
    "event_count",
    "no_trade_events",
    "endpoint_signature",
    "endpoint_ordinal",
    "endpoint_observed_at_unix_ms",
    "endpoint_price_quote",
    "endpoint_return_bps",
    "mfe_bps",
    "mae_bps",
    "time_to_peak_ms",
    "time_to_trough_ms",
    "reversal_occurred",
    "first_reversal_after_ms",
    "min_exit_capacity_base",
    "endpoint_exit_capacity_base",
    "route_unavailability_observed",
    "best_cost_adjusted_return_bps",
    "endpoint_cost_adjusted_return_bps",
)


@dataclass(frozen=True, slots=True)
class FuturePathTrainingLabel:
    decision_signature: str
    decision_ordinal: int
    decision_sequence: int
    decision_mint: str
    decision_quote_mint: str
    decision_venue: str
    decision_observed_at_unix_ms: int
    decision_entry_price_quote: float
    decision_entry_total_quote: float | None
    coverage_complete_through_unix_ms: int
    coverage_contiguous: bool
    horizon_ms: int
    label_version: int
    completeness: str
    event_count: int
    no_trade_events: bool
    endpoint_signature: str | None
    endpoint_ordinal: int | None
    endpoint_observed_at_unix_ms: int | None
    endpoint_price_quote: float | None
    endpoint_return_bps: float | None
    mfe_bps: float | None
    mae_bps: float | None
    time_to_peak_ms: int | None
    time_to_trough_ms: int | None
    reversal_occurred: bool | None
    first_reversal_after_ms: int | None
    min_exit_capacity_base: float | None
    endpoint_exit_capacity_base: float | None
    route_unavailability_observed: bool | None
    best_cost_adjusted_return_bps: float | None
    endpoint_cost_adjusted_return_bps: float | None

    @property
    def decision_identity(self) -> tuple[object, ...]:
        return (
            self.decision_signature,
            self.decision_ordinal,
            self.decision_sequence,
            self.decision_mint,
            self.decision_quote_mint,
            self.decision_venue,
            self.decision_observed_at_unix_ms,
        )

    @property
    def decision_horizon_identity(self) -> tuple[object, ...]:
        return (*self.decision_identity, self.horizon_ms, self.label_version)


@dataclass(frozen=True, slots=True)
class FuturePathTrainingLabelDataset:
    labels: tuple[FuturePathTrainingLabel, ...]
    logical_fingerprint_sha256: str
    label_version: int


def load_future_path_training_labels_from_sqlite(
    path: str | Path,
    *,
    future_path_label_version: int,
) -> FuturePathTrainingLabelDataset:
    _require_positive_int("future_path_label_version", future_path_label_version)
    source = Path(path)
    if not source.is_file():
        raise ValueError("future-path training SQLite source must be an existing file")

    uri = f"file:{quote(str(source.resolve()), safe='/')}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise ValueError("could not open future-path training SQLite source read-only") from exc
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT
                   l.decision_signature, l.decision_ordinal, l.decision_sequence,
                   l.decision_mint, l.decision_quote_mint, l.decision_venue,
                   l.decision_observed_at_unix_ms, l.decision_entry_price_quote,
                   l.decision_entry_total_quote,
                   l.coverage_complete_through_unix_ms, l.coverage_contiguous,
                   l.horizon_ms, l.label_version, l.completeness, l.event_count,
                   l.no_trade_events, l.endpoint_signature, l.endpoint_ordinal,
                   l.endpoint_observed_at_unix_ms, l.endpoint_price_quote,
                   l.endpoint_return_bps, l.mfe_bps, l.mae_bps,
                   l.time_to_peak_ms, l.time_to_trough_ms, l.reversal_occurred,
                   l.first_reversal_after_ms, l.min_exit_capacity_base,
                   l.endpoint_exit_capacity_base, l.route_unavailability_observed,
                   l.best_cost_adjusted_return_bps,
                   l.endpoint_cost_adjusted_return_bps,
                   d.sequence AS canonical_decision_sequence,
                   d.mint AS canonical_decision_mint,
                   d.quote_mint AS canonical_decision_quote_mint,
                   d.venue AS canonical_decision_venue,
                   d.observed_at_unix_ms AS canonical_decision_observed_at_unix_ms,
                   d.price_quote AS canonical_decision_price_quote,
                   e.sequence AS canonical_endpoint_sequence,
                   e.mint AS canonical_endpoint_mint,
                   e.quote_mint AS canonical_endpoint_quote_mint,
                   e.venue AS canonical_endpoint_venue,
                   e.observed_at_unix_ms AS canonical_endpoint_observed_at_unix_ms,
                   e.price_quote AS canonical_endpoint_price_quote
               FROM fast_future_path_labels AS l
               LEFT JOIN fast_events AS d
                 ON d.signature = l.decision_signature
                AND d.ordinal = l.decision_ordinal
               LEFT JOIN fast_events AS e
                 ON e.signature = l.endpoint_signature
                AND e.ordinal = l.endpoint_ordinal
               WHERE l.label_version = ?
               ORDER BY l.decision_sequence ASC, l.horizon_ms ASC,
                        l.decision_signature ASC, l.decision_ordinal ASC""",
            (future_path_label_version,),
        ).fetchall()
        if not rows:
            raise ValueError("future-path training label query returned no rows for label version")

        labels: list[FuturePathTrainingLabel] = []
        seen: set[tuple[object, ...]] = set()
        previous_sort: tuple[object, ...] | None = None
        for row in rows:
            _validate_canonical_sources(connection, row)
            label = _label_from_row(row, future_path_label_version)
            key = (
                label.decision_signature,
                label.decision_ordinal,
                label.horizon_ms,
                label.label_version,
            )
            if key in seen:
                raise ValueError("future-path training labels contain a duplicate decision/horizon")
            seen.add(key)
            sort_key = (
                label.decision_sequence,
                label.horizon_ms,
                label.decision_signature,
                label.decision_ordinal,
            )
            if previous_sort is not None and sort_key < previous_sort:
                raise ValueError("future-path training labels are not in canonical order")
            previous_sort = sort_key
            labels.append(label)
    except sqlite3.Error as exc:
        raise ValueError("future-path training SQLite source is incompatible") from exc
    finally:
        connection.close()

    canonical = tuple(labels)
    return FuturePathTrainingLabelDataset(
        labels=canonical,
        logical_fingerprint_sha256=future_path_logical_fingerprint_sha256(canonical),
        label_version=future_path_label_version,
    )


def future_path_logical_fingerprint_sha256(
    labels: tuple[FuturePathTrainingLabel, ...],
) -> str:
    if not labels:
        raise ValueError("future-path training label dataset cannot be empty")
    payload = [_canonicalize(asdict(label)) for label in labels]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_future_path_training_parquet(
    dataset: FuturePathTrainingLabelDataset,
    path: str | Path,
) -> None:
    if type(dataset) is not FuturePathTrainingLabelDataset:
        raise ValueError("dataset must be an exact FuturePathTrainingLabelDataset")
    actual = future_path_logical_fingerprint_sha256(dataset.labels)
    if actual != dataset.logical_fingerprint_sha256:
        raise ValueError("future-path training dataset fingerprint is invalid")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires the shreks-brain[research] extra"
        ) from exc
    metadata = {
        b"shreks_schema_name": FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME.encode(),
        b"shreks_schema_version": str(FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION).encode(),
        b"shreks_future_path_label_version": str(dataset.label_version).encode(),
        b"shreks_row_count": str(len(dataset.labels)).encode(),
        b"shreks_logical_sha256": dataset.logical_fingerprint_sha256.encode(),
    }
    schema = _arrow_schema(pa, metadata)
    table = pa.Table.from_pylist([asdict(label) for label in dataset.labels], schema=schema)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        destination,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
    )


def read_future_path_training_parquet(path: str | Path) -> FuturePathTrainingLabelDataset:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet import requires the shreks-brain[research] extra"
        ) from exc
    table = pq.read_table(Path(path))
    metadata = table.schema.metadata or {}
    if metadata.get(b"shreks_schema_name") != FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME.encode():
        raise ValueError("future-path training Parquet schema name is incompatible")
    if metadata.get(b"shreks_schema_version") != str(FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION).encode():
        raise ValueError("future-path training Parquet schema version is incompatible")
    expected = _arrow_schema(pa, metadata)
    if table.schema != expected:
        raise ValueError("future-path training Parquet physical schema is incompatible")
    try:
        version = int(metadata[b"shreks_future_path_label_version"].decode())
        row_count = int(metadata[b"shreks_row_count"].decode())
        logical = metadata[b"shreks_logical_sha256"].decode()
    except (KeyError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("future-path training Parquet metadata is incomplete") from exc
    if row_count != table.num_rows or row_count <= 0:
        raise ValueError("future-path training Parquet row count is incompatible")
    _require_sha256("future-path logical fingerprint", logical)
    labels = tuple(_label_from_parquet_mapping(row, version) for row in table.to_pylist())
    actual = future_path_logical_fingerprint_sha256(labels)
    if actual != logical:
        raise ValueError("future-path training Parquet logical fingerprint does not match")
    return FuturePathTrainingLabelDataset(labels, actual, version)


def _validate_canonical_sources(connection: sqlite3.Connection, row: sqlite3.Row) -> None:
    if row["canonical_decision_sequence"] is None:
        raise ValueError("FL4 canonical decision FastEvent is missing")
    if (
        row["decision_sequence"] != row["canonical_decision_sequence"]
        or row["decision_mint"] != row["canonical_decision_mint"]
        or row["decision_quote_mint"] != row["canonical_decision_quote_mint"]
        or row["decision_venue"] != row["canonical_decision_venue"]
        or row["decision_observed_at_unix_ms"]
        != row["canonical_decision_observed_at_unix_ms"]
        or row["decision_entry_price_quote"] != row["canonical_decision_price_quote"]
    ):
        raise ValueError("FL4 row does not match its canonical decision FastEvent")
    _reject_conflict(
        connection,
        signature=row["decision_signature"],
        ordinal=row["decision_ordinal"],
        venue=row["decision_venue"],
        role="decision",
    )

    endpoint_signature = row["endpoint_signature"]
    endpoint_ordinal = row["endpoint_ordinal"]
    if (endpoint_signature is None) != (endpoint_ordinal is None):
        raise ValueError("FL4 endpoint identity is partial")
    if endpoint_signature is None:
        if row["canonical_endpoint_sequence"] is not None:
            raise ValueError("null FL4 endpoint unexpectedly resolved to a FastEvent")
        return
    if row["canonical_endpoint_sequence"] is None:
        raise ValueError("FL4 canonical endpoint FastEvent is missing")
    if (
        row["canonical_endpoint_sequence"] <= row["decision_sequence"]
        or row["canonical_endpoint_mint"] != row["decision_mint"]
        or row["canonical_endpoint_quote_mint"] != row["decision_quote_mint"]
        or row["canonical_endpoint_venue"] != row["decision_venue"]
        or row["canonical_endpoint_observed_at_unix_ms"]
        != row["endpoint_observed_at_unix_ms"]
        or row["canonical_endpoint_price_quote"] != row["endpoint_price_quote"]
    ):
        raise ValueError("FL4 row does not match its canonical endpoint FastEvent")
    _reject_conflict(
        connection,
        signature=endpoint_signature,
        ordinal=endpoint_ordinal,
        venue=row["decision_venue"],
        role="endpoint",
    )


def _label_from_row(row: sqlite3.Row, requested_version: int) -> FuturePathTrainingLabel:
    mapping = {name: row[name] for name in _COLUMNS}
    return _label_from_mapping(mapping, requested_version)


def _label_from_parquet_mapping(
    mapping: dict[str, object], requested_version: int
) -> FuturePathTrainingLabel:
    if tuple(mapping) != _COLUMNS:
        raise ValueError("future-path training Parquet columns are incompatible")
    return _label_from_mapping(mapping, requested_version)


def _label_from_mapping(
    mapping: dict[str, object], requested_version: int
) -> FuturePathTrainingLabel:
    if set(mapping) != set(_COLUMNS):
        raise ValueError("future-path training label columns are incompatible")
    label_version = _positive_int("label_version", mapping["label_version"])
    if label_version != requested_version:
        raise ValueError("future-path label version is incompatible")
    decision_time = _non_negative_int(
        "decision_observed_at_unix_ms", mapping["decision_observed_at_unix_ms"]
    )
    horizon = _positive_int("horizon_ms", mapping["horizon_ms"])
    coverage = _non_negative_int(
        "coverage_complete_through_unix_ms",
        mapping["coverage_complete_through_unix_ms"],
    )
    contiguous = _bool_int("coverage_contiguous", mapping["coverage_contiguous"])
    completeness = _enum_text(
        "completeness", mapping["completeness"], {"complete", "incomplete"}
    )
    should_be_complete = contiguous and coverage >= decision_time + horizon
    if should_be_complete != (completeness == "complete"):
        raise ValueError("FL4 completeness contradicts its coverage watermark")

    event_count = _non_negative_int("event_count", mapping["event_count"])
    no_trade = _bool_int("no_trade_events", mapping["no_trade_events"])
    endpoint_signature = _optional_text("endpoint_signature", mapping["endpoint_signature"])
    endpoint_ordinal = _optional_non_negative_int("endpoint_ordinal", mapping["endpoint_ordinal"])
    endpoint_time = _optional_non_negative_int(
        "endpoint_observed_at_unix_ms", mapping["endpoint_observed_at_unix_ms"]
    )
    endpoint_price = _optional_positive_float("endpoint_price_quote", mapping["endpoint_price_quote"])
    endpoint_return = _optional_finite_float("endpoint_return_bps", mapping["endpoint_return_bps"])
    mfe = _optional_finite_float("mfe_bps", mapping["mfe_bps"])
    mae = _optional_finite_float("mae_bps", mapping["mae_bps"])
    peak = _optional_non_negative_int("time_to_peak_ms", mapping["time_to_peak_ms"])
    trough = _optional_non_negative_int("time_to_trough_ms", mapping["time_to_trough_ms"])
    reversal = _optional_bool_int("reversal_occurred", mapping["reversal_occurred"])
    first_reversal = _optional_non_negative_int(
        "first_reversal_after_ms", mapping["first_reversal_after_ms"]
    )
    min_capacity = _optional_non_negative_float(
        "min_exit_capacity_base", mapping["min_exit_capacity_base"]
    )
    endpoint_capacity = _optional_non_negative_float(
        "endpoint_exit_capacity_base", mapping["endpoint_exit_capacity_base"]
    )
    route_unavailable = _optional_bool_int(
        "route_unavailability_observed", mapping["route_unavailability_observed"]
    )
    best_cost = _optional_finite_float(
        "best_cost_adjusted_return_bps", mapping["best_cost_adjusted_return_bps"]
    )
    endpoint_cost = _optional_finite_float(
        "endpoint_cost_adjusted_return_bps",
        mapping["endpoint_cost_adjusted_return_bps"],
    )

    path_values = (
        endpoint_signature,
        endpoint_ordinal,
        endpoint_time,
        endpoint_price,
        endpoint_return,
        mfe,
        mae,
        peak,
        trough,
        reversal,
        first_reversal,
        min_capacity,
        endpoint_capacity,
        route_unavailable,
        best_cost,
        endpoint_cost,
    )
    if completeness == "incomplete":
        if event_count != 0 or no_trade or any(value is not None for value in path_values):
            raise ValueError("incomplete FL4 label must not contain future path metrics")
    elif event_count == 0:
        if not no_trade or any(value is not None for value in path_values):
            raise ValueError("complete no-trade FL4 label must preserve null path metrics")
    else:
        required = (
            endpoint_signature,
            endpoint_ordinal,
            endpoint_time,
            endpoint_price,
            endpoint_return,
            mfe,
            mae,
            peak,
            trough,
            reversal,
        )
        if no_trade or any(value is None for value in required):
            raise ValueError("complete FL4 label with events is missing required path metrics")
        assert endpoint_time is not None
        assert peak is not None and trough is not None
        if endpoint_time <= decision_time or endpoint_time > decision_time + horizon:
            raise ValueError("FL4 endpoint time is outside its decision horizon")
        if peak > horizon or trough > horizon or (
            first_reversal is not None and first_reversal > horizon
        ):
            raise ValueError("FL4 path timing exceeds its horizon")
        if (reversal is True and first_reversal is None) or (
            reversal is False and first_reversal is not None
        ):
            raise ValueError("FL4 reversal timing contradicts reversal flag")

    return FuturePathTrainingLabel(
        decision_signature=_text("decision_signature", mapping["decision_signature"]),
        decision_ordinal=_non_negative_int("decision_ordinal", mapping["decision_ordinal"]),
        decision_sequence=_positive_int("decision_sequence", mapping["decision_sequence"]),
        decision_mint=_text("decision_mint", mapping["decision_mint"]),
        decision_quote_mint=_text("decision_quote_mint", mapping["decision_quote_mint"]),
        decision_venue=_text("decision_venue", mapping["decision_venue"]),
        decision_observed_at_unix_ms=decision_time,
        decision_entry_price_quote=_positive_float(
            "decision_entry_price_quote", mapping["decision_entry_price_quote"]
        ),
        decision_entry_total_quote=_optional_positive_float(
            "decision_entry_total_quote", mapping["decision_entry_total_quote"]
        ),
        coverage_complete_through_unix_ms=coverage,
        coverage_contiguous=contiguous,
        horizon_ms=horizon,
        label_version=label_version,
        completeness=completeness,
        event_count=event_count,
        no_trade_events=no_trade,
        endpoint_signature=endpoint_signature,
        endpoint_ordinal=endpoint_ordinal,
        endpoint_observed_at_unix_ms=endpoint_time,
        endpoint_price_quote=endpoint_price,
        endpoint_return_bps=endpoint_return,
        mfe_bps=mfe,
        mae_bps=mae,
        time_to_peak_ms=peak,
        time_to_trough_ms=trough,
        reversal_occurred=reversal,
        first_reversal_after_ms=first_reversal,
        min_exit_capacity_base=min_capacity,
        endpoint_exit_capacity_base=endpoint_capacity,
        route_unavailability_observed=route_unavailable,
        best_cost_adjusted_return_bps=best_cost,
        endpoint_cost_adjusted_return_bps=endpoint_cost,
    )


def _reject_conflict(
    connection: sqlite3.Connection,
    *,
    signature: str,
    ordinal: int,
    venue: str,
    role: str,
) -> None:
    if venue == "pump_fun_bonding_curve":
        table = "pump_trade_evidence_conflicts"
    elif venue == "pump_swap":
        table = "pump_swap_trade_evidence_conflicts"
    else:
        raise ValueError(f"unsupported canonical venue for FL8 conflict quarantine: {venue}")
    try:
        found = connection.execute(
            f"SELECT 1 FROM {table} WHERE signature = ? AND ordinal = ? LIMIT 1",
            (signature, ordinal),
        ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("FL8 conflict-quarantine table is missing or incompatible") from exc
    if found is not None:
        raise ValueError(f"canonical {role} source is conflict-quarantined")


def _arrow_schema(pa, metadata: dict[bytes, bytes] | None):
    string_columns = {
        "decision_signature",
        "decision_mint",
        "decision_quote_mint",
        "decision_venue",
        "completeness",
        "endpoint_signature",
    }
    bool_columns = {
        "coverage_contiguous",
        "no_trade_events",
        "reversal_occurred",
        "route_unavailability_observed",
    }
    int_columns = {
        "decision_ordinal",
        "decision_sequence",
        "decision_observed_at_unix_ms",
        "coverage_complete_through_unix_ms",
        "horizon_ms",
        "label_version",
        "event_count",
        "endpoint_ordinal",
        "endpoint_observed_at_unix_ms",
        "time_to_peak_ms",
        "time_to_trough_ms",
        "first_reversal_after_ms",
    }
    fields = []
    for name in _COLUMNS:
        if name in string_columns:
            value_type = pa.string()
        elif name in bool_columns:
            value_type = pa.bool_()
        elif name in int_columns:
            value_type = pa.int64()
        else:
            value_type = pa.float64()
        fields.append(pa.field(name, value_type, nullable=True))
    return pa.schema(fields, metadata=metadata)


def _canonicalize(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("future-path logical fingerprint rejects non-finite floats")
        return {"__float_hex__": value.hex()}
    if isinstance(value, dict):
        return {key: _canonicalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_text(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _text(name, value)


def _enum_text(name: str, value: object, allowed: set[str]) -> str:
    result = _text(name, value)
    if result not in allowed:
        raise ValueError(f"{name} is incompatible")
    return result


def _positive_int(name: str, value: object) -> int:
    result = _non_negative_int(name, value)
    if result == 0:
        raise ValueError(f"{name} must be positive")
    return result


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _optional_non_negative_int(name: str, value: object) -> int | None:
    if value is None:
        return None
    return _non_negative_int(name, value)


def _bool_int(name: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value not in (0, 1):
        raise ValueError(f"{name} must be boolean/0/1")
    return bool(value)


def _optional_bool_int(name: str, value: object) -> bool | None:
    if value is None:
        return None
    return _bool_int(name, value)


def _finite_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_float(name: str, value: object) -> float:
    result = _finite_float(name, value)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _optional_finite_float(name: str, value: object) -> float | None:
    if value is None:
        return None
    return _finite_float(name, value)


def _optional_positive_float(name: str, value: object) -> float | None:
    if value is None:
        return None
    return _positive_float(name, value)


def _optional_non_negative_float(name: str, value: object) -> float | None:
    if value is None:
        return None
    result = _finite_float(name, value)
    if result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _require_positive_int(name: str, value: object) -> None:
    _positive_int(name, value)


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
