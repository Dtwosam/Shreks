from dataclasses import FrozenInstanceError, fields, replace
import math

import pytest

from shreks_brain.regime.models import (
    MarketRegime,
    RecentStrategyPerformance,
    RegimeAssessment,
    RegimeFinding,
    RegimeMarketWindow,
    RegimePolicy,
    RegimeReasonCode,
)


EXPECTED_REASON_CODES = (
    "SOURCE_AFTER_AS_OF",
    "SOURCE_DATA_TOO_OLD",
    "WINDOW_TOO_SHORT",
    "NO_CANDIDATES",
    "CANDIDATE_SAMPLE_TOO_SMALL",
    "MEDIAN_LIQUIDITY_UNKNOWN",
    "MEDIAN_VOLUME_M5_UNKNOWN",
    "OPPORTUNITY_RATE_DEAD",
    "EXECUTABLE_FRACTION_DEAD",
    "OPPORTUNITY_RATE_WEAK",
    "EXECUTABLE_FRACTION_WEAK",
    "LIQUIDITY_WEAK",
    "VOLUME_WEAK",
    "ALL_HOT_MARKET_THRESHOLDS_PASSED",
    "NORMAL_MIXED_MARKET",
    "PERFORMANCE_UNAVAILABLE",
    "PERFORMANCE_AFTER_AS_OF",
    "PERFORMANCE_AFTER_MARKET_SOURCE",
    "PERFORMANCE_SAMPLE_INSUFFICIENT",
    "PERFORMANCE_EXPECTANCY_UNKNOWN",
    "PERFORMANCE_EXPECTANCY_DEAD",
    "PERFORMANCE_EXPECTANCY_WEAK",
)


def market(**overrides):
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


def performance(**overrides):
    values = dict(
        observed_through_unix_ms=1_290_000,
        closed_trade_count=30,
        net_expectancy_after_costs_pct=1.5,
    )
    values.update(overrides)
    return RecentStrategyPerformance(**values)


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


def assessment(**overrides):
    values = dict(
        policy_version="regime-v1-test",
        as_of_unix_ms=1_310_000,
        source_observed_at_unix_ms=1_300_000,
        window_started_at_unix_ms=940_000,
        source_age_ms=10_000,
        window_seconds=360.0,
        candidate_count=12,
        candidate_rate_per_hour=120.0,
        executable_fraction=0.75,
        median_liquidity_usd=80_000.0,
        median_volume_m5_usd=25_000.0,
        base_regime=MarketRegime.NORMAL,
        regime=MarketRegime.NORMAL,
        performance_sample_count=30,
        performance_net_expectancy_after_costs_pct=1.5,
        performance_applied=False,
        findings=(
            RegimeFinding(
                code=RegimeReasonCode.NORMAL_MIXED_MARKET,
                message="mixed healthy market",
            ),
        ),
    )
    values.update(overrides)
    return RegimeAssessment(**values)


def test_enum_and_reason_code_contract_is_exact():
    assert tuple(item.value for item in MarketRegime) == (
        "HOT",
        "NORMAL",
        "WEAK",
        "DEAD",
    )
    assert tuple(item.value for item in RegimeReasonCode) == EXPECTED_REASON_CODES


def test_canonical_models_construct_and_are_frozen():
    market_value = market()
    performance_value = performance()
    policy_value = policy()
    finding = RegimeFinding(
        code=RegimeReasonCode.NORMAL_MIXED_MARKET,
        message="mixed healthy market",
        observed_value=12,
        threshold_value=5,
    )
    assessment_value = assessment(findings=(finding,))

    for value in (
        market_value,
        performance_value,
        policy_value,
        finding,
        assessment_value,
    ):
        with pytest.raises(FrozenInstanceError):
            value.__setattr__(next(iter(value.__dataclass_fields__)), None)


@pytest.mark.parametrize("field", [
    "as_of_unix_ms",
    "source_observed_at_unix_ms",
    "window_started_at_unix_ms",
])
@pytest.mark.parametrize("bad", [-1, -0.1, 1.5, True, False, "1"])
def test_market_timestamps_require_non_negative_integers(field, bad):
    with pytest.raises(ValueError):
        market(**{field: bad})


def test_market_allows_source_after_as_of_for_evaluator_fail_closed_handling():
    value = market(source_observed_at_unix_ms=1_320_000)
    assert value.source_observed_at_unix_ms > value.as_of_unix_ms


