from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.promotion import (
    PROMOTION_SCHEMA_VERSION,
    PromotionAssessment,
    PromotionDecision,
    PromotionGateCode,
    PromotionGateResult,
    PromotionGateStatus,
    PromotionPolicy,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def policy(**changes: object) -> PromotionPolicy:
    kwargs = dict(
        version="promotion-policy-v1",
        min_trade_count=100,
        min_evaluation_span_ms=86_400_000,
        min_net_expectancy_pct=0.5,
        min_profit_factor=1.1,
        max_drawdown_pct=20.0,
        max_cost_burden_pct=5.0,
        max_brier_score=0.25,
        max_expected_calibration_error=0.15,
        required_baseline_versions=("baseline-a", "baseline-b"),
        min_baseline_expectancy_advantage_pct=0.1,
        max_single_winner_share_of_positive_pnl=0.35,
        min_shadow_decision_count=100,
        min_shadow_distinct_mint_count=50,
        min_shadow_span_ms=86_400_000,
    )
    kwargs.update(changes)
    return PromotionPolicy(**kwargs)


def gates(
    *,
    override: tuple[PromotionGateCode, PromotionGateStatus] | None = None,
) -> tuple[PromotionGateResult, ...]:
    result = []
    for code in sorted(PromotionGateCode, key=lambda value: value.value):
        status = PromotionGateStatus.PASS
        if override is not None and code is override[0]:
            status = override[1]
        result.append(
            PromotionGateResult(
                code=code,
                status=status,
                observed_value=1,
                threshold_value=1,
                message=f"{code.value} checked",
            )
        )
    return tuple(result)


def assessment(**changes: object) -> PromotionAssessment:
    kwargs = dict(
        schema_version=PROMOTION_SCHEMA_VERSION,
        policy_version="promotion-policy-v1",
        candidate_version="challenger-v1",
        candidate_fingerprint_sha256=SHA_A,
        registry_fingerprint_sha256=SHA_B,
        evaluation_fingerprint_sha256=SHA_C,
        trade_evidence_fingerprint_sha256=SHA_D,
        shadow_ledger_fingerprint_sha256=SHA_E,
        baseline_evaluation_identities=(("baseline-a", SHA_A), ("baseline-b", SHA_B)),
        evaluated_at_unix_ms=1_000,
        gates=gates(),
        decision=PromotionDecision.ELIGIBLE,
        assessment_fingerprint_sha256=SHA_C,
    )
    kwargs.update(changes)
    return PromotionAssessment(**kwargs)


def test_schema_and_enum_contract_is_exact() -> None:
    assert PROMOTION_SCHEMA_VERSION == "e8-promotion-v1"
    assert {value.value for value in PromotionDecision} == {
        "ELIGIBLE",
        "INELIGIBLE",
        "INSUFFICIENT_EVIDENCE",
    }
    assert {value.value for value in PromotionGateStatus} == {
        "PASS",
        "FAIL",
        "INSUFFICIENT",
    }
    assert {value.value for value in PromotionGateCode} == {
        "CURRENT_CHALLENGER",
        "MODEL_VALIDATION_PROVENANCE",
        "EVALUATION_MATCH",
        "TRADE_EVIDENCE_RECONCILIATION",
        "MIN_TRADE_COUNT",
        "MIN_EVALUATION_SPAN",
        "MIN_NET_EXPECTANCY_PCT",
        "MIN_PROFIT_FACTOR",
        "MAX_DRAWDOWN_PCT",
        "MAX_COST_BURDEN_PCT",
        "MAX_BRIER_SCORE",
        "MAX_EXPECTED_CALIBRATION_ERROR",
        "BASELINE_COVERAGE",
        "BASELINE_EXPECTANCY_ADVANTAGE",
        "MAX_SINGLE_WINNER_SHARE",
        "SHADOW_PROVENANCE",
        "MIN_SHADOW_DECISION_COUNT",
        "MIN_SHADOW_DISTINCT_MINT_COUNT",
        "MIN_SHADOW_SPAN",
    }


def test_policy_preserves_explicit_thresholds_and_canonical_baselines() -> None:
    value = policy()
    assert value.min_trade_count == 100
    assert value.min_net_expectancy_pct == 0.5
    assert value.required_baseline_versions == ("baseline-a", "baseline-b")


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("version", ""),
        ("min_trade_count", True),
        ("min_trade_count", -1),
        ("min_evaluation_span_ms", -1),
        ("min_net_expectancy_pct", float("nan")),
        ("min_profit_factor", -0.1),
        ("max_drawdown_pct", -0.1),
        ("max_drawdown_pct", 100.1),
        ("max_cost_burden_pct", -0.1),
        ("max_cost_burden_pct", 100.1),
        ("max_brier_score", -0.1),
        ("max_brier_score", 1.1),
        ("max_expected_calibration_error", -0.1),
        ("max_expected_calibration_error", 1.1),
        ("min_baseline_expectancy_advantage_pct", -0.1),
        ("max_single_winner_share_of_positive_pnl", -0.1),
        ("max_single_winner_share_of_positive_pnl", 1.1),
        ("min_shadow_decision_count", True),
        ("min_shadow_distinct_mint_count", -1),
        ("min_shadow_span_ms", -1),
    ],
)
def test_policy_rejects_invalid_thresholds(field: str, bad: object) -> None:
    with pytest.raises(ValueError, match=field):
        policy(**{field: bad})


