import pytest

from shreks_brain.safety.evaluator import assess_safety
from shreks_brain.safety.models import (
    SafetyDecision,
    SafetyInputs,
    SafetyPolicy,
    SafetyReasonCode,
    SafetySeverity,
)


def policy(**overrides):
    values = {
        "version": "b1-v1",
        "min_liquidity_usd": 5_000.0,
        "soft_min_liquidity_usd": 10_000.0,
        "max_top_holder_concentration_pct": 40.0,
        "soft_max_top_holder_concentration_pct": 25.0,
        "soft_max_creator_concentration_pct": 15.0,
        "soft_max_exit_price_impact_pct": 8.0,
        "max_critical_data_age_ms": 30_000,
    }
    values.update(overrides)
    return SafetyPolicy(**values)


def inputs(**overrides):
    values = {
        "as_of_unix_ms": 100_000,
        "mint_authority_active": False,
        "freeze_authority_active": False,
        "liquidity_usd": 20_000.0,
        "top_holder_concentration_pct": 20.0,
        "creator_concentration_pct": 5.0,
        "exit_quote_available": True,
        "exit_price_impact_pct": 2.0,
        "execution_trap_detected": False,
        "critical_data_observed_at_unix_ms": 90_000,
        "critical_data_contradictory": False,
        "global_risk_halt": False,
    }
    values.update(overrides)
    return SafetyInputs(**values)


def codes(assessment):
    return [finding.code for finding in assessment.findings]


def test_clean_facts_pass_without_findings():
    assessment = assess_safety(inputs(), policy())
    assert assessment.decision is SafetyDecision.PASS
    assert assessment.policy_version == "b1-v1"
    assert assessment.as_of_unix_ms == 100_000
    assert assessment.findings == ()


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"global_risk_halt": True}, SafetyReasonCode.GLOBAL_RISK_HALT),
        ({"mint_authority_active": True}, SafetyReasonCode.MINT_AUTHORITY_ACTIVE),
        ({"freeze_authority_active": True}, SafetyReasonCode.FREEZE_AUTHORITY_ACTIVE),
        ({"liquidity_usd": 4_999.99}, SafetyReasonCode.LIQUIDITY_BELOW_MINIMUM),
        (
            {"top_holder_concentration_pct": 40.01},
            SafetyReasonCode.HOLDER_CONCENTRATION_ABOVE_MAXIMUM,
        ),
        ({"exit_quote_available": False}, SafetyReasonCode.EXIT_QUOTE_UNAVAILABLE),
        ({"execution_trap_detected": True}, SafetyReasonCode.EXECUTION_TRAP_DETECTED),
    ],
)
def test_each_hard_rule_independently_rejects(overrides, reason):
    assessment = assess_safety(inputs(**overrides), policy())
    assert assessment.decision is SafetyDecision.REJECT
    assert codes(assessment) == [reason]
    assert assessment.findings[0].severity is SafetySeverity.HARD


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"mint_authority_active": None}, SafetyReasonCode.MINT_AUTHORITY_UNKNOWN),
        ({"freeze_authority_active": None}, SafetyReasonCode.FREEZE_AUTHORITY_UNKNOWN),
        ({"liquidity_usd": None}, SafetyReasonCode.LIQUIDITY_UNKNOWN),
        (
            {"top_holder_concentration_pct": None},
            SafetyReasonCode.HOLDER_CONCENTRATION_UNKNOWN,
        ),
        ({"exit_quote_available": None}, SafetyReasonCode.EXIT_QUOTE_UNKNOWN),
    ],
)
def test_required_unknown_critical_facts_are_incomplete(overrides, reason):
    assessment = assess_safety(inputs(**overrides), policy())
    assert assessment.decision is SafetyDecision.INCOMPLETE
    assert codes(assessment) == [reason]
    assert assessment.findings[0].severity is SafetySeverity.DATA_QUALITY


def test_optional_unknown_fields_do_not_force_incomplete_but_freshness_remains_required():
    relaxed = policy(
        require_known_authorities=False,
        require_liquidity=False,
        require_holder_concentration=False,
        require_exit_quote=False,
    )
    assessment = assess_safety(
        inputs(
            mint_authority_active=None,
            freeze_authority_active=None,
            liquidity_usd=None,
            top_holder_concentration_pct=None,
            exit_quote_available=None,
        ),
        relaxed,
    )
    assert assessment.decision is SafetyDecision.PASS
    assert assessment.findings == ()

    stale = assess_safety(inputs(critical_data_observed_at_unix_ms=None), relaxed)
    assert stale.decision is SafetyDecision.INCOMPLETE
    assert codes(stale) == [SafetyReasonCode.CRITICAL_DATA_STALE]


