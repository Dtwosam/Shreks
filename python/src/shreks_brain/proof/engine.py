from __future__ import annotations

from dataclasses import asdict, replace
import math

from shreks_brain.evaluation.evidence import TradingEvaluationEvidence
from shreks_brain.paper_evaluation.codec import build_paper_evaluation_ledger
from shreks_brain.paper_evaluation.engine import build_evaluated_trades
from shreks_brain.paper_evaluation.models import PaperEvaluationLedger
from shreks_brain.promotion.models import PromotionAssessment, PromotionDecision
from shreks_brain.registry.models import ChampionChallengerRegistry, RegistryStatus

from .fingerprint import sha256_canonical
from .models import (
    PAPER_PROOF_SCHEMA_VERSION,
    CandidateProofAssessment,
    PaperProofDecision,
    PaperProofGateCode,
    PaperProofGateResult,
    PaperProofGateStatus,
    PaperProofPolicy,
)


def evaluate_candidate_proof(
    registry: ChampionChallengerRegistry,
    candidate_version: str,
    e8_assessment: PromotionAssessment,
    paper_run_id: str,
    paper_ledger: PaperEvaluationLedger,
    paper_evaluation: TradingEvaluationEvidence,
    policy: PaperProofPolicy,
    evaluated_at_unix_ms: int,
) -> CandidateProofAssessment:
    _validate_inputs(
        registry,
        candidate_version,
        e8_assessment,
        paper_run_id,
        paper_ledger,
        paper_evaluation,
        policy,
        evaluated_at_unix_ms,
    )

    candidate = next(
        (
            value
            for value in registry.candidates
            if value.candidate_version == candidate_version
        ),
        None,
    )
    if candidate is None:
        raise ValueError(f"candidate '{candidate_version}' is not registered")

    rebuilt_ledger = build_paper_evaluation_ledger(
        paper_ledger.entry_provenance,
        paper_ledger.executions,
        paper_ledger.closures,
        paper_ledger.orphan_costs,
    )
    if rebuilt_ledger.document_fingerprint_sha256 != paper_ledger.document_fingerprint_sha256:
        raise ValueError("paper ledger fingerprint does not match ledger content")

    trades = build_evaluated_trades(
        paper_run_id,
        candidate_version,
        paper_ledger.entry_provenance,
        paper_ledger.executions,
        paper_ledger.closures,
        paper_ledger.orphan_costs,
    )

    latest_evidence_ms = e8_assessment.evaluated_at_unix_ms
    if trades:
        latest_evidence_ms = max(
            latest_evidence_ms,
            max(trade.closed_at_unix_ms for trade in trades),
        )
    if evaluated_at_unix_ms < latest_evidence_ms:
        raise ValueError("evaluated_at_unix_ms cannot precede referenced proof evidence")

    trade_fingerprint = sha256_canonical([asdict(trade) for trade in trades])
    trade_summary = _summarize_trades(trades)

    gates: dict[PaperProofGateCode, PaperProofGateResult] = {}
    gates[PaperProofGateCode.E8_ASSESSMENT_ELIGIBLE] = _e8_decision_gate(
        e8_assessment.decision
    )

    e8_registry_matches = (
        e8_assessment.candidate_version == candidate_version
        and e8_assessment.candidate_fingerprint_sha256
        == candidate.candidate_fingerprint_sha256
        and e8_assessment.registry_fingerprint_sha256
        == registry.registry_fingerprint_sha256
        and registry.current_status(candidate_version) is RegistryStatus.CHALLENGER
    )
    gates[PaperProofGateCode.E8_REGISTRY_PROVENANCE] = _gate(
        PaperProofGateCode.E8_REGISTRY_PROVENANCE,
        PaperProofGateStatus.PASS
        if e8_registry_matches
        else PaperProofGateStatus.FAIL,
        "aligned" if e8_registry_matches else "mismatch",
        "aligned",
        "E8 assessment must match the current E6 challenger identity and registry state",
    )

    ledger_attribution_matches = _paper_attribution_matches(
        paper_ledger,
        paper_run_id,
        candidate_version,
        candidate.candidate_fingerprint_sha256,
        candidate.strategy_version,
    )
    paper_provenance_matches = (
        ledger_attribution_matches
        and paper_evaluation.candidate_version == candidate_version
        and paper_evaluation.trades == trades
    )
    gates[PaperProofGateCode.PAPER_EVIDENCE_PROVENANCE] = _gate(
        PaperProofGateCode.PAPER_EVIDENCE_PROVENANCE,
        PaperProofGateStatus.PASS
        if paper_provenance_matches
        else PaperProofGateStatus.FAIL,
        "aligned" if paper_provenance_matches else "mismatch",
        "aligned",
        "E10 paper source trades must exactly equal E11-rebuilt trades for the current candidate",
    )

    if not paper_provenance_matches:
        _set_untrusted_paper_gates(gates, policy)
    else:
        metrics = paper_evaluation.report.metrics
        gates[PaperProofGateCode.MIN_PAPER_TRADE_COUNT] = _minimum_gate(
            PaperProofGateCode.MIN_PAPER_TRADE_COUNT,
            trade_summary["trade_count"],
            policy.min_trade_count,
        )
        gates[PaperProofGateCode.MIN_PAPER_DISTINCT_MINT_COUNT] = _minimum_gate(
            PaperProofGateCode.MIN_PAPER_DISTINCT_MINT_COUNT,
            trade_summary["distinct_mints"],
            policy.min_distinct_mint_count,
        )
        gates[PaperProofGateCode.MIN_PAPER_EVALUATION_SPAN] = _minimum_gate(
            PaperProofGateCode.MIN_PAPER_EVALUATION_SPAN,
            trade_summary["span_ms"],
            policy.min_evaluation_span_ms,
        )
        gates[PaperProofGateCode.MIN_PAPER_NET_EXPECTANCY_PCT] = _optional_minimum_gate(
            PaperProofGateCode.MIN_PAPER_NET_EXPECTANCY_PCT,
            metrics.net_expectancy_pct,
            policy.min_net_expectancy_pct,
        )
        gates[PaperProofGateCode.MIN_PAPER_PROFIT_FACTOR] = _optional_minimum_gate(
            PaperProofGateCode.MIN_PAPER_PROFIT_FACTOR,
            metrics.profit_factor,
            policy.min_profit_factor,
        )
        gates[PaperProofGateCode.MAX_PAPER_DRAWDOWN_PCT] = _maximum_gate(
            PaperProofGateCode.MAX_PAPER_DRAWDOWN_PCT,
            metrics.maximum_drawdown_pct,
            policy.max_drawdown_pct,
        )
        gates[PaperProofGateCode.MAX_PAPER_COST_BURDEN_PCT] = _optional_maximum_gate(
            PaperProofGateCode.MAX_PAPER_COST_BURDEN_PCT,
            metrics.cost_burden_pct,
            policy.max_cost_burden_pct,
        )
        gates[PaperProofGateCode.MAX_PAPER_SINGLE_WINNER_SHARE] = _optional_maximum_gate(
            PaperProofGateCode.MAX_PAPER_SINGLE_WINNER_SHARE,
            trade_summary["single_winner_share"],
            policy.max_single_winner_share_of_positive_pnl,
        )

    ordered_gates = tuple(
        gates[code]
        for code in sorted(PaperProofGateCode, key=lambda value: value.value)
    )
    decision = _decision(ordered_gates)
    draft = CandidateProofAssessment(
        schema_version=PAPER_PROOF_SCHEMA_VERSION,
        policy_version=policy.version,
        candidate_version=candidate_version,
        candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
        registry_fingerprint_sha256=registry.registry_fingerprint_sha256,
        e8_assessment_fingerprint_sha256=e8_assessment.assessment_fingerprint_sha256,
        paper_run_id=paper_run_id,
        paper_ledger_fingerprint_sha256=paper_ledger.document_fingerprint_sha256,
        paper_evaluation_fingerprint_sha256=(
            paper_evaluation.report.evaluation_fingerprint_sha256
        ),
        paper_trade_evidence_fingerprint_sha256=trade_fingerprint,
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
    e8_assessment: object,
    paper_run_id: object,
    paper_ledger: object,
    paper_evaluation: object,
    policy: object,
    evaluated_at_unix_ms: object,
) -> None:
    if type(registry) is not ChampionChallengerRegistry:
        raise ValueError("registry must be an exact ChampionChallengerRegistry")
    _require_non_empty_string("candidate_version", candidate_version)
    if type(e8_assessment) is not PromotionAssessment:
        raise ValueError("e8_assessment must be an exact PromotionAssessment")
    _require_non_empty_string("paper_run_id", paper_run_id)
    if type(paper_ledger) is not PaperEvaluationLedger:
        raise ValueError("paper_ledger must be an exact PaperEvaluationLedger")
    if type(paper_evaluation) is not TradingEvaluationEvidence:
        raise ValueError(
            "paper_evaluation must be an exact TradingEvaluationEvidence"
        )
    if type(policy) is not PaperProofPolicy:
        raise ValueError("policy must be an exact PaperProofPolicy")
    if (
        isinstance(evaluated_at_unix_ms, bool)
        or not isinstance(evaluated_at_unix_ms, int)
        or evaluated_at_unix_ms < 0
    ):
        raise ValueError("evaluated_at_unix_ms must be a non-negative integer")


