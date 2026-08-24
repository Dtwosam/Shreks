from __future__ import annotations

import math

from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
)

from .models import ModelPrediction, TrainedLogisticRegressionModel


_D6_COLUMNS = RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
_D6_COLUMN_SET = frozenset(_D6_COLUMNS)


def predict_positive_probability(
    model: TrainedLogisticRegressionModel,
    row: dict[str, object],
) -> ModelPrediction:
    if type(model) is not TrainedLogisticRegressionModel:
        raise ValueError("model must be an exact TrainedLogisticRegressionModel")
    if type(row) is not dict:
        raise ValueError("row must be an exact D6 logical row mapping")
    if len(row) != len(_D6_COLUMNS) or frozenset(row) != _D6_COLUMN_SET:
        raise ValueError("row must expose exactly the sealed D6 physical column set")
    if row["dataset_schema_version"] != RESEARCH_DATASET_SCHEMA_VERSION:
        raise ValueError("row dataset schema must equal the sealed D6 schema")

    mint = row["candidate_mint"]
    as_of = row["as_of_unix_ms"]
    if not isinstance(mint, str) or not mint.strip():
        raise ValueError("candidate_mint must be a non-empty string")
    if isinstance(as_of, bool) or not isinstance(as_of, int) or as_of < 0:
        raise ValueError("as_of_unix_ms must be a non-negative integer")

    z = model.intercept
    for transform, coefficient in zip(
        model.feature_transforms, model.coefficients, strict=True
    ):
        raw = row[transform.feature_name]
        if raw is None:
            value = transform.imputation_median
        else:
            value = _finite_scalar(raw, transform.feature_name)
        standardized = (value - transform.mean) / transform.scale
        z += coefficient * standardized

    probability = _stable_sigmoid(z)
    return ModelPrediction(
        model_version=model.model_version,
        candidate_mint=mint,
        as_of_unix_ms=as_of,
        positive_probability=probability,
    )


def _finite_scalar(value: object, name: str) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric, boolean, or None")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _stable_sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)
