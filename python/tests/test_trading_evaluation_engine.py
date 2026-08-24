from __future__ import annotations

from dataclasses import fields
import inspect
import subprocess
import sys

import pytest

from shreks_brain.evaluation import (
    EvaluatedTrade,
    ProbabilityObservation,
    TradingEvaluationPolicy,
    evaluate_trading_performance,
)


CANDIDATE = "challenger-v1"


def _policy(
    *, starting_equity: float = 100.0, buckets: int = 4
) -> TradingEvaluationPolicy:
    return TradingEvaluationPolicy(
        version="eval-v1",
        starting_equity_usd=starting_equity,
        calibration_bucket_count=buckets,
    )


def _trade(
    position_id: str,
    opened: int,
    closed: int,
    net: float,
    friction: float,
    explicit: float,
    setup: str,
    regime: str,
    *,
    candidate_version: str = CANDIDATE,
    entry: float = 100.0,
    turnover: float = 200.0,
) -> EvaluatedTrade:
    return EvaluatedTrade(
        candidate_version=candidate_version,
        position_id=position_id,
        candidate_mint=f"mint-{position_id}",
        setup_name=setup,
        market_regime=regime,
        opened_at_unix_ms=opened,
        closed_at_unix_ms=closed,
        entry_notional_usd=entry,
        turnover_usd=turnover,
        gross_pnl_usd=net + friction + explicit,
        execution_friction_usd=friction,
        explicit_cost_usd=explicit,
        net_pnl_usd=net,
    )


def _trades() -> tuple[EvaluatedTrade, ...]:
    # Intentionally non-canonical input order.
    return (
        _trade("p3", 250, 400, 0.0, 0.5, 0.5, "fresh", "HOT"),
        _trade("p1", 100, 200, 20.0, 1.0, 1.0, "fresh", "NORMAL"),
        _trade("p4", 350, 500, -5.0, 1.0, 1.0, "graduation", "NORMAL"),
        _trade("p2", 150, 300, -10.0, 2.0, 1.0, "graduation", "HOT"),
    )


def _observation(
    mint: str,
    as_of: int,
    probability: float,
    target: bool,
    *,
    candidate_version: str = CANDIDATE,
) -> ProbabilityObservation:
    return ProbabilityObservation(
        candidate_version=candidate_version,
        model_version="model-v1",
        candidate_mint=mint,
        as_of_unix_ms=as_of,
        positive_probability=probability,
        target_positive=target,
        setup_name="fresh",
        market_regime="NORMAL",
        fold_name="fold-1",
    )


def _observations() -> tuple[ProbabilityObservation, ...]:
    # Five observations on purpose: calibration is not restricted to four trades.
    return (
        _observation("e", 500, 0.8, False),
        _observation("a", 100, 0.1, False),
        _observation("d", 400, 1.0, True),
        _observation("b", 200, 0.4, True),
        _observation("c", 300, 0.6, True),
    )


def test_overall_metrics_are_net_after_costs_and_hand_reconciled() -> None:
    report = evaluate_trading_performance(
        _trades(), _observations(), _policy(), CANDIDATE
    )
    metrics = report.metrics

    assert metrics.trade_count == 4
    assert (metrics.win_count, metrics.loss_count, metrics.flat_count) == (1, 2, 1)
    assert metrics.gross_pnl_usd == pytest.approx(13.0)
    assert metrics.execution_friction_usd == pytest.approx(4.5)
    assert metrics.explicit_cost_usd == pytest.approx(3.5)
    assert metrics.total_cost_usd == pytest.approx(8.0)
    assert metrics.net_pnl_usd == pytest.approx(5.0)
    assert metrics.net_expectancy_usd == pytest.approx(1.25)
    assert metrics.net_expectancy_pct == pytest.approx(1.25)
    assert metrics.profit_factor == pytest.approx(20.0 / 15.0)
    assert metrics.average_winner_usd == pytest.approx(20.0)
    assert metrics.average_loser_usd == pytest.approx(-7.5)
    assert metrics.win_rate == pytest.approx(0.25)
    assert metrics.turnover_usd == pytest.approx(800.0)
    assert metrics.turnover_to_starting_equity == pytest.approx(8.0)
    assert metrics.cost_burden_pct == pytest.approx(1.0)


