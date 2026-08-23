from dataclasses import fields

from shreks_brain.features import FeatureVector
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import (
    FIRST_PULLBACK_CONFIRMATIONS_REQUIRED,
    FIRST_PULLBACK_SETUP_NAME,
    FirstPullbackAssessment,
    FirstPullbackFinding,
    FirstPullbackPolicy,
    FirstPullbackReasonCode,
    PullbackContext,
    SetupState,
    assess_first_pullback,
    assess_fresh_launch,
    assess_graduation_breakout,
)


def test_public_api_can_assess_ready_first_pullback():
    configured = FirstPullbackPolicy(
        version="pullback-public-test",
        min_seconds_since_trough=15.0,
        max_seconds_since_trough=600.0,
        max_source_age_ms=30_000,
        min_structure_samples=5,
        min_initial_impulse_pct=20.0,
        min_pullback_depth_pct=8.0,
        max_pullback_depth_pct=35.0,
        min_recovery_from_trough_pct=5.0,
        min_current_vs_peak_pct=-10.0,
        max_current_vs_peak_pct=10.0,
        min_liquidity_retention_pct=70.0,
        min_liquidity_usd=50_000.0,
        max_exit_price_impact_pct=5.0,
        min_tx_count_m5=50,
        min_volume_velocity_ratio=1.2,
        min_buy_fraction_m5=0.60,
        min_buy_fraction_improvement=0.10,
        min_buy_pressure_acceleration=0.05,
        min_return_1m_pct=1.0,
        max_return_1m_pct=30.0,
    )
    structure = PullbackContext(
        impulse_started_at_unix_ms=1_000_000,
        peak_at_unix_ms=1_120_000,
        trough_at_unix_ms=1_240_000,
        impulse_start_price_usd=1.0,
        peak_price_usd=1.5,
        trough_price_usd=1.2,
        peak_liquidity_usd=100_000.0,
        trough_liquidity_usd=80_000.0,
        trough_buy_fraction_m5=0.40,
        sample_count=8,
    )
    features = FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=1_310_000,
        source_observed_at_unix_ms=1_300_000,
        source_age_ms=10_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=900.0,
        price_usd=1.44,
        liquidity_usd=100_000.0,
        liquidity_change_5m_pct=5.0,
        exit_price_impact_pct=2.0,
        volume_m5_usd=20_000.0,
        volume_h1_usd=100_000.0,
        volume_velocity_ratio=2.4,
        tx_count_m5=100,
        tx_count_h1=500,
        buy_fraction_m5=0.65,
        buy_fraction_h1=0.55,
        buy_sell_ratio_m5=1.857142857,
        buy_sell_ratio_h1=1.222222222,
        buy_pressure_acceleration=0.10,
        return_1m_pct=4.0,
        return_5m_pct=-5.0,
        return_15m_pct=30.0,
        momentum_acceleration_1m_vs_5m=5.0,
        distance_from_local_high_pct=-4.0,
        range_position_pct=80.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )

    result = assess_first_pullback(features, structure, configured)

    assert isinstance(result, FirstPullbackAssessment)
    assert result.setup_name == FIRST_PULLBACK_SETUP_NAME
    assert result.state is SetupState.READY
    assert result.confirmations_required == FIRST_PULLBACK_CONFIRMATIONS_REQUIRED
    assert result.confirmation_score == 100.0
    assert result.findings[-1].code is FirstPullbackReasonCode.ALL_CONFIRMATIONS_PASSED
    assert isinstance(result.findings[-1], FirstPullbackFinding)


def test_public_api_preserves_existing_setup_entry_points():
    assert callable(assess_fresh_launch)
    assert callable(assess_graduation_breakout)


def test_first_pullback_assessment_has_no_execution_authority():
    names = {field.name for field in fields(FirstPullbackAssessment)}
    for forbidden in (
        "trade_intent",
        "side",
        "notional",
        "position_size",
        "wallet",
        "order",
        "fill",
        "signer",
        "transaction",
        "realized_pnl",
        "mfe_pct",
        "mae_pct",
    ):
        assert forbidden not in names
