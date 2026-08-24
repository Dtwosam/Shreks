from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchDatasetManifest,
    ResearchExitability,
    ResearchOutcomeLabel,
    ResearchOutcomeLabelStatus,
)


def _values(value):
    return {field.name: getattr(value, field.name) for field in fields(value)}


def _replace(value, **changes):
    values = _values(value)
    values.update(changes)
    return type(value)(**values)


def _pending_label(*, horizon: int = 60, baseline: int = 1_000_000):
    return ResearchOutcomeLabel(
        horizon_seconds=horizon,
        baseline_observed_at_unix_ms=baseline,
        due_at_unix_ms=baseline + horizon * 1_000,
        status=ResearchOutcomeLabelStatus.PENDING,
        checkpoint_observed_at_unix_ms=None,
        completed_at_unix_ms=None,
        return_pct=None,
        mfe_pct=None,
        mae_pct=None,
        liquidity_change_pct=None,
        volume_m5_change_pct=None,
        buys_m5_change=None,
        sells_m5_change=None,
        rug_or_dead_pool=None,
        exitability=None,
    )


def _completed_label(*, horizon: int = 60, baseline: int = 1_000_000):
    due = baseline + horizon * 1_000
    return ResearchOutcomeLabel(
        horizon_seconds=horizon,
        baseline_observed_at_unix_ms=baseline,
        due_at_unix_ms=due,
        status=ResearchOutcomeLabelStatus.COMPLETED,
        checkpoint_observed_at_unix_ms=due + 500,
        completed_at_unix_ms=due + 1_000,
        return_pct=12.5,
        mfe_pct=20.0,
        mae_pct=-4.0,
        liquidity_change_pct=5.0,
        volume_m5_change_pct=-10.0,
        buys_m5_change=7,
        sells_m5_change=-3,
        rug_or_dead_pool=False,
        exitability=ResearchExitability.EXITABLE,
    )


def test_research_label_enums_and_constants_are_exact():
    assert tuple(ResearchOutcomeLabelStatus) == (
        ResearchOutcomeLabelStatus.PENDING,
        ResearchOutcomeLabelStatus.COMPLETED,
    )
    assert ResearchOutcomeLabelStatus.PENDING.value == "PENDING"
    assert ResearchOutcomeLabelStatus.COMPLETED.value == "COMPLETED"
    assert ResearchExitability.EXITABLE.value == "EXITABLE"
    assert ResearchExitability.NOT_EXITABLE.value == "NOT_EXITABLE"
    assert RESEARCH_OUTCOME_HORIZONS_SECONDS == (
        60,
        300,
        900,
        1800,
        3600,
        14_400,
        86_400,
    )


def test_research_outcome_label_is_frozen():
    label = _pending_label()
    with pytest.raises(FrozenInstanceError):
        label.horizon_seconds = 300


def test_every_approved_horizon_is_accepted():
    labels = tuple(_pending_label(horizon=value) for value in RESEARCH_OUTCOME_HORIZONS_SECONDS)
    assert tuple(label.horizon_seconds for label in labels) == RESEARCH_OUTCOME_HORIZONS_SECONDS


@pytest.mark.parametrize("horizon", [True, 0, 1, 61, 86_401])
def test_unapproved_horizon_is_rejected(horizon):
    with pytest.raises(ValueError, match="horizon_seconds"):
        _pending_label(horizon=horizon)


def test_due_time_must_match_decision_anchored_horizon():
    label = _pending_label()
    with pytest.raises(ValueError, match="due_at_unix_ms"):
        _replace(label, due_at_unix_ms=label.due_at_unix_ms + 1)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("checkpoint_observed_at_unix_ms", 1_060_000),
        ("completed_at_unix_ms", 1_060_000),
        ("return_pct", 0.0),
        ("mfe_pct", 0.0),
        ("mae_pct", 0.0),
        ("liquidity_change_pct", 0.0),
        ("volume_m5_change_pct", 0.0),
        ("buys_m5_change", 0),
        ("sells_m5_change", 0),
        ("rug_or_dead_pool", False),
        ("exitability", ResearchExitability.EXITABLE),
    ],
)
def test_pending_label_cannot_claim_future_evidence(field_name, value):
    with pytest.raises(ValueError, match="PENDING"):
        _replace(_pending_label(), **{field_name: value})


