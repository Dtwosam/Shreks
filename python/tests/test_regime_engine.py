from dataclasses import replace

import pytest

from shreks_brain.regime.engine import assess_regime
from shreks_brain.regime.models import (
    MarketRegime,
    RecentStrategyPerformance,
    RegimeMarketWindow,
    RegimePolicy,
    RegimeReasonCode,
)


def policy(**overrides):
    values = dict(
        version="regime-v1-test",
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
    values.update(overrides)
    return RegimePolicy(**values)


def normal_market(**overrides):
    values = dict(
        as_of_unix_ms=1_310_000,
        source_observed_at_unix_ms=1_300_000,
        window_started_at_unix_ms=940_000,
        candidate_count=12,
        executable_candidate_count=9,
        median_liquidity_usd=80_000.0,
        median_volume_m5_usd=25_000.0,
    )
    values.update(overrides)
    return RegimeMarketWindow(**values)


def hot_market(**overrides):
    values = dict(
        as_of_unix_ms=1_310_000,
        source_observed_at_unix_ms=1_300_000,
        window_started_at_unix_ms=940_000,
        candidate_count=12,
        executable_candidate_count=10,
        median_liquidity_usd=80_000.0,
        median_volume_m5_usd=25_000.0,
    )
    values.update(overrides)
    return RegimeMarketWindow(**values)


def perf(**overrides):
    values = dict(
        observed_through_unix_ms=1_290_000,
        closed_trade_count=30,
        net_expectancy_after_costs_pct=1.0,
    )
    values.update(overrides)
    return RecentStrategyPerformance(**values)


def codes(result):
    return tuple(finding.code for finding in result.findings)


def test_derived_metrics_are_exact_and_normal_market_is_mixed_healthy():
    result = assess_regime(normal_market(), policy())

    assert result.source_age_ms == 10_000
    assert result.window_seconds == 360.0
    assert result.candidate_rate_per_hour == 120.0
    assert result.executable_fraction == 0.75
    assert result.base_regime is MarketRegime.NORMAL
    assert result.regime is MarketRegime.NORMAL
    assert codes(result) == (
        RegimeReasonCode.NORMAL_MIXED_MARKET,
        RegimeReasonCode.PERFORMANCE_UNAVAILABLE,
    )


def test_source_after_as_of_fails_closed_without_negative_source_age():
    result = assess_regime(
        normal_market(source_observed_at_unix_ms=1_320_000),
        policy(),
    )

    assert result.source_age_ms is None
    assert result.base_regime is MarketRegime.DEAD
    assert result.regime is MarketRegime.DEAD
    assert codes(result)[0] is RegimeReasonCode.SOURCE_AFTER_AS_OF


def test_stale_source_fails_closed():
    result = assess_regime(
        normal_market(as_of_unix_ms=1_330_001),
        policy(),
    )
    assert result.base_regime is MarketRegime.DEAD
    assert codes(result)[0] is RegimeReasonCode.SOURCE_DATA_TOO_OLD


def test_too_short_window_fails_closed():
    result = assess_regime(
        normal_market(window_started_at_unix_ms=1_050_001),
        policy(),
    )
    assert result.window_seconds == pytest.approx(249.999)
    assert result.base_regime is MarketRegime.DEAD
    assert RegimeReasonCode.WINDOW_TOO_SHORT in codes(result)


def test_zero_candidates_fail_closed_without_zero_filling_executable_fraction():
    result = assess_regime(
        normal_market(
            candidate_count=0,
            executable_candidate_count=0,
            median_liquidity_usd=None,
            median_volume_m5_usd=None,
        ),
        policy(),
    )
    assert result.candidate_rate_per_hour == 0.0
    assert result.executable_fraction is None
    assert result.base_regime is MarketRegime.DEAD
    assert RegimeReasonCode.NO_CANDIDATES in codes(result)


def test_too_small_candidate_sample_fails_closed():
    result = assess_regime(
        normal_market(candidate_count=4, executable_candidate_count=4),
        policy(),
    )
    assert result.base_regime is MarketRegime.DEAD
    assert RegimeReasonCode.CANDIDATE_SAMPLE_TOO_SMALL in codes(result)


@pytest.mark.parametrize(
    "field,reason",
    [
        ("median_liquidity_usd", RegimeReasonCode.MEDIAN_LIQUIDITY_UNKNOWN),
        ("median_volume_m5_usd", RegimeReasonCode.MEDIAN_VOLUME_M5_UNKNOWN),
    ],
)
def test_missing_critical_market_median_fails_closed(field, reason):
    result = assess_regime(normal_market(**{field: None}), policy())
    assert result.base_regime is MarketRegime.DEAD
    assert reason in codes(result)


def test_candidate_rate_at_dead_maximum_is_dead():
    market = RegimeMarketWindow(
        as_of_unix_ms=10_010_000,
        source_observed_at_unix_ms=10_000_000,
        window_started_at_unix_ms=1_000_000,
        candidate_count=5,
        executable_candidate_count=4,
        median_liquidity_usd=80_000.0,
        median_volume_m5_usd=25_000.0,
    )
    result = assess_regime(market, policy())
    assert result.candidate_rate_per_hour == 2.0
    assert result.base_regime is MarketRegime.DEAD
    assert RegimeReasonCode.OPPORTUNITY_RATE_DEAD in codes(result)


def test_executable_fraction_at_dead_maximum_is_dead():
    result = assess_regime(
        hot_market(candidate_count=10, executable_candidate_count=1),
        policy(),
    )
    assert result.executable_fraction == 0.10
    assert result.base_regime is MarketRegime.DEAD
    assert RegimeReasonCode.EXECUTABLE_FRACTION_DEAD in codes(result)


@pytest.mark.parametrize(
    "market,reason",
    [
        (
            RegimeMarketWindow(
                as_of_unix_ms=5_010_000,
                source_observed_at_unix_ms=5_000_000,
                window_started_at_unix_ms=1_400_000,
                candidate_count=5,
                executable_candidate_count=5,
                median_liquidity_usd=80_000.0,
                median_volume_m5_usd=25_000.0,
            ),
            RegimeReasonCode.OPPORTUNITY_RATE_WEAK,
        ),
        (
            hot_market(candidate_count=10, executable_candidate_count=4),
            RegimeReasonCode.EXECUTABLE_FRACTION_WEAK,
        ),
        (
            hot_market(median_liquidity_usd=24_999.0),
            RegimeReasonCode.LIQUIDITY_WEAK,
        ),
        (
            hot_market(median_volume_m5_usd=4_999.0),
            RegimeReasonCode.VOLUME_WEAK,
        ),
    ],
)
def test_any_single_weak_market_dimension_makes_base_weak(market, reason):
    result = assess_regime(market, policy())
    assert result.base_regime is MarketRegime.WEAK
    assert result.regime is MarketRegime.WEAK
    assert reason in codes(result)


def test_candidate_rate_at_weak_minimum_passes_weak_gate():
    market = RegimeMarketWindow(
        as_of_unix_ms=5_010_000,
        source_observed_at_unix_ms=5_000_000,
        window_started_at_unix_ms=2_750_000,
        candidate_count=5,
        executable_candidate_count=5,
        median_liquidity_usd=80_000.0,
        median_volume_m5_usd=25_000.0,
    )
    result = assess_regime(market, policy())
    assert result.candidate_rate_per_hour == 8.0
    assert result.base_regime is MarketRegime.NORMAL
    assert RegimeReasonCode.OPPORTUNITY_RATE_WEAK not in codes(result)


def test_executable_fraction_at_weak_minimum_passes_weak_gate():
    result = assess_regime(
        hot_market(candidate_count=10, executable_candidate_count=5),
        policy(),
    )
    assert result.executable_fraction == 0.5
    assert result.base_regime is MarketRegime.NORMAL
    assert RegimeReasonCode.EXECUTABLE_FRACTION_WEAK not in codes(result)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("median_liquidity_usd", 25_000.0, RegimeReasonCode.LIQUIDITY_WEAK),
        ("median_volume_m5_usd", 5_000.0, RegimeReasonCode.VOLUME_WEAK),
    ],
)
def test_liquidity_and_volume_at_weak_minimum_pass_weak_gate(field, value, reason):
    result = assess_regime(hot_market(**{field: value}), policy())
    assert result.base_regime is MarketRegime.NORMAL
    assert reason not in codes(result)


