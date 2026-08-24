from __future__ import annotations

from dataclasses import FrozenInstanceError
import math

import pytest

from shreks_brain.evaluation import (
    TRADING_EVALUATION_SCHEMA_VERSION,
    CalibrationBucket,
    CalibrationReport,
    EvaluatedTrade,
    ProbabilityObservation,
    SegmentPerformance,
    TradingEvaluationPolicy,
    TradingEvaluationReport,
    TradingPerformanceMetrics,
)


def _policy(**overrides: object) -> TradingEvaluationPolicy:
    values: dict[str, object] = {
        "version": "eval-policy-v1",
        "starting_equity_usd": 1_000.0,
        "calibration_bucket_count": 2,
    }
    values.update(overrides)
    return TradingEvaluationPolicy(**values)  # type: ignore[arg-type]


def _trade(**overrides: object) -> EvaluatedTrade:
    values: dict[str, object] = {
        "candidate_version": "challenger-v1",
        "position_id": "position-1",
        "candidate_mint": "mint-a",
        "setup_name": "fresh_launch_continuation",
        "market_regime": "NORMAL",
        "opened_at_unix_ms": 1_000,
        "closed_at_unix_ms": 2_000,
        "entry_notional_usd": 100.0,
        "turnover_usd": 210.0,
        "gross_pnl_usd": 12.0,
        "execution_friction_usd": 1.0,
        "explicit_cost_usd": 1.0,
        "net_pnl_usd": 10.0,
    }
    values.update(overrides)
    return EvaluatedTrade(**values)  # type: ignore[arg-type]


def _observation(**overrides: object) -> ProbabilityObservation:
    values: dict[str, object] = {
        "candidate_version": "challenger-v1",
        "model_version": "model-v1",
        "candidate_mint": "mint-a",
        "as_of_unix_ms": 2_000,
        "positive_probability": 0.75,
        "target_positive": True,
        "setup_name": "fresh_launch_continuation",
        "market_regime": "NORMAL",
        "fold_name": "fold-1",
    }
    values.update(overrides)
    return ProbabilityObservation(**values)  # type: ignore[arg-type]


def _metrics(**overrides: object) -> TradingPerformanceMetrics:
    values: dict[str, object] = {
        "trade_count": 1,
        "win_count": 1,
        "loss_count": 0,
        "flat_count": 0,
        "gross_pnl_usd": 12.0,
        "net_pnl_usd": 10.0,
        "net_expectancy_usd": 10.0,
        "net_expectancy_pct": 10.0,
        "profit_factor": None,
        "maximum_drawdown_usd": 0.0,
        "maximum_drawdown_pct": 0.0,
        "average_winner_usd": 10.0,
        "average_loser_usd": None,
        "win_rate": 1.0,
        "turnover_usd": 210.0,
        "turnover_to_starting_equity": 0.21,
        "execution_friction_usd": 1.0,
        "explicit_cost_usd": 1.0,
        "total_cost_usd": 2.0,
        "cost_burden_pct": 2.0 / 210.0 * 100.0,
    }
    values.update(overrides)
    return TradingPerformanceMetrics(**values)  # type: ignore[arg-type]


def _bucket(**overrides: object) -> CalibrationBucket:
    values: dict[str, object] = {
        "bucket_index": 0,
        "lower_probability": 0.0,
        "upper_probability": 0.5,
        "observation_count": 1,
        "mean_predicted_probability": 0.25,
        "observed_positive_rate": 0.0,
        "absolute_calibration_gap": 0.25,
    }
    values.update(overrides)
    return CalibrationBucket(**values)  # type: ignore[arg-type]


def _calibration() -> CalibrationReport:
    return CalibrationReport(
        observation_count=2,
        positive_count=1,
        brier_score=0.0625,
        expected_calibration_error=0.25,
        buckets=(
            _bucket(),
            _bucket(
                bucket_index=1,
                lower_probability=0.5,
                upper_probability=1.0,
                mean_predicted_probability=0.75,
                observed_positive_rate=1.0,
                absolute_calibration_gap=0.25,
            ),
        ),
    )


