from __future__ import annotations

from dataclasses import asdict, replace
import math

from shreks_brain.evaluation import EvaluatedTrade, TradingEvaluationReport
from shreks_brain.registry import (
    ChampionChallengerRegistry,
    RegistryCandidate,
    RegistryStatus,
)
from shreks_brain.shadow import (
    SHADOW_CHALLENGER_SCHEMA_VERSION,
    ShadowDecisionRecord,
    ShadowEvidenceLedger,
)

from .fingerprint import sha256_canonical
from .models import (
    PROMOTION_SCHEMA_VERSION,
    PromotionAssessment,
    PromotionDecision,
    PromotionGateCode,
    PromotionGateResult,
    PromotionGateStatus,
    PromotionPolicy,
)


_REL_TOL = 1e-12
_ABS_TOL = 1e-9


def evaluate_promotion(
    registry: ChampionChallengerRegistry,
    candidate_version: str,
    evaluation_report: TradingEvaluationReport,
    evaluated_trades: tuple[EvaluatedTrade, ...],
    shadow_ledger: ShadowEvidenceLedger,
    baseline_reports: tuple[TradingEvaluationReport, ...],
    policy: PromotionPolicy,
    evaluated_at_unix_ms: int,
) -> PromotionAssessment:
    _validate_inputs(
        registry,
        candidate_version,
        evaluation_report,
        evaluated_trades,
        shadow_ledger,
        baseline_reports,
        policy,
        evaluated_at_unix_ms,
    )
    candidate = next(
        (value for value in registry.candidates if value.candidate_version == candidate_version),
        None,
    )
    if candidate is None:
        raise ValueError(f"candidate '{candidate_version}' is not registered")

    candidate_shadow = tuple(
        value for value in shadow_ledger.records if value.candidate_version == candidate_version
    )
    latest_evidence_ms = candidate.registered_at_unix_ms
    if evaluated_trades:
        latest_evidence_ms = max(
            latest_evidence_ms,
            max(value.closed_at_unix_ms for value in evaluated_trades),
        )
    if candidate_shadow:
        latest_evidence_ms = max(
            latest_evidence_ms,
            max(value.as_of_unix_ms for value in candidate_shadow),
        )
    if evaluated_at_unix_ms < latest_evidence_ms:
        raise ValueError("evaluated_at_unix_ms cannot precede observed promotion evidence")

    ordered_trades = tuple(sorted(evaluated_trades, key=_trade_sort_key))
    trade_fingerprint = sha256_canonical(
        [asdict(value) for value in ordered_trades]
    )

    baselines = _canonical_baselines(baseline_reports, candidate_version)
    baseline_by_version = {value.candidate_version: value for value in baselines}
    champion = registry.current_champion()
    required_versions = set(policy.required_baseline_versions)
    if champion is not None and champion.candidate_version != candidate_version:
        required_versions.add(champion.candidate_version)
    required = tuple(sorted(required_versions))

    trade_summary = _summarize_trades(ordered_trades)
    shadow_summary = _summarize_shadow(candidate_shadow)

    gates: dict[PromotionGateCode, PromotionGateResult] = {}
    gates[PromotionGateCode.CURRENT_CHALLENGER] = _status_gate(
        PromotionGateCode.CURRENT_CHALLENGER,
        PromotionGateStatus.PASS
        if registry.current_status(candidate_version) is RegistryStatus.CHALLENGER
        else PromotionGateStatus.FAIL,
        registry.current_status(candidate_version).value,
        RegistryStatus.CHALLENGER.value,
        "candidate must currently be CHALLENGER",
    )

    complete_model_provenance = all(
        value is not None
        for value in (
            candidate.model_version,
            candidate.model_training_schema_version,
            candidate.model_training_fingerprint_sha256,
            candidate.training_started_at_unix_ms,
            candidate.training_ended_at_unix_ms,
            candidate.validation_schema_version,
            candidate.validation_policy_version,
            candidate.validation_run_fingerprint_sha256,
        )
    )
    gates[PromotionGateCode.MODEL_VALIDATION_PROVENANCE] = _status_gate(
        PromotionGateCode.MODEL_VALIDATION_PROVENANCE,
        PromotionGateStatus.PASS if complete_model_provenance else PromotionGateStatus.FAIL,
        "complete" if complete_model_provenance else "incomplete",
        "complete",
        "E3 model and E4 validation provenance must be complete",
    )

    evaluation_matches = _evaluation_matches_registry(candidate, evaluation_report)
    gates[PromotionGateCode.EVALUATION_MATCH] = _status_gate(
        PromotionGateCode.EVALUATION_MATCH,
        PromotionGateStatus.PASS if evaluation_matches else PromotionGateStatus.FAIL,
        evaluation_report.evaluation_fingerprint_sha256,
        candidate.evaluation.evaluation_fingerprint_sha256,
        "E5 evaluation must match E6 persisted evaluation evidence",
    )

    trades_reconcile = _trades_reconcile_report(trade_summary, evaluation_report)
    gates[PromotionGateCode.TRADE_EVIDENCE_RECONCILIATION] = _status_gate(
        PromotionGateCode.TRADE_EVIDENCE_RECONCILIATION,
        PromotionGateStatus.PASS if trades_reconcile else PromotionGateStatus.FAIL,
        trade_summary["trade_count"],
        evaluation_report.metrics.trade_count,
        "raw E5 trade evidence must reconcile to the evaluation report",
    )

    gates[PromotionGateCode.MIN_TRADE_COUNT] = _minimum_gate(
        PromotionGateCode.MIN_TRADE_COUNT,
        trade_summary["trade_count"],
        policy.min_trade_count,
        insufficient=True,
    )
    gates[PromotionGateCode.MIN_EVALUATION_SPAN] = _minimum_gate(
        PromotionGateCode.MIN_EVALUATION_SPAN,
        trade_summary["span_ms"],
        policy.min_evaluation_span_ms,
        insufficient=True,
    )
    gates[PromotionGateCode.MIN_NET_EXPECTANCY_PCT] = _optional_minimum_gate(
        PromotionGateCode.MIN_NET_EXPECTANCY_PCT,
        evaluation_report.metrics.net_expectancy_pct,
        policy.min_net_expectancy_pct,
    )
    gates[PromotionGateCode.MIN_PROFIT_FACTOR] = _optional_minimum_gate(
        PromotionGateCode.MIN_PROFIT_FACTOR,
        evaluation_report.metrics.profit_factor,
        policy.min_profit_factor,
    )
    gates[PromotionGateCode.MAX_DRAWDOWN_PCT] = _maximum_gate(
        PromotionGateCode.MAX_DRAWDOWN_PCT,
        evaluation_report.metrics.maximum_drawdown_pct,
        policy.max_drawdown_pct,
    )
    gates[PromotionGateCode.MAX_COST_BURDEN_PCT] = _optional_maximum_gate(
        PromotionGateCode.MAX_COST_BURDEN_PCT,
        evaluation_report.metrics.cost_burden_pct,
        policy.max_cost_burden_pct,
    )
    calibration = evaluation_report.calibration
    gates[PromotionGateCode.MAX_BRIER_SCORE] = _optional_maximum_gate(
        PromotionGateCode.MAX_BRIER_SCORE,
        None if calibration is None else calibration.brier_score,
        policy.max_brier_score,
    )
    gates[PromotionGateCode.MAX_EXPECTED_CALIBRATION_ERROR] = _optional_maximum_gate(
        PromotionGateCode.MAX_EXPECTED_CALIBRATION_ERROR,
        None if calibration is None else calibration.expected_calibration_error,
        policy.max_expected_calibration_error,
    )

    missing_required = tuple(
        value for value in required if value not in baseline_by_version
    )
    wrong_policy = tuple(
        value.candidate_version
        for value in baselines
        if value.policy_version != evaluation_report.policy_version
    )
    if wrong_policy:
        baseline_coverage_status = PromotionGateStatus.FAIL
        baseline_coverage_observed: int | str = ",".join(wrong_policy)
    elif not required or missing_required:
        baseline_coverage_status = PromotionGateStatus.INSUFFICIENT
        baseline_coverage_observed = (
            "none-required" if not required else ",".join(missing_required)
        )
    else:
        baseline_coverage_status = PromotionGateStatus.PASS
        baseline_coverage_observed = len(required)
    gates[PromotionGateCode.BASELINE_COVERAGE] = _status_gate(
        PromotionGateCode.BASELINE_COVERAGE,
        baseline_coverage_status,
        baseline_coverage_observed,
        len(required),
        "all required comparable baselines must be present",
    )

    challenger_expectancy = evaluation_report.metrics.net_expectancy_pct
    if baseline_coverage_status is not PromotionGateStatus.PASS:
        baseline_advantage_status = (
            PromotionGateStatus.FAIL
            if baseline_coverage_status is PromotionGateStatus.FAIL
            else PromotionGateStatus.INSUFFICIENT
        )
        minimum_advantage: float | None = None
    elif challenger_expectancy is None:
        baseline_advantage_status = PromotionGateStatus.INSUFFICIENT
        minimum_advantage = None
    else:
        required_expectancies = tuple(
            baseline_by_version[value].metrics.net_expectancy_pct for value in required
        )
        if any(value is None for value in required_expectancies):
            baseline_advantage_status = PromotionGateStatus.INSUFFICIENT
            minimum_advantage = None
        else:
            minimum_advantage = min(
                challenger_expectancy - float(value) for value in required_expectancies
            )
            baseline_advantage_status = (
                PromotionGateStatus.PASS
                if minimum_advantage >= policy.min_baseline_expectancy_advantage_pct
                else PromotionGateStatus.FAIL
            )
    gates[PromotionGateCode.BASELINE_EXPECTANCY_ADVANTAGE] = _status_gate(
        PromotionGateCode.BASELINE_EXPECTANCY_ADVANTAGE,
        baseline_advantage_status,
        minimum_advantage,
        policy.min_baseline_expectancy_advantage_pct,
        "challenger expectancy must beat every required baseline by the policy margin",
    )

    winner_share = trade_summary["single_winner_share"]
    gates[PromotionGateCode.MAX_SINGLE_WINNER_SHARE] = _optional_maximum_gate(
        PromotionGateCode.MAX_SINGLE_WINNER_SHARE,
        winner_share,
        policy.max_single_winner_share_of_positive_pnl,
    )

    shadow_provenance_ok = _shadow_provenance_matches(candidate, candidate_shadow)
    gates[PromotionGateCode.SHADOW_PROVENANCE] = _status_gate(
        PromotionGateCode.SHADOW_PROVENANCE,
        PromotionGateStatus.PASS
        if shadow_provenance_ok
        else PromotionGateStatus.FAIL,
        "aligned" if shadow_provenance_ok else "mismatch",
        "aligned",
        "candidate E7 records must match E6 candidate/model provenance",
    )
    gates[PromotionGateCode.MIN_SHADOW_DECISION_COUNT] = _minimum_gate(
        PromotionGateCode.MIN_SHADOW_DECISION_COUNT,
        shadow_summary["count"],
        policy.min_shadow_decision_count,
        insufficient=True,
    )
    gates[PromotionGateCode.MIN_SHADOW_DISTINCT_MINT_COUNT] = _minimum_gate(
        PromotionGateCode.MIN_SHADOW_DISTINCT_MINT_COUNT,
        shadow_summary["distinct_mints"],
        policy.min_shadow_distinct_mint_count,
        insufficient=True,
    )
    gates[PromotionGateCode.MIN_SHADOW_SPAN] = _minimum_gate(
        PromotionGateCode.MIN_SHADOW_SPAN,
        shadow_summary["span_ms"],
        policy.min_shadow_span_ms,
        insufficient=True,
    )

    ordered_gates = tuple(gates[code] for code in sorted(PromotionGateCode, key=lambda value: value.value))
    decision = _decision(ordered_gates)
    baseline_identities = tuple(
        (value.candidate_version, value.evaluation_fingerprint_sha256)
        for value in baselines
    )
    draft = PromotionAssessment(
        schema_version=PROMOTION_SCHEMA_VERSION,
        policy_version=policy.version,
        candidate_version=candidate_version,
        candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
        registry_fingerprint_sha256=registry.registry_fingerprint_sha256,
        evaluation_fingerprint_sha256=evaluation_report.evaluation_fingerprint_sha256,
        trade_evidence_fingerprint_sha256=trade_fingerprint,
        shadow_ledger_fingerprint_sha256=shadow_ledger.ledger_fingerprint_sha256,
        baseline_evaluation_identities=baseline_identities,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        gates=ordered_gates,
        decision=decision,
        assessment_fingerprint_sha256="0" * 64,
    )
    return replace(
        draft,
        assessment_fingerprint_sha256=sha256_canonical(_assessment_material(draft)),
    )


