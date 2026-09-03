from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any


FAST_TRAINING_FEATURE_SCHEMA_NAME = "shreks.fast_lane_training_features"
FAST_TRAINING_FEATURE_SCHEMA_VERSION = 1
DEFAULT_FAST_WINDOWS_MS = (100, 250, 500, 1_000, 2_000, 5_000, 10_000)

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "decision_signature",
        "decision_ordinal",
        "decision_sequence",
        "mint",
        "quote_mint",
        "venue",
        "decision_observed_at_unix_ms",
        "decision_provider",
        "decision_source_observed_at_unix_ms",
        "decision_occurred_at_unix_ms",
        "decision_slot",
        "decision_event_kind",
        "decision_actor",
        "decision_executable_entry_price_quote",
        "decision_entry_total_quote",
        "snapshot_as_of_unix_ms",
        "snapshot_last_sequence",
        "snapshot_last_price_quote",
        "last_reserve_context",
        "last_lifecycle_event",
        "windows",
    }
)
_WINDOW_KEYS = frozenset(
    {
        "window_ms",
        "buy_count",
        "sell_count",
        "unique_buy_actors",
        "unique_sell_actors",
        "buy_arrival_rate_per_second",
        "sell_arrival_rate_per_second",
        "count_imbalance",
        "buy_base_quantity",
        "sell_base_quantity",
        "buy_quote_quantity",
        "sell_quote_quantity",
        "net_quote_quantity",
        "quote_flow_imbalance",
        "quote_flow_velocity_per_second",
        "quote_flow_acceleration_per_second2",
        "local_high_price_quote",
        "local_high_sequence",
        "local_high_observed_at_unix_ms",
        "local_low_price_quote",
        "local_low_sequence",
        "local_low_observed_at_unix_ms",
        "post_high_low_price_quote",
        "post_high_low_sequence",
        "post_high_low_observed_at_unix_ms",
        "last_price_quote",
        "drawdown_from_local_high",
        "recovery_from_local_low",
    }
)
_PUMP_CURVE_KEYS = frozenset(
    {
        "kind",
        "virtual_base_reserve_raw",
        "virtual_quote_reserve_raw",
        "real_base_reserve_raw",
        "real_quote_reserve_raw",
        "base_decimals",
        "quote_decimals",
    }
)
_PUMP_SWAP_KEYS = frozenset(
    {
        "kind",
        "pool_base_reserve_raw",
        "pool_quote_reserve_raw",
        "virtual_quote_reserve_raw",
        "base_decimals",
        "quote_decimals",
    }
)
_LIFECYCLE_KEYS = frozenset(
    {
        "kind",
        "provider",
        "mint",
        "quote_mint",
        "from_venue",
        "to_venue",
        "pool_address",
        "signature",
        "slot",
        "detected_at_unix_ms",
        "occurred_at_unix_ms",
    }
)


@dataclass(frozen=True, slots=True)
class FastTrainingReserveContext:
    kind: str
    virtual_base_reserve_raw: int | None = None
    virtual_quote_reserve_raw: int | None = None
    real_base_reserve_raw: int | None = None
    real_quote_reserve_raw: int | None = None
    pool_base_reserve_raw: int | None = None
    pool_quote_reserve_raw: int | None = None
    base_decimals: int = 0
    quote_decimals: int = 0


@dataclass(frozen=True, slots=True)
class FastTrainingLifecycleEvent:
    kind: str
    provider: str
    mint: str
    quote_mint: str
    from_venue: str
    to_venue: str
    pool_address: str
    signature: str
    slot: int
    detected_at_unix_ms: int
    occurred_at_unix_ms: int | None


