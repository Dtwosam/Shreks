from __future__ import annotations

import math
import subprocess
import sys

import pytest

from shreks_brain.learning import (
    ClassWeightMode,
    LogisticRegressionTrainingPolicy,
    MODEL_TRAINING_SCHEMA_VERSION,
    ModelFamily,
    ModelTrainingRequest,
    ResearchReturnTarget,
    train_logistic_regression,
)
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
)


TARGET_HORIZON = 300


def _request(
    *,
    feature_columns: tuple[str, ...] = (
        "market_liquidity_usd",
        "wallet_strong_entry_wallet_count",
    ),
    class_weight_mode: ClassWeightMode = ClassWeightMode.NONE,
) -> ModelTrainingRequest:
    return ModelTrainingRequest(
        model_version="challenger-e3-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_columns=feature_columns,
        target=ResearchReturnTarget(
            horizon_seconds=TARGET_HORIZON,
            minimum_return_pct=5.0,
        ),
        training_policy=LogisticRegressionTrainingPolicy(
            version="logit-e3-test-v1",
            regularization_c=1.0,
            max_iterations=1_000,
            tolerance=1e-8,
            class_weight_mode=class_weight_mode,
        ),
    )


def _row(
    *,
    mint: str,
    as_of: int,
    liquidity: float | None,
    strong_entries: int | None,
    target_return: float | None,
    target_completed: bool = True,
    non_target_return: float | None = None,
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
        }
    )
    for horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS:
        prefix = f"label_{horizon}s_"
        row[prefix + "status"] = "PENDING"
        row[prefix + "baseline_observed_at_unix_ms"] = as_of
        row[prefix + "due_at_unix_ms"] = as_of + horizon * 1_000

    target_prefix = f"label_{TARGET_HORIZON}s_"
    if target_completed:
        due = as_of + TARGET_HORIZON * 1_000
        row[target_prefix + "status"] = "COMPLETED"
        row[target_prefix + "checkpoint_observed_at_unix_ms"] = due
        row[target_prefix + "completed_at_unix_ms"] = due
        row[target_prefix + "return_pct"] = target_return

    if non_target_return is not None:
        prefix = "label_60s_"
        due = as_of + 60_000
        row[prefix + "status"] = "COMPLETED"
        row[prefix + "checkpoint_observed_at_unix_ms"] = due
        row[prefix + "completed_at_unix_ms"] = due
        row[prefix + "return_pct"] = non_target_return
    return row


def _rows() -> tuple[dict[str, object], ...]:
    return (
        _row(
            mint="mint-d",
            as_of=4_000,
            liquidity=400.0,
            strong_entries=4,
            target_return=20.0,
        ),
        _row(
            mint="mint-a",
            as_of=1_000,
            liquidity=100.0,
            strong_entries=1,
            target_return=-10.0,
        ),
        _row(
            mint="mint-pending",
            as_of=5_000,
            liquidity=500.0,
            strong_entries=5,
            target_return=None,
            target_completed=False,
        ),
        _row(
            mint="mint-c",
            as_of=3_000,
            liquidity=300.0,
            strong_entries=3,
            target_return=10.0,
        ),
        _row(
            mint="mint-b",
            as_of=2_000,
            liquidity=200.0,
            strong_entries=2,
            target_return=-5.0,
        ),
    )


def test_two_class_training_produces_portable_reconciled_artifact() -> None:
    model = train_logistic_regression(_rows(), _request())

    assert model.schema_version == MODEL_TRAINING_SCHEMA_VERSION
    assert model.model_family is ModelFamily.LOGISTIC_REGRESSION
    assert model.training_row_count == 4
    assert model.positive_row_count == 2
    assert model.negative_row_count == 2
    assert model.target_unavailable_row_count == 1
    assert model.min_training_as_of_unix_ms == 1_000
    assert model.max_training_as_of_unix_ms == 4_000
    assert tuple(value.feature_name for value in model.feature_transforms) == (
        "market_liquidity_usd",
        "wallet_strong_entry_wallet_count",
    )
    assert len(model.coefficients) == len(model.feature_transforms)
    assert all(math.isfinite(value) for value in model.coefficients)
    assert math.isfinite(model.intercept)


def test_training_is_input_order_independent() -> None:
    rows = _rows()
    first = train_logistic_regression(rows, _request())
    second = train_logistic_regression(tuple(reversed(rows)), _request())
    assert first == second


def test_training_requires_at_least_two_eligible_rows_and_both_classes() -> None:
    one_eligible = (
        _row(
            mint="mint-one",
            as_of=1_000,
            liquidity=100.0,
            strong_entries=1,
            target_return=10.0,
        ),
        _row(
            mint="mint-pending",
            as_of=2_000,
            liquidity=200.0,
            strong_entries=2,
            target_return=None,
            target_completed=False,
        ),
    )
    with pytest.raises(ValueError, match="at least 2"):
        train_logistic_regression(one_eligible, _request())

    one_class = tuple(
        _row(
            mint=f"mint-{index}",
            as_of=1_000 + index,
            liquidity=100.0 + index,
            strong_entries=index,
            target_return=10.0 + index,
        )
        for index in range(3)
    )
    with pytest.raises(ValueError, match="classes"):
        train_logistic_regression(one_class, _request())


def test_training_fails_through_feature_boundary_when_feature_is_all_missing() -> None:
    rows = tuple(
        _row(
            mint=f"mint-{index}",
            as_of=1_000 + index,
            liquidity=None,
            strong_entries=index,
            target_return=(-10.0 if index == 0 else 10.0),
        )
        for index in range(3)
    )
    with pytest.raises(ValueError, match="market_liquidity_usd.*observed"):
        train_logistic_regression(rows, _request())


def test_non_target_future_labels_cannot_change_trained_artifact() -> None:
    base = tuple(
        _row(
            mint=f"mint-{index}",
            as_of=1_000 + index,
            liquidity=100.0 + index * 100.0,
            strong_entries=index,
            target_return=(-10.0 if index < 2 else 10.0),
            non_target_return=-99.0,
        )
        for index in range(4)
    )
    changed = tuple(dict(row, label_60s_return_pct=99.0) for row in base)
    assert train_logistic_regression(base, _request()) == train_logistic_regression(
        changed, _request()
    )


def test_target_change_changes_training_fingerprint() -> None:
    rows = list(_rows())
    first = train_logistic_regression(tuple(rows), _request())
    changed = [dict(row) for row in rows]
    changed[0][f"label_{TARGET_HORIZON}s_return_pct"] = -50.0
    second = train_logistic_regression(tuple(changed), _request())
    assert first.training_fingerprint_sha256 != second.training_fingerprint_sha256


def test_artifact_contains_no_evaluation_or_trading_metrics() -> None:
    model = train_logistic_regression(_rows(), _request())
    for forbidden in (
        "accuracy",
        "auc",
        "calibration",
        "expectancy",
        "pnl",
        "win_rate",
        "drawdown",
        "profit_factor",
        "turnover",
    ):
        assert not hasattr(model, forbidden)


def test_learning_import_does_not_import_sklearn() -> None:
    code = (
        "import sys; import shreks_brain.learning; "
        "assert 'sklearn' not in sys.modules"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