def test_realized_equity_drawdown_uses_canonical_close_order() -> None:
    report = evaluate_trading_performance(
        _trades(), (), _policy(), CANDIDATE
    )
    assert report.metrics.maximum_drawdown_usd == pytest.approx(15.0)
    assert report.metrics.maximum_drawdown_pct == pytest.approx(12.5)

    reordered = evaluate_trading_performance(
        tuple(reversed(_trades())), (), _policy(), CANDIDATE
    )
    assert reordered == report


def test_equity_below_zero_fails_closed() -> None:
    bankrupting = (
        _trade("bad", 1, 2, -101.0, 0.0, 0.0, "fresh", "NORMAL"),
    )
    with pytest.raises(ValueError, match="equity"):
        evaluate_trading_performance(bankrupting, (), _policy(), CANDIDATE)


def test_profit_factor_no_losses_is_none_and_all_losses_is_zero() -> None:
    winners = (
        _trade("win", 1, 2, 5.0, 0.0, 0.0, "fresh", "NORMAL"),
    )
    winner_report = evaluate_trading_performance(winners, (), _policy(), CANDIDATE)
    assert winner_report.metrics.profit_factor is None

    losers = (
        _trade("loss", 1, 2, -5.0, 0.0, 0.0, "fresh", "NORMAL"),
    )
    loser_report = evaluate_trading_performance(losers, (), _policy(), CANDIDATE)
    assert loser_report.metrics.profit_factor == 0.0


def test_empty_trade_population_has_explicit_undefined_metrics() -> None:
    report = evaluate_trading_performance((), (), _policy(), CANDIDATE)
    metrics = report.metrics
    assert metrics.trade_count == 0
    assert metrics.gross_pnl_usd == 0.0
    assert metrics.net_pnl_usd == 0.0
    assert metrics.maximum_drawdown_usd == 0.0
    assert metrics.maximum_drawdown_pct == 0.0
    assert metrics.turnover_usd == 0.0
    assert metrics.total_cost_usd == 0.0
    assert metrics.net_expectancy_usd is None
    assert metrics.net_expectancy_pct is None
    assert metrics.profit_factor is None
    assert metrics.average_winner_usd is None
    assert metrics.average_loser_usd is None
    assert metrics.win_rate is None
    assert metrics.cost_burden_pct is None
    assert report.setup_performance == ()
    assert report.regime_performance == ()
    assert report.calibration is None


def test_setup_and_regime_segments_reuse_global_metric_formulas() -> None:
    report = evaluate_trading_performance(_trades(), (), _policy(), CANDIDATE)

    assert tuple(value.segment_name for value in report.setup_performance) == (
        "fresh",
        "graduation",
    )
    fresh, graduation = report.setup_performance
    assert fresh.metrics.trade_count == 2
    assert fresh.metrics.net_pnl_usd == pytest.approx(20.0)
    assert fresh.metrics.net_expectancy_usd == pytest.approx(10.0)
    assert fresh.metrics.profit_factor is None
    assert fresh.metrics.win_rate == pytest.approx(0.5)
    assert fresh.metrics.maximum_drawdown_usd == pytest.approx(0.0)
    assert graduation.metrics.trade_count == 2
    assert graduation.metrics.net_pnl_usd == pytest.approx(-15.0)
    assert graduation.metrics.profit_factor == 0.0
    assert graduation.metrics.maximum_drawdown_usd == pytest.approx(15.0)
    assert graduation.metrics.maximum_drawdown_pct == pytest.approx(15.0)

    assert tuple(value.segment_name for value in report.regime_performance) == (
        "HOT",
        "NORMAL",
    )
    hot, normal = report.regime_performance
    assert hot.metrics.trade_count == 2
    assert hot.metrics.net_pnl_usd == pytest.approx(-10.0)
    assert normal.metrics.trade_count == 2
    assert normal.metrics.net_pnl_usd == pytest.approx(15.0)
    assert normal.metrics.maximum_drawdown_usd == pytest.approx(5.0)
    assert normal.metrics.maximum_drawdown_pct == pytest.approx(5.0 / 120.0 * 100.0)
    assert sum(value.metrics.trade_count for value in report.setup_performance) == 4
    assert sum(value.metrics.trade_count for value in report.regime_performance) == 4


