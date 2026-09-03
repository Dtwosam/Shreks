from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math

from shreks_brain.evaluation import TradingEvaluationEvidence
from shreks_brain.fast_paper import FastPaperLoopState

from .models import (
    FAST_POLICY_PROOF_SCHEMA_NAME,
    FAST_POLICY_PROOF_SCHEMA_VERSION,
    FastPolicyProofDecision,
    FastPolicyProofGateCode,
    FastPolicyProofGateResult,
    FastPolicyProofGateStatus,
    FastPolicyRunEvidence,
    FastPolicySuperiorityPolicy,
    FastPolicySuperiorityReport,
    _decision_from_gates,
)


def build_fast_policy_run_evidence(
    *,
    paper_run_id: str,
    candidate_fingerprint_sha256: str,
    strategy_version: str,
    loop_state: FastPaperLoopState,
    trading_evaluation: TradingEvaluationEvidence,
) -> FastPolicyRunEvidence:
    _require_non_empty_string("paper_run_id", paper_run_id)
    _require_sha256("candidate_fingerprint_sha256", candidate_fingerprint_sha256)
    _require_non_empty_string("strategy_version", strategy_version)
    if type(loop_state) is not FastPaperLoopState:
        raise ValueError("loop_state must be an exact FastPaperLoopState")
    if type(trading_evaluation) is not TradingEvaluationEvidence:
        raise ValueError(
            "trading_evaluation must be an exact TradingEvaluationEvidence"
        )

    population_material = [
        {
            "source_event_id": record.source_event_id,
            "update_fingerprint": record.update_fingerprint,
            "market_key": record.market_key,
            "source_sequence": record.source_sequence,
            "as_of_unix_ms": record.as_of_unix_ms,
            "is_material": record.is_material,
        }
        for record in loop_state.records
    ]
    journal_material = [
        {
            **population,
            "assessment": (
                None
                if record.assessment is None
                else {
                    "version": record.assessment.version,
                    "source_event_id": record.assessment.source_event_id,
                    "market_key": record.assessment.market_key,
                    "source_sequence": record.assessment.source_sequence,
                    "as_of_unix_ms": record.assessment.as_of_unix_ms,
                    "strategy_family": record.assessment.strategy_family,
                    "strategy_version": record.assessment.strategy_version,
                    "action": record.assessment.action.value,
                    "reasons": list(record.assessment.reasons),
                }
            ),
        }
        for population, record in zip(population_material, loop_state.records)
    ]

    material_records = tuple(record for record in loop_state.records if record.is_material)
    if any(record.assessment is None for record in material_records):
        raise ValueError("every material Fast PAPER record requires an assessment")
    decision_count = sum(record.assessment is not None for record in loop_state.records)
    if decision_count != len(material_records):
        raise ValueError("Fast PAPER decision count must equal material update count")

    if loop_state.records:
        first_event_ms = min(record.as_of_unix_ms for record in loop_state.records)
        last_event_ms = max(record.as_of_unix_ms for record in loop_state.records)
    else:
        first_event_ms = 0
        last_event_ms = 0

    trades = trading_evaluation.trades
    if trades and not loop_state.records:
        raise ValueError("trade evidence requires a non-empty Fast PAPER population")
    if trades and any(trade.opened_at_unix_ms < first_event_ms for trade in trades):
        raise ValueError("trade evidence opens before Fast PAPER population window")

    observed_through = last_event_ms
    if trades:
        observed_through = max(
            observed_through,
            max(trade.closed_at_unix_ms for trade in trades),
        )
    observed_from = first_event_ms

    population_fingerprint = _sha256_canonical(population_material)
    journal_fingerprint = _sha256_canonical(journal_material)
    draft_material = {
        "schema_name": FAST_POLICY_PROOF_SCHEMA_NAME,
        "schema_version": FAST_POLICY_PROOF_SCHEMA_VERSION,
        "paper_run_id": paper_run_id,
        "candidate_version": trading_evaluation.candidate_version,
        "candidate_fingerprint_sha256": candidate_fingerprint_sha256,
        "strategy_version": strategy_version,
        "evaluation_fingerprint_sha256": (
            trading_evaluation.report.evaluation_fingerprint_sha256
        ),
        "event_population_fingerprint_sha256": population_fingerprint,
        "action_journal_fingerprint_sha256": journal_fingerprint,
        "material_update_count": len(material_records),
        "decision_count": decision_count,
        "distinct_market_count": len(
            {record.market_key for record in material_records}
        ),
        "observed_from_unix_ms": observed_from,
        "observed_through_unix_ms": observed_through,
    }
    fingerprint = _sha256_canonical(draft_material)
    return FastPolicyRunEvidence(
        schema_name=FAST_POLICY_PROOF_SCHEMA_NAME,
        schema_version=FAST_POLICY_PROOF_SCHEMA_VERSION,
        paper_run_id=paper_run_id,
        candidate_version=trading_evaluation.candidate_version,
        candidate_fingerprint_sha256=candidate_fingerprint_sha256,
        strategy_version=strategy_version,
        trading_evaluation=trading_evaluation,
        event_population_fingerprint_sha256=population_fingerprint,
        action_journal_fingerprint_sha256=journal_fingerprint,
        material_update_count=len(material_records),
        decision_count=decision_count,
        distinct_market_count=len(
            {record.market_key for record in material_records}
        ),
        observed_from_unix_ms=observed_from,
        observed_through_unix_ms=observed_through,
        run_evidence_fingerprint_sha256=fingerprint,
    )


