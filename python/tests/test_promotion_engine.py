from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.evaluation import (
    EvaluatedTrade,
    ProbabilityObservation,
    TradingEvaluationPolicy,
    TradingEvaluationReport,
    evaluate_trading_performance,
)
from shreks_brain.promotion import (
    PromotionDecision,
    PromotionGateCode,
    PromotionGateStatus,
    PromotionPolicy,
    evaluate_promotion,
)
from shreks_brain.registry import (
    CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
    RegistryCandidate,
    RegistryEvaluationEvidence,
    RegistryStatus,
    RegistryStatusEvent,
)
from shreks_brain.registry.codec import (
    build_registry,
    compute_candidate_fingerprint,
    compute_event_fingerprint,
)
from shreks_brain.shadow import (
    SHADOW_CHALLENGER_SCHEMA_VERSION,
    ShadowDecisionRecord,
    ShadowReasonCode,
)
from shreks_brain.shadow.codec import build_ledger
from shreks_brain.shadow.fingerprint import record_fingerprint


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _trades(
    candidate_version: str,
    nets: tuple[float, ...] = (20.0, 10.0, -5.0, 5.0),
) -> tuple[EvaluatedTrade, ...]:
    values = []
    for index, net in enumerate(nets):
        values.append(
            EvaluatedTrade(
                candidate_version=candidate_version,
                position_id=f"{candidate_version}-p{index}",
                candidate_mint=f"mint-{index}",
                setup_name="fresh_launch_continuation",
                market_regime="HOT",
                opened_at_unix_ms=1_000 + index * 1_000,
                closed_at_unix_ms=1_500 + index * 1_000,
                entry_notional_usd=100.0,
                turnover_usd=200.0,
                gross_pnl_usd=net + 2.0,
                execution_friction_usd=1.0,
                explicit_cost_usd=1.0,
                net_pnl_usd=net,
            )
        )
    return tuple(values)


def _report(
    candidate_version: str,
    nets: tuple[float, ...] = (20.0, 10.0, -5.0, 5.0),
) -> TradingEvaluationReport:
    observations = (
        ProbabilityObservation(
            candidate_version=candidate_version,
            model_version=f"{candidate_version}-model",
            candidate_mint="mint-cal-a",
            as_of_unix_ms=500,
            positive_probability=0.8,
            target_positive=True,
            setup_name="fresh_launch_continuation",
            market_regime="HOT",
            fold_name="fold-a",
        ),
        ProbabilityObservation(
            candidate_version=candidate_version,
            model_version=f"{candidate_version}-model",
            candidate_mint="mint-cal-b",
            as_of_unix_ms=600,
            positive_probability=0.2,
            target_positive=False,
            setup_name="fresh_launch_continuation",
            market_regime="HOT",
            fold_name="fold-a",
        ),
    )
    return evaluate_trading_performance(
        _trades(candidate_version, nets),
        observations,
        policy=TradingEvaluationPolicy(
            version="eval-policy-v1",
            starting_equity_usd=1_000.0,
            calibration_bucket_count=2,
        ),
        candidate_version=candidate_version,
    )


def _candidate(
    candidate_version: str,
    report: TradingEvaluationReport,
    *,
    registered_at_unix_ms: int = 100,
) -> RegistryCandidate:
    calibration = report.calibration
    draft = RegistryCandidate(
        schema_version=CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
        candidate_version=candidate_version,
        strategy_version="strategy-v1",
        model_version="model-v1",
        model_training_schema_version="e3-training-v1",
        model_training_fingerprint_sha256=SHA_A,
        feature_schema_version="d6-research-v1",
        feature_columns=("market_liquidity_usd",),
        training_started_at_unix_ms=10,
        training_ended_at_unix_ms=90,
        validation_schema_version="e4-time-validation-v1",
        validation_policy_version="walk-forward-v1",
        validation_run_fingerprint_sha256=SHA_B,
        evaluation=RegistryEvaluationEvidence(
            schema_version=report.schema_version,
            policy_version=report.policy_version,
            evaluation_fingerprint_sha256=report.evaluation_fingerprint_sha256,
            trade_count=report.metrics.trade_count,
            net_pnl_usd=report.metrics.net_pnl_usd,
            net_expectancy_usd=report.metrics.net_expectancy_usd,
            net_expectancy_pct=report.metrics.net_expectancy_pct,
            profit_factor=report.metrics.profit_factor,
            maximum_drawdown_usd=report.metrics.maximum_drawdown_usd,
            maximum_drawdown_pct=report.metrics.maximum_drawdown_pct,
            win_rate=report.metrics.win_rate,
            turnover_usd=report.metrics.turnover_usd,
            total_cost_usd=report.metrics.total_cost_usd,
            brier_score=None if calibration is None else calibration.brier_score,
            expected_calibration_error=(
                None if calibration is None else calibration.expected_calibration_error
            ),
        ),
        registered_at_unix_ms=registered_at_unix_ms,
        initial_status=RegistryStatus.CHALLENGER,
        candidate_fingerprint_sha256="0" * 64,
    )
    return replace(
        draft,
        candidate_fingerprint_sha256=compute_candidate_fingerprint(draft),
    )


