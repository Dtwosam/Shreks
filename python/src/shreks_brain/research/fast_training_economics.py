from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, fields
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from .counterfactuals import (
    EntryCounterfactualContext,
    ExecutableTradeEvidence,
    ExecutionStatus,
    TradeSide,
)


FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME = "shreks.fast_training_economics_overlay"
FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION = 2

_ROWS_FILENAME = "rows.jsonl"
_MANIFEST_FILENAME = "manifest.json"


class FastTrainingEconomicsStatus(StrEnum):
    AVAILABLE = "available"
    UNSUPPORTED_VENUE = "unsupported_venue"
    NO_ENDPOINT = "no_endpoint"
    ENTRY_RESERVE_UNAVAILABLE = "entry_reserve_unavailable"
    EXIT_RESERVE_UNAVAILABLE = "exit_reserve_unavailable"
    ENTRY_PROJECTION_UNAVAILABLE = "entry_projection_unavailable"
    EXIT_PROJECTION_UNAVAILABLE = "exit_projection_unavailable"
    ENTRY_FEE_MISSING = "entry_fee_missing"
    ENTRY_FEE_STALE = "entry_fee_stale"
    ENTRY_FEE_RATE_UNKNOWN = "entry_fee_rate_unknown"
    EXIT_FEE_MISSING = "exit_fee_missing"
    EXIT_FEE_STALE = "exit_fee_stale"
    EXIT_FEE_RATE_UNKNOWN = "exit_fee_rate_unknown"