@dataclass(frozen=True, slots=True)
class FastTrainingWindowSummary:
    window_ms: int
    buy_count: int
    sell_count: int
    unique_buy_actors: int
    unique_sell_actors: int
    buy_arrival_rate_per_second: float
    sell_arrival_rate_per_second: float
    count_imbalance: float
    buy_base_quantity: float
    sell_base_quantity: float
    buy_quote_quantity: float
    sell_quote_quantity: float
    net_quote_quantity: float
    quote_flow_imbalance: float
    quote_flow_velocity_per_second: float
    quote_flow_acceleration_per_second2: float
    local_high_price_quote: float | None
    local_high_sequence: int | None
    local_high_observed_at_unix_ms: int | None
    local_low_price_quote: float | None
    local_low_sequence: int | None
    local_low_observed_at_unix_ms: int | None
    post_high_low_price_quote: float | None
    post_high_low_sequence: int | None
    post_high_low_observed_at_unix_ms: int | None
    last_price_quote: float | None
    drawdown_from_local_high: float
    recovery_from_local_low: float


@dataclass(frozen=True, slots=True)
class FastTrainingFeatureRecord:
    schema_name: str
    schema_version: int
    decision_signature: str
    decision_ordinal: int
    decision_sequence: int
    mint: str
    quote_mint: str
    venue: str
    decision_observed_at_unix_ms: int
    decision_provider: str
    decision_source_observed_at_unix_ms: int
    decision_occurred_at_unix_ms: int
    decision_slot: int
    decision_event_kind: str
    decision_actor: str | None
    decision_executable_entry_price_quote: float
    decision_entry_total_quote: float | None
    snapshot_as_of_unix_ms: int
    snapshot_last_sequence: int
    snapshot_last_price_quote: float | None
    last_reserve_context: FastTrainingReserveContext | None
    last_lifecycle_event: FastTrainingLifecycleEvent | None
    windows: tuple[FastTrainingWindowSummary, ...]

    @property
    def decision_identity(self) -> tuple[object, ...]:
        return (
            self.decision_signature,
            self.decision_ordinal,
            self.decision_sequence,
            self.mint,
            self.quote_mint,
            self.venue,
            self.decision_observed_at_unix_ms,
        )


@dataclass(frozen=True, slots=True)
class FastTrainingFeatureDataset:
    records: tuple[FastTrainingFeatureRecord, ...]
    logical_fingerprint_sha256: str
    source_sha256: str


def read_fast_training_feature_jsonl(path: str | Path) -> FastTrainingFeatureDataset:
    source = Path(path)
    raw = source.read_bytes()
    if not raw:
        raise ValueError("Fast Lane training feature JSONL cannot be empty")
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"training feature JSONL line {line_number} is blank")
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"training feature JSONL line {line_number} is invalid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise ValueError("training feature JSONL rows must be JSON objects")
        rows.append(value)
    records = _records_from_mappings(tuple(rows))
    return FastTrainingFeatureDataset(
        records=records,
        logical_fingerprint_sha256=feature_logical_fingerprint_sha256(records),
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )


def feature_logical_fingerprint_sha256(
    records: tuple[FastTrainingFeatureRecord, ...],
) -> str:
    if not records:
        raise ValueError("training feature dataset cannot be empty")
    payload = [_canonicalize(asdict(record)) for record in records]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_fast_training_feature_parquet(
    dataset: FastTrainingFeatureDataset,
    path: str | Path,
) -> None:
    if type(dataset) is not FastTrainingFeatureDataset:
        raise ValueError("dataset must be an exact FastTrainingFeatureDataset")
    if dataset.logical_fingerprint_sha256 != feature_logical_fingerprint_sha256(
        dataset.records
    ):
        raise ValueError("training feature dataset logical fingerprint is invalid")
    _require_sha256("source_sha256", dataset.source_sha256)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires the shreks-brain[research] extra"
        ) from exc

    metadata = {
        b"shreks_schema_name": FAST_TRAINING_FEATURE_SCHEMA_NAME.encode(),
        b"shreks_schema_version": str(FAST_TRAINING_FEATURE_SCHEMA_VERSION).encode(),
        b"shreks_row_count": str(len(dataset.records)).encode(),
        b"shreks_logical_sha256": dataset.logical_fingerprint_sha256.encode(),
        b"shreks_source_jsonl_sha256": dataset.source_sha256.encode(),
    }
    schema = _feature_arrow_schema(pa, metadata)
    rows = [_feature_to_parquet_mapping(record) for record in dataset.records]
    table = pa.Table.from_pylist(rows, schema=schema)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        destination,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
    )