def _validate_inputs(
    registry: object,
    candidate_version: object,
    evaluation_report: object,
    evaluated_trades: object,
    shadow_ledger: object,
    baseline_reports: object,
    policy: object,
    evaluated_at_unix_ms: object,
) -> None:
    if type(registry) is not ChampionChallengerRegistry:
        raise ValueError("registry must be an exact ChampionChallengerRegistry")
    if not isinstance(candidate_version, str) or not candidate_version.strip():
        raise ValueError("candidate_version must be a non-empty string")
    if type(evaluation_report) is not TradingEvaluationReport:
        raise ValueError("evaluation_report must be an exact TradingEvaluationReport")
    if not isinstance(evaluated_trades, tuple) or not all(
        type(value) is EvaluatedTrade for value in evaluated_trades
    ):
        raise ValueError("evaluated_trades must be a tuple of exact EvaluatedTrade values")
    if type(shadow_ledger) is not ShadowEvidenceLedger:
        raise ValueError("shadow_ledger must be an exact ShadowEvidenceLedger")
    if not isinstance(baseline_reports, tuple) or not all(
        type(value) is TradingEvaluationReport for value in baseline_reports
    ):
        raise ValueError("baseline_reports must be a tuple of exact TradingEvaluationReport values")
    if type(policy) is not PromotionPolicy:
        raise ValueError("policy must be an exact PromotionPolicy")
    if (
        isinstance(evaluated_at_unix_ms, bool)
        or not isinstance(evaluated_at_unix_ms, int)
        or evaluated_at_unix_ms < 0
    ):
        raise ValueError("evaluated_at_unix_ms must be a non-negative integer")


