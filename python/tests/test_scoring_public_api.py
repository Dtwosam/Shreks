from dataclasses import fields

from shreks_brain.features import FeatureVector
from shreks_brain.regime import MarketRegime, RegimeAssessment, assess_regime
from shreks_brain.safety import SafetyDecision, assess_safety
from shreks_brain.setups import (
    FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
    FRESH_LAUNCH_SETUP_NAME,
    FreshLaunchAssessment,
    SetupState,
    assess_first_pullback,
    assess_fresh_launch,
    assess_graduation_breakout,
)
from shreks_brain.scoring import (
    ScoreAssessment,
    ScoreFinding,
    ScorePolicy,
    ScoreReasonCode,
    score_candidate,
)


def _policy() -> ScorePolicy:
    return ScorePolicy(
        version="score-v1-test",
        required_feature_schema_version="b2-v1",
        safety_weight=0.20,
        money_flow_weight=0.30,
        setup_quality_weight=0.30,
        liquidity_executability_weight=0.20,
        safety_liquidity_weak_penalty=20.0,
        safety_holder_concentration_elevated_penalty=25.0,
        safety_creator_concentration_elevated_penalty=15.0,
        safety_exit_price_impact_elevated_penalty=30.0,
        volume_velocity_zero=0.5,
        volume_velocity_full=2.0,
        buy_fraction_m5_zero=0.40,
        buy_fraction_m5_full=0.70,
        buy_pressure_acceleration_zero=-0.10,
        buy_pressure_acceleration_full=0.20,
        liquidity_usd_zero=10_000.0,
        liquidity_usd_full=100_000.0,
        exit_price_impact_full=1.0,
        exit_price_impact_zero=8.0,
    )


def _features() -> FeatureVector:
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=1_000_000,
        source_observed_at_unix_ms=995_000,
        source_age_ms=5_000,
        safety_policy_version="safety-test",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=180.0,
        price_usd=0.01,
        liquidity_usd=55_000.0,
        liquidity_change_5m_pct=10.0,
        exit_price_impact_pct=4.5,
        volume_m5_usd=20_000.0,
        volume_h1_usd=80_000.0,
        volume_velocity_ratio=1.25,
        tx_count_m5=50,
        tx_count_h1=200,
        buy_fraction_m5=0.55,
        buy_fraction_h1=0.52,
        buy_sell_ratio_m5=1.22,
        buy_sell_ratio_h1=1.08,
        buy_pressure_acceleration=0.05,
        return_1m_pct=4.0,
        return_5m_pct=12.0,
        return_15m_pct=20.0,
        momentum_acceleration_1m_vs_5m=1.6,
        distance_from_local_high_pct=-3.0,
        range_position_pct=80.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )


def _setup() -> FreshLaunchAssessment:
    return FreshLaunchAssessment(
        setup_name=FRESH_LAUNCH_SETUP_NAME,
        policy_version="fresh-test",
        feature_schema_version="b2-v1",
        as_of_unix_ms=1_000_000,
        state=SetupState.READY,
        confirmation_score=80.0,
        confirmations_passed=8,
        confirmations_required=FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
        findings=(),
    )


def _regime() -> RegimeAssessment:
    return RegimeAssessment(
        policy_version="regime-test",
        as_of_unix_ms=1_000_000,
        source_observed_at_unix_ms=990_000,
        window_started_at_unix_ms=630_000,
        source_age_ms=10_000,
        window_seconds=360.0,
        candidate_count=12,
        candidate_rate_per_hour=120.0,
        executable_fraction=0.75,
        median_liquidity_usd=80_000.0,
        median_volume_m5_usd=25_000.0,
        base_regime=MarketRegime.NORMAL,
        regime=MarketRegime.NORMAL,
        performance_sample_count=None,
        performance_net_expectancy_after_costs_pct=None,
        performance_applied=False,
        findings=(),
    )


def test_scoring_public_api_returns_score_assessment() -> None:
    assert callable(score_candidate)
    result = score_candidate(_features(), _setup(), _regime(), _policy())
    assert isinstance(result, ScoreAssessment)
    assert result.total_score == 69.0
    assert ScoreFinding is not None
    assert ScoreReasonCode.TOTAL_SCORE_AVAILABLE in tuple(
        finding.code for finding in result.findings
    )


def test_existing_brain_public_entry_points_remain_importable() -> None:
    assert callable(assess_safety)
    assert callable(assess_regime)
    assert callable(assess_fresh_launch)
    assert callable(assess_graduation_breakout)
    assert callable(assess_first_pullback)


def test_score_assessment_public_surface_has_no_wallet_decision_risk_or_execution_authority() -> None:
    field_names = {field.name for field in fields(ScoreAssessment)}
    forbidden = {
        "wallet_quality",
        "wallet_quality_score",
        "confidence",
        "win_probability",
        "expected_return",
        "entry_threshold",
        "trade_decision",
        "trade_intent",
        "side",
        "notional",
        "position_size",
        "risk",
        "wallet",
        "order",
        "fill",
        "signer",
        "transaction",
        "realized_pnl",
        "mfe_pct",
        "mae_pct",
    }
    assert field_names.isdisjoint(forbidden)