def evaluate_fast_policy_superiority(
    candidate: FastPolicyRunEvidence,
    baselines: tuple[FastPolicyRunEvidence, ...],
    policy: FastPolicySuperiorityPolicy,
) -> FastPolicySuperiorityReport:
    if type(candidate) is not FastPolicyRunEvidence:
        raise ValueError("candidate must be an exact FastPolicyRunEvidence")
    if type(policy) is not FastPolicySuperiorityPolicy:
        raise ValueError("policy must be an exact FastPolicySuperiorityPolicy")
    if (
        not isinstance(baselines, tuple)
        or not all(type(value) is FastPolicyRunEvidence for value in baselines)
    ):
        raise ValueError("baselines must be a tuple of exact FastPolicyRunEvidence values")
    if candidate.candidate_version in policy.required_baseline_versions:
        raise ValueError("candidate version cannot be a required baseline")

    versions = tuple(value.candidate_version for value in baselines)
    if len(versions) != len(set(versions)):
        raise ValueError("duplicate baseline candidate version")
    unexpected = tuple(
        value
        for value in versions
        if value not in policy.required_baseline_versions
    )
    if unexpected:
        raise ValueError("undeclared baseline candidate version")

    baseline_by_version = {value.candidate_version: value for value in baselines}
    missing = tuple(
        value
        for value in policy.required_baseline_versions
        if value not in baseline_by_version
    )

    gates: dict[FastPolicyProofGateCode, FastPolicyProofGateResult] = {}

    provenance_ok = (
        candidate.trading_evaluation.candidate_version == candidate.candidate_version
        and candidate.trading_evaluation.report.candidate_version
        == candidate.candidate_version
    )
    gates[FastPolicyProofGateCode.CANDIDATE_PROVENANCE] = _status_gate(
        FastPolicyProofGateCode.CANDIDATE_PROVENANCE,
        FastPolicyProofGateStatus.PASS
        if provenance_ok
        else FastPolicyProofGateStatus.FAIL,
        "aligned" if provenance_ok else "mismatch",
        "aligned",
        "candidate run identity must match sealed E5 evidence",
    )

    population_ok = all(
        value.event_population_fingerprint_sha256
        == candidate.event_population_fingerprint_sha256
        for value in baselines
    )
    gates[FastPolicyProofGateCode.COMPARISON_POPULATION] = _status_gate(
        FastPolicyProofGateCode.COMPARISON_POPULATION,
        FastPolicyProofGateStatus.PASS
        if population_ok
        else FastPolicyProofGateStatus.FAIL,
        "aligned" if population_ok else "mismatch",
        "aligned",
        "candidate and baselines must evaluate the same Fast PAPER event population",
    )

    evaluation_policy_ok = all(
        value.trading_evaluation.policy == candidate.trading_evaluation.policy
        for value in baselines
    )
    gates[FastPolicyProofGateCode.EVALUATION_POLICY_MATCH] = _status_gate(
        FastPolicyProofGateCode.EVALUATION_POLICY_MATCH,
        FastPolicyProofGateStatus.PASS
        if evaluation_policy_ok
        else FastPolicyProofGateStatus.FAIL,
        "aligned" if evaluation_policy_ok else "mismatch",
        "aligned",
        "candidate and baselines must use the exact same sealed E5 policy",
    )

    insufficient_baselines: list[str] = []
    for version in policy.required_baseline_versions:
        baseline = baseline_by_version.get(version)
        if baseline is None:
            continue
        metrics = baseline.trading_evaluation.report.metrics
        distinct_mints = len(
            {trade.candidate_mint for trade in baseline.trading_evaluation.trades}
        )
        if (
            metrics.trade_count < policy.min_trade_count
            or distinct_mints < policy.min_distinct_traded_mint_count
            or metrics.net_expectancy_pct is None
        ):
            insufficient_baselines.append(version)

    if missing or insufficient_baselines:
        observed_parts = []
        if missing:
            observed_parts.append("missing:" + ",".join(missing))
        if insufficient_baselines:
            observed_parts.append(
                "insufficient:" + ",".join(insufficient_baselines)
            )
        baseline_status = FastPolicyProofGateStatus.INSUFFICIENT
        baseline_observed: str | int = ";".join(observed_parts)
    else:
        baseline_status = FastPolicyProofGateStatus.PASS
        baseline_observed = len(policy.required_baseline_versions)
    gates[FastPolicyProofGateCode.BASELINE_COVERAGE] = _status_gate(
        FastPolicyProofGateCode.BASELINE_COVERAGE,
        baseline_status,
        baseline_observed,
        len(policy.required_baseline_versions),
        "all required deterministic baselines need comparable closed-trade expectancy evidence",
    )

    metrics = candidate.trading_evaluation.report.metrics
    distinct_traded_mints = len(
        {trade.candidate_mint for trade in candidate.trading_evaluation.trades}
    )
    evidence_span = (
        candidate.observed_through_unix_ms - candidate.observed_from_unix_ms
    )

    gates[FastPolicyProofGateCode.MIN_MATERIAL_DECISION_COUNT] = _minimum_sample_gate(
        FastPolicyProofGateCode.MIN_MATERIAL_DECISION_COUNT,
        candidate.decision_count,
        policy.min_material_decision_count,
    )
    gates[FastPolicyProofGateCode.MIN_DISTINCT_MARKET_COUNT] = _minimum_sample_gate(
        FastPolicyProofGateCode.MIN_DISTINCT_MARKET_COUNT,
        candidate.distinct_market_count,
        policy.min_distinct_market_count,
    )
    gates[FastPolicyProofGateCode.MIN_EVALUATION_SPAN] = _minimum_sample_gate(
        FastPolicyProofGateCode.MIN_EVALUATION_SPAN,
        evidence_span,
        policy.min_evaluation_span_ms,
    )
    gates[FastPolicyProofGateCode.MIN_TRADE_COUNT] = _minimum_sample_gate(
        FastPolicyProofGateCode.MIN_TRADE_COUNT,
        metrics.trade_count,
        policy.min_trade_count,
    )
    gates[
        FastPolicyProofGateCode.MIN_DISTINCT_TRADED_MINT_COUNT
    ] = _minimum_sample_gate(
        FastPolicyProofGateCode.MIN_DISTINCT_TRADED_MINT_COUNT,
        distinct_traded_mints,
        policy.min_distinct_traded_mint_count,
    )
    gates[FastPolicyProofGateCode.MIN_NET_EXPECTANCY_PCT] = _optional_minimum_gate(
        FastPolicyProofGateCode.MIN_NET_EXPECTANCY_PCT,
        metrics.net_expectancy_pct,
        policy.min_net_expectancy_pct,
    )
    gates[FastPolicyProofGateCode.MIN_PROFIT_FACTOR] = _optional_minimum_gate(
        FastPolicyProofGateCode.MIN_PROFIT_FACTOR,
        metrics.profit_factor,
        policy.min_profit_factor,
    )
    gates[FastPolicyProofGateCode.MAX_DRAWDOWN_PCT] = _maximum_gate(
        FastPolicyProofGateCode.MAX_DRAWDOWN_PCT,
        metrics.maximum_drawdown_pct,
        policy.max_drawdown_pct,
    )
    gates[FastPolicyProofGateCode.MAX_COST_BURDEN_PCT] = _optional_maximum_gate(
        FastPolicyProofGateCode.MAX_COST_BURDEN_PCT,
        metrics.cost_burden_pct,
        policy.max_cost_burden_pct,
    )

    winner_share = _single_winner_share(candidate.trading_evaluation)
    gates[FastPolicyProofGateCode.MAX_SINGLE_WINNER_SHARE] = _optional_maximum_gate(
        FastPolicyProofGateCode.MAX_SINGLE_WINNER_SHARE,
        winner_share,
        policy.max_single_winner_share_of_positive_pnl,
    )

    best_baseline: FastPolicyRunEvidence | None = None
    best_expectancy: float | None = None
    candidate_expectancy = metrics.net_expectancy_pct
    advantage: float | None = None

    comparison_integrity_ok = population_ok and evaluation_policy_ok
    if not comparison_integrity_ok:
        advantage_status = FastPolicyProofGateStatus.FAIL
    elif baseline_status is not FastPolicyProofGateStatus.PASS:
        advantage_status = FastPolicyProofGateStatus.INSUFFICIENT
    elif candidate_expectancy is None:
        advantage_status = FastPolicyProofGateStatus.INSUFFICIENT
    else:
        comparable = tuple(
            baseline_by_version[version]
            for version in policy.required_baseline_versions
        )
        best_baseline = min(
            comparable,
            key=lambda value: (
                -float(
                    value.trading_evaluation.report.metrics.net_expectancy_pct
                ),
                value.candidate_version,
            ),
        )
        best_expectancy = (
            best_baseline.trading_evaluation.report.metrics.net_expectancy_pct
        )
        assert best_expectancy is not None
        advantage = candidate_expectancy - best_expectancy
        advantage_status = (
            FastPolicyProofGateStatus.PASS
            if advantage >= policy.min_baseline_expectancy_advantage_pct
            else FastPolicyProofGateStatus.FAIL
        )

    gates[
        FastPolicyProofGateCode.BASELINE_EXPECTANCY_ADVANTAGE
    ] = _status_gate(
        FastPolicyProofGateCode.BASELINE_EXPECTANCY_ADVANTAGE,
        advantage_status,
        advantage,
        policy.min_baseline_expectancy_advantage_pct,
        "candidate after-cost expectancy must beat the best required deterministic baseline",
    )

    ordered_gates = tuple(
        gates[code]
        for code in sorted(FastPolicyProofGateCode, key=lambda value: value.value)
    )
    decision = _decision_from_gates(ordered_gates)
    baseline_identities = tuple(
        (
            value.candidate_version,
            value.run_evidence_fingerprint_sha256,
            value.trading_evaluation.report.evaluation_fingerprint_sha256,
        )
        for value in sorted(baselines, key=lambda item: item.candidate_version)
    )

    draft = FastPolicySuperiorityReport(
        schema_name=FAST_POLICY_PROOF_SCHEMA_NAME,
        schema_version=FAST_POLICY_PROOF_SCHEMA_VERSION,
        policy_version=policy.version,
        candidate_version=candidate.candidate_version,
        candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
        candidate_run_evidence_fingerprint_sha256=(
            candidate.run_evidence_fingerprint_sha256
        ),
        candidate_evaluation_fingerprint_sha256=(
            candidate.trading_evaluation.report.evaluation_fingerprint_sha256
        ),
        event_population_fingerprint_sha256=(
            candidate.event_population_fingerprint_sha256
        ),
        baseline_evaluation_identities=baseline_identities,
        best_baseline_version=(
            None if best_baseline is None else best_baseline.candidate_version
        ),
        best_baseline_evaluation_fingerprint_sha256=(
            None
            if best_baseline is None
            else best_baseline.trading_evaluation.report.evaluation_fingerprint_sha256
        ),
        candidate_net_expectancy_pct=candidate_expectancy,
        best_baseline_net_expectancy_pct=best_expectancy,
        expectancy_advantage_pct=advantage,
        gates=ordered_gates,
        decision=decision,
        report_fingerprint_sha256="0" * 64,
    )
    return replace(
        draft,
        report_fingerprint_sha256=_sha256_canonical(_report_material(draft)),
    )


