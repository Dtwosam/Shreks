from __future__ import annotations

from dataclasses import replace

import pytest

from fast_forecast_fixtures import feature_record
from shreks_brain.fast_learning.features import (
    FAST_FORECAST_FEATURE_NAMES,
    FAST_FORECAST_FEATURE_SCHEMA_VERSION,
    apply_feature_transforms,
    extract_fast_forecast_features,
    fit_feature_transforms,
)


def test_fast_forecast_feature_schema_is_stable_point_in_time_and_identity_free() -> None:
    assert FAST_FORECAST_FEATURE_SCHEMA_VERSION == 1
    forbidden = {
        "decision_signature",
        "decision_ordinal",
        "decision_sequence",
        "mint",
        "quote_mint",
        "decision_observed_at_unix_ms",
        "decision_slot",
        "decision_actor",
        "endpoint_return_bps",
        "mfe_bps",
        "mae_bps",
        "best_cost_adjusted_return_bps",
    }
    assert forbidden.isdisjoint(FAST_FORECAST_FEATURE_NAMES)
    assert len(FAST_FORECAST_FEATURE_NAMES) == len(set(FAST_FORECAST_FEATURE_NAMES))
    assert any(name.startswith("w100.") for name in FAST_FORECAST_FEATURE_NAMES)
    assert any(name.startswith("w10000.") for name in FAST_FORECAST_FEATURE_NAMES)


def test_feature_extraction_is_deterministic_and_ignores_identity_fields() -> None:
    original = feature_record(2, 2.5, with_context=True)
    changed_identity = replace(
        original,
        decision_signature="different-signature",
        decision_ordinal=7,
        decision_actor="different-wallet",
        decision_slot=999,
    )
    first = extract_fast_forecast_features(original)
    second = extract_fast_forecast_features(changed_identity)
    assert first == second
    assert len(first) == len(FAST_FORECAST_FEATURE_NAMES)


def test_optional_context_is_none_until_transform_fit_and_lifecycle_ages_are_non_negative() -> None:
    without_context = extract_fast_forecast_features(feature_record(1, 1.0))
    with_context = extract_fast_forecast_features(feature_record(1, 1.0, with_context=True))
    reserve_index = FAST_FORECAST_FEATURE_NAMES.index("reserve.virtual_base_reserve_raw")
    detected_age_index = FAST_FORECAST_FEATURE_NAMES.index("lifecycle.detected_age_ms")
    occurred_age_index = FAST_FORECAST_FEATURE_NAMES.index("lifecycle.occurred_age_ms")
    assert without_context[reserve_index] is None
    assert without_context[detected_age_index] is None
    assert with_context[reserve_index] is not None
    assert with_context[detected_age_index] == pytest.approx(40.0)
    assert with_context[occurred_age_index] == pytest.approx(60.0)


def test_feature_transforms_impute_scale_and_preserve_exact_order() -> None:
    raws = tuple(
        extract_fast_forecast_features(feature_record(index, float(index), with_context=index % 2 == 0))
        for index in range(4)
    )
    transforms = fit_feature_transforms(raws)
    assert tuple(value.feature_name for value in transforms) == FAST_FORECAST_FEATURE_NAMES
    assert all(value.scale > 0.0 for value in transforms)
    transformed = tuple(apply_feature_transforms(raw, transforms) for raw in raws)
    assert all(len(row) == len(FAST_FORECAST_FEATURE_NAMES) for row in transformed)
    assert all(all(isinstance(value, float) for value in row) for row in transformed)


def test_future_or_unknown_context_fails_closed() -> None:
    record = feature_record(1, 1.0, with_context=True)
    assert record.last_lifecycle_event is not None
    future = replace(
        record,
        last_lifecycle_event=replace(
            record.last_lifecycle_event,
            detected_at_unix_ms=record.decision_observed_at_unix_ms + 1,
        ),
    )
    with pytest.raises(ValueError, match="future|lifecycle"):
        extract_fast_forecast_features(future)

    unknown = replace(record, decision_event_kind="unknown")
    with pytest.raises(ValueError, match="event|kind"):
        extract_fast_forecast_features(unknown)
