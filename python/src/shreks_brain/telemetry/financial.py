from __future__ import annotations

import math

from shreks_brain.evaluation import TradingEvaluationPolicy, evaluate_trading_performance
from shreks_brain.paper import PaperPositionState
from shreks_brain.proof import (
    CandidateProofAssessment,
    PaperProofGateCode,
    PaperProofGateStatus,
)
from shreks_brain.promotion import PromotionAssessment

from .models import (
    LayerStatus,
    MoneyTelemetry,
    ProofRiskTelemetry,
    TradingPerformanceTelemetry,
)
from .sources import TelemetrySources


class TelemetryFinancialError(ValueError):
    """Raised when financial telemetry cannot be composed without invention."""


def compose_financial_telemetry(
    sources: TelemetrySources,
    *,
    evaluation_policy: TradingEvaluationPolicy,
) -> tuple[MoneyTelemetry, ProofRiskTelemetry]:
    if type(sources) is not TelemetrySources:
        raise TelemetryFinancialError("sources must be an exact TelemetrySources")
    if type(evaluation_policy) is not TradingEvaluationPolicy:
        raise TelemetryFinancialError(
            "evaluation_policy must be an exact TradingEvaluationPolicy"
        )
    if not math.isclose(
        evaluation_policy.starting_equity_usd,
        sources.state.ledger.starting_cash_usd,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise TelemetryFinancialError(
            "evaluation policy starting equity must match PAPER starting equity"
        )

    report = evaluate_trading_performance(
        trades=sources.evaluated_trades,
        probability_observations=(),
        policy=evaluation_policy,
        candidate_version=sources.manifest.candidate.candidate_version,
    )
    metrics = report.metrics
    performance = TradingPerformanceTelemetry(
        trade_count=metrics.trade_count,
        win_count=metrics.win_count,
        loss_count=metrics.loss_count,
        flat_count=metrics.flat_count,
        gross_pnl_usd=metrics.gross_pnl_usd,
        net_pnl_usd=metrics.net_pnl_usd,
        net_expectancy_usd=metrics.net_expectancy_usd,
        net_expectancy_pct=metrics.net_expectancy_pct,
        profit_factor=metrics.profit_factor,
        maximum_drawdown_usd=metrics.maximum_drawdown_usd,
        maximum_drawdown_pct=metrics.maximum_drawdown_pct,
        win_rate=metrics.win_rate,
        turnover_usd=metrics.turnover_usd,
        execution_friction_usd=metrics.execution_friction_usd,
        explicit_cost_usd=metrics.explicit_cost_usd,
        total_cost_usd=metrics.total_cost_usd,
        cost_burden_pct=metrics.cost_burden_pct,
    )

    ledger = sources.state.ledger
    open_positions = tuple(
        position
        for position in ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    money_errors: tuple[str, ...] = ()
    money_status = LayerStatus.HEALTHY
    if sources.accounting_status == "INCOMPLETE":
        money_status = LayerStatus.DEGRADED
        money_errors = ("PAPER_ACCOUNTING_INCOMPLETE",)
    money = MoneyTelemetry(
        status=money_status,
        observed_at_unix_ms=sources.as_of_unix_ms,
        source_errors=money_errors,
        starting_cash_usd=ledger.starting_cash_usd,
        cash_balance_usd=ledger.cash_balance_usd,
        realized_pnl_usd=ledger.realized_pnl_usd,
        unrealized_pnl_usd=ledger.unrealized_pnl_usd,
        accumulated_costs_usd=ledger.accumulated_costs_usd,
        open_cost_basis_usd=sum(
            position.open_cost_basis_usd for position in open_positions
        ),
        open_position_count=len(open_positions),
        daily_loss_usd=None,
        performance=performance,
    )

    proof_risk = _compose_proof_risk(sources)
    return money, proof_risk


def _compose_proof_risk(sources: TelemetrySources) -> ProofRiskTelemetry:
    source_errors = list(sources.optional_source_errors)
    proof = _latest_matching_proof(sources)
    promotion = _latest_matching_promotion(sources)

    projection: dict[str, int | float | str | None]
    if proof is None:
        projection = _empty_proof_projection()
        if not any(code.startswith("PROOF_ASSESSMENT_") for code in source_errors):
            source_errors.append("PROOF_ASSESSMENT_NOT_FOUND")
    else:
        try:
            projection = _proof_projection(proof)
        except ValueError:
            projection = _empty_proof_projection()
            source_errors.append("PROOF_ASSESSMENT_METRIC_INVALID")
            proof = None

    if promotion is None and not any(
        code.startswith("PROMOTION_ASSESSMENT_") for code in source_errors
    ):
        source_errors.append("PROMOTION_ASSESSMENT_NOT_FOUND")

    if sources.accounting_status == "INCOMPLETE":
        source_errors.append("PAPER_ACCOUNTING_INCOMPLETE")

    deduped_errors = tuple(dict.fromkeys(source_errors))
    status = LayerStatus.HEALTHY if not deduped_errors else LayerStatus.DEGRADED

    return ProofRiskTelemetry(
        status=status,
        observed_at_unix_ms=sources.as_of_unix_ms,
        source_errors=deduped_errors,
        proof_decision=(None if proof is None else proof.decision.value),
        proof_gate_count=(None if proof is None else len(proof.gates)),
        proof_pass_count=(
            None
            if proof is None
            else sum(
                gate.status is PaperProofGateStatus.PASS for gate in proof.gates
            )
        ),
        proof_fail_count=(
            None
            if proof is None
            else sum(
                gate.status is PaperProofGateStatus.FAIL for gate in proof.gates
            )
        ),
        proof_insufficient_count=(
            None
            if proof is None
            else sum(
                gate.status is PaperProofGateStatus.INSUFFICIENT
                for gate in proof.gates
            )
        ),
        promotion_decision=(
            None if promotion is None else promotion.decision.value
        ),
        promotion_gate_count=(
            None if promotion is None else len(promotion.gates)
        ),
        global_risk_halt=sources.manifest.global_risk_halt,
        accounting_integrity=sources.accounting_status,
        live_state="DISABLED",
        kill_switch_active=None,
        proof_trade_count=_optional_int(projection["trade_count"]),
        proof_distinct_mint_count=_optional_int(projection["distinct_mints"]),
        proof_net_expectancy_pct=_optional_float(projection["expectancy_pct"]),
        proof_profit_factor=_optional_float(projection["profit_factor"]),
        proof_maximum_drawdown_pct=_optional_float(projection["drawdown_pct"]),
        proof_cost_burden_pct=_optional_float(projection["cost_burden_pct"]),
    )


def _latest_matching_proof(
    sources: TelemetrySources,
) -> CandidateProofAssessment | None:
    candidate = sources.manifest.candidate
    matching = tuple(
        assessment
        for assessment in sources.proof_assessments
        if assessment.candidate_version == candidate.candidate_version
        and assessment.candidate_fingerprint_sha256
        == candidate.candidate_fingerprint_sha256
        and assessment.paper_run_id == sources.manifest.paper_run_id
        and assessment.evaluated_at_unix_ms <= sources.as_of_unix_ms
    )
    if not matching:
        return None
    return max(
        matching,
        key=lambda assessment: (
            assessment.evaluated_at_unix_ms,
            assessment.assessment_fingerprint_sha256,
        ),
    )


def _latest_matching_promotion(
    sources: TelemetrySources,
) -> PromotionAssessment | None:
    candidate = sources.manifest.candidate
    matching = tuple(
        assessment
        for assessment in sources.promotion_assessments
        if assessment.candidate_version == candidate.candidate_version
        and assessment.candidate_fingerprint_sha256
        == candidate.candidate_fingerprint_sha256
        and assessment.evaluated_at_unix_ms <= sources.as_of_unix_ms
    )
    if not matching:
        return None
    return max(
        matching,
        key=lambda assessment: (
            assessment.evaluated_at_unix_ms,
            assessment.assessment_fingerprint_sha256,
        ),
    )


def _proof_projection(
    assessment: CandidateProofAssessment,
) -> dict[str, int | float | str | None]:
    by_code = {gate.code: gate.observed_value for gate in assessment.gates}
    projection: dict[str, int | float | str | None] = {
        "trade_count": by_code[PaperProofGateCode.MIN_PAPER_TRADE_COUNT],
        "distinct_mints": by_code[PaperProofGateCode.MIN_PAPER_DISTINCT_MINT_COUNT],
        "expectancy_pct": by_code[PaperProofGateCode.MIN_PAPER_NET_EXPECTANCY_PCT],
        "profit_factor": by_code[PaperProofGateCode.MIN_PAPER_PROFIT_FACTOR],
        "drawdown_pct": by_code[PaperProofGateCode.MAX_PAPER_DRAWDOWN_PCT],
        "cost_burden_pct": by_code[PaperProofGateCode.MAX_PAPER_COST_BURDEN_PCT],
    }
    _optional_int(projection["trade_count"])
    _optional_int(projection["distinct_mints"])
    for name in (
        "expectancy_pct",
        "profit_factor",
        "drawdown_pct",
        "cost_burden_pct",
    ):
        _optional_float(projection[name])
    return projection


def _empty_proof_projection() -> dict[str, None]:
    return {
        "trade_count": None,
        "distinct_mints": None,
        "expectancy_pct": None,
        "profit_factor": None,
        "drawdown_pct": None,
        "cost_burden_pct": None,
    }


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("proof integer observation must be a non-negative integer")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("proof numeric observation must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("proof numeric observation must be finite")
    return result