def _report_material(report: FastPolicySuperiorityReport) -> dict[str, object]:
    return {
        "schema_name": report.schema_name,
        "schema_version": report.schema_version,
        "policy_version": report.policy_version,
        "candidate_version": report.candidate_version,
        "candidate_fingerprint_sha256": report.candidate_fingerprint_sha256,
        "candidate_run_evidence_fingerprint_sha256": (
            report.candidate_run_evidence_fingerprint_sha256
        ),
        "candidate_evaluation_fingerprint_sha256": (
            report.candidate_evaluation_fingerprint_sha256
        ),
        "event_population_fingerprint_sha256": (
            report.event_population_fingerprint_sha256
        ),
        "baseline_evaluation_identities": [
            list(value) for value in report.baseline_evaluation_identities
        ],
        "best_baseline_version": report.best_baseline_version,
        "best_baseline_evaluation_fingerprint_sha256": (
            report.best_baseline_evaluation_fingerprint_sha256
        ),
        "candidate_net_expectancy_pct": report.candidate_net_expectancy_pct,
        "best_baseline_net_expectancy_pct": (
            report.best_baseline_net_expectancy_pct
        ),
        "expectancy_advantage_pct": report.expectancy_advantage_pct,
        "gates": [
            {
                "code": value.code.value,
                "status": value.status.value,
                "observed_value": value.observed_value,
                "threshold_value": value.threshold_value,
                "message": value.message,
            }
            for value in report.gates
        ],
        "decision": report.decision.value,
    }


