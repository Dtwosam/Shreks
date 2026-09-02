from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

from .counterfactuals import (
    COUNTERFACTUAL_ACTION_LABEL_VERSION,
    CounterfactualAction,
    CounterfactualActionOutcome,
    CounterfactualOutcomeSet,
    ExecutionStatus,
)


COUNTERFACTUAL_DATASET_SCHEMA_NAME = "shreks.counterfactual_action_labels"
COUNTERFACTUAL_DATASET_SCHEMA_VERSION = 1

COUNTERFACTUAL_DATASET_COLUMNS = (
    "label_version",
    "decision_id",
    "mint",
    "quote_mint",
    "action",
    "alternative_id",
    "action_observed_at_unix_ms",
    "horizon_ms",
    "delay_ms",
    "base_quantity",
    "execution_status",
    "entry_total_quote",
    "exit_net_quote",
    "net_pnl_quote",
    "return_bps",
    "entry_evidence_id",
    "exit_evidence_id",
    "position_cost_basis_quote",
    "realized_cost_basis_quote",
    "remaining_base_quantity",
    "remaining_cost_basis_quote",
    "entry_quote_savings_vs_buy_now",
    "return_bps_delta_vs_buy_now",
    "entry_source_event_signature",
    "entry_source_event_ordinal",
    "entry_evidence_observed_at_unix_ms",
    "entry_evidence_version",
    "exit_source_event_signature",
    "exit_source_event_ordinal",
    "exit_evidence_observed_at_unix_ms",
    "exit_evidence_version",
)

_STRING_COLUMNS = {
    "decision_id",
    "mint",
    "quote_mint",
    "action",
    "alternative_id",
    "execution_status",
    "entry_evidence_id",
    "exit_evidence_id",
    "entry_source_event_signature",
    "entry_evidence_version",
    "exit_source_event_signature",
    "exit_evidence_version",
}

_INT_COLUMNS = {
    "label_version",
    "action_observed_at_unix_ms",
    "horizon_ms",
    "delay_ms",
    "entry_source_event_ordinal",
    "entry_evidence_observed_at_unix_ms",
    "exit_source_event_ordinal",
    "exit_evidence_observed_at_unix_ms",
}

_ACTION_ORDER = {
    CounterfactualAction.BUY_NOW.value: 0,
    CounterfactualAction.SKIP.value: 1,
    CounterfactualAction.DELAY_ENTRY.value: 2,
    CounterfactualAction.HOLD.value: 3,
    CounterfactualAction.REDUCE_NOW.value: 4,
    CounterfactualAction.SELL_NOW.value: 5,
}

_REQUIRED_METADATA_KEYS = (
    b"shreks_schema_name",
    b"shreks_schema_version",
    b"shreks_counterfactual_label_version",
    b"shreks_row_count",
    b"shreks_logical_sha256",
)


@dataclass(frozen=True, slots=True)
class CounterfactualDatasetManifest:
    schema_name: str
    schema_version: int
    label_version: int
    row_count: int
    min_action_observed_at_unix_ms: int
    max_action_observed_at_unix_ms: int
    dataset_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != COUNTERFACTUAL_DATASET_SCHEMA_NAME:
            raise ValueError(
                f"schema_name must equal {COUNTERFACTUAL_DATASET_SCHEMA_NAME}"
            )
        if self.schema_version != COUNTERFACTUAL_DATASET_SCHEMA_VERSION:
            raise ValueError(
                "schema_version must equal the sealed counterfactual Parquet version"
            )
        if self.label_version != COUNTERFACTUAL_ACTION_LABEL_VERSION:
            raise ValueError(
                "label_version must equal the current counterfactual label version"
            )
        _require_positive_int("row_count", self.row_count)
        _require_non_negative_int(
            "min_action_observed_at_unix_ms",
            self.min_action_observed_at_unix_ms,
        )
        _require_non_negative_int(
            "max_action_observed_at_unix_ms",
            self.max_action_observed_at_unix_ms,
        )
        if self.min_action_observed_at_unix_ms > self.max_action_observed_at_unix_ms:
            raise ValueError("counterfactual manifest timestamp range must satisfy min <= max")
        _require_sha256(
            "dataset_fingerprint_sha256", self.dataset_fingerprint_sha256
        )


