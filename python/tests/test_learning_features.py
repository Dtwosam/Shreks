from __future__ import annotations

import math

import pytest

from shreks_brain.learning import (
    ClassWeightMode,
    LogisticRegressionTrainingPolicy,
    ModelFamily,
    ModelTrainingRequest,
    ResearchReturnTarget,
    TRAINABLE_RESEARCH_FEATURE_COLUMNS,
)
from shreks_brain.learning.features import _prepare_training_data
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
)


TARGET_HORIZON = 300


def _request(
    feature_columns: tuple[str, ...] = (
        "market_liquidity_usd",
        "wallet_strong_entry_wallet_count",
        "market_safety_liquidity_weak",
    ),
) -> ModelTrainingRequest:
    return ModelTrainingRequest(
        model_version="model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_columns=feature_columns,
        target=ResearchReturnTarget(
            horizon_seconds=TARGET_HORIZON,
            minimum_return_pct=5.0,
        ),
        training_policy=LogisticRegressionTrainingPolicy(
            version="logit-policy-v1",
            regularization_c=1.0,
            max_iterations=500,
            tolerance=1e-6,
            class_weight_mode=ClassWeightMode.NONE,
        ),
    )


def _row(
    *,
    mint: str,
    as_of: int,
    liquidity: float | None,
    strong_entries: int | None,
    safety_liquidity_weak: bool | None,
    target_return: float | None,
    target_completed: bool = True,
    other_return: float | None = None,
) -> dict[str, object]:
    row = {
        column: None
        for column in RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
    }
    row.update(
        {
            "dataset_schema_version": RESEARCH_DATASET_SCHEMA_VERSION,
            "candidate_mint": mint,
            "as_of_unix_ms": as_of,
            "market_liquidity_usd": liquidity,
            "wallet_strong_entry_wallet_count": strong_entries,
            "market_safety_liquidity_weak": safety_liquidity_weak,
        }
    )
    for horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS:
        prefix = f"label_{horizon}s_"
        row[prefix + "status"] = "PENDING"
        row[prefix + "baseline_observed_at_unix_ms"] = as_of
        row[prefix + "due_at_unix_ms"] = as_of + horizon * 1_000

    target_prefix = f"label_{TARGET_HORIZON}s_"
    if target_completed:
        row[target_prefix + "status"] = "COMPLETED"
        row[target_prefix + "checkpoint_observed_at_unix_ms"] = (
            as_of + TARGET_HORIZON * 1_000
        )
        row[target_prefix + "completed_at_unix_ms"] = (
            as_of + TARGET_HORIZON * 1_000
        )
        row[target_prefix + "return_pct"] = target_return

    other_prefix = "label_60s_"
    if other_return is not None:
        row[other_prefix + "status"] = "COMPLETED"
        row[other_prefix + "checkpoint_observed_at_unix_ms"] = as_of + 60_000
        row[other_prefix + "completed_at_unix_ms"] = as_of + 60_000
        row[other_prefix + "return_pct"] = other_return
    return row


def _rows() -> tuple[dict[str, object], ...]:
    return (
        _row(
            mint="mint-c",
            as_of=3_000,
            liquidity=300.0,
            strong_entries=3,
            safety_liquidity_weak=False,
            target_return=10.0,
        ),
        _row(
            mint="mint-a",
            as_of=1_000,
            liquidity=100.0,
            strong_entries=1,
            safety_liquidity_weak=True,
            target_return=-5.0,
        ),
        _row(
            mint="mint-b",
            as_of=2_000,
            liquidity=None,
            strong_entries=2,
            safety_liquidity_weak=False,
            target_return=5.0,
        ),
        _row(
            mint="mint-pending",
            as_of=4_000,
            liquidity=999.0,
            strong_entries=9,
            safety_liquidity_weak=False,
            target_return=None,
            target_completed=False,
        ),
    )


def test_trainable_allow_list_is_decision_time_scalar_only() -> None:
    assert TRAINABLE_RESEARCH_FEATURE_COLUMNS
    assert set(TRAINABLE_RESEARCH_FEATURE_COLUMNS).issubset(RESEARCH_FEATURE_COLUMNS)
    assert len(set(TRAINABLE_RESEARCH_FEATURE_COLUMNS)) == len(
        TRAINABLE_RESEARCH_FEATURE_COLUMNS
    )
    assert all(not name.startswith("label_") for name in TRAINABLE_RESEARCH_FEATURE_COLUMNS)
    for forbidden in (
        "candidate_mint",
        "as_of_unix_ms",
        "dataset_schema_version",
        "market_feature_schema_version",
        "score_policy_version",
        "decision_policy_version",
        "setup_name",
        "regime",
        "safety_decision",
        "setup_state",
        "market_regime",
        "decision_action",
        "required_score_threshold",
        "market_missing_features",
        "wallet_missing_features",
        "wallet_strength_assessments_json",
        "score_reason_codes",
        "decision_reason_codes",
    ):
        assert forbidden not in TRAINABLE_RESEARCH_FEATURE_COLUMNS


