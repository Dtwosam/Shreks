from __future__ import annotations

import hashlib
import json
import math

from shreks_brain.learning import (
    ModelTrainingRequest,
    predict_positive_probability,
    train_logistic_regression,
)
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
)

from .models import (
    TIME_AWARE_VALIDATION_SCHEMA_VERSION,
    ChronologicalValidationFold,
    TimeAwareValidationPolicy,
    TimeAwareValidationRun,
    ValidationFoldResult,
)


_D6_COLUMNS = RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
_D6_COLUMN_SET = frozenset(_D6_COLUMNS)


def run_time_aware_validation(
    rows: tuple[dict[str, object], ...],
    request: ModelTrainingRequest,
    policy: TimeAwareValidationPolicy,
) -> TimeAwareValidationRun:
    if type(request) is not ModelTrainingRequest:
        raise ValueError("request must be an exact ModelTrainingRequest")
    if type(policy) is not TimeAwareValidationPolicy:
        raise ValueError("policy must be an exact TimeAwareValidationPolicy")

    ordered_rows = _validate_and_order_rows(rows)
    ordered_folds = tuple(sorted(policy.folds, key=_fold_sort_key))
    fold_results = tuple(
        _run_fold(ordered_rows, request, fold)
        for fold in ordered_folds
    )
    fingerprint = _run_fingerprint(policy.version, request, fold_results)
    return TimeAwareValidationRun(
        schema_version=TIME_AWARE_VALIDATION_SCHEMA_VERSION,
        validation_policy_version=policy.version,
        model_training_request=request,
        fold_results=fold_results,
        validation_run_fingerprint_sha256=fingerprint,
    )


