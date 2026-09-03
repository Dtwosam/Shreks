from __future__ import annotations

from dataclasses import replace
import json

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
    FastPolicySuperiorityPolicy,
    build_fast_policy_run_evidence,
    decode_fast_policy_superiority_report,
    encode_fast_policy_superiority_report,
    evaluate_fast_policy_superiority,
)


def _run(candidate: str, sha: str, pnls: tuple[float, float]):
    records = tuple(
        FastPaperEventRecord(
            source_event_id=f"event-{index}",
            update_fingerprint=str(index) * 64,
            market_key="market-a",
            source_sequence=index,
            as_of_unix_ms=1_000 + index * 500,
            is_material=True,
            assessment=FastPaperActionAssessment(
                version="assessment-v1",
                source_event_id=f"event-{index}",
                market_key="market-a",
                source_sequence=index,
                as_of_unix_ms=1_000 + index * 500,
                strategy_family=candidate,
                strategy_version=f"{candidate}-v1",
                action=(FastPaperAction.BUY if index == 1 else FastPaperAction.SELL),
                reasons=("fixture",),
            ),
        )
        for index in (1, 2)
    )
    loop = FastPaperLoopState(
        version=FAST_PAPER_EVENT_LOOP_VERSION,
        market_cursors=(FastPaperMarketCursor("market-a", 2, 2_000),),
        records=records,
    )
    policy = TradingEvaluationPolicy("eval-v1", 10_000.0, 10)
    trades = tuple(
        EvaluatedTrade(
            candidate_version=candidate,
            position_id=f"{candidate}-{index}",
            candidate_mint=f"mint-{index}",
            setup_name="fast-policy",
            market_regime="NORMAL",
            opened_at_unix_ms=1_550,
            closed_at_unix_ms=1_700 + index * 100,
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
    evidence = TradingEvaluationEvidence(candidate, policy, trades, (), report)
    return build_fast_policy_run_evidence(
        paper_run_id=f"run-{candidate}",
        candidate_fingerprint_sha256=sha,
        strategy_version=f"{candidate}-strategy-v1",
        loop_state=loop,
        trading_evaluation=evidence,
    )


def _report():
    candidate = _run("learned-v1", "a" * 64, (25.0, -5.0))
    baseline = _run("baseline-a", "b" * 64, (15.0, -5.0))
    policy = FastPolicySuperiorityPolicy(
        version="proof-v1",
        required_baseline_versions=("baseline-a",),
        min_material_decision_count=2,
        min_distinct_market_count=1,
        min_evaluation_span_ms=500,
        min_trade_count=2,
        min_distinct_traded_mint_count=2,
        min_net_expectancy_pct=0.0,
        min_profit_factor=1.0,
        max_drawdown_pct=50.0,
        max_cost_burden_pct=10.0,
        max_single_winner_share_of_positive_pnl=1.0,
        min_baseline_expectancy_advantage_pct=1.0,
    )
    return evaluate_fast_policy_superiority(candidate, (baseline,), policy)


def test_codec_is_canonical_and_round_trips_exact_report() -> None:
    report = _report()
    payload = encode_fast_policy_superiority_report(report)
    assert payload == json.dumps(
        json.loads(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert decode_fast_policy_superiority_report(payload) == report
    assert encode_fast_policy_superiority_report(
        decode_fast_policy_superiority_report(payload)
    ) == payload


def test_codec_rejects_unknown_fields_and_fingerprint_tampering() -> None:
    payload = encode_fast_policy_superiority_report(_report())
    document = json.loads(payload)

    unknown = dict(document)
    unknown["unexpected"] = True
    with pytest.raises(ValueError, match="field|unknown|malformed"):
        decode_fast_policy_superiority_report(
            json.dumps(unknown, sort_keys=True, separators=(",", ":"))
        )

    tampered = dict(document)
    tampered["report_fingerprint_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_policy_superiority_report(
            json.dumps(tampered, sort_keys=True, separators=(",", ":"))
        )


def test_codec_rejects_noncanonical_json() -> None:
    payload = encode_fast_policy_superiority_report(_report())
    with pytest.raises(ValueError, match="canonical"):
        decode_fast_policy_superiority_report(
            json.dumps(json.loads(payload), sort_keys=False, indent=2)
        )
