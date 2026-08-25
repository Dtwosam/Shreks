from __future__ import annotations

from dataclasses import dataclass

from .engine import evaluate_trading_performance
from .models import (
    EvaluatedTrade,
    ProbabilityObservation,
    TradingEvaluationPolicy,
    TradingEvaluationReport,
)


@dataclass(frozen=True, slots=True)
class TradingEvaluationEvidence:
    candidate_version: str
    policy: TradingEvaluationPolicy
    trades: tuple[EvaluatedTrade, ...]
    probability_observations: tuple[ProbabilityObservation, ...]
    report: TradingEvaluationReport

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_version, str) or not self.candidate_version.strip():
            raise ValueError("candidate_version must be a non-empty string")
        if type(self.policy) is not TradingEvaluationPolicy:
            raise ValueError("policy must be an exact TradingEvaluationPolicy")
        if not isinstance(self.trades, tuple):
            raise ValueError("trades must be a tuple")
        if not isinstance(self.probability_observations, tuple):
            raise ValueError("probability_observations must be a tuple")
        if any(type(trade) is not EvaluatedTrade for trade in self.trades):
            raise ValueError("trades must contain exact EvaluatedTrade values")
        if any(
            type(observation) is not ProbabilityObservation
            for observation in self.probability_observations
        ):
            raise ValueError(
                "probability_observations must contain exact ProbabilityObservation values"
            )
        if type(self.report) is not TradingEvaluationReport:
            raise ValueError("report must be an exact TradingEvaluationReport")
        if any(
            trade.candidate_version != self.candidate_version for trade in self.trades
        ):
            raise ValueError(
                "trade candidate_version must match evidence candidate_version"
            )
        if any(
            observation.candidate_version != self.candidate_version
            for observation in self.probability_observations
        ):
            raise ValueError(
                "probability observation candidate_version must match evidence candidate_version"
            )
        if self.report.candidate_version != self.candidate_version:
            raise ValueError(
                "report candidate_version must match evidence candidate_version"
            )
        if self.report.policy_version != self.policy.version:
            raise ValueError("report policy_version must match evidence policy version")

        canonical_trades = tuple(
            sorted(
                self.trades,
                key=lambda trade: (
                    trade.closed_at_unix_ms,
                    trade.opened_at_unix_ms,
                    trade.position_id,
                    trade.candidate_mint,
                ),
            )
        )
        if self.trades != canonical_trades:
            raise ValueError("trades must be in sealed E5 canonical order")

        canonical_observations = tuple(
            sorted(
                self.probability_observations,
                key=lambda observation: (
                    observation.as_of_unix_ms,
                    observation.candidate_mint,
                ),
            )
        )
        if self.probability_observations != canonical_observations:
            raise ValueError(
                "probability_observations must be in sealed E5 canonical order"
            )

        rebuilt = evaluate_trading_performance(
            self.trades,
            self.probability_observations,
            self.policy,
            self.candidate_version,
        )
        if self.report != rebuilt:
            raise ValueError("report must equal sealed E5 reconstruction from source evidence")
