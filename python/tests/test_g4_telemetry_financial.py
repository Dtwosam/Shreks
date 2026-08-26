from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import shreks_brain.telemetry.financial as financial_module
from shreks_brain.evaluation import (
    EvaluatedTrade,
    TradingEvaluationPolicy,
    evaluate_trading_performance,
)
from shreks_brain.proof import (
    PAPER_PROOF_SCHEMA_VERSION,
    CandidateProofAssessment,
    PaperProofDecision,
    PaperProofGateCode,
    PaperProofGateResult,
    PaperProofGateStatus,
)
from shreks_brain.promotion import (
    PROMOTION_SCHEMA_VERSION,
    PromotionAssessment,
    PromotionDecision,
    PromotionGateCode,
    PromotionGateResult,
    PromotionGateStatus,
)
from shreks_brain.telemetry import LayerStatus
from shreks_brain.telemetry.financial import compose_financial_telemetry
from shreks_brain.telemetry.sources import (
    TelemetrySourceConfig,
    collect_telemetry_sources,
)

from test_g4_telemetry_sources import _add_operational_tables
from test_observer_campaign_runner import AS_OF
from test_observer_campaign_runtime import _runtime_config


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def _sources(tmp_path: Path):
    runtime = _runtime_config(tmp_path, max_cycles=1)
    _add_operational_tables(runtime.observer_database_path)
    return collect_telemetry_sources(
        TelemetrySourceConfig(
            runtime_config=runtime,
            proof_path=tmp_path / "proof.json",
            promotion_path=tmp_path / "promotion.json",
        ),
        as_of_unix_ms=AS_OF,
    )


def _trades(candidate_version: str) -> tuple[EvaluatedTrade, ...]:
    return (
        EvaluatedTrade(
            candidate_version=candidate_version,
            position_id="position-1",
            candidate_mint="MintOne",
            setup_name="fresh_launch_continuation",
            market_regime="NORMAL",
            opened_at_unix_ms=1_000,
            closed_at_unix_ms=2_000,
            entry_notional_usd=100.0,
            turnover_usd=210.0,
            gross_pnl_usd=12.0,
            execution_friction_usd=1.0,
            explicit_cost_usd=1.0,
            net_pnl_usd=10.0,
        ),
        EvaluatedTrade(
            candidate_version=candidate_version,
            position_id="position-2",
            candidate_mint="MintTwo",
            setup_name="fresh_launch_continuation",
            market_regime="NORMAL",
            opened_at_unix_ms=3_000,
            closed_at_unix_ms=4_000,
            entry_notional_usd=100.0,
            turnover_usd=195.0,
            gross_pnl_usd=-3.0,
            execution_friction_usd=1.0,
            explicit_cost_usd=1.0,
            net_pnl_usd=-5.0,
        ),
    )


def _evaluation_policy(starting_equity_usd: float) -> TradingEvaluationPolicy:
    return TradingEvaluationPolicy(
        version="g4-paper-evaluation-v1",
        starting_equity_usd=starting_equity_usd,
        calibration_bucket_count=2,
    )


def _proof_assessment(
    sources,
    *,
    evaluated_at_unix_ms: int,
    fingerprint: str,
    trade_count: int,
    distinct_mints: int,
    expectancy_pct: float,
    profit_factor: float,
    drawdown_pct: float,
    cost_burden_pct: float,
    candidate_version: str | None = None,
    paper_run_id: str | None = None,
) -> CandidateProofAssessment:
    observed = {
        PaperProofGateCode.MIN_PAPER_TRADE_COUNT: trade_count,
        PaperProofGateCode.MIN_PAPER_DISTINCT_MINT_COUNT: distinct_mints,
        PaperProofGateCode.MIN_PAPER_NET_EXPECTANCY_PCT: expectancy_pct,
        PaperProofGateCode.MIN_PAPER_PROFIT_FACTOR: profit_factor,
        PaperProofGateCode.MAX_PAPER_DRAWDOWN_PCT: drawdown_pct,
        PaperProofGateCode.MAX_PAPER_COST_BURDEN_PCT: cost_burden_pct,
    }
    gates = tuple(
        PaperProofGateResult(
            code=code,
            status=PaperProofGateStatus.PASS,
            observed_value=observed.get(code, 1),
            threshold_value=1,
            message=f"{code.value} checked",
        )
        for code in sorted(PaperProofGateCode, key=lambda value: value.value)
    )
    return CandidateProofAssessment(
        schema_version=PAPER_PROOF_SCHEMA_VERSION,
        policy_version="paper-proof-v1",
        candidate_version=(
            sources.manifest.candidate.candidate_version
            if candidate_version is None
            else candidate_version
        ),
        candidate_fingerprint_sha256=sources.manifest.candidate.candidate_fingerprint_sha256,
        registry_fingerprint_sha256=SHA_A,
        e8_assessment_fingerprint_sha256=SHA_B,
        paper_run_id=(sources.manifest.paper_run_id if paper_run_id is None else paper_run_id),
        paper_ledger_fingerprint_sha256=SHA_C,
        paper_evaluation_fingerprint_sha256=SHA_D,
        paper_trade_evidence_fingerprint_sha256=SHA_A,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        gates=gates,
        decision=PaperProofDecision.SUFFICIENT,
        assessment_fingerprint_sha256=fingerprint,
    )