def _validate_and_order_rows(
    rows: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    if not isinstance(rows, tuple) or not rows:
        raise ValueError("rows must be a non-empty tuple")

    identities: set[tuple[str, int]] = set()
    ordered: list[dict[str, object]] = []
    for row in rows:
        if type(row) is not dict:
            raise ValueError("rows must contain exact D6 logical row mappings")
        if len(row) != len(_D6_COLUMNS) or frozenset(row) != _D6_COLUMN_SET:
            raise ValueError("each D6 row must expose exactly the sealed physical column set")
        if row["dataset_schema_version"] != RESEARCH_DATASET_SCHEMA_VERSION:
            raise ValueError("row dataset schema must equal the sealed D6 schema")

        mint = row["candidate_mint"]
        as_of = row["as_of_unix_ms"]
        if not isinstance(mint, str) or not mint.strip():
            raise ValueError("candidate_mint must be a non-empty string")
        if isinstance(as_of, bool) or not isinstance(as_of, int) or as_of < 0:
            raise ValueError("as_of_unix_ms must be a non-negative integer")

        identity = (mint, as_of)
        if identity in identities:
            raise ValueError("duplicate D6 validation row identity")
        identities.add(identity)
        ordered.append(row)

    ordered.sort(key=lambda row: (row["as_of_unix_ms"], row["candidate_mint"]))
    return tuple(ordered)


def _run_fold(
    rows: tuple[dict[str, object], ...],
    request: ModelTrainingRequest,
    fold: ChronologicalValidationFold,
) -> ValidationFoldResult:
    training_window = tuple(
        row
        for row in rows
        if (
            fold.training_started_at_unix_ms
            <= row["as_of_unix_ms"]
            < fold.training_ended_at_unix_ms
        )
    )

    mature_rows: list[dict[str, object]] = []
    unavailable_count = 0
    for row in training_window:
        try:
            mature = _target_is_mature_at_split(row, request, fold)
        except ValueError as exc:
            raise ValueError(f"fold {fold.name!r}: {exc}") from exc
        if mature:
            mature_rows.append(row)
        else:
            unavailable_count += 1

    try:
        model = train_logistic_regression(tuple(mature_rows), request)
    except ValueError as exc:
        raise ValueError(f"fold {fold.name!r}: {exc}") from exc
    except RuntimeError as exc:
        raise RuntimeError(f"fold {fold.name!r}: {exc}") from exc

    validation_rows = tuple(
        row
        for row in rows
        if (
            fold.validation_started_at_unix_ms
            <= row["as_of_unix_ms"]
            < fold.validation_ended_at_unix_ms
        )
    )
    if not validation_rows:
        raise ValueError(f"fold {fold.name!r}: validation interval contains no rows")

    predictions = []
    for row in validation_rows:
        try:
            predictions.append(predict_positive_probability(model, row))
        except ValueError as exc:
            raise ValueError(f"fold {fold.name!r}: {exc}") from exc

    return ValidationFoldResult(
        fold=fold,
        training_window_row_count=len(training_window),
        training_mature_target_row_count=len(mature_rows),
        training_target_unavailable_at_split_count=unavailable_count,
        validation_row_count=len(validation_rows),
        model=model,
        predictions=tuple(predictions),
    )


def _target_is_mature_at_split(
    row: dict[str, object],
    request: ModelTrainingRequest,
    fold: ChronologicalValidationFold,
) -> bool:
    horizon = request.target.horizon_seconds
    prefix = f"label_{horizon}s_"
    as_of = row["as_of_unix_ms"]
    baseline = row[prefix + "baseline_observed_at_unix_ms"]
    due = row[prefix + "due_at_unix_ms"]
    expected_due = as_of + horizon * 1_000

    if baseline != as_of:
        raise ValueError("selected target baseline must equal row as_of_unix_ms")
    if due != expected_due:
        raise ValueError("selected target due timestamp must match the selected horizon")

    status = row[prefix + "status"]
    if status == "PENDING":
        return False
    if status != "COMPLETED":
        raise ValueError("selected target status must be PENDING or COMPLETED")

    target_return = row[prefix + "return_pct"]
    if target_return is None:
        return False

    checkpoint = row[prefix + "checkpoint_observed_at_unix_ms"]
    completed = row[prefix + "completed_at_unix_ms"]
    if not _is_non_negative_int(checkpoint):
        raise ValueError("completed selected target checkpoint must be a non-negative integer")
    if checkpoint < expected_due:
        raise ValueError("completed selected target checkpoint cannot precede due time")
    if not _is_non_negative_int(completed):
        raise ValueError("completed selected target completion must be a non-negative integer")
    if completed < checkpoint:
        raise ValueError("selected target completion cannot precede checkpoint")

    _finite_number(target_return, prefix + "return_pct")
    return completed <= fold.validation_started_at_unix_ms


def _run_fingerprint(
    policy_version: str,
    request: ModelTrainingRequest,
    fold_results: tuple[ValidationFoldResult, ...],
) -> str:
    training_policy = request.training_policy
    payload = {
        "schema_version": TIME_AWARE_VALIDATION_SCHEMA_VERSION,
        "validation_policy_version": policy_version,
        "model_training_request": {
            "model_version": request.model_version,
            "model_family": request.model_family.value,
            "feature_columns": list(request.feature_columns),
            "target": {
                "horizon_seconds": request.target.horizon_seconds,
                "minimum_return_pct": _canonical_number(
                    request.target.minimum_return_pct
                ),
            },
            "training_policy": {
                "version": training_policy.version,
                "regularization_c": _canonical_number(
                    training_policy.regularization_c
                ),
                "max_iterations": training_policy.max_iterations,
                "tolerance": _canonical_number(training_policy.tolerance),
                "class_weight_mode": training_policy.class_weight_mode.value,
            },
        },
        "folds": [
            {
                "name": result.fold.name,
                "training_started_at_unix_ms": result.fold.training_started_at_unix_ms,
                "training_ended_at_unix_ms": result.fold.training_ended_at_unix_ms,
                "validation_started_at_unix_ms": result.fold.validation_started_at_unix_ms,
                "validation_ended_at_unix_ms": result.fold.validation_ended_at_unix_ms,
                "training_fingerprint_sha256": result.model.training_fingerprint_sha256,
                "predictions": [
                    {
                        "model_version": prediction.model_version,
                        "candidate_mint": prediction.candidate_mint,
                        "as_of_unix_ms": prediction.as_of_unix_ms,
                        "positive_probability": _canonical_number(
                            prediction.positive_probability
                        ),
                    }
                    for prediction in result.predictions
                ],
            }
            for result in fold_results
        ],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fold_sort_key(fold: ChronologicalValidationFold) -> tuple[int, int, str]:
    return (
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.name,
    )


def _is_non_negative_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _canonical_number(value: float | int) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("validation fingerprint numeric provenance must be numeric")
    if not math.isfinite(value):
        raise ValueError("validation fingerprint cannot contain non-finite numbers")
    if isinstance(value, int):
        return value
    return {"float_hex": float(value).hex()}