def test_all_hot_thresholds_at_equality_are_hot():
    market = RegimeMarketWindow(
        as_of_unix_ms=1_310_000,
        source_observed_at_unix_ms=1_300_000,
        window_started_at_unix_ms=400_000,
        candidate_count=5,
        executable_candidate_count=4,
        median_liquidity_usd=75_000.0,
        median_volume_m5_usd=20_000.0,
    )
    result = assess_regime(market, policy())
    assert result.candidate_rate_per_hour == 20.0
    assert result.executable_fraction == 0.8
    assert result.base_regime is MarketRegime.HOT
    assert result.regime is MarketRegime.HOT
    assert codes(result) == (
        RegimeReasonCode.ALL_HOT_MARKET_THRESHOLDS_PASSED,
        RegimeReasonCode.PERFORMANCE_UNAVAILABLE,
    )


def test_missing_performance_never_changes_base_regime():
    result = assess_regime(hot_market(), policy(), performance=None)
    assert result.base_regime is MarketRegime.HOT
    assert result.regime is MarketRegime.HOT
    assert result.performance_applied is False
    assert codes(result)[-1] is RegimeReasonCode.PERFORMANCE_UNAVAILABLE


def test_performance_after_as_of_fails_closed_without_using_expectancy():
    result = assess_regime(
        hot_market(),
        policy(),
        perf(observed_through_unix_ms=1_320_000, net_expectancy_after_costs_pct=99.0),
    )
    assert result.base_regime is MarketRegime.HOT
    assert result.regime is MarketRegime.DEAD
    assert result.performance_applied is False
    assert codes(result)[-1] is RegimeReasonCode.PERFORMANCE_AFTER_AS_OF


