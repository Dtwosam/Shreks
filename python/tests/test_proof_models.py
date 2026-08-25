from __future__ import annotations

from dataclasses import replace
import inspect

import pytest

from shreks_brain.proof import (
    PAPER_PROOF_SCHEMA_VERSION,
    CandidateProofAssessment,
    PaperProofDecision,
    PaperProofGateCode,
    PaperProofGateResult,
    PaperProofGateStatus,
    PaperProofPolicy,
)
from shreks_brain.proof.fingerprint import sha256_canonical


SHA = "a" * 64
ZERO_SHA = "0" * 64


def _policy(**overrides: object) -> PaperProofPolicy:
    values: dict[str, object] = dict(
        version="paper-proof-v1",
        min_trade_count=20,
        min_distinct_mint_count=10,
        min_evaluation_span_ms=86_400_000,
        min_net_expectancy_pct=1.0,
        min_profit_factor=1.2,
        max_drawdown_pct=20.0,
        max_cost_burden_pct=5.0,
        max_single_winner_share_of_positive_pnl=0.4,
    )
    values.update(overrides)
    return PaperProofPolicy(**values)  # type: ignore[arg-type]


def _gates(
    *,
    status: PaperProofGateStatus = PaperProofGateStatus.PASS,
) -> tuple[PaperProofGateResult, ...]:
    return tuple(
        PaperProofGateResult(
            code=code,
            status=status,
            observed_value=1,
            threshold_value=1,
            message=f"{code.value} checked",
        )
        for code in sorted(PaperProofGateCode, key=lambda value: value.value)
    )


def _assessment(**overrides: object) -> CandidateProofAssessment:
    values: dict[str, object] = dict(
        schema_version=PAPER_PROOF_SCHEMA_VERSION,
        policy_version="paper-proof-v1",
        candidate_version="candidate-v1",
        candidate_fingerprint_sha256=SHA,
        registry_fingerprint_sha256=SHA,
        e8_assessment_fingerprint_sha256=SHA,
        paper_run_id="paper-run-1",
        paper_ledger_fingerprint_sha256=SHA,
        paper_evaluation_fingerprint_sha256=SHA,
        paper_trade_evidence_fingerprint_sha256=SHA,
        evaluated_at_unix_ms=10_000,
        gates=_gates(),
        decision=PaperProofDecision.SUFFICIENT,
        assessment_fingerprint_sha256=SHA,
    )
    values.update(overrides)
    return CandidateProofAssessment(**values)  # type: ignore[arg-type]


def test_schema_and_enum_values_are_exact() -> None:
    assert PAPER_PROOF_SCHEMA_VERSION == "e12-paper-proof-v1"
    assert tuple(value.value for value in PaperProofDecision) == (
        "SUFFICIENT",
        "INSUFFICIENT_EVIDENCE",
        "FAILED",
    )
    assert tuple(value.value for value in PaperProofGateStatus) == (
        "PASS",
        "FAIL",
        "INSUFFICIENT",
    )
    assert tuple(sorted(value.value for value in PaperProofGateCode)) == (
        "E8_ASSESSMENT_ELIGIBLE",
        "E8_REGISTRY_PROVENANCE",
        "MAX_PAPER_COST_BURDEN_PCT",
        "MAX_PAPER_DRAWDOWN_PCT",
        "MAX_PAPER_SINGLE_WINNER_SHARE",
        "MIN_PAPER_DISTINCT_MINT_COUNT",
        "MIN_PAPER_EVALUATION_SPAN",
        "MIN_PAPER_NET_EXPECTANCY_PCT",
        "MIN_PAPER_PROFIT_FACTOR",
        "MIN_PAPER_TRADE_COUNT",
        "PAPER_EVIDENCE_PROVENANCE",
    )


def test_policy_has_no_default_thresholds() -> None:
    signature = inspect.signature(PaperProofPolicy)
    for parameter in signature.parameters.values():
        assert parameter.default is inspect.Parameter.empty


