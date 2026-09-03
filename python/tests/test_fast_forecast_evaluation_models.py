from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shreks_brain.fast_evaluation import (
    FAST_FORECAST_EVALUATION_SCHEMA_NAME,
    FAST_FORECAST_EVALUATION_SCHEMA_VERSION,
    FastBinaryForecastMetrics,
    FastCalibrationBucket,
    FastContinuousForecastMetrics,
    FastForecastEvaluationContext,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
)


IDENTITY = ("sig", 0, 1, "mint", "quote", "venue", 1_000)


def context(**overrides) -> FastForecastEvaluationContext:
    values = {
        "decision_identity": IDENTITY,
        "as_of_unix_ms": 1_000,
        "market_regime": "HOT",
        "strategy_families": ("impulse-scalp", "micro-pullback"),
        "executable_exit_capacity_quote": 25.0,
        "expected_round_trip_cost_bps": 8.0,
    }
    values.update(overrides)
    return FastForecastEvaluationContext(**values)


def policy(**overrides) -> FastForecastEvaluationPolicy:
    values = {
        "version": "eval-v1",
        "partition": FastForecastEvaluationPartition.TEST,
        "probability_bucket_count": 10,
        "liquidity_capacity_quote_boundaries": (10.0, 100.0),
        "round_trip_cost_bps_boundaries": (5.0, 20.0),
        "binary_log_loss_clip_epsilon": 1e-12,
    }
    values.update(overrides)
    return FastForecastEvaluationPolicy(**values)


def test_schema_and_partition_contract_are_exact() -> None:
    assert FAST_FORECAST_EVALUATION_SCHEMA_NAME == "shreks.fast_lane_forecast_evaluation"
    assert FAST_FORECAST_EVALUATION_SCHEMA_VERSION == 1
    assert tuple(value.value for value in FastForecastEvaluationPartition) == (
        "VALIDATION",
        "TEST",
    )


def test_context_is_frozen_point_in_time_and_requires_canonical_strategy_families() -> None:
    value = context()
    with pytest.raises(FrozenInstanceError):
        value.market_regime = "NORMAL"  # type: ignore[misc]
    with pytest.raises(ValueError, match="timestamp|as_of|identity"):
        context(as_of_unix_ms=999)
    with pytest.raises(ValueError, match="strategy|sorted|canonical"):
        context(strategy_families=("micro-pullback", "impulse-scalp"))
    with pytest.raises(ValueError, match="strategy|unique"):
        context(strategy_families=("impulse-scalp", "impulse-scalp"))
    with pytest.raises(ValueError, match="liquidity|capacity|non-negative"):
        context(executable_exit_capacity_quote=-1.0)
    with pytest.raises(ValueError, match="cost|non-negative"):
        context(expected_round_trip_cost_bps=-0.1)


def test_policy_requires_explicit_valid_bucket_contracts() -> None:
    value = policy()
    assert value.partition is FastForecastEvaluationPartition.TEST
    with pytest.raises(ValueError, match="probability_bucket_count"):
        policy(probability_bucket_count=1)
    with pytest.raises(ValueError, match="liquidity|increasing"):
        policy(liquidity_capacity_quote_boundaries=(10.0, 10.0))
    with pytest.raises(ValueError, match="cost|non-negative"):
        policy(round_trip_cost_bps_boundaries=(-1.0, 5.0))
    with pytest.raises(ValueError, match="epsilon"):
        policy(binary_log_loss_clip_epsilon=0.5)


def test_continuous_metrics_reject_arithmetic_contradictions() -> None:
    value = FastContinuousForecastMetrics(
        observation_count=2,
        mean_predicted_value=2.0,
        mean_actual_value=1.0,
        mean_error=1.0,
        mean_absolute_error=1.0,
        root_mean_squared_error=1.0,
    )
    assert value.mean_error == 1.0
    with pytest.raises(ValueError, match="mean_error|reconcile"):
        FastContinuousForecastMetrics(
            observation_count=2,
            mean_predicted_value=2.0,
            mean_actual_value=1.0,
            mean_error=0.5,
            mean_absolute_error=1.0,
            root_mean_squared_error=1.0,
        )


def test_binary_metrics_require_reconciling_calibration_buckets() -> None:
    buckets = (
        FastCalibrationBucket(
            bucket_index=0,
            lower_probability=0.0,
            upper_probability=0.5,
            observation_count=1,
            mean_predicted_probability=0.25,
            observed_positive_rate=0.0,
            absolute_calibration_gap=0.25,
        ),
        FastCalibrationBucket(
            bucket_index=1,
            lower_probability=0.5,
            upper_probability=1.0,
            observation_count=1,
            mean_predicted_probability=0.75,
            observed_positive_rate=1.0,
            absolute_calibration_gap=0.25,
        ),
    )
    value = FastBinaryForecastMetrics(
        observation_count=2,
        positive_count=1,
        mean_predicted_probability=0.5,
        brier_score=0.0625,
        log_loss=0.2876820724517809,
        expected_calibration_error=0.25,
        calibration_buckets=buckets,
    )
    assert value.positive_count == 1
    with pytest.raises(ValueError, match="bucket|reconcile|observation"):
        FastBinaryForecastMetrics(
            observation_count=3,
            positive_count=1,
            mean_predicted_probability=0.5,
            brier_score=0.1,
            log_loss=0.2,
            expected_calibration_error=0.25,
            calibration_buckets=buckets,
        )