def _canonical_baselines(
    reports: tuple[TradingEvaluationReport, ...], candidate_version: str
) -> tuple[TradingEvaluationReport, ...]:
    versions = tuple(value.candidate_version for value in reports)
    if candidate_version in versions:
        raise ValueError("baseline report cannot be the challenger itself")
    if len(versions) != len(set(versions)):
        raise ValueError("baseline report candidate versions must be unique")
    return tuple(sorted(reports, key=lambda value: value.candidate_version))


def _evaluation_matches_registry(
    candidate: RegistryCandidate, report: TradingEvaluationReport
) -> bool:
    evidence = candidate.evaluation
    metrics = report.metrics
    calibration = report.calibration
    pairs = (
        (evidence.net_pnl_usd, metrics.net_pnl_usd),
        (evidence.net_expectancy_usd, metrics.net_expectancy_usd),
        (evidence.net_expectancy_pct, metrics.net_expectancy_pct),
        (evidence.profit_factor, metrics.profit_factor),
        (evidence.maximum_drawdown_usd, metrics.maximum_drawdown_usd),
        (evidence.maximum_drawdown_pct, metrics.maximum_drawdown_pct),
        (evidence.win_rate, metrics.win_rate),
        (evidence.turnover_usd, metrics.turnover_usd),
        (evidence.total_cost_usd, metrics.total_cost_usd),
        (evidence.brier_score, None if calibration is None else calibration.brier_score),
        (
            evidence.expected_calibration_error,
            None if calibration is None else calibration.expected_calibration_error,
        ),
    )
    return (
        report.candidate_version == candidate.candidate_version
        and report.schema_version == evidence.schema_version
        and report.policy_version == evidence.policy_version
        and report.evaluation_fingerprint_sha256 == evidence.evaluation_fingerprint_sha256
        and metrics.trade_count == evidence.trade_count
        and all(_optional_close(left, right) for left, right in pairs)
    )


