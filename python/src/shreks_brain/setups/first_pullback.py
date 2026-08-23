from __future__ import annotations

from shreks_brain.features import FeatureVector
from shreks_brain.safety import SafetyDecision

from .models import (
    FIRST_PULLBACK_CONFIRMATIONS_REQUIRED,
    FIRST_PULLBACK_SETUP_NAME,
    FirstPullbackAssessment,
    FirstPullbackFinding,
    FirstPullbackPolicy,
    FirstPullbackReasonCode,
    PullbackContext,
    SetupState,
)


def assess_first_pullback(
    features: FeatureVector,
    pullback: PullbackContext | None,
    policy: FirstPullbackPolicy,
) -> FirstPullbackAssessment:
    if not isinstance(features, FeatureVector):
        raise TypeError("features must be a FeatureVector")
    if pullback is not None and not isinstance(pullback, PullbackContext):
        raise TypeError("pullback must be a PullbackContext or None")
    if not isinstance(policy, FirstPullbackPolicy):
        raise TypeError("policy must be a FirstPullbackPolicy")

    findings: list[FirstPullbackFinding] = []
    hard_blocked = False
    watch_evidence = False

    seconds_since_trough: float | None = None
    impulse_return_pct: float | None = None
    pullback_depth_pct: float | None = None
    recovery_from_trough_pct: float | None = None
    current_vs_peak_pct: float | None = None
    liquidity_retention_pct: float | None = None
    buy_fraction_improvement: float | None = None
    context_time_valid = False

    # Stage 1: safety and point-in-time context integrity. Hard blockers dominate
    # the final state, but later computable confirmations are still retained for
    # research rather than short-circuited.
    if features.safety_decision is not SafetyDecision.PASS:
        hard_blocked = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.SAFETY_NOT_PASS,
                message="B1 safety must be PASS before this setup can be ready",
                observed_value=features.safety_decision.value,
            )
        )

    if pullback is None:
        watch_evidence = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.PULLBACK_NOT_OBSERVED,
                message="explicit impulse, peak, and trough structure is not available",
            )
        )
    elif pullback.trough_at_unix_ms > features.as_of_unix_ms:
        hard_blocked = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.PULLBACK_AFTER_AS_OF,
                message="pullback trough is later than the decision time",
                observed_value=pullback.trough_at_unix_ms,
                threshold_value=features.as_of_unix_ms,
            )
        )
    elif pullback.trough_at_unix_ms > features.source_observed_at_unix_ms:
        hard_blocked = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.PULLBACK_AFTER_MARKET_SOURCE,
                message="pullback structure is newer than the current market observation",
                observed_value=pullback.trough_at_unix_ms,
                threshold_value=features.source_observed_at_unix_ms,
            )
        )
    else:
        context_time_valid = True
        seconds_since_trough = (
            features.source_observed_at_unix_ms - pullback.trough_at_unix_ms
        ) / 1000.0
        impulse_return_pct = (
            pullback.peak_price_usd / pullback.impulse_start_price_usd - 1.0
        ) * 100.0
        pullback_depth_pct = (
            1.0 - pullback.trough_price_usd / pullback.peak_price_usd
        ) * 100.0

        if features.price_usd is not None:
            current_vs_peak_pct = (
                features.price_usd / pullback.peak_price_usd - 1.0
            ) * 100.0
            if features.price_usd >= pullback.trough_price_usd:
                recovery_from_trough_pct = (
                    features.price_usd / pullback.trough_price_usd - 1.0
                ) * 100.0

        if (
            pullback.peak_liquidity_usd is not None
            and pullback.peak_liquidity_usd > 0
            and pullback.trough_liquidity_usd is not None
        ):
            liquidity_retention_pct = (
                pullback.trough_liquidity_usd / pullback.peak_liquidity_usd
            ) * 100.0

        if (
            pullback.trough_buy_fraction_m5 is not None
            and features.buy_fraction_m5 is not None
        ):
            buy_fraction_improvement = (
                features.buy_fraction_m5 - pullback.trough_buy_fraction_m5
            )

    # Stage 2: pattern age and sample quality.
    if context_time_valid and pullback is not None:
        if pullback.sample_count < policy.min_structure_samples:
            watch_evidence = True
            findings.append(
                FirstPullbackFinding(
                    code=FirstPullbackReasonCode.INSUFFICIENT_STRUCTURE_SAMPLES,
                    message="pullback structure has too few observations",
                    observed_value=pullback.sample_count,
                    threshold_value=policy.min_structure_samples,
                )
            )

        if seconds_since_trough is not None:
            if seconds_since_trough > policy.max_seconds_since_trough:
                hard_blocked = True
                findings.append(
                    FirstPullbackFinding(
                        code=FirstPullbackReasonCode.PULLBACK_WINDOW_EXPIRED,
                        message="pullback trough is older than the setup window",
                        observed_value=seconds_since_trough,
                        threshold_value=policy.max_seconds_since_trough,
                    )
                )
            elif seconds_since_trough < policy.min_seconds_since_trough:
                watch_evidence = True
                findings.append(
                    FirstPullbackFinding(
                        code=FirstPullbackReasonCode.PULLBACK_TOO_RECENT,
                        message="pullback is too recent for the minimum recovery window",
                        observed_value=seconds_since_trough,
                        threshold_value=policy.min_seconds_since_trough,
                    )
                )

        # Stage 3: structural hard gates.
        if (
            impulse_return_pct is not None
            and impulse_return_pct < policy.min_initial_impulse_pct
        ):
            hard_blocked = True
            findings.append(
                FirstPullbackFinding(
                    code=FirstPullbackReasonCode.INITIAL_IMPULSE_TOO_WEAK,
                    message="initial impulse is below the configured minimum",
                    observed_value=impulse_return_pct,
                    threshold_value=policy.min_initial_impulse_pct,
                )
            )

        if (
            pullback_depth_pct is not None
            and pullback_depth_pct > policy.max_pullback_depth_pct
        ):
            hard_blocked = True
            findings.append(
                FirstPullbackFinding(
                    code=FirstPullbackReasonCode.PULLBACK_TOO_DEEP,
                    message="pullback depth exceeds the configured maximum",
                    observed_value=pullback_depth_pct,
                    threshold_value=policy.max_pullback_depth_pct,
                )
            )

        if features.price_usd is not None:
            if features.price_usd < pullback.trough_price_usd:
                hard_blocked = True
                findings.append(
                    FirstPullbackFinding(
                        code=FirstPullbackReasonCode.PULLBACK_LOW_BROKEN,
                        message="current price has broken below the recorded pullback trough",
                        observed_value=features.price_usd,
                        threshold_value=pullback.trough_price_usd,
                    )
                )
            if (
                current_vs_peak_pct is not None
                and current_vs_peak_pct > policy.max_current_vs_peak_pct
            ):
                hard_blocked = True
                findings.append(
                    FirstPullbackFinding(
                        code=FirstPullbackReasonCode.BREAKOUT_TOO_EXTENDED,
                        message="current price is too far above the prior impulse peak",
                        observed_value=current_vs_peak_pct,
                        threshold_value=policy.max_current_vs_peak_pct,
                    )
                )

        # Stage 4: a shallow retracement may still mature, so it remains WATCH.
        if (
            pullback_depth_pct is not None
            and pullback_depth_pct < policy.min_pullback_depth_pct
        ):
            watch_evidence = True
            findings.append(
                FirstPullbackFinding(
                    code=FirstPullbackReasonCode.PULLBACK_NOT_DEEP_ENOUGH,
                    message="retracement has not reached the configured pullback depth",
                    observed_value=pullback_depth_pct,
                    threshold_value=policy.min_pullback_depth_pct,
                )
            )

    # Stage 5: current freshness, executability, and anti-chase hard gates.
    if features.source_age_ms > policy.max_source_age_ms:
        hard_blocked = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.SOURCE_DATA_TOO_OLD,
                message="current market source data is too old for setup evaluation",
                observed_value=features.source_age_ms,
                threshold_value=policy.max_source_age_ms,
            )
        )

    if (
        features.liquidity_usd is not None
        and features.liquidity_usd < policy.min_liquidity_usd
    ):
        hard_blocked = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.LIQUIDITY_BELOW_MINIMUM,
                message="current executable liquidity is below the setup minimum",
                observed_value=features.liquidity_usd,
                threshold_value=policy.min_liquidity_usd,
            )
        )

    if (
        features.exit_price_impact_pct is not None
        and features.exit_price_impact_pct > policy.max_exit_price_impact_pct
    ):
        hard_blocked = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
                message="estimated exit price impact exceeds the setup ceiling",
                observed_value=features.exit_price_impact_pct,
                threshold_value=policy.max_exit_price_impact_pct,
            )
        )

    if (
        features.return_1m_pct is not None
        and features.return_1m_pct > policy.max_return_1m_pct
    ):
        hard_blocked = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.MOVE_TOO_EXTENDED,
                message="one-minute recovery move is beyond the anti-chase ceiling",
                observed_value=features.return_1m_pct,
                threshold_value=policy.max_return_1m_pct,
            )
        )

    # Stage 6: required evidence that may be absent while the setup develops.
    if features.price_usd is None:
        watch_evidence = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.CURRENT_PRICE_UNKNOWN,
                message="current price evidence is missing",
            )
        )

    if features.liquidity_usd is None:
        watch_evidence = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.LIQUIDITY_UNKNOWN,
                message="current liquidity evidence is missing",
            )
        )

    if features.exit_price_impact_pct is None:
        watch_evidence = True
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.EXIT_PRICE_IMPACT_UNKNOWN,
                message="exit price-impact evidence is missing",
            )
        )

    if context_time_valid and pullback is not None:
        if liquidity_retention_pct is None:
            watch_evidence = True
            findings.append(
                FirstPullbackFinding(
                    code=FirstPullbackReasonCode.LIQUIDITY_RETENTION_UNKNOWN,
                    message="peak-to-trough liquidity retention cannot be measured",
                    threshold_value=policy.min_liquidity_retention_pct,
                )
            )
        if pullback.trough_buy_fraction_m5 is None:
            watch_evidence = True
            findings.append(
                FirstPullbackFinding(
                    code=FirstPullbackReasonCode.TROUGH_BUY_FRACTION_UNKNOWN,
                    message="trough buy-fraction evidence is missing",
                )
            )

    # Stage 7: nine equal-weight confirmations, in fixed contract order.
    confirmations_passed = 0
    confirmations_passed += _confirm_minimum(
        findings,
        recovery_from_trough_pct,
        policy.min_recovery_from_trough_pct,
        FirstPullbackReasonCode.RECOVERY_FROM_TROUGH_UNKNOWN,
        FirstPullbackReasonCode.RECOVERY_FROM_TROUGH_BELOW_MINIMUM,
        "recovery from pullback trough",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        current_vs_peak_pct,
        policy.min_current_vs_peak_pct,
        FirstPullbackReasonCode.CURRENT_VS_PEAK_UNKNOWN,
        FirstPullbackReasonCode.CURRENT_VS_PEAK_BELOW_MINIMUM,
        "current price versus prior impulse peak",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        liquidity_retention_pct,
        policy.min_liquidity_retention_pct,
        FirstPullbackReasonCode.LIQUIDITY_RETENTION_UNKNOWN,
        FirstPullbackReasonCode.LIQUIDITY_RETENTION_BELOW_MINIMUM,
        "peak-to-trough liquidity retention",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.tx_count_m5,
        policy.min_tx_count_m5,
        FirstPullbackReasonCode.TX_COUNT_M5_UNKNOWN,
        FirstPullbackReasonCode.TX_COUNT_M5_BELOW_MINIMUM,
        "five-minute transaction count",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.volume_velocity_ratio,
        policy.min_volume_velocity_ratio,
        FirstPullbackReasonCode.VOLUME_VELOCITY_UNKNOWN,
        FirstPullbackReasonCode.VOLUME_VELOCITY_BELOW_MINIMUM,
        "recent volume velocity",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.buy_fraction_m5,
        policy.min_buy_fraction_m5,
        FirstPullbackReasonCode.BUY_FRACTION_M5_UNKNOWN,
        FirstPullbackReasonCode.BUY_FRACTION_M5_BELOW_MINIMUM,
        "five-minute buy fraction",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        buy_fraction_improvement,
        policy.min_buy_fraction_improvement,
        FirstPullbackReasonCode.BUY_FRACTION_IMPROVEMENT_UNKNOWN,
        FirstPullbackReasonCode.BUY_FRACTION_IMPROVEMENT_BELOW_MINIMUM,
        "buy-fraction improvement versus the trough",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.buy_pressure_acceleration,
        policy.min_buy_pressure_acceleration,
        FirstPullbackReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
        FirstPullbackReasonCode.BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM,
        "buy-pressure acceleration",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.return_1m_pct,
        policy.min_return_1m_pct,
        FirstPullbackReasonCode.RETURN_1M_UNKNOWN,
        FirstPullbackReasonCode.RETURN_1M_BELOW_MINIMUM,
        "one-minute return",
    )

    confirmation_score = (
        confirmations_passed / FIRST_PULLBACK_CONFIRMATIONS_REQUIRED
    ) * 100.0

    # Stage 8: hard blockers dominate temporary/missing evidence and checklist
    # completeness. READY adds exactly one final marker.
    if hard_blocked:
        state = SetupState.BLOCKED
    elif watch_evidence or (
        confirmations_passed < FIRST_PULLBACK_CONFIRMATIONS_REQUIRED
    ):
        state = SetupState.WATCH
    else:
        state = SetupState.READY
        findings.append(
            FirstPullbackFinding(
                code=FirstPullbackReasonCode.ALL_CONFIRMATIONS_PASSED,
                message="all First Pullback confirmations passed",
            )
        )

    return FirstPullbackAssessment(
        setup_name=FIRST_PULLBACK_SETUP_NAME,
        policy_version=policy.version,
        feature_schema_version=features.schema_version,
        as_of_unix_ms=features.as_of_unix_ms,
        state=state,
        seconds_since_trough=seconds_since_trough,
        impulse_return_pct=impulse_return_pct,
        pullback_depth_pct=pullback_depth_pct,
        recovery_from_trough_pct=recovery_from_trough_pct,
        current_vs_peak_pct=current_vs_peak_pct,
        liquidity_retention_pct=liquidity_retention_pct,
        buy_fraction_improvement=buy_fraction_improvement,
        confirmation_score=confirmation_score,
        confirmations_passed=confirmations_passed,
        confirmations_required=FIRST_PULLBACK_CONFIRMATIONS_REQUIRED,
        findings=tuple(findings),
    )


def _confirm_minimum(
    findings: list[FirstPullbackFinding],
    observed: float | int | None,
    threshold: float | int,
    unknown_code: FirstPullbackReasonCode,
    below_code: FirstPullbackReasonCode,
    label: str,
) -> int:
    if observed is None:
        findings.append(
            FirstPullbackFinding(
                code=unknown_code,
                message=f"{label} is unknown",
                threshold_value=threshold,
            )
        )
        return 0
    if observed < threshold:
        findings.append(
            FirstPullbackFinding(
                code=below_code,
                message=f"{label} is below the configured confirmation threshold",
                observed_value=observed,
                threshold_value=threshold,
            )
        )
        return 0
    return 1
