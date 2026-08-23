from __future__ import annotations

from .models import (
    MarketRegime,
    RecentStrategyPerformance,
    RegimeAssessment,
    RegimeFinding,
    RegimeMarketWindow,
    RegimePolicy,
    RegimeReasonCode,
)


def assess_regime(
    market: RegimeMarketWindow,
    policy: RegimePolicy,
    performance: RecentStrategyPerformance | None = None,
) -> RegimeAssessment:
    if not isinstance(market, RegimeMarketWindow):
        raise TypeError("market must be a RegimeMarketWindow")
    if not isinstance(policy, RegimePolicy):
        raise TypeError("policy must be a RegimePolicy")
    if performance is not None and not isinstance(
        performance, RecentStrategyPerformance
    ):
        raise TypeError(
            "performance must be a RecentStrategyPerformance or None"
        )

    findings: list[RegimeFinding] = []

    window_seconds = (
        market.source_observed_at_unix_ms - market.window_started_at_unix_ms
    ) / 1000.0
    candidate_rate_per_hour = (
        market.candidate_count / window_seconds
    ) * 3600.0
    executable_fraction = (
        None
        if market.candidate_count == 0
        else market.executable_candidate_count / market.candidate_count
    )
    source_age_ms = (
        None
        if market.source_observed_at_unix_ms > market.as_of_unix_ms
        else market.as_of_unix_ms - market.source_observed_at_unix_ms
    )

    # Critical source/data-quality gates. These are global no-entry conditions,
    # so the base regime fails closed to DEAD rather than guessing a healthier
    # environment from partial evidence.
    critical_data_failure = False

    if market.source_observed_at_unix_ms > market.as_of_unix_ms:
        critical_data_failure = True
        findings.append(
            RegimeFinding(
                code=RegimeReasonCode.SOURCE_AFTER_AS_OF,
                message="market source observation is later than the regime decision time",
                observed_value=market.source_observed_at_unix_ms,
                threshold_value=market.as_of_unix_ms,
            )
        )
    elif source_age_ms is not None and source_age_ms > policy.max_source_age_ms:
        critical_data_failure = True
        findings.append(
            RegimeFinding(
                code=RegimeReasonCode.SOURCE_DATA_TOO_OLD,
                message="market source data is older than the configured regime freshness limit",
                observed_value=source_age_ms,
                threshold_value=policy.max_source_age_ms,
            )
        )

    if window_seconds < policy.min_window_seconds:
        critical_data_failure = True
        findings.append(
            RegimeFinding(
                code=RegimeReasonCode.WINDOW_TOO_SHORT,
                message="aggregate market window is shorter than the configured minimum",
                observed_value=window_seconds,
                threshold_value=policy.min_window_seconds,
            )
        )

    if market.candidate_count == 0:
        critical_data_failure = True
        findings.append(
            RegimeFinding(
                code=RegimeReasonCode.NO_CANDIDATES,
                message="aggregate market window contains no candidates",
                observed_value=market.candidate_count,
            )
        )

    if market.candidate_count < policy.min_candidate_samples:
        critical_data_failure = True
        findings.append(
            RegimeFinding(
                code=RegimeReasonCode.CANDIDATE_SAMPLE_TOO_SMALL,
                message="aggregate market window has too few candidates for regime classification",
                observed_value=market.candidate_count,
                threshold_value=policy.min_candidate_samples,
            )
        )

    if market.median_liquidity_usd is None:
        critical_data_failure = True
        findings.append(
            RegimeFinding(
                code=RegimeReasonCode.MEDIAN_LIQUIDITY_UNKNOWN,
                message="median market liquidity is unavailable",
                threshold_value=policy.weak_min_median_liquidity_usd,
            )
        )

    if market.median_volume_m5_usd is None:
        critical_data_failure = True
        findings.append(
            RegimeFinding(
                code=RegimeReasonCode.MEDIAN_VOLUME_M5_UNKNOWN,
                message="median five-minute market volume is unavailable",
                threshold_value=policy.weak_min_median_volume_m5_usd,
            )
        )

    if critical_data_failure:
        base_regime = MarketRegime.DEAD
    else:
        # Extremely weak opportunity frequency or executable breadth can each
        # independently make the market effectively DEAD for this system.
        dead_market = False
        if candidate_rate_per_hour <= policy.dead_max_candidate_rate_per_hour:
            dead_market = True
            findings.append(
                RegimeFinding(
                    code=RegimeReasonCode.OPPORTUNITY_RATE_DEAD,
                    message="candidate opportunity rate is at or below the DEAD ceiling",
                    observed_value=candidate_rate_per_hour,
                    threshold_value=policy.dead_max_candidate_rate_per_hour,
                )
            )
        if (
            executable_fraction is not None
            and executable_fraction <= policy.dead_max_executable_fraction
        ):
            dead_market = True
            findings.append(
                RegimeFinding(
                    code=RegimeReasonCode.EXECUTABLE_FRACTION_DEAD,
                    message="executable candidate breadth is at or below the DEAD ceiling",
                    observed_value=executable_fraction,
                    threshold_value=policy.dead_max_executable_fraction,
                )
            )

        if dead_market:
            base_regime = MarketRegime.DEAD
        else:
            weak_market = False
            if candidate_rate_per_hour < policy.weak_min_candidate_rate_per_hour:
                weak_market = True
                findings.append(
                    RegimeFinding(
                        code=RegimeReasonCode.OPPORTUNITY_RATE_WEAK,
                        message="candidate opportunity rate is below the WEAK minimum",
                        observed_value=candidate_rate_per_hour,
                        threshold_value=policy.weak_min_candidate_rate_per_hour,
                    )
                )
            if (
                executable_fraction is not None
                and executable_fraction < policy.weak_min_executable_fraction
            ):
                weak_market = True
                findings.append(
                    RegimeFinding(
                        code=RegimeReasonCode.EXECUTABLE_FRACTION_WEAK,
                        message="executable candidate breadth is below the WEAK minimum",
                        observed_value=executable_fraction,
                        threshold_value=policy.weak_min_executable_fraction,
                    )
                )
            if (
                market.median_liquidity_usd is not None
                and market.median_liquidity_usd
                < policy.weak_min_median_liquidity_usd
            ):
                weak_market = True
                findings.append(
                    RegimeFinding(
                        code=RegimeReasonCode.LIQUIDITY_WEAK,
                        message="median market liquidity is below the WEAK minimum",
                        observed_value=market.median_liquidity_usd,
                        threshold_value=policy.weak_min_median_liquidity_usd,
                    )
                )
            if (
                market.median_volume_m5_usd is not None
                and market.median_volume_m5_usd
                < policy.weak_min_median_volume_m5_usd
            ):
                weak_market = True
                findings.append(
                    RegimeFinding(
                        code=RegimeReasonCode.VOLUME_WEAK,
                        message="median five-minute market volume is below the WEAK minimum",
                        observed_value=market.median_volume_m5_usd,
                        threshold_value=policy.weak_min_median_volume_m5_usd,
                    )
                )

            if weak_market:
                base_regime = MarketRegime.WEAK
            else:
                hot_market = (
                    candidate_rate_per_hour
                    >= policy.hot_min_candidate_rate_per_hour
                    and executable_fraction is not None
                    and executable_fraction >= policy.hot_min_executable_fraction
                    and market.median_liquidity_usd is not None
                    and market.median_liquidity_usd
                    >= policy.hot_min_median_liquidity_usd
                    and market.median_volume_m5_usd is not None
                    and market.median_volume_m5_usd
                    >= policy.hot_min_median_volume_m5_usd
                )
                if hot_market:
                    base_regime = MarketRegime.HOT
                    findings.append(
                        RegimeFinding(
                            code=RegimeReasonCode.ALL_HOT_MARKET_THRESHOLDS_PASSED,
                            message="all configured HOT market thresholds passed",
                        )
                    )
                else:
                    base_regime = MarketRegime.NORMAL
                    findings.append(
                        RegimeFinding(
                            code=RegimeReasonCode.NORMAL_MIXED_MARKET,
                            message="market evidence is healthy but not uniformly HOT",
                        )
                    )

    regime = base_regime
    performance_applied = False
    performance_sample_count: int | None = None
    performance_expectancy: float | None = None

    # Recent after-cost strategy performance is intentionally downgrade-only.
    # This prevents a recent winning streak from manufacturing a HOT regime.
    if performance is None:
        findings.append(
            RegimeFinding(
                code=RegimeReasonCode.PERFORMANCE_UNAVAILABLE,
                message="recent after-cost strategy performance is unavailable",
            )
        )
    else:
        performance_sample_count = performance.closed_trade_count
        performance_expectancy = performance.net_expectancy_after_costs_pct

        if performance.observed_through_unix_ms > market.as_of_unix_ms:
            regime = MarketRegime.DEAD
            findings.append(
                RegimeFinding(
                    code=RegimeReasonCode.PERFORMANCE_AFTER_AS_OF,
                    message="strategy performance evidence is later than the regime decision time",
                    observed_value=performance.observed_through_unix_ms,
                    threshold_value=market.as_of_unix_ms,
                )
            )
        elif (
            performance.observed_through_unix_ms
            > market.source_observed_at_unix_ms
        ):
            regime = MarketRegime.DEAD
            findings.append(
                RegimeFinding(
                    code=RegimeReasonCode.PERFORMANCE_AFTER_MARKET_SOURCE,
                    message="strategy performance evidence is later than the market source observation",
                    observed_value=performance.observed_through_unix_ms,
                    threshold_value=market.source_observed_at_unix_ms,
                )
            )
        elif performance.closed_trade_count < policy.min_performance_sample_count:
            findings.append(
                RegimeFinding(
                    code=RegimeReasonCode.PERFORMANCE_SAMPLE_INSUFFICIENT,
                    message="recent strategy-performance sample is too small for a regime downgrade",
                    observed_value=performance.closed_trade_count,
                    threshold_value=policy.min_performance_sample_count,
                )
            )
        elif performance.net_expectancy_after_costs_pct is None:
            findings.append(
                RegimeFinding(
                    code=RegimeReasonCode.PERFORMANCE_EXPECTANCY_UNKNOWN,
                    message="recent after-cost strategy expectancy is unavailable",
                )
            )
        elif (
            performance.net_expectancy_after_costs_pct
            <= policy.dead_performance_expectancy_pct
        ):
            if regime is not MarketRegime.DEAD:
                performance_applied = True
            regime = MarketRegime.DEAD
            findings.append(
                RegimeFinding(
                    code=RegimeReasonCode.PERFORMANCE_EXPECTANCY_DEAD,
                    message="recent after-cost strategy expectancy reached the DEAD downgrade threshold",
                    observed_value=performance.net_expectancy_after_costs_pct,
                    threshold_value=policy.dead_performance_expectancy_pct,
                )
            )
        elif (
            performance.net_expectancy_after_costs_pct
            < policy.weak_performance_expectancy_pct
        ):
            if regime in (MarketRegime.HOT, MarketRegime.NORMAL):
                regime = MarketRegime.WEAK
                performance_applied = True
            findings.append(
                RegimeFinding(
                    code=RegimeReasonCode.PERFORMANCE_EXPECTANCY_WEAK,
                    message="recent after-cost strategy expectancy is below the WEAK downgrade floor",
                    observed_value=performance.net_expectancy_after_costs_pct,
                    threshold_value=policy.weak_performance_expectancy_pct,
                )
            )

    return RegimeAssessment(
        policy_version=policy.version,
        as_of_unix_ms=market.as_of_unix_ms,
        source_observed_at_unix_ms=market.source_observed_at_unix_ms,
        window_started_at_unix_ms=market.window_started_at_unix_ms,
        source_age_ms=source_age_ms,
        window_seconds=window_seconds,
        candidate_count=market.candidate_count,
        candidate_rate_per_hour=candidate_rate_per_hour,
        executable_fraction=executable_fraction,
        median_liquidity_usd=market.median_liquidity_usd,
        median_volume_m5_usd=market.median_volume_m5_usd,
        base_regime=base_regime,
        regime=regime,
        performance_sample_count=performance_sample_count,
        performance_net_expectancy_after_costs_pct=performance_expectancy,
        performance_applied=performance_applied,
        findings=tuple(findings),
    )
