from __future__ import annotations

import math

from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
)
from shreks_brain.validation import TimeAwareValidationRun

from .models import ProbabilityObservation


_D6_COLUMNS = RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
_D6_COLUMN_SET = frozenset(_D6_COLUMNS)


def build_probability_observations_from_e4(
    rows: tuple[dict[str, object], ...],
    validation_run: TimeAwareValidationRun,
    candidate_version: str,
) -> tuple[ProbabilityObservation, ...]:
    if not isinstance(candidate_version, str) or not candidate_version.strip():
        raise ValueError("candidate_version must be a non-empty string")
    if type(validation_run) is not TimeAwareValidationRun:
        raise ValueError("validation_run must be an exact TimeAwareValidationRun")

    row_by_identity = _validate_rows(rows)
    request = validation_run.model_training_request
    prefix = f"label_{request.target.horizon_seconds}s_"
    status_column = prefix + "status"
    return_column = prefix + "return_pct"

    prediction_identities: set[tuple[str, int]] = set()
    observations: list[ProbabilityObservation] = []
    for fold_result in validation_run.fold_results:
        for prediction in fold_result.predictions:
            identity = (prediction.candidate_mint, prediction.as_of_unix_ms)
            if identity in prediction_identities:
                raise ValueError(
                    "duplicate E4 prediction identity: "
                    f"{prediction.candidate_mint}@{prediction.as_of_unix_ms}"
                )
            prediction_identities.add(identity)

            row = row_by_identity.get(identity)
            if row is None:
                raise ValueError(
                    "missing D6 row for E4 prediction identity: "
                    f"{prediction.candidate_mint}@{prediction.as_of_unix_ms}"
                )

            status = row[status_column]
            if status != "COMPLETED":
                raise ValueError(
                    "selected target is not completed for E4 prediction identity "
                    f"{prediction.candidate_mint}@{prediction.as_of_unix_ms}"
                )
            selected_return = row[return_column]
            if (
                isinstance(selected_return, bool)
                or not isinstance(selected_return, (int, float))
                or not math.isfinite(selected_return)
            ):
                raise ValueError(
                    "selected target return is not finite for E4 prediction identity "
                    f"{prediction.candidate_mint}@{prediction.as_of_unix_ms}"
                )

            observations.append(
                ProbabilityObservation(
                    candidate_version=candidate_version,
                    model_version=prediction.model_version,
                    candidate_mint=prediction.candidate_mint,
                    as_of_unix_ms=prediction.as_of_unix_ms,
                    positive_probability=prediction.positive_probability,
                    target_positive=(
                        float(selected_return)
                        >= float(request.target.minimum_return_pct)
                    ),
                    setup_name=_row_string(row, "setup_name", identity),
                    market_regime=_row_string(row, "market_regime", identity),
                    fold_name=fold_result.fold.name,
                )
            )

    observations.sort(key=lambda value: (value.as_of_unix_ms, value.candidate_mint))
    return tuple(observations)


def _validate_rows(
    rows: tuple[dict[str, object], ...],
) -> dict[tuple[str, int], dict[str, object]]:
    if not isinstance(rows, tuple) or not rows:
        raise ValueError("rows must be a non-empty tuple")

    values: dict[tuple[str, int], dict[str, object]] = {}
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
        if identity in values:
            raise ValueError(f"duplicate D6 row identity: {mint}@{as_of}")
        values[identity] = row
    return values


def _row_string(
    row: dict[str, object],
    column: str,
    identity: tuple[str, int],
) -> str:
    value = row[column]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{column} must be a non-empty string for E4 prediction identity "
            f"{identity[0]}@{identity[1]}"
        )
    return value
