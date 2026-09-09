from __future__ import annotations

import pytest

from fast_forecast_fixtures import feature_record, future_label

from shreks_brain.fl9_v2_cohort_acceptance import Fl9V2AcceptedDecision
from shreks_brain.fast_first_champion_v2.bundle import (
    _select_exact_features,
    _select_exact_labels,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureDataset,
    feature_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_targets import (
    FuturePathTrainingLabelDataset,
    future_path_logical_fingerprint_sha256,
)


def _accepted(record, *, partition: str = "training"):
    novelty = "not_applicable" if partition == "training" else "unseen"
    return Fl9V2AcceptedDecision(
        decision_identity=record.decision_identity,
        partition=partition,
        assessment_fingerprint_sha256="a" * 64,
        mint_novelty=novelty,
        actor_novelty=novelty,
    )


def _features(*records):
    values = tuple(records)
    return FastTrainingFeatureDataset(
        records=values,
        logical_fingerprint_sha256=feature_logical_fingerprint_sha256(values),
        source_sha256="b" * 64,
    )


def _labels(*labels):
    values = tuple(labels)
    return FuturePathTrainingLabelDataset(
        labels=values,
        logical_fingerprint_sha256=future_path_logical_fingerprint_sha256(values),
        label_version=1,
    )


def test_feature_source_superset_cannot_add_unaccepted_identity() -> None:
    one = feature_record(1, 1.0)
    two = feature_record(2, 2.0)
    three = feature_record(3, 3.0)

    selected = _select_exact_features(
        (_accepted(three), _accepted(one)),
        _features(one, two, three),
    )

    assert tuple(record.decision_identity for record in selected.records) == (
        three.decision_identity,
        one.decision_identity,
    )
    assert two.decision_identity not in {
        record.decision_identity for record in selected.records
    }
    assert selected.source_sha256 == "b" * 64


def test_missing_accepted_feature_identity_fails_closed() -> None:
    one = feature_record(1, 1.0)
    two = feature_record(2, 2.0)

    with pytest.raises(ValueError, match="missing.*accepted"):
        _select_exact_features(
            (_accepted(one), _accepted(two)),
            _features(one),
        )


def test_duplicate_feature_identity_fails_closed() -> None:
    one = feature_record(1, 1.0)
    duplicate = _features(one, one)

    with pytest.raises(ValueError, match="duplicate"):
        _select_exact_features((_accepted(one),), duplicate)


def test_exact_30000ms_labels_are_selected_in_cohort_order() -> None:
    one = feature_record(1, 1.0)
    two = feature_record(2, 2.0)
    extra = feature_record(3, 3.0)

    one_30 = future_label(
        one,
        30_000,
        endpoint_return_bps=10.0,
        reversal_occurred=False,
    )
    two_30 = future_label(
        two,
        30_000,
        endpoint_return_bps=20.0,
        reversal_occurred=True,
    )
    extra_30 = future_label(
        extra,
        30_000,
        endpoint_return_bps=30.0,
        reversal_occurred=False,
    )
    one_10 = future_label(
        one,
        10_000,
        endpoint_return_bps=5.0,
        reversal_occurred=False,
    )

    selected = _select_exact_labels(
        (_accepted(two), _accepted(one)),
        _labels(one_10, one_30, extra_30, two_30),
        horizon_ms=30_000,
        label_version=1,
    )

    assert tuple(label.decision_identity for label in selected.labels) == (
        two.decision_identity,
        one.decision_identity,
    )
    assert all(label.horizon_ms == 30_000 for label in selected.labels)


def test_missing_accepted_30000ms_label_fails_closed() -> None:
    one = feature_record(1, 1.0)
    only_wrong_horizon = future_label(
        one,
        10_000,
        endpoint_return_bps=5.0,
        reversal_occurred=False,
    )

    with pytest.raises(ValueError, match="missing.*30000"):
        _select_exact_labels(
            (_accepted(one),),
            _labels(only_wrong_horizon),
            horizon_ms=30_000,
            label_version=1,
        )