def test_stale_missing_future_and_explicitly_contradictory_data_fail_closed():
    missing = assess_safety(inputs(critical_data_observed_at_unix_ms=None), policy())
    stale = assess_safety(inputs(critical_data_observed_at_unix_ms=69_999), policy())
    exact_boundary = assess_safety(inputs(critical_data_observed_at_unix_ms=70_000), policy())
    future = assess_safety(inputs(critical_data_observed_at_unix_ms=100_001), policy())
    explicit = assess_safety(inputs(critical_data_contradictory=True), policy())

    assert missing.decision is SafetyDecision.INCOMPLETE
    assert codes(missing) == [SafetyReasonCode.CRITICAL_DATA_STALE]
    assert stale.decision is SafetyDecision.INCOMPLETE
    assert codes(stale) == [SafetyReasonCode.CRITICAL_DATA_STALE]
    assert exact_boundary.decision is SafetyDecision.PASS
    assert future.decision is SafetyDecision.INCOMPLETE
    assert codes(future) == [SafetyReasonCode.CRITICAL_DATA_CONTRADICTORY]
    assert explicit.decision is SafetyDecision.INCOMPLETE
    assert codes(explicit) == [SafetyReasonCode.CRITICAL_DATA_CONTRADICTORY]


def test_hard_rejection_has_precedence_over_incomplete_data():
    assessment = assess_safety(
        inputs(
            global_risk_halt=True,
            mint_authority_active=None,
            critical_data_observed_at_unix_ms=None,
        ),
        policy(),
    )
    assert assessment.decision is SafetyDecision.REJECT
    assert codes(assessment) == [
        SafetyReasonCode.GLOBAL_RISK_HALT,
        SafetyReasonCode.MINT_AUTHORITY_UNKNOWN,
        SafetyReasonCode.CRITICAL_DATA_STALE,
    ]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"liquidity_usd": 7_500.0}, SafetyReasonCode.LIQUIDITY_WEAK),
        (
            {"top_holder_concentration_pct": 30.0},
            SafetyReasonCode.HOLDER_CONCENTRATION_ELEVATED,
        ),
        (
            {"creator_concentration_pct": 20.0},
            SafetyReasonCode.CREATOR_CONCENTRATION_ELEVATED,
        ),
        ({"exit_price_impact_pct": 10.0}, SafetyReasonCode.EXIT_PRICE_IMPACT_ELEVATED),
    ],
)
def test_soft_risks_remain_pass(overrides, reason):
    assessment = assess_safety(inputs(**overrides), policy())
    assert assessment.decision is SafetyDecision.PASS
    assert codes(assessment) == [reason]
    assert assessment.findings[0].severity is SafetySeverity.SOFT


def test_threshold_boundaries_are_exact():
    hard_liquidity_boundary = assess_safety(inputs(liquidity_usd=5_000.0), policy())
    soft_liquidity_boundary = assess_safety(inputs(liquidity_usd=10_000.0), policy())
    hard_holder_boundary = assess_safety(inputs(top_holder_concentration_pct=40.0), policy())
    soft_holder_boundary = assess_safety(inputs(top_holder_concentration_pct=25.0), policy())
    creator_boundary = assess_safety(inputs(creator_concentration_pct=15.0), policy())
    impact_boundary = assess_safety(inputs(exit_price_impact_pct=8.0), policy())

    assert hard_liquidity_boundary.decision is SafetyDecision.PASS
    assert codes(hard_liquidity_boundary) == [SafetyReasonCode.LIQUIDITY_WEAK]
    assert soft_liquidity_boundary.findings == ()
    assert hard_holder_boundary.decision is SafetyDecision.PASS
    assert codes(hard_holder_boundary) == [SafetyReasonCode.HOLDER_CONCENTRATION_ELEVATED]
    assert soft_holder_boundary.findings == ()
    assert creator_boundary.findings == ()
    assert impact_boundary.findings == ()


def test_finding_order_is_fixed_across_hard_data_quality_and_soft_passes():
    assessment = assess_safety(
        inputs(
            global_risk_halt=True,
            mint_authority_active=True,
            freeze_authority_active=True,
            liquidity_usd=4_000.0,
            top_holder_concentration_pct=50.0,
            exit_quote_available=False,
            execution_trap_detected=True,
            critical_data_observed_at_unix_ms=None,
            creator_concentration_pct=20.0,
            exit_price_impact_pct=10.0,
        ),
        policy(),
    )
    assert assessment.decision is SafetyDecision.REJECT
    assert codes(assessment) == [
        SafetyReasonCode.GLOBAL_RISK_HALT,
        SafetyReasonCode.MINT_AUTHORITY_ACTIVE,
        SafetyReasonCode.FREEZE_AUTHORITY_ACTIVE,
        SafetyReasonCode.LIQUIDITY_BELOW_MINIMUM,
        SafetyReasonCode.HOLDER_CONCENTRATION_ABOVE_MAXIMUM,
        SafetyReasonCode.EXIT_QUOTE_UNAVAILABLE,
        SafetyReasonCode.EXECUTION_TRAP_DETECTED,
        SafetyReasonCode.CRITICAL_DATA_STALE,
        SafetyReasonCode.CREATOR_CONCENTRATION_ELEVATED,
        SafetyReasonCode.EXIT_PRICE_IMPACT_ELEVATED,
    ]


def test_repeated_evaluation_is_equal_and_order_stable():
    case = inputs(liquidity_usd=7_500.0, creator_concentration_pct=20.0)
    first = assess_safety(case, policy())
    second = assess_safety(case, policy())
    assert first == second
    assert codes(first) == codes(second)