@pytest.mark.parametrize(
    "start,source",
    [
        (1_300_000, 1_300_000),
        (1_301_000, 1_300_000),
    ],
)
def test_window_start_must_be_strictly_before_source(start, source):
    with pytest.raises(ValueError):
        market(window_started_at_unix_ms=start, source_observed_at_unix_ms=source)


@pytest.mark.parametrize("field", ["candidate_count", "executable_candidate_count"])
@pytest.mark.parametrize("bad", [-1, -0.1, 1.5, True, False, "1"])
def test_market_counts_require_non_negative_integers(field, bad):
    with pytest.raises(ValueError):
        market(**{field: bad})


def test_executable_count_cannot_exceed_candidate_count():
    with pytest.raises(ValueError):
        market(candidate_count=3, executable_candidate_count=4)


@pytest.mark.parametrize("field", ["median_liquidity_usd", "median_volume_m5_usd"])
def test_market_medians_allow_none(field):
    assert getattr(market(**{field: None}), field) is None


@pytest.mark.parametrize("field", ["median_liquidity_usd", "median_volume_m5_usd"])
@pytest.mark.parametrize("bad", [-1.0, math.inf, -math.inf, math.nan, True, "1"])
def test_market_medians_require_finite_non_negative_numbers(field, bad):
    with pytest.raises(ValueError):
        market(**{field: bad})


@pytest.mark.parametrize("bad", [-1, 1.5, True, "1"])
def test_performance_timestamp_requires_non_negative_integer(bad):
    with pytest.raises(ValueError):
        performance(observed_through_unix_ms=bad)


@pytest.mark.parametrize("bad", [-1, 1.5, True, "1"])
def test_performance_trade_count_requires_non_negative_integer(bad):
    with pytest.raises(ValueError):
        performance(closed_trade_count=bad)


def test_performance_expectancy_is_optional_and_signed():
    assert performance(net_expectancy_after_costs_pct=None).net_expectancy_after_costs_pct is None
    assert performance(net_expectancy_after_costs_pct=-12.5).net_expectancy_after_costs_pct == -12.5


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan, True, "1"])
def test_performance_expectancy_must_be_finite_when_present(bad):
    with pytest.raises(ValueError):
        performance(net_expectancy_after_costs_pct=bad)


def test_policy_version_must_be_non_empty():
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            policy(version=bad)


@pytest.mark.parametrize("field", [
    "max_source_age_ms",
    "min_candidate_samples",
    "min_performance_sample_count",
])
@pytest.mark.parametrize("bad", [-1, 1.5, True, "1"])
def test_policy_integer_fields_are_non_negative_integers(field, bad):
    with pytest.raises(ValueError):
        policy(**{field: bad})


@pytest.mark.parametrize("field", [
    "min_window_seconds",
    "dead_max_candidate_rate_per_hour",
    "weak_min_candidate_rate_per_hour",
    "hot_min_candidate_rate_per_hour",
    "weak_min_median_liquidity_usd",
    "hot_min_median_liquidity_usd",
    "weak_min_median_volume_m5_usd",
    "hot_min_median_volume_m5_usd",
])
@pytest.mark.parametrize("bad", [-1.0, math.inf, -math.inf, math.nan, True, "1"])
def test_policy_non_negative_market_numbers_are_validated(field, bad):
    with pytest.raises(ValueError):
        policy(**{field: bad})


@pytest.mark.parametrize("field", [
    "dead_max_executable_fraction",
    "weak_min_executable_fraction",
    "hot_min_executable_fraction",
])
@pytest.mark.parametrize("bad", [-0.01, 1.01, math.inf, math.nan, True, "1"])
def test_policy_fraction_fields_are_bounded(field, bad):
    with pytest.raises(ValueError):
        policy(**{field: bad})