def _promotion_assessment(
    sources,
    *,
    evaluated_at_unix_ms: int,
    fingerprint: str,
    decision: PromotionDecision,
    candidate_version: str | None = None,
) -> PromotionAssessment:
    statuses = {code: PromotionGateStatus.PASS for code in PromotionGateCode}
    if decision is PromotionDecision.INELIGIBLE:
        statuses[PromotionGateCode.MIN_NET_EXPECTANCY_PCT] = PromotionGateStatus.FAIL
    elif decision is PromotionDecision.INSUFFICIENT_EVIDENCE:
        statuses[PromotionGateCode.MIN_TRADE_COUNT] = PromotionGateStatus.INSUFFICIENT
    gates = tuple(
        PromotionGateResult(
            code=code,
            status=statuses[code],
            observed_value=1,
            threshold_value=1,
            message=f"{code.value} checked",
        )
        for code in sorted(PromotionGateCode, key=lambda value: value.value)
    )
    return PromotionAssessment(
        schema_version=PROMOTION_SCHEMA_VERSION,
        policy_version="promotion-v1",
        candidate_version=(
            sources.manifest.candidate.candidate_version
            if candidate_version is None
            else candidate_version
        ),
        candidate_fingerprint_sha256=sources.manifest.candidate.candidate_fingerprint_sha256,
        registry_fingerprint_sha256=SHA_A,
        evaluation_fingerprint_sha256=SHA_B,
        trade_evidence_fingerprint_sha256=SHA_C,
        shadow_ledger_fingerprint_sha256=SHA_D,
        baseline_evaluation_identities=(),
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        gates=gates,
        decision=decision,
        assessment_fingerprint_sha256=fingerprint,
    )


def test_money_telemetry_copies_sealed_evaluator_metrics_and_calls_it_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base = _sources(tmp_path)
    trades = _trades(base.manifest.candidate.candidate_version)
    sources = replace(base, evaluated_trades=trades, optional_source_errors=())
    policy = _evaluation_policy(sources.state.ledger.starting_cash_usd)
    expected = evaluate_trading_performance(
        candidate_version=sources.manifest.candidate.candidate_version,
        model_version=sources.manifest.candidate.model_version,
        trades=trades,
        probability_observations=(),
        policy=policy,
    ).metrics
    calls = 0
    real_evaluator = financial_module.evaluate_trading_performance

    def recording_evaluator(**kwargs):
        nonlocal calls
        calls += 1
        return real_evaluator(**kwargs)

    monkeypatch.setattr(financial_module, "evaluate_trading_performance", recording_evaluator)

    money, _proof_risk = compose_financial_telemetry(sources, evaluation_policy=policy)

    assert calls == 1
    assert money.status is LayerStatus.HEALTHY
    assert money.daily_loss_usd is None
    assert money.performance is not None
    assert money.performance.trade_count == expected.trade_count
    assert money.performance.net_pnl_usd == expected.net_pnl_usd
    assert money.performance.net_expectancy_usd == expected.net_expectancy_usd
    assert money.performance.net_expectancy_pct == expected.net_expectancy_pct
    assert money.performance.profit_factor == expected.profit_factor
    assert money.performance.maximum_drawdown_usd == expected.maximum_drawdown_usd
    assert money.performance.maximum_drawdown_pct == expected.maximum_drawdown_pct
    assert money.performance.turnover_usd == expected.turnover_usd
    assert money.performance.execution_friction_usd == expected.execution_friction_usd
    assert money.performance.explicit_cost_usd == expected.explicit_cost_usd
    assert money.performance.total_cost_usd == expected.total_cost_usd
    assert money.performance.cost_burden_pct == expected.cost_burden_pct


