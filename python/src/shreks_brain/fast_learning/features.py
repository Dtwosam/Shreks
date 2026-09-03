from __future__ import annotations

from dataclasses import dataclass
import math
import statistics

from shreks_brain.research.fast_training_features import (
    DEFAULT_FAST_WINDOWS_MS,
    FastTrainingFeatureRecord,
)


FAST_FORECAST_FEATURE_SCHEMA_VERSION = 1

_WINDOW_NUMERIC_FIELDS = (
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
    "local_low_price_quote",
    "post_high_low_price_quote",
    "last_price_quote",
    "drawdown_from_local_high",
    "recovery_from_local_low",
)

_TOP_LEVEL_FEATURE_NAMES = (
    "decision.executable_entry_price_quote",
    "decision.entry_total_quote",
    "snapshot.last_price_quote",
    "decision.is_buy",
    "decision.is_sell",
    "venue.pump_fun_bonding_curve",
    "venue.pump_swap",
    "decision.actor_present",
    "reserve.present",
    "reserve.is_pump_curve",
    "reserve.is_pump_swap_pool",
    "reserve.virtual_base_reserve_raw",
    "reserve.virtual_quote_reserve_raw",
    "reserve.real_base_reserve_raw",
    "reserve.real_quote_reserve_raw",
    "reserve.pool_base_reserve_raw",
    "reserve.pool_quote_reserve_raw",
    "reserve.base_decimals",
    "reserve.quote_decimals",
    "lifecycle.present",
    "lifecycle.detected_age_ms",
    "lifecycle.occurred_age_ms",
)

FAST_FORECAST_FEATURE_NAMES = _TOP_LEVEL_FEATURE_NAMES + tuple(
    f"w{window_ms}.{field_name}"
    for window_ms in DEFAULT_FAST_WINDOWS_MS
    for field_name in _WINDOW_NUMERIC_FIELDS
)


@dataclass(frozen=True, slots=True)
class FastForecastFeatureTransform:
    feature_name: str
    imputation_median: float
    mean: float
    scale: float

    def __post_init__(self) -> None:
        if not isinstance(self.feature_name, str) or not self.feature_name.strip():
            raise ValueError("feature_name must be a non-empty string")
        _require_finite("imputation_median", self.imputation_median)
        _require_finite("mean", self.mean)
        _require_finite("scale", self.scale)
        if self.scale <= 0.0:
            raise ValueError("scale must be positive")


def extract_fast_forecast_features(
    record: FastTrainingFeatureRecord,
) -> tuple[float | None, ...]:
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be an exact FastTrainingFeatureRecord")
    if record.decision_event_kind not in {"buy", "sell"}:
        raise ValueError("decision event kind is incompatible with the Fast Lane forecast schema")
    if record.venue not in {"pump_fun_bonding_curve", "pump_swap"}:
        raise ValueError("decision venue is incompatible with the Fast Lane forecast schema")
    if tuple(window.window_ms for window in record.windows) != DEFAULT_FAST_WINDOWS_MS:
        raise ValueError("Fast Lane forecast features require the sealed default window order")

    reserve = record.last_reserve_context
    if reserve is not None and reserve.kind not in {"pump_curve", "pump_swap_pool"}:
        raise ValueError("reserve context kind is incompatible with the forecast schema")

    lifecycle = record.last_lifecycle_event
    detected_age: float | None = None
    occurred_age: float | None = None
    if lifecycle is not None:
        if lifecycle.detected_at_unix_ms > record.decision_observed_at_unix_ms:
            raise ValueError("future lifecycle evidence cannot enter forecast features")
        detected_age = float(
            record.decision_observed_at_unix_ms - lifecycle.detected_at_unix_ms
        )
        if lifecycle.occurred_at_unix_ms is not None:
            if lifecycle.occurred_at_unix_ms > record.decision_observed_at_unix_ms:
                raise ValueError("future lifecycle occurrence cannot enter forecast features")
            occurred_age = float(
                record.decision_observed_at_unix_ms - lifecycle.occurred_at_unix_ms
            )

    values: list[float | None] = [
        _optional_finite(
            "decision_executable_entry_price_quote",
            record.decision_executable_entry_price_quote,
        ),
        _optional_finite("decision_entry_total_quote", record.decision_entry_total_quote),
        _optional_finite("snapshot_last_price_quote", record.snapshot_last_price_quote),
        1.0 if record.decision_event_kind == "buy" else 0.0,
        1.0 if record.decision_event_kind == "sell" else 0.0,
        1.0 if record.venue == "pump_fun_bonding_curve" else 0.0,
        1.0 if record.venue == "pump_swap" else 0.0,
        1.0 if record.decision_actor is not None else 0.0,
        1.0 if reserve is not None else 0.0,
        1.0 if reserve is not None and reserve.kind == "pump_curve" else 0.0,
        1.0 if reserve is not None and reserve.kind == "pump_swap_pool" else 0.0,
        _reserve_value(reserve, "virtual_base_reserve_raw"),
        _reserve_value(reserve, "virtual_quote_reserve_raw"),
        _reserve_value(reserve, "real_base_reserve_raw"),
        _reserve_value(reserve, "real_quote_reserve_raw"),
        _reserve_value(reserve, "pool_base_reserve_raw"),
        _reserve_value(reserve, "pool_quote_reserve_raw"),
        _reserve_value(reserve, "base_decimals"),
        _reserve_value(reserve, "quote_decimals"),
        1.0 if lifecycle is not None else 0.0,
        detected_age,
        occurred_age,
    ]

    for window in record.windows:
        for field_name in _WINDOW_NUMERIC_FIELDS:
            raw_value = getattr(window, field_name)
            values.append(_optional_finite(f"w{window.window_ms}.{field_name}", raw_value))

    result = tuple(values)
    if len(result) != len(FAST_FORECAST_FEATURE_NAMES):
        raise ValueError("Fast Lane forecast feature schema length changed unexpectedly")
    return result