def _paper_attribution_matches(
    ledger: PaperEvaluationLedger,
    paper_run_id: str,
    candidate_version: str,
    candidate_fingerprint_sha256: str,
    strategy_version: str,
) -> bool:
    selected = []
    for collection in (
        ledger.entry_provenance,
        ledger.executions,
        ledger.closures,
        ledger.orphan_costs,
    ):
        selected.extend(
            value
            for value in collection
            if value.paper_run_id == paper_run_id
            and value.candidate_version == candidate_version
        )
    return all(
        value.candidate_fingerprint_sha256 == candidate_fingerprint_sha256
        and value.strategy_version == strategy_version
        for value in selected
    )


def _summarize_trades(trades: tuple[object, ...]) -> dict[str, object]:
    if not trades:
        return {
            "trade_count": 0,
            "distinct_mints": 0,
            "span_ms": 0,
            "single_winner_share": None,
        }
    opened = min(trade.opened_at_unix_ms for trade in trades)  # type: ignore[attr-defined]
    closed = max(trade.closed_at_unix_ms for trade in trades)  # type: ignore[attr-defined]
    positive = tuple(
        trade.net_pnl_usd  # type: ignore[attr-defined]
        for trade in trades
        if trade.net_pnl_usd > 0  # type: ignore[attr-defined]
    )
    winner_share = None
    if positive:
        winner_share = max(positive) / sum(positive)
    return {
        "trade_count": len(trades),
        "distinct_mints": len(
            {trade.candidate_mint for trade in trades}  # type: ignore[attr-defined]
        ),
        "span_ms": closed - opened,
        "single_winner_share": winner_share,
    }


