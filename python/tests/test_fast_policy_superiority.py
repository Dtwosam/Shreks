from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.evaluation import (
    EvaluatedTrade,
    TradingEvaluationEvidence,
    TradingEvaluationPolicy,
    evaluate_trading_performance,
)
from shreks_brain.fast_paper import (
    FAST_PAPER_EVENT_LOOP_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperEventRecord,
    FastPaperLoopState,
    FastPaperMarketCursor,
)
from shreks_brain.fast_policy_proof import (
    FastPolicyProofDecision,
    FastPolicyProofGateCode,
    FastPolicyProofGateStatus,
    FastPolicySuperiorityPolicy,
    build_fast_policy_run_evidence,
    evaluate_fast_policy_superiority,
)


def _assessment(event, market, sequence, at, strategy, action):
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=event,
        market_key=market,
        source_sequence=sequence,
        as_of_unix_ms=at,
        strategy_family=strategy,
        strategy_version=f"{strategy}-v1",
        action=action,
        reasons=(f"{action.value.lower()}_fixture",),
    )


def _loop(strategy: str, *, mutate_population: bool = False):
    rows = (
        ("event-1", "market-a", 1, 1_000, FastPaperAction.BUY),
        ("event-2", "market-b", 1, 1_200, FastPaperAction.SKIP),
        ("event-3", "market-a", 2, 1_800, FastPaperAction.SELL),
        ("event-4", "market-b", 2, 2_200, FastPaperAction.SKIP),
    )
    records = []
    for index, (event, market, sequence, at, action) in enumerate(rows, start=1):
        fingerprint_digit = 9 if mutate_population and index == 4 else index
        records.append(
            FastPaperEventRecord(
                source_event_id=event,
                update_fingerprint=str(fingerprint_digit) * 64,
                market_key=market,
                source_sequence=sequence,
                as_of_unix_ms=at,
                is_material=True,
                assessment=_assessment(event, market, sequence, at, strategy, action),
            )
        )
    return FastPaperLoopState(
        version=FAST_PAPER_EVENT_LOOP_VERSION,
        market_cursors=(
            FastPaperMarketCursor("market-a", 2, 1_800),
            FastPaperMarketCursor("market-b", 2, 2_200),
        ),
        records=tuple(records),
    )


def _trading(candidate: str, pnls: tuple[float, float], *, policy_version="eval-v1"):
    policy = TradingEvaluationPolicy(
        version=policy_version,
        starting_equity_usd=10_000.0,
        calibration_bucket_count=10,
    )
    trades = tuple(
        EvaluatedTrade(
            candidate_version=candidate,
            position_id=f"{candidate}-position-{index}",
            candidate_mint=f"mint-{index}",
            setup_name="fast-policy",
            market_regime="NORMAL",
            opened_at_unix_ms=1_050 + index * 100,
            closed_at_unix_ms=1_500 + index * 500,
            entry_notional_usd=100.0,
            turnover_usd=210.0,
            gross_pnl_usd=pnl + 2.0,
            execution_friction_usd=1.0,
            explicit_cost_usd=1.0,
            net_pnl_usd=pnl,
        )
        for index, pnl in enumerate(pnls, start=1)
    )
    report = evaluate_trading_performance(trades, (), policy, candidate)
    return TradingEvaluationEvidence(
        candidate_version=candidate,
        policy=policy,
        trades=trades,
        probability_observations=(),
        report=report,
    )


def _run(
    candidate: str,
    pnls: tuple[float, float],
    *,
    mutate_population=False,
    policy_version="eval-v1",
):
    return build_fast_policy_run_evidence(
        paper_run_id=f"run-{candidate}",
        candidate_fingerprint_sha256=(
            "a" * 64 if candidate == "learned-v1" else ("b" * 64 if candidate == "baseline-a" else "c" * 64)
        ),
        strategy_version=f"{candidate}-strategy-v1",
        loop_state=_loop(candidate, mutate_population=mutate_population),
        trading_evaluation=_trading(candidate, pnls, policy_version=policy_version),
    )


def _policy(**overrides):
    values = dict(
        version="fl9-proof-policy-v1",
        required_baseline_versions=("baseline-a", "baseline-b"),
        min_material_decision_count=4,
        min_distinct_market_count=2,
        min_evaluation_span_ms=1_000,
        min_trade_count=2,
        min_distinct_traded_mint_count=2,
        min_net_expectancy_pct=0.0,
        min_profit_factor=1.0,
        max_drawdown_pct=50.0,
        max_cost_burden_pct=10.0,
        max_single_winner_share_of_positive_pnl=1.0,
        min_baseline_expectancy_advantage_pct=1.0,
    )
    values.update(overrides)
    return FastPolicySuperiorityPolicy(**values)


def _gate(report, code):
    return next(value for value in report.gates if value.code is code)


def _fixture():
    candidate = _run("learned-v1", (25.0, -5.0))
    baseline_a = _run("baseline-a", (15.0, -5.0))
    baseline_b = _run("baseline-b", (15.0, -5.0))
    return candidate, baseline_a, baseline_b


def test_candidate_beats_best_required_baseline_after_costs() -> None:
    candidate, baseline_a, baseline_b = _fixture()
    report = evaluate_fast_policy_superiority(
        candidate,
        (baseline_a, baseline_b),
        _policy(),
    )

    assert report.decision is FastPolicyProofDecision.SUPERIOR
    assert report.best_baseline_version == "baseline-a"
    assert report.candidate_net_expectancy_pct == pytest.approx(10.0)
    assert report.best_baseline_net_expectancy_pct == pytest.approx(5.0)
    assert report.expectancy_advantage_pct == pytest.approx(5.0)
    assert _gate(
        report, FastPolicyProofGateCode.BASELINE_EXPECTANCY_ADVANTAGE
    ).status is FastPolicyProofGateStatus.PASS
    assert tuple(value.code.value for value in report.gates) == tuple(
        sorted(value.code.value for value in report.gates)
    )