def _summarize_trades(trades: tuple[EvaluatedTrade, ...]) -> dict[str, object]:
    count = len(trades)
    if not trades:
        return {
            "trade_count": 0,
            "gross_pnl_usd": 0.0,
            "net_pnl_usd": 0.0,
            "turnover_usd": 0.0,
            "total_cost_usd": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "flat_count": 0,
            "average_winner_usd": None,
            "average_loser_usd": None,
            "win_rate": None,
            "cost_burden_pct": None,
            "net_expectancy_usd": None,
            "net_expectancy_pct": None,
            "profit_factor": None,
            "span_ms": 0,
            "single_winner_share": None,
        }
    nets = tuple(value.net_pnl_usd for value in trades)
    winners = tuple(value for value in nets if value > 0.0)
    losers = tuple(value for value in nets if value < 0.0)
    gross = math.fsum(value.gross_pnl_usd for value in trades)
    net = math.fsum(nets)
    turnover = math.fsum(value.turnover_usd for value in trades)
    total_cost = math.fsum(
        value.execution_friction_usd + value.explicit_cost_usd for value in trades
    )
    positive_sum = math.fsum(winners)
    negative_sum = math.fsum(losers)
    return {
        "trade_count": count,
        "gross_pnl_usd": gross,
        "net_pnl_usd": net,
        "turnover_usd": turnover,
        "total_cost_usd": total_cost,
        "win_count": len(winners),
        "loss_count": len(losers),
        "flat_count": count - len(winners) - len(losers),
        "average_winner_usd": None if not winners else positive_sum / len(winners),
        "average_loser_usd": None if not losers else negative_sum / len(losers),
        "win_rate": len(winners) / count,
        "cost_burden_pct": total_cost / turnover * 100.0,
        "net_expectancy_usd": net / count,
        "net_expectancy_pct": math.fsum(
            value.net_pnl_usd / value.entry_notional_usd * 100.0 for value in trades
        ) / count,
        "profit_factor": None if not losers else positive_sum / abs(negative_sum),
        "span_ms": max(value.closed_at_unix_ms for value in trades)
        - min(value.opened_at_unix_ms for value in trades),
        "single_winner_share": None
        if not winners
        else max(winners) / positive_sum,
    }


