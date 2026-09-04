from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from fast_chronological_fixtures import HORIZON_MS, chronological_bundle
from shreks_brain.fast_first_champion_plan import (
    FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_VERSION,
    FAST_FIRST_CHAMPION_EVIDENCE_PLAN_VERSION,
    FastFirstChampionEvidencePlan,
    build_fast_first_champion_evidence_plan,
    decode_fast_first_champion_evidence_plan,
    encode_fast_first_champion_evidence_plan,
)
from shreks_brain.research.fast_training_bundle import (
    bundle_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_targets import (
    future_path_logical_fingerprint_sha256,
)


SELECTION_AT = 4_000


def _plan(bundle=None, **overrides):
    values = dict(
        bundle=bundle or chronological_bundle(),
        horizon_ms=HORIZON_MS,
        selection_at_unix_ms=SELECTION_AT,
        minimum_raw_rows_per_partition=2,
        minimum_test_scored_observations=2,
    )
    values.update(overrides)
    return build_fast_first_champion_evidence_plan(**values)


def _without_test_route_labels(bundle):
    labels = tuple(
        replace(label, route_unavailability_observed=None)
        if (
            label.horizon_ms == HORIZON_MS
            and label.decision_observed_at_unix_ms >= 3_100
        )
        else label
        for label in bundle.future_path_labels.labels
    )
    logical = future_path_logical_fingerprint_sha256(labels)
    future = replace(
        bundle.future_path_labels,
        labels=labels,
        logical_fingerprint_sha256=logical,
    )
    provisional = replace(
        bundle.manifest,
        future_path_logical_fingerprint_sha256=logical,
        bundle_fingerprint_sha256="0" * 64,
    )
    manifest = replace(
        provisional,
        bundle_fingerprint_sha256=bundle_logical_fingerprint_sha256(
            provisional
        ),
    )
    return replace(
        bundle,
        future_path_labels=future,
        manifest=manifest,
    )


def test_plan_uses_fixed_feature_only_60_20_20_split() -> None:
    plan = _plan()

    assert type(plan) is FastFirstChampionEvidencePlan
    assert plan.schema_name == FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_NAME
    assert plan.schema_version == FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_VERSION
    assert plan.version == FAST_FIRST_CHAMPION_EVIDENCE_PLAN_VERSION
    assert plan.horizon_ms == HORIZON_MS
    assert plan.selection_at_unix_ms == SELECTION_AT
    assert plan.minimum_raw_rows_per_partition == 2
    assert plan.minimum_test_scored_observations == 2
    assert plan.eligible_preselection_row_count == 12

    fold = plan.validation_policy.folds[0]
    assert fold.training_started_at_unix_ms == 1_000
    assert fold.training_ended_at_unix_ms == 2_100
    assert fold.validation_started_at_unix_ms == 2_100
    assert fold.validation_ended_at_unix_ms == 3_100
    assert fold.test_started_at_unix_ms == 3_100
    assert fold.test_ended_at_unix_ms == SELECTION_AT - HORIZON_MS

    assert plan.training_raw_row_count == 7
    assert plan.validation_raw_row_count == 3
    assert plan.test_raw_row_count == 2
    assert plan.training_row_count == 7
    assert plan.validation_row_count == 3
    assert plan.test_row_count == 2
    assert len(plan.target_evidence) == 5
    assert all(value.test_prediction_count == 2 for value in plan.target_evidence)
    assert all(
        value.test_target_available_count >= 2
        for value in plan.target_evidence
    )


def test_split_is_independent_of_future_target_values() -> None:
    baseline = _plan(chronological_bundle())
    shifted = _plan(
        chronological_bundle(
            validation_target_shift=9_999.0,
            test_target_shift=-9_999.0,
        )
    )

    assert baseline.validation_policy == shifted.validation_policy
    assert baseline.selection_at_unix_ms == shifted.selection_at_unix_ms
    assert baseline.eligible_preselection_row_count == (
        shifted.eligible_preselection_row_count
    )


def test_plan_preserves_sealed_leakage_quarantine() -> None:
    plan = _plan(
        chronological_bundle(
            shared_actor=True,
            shared_signature=True,
        ),
        minimum_test_scored_observations=2,
    )

    assert plan.training_raw_row_count == 7
    assert plan.validation_raw_row_count == 3
    assert plan.test_raw_row_count == 2
    assert plan.training_row_count < plan.training_raw_row_count
    assert plan.validation_row_count < plan.validation_raw_row_count
    assert plan.test_row_count == plan.test_raw_row_count
    assert len(plan.quarantine_fingerprint_sha256) == 64


def test_plan_rejects_insufficient_mature_preselection_population() -> None:
    with pytest.raises(ValueError, match="eligible|partition|evidence"):
        _plan(
            selection_at_unix_ms=1_750,
            minimum_raw_rows_per_partition=2,
        )


def test_plan_rejects_insufficient_required_target_test_evidence() -> None:
    bundle = _without_test_route_labels(chronological_bundle())

    with pytest.raises(
        ValueError,
        match="route_unavailability_observed.*TEST|TEST.*route_unavailability_observed",
    ):
        _plan(bundle)


def test_plan_codec_is_canonical_and_authenticated() -> None:
    plan = _plan()
    payload = encode_fast_first_champion_evidence_plan(plan)

    assert payload.endswith("\n")
    decoded = decode_fast_first_champion_evidence_plan(payload)
    assert decoded == plan
    assert encode_fast_first_champion_evidence_plan(decoded) == payload


def test_plan_codec_rejects_tamper_and_noncanonical_json() -> None:
    payload = encode_fast_first_champion_evidence_plan(_plan())
    tampered = payload.replace(
        '"minimum_test_scored_observations":2',
        '"minimum_test_scored_observations":1',
    )
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_first_champion_evidence_plan(tampered)

    with pytest.raises(ValueError, match="canonical|trailing newline"):
        decode_fast_first_champion_evidence_plan(payload + "\n")


def test_plan_source_has_no_network_execution_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion_plan.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
        "sqlite3",
    ):
        assert forbidden not in source