@pytest.mark.parametrize(
    "overrides",
    [
        {"dead_max_candidate_rate_per_hour": 9.0, "weak_min_candidate_rate_per_hour": 8.0},
        {"weak_min_candidate_rate_per_hour": 21.0, "hot_min_candidate_rate_per_hour": 20.0},
        {"dead_max_executable_fraction": 0.6, "weak_min_executable_fraction": 0.5},
        {"weak_min_executable_fraction": 0.9, "hot_min_executable_fraction": 0.8},
        {"weak_min_median_liquidity_usd": 80_000.0, "hot_min_median_liquidity_usd": 75_000.0},
        {"weak_min_median_volume_m5_usd": 25_000.0, "hot_min_median_volume_m5_usd": 20_000.0},
        {"dead_performance_expectancy_pct": 1.0, "weak_performance_expectancy_pct": 0.0},
    ],
)
def test_policy_threshold_bands_are_ordered(overrides):
    with pytest.raises(ValueError):
        policy(**overrides)


@pytest.mark.parametrize("field", [
    "dead_performance_expectancy_pct",
    "weak_performance_expectancy_pct",
])
@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan, True, "1"])
def test_policy_performance_thresholds_are_finite_signed_numbers(field, bad):
    with pytest.raises(ValueError):
        policy(**{field: bad})


def test_assessment_canonical_contract_and_fields():
    value = assessment()
    assert value.base_regime is MarketRegime.NORMAL
    assert value.regime is MarketRegime.NORMAL
    assert value.performance_applied is False

    assert tuple(field.name for field in fields(RegimeAssessment)) == (
        "policy_version",
        "as_of_unix_ms",
        "source_observed_at_unix_ms",
        "window_started_at_unix_ms",
        "source_age_ms",
        "window_seconds",
        "candidate_count",
        "candidate_rate_per_hour",
        "executable_fraction",
        "median_liquidity_usd",
        "median_volume_m5_usd",
        "base_regime",
        "regime",
        "performance_sample_count",
        "performance_net_expectancy_after_costs_pct",
        "performance_applied",
        "findings",
    )


def test_assessment_allows_none_for_contradictory_source_age_and_optional_evidence():
    value = assessment(
        source_age_ms=None,
        executable_fraction=None,
        median_liquidity_usd=None,
        median_volume_m5_usd=None,
        performance_sample_count=None,
        performance_net_expectancy_after_costs_pct=None,
        base_regime=MarketRegime.DEAD,
        regime=MarketRegime.DEAD,
    )
    assert value.source_age_ms is None
    assert value.executable_fraction is None


@pytest.mark.parametrize("bad", ["", " ", None])
def test_assessment_policy_version_must_be_non_empty(bad):
    with pytest.raises(ValueError):
        assessment(policy_version=bad)


@pytest.mark.parametrize("field", [
    "as_of_unix_ms",
    "source_observed_at_unix_ms",
    "window_started_at_unix_ms",
    "candidate_count",
])
@pytest.mark.parametrize("bad", [-1, 1.5, True, "1"])
def test_assessment_non_negative_integer_fields_are_validated(field, bad):
    with pytest.raises(ValueError):
        assessment(**{field: bad})


@pytest.mark.parametrize("bad", [-1, 1.5, True, "1"])
def test_assessment_optional_source_age_is_validated(bad):
    with pytest.raises(ValueError):
        assessment(source_age_ms=bad)


@pytest.mark.parametrize("field", ["window_seconds", "candidate_rate_per_hour"])
@pytest.mark.parametrize("bad", [-1.0, math.inf, -math.inf, math.nan, True, "1"])
def test_assessment_derived_non_negative_numbers_are_validated(field, bad):
    with pytest.raises(ValueError):
        assessment(**{field: bad})


@pytest.mark.parametrize("bad", [-0.01, 1.01, math.inf, math.nan, True, "1"])
def test_assessment_optional_executable_fraction_is_bounded(bad):
    with pytest.raises(ValueError):
        assessment(executable_fraction=bad)


@pytest.mark.parametrize("bad", [-1, 1.5, True, "1"])
def test_assessment_optional_performance_sample_count_is_validated(bad):
    with pytest.raises(ValueError):
        assessment(performance_sample_count=bad)


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan, True, "1"])
def test_assessment_optional_performance_expectancy_is_finite(bad):
    with pytest.raises(ValueError):
        assessment(performance_net_expectancy_after_costs_pct=bad)


def test_assessment_requires_regime_enums_and_boolean_application_flag():
    with pytest.raises(ValueError):
        assessment(base_regime="NORMAL")
    with pytest.raises(ValueError):
        assessment(regime="NORMAL")
    with pytest.raises(ValueError):
        assessment(performance_applied=1)


def test_regime_assessment_has_no_execution_or_future_outcome_authority():
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
