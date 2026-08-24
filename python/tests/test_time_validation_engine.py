from __future__ import annotations

from dataclasses import fields
import inspect
import subprocess
import sys

import pytest

from shreks_brain.learning import (
    ClassWeightMode,
    LogisticRegressionTrainingPolicy,
    ModelFamily,
    ModelTrainingRequest,
    ResearchReturnTarget,
)
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
)
from shreks_brain.validation import (
    ChronologicalValidationFold,
    TimeAwareValidationPolicy,
    TimeAwareValidationRun,
    ValidationFoldResult,
    run_time_aware_validation,
)


TARGET_HORIZON = 300
FOLD1_VALIDATION_START = 1_000_000
FOLD2_VALIDATION_START = 1_400_000


def _request(
    feature_columns: tuple[str, ...] = (
        "market_liquidity_usd",
        "wallet_strong_entry_wallet_count",
    ),
) -> ModelTrainingRequest:
    return ModelTrainingRequest(
        model_version="e4-model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_columns=feature_columns,
        target=ResearchReturnTarget(
            horizon_seconds=TARGET_HORIZON,
            minimum_return_pct=5.0,
        ),
        training_policy=LogisticRegressionTrainingPolicy(
            version="e4-logit-v1",
            regularization_c=1.0,
            max_iterations=500,
            tolerance=1e-6,
            class_weight_mode=ClassWeightMode.NONE,
        ),
    )


def _fold1() -> ChronologicalValidationFold:
    return ChronologicalValidationFold(
        name="fold-1",
        training_started_at_unix_ms=0,
        training_ended_at_unix_ms=FOLD1_VALIDATION_START,
        validation_started_at_unix_ms=FOLD1_VALIDATION_START,
        validation_ended_at_unix_ms=1_100_000,
    )


def _fold2() -> ChronologicalValidationFold:
    return ChronologicalValidationFold(
        name="fold-2",
        training_started_at_unix_ms=0,
        training_ended_at_unix_ms=1_100_000,
        validation_started_at_unix_ms=FOLD2_VALIDATION_START,
        validation_ended_at_unix_ms=1_500_000,
    )


def _policy(*folds: ChronologicalValidationFold) -> TimeAwareValidationPolicy:
    return TimeAwareValidationPolicy(
        version="walk-v1",
        folds=folds or (_fold1(), _fold2()),
    )


def _row(
    *,
    mint: str,
    as_of: int,
    liquidity: float | None,
    strong_entries: int | None,
    target_return: float | None = None,
    target_status: str = "PENDING",
    target_checkpoint_at: int | None = None,
    target_completed_at: int | None = None,
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
        }
    )
    for horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS:
        prefix = f"label_{horizon}s_"
        row[prefix + "status"] = "PENDING"
        row[prefix + "baseline_observed_at_unix_ms"] = as_of
        row[prefix + "due_at_unix_ms"] = as_of + horizon * 1_000

    target_prefix = f"label_{TARGET_HORIZON}s_"
    if target_status == "COMPLETED":
        due = as_of + TARGET_HORIZON * 1_000
        checkpoint = due if target_checkpoint_at is None else target_checkpoint_at
        completed = checkpoint if target_completed_at is None else target_completed_at
        row[target_prefix + "status"] = "COMPLETED"
        row[target_prefix + "checkpoint_observed_at_unix_ms"] = checkpoint
        row[target_prefix + "completed_at_unix_ms"] = completed
        row[target_prefix + "return_pct"] = target_return
    elif target_status != "PENDING":
        row[target_prefix + "status"] = target_status

    if other_return is not None:
        prefix = "label_60s_"
        due = as_of + 60_000
        row[prefix + "status"] = "COMPLETED"
        row[prefix + "checkpoint_observed_at_unix_ms"] = due
        row[prefix + "completed_at_unix_ms"] = due
        row[prefix + "return_pct"] = other_return
    return row