def test_preparation_validates_requested_features_and_d6_rows() -> None:
    rows = _rows()
    with pytest.raises(ValueError, match="trainable"):
        _prepare_training_data(rows, _request(("decision_action",)))
    with pytest.raises(ValueError, match="rows.*tuple"):
        _prepare_training_data(list(rows), _request())  # type: ignore[arg-type]

    wrong_schema = dict(rows[0])
    wrong_schema["dataset_schema_version"] = "wrong"
    with pytest.raises(ValueError, match="schema"):
        _prepare_training_data((wrong_schema,), _request())

    missing_column = dict(rows[0])
    missing_column.pop("market_liquidity_usd")
    with pytest.raises(ValueError, match="column"):
        _prepare_training_data((missing_column,), _request())

    duplicate = (rows[0], dict(rows[0]))
    with pytest.raises(ValueError, match="duplicate"):
        _prepare_training_data(duplicate, _request())


def test_pending_target_is_excluded_and_completed_return_uses_inclusive_threshold() -> None:
    prepared = _prepare_training_data(_rows(), _request())
    assert prepared.ordered_identities == (
        ("mint-a", 1_000),
        ("mint-b", 2_000),
        ("mint-c", 3_000),
    )
    assert prepared.targets == (0, 1, 1)
    assert prepared.target_unavailable_row_count == 1


def test_missing_feature_uses_training_median_and_bool_becomes_numeric() -> None:
    prepared = _prepare_training_data(_rows(), _request())
    transforms = {value.feature_name: value for value in prepared.feature_transforms}
    assert transforms["market_liquidity_usd"].imputation_median == 200.0

    liquidity_index = _request().feature_columns.index("market_liquidity_usd")
    bool_index = _request().feature_columns.index("market_safety_liquidity_weak")
    # mint-b has missing liquidity, so its raw-imputed value equals the median and
    # therefore its standardized value is computed from 200.0.
    transform = transforms["market_liquidity_usd"]
    expected = (200.0 - transform.mean) / transform.scale
    assert prepared.feature_matrix[1][liquidity_index] == pytest.approx(expected)
    assert prepared.feature_matrix[0][bool_index] != prepared.feature_matrix[1][bool_index]


def test_invalid_or_all_missing_feature_evidence_fails_closed() -> None:
    rows = list(_rows()[:3])
    for invalid in (float("nan"), float("inf"), "100"):
        broken = [dict(value) for value in rows]
        broken[0]["market_liquidity_usd"] = invalid
        with pytest.raises(ValueError, match="market_liquidity_usd"):
            _prepare_training_data(tuple(broken), _request())

    all_missing = [dict(value) for value in rows]
    for row in all_missing:
        row["market_liquidity_usd"] = None
    with pytest.raises(ValueError, match="market_liquidity_usd.*observed"):
        _prepare_training_data(tuple(all_missing), _request())


def test_preparation_is_input_order_independent() -> None:
    rows = _rows()
    first = _prepare_training_data(rows, _request())
    second = _prepare_training_data(tuple(reversed(rows)), _request())
    assert first == second


def test_non_target_future_labels_cannot_change_features_targets_or_fingerprint() -> None:
    base = tuple(
        _row(
            mint=f"mint-{index}",
            as_of=1_000 + index,
            liquidity=100.0 + index,
            strong_entries=index,
            safety_liquidity_weak=False,
            target_return=(-5.0 if index == 0 else 10.0),
            other_return=-99.0,
        )
        for index in range(3)
    )
    changed = tuple(
        dict(row, label_60s_return_pct=99.0)
        for row in base
    )
    first = _prepare_training_data(base, _request())
    second = _prepare_training_data(changed, _request())
    assert first == second


def test_target_change_changes_targets_and_training_fingerprint() -> None:
    rows = list(_rows()[:3])
    first = _prepare_training_data(tuple(rows), _request())
    changed = [dict(value) for value in rows]
    changed[0][f"label_{TARGET_HORIZON}s_return_pct"] = -50.0
    second = _prepare_training_data(tuple(changed), _request())
    assert first.targets != second.targets
    assert first.training_fingerprint_sha256 != second.training_fingerprint_sha256


def test_prepared_matrix_and_transforms_are_finite() -> None:
    prepared = _prepare_training_data(_rows(), _request())
    assert all(
        math.isfinite(value)
        for row in prepared.feature_matrix
        for value in row
    )
    assert all(
        math.isfinite(transform.imputation_median)
        and math.isfinite(transform.mean)
        and math.isfinite(transform.scale)
        and transform.scale > 0
        for transform in prepared.feature_transforms
    )
