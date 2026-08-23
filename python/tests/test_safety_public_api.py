from dataclasses import fields

from shreks_brain.safety import (
    SafetyAssessment,
    SafetyDecision,
    SafetyFinding,
    SafetyInputs,
    SafetyPolicy,
    SafetyReasonCode,
    SafetySeverity,
    assess_safety,
)


def test_public_safety_api_is_complete_and_runs_clean_assessment():
    policy = SafetyPolicy(
        version="b1-public-v1",
        min_liquidity_usd=5_000.0,
        soft_min_liquidity_usd=10_000.0,
        max_top_holder_concentration_pct=40.0,
        soft_max_top_holder_concentration_pct=25.0,
        soft_max_creator_concentration_pct=15.0,
        soft_max_exit_price_impact_pct=8.0,
        max_critical_data_age_ms=30_000,
    )
    inputs = SafetyInputs(
        as_of_unix_ms=100_000,
        mint_authority_active=False,
        freeze_authority_active=False,
        liquidity_usd=20_000.0,
        top_holder_concentration_pct=20.0,
        creator_concentration_pct=5.0,
        exit_quote_available=True,
        exit_price_impact_pct=2.0,
        execution_trap_detected=False,
        critical_data_observed_at_unix_ms=90_000,
        critical_data_contradictory=False,
        global_risk_halt=False,
    )

    assessment = assess_safety(inputs, policy)

    assert isinstance(assessment, SafetyAssessment)
    assert assessment.decision is SafetyDecision.PASS
    assert assessment.findings == ()
    assert issubclass(SafetyReasonCode, str)
    assert issubclass(SafetySeverity, str)
    assert SafetyFinding.__dataclass_fields__["code"]


def test_public_inputs_expose_no_future_outcome_fields():
    names = {field.name for field in fields(SafetyInputs)}
    forbidden = {
        "return_pct",
        "mfe_pct",
        "mae_pct",
        "future_price_usd",
        "future_liquidity_usd",
        "realized_pnl",
    }
    assert names.isdisjoint(forbidden)