def fit_feature_transforms(
    rows: tuple[tuple[float | None, ...], ...],
) -> tuple[FastForecastFeatureTransform, ...]:
    if not isinstance(rows, tuple) or not rows:
        raise ValueError("feature rows must be a non-empty tuple")
    if any(not isinstance(row, tuple) for row in rows):
        raise ValueError("feature rows must contain tuples")
    if any(len(row) != len(FAST_FORECAST_FEATURE_NAMES) for row in rows):
        raise ValueError("feature row length does not match the sealed forecast schema")

    transforms: list[FastForecastFeatureTransform] = []
    for column_index, feature_name in enumerate(FAST_FORECAST_FEATURE_NAMES):
        raw_values = [row[column_index] for row in rows]
        observed: list[float] = []
        for value in raw_values:
            if value is None:
                continue
            observed.append(_finite_scalar(feature_name, value))

        if observed:
            median = float(statistics.median(observed))
            imputed = [
                median if value is None else _finite_scalar(feature_name, value)
                for value in raw_values
            ]
            mean = float(math.fsum(imputed) / len(imputed))
            variance = float(
                math.fsum((value - mean) ** 2 for value in imputed) / len(imputed)
            )
            scale = math.sqrt(variance)
            if scale == 0.0:
                scale = 1.0
        else:
            # An optional feature can be absent from an entire training slice. Keep it
            # neutral rather than inventing variation or dropping the sealed column.
            median = 0.0
            mean = 0.0
            scale = 1.0

        transforms.append(
            FastForecastFeatureTransform(
                feature_name=feature_name,
                imputation_median=median,
                mean=mean,
                scale=scale,
            )
        )
    return tuple(transforms)


def apply_feature_transforms(
    raw: tuple[float | None, ...],
    transforms: tuple[FastForecastFeatureTransform, ...],
) -> tuple[float, ...]:
    if not isinstance(raw, tuple) or len(raw) != len(FAST_FORECAST_FEATURE_NAMES):
        raise ValueError("raw feature vector does not match the sealed forecast schema")
    if not isinstance(transforms, tuple) or len(transforms) != len(
        FAST_FORECAST_FEATURE_NAMES
    ):
        raise ValueError("feature transforms do not match the sealed forecast schema")
    if tuple(value.feature_name for value in transforms) != FAST_FORECAST_FEATURE_NAMES:
        raise ValueError("feature transform order does not match the sealed forecast schema")

    transformed: list[float] = []
    for feature_name, value, transform in zip(
        FAST_FORECAST_FEATURE_NAMES, raw, transforms, strict=True
    ):
        if type(transform) is not FastForecastFeatureTransform:
            raise ValueError("feature transforms must contain exact transform values")
        scalar = (
            transform.imputation_median
            if value is None
            else _finite_scalar(feature_name, value)
        )
        result = (scalar - transform.mean) / transform.scale
        _require_finite(feature_name, result)
        transformed.append(float(result))
    return tuple(transformed)


def _reserve_value(reserve: object, field_name: str) -> float | None:
    if reserve is None:
        return None
    return _optional_finite(f"reserve.{field_name}", getattr(reserve, field_name))


def _optional_finite(name: str, value: object) -> float | None:
    if value is None:
        return None
    return _finite_scalar(name, value)


def _finite_scalar(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite numeric value or None")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
