from __future__ import annotations

from dataclasses import fields, is_dataclass
import hashlib
import json
import math

from .models import (
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


_EQUITY_ABS_TOL = 1e-9


def evaluate_trading_performance(
    trades: tuple[EvaluatedTrade, ...],
    probability_observations: tuple[ProbabilityObservation, ...],
    policy: TradingEvaluationPolicy,
    candidate_version: str,
) -> TradingEvaluationReport:
    if not isinstance(trades, tuple):
        raise ValueError("trades must be a tuple")
    if not isinstance(probability_observations, tuple):
        raise ValueError("probability_observations must be a tuple")
    if type(policy) is not TradingEvaluationPolicy:
        raise ValueError("policy must be an exact TradingEvaluationPolicy")
    if not isinstance(candidate_version, str) or not candidate_version.strip():
        raise ValueError("candidate_version must be a non-empty string")

    canonical_trades = _canonical_trades(trades, candidate_version)
    canonical_observations = _canonical_observations(
        probability_observations, candidate_version
    )

    metrics = _performance_metrics(canonical_trades, policy.starting_equity_usd)
    setup_performance = _segments(
        canonical_trades,
        policy.starting_equity_usd,
        lambda trade: trade.setup_name,
    )
    regime_performance = _segments(
        canonical_trades,
        policy.starting_equity_usd,
        lambda trade: trade.market_regime,
    )
    calibration = _calibration_report(
        canonical_observations, policy.calibration_bucket_count
    )

    fingerprint = _evaluation_fingerprint(
        policy=policy,
        candidate_version=candidate_version,
        trades=canonical_trades,
        observations=canonical_observations,
        metrics=metrics,
        setup_performance=setup_performance,
        regime_performance=regime_performance,
        calibration=calibration,
    )
    return TradingEvaluationReport(
        schema_version=TRADING_EVALUATION_SCHEMA_VERSION,
        policy_version=policy.version,
        candidate_version=candidate_version,
        metrics=metrics,
        calibration=calibration,
        setup_performance=setup_performance,
        regime_performance=regime_performance,
        evaluation_fingerprint_sha256=fingerprint,
    )


def _canonical_trades(
    trades: tuple[EvaluatedTrade, ...], candidate_version: str
) -> tuple[EvaluatedTrade, ...]:
    seen_positions: set[str] = set()
    values: list[EvaluatedTrade] = []
    for trade in trades:
        if type(trade) is not EvaluatedTrade:
            raise ValueError("trades must contain exact EvaluatedTrade values")
        if trade.candidate_version != candidate_version:
            raise ValueError("trade candidate_version must match evaluation candidate_version")
        if trade.position_id in seen_positions:
            raise ValueError(f"duplicate trade position_id: {trade.position_id}")
        seen_positions.add(trade.position_id)
        values.append(trade)
    values.sort(
        key=lambda trade: (
            trade.closed_at_unix_ms,
            trade.opened_at_unix_ms,
            trade.position_id,
            trade.candidate_mint,
        )
    )
    return tuple(values)


def _canonical_observations(
    observations: tuple[ProbabilityObservation, ...], candidate_version: str
) -> tuple[ProbabilityObservation, ...]:
    seen: set[tuple[str, int]] = set()
    values: list[ProbabilityObservation] = []
    for observation in observations:
        if type(observation) is not ProbabilityObservation:
            raise ValueError(
                "probability_observations must contain exact ProbabilityObservation values"
            )
        if observation.candidate_version != candidate_version:
            raise ValueError(
                "probability observation candidate_version must match evaluation candidate_version"
            )
        identity = (observation.candidate_mint, observation.as_of_unix_ms)
        if identity in seen:
            raise ValueError(
                "duplicate probability observation identity: "
                f"{observation.candidate_mint}@{observation.as_of_unix_ms}"
            )
        seen.add(identity)
        values.append(observation)
    values.sort(key=lambda value: (value.as_of_unix_ms, value.candidate_mint))
    return tuple(values)


def _performance_metrics(
    trades: tuple[EvaluatedTrade, ...], starting_equity_usd: float
) -> TradingPerformanceMetrics:
    if not trades:
        return TradingPerformanceMetrics(
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

    wins = tuple(trade for trade in trades if trade.net_pnl_usd > 0.0)
    losses = tuple(trade for trade in trades if trade.net_pnl_usd < 0.0)
    flats = tuple(trade for trade in trades if trade.net_pnl_usd == 0.0)
    trade_count = len(trades)

    gross_pnl = math.fsum(trade.gross_pnl_usd for trade in trades)
    net_pnl = math.fsum(trade.net_pnl_usd for trade in trades)
    execution_friction = math.fsum(
        trade.execution_friction_usd for trade in trades
    )
    explicit_cost = math.fsum(trade.explicit_cost_usd for trade in trades)
    total_cost = execution_friction + explicit_cost
    turnover = math.fsum(trade.turnover_usd for trade in trades)

    sum_wins = math.fsum(trade.net_pnl_usd for trade in wins)
    sum_losses = math.fsum(trade.net_pnl_usd for trade in losses)
    profit_factor = None if not losses else sum_wins / abs(sum_losses)
    maximum_drawdown_usd, maximum_drawdown_pct = _maximum_drawdown(
        trades, starting_equity_usd
    )

    return TradingPerformanceMetrics(
        trade_count=trade_count,
        win_count=len(wins),
        loss_count=len(losses),
        flat_count=len(flats),
        gross_pnl_usd=gross_pnl,
        net_pnl_usd=net_pnl,
        net_expectancy_usd=net_pnl / trade_count,
        net_expectancy_pct=math.fsum(
            trade.net_pnl_usd / trade.entry_notional_usd * 100.0
            for trade in trades
        )
        / trade_count,
        profit_factor=profit_factor,
        maximum_drawdown_usd=maximum_drawdown_usd,
        maximum_drawdown_pct=maximum_drawdown_pct,
        average_winner_usd=(None if not wins else sum_wins / len(wins)),
        average_loser_usd=(None if not losses else sum_losses / len(losses)),
        win_rate=len(wins) / trade_count,
        turnover_usd=turnover,
        turnover_to_starting_equity=turnover / starting_equity_usd,
        execution_friction_usd=execution_friction,
        explicit_cost_usd=explicit_cost,
        total_cost_usd=total_cost,
        cost_burden_pct=total_cost / turnover * 100.0,
    )


def _maximum_drawdown(
    trades: tuple[EvaluatedTrade, ...], starting_equity_usd: float
) -> tuple[float, float]:
    equity = starting_equity_usd
    peak = starting_equity_usd
    maximum_drawdown = 0.0
    maximum_drawdown_pct = 0.0

    for trade in trades:
        equity += trade.net_pnl_usd
        if equity < -_EQUITY_ABS_TOL:
            raise ValueError(
                "realized evaluation equity cannot fall below zero under starting equity"
            )
        if equity < 0.0:
            equity = 0.0
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        drawdown_pct = drawdown / peak * 100.0
        if drawdown > maximum_drawdown:
            maximum_drawdown = drawdown
            maximum_drawdown_pct = drawdown_pct
    return maximum_drawdown, maximum_drawdown_pct


def _segments(
    trades: tuple[EvaluatedTrade, ...],
    starting_equity_usd: float,
    key_function,
) -> tuple[SegmentPerformance, ...]:
    groups: dict[str, list[EvaluatedTrade]] = {}
    for trade in trades:
        key = key_function(trade)
        groups.setdefault(key, []).append(trade)
    return tuple(
        SegmentPerformance(
            segment_name=name,
            metrics=_performance_metrics(tuple(groups[name]), starting_equity_usd),
        )
        for name in sorted(groups)
    )


def _calibration_report(
    observations: tuple[ProbabilityObservation, ...], bucket_count: int
) -> CalibrationReport | None:
    if not observations:
        return None

    bucket_values: list[list[ProbabilityObservation]] = [
        [] for _ in range(bucket_count)
    ]
    for observation in observations:
        index = min(int(observation.positive_probability * bucket_count), bucket_count - 1)
        bucket_values[index].append(observation)

    buckets: list[CalibrationBucket] = []
    for index, values in enumerate(bucket_values):
        lower = index / bucket_count
        upper = (index + 1) / bucket_count
        if not values:
            buckets.append(
                CalibrationBucket(
                    bucket_index=index,
                    lower_probability=lower,
                    upper_probability=upper,
                    observation_count=0,
                    mean_predicted_probability=None,
                    observed_positive_rate=None,
                    absolute_calibration_gap=None,
                )
            )
            continue
        mean_probability = math.fsum(
            value.positive_probability for value in values
        ) / len(values)
        observed_rate = sum(value.target_positive for value in values) / len(values)
        buckets.append(
            CalibrationBucket(
                bucket_index=index,
                lower_probability=lower,
                upper_probability=upper,
                observation_count=len(values),
                mean_predicted_probability=mean_probability,
                observed_positive_rate=observed_rate,
                absolute_calibration_gap=abs(mean_probability - observed_rate),
            )
        )

    total = len(observations)
    brier_score = math.fsum(
        (observation.positive_probability - float(observation.target_positive)) ** 2
        for observation in observations
    ) / total
    expected_calibration_error = math.fsum(
        (bucket.absolute_calibration_gap or 0.0)
        * bucket.observation_count
        / total
        for bucket in buckets
    )
    return CalibrationReport(
        observation_count=total,
        positive_count=sum(observation.target_positive for observation in observations),
        brier_score=brier_score,
        expected_calibration_error=expected_calibration_error,
        buckets=tuple(buckets),
    )


def _evaluation_fingerprint(
    *,
    policy: TradingEvaluationPolicy,
    candidate_version: str,
    trades: tuple[EvaluatedTrade, ...],
    observations: tuple[ProbabilityObservation, ...],
    metrics: TradingPerformanceMetrics,
    setup_performance: tuple[SegmentPerformance, ...],
    regime_performance: tuple[SegmentPerformance, ...],
    calibration: CalibrationReport | None,
) -> str:
    payload = {
        "schema_version": TRADING_EVALUATION_SCHEMA_VERSION,
        "policy": policy,
        "candidate_version": candidate_version,
        "trades": trades,
        "probability_observations": observations,
        "metrics": metrics,
        "setup_performance": setup_performance,
        "regime_performance": regime_performance,
        "calibration": calibration,
    }
    encoded = json.dumps(
        _canonical_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("evaluation fingerprint cannot contain non-finite floats")
        return {"float_hex": value.hex()}
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical_value(getattr(value, field.name))
            for field in fields(value)
        }
    raise TypeError(
        f"unsupported E5 evaluation fingerprint value: {type(value).__name__}"
    )