def test_performance_after_market_source_fails_closed():
    result = assess_regime(
        hot_market(),
        policy(),
        perf(observed_through_unix_ms=1_305_000),
    )
    assert result.base_regime is MarketRegime.HOT
    assert result.regime is MarketRegime.DEAD
    assert result.performance_applied is False
    assert codes(result)[-1] is RegimeReasonCode.PERFORMANCE_AFTER_MARKET_SOURCE


def test_insufficient_performance_sample_does_not_change_base_regime():
    result = assess_regime(
        hot_market(),
        policy(),
        perf(closed_trade_count=19, net_expectancy_after_costs_pct=-50.0),
    )
    assert result.regime is MarketRegime.HOT
    assert result.performance_applied is False
    assert codes(result)[-1] is RegimeReasonCode.PERFORMANCE_SAMPLE_INSUFFICIENT


def test_missing_performance_expectancy_does_not_change_base_regime():
    result = assess_regime(
        hot_market(),
        policy(),
        perf(net_expectancy_after_costs_pct=None),
    )
    assert result.regime is MarketRegime.HOT
    assert result.performance_applied is False
    assert codes(result)[-1] is RegimeReasonCode.PERFORMANCE_EXPECTANCY_UNKNOWN


def test_dead_performance_expectancy_at_threshold_downgrades_to_dead():
    result = assess_regime(
        hot_market(),
        policy(),
        perf(net_expectancy_after_costs_pct=-5.0),
    )
    assert result.base_regime is MarketRegime.HOT
    assert result.regime is MarketRegime.DEAD
    assert result.performance_applied is True
    assert codes(result)[-1] is RegimeReasonCode.PERFORMANCE_EXPECTANCY_DEAD


def test_negative_expectancy_below_weak_floor_downgrades_hot_to_weak():
    result = assess_regime(
        hot_market(),
        policy(),
        perf(net_expectancy_after_costs_pct=-0.01),
    )
    assert result.base_regime is MarketRegime.HOT
    assert result.regime is MarketRegime.WEAK
    assert result.performance_applied is True
    assert codes(result)[-1] is RegimeReasonCode.PERFORMANCE_EXPECTANCY_WEAK


def test_performance_at_weak_floor_does_not_downgrade():
    result = assess_regime(
        hot_market(),
        policy(),
        perf(net_expectancy_after_costs_pct=0.0),
    )
    assert result.regime is MarketRegime.HOT
    assert result.performance_applied is False
    assert RegimeReasonCode.PERFORMANCE_EXPECTANCY_WEAK not in codes(result)


def test_strong_performance_never_upgrades_normal_market_to_hot():
    result = assess_regime(
        normal_market(),
        policy(),
        perf(net_expectancy_after_costs_pct=100.0),
    )
    assert result.base_regime is MarketRegime.NORMAL
    assert result.regime is MarketRegime.NORMAL
    assert result.performance_applied is False


def test_strong_performance_never_upgrades_weak_market():
    result = assess_regime(
        hot_market(median_liquidity_usd=20_000.0),
        policy(),
        perf(net_expectancy_after_costs_pct=100.0),
    )
    assert result.base_regime is MarketRegime.WEAK
    assert result.regime is MarketRegime.WEAK
    assert result.performance_applied is False


def test_multiple_weak_findings_have_deterministic_metric_order():
    market = RegimeMarketWindow(
        as_of_unix_ms=5_010_000,
        source_observed_at_unix_ms=5_000_000,
        window_started_at_unix_ms=1_400_000,
        candidate_count=5,
        executable_candidate_count=2,
        median_liquidity_usd=20_000.0,
        median_volume_m5_usd=4_000.0,
    )
    result = assess_regime(market, policy())
    assert codes(result) == (
        RegimeReasonCode.OPPORTUNITY_RATE_WEAK,
        RegimeReasonCode.EXECUTABLE_FRACTION_WEAK,
        RegimeReasonCode.LIQUIDITY_WEAK,
        RegimeReasonCode.VOLUME_WEAK,
        RegimeReasonCode.PERFORMANCE_UNAVAILABLE,
    )


def test_repeated_equal_inputs_produce_equal_assessments():
    market = normal_market()
    configured = policy()
    performance = perf(net_expectancy_after_costs_pct=-0.25)
    assert assess_regime(market, configured, performance) == assess_regime(
        market, configured, performance
    )