@dataclass(frozen=True, slots=True)
class FastTrainingExecutionCostPolicy:
    version: str
    additional_entry_slippage_bps: int
    additional_exit_slippage_bps: int
    entry_latency_bps: int
    exit_latency_bps: int
    entry_network_fee_quote: float
    exit_network_fee_quote: float
    entry_priority_fee_quote: float
    exit_priority_fee_quote: float
    entry_expected_failure_cost_quote: float
    exit_expected_failure_cost_quote: float

    def __post_init__(self) -> None:
        _require_canonical_text("version", self.version)
        for name in (
            "additional_entry_slippage_bps",
            "additional_exit_slippage_bps",
            "entry_latency_bps",
            "exit_latency_bps",
        ):
            value = getattr(self, name)
            _require_non_negative_int(name, value)
            if value > 10_000:
                raise ValueError(f"{name} must be at most 10000")

        for name in (
            "entry_network_fee_quote",
            "exit_network_fee_quote",
            "entry_priority_fee_quote",
            "exit_priority_fee_quote",
            "entry_expected_failure_cost_quote",
            "exit_expected_failure_cost_quote",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a non-negative finite number")
            normalized = float(value)
            if not math.isfinite(normalized) or normalized < 0:
                raise ValueError(f"{name} must be a non-negative finite number")
            object.__setattr__(self, name, normalized)


@dataclass(frozen=True, slots=True)
class FastTrainingEconomicsReserveProvenance:
    source_signature: str
    source_ordinal: int
    source_sequence: int
    source_observed_at_unix_ms: int
    pool_base_reserve_raw: int
    pool_quote_reserve_raw: int
    virtual_quote_reserve_raw: int
    base_decimals: int
    quote_decimals: int

    def __post_init__(self) -> None:
        _require_canonical_text("reserve source_signature", self.source_signature)
        _require_non_negative_int("reserve source_ordinal", self.source_ordinal)
        _require_positive_int("reserve source_sequence", self.source_sequence)
        _require_non_negative_int(
            "reserve source_observed_at_unix_ms", self.source_observed_at_unix_ms
        )
        _require_positive_int("pool_base_reserve_raw", self.pool_base_reserve_raw)
        _require_positive_int("pool_quote_reserve_raw", self.pool_quote_reserve_raw)
        if isinstance(self.virtual_quote_reserve_raw, bool) or not isinstance(
            self.virtual_quote_reserve_raw, int
        ):
            raise ValueError("virtual_quote_reserve_raw must be an integer")
        _require_u8("base_decimals", self.base_decimals)
        _require_u8("quote_decimals", self.quote_decimals)


@dataclass(frozen=True, slots=True)
class FastTrainingEconomicsEntryProjection:
    base_quantity_raw: int
    quote_input_raw: int
    base_quantity: float
    quote_input: float
    average_price_quote: float

    def __post_init__(self) -> None:
        _require_positive_int("entry base_quantity_raw", self.base_quantity_raw)
        _require_positive_int("entry quote_input_raw", self.quote_input_raw)
        _require_positive_finite("entry base_quantity", self.base_quantity)
        _require_positive_finite("entry quote_input", self.quote_input)
        _require_positive_finite("entry average_price_quote", self.average_price_quote)


@dataclass(frozen=True, slots=True)
class FastTrainingEconomicsExitProjection:
    base_quantity_raw: int
    quote_output_raw: int
    base_quantity: float
    quote_output: float
    average_price_quote: float

    def __post_init__(self) -> None:
        _require_positive_int("exit base_quantity_raw", self.base_quantity_raw)
        _require_positive_int("exit quote_output_raw", self.quote_output_raw)
        _require_positive_finite("exit base_quantity", self.base_quantity)
        _require_positive_finite("exit quote_output", self.quote_output)
        _require_positive_finite("exit average_price_quote", self.average_price_quote)


@dataclass(frozen=True, slots=True)
class FastTrainingEconomicsFeeProvenance:
    source_signature: str
    source_ordinal: int
    source_sequence: int
    source_observed_at_unix_ms: int
    age_ms: int
    market_quote_amount_raw: int
    user_quote_amount_raw: int
    signed_user_cost_quote_raw: int
    effective_fee_bps: int | None

    def __post_init__(self) -> None:
        _require_canonical_text("fee source_signature", self.source_signature)
        _require_non_negative_int("fee source_ordinal", self.source_ordinal)
        _require_positive_int("fee source_sequence", self.source_sequence)
        _require_non_negative_int(
            "fee source_observed_at_unix_ms", self.source_observed_at_unix_ms
        )
        _require_non_negative_int("fee age_ms", self.age_ms)
        _require_positive_int("fee market_quote_amount_raw", self.market_quote_amount_raw)
        _require_non_negative_int("fee user_quote_amount_raw", self.user_quote_amount_raw)
        if isinstance(self.signed_user_cost_quote_raw, bool) or not isinstance(
            self.signed_user_cost_quote_raw, int
        ):
            raise ValueError("signed_user_cost_quote_raw must be an integer")
        if self.signed_user_cost_quote_raw < 0:
            raise ValueError(
                "attached fee provenance cannot contain a negative user-cost delta"
            )

        bps_numerator = self.signed_user_cost_quote_raw * 10_000
        exact_bps, remainder = divmod(
            bps_numerator,
            self.market_quote_amount_raw,
        )
        if remainder == 0:
            if self.effective_fee_bps is None:
                raise ValueError(
                    "exact integer-bps fee ratio requires effective_fee_bps"
                )
            _require_non_negative_int(
                "effective_fee_bps",
                self.effective_fee_bps,
            )
            if self.effective_fee_bps != exact_bps:
                raise ValueError(
                    "effective_fee_bps contradicts exact raw fee ratio"
                )
        elif self.effective_fee_bps is not None:
            raise ValueError(
                "non-integral raw fee ratio must not carry effective_fee_bps"
            )


@dataclass(frozen=True, slots=True)
class FastTrainingEconomicsOverlayRow:
    decision_signature: str
    decision_ordinal: int
    decision_sequence: int
    decision_observed_at_unix_ms: int
    mint: str
    quote_mint: str
    venue: str
    horizon_ms: int
    future_path_label_version: int
    counterfactual_base_quantity: str
    endpoint_signature: str | None
    endpoint_ordinal: int | None
    endpoint_sequence: int | None
    endpoint_observed_at_unix_ms: int | None
    status: FastTrainingEconomicsStatus
    requested_base_quantity_raw: int | None
    entry_reserve: FastTrainingEconomicsReserveProvenance | None
    exit_reserve: FastTrainingEconomicsReserveProvenance | None
    entry_projection: FastTrainingEconomicsEntryProjection | None
    exit_projection: FastTrainingEconomicsExitProjection | None
    entry_fee: FastTrainingEconomicsFeeProvenance | None
    exit_fee: FastTrainingEconomicsFeeProvenance | None

    def __post_init__(self) -> None:
        _require_canonical_text("decision_signature", self.decision_signature)
        _require_non_negative_int("decision_ordinal", self.decision_ordinal)
        _require_positive_int("decision_sequence", self.decision_sequence)
        _require_non_negative_int(
            "decision_observed_at_unix_ms", self.decision_observed_at_unix_ms
        )
        _require_canonical_text("mint", self.mint)
        _require_canonical_text("quote_mint", self.quote_mint)
        _require_canonical_text("venue", self.venue)
        _require_positive_int("horizon_ms", self.horizon_ms)
        _require_positive_int(
            "future_path_label_version", self.future_path_label_version
        )
        if (
            _canonical_decimal_string(self.counterfactual_base_quantity)
            != self.counterfactual_base_quantity
        ):
            raise ValueError(
                "counterfactual_base_quantity must use canonical positive decimal text"
            )
        if not isinstance(self.status, FastTrainingEconomicsStatus):
            raise ValueError("status must be a FastTrainingEconomicsStatus")

        endpoint_presence = (
            self.endpoint_signature is not None,
            self.endpoint_ordinal is not None,
            self.endpoint_sequence is not None,
            self.endpoint_observed_at_unix_ms is not None,
        )
        if len(set(endpoint_presence)) != 1:
            raise ValueError("endpoint identity fields must be all present or all absent")
        if self.endpoint_signature is not None:
            _require_canonical_text("endpoint_signature", self.endpoint_signature)
            _require_non_negative_int("endpoint_ordinal", self.endpoint_ordinal)
            _require_positive_int("endpoint_sequence", self.endpoint_sequence)
            _require_non_negative_int(
                "endpoint_observed_at_unix_ms",
                self.endpoint_observed_at_unix_ms,
            )
            if self.endpoint_sequence <= self.decision_sequence:
                raise ValueError("endpoint_sequence must be after decision_sequence")
            if not (
                self.decision_observed_at_unix_ms
                < self.endpoint_observed_at_unix_ms
                <= self.decision_observed_at_unix_ms + self.horizon_ms
            ):
                raise ValueError("endpoint timestamp must be within the FL4 horizon")

        if self.requested_base_quantity_raw is not None:
            _require_positive_int(
                "requested_base_quantity_raw", self.requested_base_quantity_raw
            )
        _require_optional_exact_type(
            "entry_reserve",
            self.entry_reserve,
            FastTrainingEconomicsReserveProvenance,
        )
        _require_optional_exact_type(
            "exit_reserve",
            self.exit_reserve,
            FastTrainingEconomicsReserveProvenance,
        )
        _require_optional_exact_type(
            "entry_projection",
            self.entry_projection,
            FastTrainingEconomicsEntryProjection,
        )
        _require_optional_exact_type(
            "exit_projection",
            self.exit_projection,
            FastTrainingEconomicsExitProjection,
        )
        _require_optional_exact_type(
            "entry_fee", self.entry_fee, FastTrainingEconomicsFeeProvenance
        )
        _require_optional_exact_type(
            "exit_fee", self.exit_fee, FastTrainingEconomicsFeeProvenance
        )
        self._validate_evidence_shape()
        self._validate_provenance()

    def _validate_evidence_shape(self) -> None:
        evidence = (
            self.requested_base_quantity_raw is not None,
            self.entry_reserve is not None,
            self.exit_reserve is not None,
            self.entry_projection is not None,
            self.exit_projection is not None,
            self.entry_fee is not None,
            self.exit_fee is not None,
        )
        expected: tuple[bool, ...]
        if self.status is FastTrainingEconomicsStatus.UNSUPPORTED_VENUE:
            if self.venue == "pump_swap":
                raise ValueError("unsupported_venue cannot claim PumpSwap")
            expected = (False, False, False, False, False, False, False)
        else:
            if self.venue != "pump_swap":
                raise ValueError("supported training economics rows must be PumpSwap")
            if self.status is FastTrainingEconomicsStatus.NO_ENDPOINT:
                if self.endpoint_signature is not None:
                    raise ValueError("no_endpoint row cannot contain an endpoint")
                expected = (False, False, False, False, False, False, False)
            else:
                if self.endpoint_signature is None:
                    raise ValueError("PumpSwap evidence status requires an endpoint")
                if self.status is FastTrainingEconomicsStatus.ENTRY_RESERVE_UNAVAILABLE:
                    expected = (True, False, False, False, False, False, False)
                elif self.status is FastTrainingEconomicsStatus.EXIT_RESERVE_UNAVAILABLE:
                    expected = (True, True, False, False, False, False, False)
                elif self.status is FastTrainingEconomicsStatus.ENTRY_PROJECTION_UNAVAILABLE:
                    expected = (True, True, True, False, False, False, False)
                elif self.status is FastTrainingEconomicsStatus.EXIT_PROJECTION_UNAVAILABLE:
                    expected = (True, True, True, True, False, False, False)
                elif self.status in {
                    FastTrainingEconomicsStatus.ENTRY_FEE_MISSING,
                    FastTrainingEconomicsStatus.ENTRY_FEE_STALE,
                    FastTrainingEconomicsStatus.ENTRY_FEE_RATE_UNKNOWN,
                }:
                    expected = (True, True, True, True, True, False, False)
                elif self.status in {
                    FastTrainingEconomicsStatus.EXIT_FEE_MISSING,
                    FastTrainingEconomicsStatus.EXIT_FEE_STALE,
                    FastTrainingEconomicsStatus.EXIT_FEE_RATE_UNKNOWN,
                }:
                    expected = (True, True, True, True, True, True, False)
                elif self.status is FastTrainingEconomicsStatus.AVAILABLE:
                    expected = (True, True, True, True, True, True, True)
                else:
                    raise ValueError("training economics status is unsupported")
        if evidence != expected:
            raise ValueError(
                f"training economics evidence shape contradicts status {self.status.value}"
            )

    def _validate_provenance(self) -> None:
        if self.entry_reserve is not None:
            if (
                self.entry_reserve.source_signature != self.decision_signature
                or self.entry_reserve.source_ordinal != self.decision_ordinal
                or self.entry_reserve.source_sequence != self.decision_sequence
                or self.entry_reserve.source_observed_at_unix_ms
                > self.decision_observed_at_unix_ms
            ):
                raise ValueError("entry reserve provenance contradicts decision identity")
        if self.exit_reserve is not None:
            if (
                self.exit_reserve.source_signature != self.endpoint_signature
                or self.exit_reserve.source_ordinal != self.endpoint_ordinal
                or self.exit_reserve.source_sequence != self.endpoint_sequence
                or self.exit_reserve.source_observed_at_unix_ms
                > self.endpoint_observed_at_unix_ms
            ):
                raise ValueError("exit reserve provenance contradicts endpoint identity")

        if self.entry_projection is not None:
            if self.entry_projection.base_quantity_raw != self.requested_base_quantity_raw:
                raise ValueError("entry projection raw quantity contradicts requested quantity")
        if self.exit_projection is not None:
            if self.exit_projection.base_quantity_raw != self.requested_base_quantity_raw:
                raise ValueError("exit projection raw quantity contradicts requested quantity")

        if self.entry_fee is not None:
            if (
                self.entry_fee.source_sequence > self.decision_sequence
                or self.entry_fee.source_observed_at_unix_ms
                > self.decision_observed_at_unix_ms
                or self.entry_fee.age_ms
                != self.decision_observed_at_unix_ms
                - self.entry_fee.source_observed_at_unix_ms
            ):
                raise ValueError("entry fee provenance is not causal at the decision")
        if self.exit_fee is not None:
            if self.endpoint_sequence is None or self.endpoint_observed_at_unix_ms is None:
                raise ValueError("exit fee provenance requires endpoint identity")
            if (
                self.exit_fee.source_sequence > self.endpoint_sequence
                or self.exit_fee.source_observed_at_unix_ms
                > self.endpoint_observed_at_unix_ms
                or self.exit_fee.age_ms
                != self.endpoint_observed_at_unix_ms
                - self.exit_fee.source_observed_at_unix_ms
            ):
                raise ValueError("exit fee provenance is not causal at the endpoint")


@dataclass(frozen=True, slots=True)
class FastTrainingEconomicsOverlayManifest:
    schema_name: str
    schema_version: int
    row_count: int
    available_row_count: int
    status_counts: dict[str, int]
    feature_source_jsonl_sha256: str
    future_path_logical_fingerprint_sha256: str
    future_path_label_version: int
    counterfactual_base_quantity: str
    pump_swap_fee_maximum_age_ms: int
    min_decision_observed_at_unix_ms: int
    max_decision_observed_at_unix_ms: int
    ordered_row_logical_fingerprint_sha256: str
    manifest_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME:
            raise ValueError("training economics overlay schema name is incompatible")
        if self.schema_version != FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION:
            raise ValueError("training economics overlay schema version is incompatible")
        _require_positive_int("row_count", self.row_count)
        _require_non_negative_int("available_row_count", self.available_row_count)
        if self.available_row_count > self.row_count:
            raise ValueError("available_row_count cannot exceed row_count")
        if type(self.status_counts) is not dict or not self.status_counts:
            raise ValueError("status_counts must be a non-empty exact dict")
        normalized_counts: dict[str, int] = {}
        allowed = {status.value for status in FastTrainingEconomicsStatus}
        for key, value in self.status_counts.items():
            if key not in allowed:
                raise ValueError("status_counts contains an unknown status")
            _require_positive_int(f"status_counts[{key}]", value)
            normalized_counts[key] = value
        if sum(normalized_counts.values()) != self.row_count:
            raise ValueError("status_counts must sum exactly to row_count")
        if normalized_counts.get(FastTrainingEconomicsStatus.AVAILABLE.value, 0) != (
            self.available_row_count
        ):
            raise ValueError("available_row_count contradicts status_counts")
        object.__setattr__(self, "status_counts", dict(sorted(normalized_counts.items())))

        _require_sha256(
            "feature_source_jsonl_sha256", self.feature_source_jsonl_sha256
        )
        _require_sha256(
            "future_path_logical_fingerprint_sha256",
            self.future_path_logical_fingerprint_sha256,
        )
        _require_positive_int(
            "future_path_label_version", self.future_path_label_version
        )
        if (
            _canonical_decimal_string(self.counterfactual_base_quantity)
            != self.counterfactual_base_quantity
        ):
            raise ValueError(
                "manifest counterfactual_base_quantity must be canonical positive decimal text"
            )
        _require_non_negative_int(
            "pump_swap_fee_maximum_age_ms", self.pump_swap_fee_maximum_age_ms
        )
        _require_non_negative_int(
            "min_decision_observed_at_unix_ms",
            self.min_decision_observed_at_unix_ms,
        )
        _require_non_negative_int(
            "max_decision_observed_at_unix_ms",
            self.max_decision_observed_at_unix_ms,
        )
        if (
            self.min_decision_observed_at_unix_ms
            > self.max_decision_observed_at_unix_ms
        ):
            raise ValueError("manifest decision timestamp range is incompatible")
        _require_sha256(
            "ordered_row_logical_fingerprint_sha256",
            self.ordered_row_logical_fingerprint_sha256,
        )
        _require_sha256(
            "manifest_fingerprint_sha256", self.manifest_fingerprint_sha256
        )


@dataclass(frozen=True, slots=True)
class FastTrainingEconomicsOverlayDataset:
    manifest: FastTrainingEconomicsOverlayManifest
    rows: tuple[FastTrainingEconomicsOverlayRow, ...]

    def __post_init__(self) -> None:
        if type(self.manifest) is not FastTrainingEconomicsOverlayManifest:
            raise ValueError("manifest must be an exact training economics manifest")
        if (
            not isinstance(self.rows, tuple)
            or not self.rows
            or not all(type(row) is FastTrainingEconomicsOverlayRow for row in self.rows)
        ):
            raise ValueError("rows must be a non-empty tuple of exact overlay rows")


_POLICY_KEYS = frozenset(field.name for field in fields(FastTrainingExecutionCostPolicy))
_MANIFEST_KEYS = frozenset(
    field.name for field in fields(FastTrainingEconomicsOverlayManifest)
)
_ROW_KEYS = frozenset(field.name for field in fields(FastTrainingEconomicsOverlayRow))
_RESERVE_KEYS = frozenset(
    field.name for field in fields(FastTrainingEconomicsReserveProvenance)
)
_ENTRY_PROJECTION_KEYS = frozenset(
    field.name for field in fields(FastTrainingEconomicsEntryProjection)
)
_EXIT_PROJECTION_KEYS = frozenset(
    field.name for field in fields(FastTrainingEconomicsExitProjection)
)
_FEE_KEYS = frozenset(
    field.name for field in fields(FastTrainingEconomicsFeeProvenance)
)


def encode_fast_training_execution_cost_policy(
    policy: FastTrainingExecutionCostPolicy,
) -> str:
    if type(policy) is not FastTrainingExecutionCostPolicy:
        raise ValueError("policy must be an exact FastTrainingExecutionCostPolicy")
    return json.dumps(
        asdict(policy),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def decode_fast_training_execution_cost_policy(
    payload: str,
) -> FastTrainingExecutionCostPolicy:
    mapping = _load_json_object(payload, "training execution cost policy")
    _require_exact_keys(mapping, _POLICY_KEYS, "training execution cost policy")
    return FastTrainingExecutionCostPolicy(**mapping)


def fast_training_execution_cost_policy_fingerprint_sha256(
    policy: FastTrainingExecutionCostPolicy,
) -> str:
    encoded = encode_fast_training_execution_cost_policy(policy).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_fast_training_economics_overlay(
    path: str | Path,
) -> FastTrainingEconomicsOverlayDataset:
    source = Path(path)
    if not source.is_dir():
        raise ValueError("training economics overlay path must be an existing directory")
    names = {entry.name for entry in source.iterdir()}
    if names != {_ROWS_FILENAME, _MANIFEST_FILENAME}:
        raise ValueError("training economics overlay file set is incompatible")

    manifest_path = source / _MANIFEST_FILENAME
    manifest_mapping = _load_json_object(
        manifest_path.read_text(encoding="utf-8"),
        "training economics overlay manifest",
    )
    _require_exact_keys(
        manifest_mapping, _MANIFEST_KEYS, "training economics overlay manifest"
    )
    provided_manifest_fingerprint = manifest_mapping.get(
        "manifest_fingerprint_sha256"
    )
    if not isinstance(provided_manifest_fingerprint, str):
        raise ValueError("training economics manifest fingerprint is incompatible")
    fingerprint_payload = dict(manifest_mapping)
    fingerprint_payload.pop("manifest_fingerprint_sha256")
    expected_manifest_fingerprint = hashlib.sha256(
        _canonical_json_bytes(fingerprint_payload)
    ).hexdigest()
    if provided_manifest_fingerprint != expected_manifest_fingerprint:
        raise ValueError("training economics manifest fingerprint is invalid")

    manifest = FastTrainingEconomicsOverlayManifest(**manifest_mapping)

    rows_path = source / _ROWS_FILENAME
    raw_rows = rows_path.read_bytes()
    if not raw_rows or not raw_rows.endswith(b"\n"):
        raise ValueError("training economics rows JSONL must be non-empty and newline terminated")
    if (
        hashlib.sha256(raw_rows).hexdigest()
        != manifest.ordered_row_logical_fingerprint_sha256
    ):
        raise ValueError("training economics row fingerprint is invalid")

    rows: list[FastTrainingEconomicsOverlayRow] = []
    seen: set[tuple[object, ...]] = set()
    previous_sort: tuple[object, ...] | None = None
    for line_number, line in enumerate(raw_rows.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"training economics row {line_number} is blank")
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"training economics row {line_number} is not UTF-8"
            ) from exc
        mapping = _load_json_object(
            text, f"training economics overlay row {line_number}"
        )
        row = _row_from_mapping(mapping)
        key = (
            row.decision_signature,
            row.decision_ordinal,
            row.horizon_ms,
            row.future_path_label_version,
        )
        if key in seen:
            raise ValueError("training economics overlay contains a duplicate row identity")
        seen.add(key)
        sort_key = (
            row.decision_sequence,
            row.horizon_ms,
            row.decision_signature,
            row.decision_ordinal,
            row.future_path_label_version,
        )
        if previous_sort is not None and sort_key < previous_sort:
            raise ValueError("training economics overlay rows are not in canonical order")
        previous_sort = sort_key
        if row.future_path_label_version != manifest.future_path_label_version:
            raise ValueError("training economics row label version contradicts manifest")
        if row.counterfactual_base_quantity != manifest.counterfactual_base_quantity:
            raise ValueError(
                "training economics row counterfactual quantity contradicts manifest"
            )
        rows.append(row)

    if len(rows) != manifest.row_count:
        raise ValueError("training economics row count contradicts manifest")
    actual_counts = Counter(row.status.value for row in rows)
    if dict(sorted(actual_counts.items())) != manifest.status_counts:
        raise ValueError("training economics status counts contradict rows")
    if actual_counts.get(FastTrainingEconomicsStatus.AVAILABLE.value, 0) != (
        manifest.available_row_count
    ):
        raise ValueError("training economics available row count contradicts rows")
    decision_times = [row.decision_observed_at_unix_ms for row in rows]
    if min(decision_times) != manifest.min_decision_observed_at_unix_ms:
        raise ValueError("training economics minimum decision timestamp contradicts rows")
    if max(decision_times) != manifest.max_decision_observed_at_unix_ms:
        raise ValueError("training economics maximum decision timestamp contradicts rows")

    return FastTrainingEconomicsOverlayDataset(
        manifest=manifest,
        rows=tuple(rows),
    )


def build_entry_counterfactual_context_from_training_economics(
    row: FastTrainingEconomicsOverlayRow,
    *,
    policy: FastTrainingExecutionCostPolicy,
    overlay_manifest_fingerprint_sha256: str,
    base_quantity: float,
    horizon_complete: bool,
) -> EntryCounterfactualContext:
    if type(row) is not FastTrainingEconomicsOverlayRow:
        raise ValueError("row must be an exact FastTrainingEconomicsOverlayRow")
    if type(policy) is not FastTrainingExecutionCostPolicy:
        raise ValueError("policy must be an exact FastTrainingExecutionCostPolicy")
    _require_sha256(
        "overlay_manifest_fingerprint_sha256",
        overlay_manifest_fingerprint_sha256,
    )
    _require_positive_finite("base_quantity", base_quantity)
    if not isinstance(horizon_complete, bool):
        raise ValueError("horizon_complete must be bool")
    if Decimal(str(base_quantity)) != Decimal(row.counterfactual_base_quantity):
        raise ValueError("requested base quantity contradicts training economics overlay")

    decision_id = (
        f"{row.decision_signature}:{row.decision_ordinal}:"
        f"h{row.horizon_ms}:v{row.future_path_label_version}"
    )
    if row.status is not FastTrainingEconomicsStatus.AVAILABLE:
        return EntryCounterfactualContext(
            decision_id=decision_id,
            mint=row.mint,
            quote_mint=row.quote_mint,
            decision_observed_at_unix_ms=row.decision_observed_at_unix_ms,
            base_quantity=base_quantity,
            horizon_ms=row.horizon_ms,
            horizon_complete=horizon_complete,
            buy_now=None,
            exit_at_horizon=None,
            delayed_entries=(),
        )

    if not horizon_complete:
        raise ValueError("available training economics row requires a complete FL4 horizon")
    entry_projection = row.entry_projection
    exit_projection = row.exit_projection
    entry_fee = row.entry_fee
    exit_fee = row.exit_fee
    if (
        entry_projection is None
        or exit_projection is None
        or entry_fee is None
        or exit_fee is None
        or row.endpoint_signature is None
        or row.endpoint_ordinal is None
        or row.endpoint_observed_at_unix_ms is None
    ):
        raise ValueError("available training economics row is incomplete")
    if entry_projection.base_quantity != base_quantity:
        raise ValueError("entry projection base quantity contradicts requested quantity")
    if exit_projection.base_quantity != base_quantity:
        raise ValueError("exit projection base quantity contradicts requested quantity")

    if row.entry_reserve is None or row.exit_reserve is None:
        raise ValueError("available training economics row requires reserve provenance")

    entry_source_rate = Fraction(
        entry_fee.signed_user_cost_quote_raw,
        entry_fee.market_quote_amount_raw,
    )
    exit_source_rate = Fraction(
        exit_fee.signed_user_cost_quote_raw,
        exit_fee.market_quote_amount_raw,
    )
    entry_policy_rate = Fraction(
        policy.additional_entry_slippage_bps + policy.entry_latency_bps,
        10_000,
    )
    exit_policy_rate = Fraction(
        policy.additional_exit_slippage_bps + policy.exit_latency_bps,
        10_000,
    )
    entry_variable_rate = entry_source_rate + entry_policy_rate
    exit_variable_rate = exit_source_rate + exit_policy_rate
    if exit_variable_rate >= 1:
        raise ValueError("exit variable cost rate must remain below 100 percent")

    entry_gross_quote = Fraction(
        entry_projection.quote_input_raw,
        10 ** row.entry_reserve.quote_decimals,
    )
    exit_gross_quote = Fraction(
        exit_projection.quote_output_raw,
        10 ** row.exit_reserve.quote_decimals,
    )
    entry_fixed_quote = sum(
        (
            Fraction(str(policy.entry_network_fee_quote)),
            Fraction(str(policy.entry_priority_fee_quote)),
            Fraction(str(policy.entry_expected_failure_cost_quote)),
        ),
        Fraction(0),
    )
    exit_fixed_quote = sum(
        (
            Fraction(str(policy.exit_network_fee_quote)),
            Fraction(str(policy.exit_priority_fee_quote)),
            Fraction(str(policy.exit_expected_failure_cost_quote)),
        ),
        Fraction(0),
    )
    entry_total_quote_fraction = (
        entry_gross_quote * (1 + entry_variable_rate) + entry_fixed_quote
    )
    exit_net_quote_fraction = (
        exit_gross_quote * (1 - exit_variable_rate) - exit_fixed_quote
    )
    entry_total_quote = float(entry_total_quote_fraction)
    exit_net_quote = float(exit_net_quote_fraction)
    _require_positive_finite("entry_total_quote", entry_total_quote)
    _require_positive_finite("exit_net_quote", exit_net_quote)

    policy_fingerprint = fast_training_execution_cost_policy_fingerprint_sha256(policy)
    evidence_version = (
        f"{FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME}:"
        f"v{FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION}:"
        f"manifest={overlay_manifest_fingerprint_sha256}:"
        f"policy={policy.version}:{policy_fingerprint}"
    )
    buy_evidence = ExecutableTradeEvidence(
        evidence_id=_evidence_id(
            evidence_version,
            "entry",
            row.decision_signature,
            row.decision_ordinal,
            row.horizon_ms,
            row.future_path_label_version,
        ),
        source_event_signature=row.decision_signature,
        source_event_ordinal=row.decision_ordinal,
        observed_at_unix_ms=row.decision_observed_at_unix_ms,
        side=TradeSide.BUY,
        base_quantity=base_quantity,
        status=ExecutionStatus.EXECUTABLE,
        quote_amount=entry_total_quote,
        evidence_version=evidence_version,
    )
    exit_evidence = ExecutableTradeEvidence(
        evidence_id=_evidence_id(
            evidence_version,
            "exit",
            row.endpoint_signature,
            row.endpoint_ordinal,
            row.horizon_ms,
            row.future_path_label_version,
        ),
        source_event_signature=row.endpoint_signature,
        source_event_ordinal=row.endpoint_ordinal,
        observed_at_unix_ms=row.endpoint_observed_at_unix_ms,
        side=TradeSide.SELL,
        base_quantity=base_quantity,
        status=ExecutionStatus.EXECUTABLE,
        quote_amount=exit_net_quote,
        evidence_version=evidence_version,
    )
    return EntryCounterfactualContext(
        decision_id=decision_id,
        mint=row.mint,
        quote_mint=row.quote_mint,
        decision_observed_at_unix_ms=row.decision_observed_at_unix_ms,
        base_quantity=base_quantity,
        horizon_ms=row.horizon_ms,
        horizon_complete=True,
        buy_now=buy_evidence,
        exit_at_horizon=exit_evidence,
        delayed_entries=(),
    )


def _row_from_mapping(mapping: dict[str, object]) -> FastTrainingEconomicsOverlayRow:
    _require_exact_keys(mapping, _ROW_KEYS, "training economics overlay row")
    status_value = mapping["status"]
    if not isinstance(status_value, str):
        raise ValueError("training economics row status must be text")
    try:
        status = FastTrainingEconomicsStatus(status_value)
    except ValueError as exc:
        raise ValueError("training economics row status is unknown") from exc

    return FastTrainingEconomicsOverlayRow(
        decision_signature=mapping["decision_signature"],
        decision_ordinal=mapping["decision_ordinal"],
        decision_sequence=mapping["decision_sequence"],
        decision_observed_at_unix_ms=mapping["decision_observed_at_unix_ms"],
        mint=mapping["mint"],
        quote_mint=mapping["quote_mint"],
        venue=mapping["venue"],
        horizon_ms=mapping["horizon_ms"],
        future_path_label_version=mapping["future_path_label_version"],
        counterfactual_base_quantity=mapping["counterfactual_base_quantity"],
        endpoint_signature=mapping["endpoint_signature"],
        endpoint_ordinal=mapping["endpoint_ordinal"],
        endpoint_sequence=mapping["endpoint_sequence"],
        endpoint_observed_at_unix_ms=mapping["endpoint_observed_at_unix_ms"],
        status=status,
        requested_base_quantity_raw=mapping["requested_base_quantity_raw"],
        entry_reserve=_optional_dataclass(
            mapping["entry_reserve"],
            FastTrainingEconomicsReserveProvenance,
            _RESERVE_KEYS,
            "entry_reserve",
        ),
        exit_reserve=_optional_dataclass(
            mapping["exit_reserve"],
            FastTrainingEconomicsReserveProvenance,
            _RESERVE_KEYS,
            "exit_reserve",
        ),
        entry_projection=_optional_dataclass(
            mapping["entry_projection"],
            FastTrainingEconomicsEntryProjection,
            _ENTRY_PROJECTION_KEYS,
            "entry_projection",
        ),
        exit_projection=_optional_dataclass(
            mapping["exit_projection"],
            FastTrainingEconomicsExitProjection,
            _EXIT_PROJECTION_KEYS,
            "exit_projection",
        ),
        entry_fee=_optional_dataclass(
            mapping["entry_fee"],
            FastTrainingEconomicsFeeProvenance,
            _FEE_KEYS,
            "entry_fee",
        ),
        exit_fee=_optional_dataclass(
            mapping["exit_fee"],
            FastTrainingEconomicsFeeProvenance,
            _FEE_KEYS,
            "exit_fee",
        ),
    )


def _optional_dataclass(
    value: object,
    cls,
    expected_keys: frozenset[str],
    label: str,
):
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object or null")
    _require_exact_keys(value, expected_keys, label)
    return cls(**value)


def _load_json_object(payload: str, label: str) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty JSON text")

    def _reject_constant(value: str):
        raise ValueError(f"{label} contains non-finite JSON number {value}")

    try:
        value = json.loads(payload, parse_constant=_reject_constant)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    return value


def _require_exact_keys(
    mapping: dict[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    if frozenset(mapping) != expected:
        raise ValueError(f"{label} keys are incompatible")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_decimal_string(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("decimal value must be canonical non-empty text")
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("decimal value is invalid") from exc
    if not decimal.is_finite() or decimal <= 0:
        raise ValueError("decimal value must be finite and positive")
    normalized = format(decimal, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized.startswith("."):
        normalized = f"0{normalized}"
    return normalized


def _evidence_id(
    evidence_version: str,
    leg: str,
    signature: str,
    ordinal: int,
    horizon_ms: int,
    label_version: int,
) -> str:
    payload = (
        f"{evidence_version}|{leg}|{signature}|{ordinal}|"
        f"{horizon_ms}|{label_version}"
    ).encode("utf-8")
    return f"training-economics-{leg}:{hashlib.sha256(payload).hexdigest()}"


def _require_optional_exact_type(name: str, value: object, expected_type: type) -> None:
    if value is not None and type(value) is not expected_type:
        raise ValueError(f"{name} must be an exact {expected_type.__name__} or None")


def _require_canonical_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-blank canonical text")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_u8(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value > 255:
        raise ValueError(f"{name} must fit u8")


def _require_positive_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be a positive finite number")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