def _e8_decision_gate(decision: PromotionDecision) -> PaperProofGateResult:
    if decision is PromotionDecision.ELIGIBLE:
        status = PaperProofGateStatus.PASS
    elif decision is PromotionDecision.INSUFFICIENT_EVIDENCE:
        status = PaperProofGateStatus.INSUFFICIENT
    else:
        status = PaperProofGateStatus.FAIL
    return _gate(
        PaperProofGateCode.E8_ASSESSMENT_ELIGIBLE,
        status,
        decision.value,
        PromotionDecision.ELIGIBLE.value,
        "sealed E8 assessment must already be eligible",
    )


def _minimum_gate(
    code: PaperProofGateCode,
    observed: int,
    threshold: int,
) -> PaperProofGateResult:
    status = (
        PaperProofGateStatus.PASS
        if observed >= threshold
        else PaperProofGateStatus.INSUFFICIENT
    )
    return _gate(code, status, observed, threshold, "paper evidence must meet minimum sample coverage")


def _optional_minimum_gate(
    code: PaperProofGateCode,
    observed: float | None,
    threshold: float,
) -> PaperProofGateResult:
    if observed is None:
        status = PaperProofGateStatus.INSUFFICIENT
    else:
        status = (
            PaperProofGateStatus.PASS
            if observed >= threshold
            else PaperProofGateStatus.FAIL
        )
    return _gate(code, status, observed, threshold, "paper metric must meet minimum threshold")


