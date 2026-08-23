from dataclasses import fields

from shreks_brain.features import FeatureVector
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import (
    FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
    FRESH_LAUNCH_SETUP_NAME,
    FreshLaunchAssessment,
    FreshLaunchPolicy,
    FreshLaunchReasonCode,
    SetupFinding,
    SetupState,
    assess_fresh_launch,
)


def test_public_api_can_assess_ready_fresh_launch():
    configured = FreshLaunchPolicy(
        version="fresh-public-test",
        min_age_seconds=60.0,
        max_age_seconds=900.0,
        max_source_age_ms=30_000,
        min_liquidity_usd=50_000.0,
        max_exit_price_impact_pct=5.0,
        max_return_5m_pct=80.0,
        min_tx_count_m5=50,
        min_volume_velocity_ratio=1.2,
        min_buy_fraction_m5=0.60,
        min_buy_pressure_acceleration=0.05,
        min_return_1m_pct=1.0,
        min_return_5m_pct=5.0,
        min_liquidity_change_5m_pct=0.0,
        min_distance_from_local_high_pct=-15.0,
        min_range_position_pct=60.0,
    )
    vector = FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=2_000_000,
        source_observed_at_unix_ms=1_990_000,
        source_age_ms=10_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=300.0,
        price_usd=1.0,
        liquidity_usd=100_000.0,
        liquidity_change_5m_pct=10.0,
        exit_price_impact_pct=2.0,
        volume_m5_usd=20_000.0,
        volume_h1_usd=100_000.0,
        volume_velocity_ratio=2.4,
        tx_count_m5=100,
        tx_count_h1=500,
        buy_fraction_m5=0.75,
        buy_fraction_h1=0.60,
        buy_sell_ratio_m5=3.0,
        buy_sell_ratio_h1=1.5,
        buy_pressure_acceleration=0.15,
        return_1m_pct=4.0,
        return_5m_pct=20.0,
        return_15m_pct=30.0,
        momentum_acceleration_1m_vs_5m=0.0,
        distance_from_local_high_pct=-5.0,
        range_position_pct=85.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )

    result = assess_fresh_launch(vector, configured)

    assert isinstance(result, FreshLaunchAssessment)
    assert result.setup_name == FRESH_LAUNCH_SETUP_NAME
    assert result.state is SetupState.READY
    assert result.confirmations_required == FRESH_LAUNCH_CONFIRMATIONS_REQUIRED
    assert result.confirmation_score == 100.0
    assert result.findings[-1].code is FreshLaunchReasonCode.ALL_CONFIRMATIONS_PASSED
    assert isinstance(result.findings[-1], SetupFinding)


def test_ready_assessment_is_not_an_execution_request():
    names = {field.name for field in fields(FreshLaunchAssessment)}
    assert "trade_intent" not in names
    assert "side" not in names
    assert "notional" not in names
    assert "wallet" not in names
    assert "transaction" not in names