def _report(**overrides: object) -> TradingEvaluationReport:
    metrics = _metrics()
    values: dict[str, object] = {
        "schema_version": TRADING_EVALUATION_SCHEMA_VERSION,
        "policy_version": "eval-policy-v1",
        "candidate_version": "challenger-v1",
        "metrics": metrics,
        "calibration": _calibration(),
        "setup_performance": (
            SegmentPerformance(
                segment_name="fresh_launch_continuation", metrics=metrics
            ),
        ),
        "regime_performance": (
            SegmentPerformance(segment_name="NORMAL", metrics=metrics),
        ),
        "evaluation_fingerprint_sha256": "a" * 64,
    }
    values.update(overrides)
    return TradingEvaluationReport(**values)  # type: ignore[arg-type]


def test_schema_version_and_contracts_are_frozen_slotted() -> None:
    assert TRADING_EVALUATION_SCHEMA_VERSION == "e5-trading-evaluation-v1"
    policy = _policy()
    trade = _trade()
    observation = _observation()
    metrics = _metrics()
    bucket = _bucket()
    calibration = _calibration()
    segment = SegmentPerformance(segment_name="NORMAL", metrics=metrics)
    report = _report()

    for value in (
        policy,
        trade,
        observation,
        metrics,
        bucket,
        calibration,
        segment,
        report,
    ):
        assert hasattr(type(value), "__slots__")
        with pytest.raises(FrozenInstanceError):
            value.__setattr__(next(iter(value.__slots__)), None)


def test_policy_rejects_invalid_values() -> None:
    for kwargs in (
        {"version": ""},
        {"starting_equity_usd": 0.0},
        {"starting_equity_usd": float("inf")},
        {"calibration_bucket_count": True},
        {"calibration_bucket_count": 1},
        {"calibration_bucket_count": 101},
    ):
        with pytest.raises(ValueError):
            _policy(**kwargs)


def test_trade_reconciles_closed_economics() -> None:
    trade = _trade()
    assert trade.net_pnl_usd == pytest.approx(
        trade.gross_pnl_usd
        - trade.execution_friction_usd
        - trade.explicit_cost_usd
    )

    for kwargs in (
        {"candidate_version": ""},
        {"position_id": ""},
        {"candidate_mint": ""},
        {"setup_name": ""},
        {"market_regime": ""},
        {"opened_at_unix_ms": True},
        {"opened_at_unix_ms": -1},
        {"closed_at_unix_ms": 999},
        {"entry_notional_usd": 0.0},
        {"turnover_usd": 99.0},
        {"gross_pnl_usd": math.nan},
        {"execution_friction_usd": -0.01},
        {"explicit_cost_usd": -0.01},
        {"net_pnl_usd": 9.0},
    ):
        with pytest.raises(ValueError):
            _trade(**kwargs)


def test_probability_observation_rejects_invalid_probability_target_and_identity() -> None:
    assert _observation(positive_probability=0.0).positive_probability == 0.0
    assert _observation(positive_probability=1.0).positive_probability == 1.0

    for kwargs in (
        {"candidate_version": ""},
        {"model_version": ""},
        {"candidate_mint": ""},
        {"setup_name": ""},
        {"market_regime": ""},
        {"fold_name": ""},
        {"as_of_unix_ms": True},
        {"as_of_unix_ms": -1},
        {"positive_probability": -0.01},
        {"positive_probability": 1.01},
        {"positive_probability": math.inf},
        {"target_positive": 1},
    ):
        with pytest.raises(ValueError):
            _observation(**kwargs)


