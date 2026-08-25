from dataclasses import replace

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.shadow import (
    SHADOW_CHALLENGER_SCHEMA_VERSION,
    ShadowDecisionPolicy,
    ShadowDecisionRecord,
    ShadowEvidenceLedger,
    ShadowReasonCode,
)


def record(
    *,
    candidate_version: str = "candidate-v1",
    mint: str = "mint-a",
    as_of_unix_ms: int = 200,
    policy_version: str = "shadow-policy-v1",
    fingerprint_char: str = "a",
) -> ShadowDecisionRecord:
    return ShadowDecisionRecord(
        schema_version=SHADOW_CHALLENGER_SCHEMA_VERSION,
        candidate_version=candidate_version,
        strategy_version="strategy-v1",
        candidate_fingerprint_sha256="1" * 64,
        registry_fingerprint_sha256="2" * 64,
        model_version="model-v1",
        model_training_fingerprint_sha256="3" * 64,
        target_horizon_seconds=300,
        target_minimum_return_pct=5.0,
        shadow_policy_version=policy_version,
        enter_min_probability=0.7,
        candidate_mint=mint,
        as_of_unix_ms=as_of_unix_ms,
        dataset_schema_version="d6-research-v1",
        decision_feature_fingerprint_sha256="4" * 64,
        setup_name="fresh_launch_continuation",
        safety_decision="PASS",
        setup_state="READY",
        market_regime="NORMAL",
        baseline_action=DecisionAction.WATCH,
        positive_probability=0.8,
        challenger_action=DecisionAction.ENTER,
        reason=ShadowReasonCode.PROBABILITY_ENTER_APPROVED,
        record_fingerprint_sha256=fingerprint_char * 64,
    )


def test_schema_and_reason_code_vocabulary_are_exact() -> None:
    assert SHADOW_CHALLENGER_SCHEMA_VERSION == "e7-shadow-v1"
    assert {value.value for value in ShadowReasonCode} == {
        "SAFETY_NOT_PASS",
        "SETUP_BLOCKED",
        "REGIME_DEAD",
        "SETUP_WATCH",
        "PROBABILITY_BELOW_ENTER_THRESHOLD",
        "PROBABILITY_ENTER_APPROVED",
    }


def test_shadow_policy_requires_explicit_finite_probability_fraction() -> None:
    assert ShadowDecisionPolicy("shadow-policy-v1", 0.0).enter_min_probability == 0.0
    assert ShadowDecisionPolicy("shadow-policy-v1", 1.0).enter_min_probability == 1.0

    for bad in (-0.01, 1.01, float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="enter_min_probability"):
            ShadowDecisionPolicy("shadow-policy-v1", bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="version"):
        ShadowDecisionPolicy("", 0.5)


def test_shadow_record_rejects_invalid_identity_numeric_and_action_fields() -> None:
    base = record()

    with pytest.raises(ValueError, match="schema_version"):
        replace(base, schema_version="wrong")
    with pytest.raises(ValueError, match="candidate_version"):
        replace(base, candidate_version="")
    with pytest.raises(ValueError, match="candidate_fingerprint"):
        replace(base, candidate_fingerprint_sha256="bad")
    with pytest.raises(ValueError, match="target_horizon_seconds"):
        replace(base, target_horizon_seconds=0)
    with pytest.raises(ValueError, match="target_minimum_return_pct"):
        replace(base, target_minimum_return_pct=float("nan"))
    with pytest.raises(ValueError, match="enter_min_probability"):
        replace(base, enter_min_probability=1.1)
    with pytest.raises(ValueError, match="as_of_unix_ms"):
        replace(base, as_of_unix_ms=-1)
    with pytest.raises(ValueError, match="positive_probability"):
        replace(base, positive_probability=float("inf"))
    with pytest.raises(ValueError, match="baseline_action"):
        replace(base, baseline_action=DecisionAction.HOLD)
    with pytest.raises(ValueError, match="challenger_action"):
        replace(base, challenger_action=DecisionAction.EXIT)
    with pytest.raises(ValueError, match="reason"):
        replace(base, reason="PROBABILITY_ENTER_APPROVED")  # type: ignore[arg-type]


def test_shadow_record_requires_nonempty_decision_context_strings() -> None:
    base = record()
    for field in (
        "strategy_version",
        "model_version",
        "shadow_policy_version",
        "candidate_mint",
        "dataset_schema_version",
        "setup_name",
        "safety_decision",
        "setup_state",
        "market_regime",
    ):
        with pytest.raises(ValueError, match=field):
            replace(base, **{field: ""})


def test_shadow_ledger_requires_canonical_order_and_unique_decision_identity() -> None:
    first = record(candidate_version="candidate-v1", mint="mint-a", as_of_unix_ms=100, fingerprint_char="a")
    second = record(candidate_version="candidate-v2", mint="mint-b", as_of_unix_ms=200, fingerprint_char="b")

    ledger = ShadowEvidenceLedger(
        schema_version=SHADOW_CHALLENGER_SCHEMA_VERSION,
        records=(first, second),
        ledger_fingerprint_sha256="c" * 64,
    )
    assert ledger.records == (first, second)

    with pytest.raises(ValueError, match="canonical order"):
        replace(ledger, records=(second, first))

    conflicting_identity = replace(
        first,
        strategy_version="different-strategy",
        record_fingerprint_sha256="d" * 64,
    )
    with pytest.raises(ValueError, match="decision identity"):
        replace(ledger, records=(first, conflicting_identity))


def test_shadow_ledger_rejects_wrong_schema_and_invalid_fingerprint() -> None:
    ledger = ShadowEvidenceLedger(
        schema_version=SHADOW_CHALLENGER_SCHEMA_VERSION,
        records=(),
        ledger_fingerprint_sha256="e" * 64,
    )
    with pytest.raises(ValueError, match="schema_version"):
        replace(ledger, schema_version="wrong")
    with pytest.raises(ValueError, match="ledger_fingerprint"):
        replace(ledger, ledger_fingerprint_sha256="bad")