def _rows() -> tuple[dict[str, object], ...]:
    return (
        _row(
            mint="train-start",
            as_of=0,
            liquidity=100.0,
            strong_entries=0,
            target_status="COMPLETED",
            target_return=-10.0,
        ),
        _row(
            mint="train-neg",
            as_of=100_000,
            liquidity=120.0,
            strong_entries=1,
            target_status="COMPLETED",
            target_return=-5.0,
        ),
        _row(
            mint="train-pos",
            as_of=200_000,
            liquidity=220.0,
            strong_entries=2,
            target_status="COMPLETED",
            target_return=10.0,
        ),
        _row(
            mint="train-late",
            as_of=300_000,
            liquidity=320.0,
            strong_entries=3,
            target_status="COMPLETED",
            target_return=20.0,
            target_completed_at=FOLD1_VALIDATION_START + 1,
        ),
        _row(
            mint="train-pending",
            as_of=400_000,
            liquidity=420.0,
            strong_entries=4,
        ),
        _row(
            mint="train-boundary",
            as_of=500_000,
            liquidity=520.0,
            strong_entries=5,
            target_status="COMPLETED",
            target_return=-20.0,
            target_completed_at=FOLD1_VALIDATION_START,
        ),
        _row(
            mint="validation-start",
            as_of=1_000_000,
            liquidity=620.0,
            strong_entries=6,
            target_status="COMPLETED",
            target_return=15.0,
            target_completed_at=1_300_000,
        ),
        _row(
            mint="validation-mid",
            as_of=1_050_000,
            liquidity=720.0,
            strong_entries=7,
            target_status="COMPLETED",
            target_return=-15.0,
            target_completed_at=1_450_000,
        ),
        _row(
            mint="validation-end-boundary",
            as_of=1_100_000,
            liquidity=820.0,
            strong_entries=8,
        ),
        _row(
            mint="fold2-validation-start",
            as_of=1_400_000,
            liquidity=920.0,
            strong_entries=9,
        ),
        _row(
            mint="fold2-validation-mid",
            as_of=1_450_000,
            liquidity=1_020.0,
            strong_entries=10,
        ),
        _row(
            mint="fold2-validation-end",
            as_of=1_500_000,
            liquidity=1_120.0,
            strong_entries=11,
        ),
    )


def _replace_row(
    rows: tuple[dict[str, object], ...],
    mint: str,
    **changes: object,
) -> tuple[dict[str, object], ...]:
    values: list[dict[str, object]] = []
    for row in rows:
        changed = dict(row)
        if row["candidate_mint"] == mint:
            changed.update(changes)
        values.append(changed)
    return tuple(values)


def test_canonical_order_half_open_membership_and_fold_counts() -> None:
    rows = _rows()
    first = run_time_aware_validation(rows, _request(), _policy())
    second = run_time_aware_validation(
        tuple(reversed(rows)),
        _request(),
        _policy(_fold2(), _fold1()),
    )
    assert first == second
    assert tuple(result.fold.name for result in first.fold_results) == (
        "fold-1",
        "fold-2",
    )

    fold1, fold2 = first.fold_results
    assert fold1.training_window_row_count == 6
    assert fold1.training_mature_target_row_count == 4
    assert fold1.training_target_unavailable_at_split_count == 2
    assert tuple(p.candidate_mint for p in fold1.predictions) == (
        "validation-start",
        "validation-mid",
    )

    assert fold2.training_window_row_count == 8
    assert fold2.training_mature_target_row_count == 6
    assert fold2.training_target_unavailable_at_split_count == 2
    assert tuple(p.candidate_mint for p in fold2.predictions) == (
        "fold2-validation-start",
        "fold2-validation-mid",
    )


def test_late_target_is_withheld_from_same_fold_and_cannot_change_it() -> None:
    rows = _rows()
    base = run_time_aware_validation(rows, _request(), _policy(_fold1()))
    changed = _replace_row(
        rows,
        "train-late",
        label_300s_return_pct=-99.0,
    )
    second = run_time_aware_validation(changed, _request(), _policy(_fold1()))
    assert base == second
    assert base.fold_results[0].training_target_unavailable_at_split_count == 2


def test_completion_exactly_at_split_is_eligible() -> None:
    base = run_time_aware_validation(_rows(), _request(), _policy(_fold1()))
    late = _replace_row(
        _rows(),
        "train-boundary",
        label_300s_completed_at_unix_ms=FOLD1_VALIDATION_START + 1,
    )
    second = run_time_aware_validation(late, _request(), _policy(_fold1()))
    assert base.fold_results[0].training_mature_target_row_count == 4
    assert second.fold_results[0].training_mature_target_row_count == 3
    assert (
        base.fold_results[0].model.training_fingerprint_sha256
        != second.fold_results[0].model.training_fingerprint_sha256
    )


def test_pending_target_is_withheld_from_training() -> None:
    run = run_time_aware_validation(_rows(), _request(), _policy(_fold1()))
    assert run.fold_results[0].training_target_unavailable_at_split_count == 2


def test_same_fold_validation_labels_do_not_affect_model_predictions_or_fingerprint() -> None:
    rows = _rows()
    policy = _policy(_fold1())
    first = run_time_aware_validation(rows, _request(), policy)
    changed = _replace_row(
        rows,
        "validation-start",
        label_300s_status="PENDING",
        label_300s_return_pct=None,
        label_300s_checkpoint_observed_at_unix_ms=None,
        label_300s_completed_at_unix_ms=None,
    )
    changed = _replace_row(
        changed,
        "validation-mid",
        label_300s_return_pct=999.0,
        label_300s_completed_at_unix_ms=9_999_999,
    )
    second = run_time_aware_validation(changed, _request(), policy)
    assert first == second


def test_non_target_future_labels_cannot_change_run() -> None:
    rows = _rows()
    first = run_time_aware_validation(rows, _request(), _policy())
    changed = tuple(dict(row, label_60s_return_pct=999.0) for row in rows)
    second = run_time_aware_validation(changed, _request(), _policy())
    assert first == second