def test_calibration_uses_all_unseen_observations_and_fixed_buckets() -> None:
    report = evaluate_trading_performance(
        _trades(), _observations(), _policy(), CANDIDATE
    )
    calibration = report.calibration
    assert calibration is not None
    assert calibration.observation_count == 5
    assert calibration.positive_count == 3
    assert calibration.brier_score == pytest.approx(0.234)
    assert calibration.expected_calibration_error == pytest.approx(0.38)
    assert len(calibration.buckets) == 4

    first, second, third, last = calibration.buckets
    assert (first.lower_probability, first.upper_probability) == (0.0, 0.25)
    assert first.observation_count == 1
    assert first.mean_predicted_probability == pytest.approx(0.1)
    assert first.observed_positive_rate == 0.0
    assert second.absolute_calibration_gap == pytest.approx(0.6)
    assert third.absolute_calibration_gap == pytest.approx(0.4)
    assert last.observation_count == 2
    assert last.mean_predicted_probability == pytest.approx(0.9)
    assert last.observed_positive_rate == pytest.approx(0.5)
    assert last.absolute_calibration_gap == pytest.approx(0.4)


def test_empty_calibration_buckets_are_retained_and_one_belongs_to_last_bucket() -> None:
    observations = (
        _observation("zero", 1, 0.0, False),
        _observation("one", 2, 1.0, True),
    )
    report = evaluate_trading_performance(
        (), observations, _policy(buckets=4), CANDIDATE
    )
    calibration = report.calibration
    assert calibration is not None
    assert tuple(value.observation_count for value in calibration.buckets) == (1, 0, 0, 1)
    assert calibration.buckets[1].mean_predicted_probability is None
    assert calibration.buckets[2].observed_positive_rate is None
    assert calibration.buckets[-1].mean_predicted_probability == 1.0


def test_input_order_does_not_change_report_or_fingerprint() -> None:
    left = evaluate_trading_performance(
        _trades(), _observations(), _policy(), CANDIDATE
    )
    right = evaluate_trading_performance(
        tuple(reversed(_trades())),
        tuple(reversed(_observations())),
        _policy(),
        CANDIDATE,
    )
    assert left == right
    assert len(left.evaluation_fingerprint_sha256) == 64


def test_engine_fails_closed_for_duplicate_identity_type_and_candidate_mismatch() -> None:
    with pytest.raises(ValueError, match="trades"):
        evaluate_trading_performance([], (), _policy(), CANDIDATE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="probability_observations"):
        evaluate_trading_performance((), [], _policy(), CANDIDATE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="policy"):
        evaluate_trading_performance((), (), object(), CANDIDATE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="candidate_version"):
        evaluate_trading_performance((), (), _policy(), "")

    duplicate_trade = _trades()[0]
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_trading_performance(
            (duplicate_trade, duplicate_trade), (), _policy(), CANDIDATE
        )

    duplicate_observation = _observations()[0]
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_trading_performance(
            (),
            (duplicate_observation, duplicate_observation),
            _policy(),
            CANDIDATE,
        )

    wrong_trade = _trade(
        "wrong", 1, 2, 1.0, 0.0, 0.0, "fresh", "NORMAL",
        candidate_version="other",
    )
    with pytest.raises(ValueError, match="candidate_version"):
        evaluate_trading_performance((wrong_trade,), (), _policy(), CANDIDATE)

    wrong_observation = _observation(
        "wrong", 1, 0.5, True, candidate_version="other"
    )
    with pytest.raises(ValueError, match="candidate_version"):
        evaluate_trading_performance((), (wrong_observation,), _policy(), CANDIDATE)


def test_result_contract_has_no_winner_or_promotion_authority_fields() -> None:
    import shreks_brain.evaluation as evaluation

    forbidden = (
        "winner",
        "beat_baseline",
        "promotion",
        "promote",
        "shadow_authority",
        "live_authority",
    )
    for cls in (
        evaluation.TradingPerformanceMetrics,
        evaluation.CalibrationReport,
        evaluation.TradingEvaluationReport,
    ):
        names = tuple(value.name for value in fields(cls))
        assert not any(token in name for name in names for token in forbidden)


def test_import_and_production_source_keep_dependency_and_io_firewalls() -> None:
    code = (
        "import sys; import shreks_brain.evaluation; "
        "assert 'sklearn' not in sys.modules; "
        "assert 'pyarrow' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)

    import shreks_brain.evaluation.engine as engine

    source = inspect.getsource(engine).lower()
    for forbidden in (
        "import sqlite3",
        "import pyarrow",
        "from pathlib",
        "import pathlib",
        "import requests",
        "import random",
        "from time import",
        "import time",
    ):
        assert forbidden not in source
