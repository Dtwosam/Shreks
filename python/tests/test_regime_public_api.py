from dataclasses import fields

from shreks_brain.regime import (
    MarketRegime,
    RecentStrategyPerformance,
    RegimeAssessment,
    RegimeFinding,
    RegimeMarketWindow,
    RegimePolicy,
    RegimeReasonCode,
    assess_regime,
)
from shreks_brain.setups import (
    assess_first_pullback,
    assess_fresh_launch,
    assess_graduation_breakout,
)


def configured_policy() -> RegimePolicy:
    return RegimePolicy(
        version="regime-public-test",
        max_source_age_ms=30_000,
        min_window_seconds=300.0,
        min_candidate_samples=5,
        dead_max_candidate_rate_per_hour=2.0,
        weak_min_candidate_rate_per_hour=8.0,
        hot_min_candidate_rate_per_hour=20.0,
        dead_max_executable_fraction=0.10,
        weak_min_executable_fraction=0.50,
        hot_min_executable_fraction=0.80,
        weak_min_median_liquidity_usd=25_000.0,
        hot_min_median_liquidity_usd=75_000.0,
        weak_min_median_volume_m5_usd=5_000.0,
        hot_min_median_volume_m5_usd=20_000.0,
        min_performance_sample_count=20,
        dead_performance_expectancy_pct=-5.0,
        weak_performance_expectancy_pct=0.0,
    )


def hot_market() -> RegimeMarketWindow:
    return RegimeMarketWindow(
        as_of_unix_ms=1_310_000,
        source_observed_at_unix_ms=1_300_000,
        window_started_at_unix_ms=400_000,
        candidate_count=5,
        executable_candidate_count=4,
        median_liquidity_usd=75_000.0,
        median_volume_m5_usd=20_000.0,
    )


def test_public_api_can_assess_hot_market_without_performance_overlay():
    result = assess_regime(hot_market(), configured_policy())

    assert isinstance(result, RegimeAssessment)
    assert result.base_regime is MarketRegime.HOT
    assert result.regime is MarketRegime.HOT
    assert result.performance_applied is False
    assert result.findings[0].code is RegimeReasonCode.ALL_HOT_MARKET_THRESHOLDS_PASSED
    assert isinstance(result.findings[0], RegimeFinding)


def test_public_api_accepts_explicit_recent_performance_context():
    performance = RecentStrategyPerformance(
        observed_through_unix_ms=1_290_000,
        closed_trade_count=30,
        net_expectancy_after_costs_pct=-0.25,
    )
    result = assess_regime(hot_market(), configured_policy(), performance)

    assert result.base_regime is MarketRegime.HOT
    assert result.regime is MarketRegime.WEAK
    assert result.performance_applied is True


def test_existing_setup_entry_points_remain_importable():
    assert callable(assess_fresh_launch)
    assert callable(assess_graduation_breakout)
    assert callable(assess_first_pullback)


def test_regime_assessment_public_surface_has_no_execution_authority():
    names = {field.name for field in fields(RegimeAssessment)}
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