def _maximum_gate(
    code: PaperProofGateCode,
    observed: float,
    threshold: float,
) -> PaperProofGateResult:
    status = (
        PaperProofGateStatus.PASS
        if observed <= threshold
        else PaperProofGateStatus.FAIL
    )
    return _gate(code, status, observed, threshold, "paper risk metric must remain below maximum threshold")


def _optional_maximum_gate(
    code: PaperProofGateCode,
    observed: float | None | object,
    threshold: float,
) -> PaperProofGateResult:
    if observed is None:
        status = PaperProofGateStatus.INSUFFICIENT
        value = None
    else:
        value = float(observed)
        if not math.isfinite(value):
            raise ValueError("paper metric must be finite")
        status = (
            PaperProofGateStatus.PASS
            if value <= threshold
            else PaperProofGateStatus.FAIL
        )
    return _gate(code, status, value, threshold, "paper metric must remain below maximum threshold")


def _set_untrusted_paper_gates(
    gates: dict[PaperProofGateCode, PaperProofGateResult],
    policy: PaperProofPolicy,
) -> None:
    thresholds: dict[PaperProofGateCode, int | float] = {
        PaperProofGateCode.MIN_PAPER_TRADE_COUNT: policy.min_trade_count,
        PaperProofGateCode.MIN_PAPER_DISTINCT_MINT_COUNT: policy.min_distinct_mint_count,
        PaperProofGateCode.MIN_PAPER_EVALUATION_SPAN: policy.min_evaluation_span_ms,
        PaperProofGateCode.MIN_PAPER_NET_EXPECTANCY_PCT: policy.min_net_expectancy_pct,
        PaperProofGateCode.MIN_PAPER_PROFIT_FACTOR: policy.min_profit_factor,
        PaperProofGateCode.MAX_PAPER_DRAWDOWN_PCT: policy.max_drawdown_pct,
        PaperProofGateCode.MAX_PAPER_COST_BURDEN_PCT: policy.max_cost_burden_pct,
        PaperProofGateCode.MAX_PAPER_SINGLE_WINNER_SHARE: (
            policy.max_single_winner_share_of_positive_pnl
        ),
    }
    for code, threshold in thresholds.items():
        gates[code] = _gate(
            code,
            PaperProofGateStatus.FAIL,
            "untrusted",
            threshold,
            "paper metric cannot be scored until E11 and E10 source evidence match",
        )


def _gate(
    code: PaperProofGateCode,
    status: PaperProofGateStatus,
    observed_value: float | int | str | None,
    threshold_value: float | int | str | None,
    message: str,
) -> PaperProofGateResult:
    return PaperProofGateResult(
        code=code,
        status=status,
        observed_value=observed_value,
        threshold_value=threshold_value,
        message=message,
    )


def _decision(gates: tuple[PaperProofGateResult, ...]) -> PaperProofDecision:
    if any(gate.status is PaperProofGateStatus.FAIL for gate in gates):
        return PaperProofDecision.FAILED
    if any(gate.status is PaperProofGateStatus.INSUFFICIENT for gate in gates):
        return PaperProofDecision.INSUFFICIENT_EVIDENCE
    return PaperProofDecision.SUFFICIENT


def _assessment_material(assessment: CandidateProofAssessment) -> dict[str, object]:
    material = asdict(assessment)
    material["assessment_fingerprint_sha256"] = "0" * 64
    return material


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
