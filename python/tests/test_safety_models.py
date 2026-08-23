from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.safety.models import (
    SafetyAssessment,
    SafetyDecision,
    SafetyFinding,
    SafetyInputs,
    SafetyPolicy,
    SafetyReasonCode,
    SafetySeverity,
)


def valid_policy(**overrides):
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


def valid_inputs(**overrides):
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


def test_enum_values_are_stable():
    assert [item.value for item in SafetyDecision] == ["PASS", "REJECT", "INCOMPLETE"]
    assert [item.value for item in SafetySeverity] == ["HARD", "SOFT", "DATA_QUALITY"]
    assert SafetyReasonCode.GLOBAL_RISK_HALT.value == "GLOBAL_RISK_HALT"
    assert SafetyReasonCode.CRITICAL_DATA_STALE.value == "CRITICAL_DATA_STALE"
    assert SafetyReasonCode.EXIT_PRICE_IMPACT_ELEVATED.value == "EXIT_PRICE_IMPACT_ELEVATED"


def test_models_are_frozen_and_assessment_filters_preserve_order():
    finding = SafetyFinding(
        SafetyReasonCode.GLOBAL_RISK_HALT,
        SafetySeverity.HARD,
        "global halt",
        True,
        None,
    )
    assessment = SafetyAssessment(
        decision=SafetyDecision.REJECT,
        policy_version="b1-v1",
        as_of_unix_ms=100,
        findings=(finding,),
    )

    assert assessment.hard_findings == (finding,)
    assert assessment.data_quality_findings == ()
    assert assessment.soft_findings == ()

    with pytest.raises(FrozenInstanceError):
        assessment.decision = SafetyDecision.PASS


def test_valid_policy_and_inputs_construct():
    assert valid_policy().version == "b1-v1"
    assert valid_inputs().liquidity_usd == 20_000.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"version": ""}, "version"),
        ({"version": "   "}, "version"),
        ({"min_liquidity_usd": -1.0}, "min_liquidity_usd"),
        ({"min_liquidity_usd": math.inf}, "min_liquidity_usd"),
        ({"soft_min_liquidity_usd": 4_999.0}, "soft_min_liquidity_usd"),
        ({"max_top_holder_concentration_pct": 101.0}, "max_top_holder_concentration_pct"),
        ({"soft_max_top_holder_concentration_pct": -0.1}, "soft_max_top_holder_concentration_pct"),
        ({"soft_max_top_holder_concentration_pct": 41.0}, "soft_max_top_holder_concentration_pct"),
        ({"soft_max_creator_concentration_pct": math.nan}, "soft_max_creator_concentration_pct"),
        ({"soft_max_exit_price_impact_pct": 100.1}, "soft_max_exit_price_impact_pct"),
        ({"max_critical_data_age_ms": -1}, "max_critical_data_age_ms"),
    ],
)
def test_invalid_policy_is_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        valid_policy(**overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"as_of_unix_ms": -1}, "as_of_unix_ms"),
        ({"critical_data_observed_at_unix_ms": -1}, "critical_data_observed_at_unix_ms"),
        ({"liquidity_usd": -0.01}, "liquidity_usd"),
        ({"liquidity_usd": math.nan}, "liquidity_usd"),
        ({"top_holder_concentration_pct": 100.1}, "top_holder_concentration_pct"),
        ({"creator_concentration_pct": -0.1}, "creator_concentration_pct"),
        ({"exit_price_impact_pct": math.inf}, "exit_price_impact_pct"),
    ],
)
def test_invalid_inputs_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        valid_inputs(**overrides)


def test_safety_inputs_exclude_future_outcome_fields():
    names = {field.name for field in fields(SafetyInputs)}
    assert "return_pct" not in names
    assert "mfe_pct" not in names
    assert "mae_pct" not in names
    assert "future_liquidity_usd" not in names