def test_missing_required_baseline_is_insufficient_not_superior() -> None:
    candidate, baseline_a, _ = _fixture()
    report = evaluate_fast_policy_superiority(candidate, (baseline_a,), _policy())
    assert report.decision is FastPolicyProofDecision.INSUFFICIENT_EVIDENCE
    assert _gate(
        report, FastPolicyProofGateCode.BASELINE_COVERAGE
    ).status is FastPolicyProofGateStatus.INSUFFICIENT


def test_below_baseline_margin_fails() -> None:
    candidate, baseline_a, baseline_b = _fixture()
    policy = _policy(min_baseline_expectancy_advantage_pct=6.0)
    report = evaluate_fast_policy_superiority(candidate, (baseline_a, baseline_b), policy)
    assert report.decision is FastPolicyProofDecision.FAILED
    assert _gate(
        report, FastPolicyProofGateCode.BASELINE_EXPECTANCY_ADVANTAGE
    ).status is FastPolicyProofGateStatus.FAIL


def test_population_or_evaluation_policy_mismatch_fails_comparability() -> None:
    candidate, baseline_a, baseline_b = _fixture()
    mismatched_population = _run(
        "baseline-b",
        (15.0, -5.0),
        mutate_population=True,
    )
    report = evaluate_fast_policy_superiority(
        candidate, (baseline_a, mismatched_population), _policy()
    )
    assert report.decision is FastPolicyProofDecision.FAILED
    assert _gate(
        report, FastPolicyProofGateCode.COMPARISON_POPULATION
    ).status is FastPolicyProofGateStatus.FAIL

    mismatched_policy = _run("baseline-b", (15.0, -5.0), policy_version="other-eval")
    report = evaluate_fast_policy_superiority(
        candidate, (baseline_a, mismatched_policy), _policy()
    )
    assert report.decision is FastPolicyProofDecision.FAILED
    assert _gate(
        report, FastPolicyProofGateCode.EVALUATION_POLICY_MATCH
    ).status is FastPolicyProofGateStatus.FAIL


@pytest.mark.parametrize(
    "field,value,code,status",
    (
        (
            "min_material_decision_count",
            5,
            FastPolicyProofGateCode.MIN_MATERIAL_DECISION_COUNT,
            FastPolicyProofGateStatus.INSUFFICIENT,
        ),
        (
            "min_distinct_market_count",
            3,
            FastPolicyProofGateCode.MIN_DISTINCT_MARKET_COUNT,
            FastPolicyProofGateStatus.INSUFFICIENT,
        ),
        (
            "min_evaluation_span_ms",
            2_000,
            FastPolicyProofGateCode.MIN_EVALUATION_SPAN,
            FastPolicyProofGateStatus.INSUFFICIENT,
        ),
        (
            "min_trade_count",
            3,
            FastPolicyProofGateCode.MIN_TRADE_COUNT,
            FastPolicyProofGateStatus.INSUFFICIENT,
        ),
        (
            "min_distinct_traded_mint_count",
            3,
            FastPolicyProofGateCode.MIN_DISTINCT_TRADED_MINT_COUNT,
            FastPolicyProofGateStatus.INSUFFICIENT,
        ),
        (
            "min_net_expectancy_pct",
            11.0,
            FastPolicyProofGateCode.MIN_NET_EXPECTANCY_PCT,
            FastPolicyProofGateStatus.FAIL,
        ),
        (
            "min_profit_factor",
            6.0,
            FastPolicyProofGateCode.MIN_PROFIT_FACTOR,
            FastPolicyProofGateStatus.FAIL,
        ),
        (
            "max_cost_burden_pct",
            0.5,
            FastPolicyProofGateCode.MAX_COST_BURDEN_PCT,
            FastPolicyProofGateStatus.FAIL,
        ),
    ),
)
def test_candidate_sample_and_economic_gates(field, value, code, status) -> None:
    candidate, baseline_a, baseline_b = _fixture()
    report = evaluate_fast_policy_superiority(
        candidate,
        (baseline_a, baseline_b),
        replace(_policy(), **{field: value}),
    )
    assert report.decision is (
        FastPolicyProofDecision.INSUFFICIENT_EVIDENCE
        if status is FastPolicyProofGateStatus.INSUFFICIENT
        else FastPolicyProofDecision.FAILED
    )
    assert _gate(report, code).status is status


def test_undeclared_or_duplicate_baselines_are_rejected() -> None:
    candidate, baseline_a, baseline_b = _fixture()
    extra = _run("baseline-extra", (1.0, -1.0))
    with pytest.raises(ValueError, match="baseline"):
        evaluate_fast_policy_superiority(
            candidate, (baseline_a, baseline_b, extra), _policy()
        )
    with pytest.raises(ValueError, match="duplicate|baseline"):
        evaluate_fast_policy_superiority(
            candidate, (baseline_a, baseline_a), _policy()
        )


def test_same_inputs_produce_same_report_fingerprint() -> None:
    candidate, baseline_a, baseline_b = _fixture()
    first = evaluate_fast_policy_superiority(
        candidate, (baseline_a, baseline_b), _policy()
    )
    second = evaluate_fast_policy_superiority(
        candidate, (baseline_a, baseline_b), _policy()
    )
    assert first == second
    assert len(first.report_fingerprint_sha256) == 64
