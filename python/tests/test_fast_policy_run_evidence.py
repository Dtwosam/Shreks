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
    FAST_POLICY_PROOF_SCHEMA_NAME,
    FAST_POLICY_PROOF_SCHEMA_VERSION,
    FastPolicyRunEvidence,
    build_fast_policy_run_evidence,
)


def _assessment(event: str, sequence: int, at: int, action: FastPaperAction):
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=event,
        market_key="market-a",
        source_sequence=sequence,
        as_of_unix_ms=at,
        strategy_family="learned-policy",
        strategy_version="fl9-v1",
        action=action,
        reasons=(f"{action.value.lower()}_fixture",),
    )


def _loop(actions=(FastPaperAction.BUY, FastPaperAction.SELL)) -> FastPaperLoopState:
    records = tuple(
        FastPaperEventRecord(
            source_event_id=f"event-{index}",
            update_fingerprint=(str(index) * 64)[:64],
            market_key="market-a",
            source_sequence=index,
            as_of_unix_ms=1_000 + index * 400,
            is_material=True,
            assessment=_assessment(
                f"event-{index}",
                index,
                1_000 + index * 400,
                action,
            ),
        )
        for index, action in enumerate(actions, start=1)
    )
    return FastPaperLoopState(
        version=FAST_PAPER_EVENT_LOOP_VERSION,
        market_cursors=(
            FastPaperMarketCursor(
                market_key="market-a",
                last_source_sequence=len(records),
                last_as_of_unix_ms=records[-1].as_of_unix_ms,
            ),
        ),
        records=records,
    )


def _trading_evidence(candidate: str, net_pnl: float = 10.0) -> TradingEvaluationEvidence:
    policy = TradingEvaluationPolicy(
        version="paper-eval-v1",
        starting_equity_usd=10_000.0,
        calibration_bucket_count=10,
    )
    trade = EvaluatedTrade(
        candidate_version=candidate,
        position_id=f"{candidate}-position-1",
        candidate_mint="mint-a",
        setup_name="learned-policy",
        market_regime="NORMAL",
        opened_at_unix_ms=1_500,
        closed_at_unix_ms=2_000,
        entry_notional_usd=100.0,
        turnover_usd=210.0,
        gross_pnl_usd=net_pnl + 3.0,
        execution_friction_usd=2.0,
        explicit_cost_usd=1.0,
        net_pnl_usd=net_pnl,
    )
    report = evaluate_trading_performance((trade,), (), policy, candidate)
    return TradingEvaluationEvidence(
        candidate_version=candidate,
        policy=policy,
        trades=(trade,),
        probability_observations=(),
        report=report,
    )


def _run(actions=(FastPaperAction.BUY, FastPaperAction.SELL)) -> FastPolicyRunEvidence:
    return build_fast_policy_run_evidence(
        paper_run_id="paper-run-learned",
        candidate_fingerprint_sha256="a" * 64,
        strategy_version="fl9-v1",
        loop_state=_loop(actions),
        trading_evaluation=_trading_evidence("learned-v1"),
    )


def test_schema_and_run_evidence_are_deterministic() -> None:
    assert FAST_POLICY_PROOF_SCHEMA_NAME == "shreks.fast_policy_superiority"
    assert FAST_POLICY_PROOF_SCHEMA_VERSION == 1

    first = _run()
    second = _run()
    assert first == second
    assert first.candidate_version == "learned-v1"
    assert first.material_update_count == 2
    assert first.decision_count == 2
    assert first.distinct_market_count == 1
    assert first.observed_from_unix_ms == 1_400
    assert first.observed_through_unix_ms == 2_000
    assert len(first.event_population_fingerprint_sha256) == 64
    assert len(first.action_journal_fingerprint_sha256) == 64
    assert len(first.run_evidence_fingerprint_sha256) == 64


def test_population_fingerprint_excludes_actions_but_journal_fingerprint_does_not() -> None:
    first = _run((FastPaperAction.BUY, FastPaperAction.SELL))
    second = _run((FastPaperAction.SKIP, FastPaperAction.HOLD))
    assert first.event_population_fingerprint_sha256 == second.event_population_fingerprint_sha256
    assert first.action_journal_fingerprint_sha256 != second.action_journal_fingerprint_sha256


def test_run_evidence_rejects_candidate_mismatch_and_trade_before_population() -> None:
    evidence = _trading_evidence("other-v1")
    with pytest.raises(ValueError, match="candidate"):
        build_fast_policy_run_evidence(
            paper_run_id="paper-run-learned",
            candidate_fingerprint_sha256="a" * 64,
            strategy_version="fl9-v1",
            loop_state=_loop(),
            trading_evaluation=replace(evidence, candidate_version="learned-v1"),
        )

    valid = _trading_evidence("learned-v1")
    early = replace(
        valid.trades[0],
        opened_at_unix_ms=100,
        closed_at_unix_ms=200,
    )
    early_report = evaluate_trading_performance(
        (early,), (), valid.policy, valid.candidate_version
    )
    early_evidence = TradingEvaluationEvidence(
        candidate_version=valid.candidate_version,
        policy=valid.policy,
        trades=(early,),
        probability_observations=(),
        report=early_report,
    )
    with pytest.raises(ValueError, match="window|population"):
        build_fast_policy_run_evidence(
            paper_run_id="paper-run-learned",
            candidate_fingerprint_sha256="a" * 64,
            strategy_version="fl9-v1",
            loop_state=_loop(),
            trading_evaluation=early_evidence,
        )


def test_run_evidence_requires_lowercase_sha_and_nonempty_identity() -> None:
    with pytest.raises(ValueError):
        build_fast_policy_run_evidence(
            paper_run_id="",
            candidate_fingerprint_sha256="a" * 64,
            strategy_version="fl9-v1",
            loop_state=_loop(),
            trading_evaluation=_trading_evidence("learned-v1"),
        )
    with pytest.raises(ValueError):
        build_fast_policy_run_evidence(
            paper_run_id="run",
            candidate_fingerprint_sha256="ABC",
            strategy_version="fl9-v1",
            loop_state=_loop(),
            trading_evaluation=_trading_evidence("learned-v1"),
        )