@pytest.mark.parametrize(
    "field_name",
    ["checkpoint_observed_at_unix_ms", "completed_at_unix_ms", "return_pct"],
)
def test_completed_label_requires_core_completion_evidence(field_name):
    with pytest.raises(ValueError, match="COMPLETED"):
        _replace(_completed_label(), **{field_name: None})


def test_completed_checkpoint_cannot_precede_due_time():
    label = _completed_label()
    with pytest.raises(ValueError, match="checkpoint_observed_at_unix_ms"):
        _replace(label, checkpoint_observed_at_unix_ms=label.due_at_unix_ms - 1)


def test_completed_at_cannot_precede_checkpoint_observation():
    label = _completed_label()
    with pytest.raises(ValueError, match="completed_at_unix_ms"):
        _replace(
            label,
            completed_at_unix_ms=label.checkpoint_observed_at_unix_ms - 1,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "return_pct",
        "mfe_pct",
        "mae_pct",
        "liquidity_change_pct",
        "volume_m5_change_pct",
    ],
)
@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf, True])
def test_numeric_label_metrics_must_be_finite_numbers(field_name, bad_value):
    with pytest.raises(ValueError, match=field_name):
        _replace(_completed_label(), **{field_name: bad_value})


@pytest.mark.parametrize("field_name", ["buys_m5_change", "sells_m5_change"])
def test_integer_deltas_reject_bool(field_name):
    with pytest.raises(ValueError, match=field_name):
        _replace(_completed_label(), **{field_name: True})


def test_rug_flag_requires_bool_or_none():
    with pytest.raises(ValueError, match="rug_or_dead_pool"):
        _replace(_completed_label(), rug_or_dead_pool=1)


def test_exitability_requires_enum_or_none():
    with pytest.raises(ValueError, match="exitability"):
        _replace(_completed_label(), exitability="EXITABLE")


def test_manifest_accepts_canonical_sha256():
    manifest = ResearchDatasetManifest(
        schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        row_count=2,
        min_as_of_unix_ms=100,
        max_as_of_unix_ms=200,
        dataset_fingerprint_sha256="a" * 64,
    )
    assert manifest.row_count == 2


def test_manifest_is_frozen():
    manifest = ResearchDatasetManifest(
        schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        row_count=1,
        min_as_of_unix_ms=100,
        max_as_of_unix_ms=100,
        dataset_fingerprint_sha256="0" * 64,
    )
    with pytest.raises(FrozenInstanceError):
        manifest.row_count = 2


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"schema_version": "wrong"}, "schema_version"),
        ({"row_count": 0}, "row_count"),
        ({"row_count": True}, "row_count"),
        ({"min_as_of_unix_ms": True}, "min_as_of_unix_ms"),
        ({"max_as_of_unix_ms": True}, "max_as_of_unix_ms"),
        ({"min_as_of_unix_ms": 201}, "timestamp"),
        ({"dataset_fingerprint_sha256": "A" * 64}, "dataset_fingerprint_sha256"),
        ({"dataset_fingerprint_sha256": "g" * 64}, "dataset_fingerprint_sha256"),
        ({"dataset_fingerprint_sha256": "a" * 63}, "dataset_fingerprint_sha256"),
    ],
)
def test_manifest_rejects_invalid_values(changes, match):
    values = {
        "schema_version": RESEARCH_DATASET_SCHEMA_VERSION,
        "row_count": 2,
        "min_as_of_unix_ms": 100,
        "max_as_of_unix_ms": 200,
        "dataset_fingerprint_sha256": "a" * 64,
    }
    values.update(changes)
    with pytest.raises(ValueError, match=match):
        ResearchDatasetManifest(**values)