def test_metrics_validate_counts_and_undefined_semantics() -> None:
    empty = TradingPerformanceMetrics(
        trade_count=0,
        win_count=0,
        loss_count=0,
        flat_count=0,
        gross_pnl_usd=0.0,
        net_pnl_usd=0.0,
        net_expectancy_usd=None,
        net_expectancy_pct=None,
        profit_factor=None,
        maximum_drawdown_usd=0.0,
        maximum_drawdown_pct=0.0,
        average_winner_usd=None,
        average_loser_usd=None,
        win_rate=None,
        turnover_usd=0.0,
        turnover_to_starting_equity=0.0,
        execution_friction_usd=0.0,
        explicit_cost_usd=0.0,
        total_cost_usd=0.0,
        cost_burden_pct=None,
    )
    assert empty.trade_count == 0

    invalid = (
        {"trade_count": 2},
        {"average_winner_usd": None},
        {"average_loser_usd": -1.0},
        {"win_rate": None},
        {"maximum_drawdown_usd": -1.0},
        {"maximum_drawdown_pct": 101.0},
        {"turnover_usd": -1.0},
        {"execution_friction_usd": -1.0},
        {"explicit_cost_usd": -1.0},
        {"total_cost_usd": 3.0},
        {"cost_burden_pct": -1.0},
    )
    for kwargs in invalid:
        with pytest.raises(ValueError):
            _metrics(**kwargs)


def test_calibration_bucket_requires_stable_empty_and_non_empty_shapes() -> None:
    empty = CalibrationBucket(
        bucket_index=0,
        lower_probability=0.0,
        upper_probability=0.5,
        observation_count=0,
        mean_predicted_probability=None,
        observed_positive_rate=None,
        absolute_calibration_gap=None,
    )
    assert empty.observation_count == 0

    for kwargs in (
        {"bucket_index": -1},
        {"lower_probability": -0.1},
        {"upper_probability": 1.1},
        {"upper_probability": 0.0},
        {"observation_count": -1},
        {"mean_predicted_probability": None},
        {"observed_positive_rate": None},
        {"absolute_calibration_gap": None},
        {"absolute_calibration_gap": 0.1},
    ):
        with pytest.raises(ValueError):
            _bucket(**kwargs)

    with pytest.raises(ValueError):
        CalibrationBucket(
            bucket_index=0,
            lower_probability=0.0,
            upper_probability=0.5,
            observation_count=0,
            mean_predicted_probability=0.1,
            observed_positive_rate=None,
            absolute_calibration_gap=None,
        )


def test_calibration_report_requires_contiguous_bucket_partition_and_counts() -> None:
    report = _calibration()
    assert report.observation_count == 2

    with pytest.raises(ValueError):
        CalibrationReport(
            observation_count=2,
            positive_count=1,
            brier_score=0.1,
            expected_calibration_error=0.1,
            buckets=(report.buckets[1], report.buckets[0]),
        )
    with pytest.raises(ValueError):
        CalibrationReport(
            observation_count=3,
            positive_count=1,
            brier_score=0.1,
            expected_calibration_error=0.1,
            buckets=report.buckets,
        )
    with pytest.raises(ValueError):
        CalibrationReport(
            observation_count=2,
            positive_count=3,
            brier_score=0.1,
            expected_calibration_error=0.1,
            buckets=report.buckets,
        )


def test_segment_and_report_reconcile_counts_order_and_fingerprint() -> None:
    report = _report()
    assert report.metrics.trade_count == 1

    with pytest.raises(ValueError):
        SegmentPerformance(segment_name="", metrics=_metrics())

    second = SegmentPerformance(
        segment_name="graduation_breakout",
        metrics=_metrics(
            trade_count=0,
            win_count=0,
            loss_count=0,
            flat_count=0,
            gross_pnl_usd=0.0,
            net_pnl_usd=0.0,
            net_expectancy_usd=None,
            net_expectancy_pct=None,
            average_winner_usd=None,
            win_rate=None,
            turnover_usd=0.0,
            turnover_to_starting_equity=0.0,
            execution_friction_usd=0.0,
            explicit_cost_usd=0.0,
            total_cost_usd=0.0,
            cost_burden_pct=None,
        ),
    )
    with pytest.raises(ValueError):
        _report(setup_performance=(report.setup_performance[0], second))
    with pytest.raises(ValueError):
        _report(
            setup_performance=(
                report.setup_performance[0],
                report.setup_performance[0],
            )
        )
    with pytest.raises(ValueError):
        _report(evaluation_fingerprint_sha256="ABC")
    with pytest.raises(ValueError):
        _report(schema_version="wrong")