def _shadow_record(
    candidate: RegistryCandidate,
    registry_fingerprint: str,
    *,
    index: int,
    candidate_fingerprint: str | None = None,
) -> ShadowDecisionRecord:
    draft = ShadowDecisionRecord(
        schema_version=SHADOW_CHALLENGER_SCHEMA_VERSION,
        candidate_version=candidate.candidate_version,
        strategy_version=candidate.strategy_version,
        candidate_fingerprint_sha256=(
            candidate.candidate_fingerprint_sha256
            if candidate_fingerprint is None
            else candidate_fingerprint
        ),
        registry_fingerprint_sha256=registry_fingerprint,
        model_version=candidate.model_version or "",
        model_training_fingerprint_sha256=(
            candidate.model_training_fingerprint_sha256 or ""
        ),
        target_horizon_seconds=300,
        target_minimum_return_pct=5.0,
        shadow_policy_version="shadow-policy-v1",
        enter_min_probability=0.7,
        candidate_mint=f"shadow-mint-{index}",
        as_of_unix_ms=5_000 + index * 1_000,
        dataset_schema_version="d6-research-v1",
        decision_feature_fingerprint_sha256=SHA_C,
        setup_name="fresh_launch_continuation",
        safety_decision="PASS",
        setup_state="READY",
        market_regime="HOT",
        baseline_action=DecisionAction.WATCH,
        positive_probability=0.8,
        challenger_action=DecisionAction.ENTER,
        reason=ShadowReasonCode.PROBABILITY_ENTER_APPROVED,
        record_fingerprint_sha256="0" * 64,
    )
    return replace(draft, record_fingerprint_sha256=record_fingerprint(draft))


def _policy(**changes: object) -> PromotionPolicy:
    kwargs = dict(
        version="promotion-policy-v1",
        min_trade_count=4,
        min_evaluation_span_ms=3_000,
        min_net_expectancy_pct=1.0,
        min_profit_factor=1.0,
        max_drawdown_pct=100.0,
        max_cost_burden_pct=100.0,
        max_brier_score=1.0,
        max_expected_calibration_error=1.0,
        required_baseline_versions=("baseline-a",),
        min_baseline_expectancy_advantage_pct=1.0,
        max_single_winner_share_of_positive_pnl=0.6,
        min_shadow_decision_count=3,
        min_shadow_distinct_mint_count=3,
        min_shadow_span_ms=2_000,
    )
    kwargs.update(changes)
    return PromotionPolicy(**kwargs)


def _fixture():
    challenger_report = _report("challenger-v1")
    baseline_report = _report("baseline-a", (2.0, 1.0, -2.0, -1.0))
    challenger = _candidate("challenger-v1", challenger_report)
    registry = build_registry((challenger,), ())
    shadow = build_ledger(
        tuple(
            _shadow_record(challenger, registry.registry_fingerprint_sha256, index=index)
            for index in range(3)
        )
    )
    return challenger_report, baseline_report, challenger, registry, shadow


def _gate(assessment, code: PromotionGateCode):
    return next(value for value in assessment.gates if value.code is code)


def test_passing_evidence_is_eligible_but_does_not_mutate_registry() -> None:
    report, baseline, candidate, registry, shadow = _fixture()
    before = registry

    result = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (baseline,),
        _policy(),
        10_000,
    )

    assert result.decision is PromotionDecision.ELIGIBLE
    assert all(value.status is PromotionGateStatus.PASS for value in result.gates)
    assert len(result.assessment_fingerprint_sha256) == 64
    assert len(result.trade_evidence_fingerprint_sha256) == 64
    assert registry == before
    assert registry.current_status(candidate.candidate_version) is RegistryStatus.CHALLENGER


def test_insufficient_sample_does_not_become_failed_performance() -> None:
    report, baseline, candidate, registry, shadow = _fixture()
    result = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (baseline,),
        _policy(min_trade_count=5),
        10_000,
    )
    assert result.decision is PromotionDecision.INSUFFICIENT_EVIDENCE
    assert _gate(result, PromotionGateCode.MIN_TRADE_COUNT).status is PromotionGateStatus.INSUFFICIENT


def test_failed_economic_gate_dominates_insufficient_evidence() -> None:
    report, _baseline, candidate, registry, shadow = _fixture()
    result = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (),
        _policy(min_net_expectancy_pct=8.0),
        10_000,
    )
    assert result.decision is PromotionDecision.INELIGIBLE
    assert _gate(result, PromotionGateCode.MIN_NET_EXPECTANCY_PCT).status is PromotionGateStatus.FAIL
    assert _gate(result, PromotionGateCode.BASELINE_COVERAGE).status is PromotionGateStatus.INSUFFICIENT