def read_fast_training_feature_parquet(path: str | Path) -> FastTrainingFeatureDataset:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet import requires the shreks-brain[research] extra"
        ) from exc
    table = pq.read_table(Path(path))
    metadata = table.schema.metadata or {}
    expected_metadata = {
        b"shreks_schema_name": FAST_TRAINING_FEATURE_SCHEMA_NAME.encode(),
        b"shreks_schema_version": str(FAST_TRAINING_FEATURE_SCHEMA_VERSION).encode(),
    }
    if any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise ValueError("training feature Parquet metadata is incompatible")
    expected_schema = _feature_arrow_schema(pa, metadata)
    if table.schema != expected_schema:
        raise ValueError("training feature Parquet schema is incompatible")
    try:
        row_count = int(metadata[b"shreks_row_count"].decode())
        logical = metadata[b"shreks_logical_sha256"].decode()
        source_sha = metadata[b"shreks_source_jsonl_sha256"].decode()
    except (KeyError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("training feature Parquet metadata is incomplete") from exc
    _require_sha256("logical fingerprint", logical)
    _require_sha256("source JSONL fingerprint", source_sha)
    if row_count != table.num_rows or row_count <= 0:
        raise ValueError("training feature Parquet row count is incompatible")
    mappings = tuple(_parquet_mapping_to_feature_mapping(row) for row in table.to_pylist())
    records = _records_from_mappings(mappings)
    actual = feature_logical_fingerprint_sha256(records)
    if actual != logical:
        raise ValueError("training feature Parquet logical fingerprint does not match")
    return FastTrainingFeatureDataset(records, actual, source_sha)


def _records_from_mappings(
    rows: tuple[dict[str, object], ...],
) -> tuple[FastTrainingFeatureRecord, ...]:
    if not rows:
        raise ValueError("training feature dataset cannot be empty")
    records: list[FastTrainingFeatureRecord] = []
    seen: set[tuple[str, int]] = set()
    previous_sort: tuple[object, ...] | None = None
    previous_sequence: int | None = None
    for row in rows:
        record = _record_from_mapping(row)
        key = (record.decision_signature, record.decision_ordinal)
        if key in seen:
            raise ValueError("training feature dataset contains a duplicate decision identity")
        seen.add(key)
        sort_key = (
            record.decision_sequence,
            record.decision_signature,
            record.decision_ordinal,
        )
        if previous_sort is not None and sort_key < previous_sort:
            raise ValueError("training feature rows are not in canonical order")
        if previous_sequence is not None and record.decision_sequence <= previous_sequence:
            raise ValueError("training feature decision sequences must strictly increase")
        previous_sort = sort_key
        previous_sequence = record.decision_sequence
        records.append(record)
    return tuple(records)


def _record_from_mapping(row: dict[str, object]) -> FastTrainingFeatureRecord:
    _require_exact_keys("training feature row", row, _TOP_LEVEL_KEYS)
    schema_name = _text("schema_name", row["schema_name"])
    schema_version = _int("schema_version", row["schema_version"], minimum=1)
    if schema_name != FAST_TRAINING_FEATURE_SCHEMA_NAME or schema_version != FAST_TRAINING_FEATURE_SCHEMA_VERSION:
        raise ValueError("training feature schema name/version is incompatible")

    decision_time = _int(
        "decision_observed_at_unix_ms", row["decision_observed_at_unix_ms"], minimum=0
    )
    decision_sequence = _int("decision_sequence", row["decision_sequence"], minimum=1)
    snapshot_time = _int("snapshot_as_of_unix_ms", row["snapshot_as_of_unix_ms"], minimum=0)
    snapshot_sequence = _int("snapshot_last_sequence", row["snapshot_last_sequence"], minimum=1)
    if snapshot_time != decision_time:
        raise ValueError("training feature snapshot timestamp must equal decision timestamp")
    if snapshot_sequence > decision_sequence:
        raise ValueError("training feature snapshot contains a future sequence")
    if snapshot_sequence != decision_sequence:
        raise ValueError("training feature snapshot must terminate at the decision sequence")

    source_time = _int(
        "decision_source_observed_at_unix_ms",
        row["decision_source_observed_at_unix_ms"],
        minimum=0,
    )
    occurred_time = _int(
        "decision_occurred_at_unix_ms", row["decision_occurred_at_unix_ms"], minimum=0
    )
    if source_time > decision_time or occurred_time > decision_time:
        raise ValueError("training feature decision provenance contains a future timestamp")

    windows_value = row["windows"]
    if not isinstance(windows_value, list) or len(windows_value) != len(DEFAULT_FAST_WINDOWS_MS):
        raise ValueError("training feature row must contain the sealed default windows")
    windows = tuple(
        _window_from_mapping(value, decision_sequence, decision_time)
        for value in windows_value
    )
    if tuple(value.window_ms for value in windows) != DEFAULT_FAST_WINDOWS_MS:
        raise ValueError("training feature windows are not the sealed defaults in order")

    reserve = _reserve_from_mapping(row["last_reserve_context"])
    lifecycle = _lifecycle_from_mapping(row["last_lifecycle_event"])
    mint = _text("mint", row["mint"])
    quote_mint = _text("quote_mint", row["quote_mint"])
    venue = _text("venue", row["venue"])
    if lifecycle is not None:
        if lifecycle.detected_at_unix_ms > decision_time:
            raise ValueError("training feature row contains future lifecycle evidence")
        if lifecycle.mint != mint or lifecycle.quote_mint != quote_mint:
            raise ValueError("training lifecycle evidence does not match feature market")
        if venue not in {lifecycle.from_venue, lifecycle.to_venue}:
            raise ValueError("training lifecycle evidence does not map to feature venue")

    actor_value = row["decision_actor"]
    actor = None if actor_value is None else _text("decision_actor", actor_value)
    entry_total = _optional_positive_float("decision_entry_total_quote", row["decision_entry_total_quote"])
    last_price = _optional_positive_float("snapshot_last_price_quote", row["snapshot_last_price_quote"])

    return FastTrainingFeatureRecord(
        schema_name=schema_name,
        schema_version=schema_version,
        decision_signature=_text("decision_signature", row["decision_signature"]),
        decision_ordinal=_int("decision_ordinal", row["decision_ordinal"], minimum=0),
        decision_sequence=decision_sequence,
        mint=mint,
        quote_mint=quote_mint,
        venue=venue,
        decision_observed_at_unix_ms=decision_time,
        decision_provider=_text("decision_provider", row["decision_provider"]),
        decision_source_observed_at_unix_ms=source_time,
        decision_occurred_at_unix_ms=occurred_time,
        decision_slot=_int("decision_slot", row["decision_slot"], minimum=0),
        decision_event_kind=_enum_text("decision_event_kind", row["decision_event_kind"], {"buy", "sell"}),
        decision_actor=actor,
        decision_executable_entry_price_quote=_positive_float(
            "decision_executable_entry_price_quote",
            row["decision_executable_entry_price_quote"],
        ),
        decision_entry_total_quote=entry_total,
        snapshot_as_of_unix_ms=snapshot_time,
        snapshot_last_sequence=snapshot_sequence,
        snapshot_last_price_quote=last_price,
        last_reserve_context=reserve,
        last_lifecycle_event=lifecycle,
        windows=windows,
    )


def _window_from_mapping(
    value: object, decision_sequence: int, decision_time: int
) -> FastTrainingWindowSummary:
    if not isinstance(value, dict):
        raise ValueError("training feature windows must be objects")
    _require_exact_keys("training feature window", value, _WINDOW_KEYS)
    optional_sequences = {
        name: _optional_int(name, value[name], minimum=0)
        for name in (
            "local_high_sequence",
            "local_low_sequence",
            "post_high_low_sequence",
        )
    }
    if any(
        sequence is not None and sequence > decision_sequence
        for sequence in optional_sequences.values()
    ):
        raise ValueError("training feature window contains a future sequence")
    optional_times = {
        name: _optional_int(name, value[name], minimum=0)
        for name in (
            "local_high_observed_at_unix_ms",
            "local_low_observed_at_unix_ms",
            "post_high_low_observed_at_unix_ms",
        )
    }
    if any(
        timestamp is not None and timestamp > decision_time
        for timestamp in optional_times.values()
    ):
        raise ValueError("training feature window contains a future timestamp")

    return FastTrainingWindowSummary(
        window_ms=_int("window_ms", value["window_ms"], minimum=1),
        buy_count=_int("buy_count", value["buy_count"], minimum=0),
        sell_count=_int("sell_count", value["sell_count"], minimum=0),
        unique_buy_actors=_int("unique_buy_actors", value["unique_buy_actors"], minimum=0),
        unique_sell_actors=_int("unique_sell_actors", value["unique_sell_actors"], minimum=0),
        buy_arrival_rate_per_second=_finite_float("buy_arrival_rate_per_second", value["buy_arrival_rate_per_second"]),
        sell_arrival_rate_per_second=_finite_float("sell_arrival_rate_per_second", value["sell_arrival_rate_per_second"]),
        count_imbalance=_finite_float("count_imbalance", value["count_imbalance"]),
        buy_base_quantity=_finite_float("buy_base_quantity", value["buy_base_quantity"]),
        sell_base_quantity=_finite_float("sell_base_quantity", value["sell_base_quantity"]),
        buy_quote_quantity=_finite_float("buy_quote_quantity", value["buy_quote_quantity"]),
        sell_quote_quantity=_finite_float("sell_quote_quantity", value["sell_quote_quantity"]),
        net_quote_quantity=_finite_float("net_quote_quantity", value["net_quote_quantity"]),
        quote_flow_imbalance=_finite_float("quote_flow_imbalance", value["quote_flow_imbalance"]),
        quote_flow_velocity_per_second=_finite_float("quote_flow_velocity_per_second", value["quote_flow_velocity_per_second"]),
        quote_flow_acceleration_per_second2=_finite_float("quote_flow_acceleration_per_second2", value["quote_flow_acceleration_per_second2"]),
        local_high_price_quote=_optional_positive_float("local_high_price_quote", value["local_high_price_quote"]),
        local_high_sequence=optional_sequences["local_high_sequence"],
        local_high_observed_at_unix_ms=optional_times["local_high_observed_at_unix_ms"],
        local_low_price_quote=_optional_positive_float("local_low_price_quote", value["local_low_price_quote"]),
        local_low_sequence=optional_sequences["local_low_sequence"],
        local_low_observed_at_unix_ms=optional_times["local_low_observed_at_unix_ms"],
        post_high_low_price_quote=_optional_positive_float("post_high_low_price_quote", value["post_high_low_price_quote"]),
        post_high_low_sequence=optional_sequences["post_high_low_sequence"],
        post_high_low_observed_at_unix_ms=optional_times["post_high_low_observed_at_unix_ms"],
        last_price_quote=_optional_positive_float("last_price_quote", value["last_price_quote"]),
        drawdown_from_local_high=_finite_float("drawdown_from_local_high", value["drawdown_from_local_high"]),
        recovery_from_local_low=_finite_float("recovery_from_local_low", value["recovery_from_local_low"]),
    )


def _reserve_from_mapping(value: object) -> FastTrainingReserveContext | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("training reserve context must be an object or null")
    kind = _text("reserve kind", value.get("kind"))
    if kind == "pump_curve":
        _require_exact_keys("Pump curve reserve context", value, _PUMP_CURVE_KEYS)
        return FastTrainingReserveContext(
            kind=kind,
            virtual_base_reserve_raw=_int("virtual_base_reserve_raw", value["virtual_base_reserve_raw"], minimum=0),
            virtual_quote_reserve_raw=_int("virtual_quote_reserve_raw", value["virtual_quote_reserve_raw"], minimum=0),
            real_base_reserve_raw=_int("real_base_reserve_raw", value["real_base_reserve_raw"], minimum=0),
            real_quote_reserve_raw=_int("real_quote_reserve_raw", value["real_quote_reserve_raw"], minimum=0),
            base_decimals=_int("base_decimals", value["base_decimals"], minimum=0, maximum=255),
            quote_decimals=_int("quote_decimals", value["quote_decimals"], minimum=0, maximum=255),
        )
    if kind == "pump_swap_pool":
        _require_exact_keys("PumpSwap reserve context", value, _PUMP_SWAP_KEYS)
        return FastTrainingReserveContext(
            kind=kind,
            pool_base_reserve_raw=_int("pool_base_reserve_raw", value["pool_base_reserve_raw"], minimum=0),
            pool_quote_reserve_raw=_int("pool_quote_reserve_raw", value["pool_quote_reserve_raw"], minimum=0),
            virtual_quote_reserve_raw=_optional_int("virtual_quote_reserve_raw", value["virtual_quote_reserve_raw"]),
            base_decimals=_int("base_decimals", value["base_decimals"], minimum=0, maximum=255),
            quote_decimals=_int("quote_decimals", value["quote_decimals"], minimum=0, maximum=255),
        )
    raise ValueError(f"unsupported training reserve context kind '{kind}'")


def _lifecycle_from_mapping(value: object) -> FastTrainingLifecycleEvent | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("training lifecycle event must be an object or null")
    _require_exact_keys("training lifecycle event", value, _LIFECYCLE_KEYS)
    kind = _enum_text("lifecycle kind", value["kind"], {"pump_graduation"})
    occurred = _optional_int("lifecycle occurred_at_unix_ms", value["occurred_at_unix_ms"], minimum=0)
    return FastTrainingLifecycleEvent(
        kind=kind,
        provider=_text("lifecycle provider", value["provider"]),
        mint=_text("lifecycle mint", value["mint"]),
        quote_mint=_text("lifecycle quote_mint", value["quote_mint"]),
        from_venue=_text("lifecycle from_venue", value["from_venue"]),
        to_venue=_text("lifecycle to_venue", value["to_venue"]),
        pool_address=_text("lifecycle pool_address", value["pool_address"]),
        signature=_text("lifecycle signature", value["signature"]),
        slot=_int("lifecycle slot", value["slot"], minimum=0),
        detected_at_unix_ms=_int("lifecycle detected_at_unix_ms", value["detected_at_unix_ms"], minimum=0),
        occurred_at_unix_ms=occurred,
    )


def _feature_arrow_schema(pa: Any, metadata: dict[bytes, bytes] | None):
    reserve = pa.struct(
        [
            pa.field("kind", pa.string(), nullable=False),
            pa.field("virtual_base_reserve_raw", pa.string()),
            pa.field("virtual_quote_reserve_raw", pa.string()),
            pa.field("real_base_reserve_raw", pa.string()),
            pa.field("real_quote_reserve_raw", pa.string()),
            pa.field("pool_base_reserve_raw", pa.string()),
            pa.field("pool_quote_reserve_raw", pa.string()),
            pa.field("base_decimals", pa.int16(), nullable=False),
            pa.field("quote_decimals", pa.int16(), nullable=False),
        ]
    )
    lifecycle = pa.struct(
        [
            pa.field("kind", pa.string(), nullable=False),
            pa.field("provider", pa.string(), nullable=False),
            pa.field("mint", pa.string(), nullable=False),
            pa.field("quote_mint", pa.string(), nullable=False),
            pa.field("from_venue", pa.string(), nullable=False),
            pa.field("to_venue", pa.string(), nullable=False),
            pa.field("pool_address", pa.string(), nullable=False),
            pa.field("signature", pa.string(), nullable=False),
            pa.field("slot", pa.string(), nullable=False),
            pa.field("detected_at_unix_ms", pa.int64(), nullable=False),
            pa.field("occurred_at_unix_ms", pa.int64()),
        ]
    )
    window = pa.struct(
        [
            pa.field("window_ms", pa.int64(), nullable=False),
            pa.field("buy_count", pa.int64(), nullable=False),
            pa.field("sell_count", pa.int64(), nullable=False),
            pa.field("unique_buy_actors", pa.int64(), nullable=False),
            pa.field("unique_sell_actors", pa.int64(), nullable=False),
            pa.field("buy_arrival_rate_per_second", pa.float64(), nullable=False),
            pa.field("sell_arrival_rate_per_second", pa.float64(), nullable=False),
            pa.field("count_imbalance", pa.float64(), nullable=False),
            pa.field("buy_base_quantity", pa.float64(), nullable=False),
            pa.field("sell_base_quantity", pa.float64(), nullable=False),
            pa.field("buy_quote_quantity", pa.float64(), nullable=False),
            pa.field("sell_quote_quantity", pa.float64(), nullable=False),
            pa.field("net_quote_quantity", pa.float64(), nullable=False),
            pa.field("quote_flow_imbalance", pa.float64(), nullable=False),
            pa.field("quote_flow_velocity_per_second", pa.float64(), nullable=False),
            pa.field("quote_flow_acceleration_per_second2", pa.float64(), nullable=False),
            pa.field("local_high_price_quote", pa.float64()),
            pa.field("local_high_sequence", pa.int64()),
            pa.field("local_high_observed_at_unix_ms", pa.int64()),
            pa.field("local_low_price_quote", pa.float64()),
            pa.field("local_low_sequence", pa.int64()),
            pa.field("local_low_observed_at_unix_ms", pa.int64()),
            pa.field("post_high_low_price_quote", pa.float64()),
            pa.field("post_high_low_sequence", pa.int64()),
            pa.field("post_high_low_observed_at_unix_ms", pa.int64()),
            pa.field("last_price_quote", pa.float64()),
            pa.field("drawdown_from_local_high", pa.float64(), nullable=False),
            pa.field("recovery_from_local_low", pa.float64(), nullable=False),
        ]
    )
    return pa.schema(
        [
            pa.field("schema_name", pa.string(), nullable=False),
            pa.field("schema_version", pa.int16(), nullable=False),
            pa.field("decision_signature", pa.string(), nullable=False),
            pa.field("decision_ordinal", pa.int64(), nullable=False),
            pa.field("decision_sequence", pa.int64(), nullable=False),
            pa.field("mint", pa.string(), nullable=False),
            pa.field("quote_mint", pa.string(), nullable=False),
            pa.field("venue", pa.string(), nullable=False),
            pa.field("decision_observed_at_unix_ms", pa.int64(), nullable=False),
            pa.field("decision_provider", pa.string(), nullable=False),
            pa.field("decision_source_observed_at_unix_ms", pa.int64(), nullable=False),
            pa.field("decision_occurred_at_unix_ms", pa.int64(), nullable=False),
            pa.field("decision_slot", pa.string(), nullable=False),
            pa.field("decision_event_kind", pa.string(), nullable=False),
            pa.field("decision_actor", pa.string()),
            pa.field("decision_executable_entry_price_quote", pa.float64(), nullable=False),
            pa.field("decision_entry_total_quote", pa.float64()),
            pa.field("snapshot_as_of_unix_ms", pa.int64(), nullable=False),
            pa.field("snapshot_last_sequence", pa.int64(), nullable=False),
            pa.field("snapshot_last_price_quote", pa.float64()),
            pa.field("last_reserve_context", reserve),
            pa.field("last_lifecycle_event", lifecycle),
            pa.field("windows", pa.list_(window), nullable=False),
        ],
        metadata=metadata,
    )


def _feature_to_parquet_mapping(record: FastTrainingFeatureRecord) -> dict[str, object]:
    result = asdict(record)
    result["decision_slot"] = str(record.decision_slot)
    reserve = result["last_reserve_context"]
    if reserve is not None:
        for name in (
            "virtual_base_reserve_raw",
            "virtual_quote_reserve_raw",
            "real_base_reserve_raw",
            "real_quote_reserve_raw",
            "pool_base_reserve_raw",
            "pool_quote_reserve_raw",
        ):
            if reserve[name] is not None:
                reserve[name] = str(reserve[name])
    lifecycle = result["last_lifecycle_event"]
    if lifecycle is not None:
        lifecycle["slot"] = str(lifecycle["slot"])
    result["windows"] = [dict(value) for value in result["windows"]]
    return result


def _parquet_mapping_to_feature_mapping(row: dict[str, object]) -> dict[str, object]:
    result = dict(row)
    result["decision_slot"] = int(str(result["decision_slot"]))
    reserve = result["last_reserve_context"]
    if reserve is not None:
        reserve = dict(reserve)
        for name in (
            "virtual_base_reserve_raw",
            "virtual_quote_reserve_raw",
            "real_base_reserve_raw",
            "real_quote_reserve_raw",
            "pool_base_reserve_raw",
            "pool_quote_reserve_raw",
        ):
            if reserve[name] is not None:
                reserve[name] = int(str(reserve[name]))
        # Reconstruct the exact tagged Rust shape rather than exposing null fields
        # that do not belong to the active variant.
        if reserve["kind"] == "pump_curve":
            result["last_reserve_context"] = {
                name: reserve[name]
                for name in (
                    "kind",
                    "virtual_base_reserve_raw",
                    "virtual_quote_reserve_raw",
                    "real_base_reserve_raw",
                    "real_quote_reserve_raw",
                    "base_decimals",
                    "quote_decimals",
                )
            }
        else:
            result["last_reserve_context"] = {
                "kind": reserve["kind"],
                "pool_base_reserve_raw": reserve["pool_base_reserve_raw"],
                "pool_quote_reserve_raw": reserve["pool_quote_reserve_raw"],
                "virtual_quote_reserve_raw": reserve["virtual_quote_reserve_raw"],
                "base_decimals": reserve["base_decimals"],
                "quote_decimals": reserve["quote_decimals"],
            }
    lifecycle = result["last_lifecycle_event"]
    if lifecycle is not None:
        lifecycle = dict(lifecycle)
        lifecycle["slot"] = int(str(lifecycle["slot"]))
        result["last_lifecycle_event"] = lifecycle
    result["windows"] = [dict(value) for value in result["windows"]]
    return result


def _canonicalize(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("training feature logical fingerprint rejects non-finite floats")
        return {"__float_hex__": value.hex()}
    if isinstance(value, dict):
        return {key: _canonicalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def _require_exact_keys(name: str, value: dict[str, object], expected: frozenset[str]) -> None:
    if frozenset(value) != expected:
        missing = sorted(expected.difference(value))
        extra = sorted(frozenset(value).difference(expected))
        raise ValueError(f"{name} keys are incompatible; missing={missing}, extra={extra}")


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _enum_text(name: str, value: object, allowed: set[str]) -> str:
    result = _text(name, value)
    if result not in allowed:
        raise ValueError(f"{name} is incompatible")
    return result


def _int(
    name: str,
    value: object,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _optional_int(
    name: str, value: object, *, minimum: int | None = None
) -> int | None:
    if value is None:
        return None
    return _int(name, value, minimum=minimum)


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


def _optional_positive_float(name: str, value: object) -> float | None:
    if value is None:
        return None
    return _positive_float(name, value)


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