def test_proof_risk_copies_latest_matching_persisted_assessments_without_recomputing(
    tmp_path: Path,
) -> None:
    base = _sources(tmp_path)
    older = _proof_assessment(
        base,
        evaluated_at_unix_ms=AS_OF - 2,
        fingerprint=SHA_A,
        trade_count=5,
        distinct_mints=4,
        expectancy_pct=0.5,
        profit_factor=1.1,
        drawdown_pct=9.0,
        cost_burden_pct=2.0,
    )
    same_time_lower = _proof_assessment(
        base,
        evaluated_at_unix_ms=AS_OF - 1,
        fingerprint=SHA_B,
        trade_count=10,
        distinct_mints=6,
        expectancy_pct=1.0,
        profit_factor=1.5,
        drawdown_pct=6.0,
        cost_burden_pct=1.0,
    )
    chosen = _proof_assessment(
        base,
        evaluated_at_unix_ms=AS_OF - 1,
        fingerprint=SHA_C,
        trade_count=11,
        distinct_mints=7,
        expectancy_pct=1.25,
        profit_factor=1.8,
        drawdown_pct=4.5,
        cost_burden_pct=0.75,
    )
    unrelated = _proof_assessment(
        base,
        evaluated_at_unix_ms=AS_OF - 1,
        fingerprint=SHA_D,
        trade_count=999,
        distinct_mints=999,
        expectancy_pct=99.0,
        profit_factor=99.0,
        drawdown_pct=99.0,
        cost_burden_pct=99.0,
        paper_run_id="other-run",
    )
    future = _proof_assessment(
        base,
        evaluated_at_unix_ms=AS_OF + 1,
        fingerprint=SHA_D,
        trade_count=888,
        distinct_mints=888,
        expectancy_pct=88.0,
        profit_factor=88.0,
        drawdown_pct=88.0,
        cost_burden_pct=88.0,
    )
    promotion_lower = _promotion_assessment(
        base,
        evaluated_at_unix_ms=AS_OF - 1,
        fingerprint=SHA_B,
        decision=PromotionDecision.INELIGIBLE,
    )
    promotion_chosen = _promotion_assessment(
        base,
        evaluated_at_unix_ms=AS_OF - 1,
        fingerprint=SHA_C,
        decision=PromotionDecision.ELIGIBLE,
    )
    sources = replace(
        base,
        proof_assessments=(older, same_time_lower, chosen, unrelated, future),
        promotion_assessments=(promotion_lower, promotion_chosen),
        optional_source_errors=(),
    )
    policy = _evaluation_policy(sources.state.ledger.starting_cash_usd)

    _money, proof_risk = compose_financial_telemetry(sources, evaluation_policy=policy)

    assert proof_risk.status is LayerStatus.HEALTHY
    assert proof_risk.proof_decision == chosen.decision.value
    assert proof_risk.proof_gate_count == len(chosen.gates)
    assert proof_risk.proof_pass_count == len(chosen.gates)
    assert proof_risk.proof_fail_count == 0
    assert proof_risk.proof_insufficient_count == 0
    assert proof_risk.proof_trade_count == 11
    assert proof_risk.proof_distinct_mint_count == 7
    assert proof_risk.proof_net_expectancy_pct == 1.25
    assert proof_risk.proof_profit_factor == 1.8
    assert proof_risk.proof_maximum_drawdown_pct == 4.5
    assert proof_risk.proof_cost_burden_pct == 0.75
    assert proof_risk.promotion_decision == PromotionDecision.ELIGIBLE.value
    assert proof_risk.promotion_gate_count == len(promotion_chosen.gates)
    assert proof_risk.global_risk_halt is base.manifest.global_risk_halt
    assert proof_risk.accounting_integrity == base.accounting_status
    assert proof_risk.live_state == "DISABLED"
    assert proof_risk.kill_switch_active is None


def test_invalid_or_missing_optional_proof_sources_degrade_without_fabrication(
    tmp_path: Path,
) -> None:
    base = _sources(tmp_path)
    sources = replace(
        base,
        proof_assessments=(),
        promotion_assessments=(),
        optional_source_errors=(
            "PROOF_ASSESSMENT_INVALID",
            "PROMOTION_ASSESSMENT_UNAVAILABLE",
        ),
    )
    policy = _evaluation_policy(sources.state.ledger.starting_cash_usd)

    _money, proof_risk = compose_financial_telemetry(sources, evaluation_policy=policy)

    assert proof_risk.status is LayerStatus.DEGRADED
    assert proof_risk.source_errors == sources.optional_source_errors
    assert proof_risk.proof_decision is None
    assert proof_risk.proof_trade_count is None
    assert proof_risk.proof_net_expectancy_pct is None
    assert proof_risk.proof_profit_factor is None
    assert proof_risk.proof_maximum_drawdown_pct is None
    assert proof_risk.proof_cost_burden_pct is None
    assert proof_risk.promotion_decision is None
    assert proof_risk.kill_switch_active is None


def test_evaluation_policy_is_explicit_and_must_match_paper_starting_equity(
    tmp_path: Path,
) -> None:
    sources = _sources(tmp_path)
    wrong = _evaluation_policy(sources.state.ledger.starting_cash_usd + 1.0)

    with pytest.raises(ValueError, match="starting equity"):
        compose_financial_telemetry(sources, evaluation_policy=wrong)