def test_policy_accepts_explicit_valid_thresholds() -> None:
    policy = _policy()
    assert policy.version == "paper-proof-v1"
    assert policy.min_trade_count == 20
    assert policy.max_single_winner_share_of_positive_pnl == 0.4


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("version", "", "non-empty"),
        ("min_trade_count", -1, "non-negative"),
        ("min_distinct_mint_count", -1, "non-negative"),
        ("min_evaluation_span_ms", -1, "non-negative"),
        ("min_net_expectancy_pct", float("nan"), "finite"),
        ("min_profit_factor", -0.1, "non-negative"),
        ("max_drawdown_pct", 100.1, "within"),
        ("max_cost_burden_pct", -0.1, "within"),
        ("max_single_winner_share_of_positive_pnl", 1.1, "within"),
    ),
)
def test_policy_rejects_invalid_thresholds(field: str, value: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _policy(**{field: value})


def test_gate_result_requires_exact_enums_and_finite_values() -> None:
    with pytest.raises(ValueError, match="PaperProofGateCode"):
        PaperProofGateResult(
            code="MIN_PAPER_TRADE_COUNT",  # type: ignore[arg-type]
            status=PaperProofGateStatus.PASS,
            observed_value=1,
            threshold_value=1,
            message="checked",
        )
    with pytest.raises(ValueError, match="PaperProofGateStatus"):
        PaperProofGateResult(
            code=PaperProofGateCode.MIN_PAPER_TRADE_COUNT,
            status="PASS",  # type: ignore[arg-type]
            observed_value=1,
            threshold_value=1,
            message="checked",
        )
    with pytest.raises(ValueError, match="finite"):
        PaperProofGateResult(
            code=PaperProofGateCode.MIN_PAPER_TRADE_COUNT,
            status=PaperProofGateStatus.PASS,
            observed_value=float("inf"),
            threshold_value=1,
            message="checked",
        )
    with pytest.raises(ValueError, match="non-empty"):
        PaperProofGateResult(
            code=PaperProofGateCode.MIN_PAPER_TRADE_COUNT,
            status=PaperProofGateStatus.PASS,
            observed_value=1,
            threshold_value=1,
            message="",
        )


def test_assessment_requires_every_gate_once_in_lexical_order() -> None:
    gates = _gates()
    with pytest.raises(ValueError, match="every gate"):
        _assessment(gates=gates[:-1])
    with pytest.raises(ValueError, match="every gate"):
        _assessment(gates=tuple(reversed(gates)))
    with pytest.raises(ValueError, match="every gate"):
        _assessment(gates=gates[:-1] + (gates[0],))


def test_assessment_decision_precedence_is_enforced() -> None:
    insufficient = list(_gates())
    insufficient[0] = replace(
        insufficient[0], status=PaperProofGateStatus.INSUFFICIENT
    )
    with pytest.raises(ValueError, match="decision"):
        _assessment(gates=tuple(insufficient), decision=PaperProofDecision.SUFFICIENT)
    assert (
        _assessment(
            gates=tuple(insufficient),
            decision=PaperProofDecision.INSUFFICIENT_EVIDENCE,
        ).decision
        is PaperProofDecision.INSUFFICIENT_EVIDENCE
    )

    failed = list(_gates())
    failed[0] = replace(failed[0], status=PaperProofGateStatus.FAIL)
    failed[1] = replace(failed[1], status=PaperProofGateStatus.INSUFFICIENT)
    assert (
        _assessment(gates=tuple(failed), decision=PaperProofDecision.FAILED).decision
        is PaperProofDecision.FAILED
    )


@pytest.mark.parametrize(
    "field",
    (
        "candidate_fingerprint_sha256",
        "registry_fingerprint_sha256",
        "e8_assessment_fingerprint_sha256",
        "paper_ledger_fingerprint_sha256",
        "paper_evaluation_fingerprint_sha256",
        "paper_trade_evidence_fingerprint_sha256",
        "assessment_fingerprint_sha256",
    ),
)
def test_assessment_rejects_malformed_sha256(field: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        _assessment(**{field: "bad"})


def test_assessment_rejects_blank_identity_and_negative_time() -> None:
    for field in ("policy_version", "candidate_version", "paper_run_id"):
        with pytest.raises(ValueError, match="non-empty"):
            _assessment(**{field: ""})
    with pytest.raises(ValueError, match="non-negative"):
        _assessment(evaluated_at_unix_ms=-1)


def test_assessment_requires_exact_decision_enum() -> None:
    with pytest.raises(ValueError, match="PaperProofDecision"):
        _assessment(decision="SUFFICIENT")  # type: ignore[arg-type]


def test_sha256_canonical_is_deterministic_and_float_sensitive() -> None:
    assert sha256_canonical({"x": 0.1}) == sha256_canonical({"x": 0.1})
    assert sha256_canonical({"x": 0.1}) != sha256_canonical(
        {"x": 0.10000000000000002}
    )
    assert sha256_canonical({"x": -0.0}) != sha256_canonical({"x": 0.0})


def test_sha256_canonical_rejects_non_finite_float() -> None:
    with pytest.raises(ValueError, match="finite"):
        sha256_canonical({"x": float("nan")})


def test_assessment_accepts_zero_placeholder_fingerprint_for_drafting() -> None:
    assessment = _assessment(assessment_fingerprint_sha256=ZERO_SHA)
    assert assessment.assessment_fingerprint_sha256 == ZERO_SHA