def _trades_reconcile_report(
    summary: dict[str, object], report: TradingEvaluationReport
) -> bool:
    metrics = report.metrics
    exact_pairs = (
        (summary["trade_count"], metrics.trade_count),
        (summary["win_count"], metrics.win_count),
        (summary["loss_count"], metrics.loss_count),
        (summary["flat_count"], metrics.flat_count),
    )
    if any(left != right for left, right in exact_pairs):
        return False
    float_pairs = (
        (summary["gross_pnl_usd"], metrics.gross_pnl_usd),
        (summary["net_pnl_usd"], metrics.net_pnl_usd),
        (summary["turnover_usd"], metrics.turnover_usd),
        (summary["total_cost_usd"], metrics.total_cost_usd),
        (summary["average_winner_usd"], metrics.average_winner_usd),
        (summary["average_loser_usd"], metrics.average_loser_usd),
        (summary["win_rate"], metrics.win_rate),
        (summary["cost_burden_pct"], metrics.cost_burden_pct),
        (summary["net_expectancy_usd"], metrics.net_expectancy_usd),
        (summary["net_expectancy_pct"], metrics.net_expectancy_pct),
        (summary["profit_factor"], metrics.profit_factor),
    )
    return all(_optional_close(left, right) for left, right in float_pairs)


def _summarize_shadow(records: tuple[ShadowDecisionRecord, ...]) -> dict[str, int]:
    if not records:
        return {"count": 0, "distinct_mints": 0, "span_ms": 0}
    return {
        "count": len(records),
        "distinct_mints": len({value.candidate_mint for value in records}),
        "span_ms": max(value.as_of_unix_ms for value in records)
        - min(value.as_of_unix_ms for value in records),
    }


