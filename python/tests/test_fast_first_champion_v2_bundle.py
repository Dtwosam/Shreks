from __future__ import annotations

from dataclasses import replace

import pytest

from fast_forecast_fixtures import feature_record, future_label

from shreks_brain.fl9_v2_cohort_acceptance import Fl9V2AcceptedDecision
from shreks_brain.fast_first_champion_v2 import bundle as bundle_module
from shreks_brain.fast_first_champion_v2.bundle import (
    _select_exact_features,
    _select_exact_labels,
    _validate_provenance_matches_label,
    build_fast_first_champion_v2_bundle,
)
from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2CohortAcceptanceArtifact,
)
from shreks_brain.research.counterfactual_source import (
    CounterfactualSourceProvenance,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
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


def _execution_cost_policy() -> FastTrainingExecutionCostPolicy:
    return FastTrainingExecutionCostPolicy(
        version="fixture-cost-v1",
        additional_entry_slippage_bps=0,
        additional_exit_slippage_bps=0,
        entry_latency_bps=0,
        exit_latency_bps=0,
        entry_network_fee_quote=0.0,
        exit_network_fee_quote=0.0,
        entry_priority_fee_quote=0.0,
        exit_priority_fee_quote=0.0,
        entry_expected_failure_cost_quote=0.0,
        exit_expected_failure_cost_quote=0.0,
    )


def test_wrong_cohort_fails_before_any_target_access(monkeypatch) -> None:
    cohort = object.__new__(Fl9V2CohortAcceptanceArtifact)
    target_accessed = False

    monkeypatch.setattr(
        bundle_module,
        "read_fl9_v2_cohort_acceptance",
        lambda path: cohort,
    )

    def reject_cohort(value, policy):
        raise ValueError("physical V2 cohort artifact fingerprint mismatch")

    monkeypatch.setattr(bundle_module, "_validate_cohort", reject_cohort)

    def forbidden_target_access(*args, **kwargs):
        nonlocal target_accessed
        target_accessed = True
        raise AssertionError("target source must not be read")

    monkeypatch.setattr(
        bundle_module,
        "load_future_path_training_labels_from_sqlite",
        forbidden_target_access,
    )

    with pytest.raises(ValueError, match="physical V2 cohort artifact"):
        build_fast_first_champion_v2_bundle(
            cohort_path="cohort",
            feature_jsonl_path="features.jsonl",
            sqlite_path="observer.sqlite",
            future_path_label_version=1,
            training_economics_overlay_path="economics",
            training_execution_cost_policy=_execution_cost_policy(),
            counterfactual_base_quantity=1.0,
        )

    assert target_accessed is False


def test_canonical_counterfactual_provenance_must_match_full_fl4_identity() -> None:
    record = feature_record(7, 7.0)
    label = future_label(
        record,
        30_000,
        endpoint_return_bps=12.0,
        reversal_occurred=False,
    )
    provenance = CounterfactualSourceProvenance(
        decision_signature=label.decision_signature,
        decision_ordinal=label.decision_ordinal,
        decision_sequence=label.decision_sequence,
        decision_observed_at_unix_ms=label.decision_observed_at_unix_ms,
        mint=label.decision_mint,
        quote_mint=label.decision_quote_mint,
        venue=label.decision_venue,
        horizon_ms=label.horizon_ms,
        future_path_label_version=label.label_version,
        completeness=label.completeness,
        coverage_complete_through_unix_ms=(
            label.coverage_complete_through_unix_ms
        ),
        coverage_contiguous=label.coverage_contiguous,
        endpoint_signature=label.endpoint_signature,
        endpoint_ordinal=label.endpoint_ordinal,
        endpoint_observed_at_unix_ms=label.endpoint_observed_at_unix_ms,
        endpoint_price_quote=label.endpoint_price_quote,
        decision_entry_total_quote=label.decision_entry_total_quote,
        endpoint_exit_capacity_base=label.endpoint_exit_capacity_base,
        route_unavailability_observed=(
            label.route_unavailability_observed
        ),
        endpoint_cost_adjusted_return_bps=(
            label.endpoint_cost_adjusted_return_bps
        ),
        decision_execution_economics_present=False,
        endpoint_execution_economics_present=False,
    )

    _validate_provenance_matches_label(provenance, label)

    with pytest.raises(ValueError, match="provenance.*accepted FL4"):
        _validate_provenance_matches_label(
            replace(
                provenance,
                decision_sequence=provenance.decision_sequence + 1,
            ),
            label,
        )