def test_missing_required_baseline_is_insufficient_not_zero_scored() -> None:
    report, _baseline, candidate, registry, shadow = _fixture()
    result = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (),
        _policy(),
        10_000,
    )
    assert result.decision is PromotionDecision.INSUFFICIENT_EVIDENCE
    assert _gate(result, PromotionGateCode.BASELINE_COVERAGE).status is PromotionGateStatus.INSUFFICIENT


def test_baseline_expectancy_margin_is_a_real_failure() -> None:
    report, _baseline, candidate, registry, shadow = _fixture()
    strong_baseline = _report("baseline-a", (20.0, 10.0, -5.0, 4.0))
    result = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (strong_baseline,),
        _policy(min_baseline_expectancy_advantage_pct=1.0),
        10_000,
    )
    assert result.decision is PromotionDecision.INELIGIBLE
    assert _gate(result, PromotionGateCode.BASELINE_EXPECTANCY_ADVANTAGE).status is PromotionGateStatus.FAIL


def test_current_champion_is_automatically_required_as_baseline() -> None:
    report, _baseline, candidate, _registry, _shadow = _fixture()
    champion_report = _report("champion-v1", (2.0, 1.0, -2.0, -1.0))
    champion = _candidate("champion-v1", champion_report)
    draft_event = RegistryStatusEvent(
        candidate_version="champion-v1",
        from_status=RegistryStatus.CHALLENGER,
        to_status=RegistryStatus.CHAMPION,
        decision_reference="prior-promotion",
        decided_at_unix_ms=200,
        reason="prior explicit promotion",
        event_fingerprint_sha256="0" * 64,
    )
    event = replace(
        draft_event,
        event_fingerprint_sha256=compute_event_fingerprint(draft_event),
    )
    registry = build_registry((candidate, champion), (event,))
    shadow = build_ledger(
        tuple(
            _shadow_record(candidate, registry.registry_fingerprint_sha256, index=index)
            for index in range(3)
        )
    )

    missing = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (),
        _policy(required_baseline_versions=()),
        10_000,
    )
    assert _gate(missing, PromotionGateCode.BASELINE_COVERAGE).status is PromotionGateStatus.INSUFFICIENT

    present = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (champion_report,),
        _policy(required_baseline_versions=()),
        10_000,
    )
    assert present.decision is PromotionDecision.ELIGIBLE
    assert present.baseline_evaluation_identities == (
        ("champion-v1", champion_report.evaluation_fingerprint_sha256),
    )


def test_single_winner_concentration_can_block_promotion() -> None:
    report, baseline, candidate, registry, shadow = _fixture()
    result = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (baseline,),
        _policy(max_single_winner_share_of_positive_pnl=0.5),
        10_000,
    )
    assert result.decision is PromotionDecision.INELIGIBLE
    assert _gate(result, PromotionGateCode.MAX_SINGLE_WINNER_SHARE).status is PromotionGateStatus.FAIL


def test_shadow_provenance_mismatch_is_a_failed_gate() -> None:
    report, baseline, candidate, registry, _shadow = _fixture()
    bad_shadow = build_ledger(
        tuple(
            _shadow_record(
                candidate,
                registry.registry_fingerprint_sha256,
                index=index,
                candidate_fingerprint=SHA_C,
            )
            for index in range(3)
        )
    )
    result = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        bad_shadow,
        (baseline,),
        _policy(),
        10_000,
    )
    assert result.decision is PromotionDecision.INELIGIBLE
    assert _gate(result, PromotionGateCode.SHADOW_PROVENANCE).status is PromotionGateStatus.FAIL


def test_trade_evidence_mismatch_is_a_failed_gate_and_changes_trade_hash() -> None:
    report, baseline, candidate, registry, shadow = _fixture()
    canonical = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (baseline,),
        _policy(),
        10_000,
    )
    changed_trades = _trades(candidate.candidate_version, (20.0, 10.0, -5.0, 4.0))
    changed = evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        changed_trades,
        shadow,
        (baseline,),
        _policy(),
        10_000,
    )
    assert changed.decision is PromotionDecision.INELIGIBLE
    assert _gate(changed, PromotionGateCode.TRADE_EVIDENCE_RECONCILIATION).status is PromotionGateStatus.FAIL
    assert changed.trade_evidence_fingerprint_sha256 != canonical.trade_evidence_fingerprint_sha256


def test_evaluation_time_cannot_precede_observed_evidence() -> None:
    report, baseline, candidate, registry, shadow = _fixture()
    with pytest.raises(ValueError, match="evaluated_at_unix_ms"):
        evaluate_promotion(
            registry,
            candidate.candidate_version,
            report,
            _trades(candidate.candidate_version),
            shadow,
            (baseline,),
            _policy(),
            6_000,
        )