def _shadow_provenance_matches(
    candidate: RegistryCandidate, records: tuple[ShadowDecisionRecord, ...]
) -> bool:
    if candidate.model_version is None or candidate.model_training_fingerprint_sha256 is None:
        return False
    return all(
        value.schema_version == SHADOW_CHALLENGER_SCHEMA_VERSION
        and value.candidate_fingerprint_sha256 == candidate.candidate_fingerprint_sha256
        and value.strategy_version == candidate.strategy_version
        and value.model_version == candidate.model_version
        and value.model_training_fingerprint_sha256
        == candidate.model_training_fingerprint_sha256
        for value in records
    )


def _trade_sort_key(value: EvaluatedTrade) -> tuple[int, int, str, str]:
    return (
        value.closed_at_unix_ms,
        value.opened_at_unix_ms,
        value.position_id,
        value.candidate_mint,
    )


def _status_gate(
    code: PromotionGateCode,
    status: PromotionGateStatus,
    observed: float | int | str | None,
    threshold: float | int | str | None,
    message: str,
) -> PromotionGateResult:
    return PromotionGateResult(code, status, observed, threshold, message)


def _minimum_gate(
    code: PromotionGateCode,
    observed: int | float,
    threshold: int | float,
    *,
    insufficient: bool,
) -> PromotionGateResult:
    status = (
        PromotionGateStatus.PASS
        if observed >= threshold
        else PromotionGateStatus.INSUFFICIENT
        if insufficient
        else PromotionGateStatus.FAIL
    )
    return _status_gate(code, status, observed, threshold, "minimum promotion gate")


def _maximum_gate(
    code: PromotionGateCode, observed: float, threshold: float
) -> PromotionGateResult:
    return _status_gate(
        code,
        PromotionGateStatus.PASS if observed <= threshold else PromotionGateStatus.FAIL,
        observed,
        threshold,
        "maximum promotion gate",
    )


def _optional_minimum_gate(
    code: PromotionGateCode, observed: float | None, threshold: float
) -> PromotionGateResult:
    if observed is None:
        return _status_gate(
            code,
            PromotionGateStatus.INSUFFICIENT,
            None,
            threshold,
            "metric is unavailable",
        )
    return _minimum_gate(code, observed, threshold, insufficient=False)


def _optional_maximum_gate(
    code: PromotionGateCode, observed: float | None, threshold: float
) -> PromotionGateResult:
    if observed is None:
        return _status_gate(
            code,
            PromotionGateStatus.INSUFFICIENT,
            None,
            threshold,
            "metric is unavailable",
        )
    return _maximum_gate(code, observed, threshold)


def _decision(gates: tuple[PromotionGateResult, ...]) -> PromotionDecision:
    if any(value.status is PromotionGateStatus.FAIL for value in gates):
        return PromotionDecision.INELIGIBLE
    if any(value.status is PromotionGateStatus.INSUFFICIENT for value in gates):
        return PromotionDecision.INSUFFICIENT_EVIDENCE
    return PromotionDecision.ELIGIBLE


def _assessment_material(value: PromotionAssessment) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "policy_version": value.policy_version,
        "candidate_version": value.candidate_version,
        "candidate_fingerprint_sha256": value.candidate_fingerprint_sha256,
        "registry_fingerprint_sha256": value.registry_fingerprint_sha256,
        "evaluation_fingerprint_sha256": value.evaluation_fingerprint_sha256,
        "trade_evidence_fingerprint_sha256": value.trade_evidence_fingerprint_sha256,
        "shadow_ledger_fingerprint_sha256": value.shadow_ledger_fingerprint_sha256,
        "baseline_evaluation_identities": value.baseline_evaluation_identities,
        "evaluated_at_unix_ms": value.evaluated_at_unix_ms,
        "gates": tuple(
            {
                "code": gate.code,
                "status": gate.status,
                "observed_value": gate.observed_value,
                "threshold_value": gate.threshold_value,
                "message": gate.message,
            }
            for gate in value.gates
        ),
        "decision": value.decision,
    }


def _optional_close(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    return math.isclose(float(left), float(right), rel_tol=_REL_TOL, abs_tol=_ABS_TOL)