def _single_winner_share(evidence: TradingEvaluationEvidence) -> float | None:
    positive = tuple(
        trade.net_pnl_usd
        for trade in evidence.trades
        if trade.net_pnl_usd > 0.0
    )
    if not positive:
        return None
    return max(positive) / math.fsum(positive)


def _status_gate(
    code: FastPolicyProofGateCode,
    status: FastPolicyProofGateStatus,
    observed: float | int | str | None,
    threshold: float | int | str | None,
    message: str,
) -> FastPolicyProofGateResult:
    return FastPolicyProofGateResult(code, status, observed, threshold, message)


def _minimum_sample_gate(
    code: FastPolicyProofGateCode, observed: int, threshold: int
) -> FastPolicyProofGateResult:
    return _status_gate(
        code,
        FastPolicyProofGateStatus.PASS
        if observed >= threshold
        else FastPolicyProofGateStatus.INSUFFICIENT,
        observed,
        threshold,
        "evidence must meet minimum sample coverage",
    )


def _optional_minimum_gate(
    code: FastPolicyProofGateCode,
    observed: float | None,
    threshold: float,
) -> FastPolicyProofGateResult:
    if observed is None:
        status = FastPolicyProofGateStatus.INSUFFICIENT
    else:
        status = (
            FastPolicyProofGateStatus.PASS
            if observed >= threshold
            else FastPolicyProofGateStatus.FAIL
        )
    return _status_gate(code, status, observed, threshold, "metric must meet minimum")


def _maximum_gate(
    code: FastPolicyProofGateCode,
    observed: float,
    threshold: float,
) -> FastPolicyProofGateResult:
    return _status_gate(
        code,
        FastPolicyProofGateStatus.PASS
        if observed <= threshold
        else FastPolicyProofGateStatus.FAIL,
        observed,
        threshold,
        "metric must not exceed maximum",
    )


def _optional_maximum_gate(
    code: FastPolicyProofGateCode,
    observed: float | None,
    threshold: float,
) -> FastPolicyProofGateResult:
    if observed is None:
        status = FastPolicyProofGateStatus.INSUFFICIENT
    else:
        status = (
            FastPolicyProofGateStatus.PASS
            if observed <= threshold
            else FastPolicyProofGateStatus.FAIL
        )
    return _status_gate(code, status, observed, threshold, "metric must not exceed maximum")


def _sha256_canonical(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            f"{name} must be a lowercase 64-character SHA-256 hex digest"
        )