def write_counterfactual_parquet(
    outcome_sets: tuple[CounterfactualOutcomeSet, ...],
    path: str | Path,
) -> CounterfactualDatasetManifest:
    rows = _build_counterfactual_rows(outcome_sets)

    destination = Path(path)
    if destination.suffix != ".parquet":
        raise ValueError("counterfactual dataset path must end with .parquet")

    digest = _logical_dataset_fingerprint_sha256(rows)
    manifest = _manifest_for_rows(rows, digest)

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires the shreks-brain[research] extra"
        ) from exc

    metadata = {
        b"shreks_schema_name": COUNTERFACTUAL_DATASET_SCHEMA_NAME.encode(),
        b"shreks_schema_version": str(
            COUNTERFACTUAL_DATASET_SCHEMA_VERSION
        ).encode(),
        b"shreks_counterfactual_label_version": str(
            COUNTERFACTUAL_ACTION_LABEL_VERSION
        ).encode(),
        b"shreks_row_count": str(manifest.row_count).encode(),
        b"shreks_logical_sha256": digest.encode(),
    }
    schema = _arrow_schema(pa, metadata)
    table = pa.Table.from_pylist([dict(row) for row in rows], schema=schema)

    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        destination,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
    )
    return manifest


def read_counterfactual_parquet(
    path: str | Path,
) -> tuple[tuple[dict[str, object], ...], CounterfactualDatasetManifest]:
    source = Path(path)
    if source.suffix != ".parquet":
        raise ValueError("counterfactual dataset path must end with .parquet")

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet import requires the shreks-brain[research] extra"
        ) from exc

    table = pq.read_table(source)
    if tuple(table.column_names) != COUNTERFACTUAL_DATASET_COLUMNS:
        raise ValueError("counterfactual Parquet schema columns are incompatible")

    expected_schema = _arrow_schema(pa, table.schema.metadata)
    for actual, expected in zip(table.schema, expected_schema, strict=True):
        if actual.name != expected.name or actual.type != expected.type:
            raise ValueError("counterfactual Parquet schema types are incompatible")

    metadata = table.schema.metadata or {}
    _validate_metadata(metadata)

    try:
        metadata_row_count = int(metadata[b"shreks_row_count"].decode())
        metadata_digest = metadata[b"shreks_logical_sha256"].decode()
    except (KeyError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("counterfactual Parquet metadata is incompatible") from exc

    _require_sha256("shreks_logical_sha256", metadata_digest)
    if metadata_row_count != table.num_rows or metadata_row_count <= 0:
        raise ValueError("counterfactual Parquet metadata row count is incompatible")

    rows = tuple(dict(row) for row in table.to_pylist())
    _validate_loaded_rows(rows)
    digest = _logical_dataset_fingerprint_sha256(rows)
    if digest != metadata_digest:
        raise ValueError("counterfactual Parquet logical fingerprint does not match metadata")

    return rows, _manifest_for_rows(rows, digest)


def _build_counterfactual_rows(
    outcome_sets: tuple[CounterfactualOutcomeSet, ...],
) -> tuple[dict[str, object], ...]:
    if not isinstance(outcome_sets, tuple) or not outcome_sets:
        raise ValueError("counterfactual dataset cannot be empty")

    rows: list[dict[str, object]] = []
    seen_keys: set[tuple[object, ...]] = set()
    for outcome_set in outcome_sets:
        if type(outcome_set) is not CounterfactualOutcomeSet:
            raise ValueError(
                "counterfactual dataset inputs must be exact CounterfactualOutcomeSet values"
            )
        if not outcome_set.outcomes:
            raise ValueError("counterfactual outcome set cannot be empty")
        expected_set_fingerprint = _outcome_set_fingerprint_sha256(
            outcome_set.outcomes
        )
        if outcome_set.fingerprint_sha256 != expected_set_fingerprint:
            raise ValueError("counterfactual outcome-set fingerprint does not match rows")

        for outcome in outcome_set.outcomes:
            if type(outcome) is not CounterfactualActionOutcome:
                raise ValueError(
                    "counterfactual outcome set contains a non-canonical row type"
                )
            if outcome.label_version != COUNTERFACTUAL_ACTION_LABEL_VERSION:
                raise ValueError("counterfactual row label version is incompatible")
            row = _row_from_outcome(outcome)
            key = _logical_action_key(row)
            if key in seen_keys:
                raise ValueError("counterfactual dataset contains a duplicate logical action row")
            seen_keys.add(key)
            rows.append(row)

    rows.sort(key=_canonical_row_sort_key)
    _validate_loaded_rows(tuple(rows))
    return tuple(rows)


def _row_from_outcome(outcome: CounterfactualActionOutcome) -> dict[str, object]:
    row = asdict(outcome)
    row["action"] = outcome.action.value
    row["execution_status"] = outcome.execution_status.value
    if tuple(row) != COUNTERFACTUAL_DATASET_COLUMNS:
        raise ValueError(
            "counterfactual outcome fields changed without a Parquet schema version bump"
        )
    return row


def _validate_loaded_rows(rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        raise ValueError("counterfactual dataset cannot be empty")

    previous_sort_key: tuple[object, ...] | None = None
    seen_keys: set[tuple[object, ...]] = set()
    for row in rows:
        if tuple(row) != COUNTERFACTUAL_DATASET_COLUMNS:
            raise ValueError("counterfactual Parquet row columns are incompatible")
        if row["label_version"] != COUNTERFACTUAL_ACTION_LABEL_VERSION:
            raise ValueError("counterfactual Parquet row label version is incompatible")
        action = row["action"]
        status = row["execution_status"]
        if action not in _ACTION_ORDER:
            raise ValueError("counterfactual Parquet row action is incompatible")
        if status not in {value.value for value in ExecutionStatus}:
            raise ValueError("counterfactual Parquet execution status is incompatible")
        _require_text("decision_id", row["decision_id"])
        _require_text("mint", row["mint"])
        _require_text("quote_mint", row["quote_mint"])
        _require_non_negative_int(
            "action_observed_at_unix_ms", row["action_observed_at_unix_ms"]
        )
        _require_positive_int("horizon_ms", row["horizon_ms"])
        _require_non_negative_int("delay_ms", row["delay_ms"])
        _require_positive_finite("base_quantity", row["base_quantity"])
        for name in (
            "entry_total_quote",
            "exit_net_quote",
            "net_pnl_quote",
            "return_bps",
            "position_cost_basis_quote",
            "realized_cost_basis_quote",
            "remaining_base_quantity",
            "remaining_cost_basis_quote",
            "entry_quote_savings_vs_buy_now",
            "return_bps_delta_vs_buy_now",
        ):
            _require_optional_finite(name, row[name])
        for name in (
            "entry_source_event_ordinal",
            "entry_evidence_observed_at_unix_ms",
            "exit_source_event_ordinal",
            "exit_evidence_observed_at_unix_ms",
        ):
            _require_optional_non_negative_int(name, row[name])

        key = _logical_action_key(row)
        if key in seen_keys:
            raise ValueError("counterfactual dataset contains a duplicate logical action row")
        seen_keys.add(key)

        sort_key = _canonical_row_sort_key(row)
        if previous_sort_key is not None and sort_key < previous_sort_key:
            raise ValueError("counterfactual Parquet rows are not in canonical order")
        previous_sort_key = sort_key


def _logical_action_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["decision_id"],
        row["mint"],
        row["quote_mint"],
        row["action"],
        row["alternative_id"],
        row["action_observed_at_unix_ms"],
        row["horizon_ms"],
        row["base_quantity"],
    )


def _canonical_row_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    action = row["action"]
    assert isinstance(action, str)
    return (
        row["action_observed_at_unix_ms"],
        row["decision_id"],
        row["horizon_ms"],
        _ACTION_ORDER[action],
        "" if row["alternative_id"] is None else row["alternative_id"],
        row["base_quantity"],
    )


def _logical_dataset_fingerprint_sha256(
    rows: tuple[dict[str, object], ...],
) -> str:
    encoded = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _outcome_set_fingerprint_sha256(
    outcomes: tuple[CounterfactualActionOutcome, ...],
) -> str:
    payload = [asdict(outcome) for outcome in outcomes]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_for_rows(
    rows: tuple[dict[str, object], ...],
    digest: str,
) -> CounterfactualDatasetManifest:
    timestamps = tuple(int(row["action_observed_at_unix_ms"]) for row in rows)
    return CounterfactualDatasetManifest(
        schema_name=COUNTERFACTUAL_DATASET_SCHEMA_NAME,
        schema_version=COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
        label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        row_count=len(rows),
        min_action_observed_at_unix_ms=min(timestamps),
        max_action_observed_at_unix_ms=max(timestamps),
        dataset_fingerprint_sha256=digest,
    )


def _arrow_schema(pa, metadata: dict[bytes, bytes] | None):
    fields = []
    for column in COUNTERFACTUAL_DATASET_COLUMNS:
        if column in _STRING_COLUMNS:
            value_type = pa.string()
        elif column in _INT_COLUMNS:
            value_type = pa.int64()
        else:
            value_type = pa.float64()
        fields.append(pa.field(column, value_type, nullable=True))
    return pa.schema(fields, metadata=metadata)


def _validate_metadata(metadata: dict[bytes, bytes]) -> None:
    if any(key not in metadata for key in _REQUIRED_METADATA_KEYS):
        raise ValueError("counterfactual Parquet metadata is incomplete")
    expected = {
        b"shreks_schema_name": COUNTERFACTUAL_DATASET_SCHEMA_NAME.encode(),
        b"shreks_schema_version": str(
            COUNTERFACTUAL_DATASET_SCHEMA_VERSION
        ).encode(),
        b"shreks_counterfactual_label_version": str(
            COUNTERFACTUAL_ACTION_LABEL_VERSION
        ).encode(),
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("counterfactual Parquet metadata is incompatible")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_non_negative_int(name: str, value: object) -> None:
    if value is None:
        return
    _require_non_negative_int(name, value)


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_positive_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")


def _require_optional_finite(name: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number or None")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number or None")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase 64-character hex digest")