def test_policy_requires_unique_lexical_non_empty_baseline_versions() -> None:
    with pytest.raises(ValueError, match="required_baseline_versions"):
        policy(required_baseline_versions=("baseline-b", "baseline-a"))
    with pytest.raises(ValueError, match="required_baseline_versions"):
        policy(required_baseline_versions=("baseline-a", "baseline-a"))
    with pytest.raises(ValueError, match="required_baseline_versions"):
        policy(required_baseline_versions=("",))

    assert policy(required_baseline_versions=()).required_baseline_versions == ()


def test_gate_result_requires_exact_enums_and_non_empty_message() -> None:
    with pytest.raises(ValueError, match="code"):
        PromotionGateResult(
            code="MIN_TRADE_COUNT",  # type: ignore[arg-type]
            status=PromotionGateStatus.PASS,
            observed_value=1,
            threshold_value=1,
            message="ok",
        )
    with pytest.raises(ValueError, match="status"):
        PromotionGateResult(
            code=PromotionGateCode.MIN_TRADE_COUNT,
            status="PASS",  # type: ignore[arg-type]
            observed_value=1,
            threshold_value=1,
            message="ok",
        )
    with pytest.raises(ValueError, match="message"):
        PromotionGateResult(
            code=PromotionGateCode.MIN_TRADE_COUNT,
            status=PromotionGateStatus.PASS,
            observed_value=1,
            threshold_value=1,
            message="",
        )


def test_assessment_requires_canonical_unique_gates_and_baselines() -> None:
    reversed_gates = tuple(reversed(gates()))
    with pytest.raises(ValueError, match="gates"):
        assessment(gates=reversed_gates)

    duplicated = gates() + (gates()[0],)
    with pytest.raises(ValueError, match="gates"):
        assessment(gates=duplicated)

    with pytest.raises(ValueError, match="baseline_evaluation_identities"):
        assessment(
            baseline_evaluation_identities=(("baseline-b", SHA_B), ("baseline-a", SHA_A))
        )


def test_assessment_decision_must_match_gate_precedence() -> None:
    insufficient_gates = gates(
        override=(PromotionGateCode.MIN_TRADE_COUNT, PromotionGateStatus.INSUFFICIENT)
    )
    with pytest.raises(ValueError, match="decision"):
        assessment(gates=insufficient_gates, decision=PromotionDecision.ELIGIBLE)
    assert (
        assessment(
            gates=insufficient_gates,
            decision=PromotionDecision.INSUFFICIENT_EVIDENCE,
        ).decision
        is PromotionDecision.INSUFFICIENT_EVIDENCE
    )

    failed_gates = gates(
        override=(PromotionGateCode.MIN_NET_EXPECTANCY_PCT, PromotionGateStatus.FAIL)
    )
    with pytest.raises(ValueError, match="decision"):
        assessment(
            gates=failed_gates,
            decision=PromotionDecision.INSUFFICIENT_EVIDENCE,
        )
    assert (
        assessment(gates=failed_gates, decision=PromotionDecision.INELIGIBLE).decision
        is PromotionDecision.INELIGIBLE
    )


def test_assessment_requires_exact_schema_and_sha256_fields() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        assessment(schema_version="wrong")
    for field in (
        "candidate_fingerprint_sha256",
        "registry_fingerprint_sha256",
        "evaluation_fingerprint_sha256",
        "trade_evidence_fingerprint_sha256",
        "shadow_ledger_fingerprint_sha256",
        "assessment_fingerprint_sha256",
    ):
        with pytest.raises(ValueError, match=field):
            assessment(**{field: "not-a-sha"})


def test_assessment_is_immutable() -> None:
    value = assessment()
    with pytest.raises(Exception):
        value.decision = PromotionDecision.INELIGIBLE  # type: ignore[misc]
    assert replace(value) == value
