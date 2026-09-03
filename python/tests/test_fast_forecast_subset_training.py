from __future__ import annotations

import pytest

from fast_forecast_fixtures import training_bundle
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
    train_fast_forecast_baseline,
)
from shreks_brain.fast_learning.trainer import (
    train_fast_forecast_baseline_for_decision_identities,
)


def request() -> FastForecastTrainingRequest:
    return FastForecastTrainingRequest(
        model_version="subset-ridge-h250",
        model_family=FastForecastModelFamily.RIDGE_REGRESSION,
        target=FastForecastTarget.ENDPOINT_RETURN_BPS,
        horizon_ms=250,
        training_policy=FastForecastTrainingPolicy(version="ridge-v1", ridge_alpha=1.0),
    )


def test_subset_training_uses_only_requested_decision_identities() -> None:
    bundle = training_bundle()
    identities = tuple(record.decision_identity for record in bundle.features.records[:4])
    model = train_fast_forecast_baseline_for_decision_identities(bundle, request(), identities)
    assert model.training_row_count == 4
    assert model.target_unavailable_row_count == 0
    assert model.min_training_decision_observed_at_unix_ms == 1_000
    assert model.max_training_decision_observed_at_unix_ms == 1_300


def test_subset_training_fingerprint_changes_with_identity_subset() -> None:
    bundle = training_bundle()
    first = tuple(record.decision_identity for record in bundle.features.records[:4])
    second = tuple(record.decision_identity for record in bundle.features.records[1:5])
    first_model = train_fast_forecast_baseline_for_decision_identities(bundle, request(), first)
    second_model = train_fast_forecast_baseline_for_decision_identities(bundle, request(), second)
    assert first_model.training_bundle_fingerprint_sha256 == second_model.training_bundle_fingerprint_sha256
    assert first_model.training_data_fingerprint_sha256 != second_model.training_data_fingerprint_sha256
    assert first_model.artifact_fingerprint_sha256 != second_model.artifact_fingerprint_sha256


def test_subset_training_rejects_empty_duplicate_and_unknown_identities() -> None:
    bundle = training_bundle()
    identity = bundle.features.records[0].decision_identity
    with pytest.raises(ValueError, match="non-empty|identity"):
        train_fast_forecast_baseline_for_decision_identities(bundle, request(), ())
    with pytest.raises(ValueError, match="duplicate|identity"):
        train_fast_forecast_baseline_for_decision_identities(bundle, request(), (identity, identity))
    unknown = ("missing", 0, 999, "mint", "quote", "venue", 999)
    with pytest.raises(ValueError, match="unknown|identity|feature"):
        train_fast_forecast_baseline_for_decision_identities(bundle, request(), (unknown,))


def test_existing_full_bundle_training_behavior_is_unchanged() -> None:
    bundle = training_bundle()
    full = train_fast_forecast_baseline(bundle, request())
    selected = train_fast_forecast_baseline_for_decision_identities(
        bundle,
        request(),
        tuple(record.decision_identity for record in bundle.features.records),
    )
    assert selected == full