def test_earlier_validation_row_can_train_later_fold_only_after_maturity() -> None:
    base = run_time_aware_validation(_rows(), _request(), _policy())
    late = _replace_row(
        _rows(),
        "validation-start",
        label_300s_completed_at_unix_ms=FOLD2_VALIDATION_START + 1,
    )
    second = run_time_aware_validation(late, _request(), _policy())
    assert base.fold_results[0] == second.fold_results[0]
    assert base.fold_results[1].training_mature_target_row_count == 6
    assert second.fold_results[1].training_mature_target_row_count == 5
    assert (
        base.fold_results[1].model.training_fingerprint_sha256
        != second.fold_results[1].model.training_fingerprint_sha256
    )


def test_fold_models_are_fresh_and_keep_request_model_version() -> None:
    run = run_time_aware_validation(_rows(), _request(), _policy())
    first, second = run.fold_results
    assert first.model.model_version == "e4-model-v1"
    assert second.model.model_version == "e4-model-v1"
    assert (
        first.model.training_fingerprint_sha256
        != second.model.training_fingerprint_sha256
    )


def test_global_row_contract_fails_closed() -> None:
    rows = _rows()
    with pytest.raises(ValueError, match="rows.*tuple"):
        run_time_aware_validation(list(rows), _request(), _policy())  # type: ignore[arg-type]

    wrong_schema = _replace_row(
        rows,
        "train-start",
        dataset_schema_version="wrong",
    )
    with pytest.raises(ValueError, match="schema"):
        run_time_aware_validation(wrong_schema, _request(), _policy())

    missing = [dict(row) for row in rows]
    missing[0].pop("market_liquidity_usd")
    with pytest.raises(ValueError, match="column"):
        run_time_aware_validation(tuple(missing), _request(), _policy())

    extra = [dict(row) for row in rows]
    extra[0]["extra"] = 1
    with pytest.raises(ValueError, match="column"):
        run_time_aware_validation(tuple(extra), _request(), _policy())

    bad_mint = _replace_row(rows, "train-start", candidate_mint="")
    with pytest.raises(ValueError, match="candidate_mint"):
        run_time_aware_validation(bad_mint, _request(), _policy())

    duplicate = rows + (dict(rows[0]),)
    with pytest.raises(ValueError, match="duplicate"):
        run_time_aware_validation(duplicate, _request(), _policy())


def test_completed_target_chronology_contradiction_fails_with_fold_context() -> None:
    broken = _replace_row(
        _rows(),
        "train-start",
        label_300s_due_at_unix_ms=123,
    )
    with pytest.raises(ValueError, match="fold-1.*due"):
        run_time_aware_validation(broken, _request(), _policy(_fold1()))


def test_empty_validation_and_training_failures_include_fold_name() -> None:
    empty_validation_fold = ChronologicalValidationFold(
        name="empty-validation",
        training_started_at_unix_ms=0,
        training_ended_at_unix_ms=900_000,
        validation_started_at_unix_ms=900_000,
        validation_ended_at_unix_ms=950_000,
    )
    with pytest.raises(ValueError, match="empty-validation"):
        run_time_aware_validation(_rows(), _request(), _policy(empty_validation_fold))

    sparse_rows = (
        _rows()[0],
        _rows()[6],
    )
    with pytest.raises(ValueError, match="fold-1.*at least 2"):
        run_time_aware_validation(sparse_rows, _request(), _policy(_fold1()))

    one_class_rows = (
        _rows()[0],
        _rows()[1],
        _rows()[6],
    )
    with pytest.raises(ValueError, match="fold-1.*both target classes"):
        run_time_aware_validation(one_class_rows, _request(), _policy(_fold1()))

    all_missing_rows = (
        dict(_rows()[0], market_liquidity_usd=None),
        dict(_rows()[2], market_liquidity_usd=None),
        _rows()[6],
    )
    with pytest.raises(ValueError, match="fold-1.*market_liquidity_usd.*observed"):
        run_time_aware_validation(
            all_missing_rows,
            _request(("market_liquidity_usd",)),
            _policy(_fold1()),
        )


def test_metric_firewall_and_import_purity() -> None:
    forbidden = (
        "accuracy",
        "auc",
        "calibration",
        "expectancy",
        "pnl",
        "profit_factor",
        "drawdown",
        "win_rate",
        "turnover",
        "cost",
        "promotion",
    )
    field_names = {
        value.name.lower()
        for cls in (ValidationFoldResult, TimeAwareValidationRun)
        for value in fields(cls)
    }
    assert not any(any(token in name for token in forbidden) for name in field_names)

    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import shreks_brain.validation; "
                "assert not any(k == 'sklearn' or k.startswith('sklearn.') "
                "for k in sys.modules)"
            ),
        ],
        check=True,
    )

    import shreks_brain.validation.engine as engine

    source = inspect.getsource(engine).lower()
    for forbidden_import in (
        "sqlite3",
        "pyarrow",
        "pathlib",
        "requests",
        "import random",
        "from random",
        "import time",
        "from time",
    ):
        assert forbidden_import not in source
