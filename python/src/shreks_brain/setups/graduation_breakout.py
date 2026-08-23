from __future__ import annotations

from shreks_brain.features import FeatureVector
from shreks_brain.safety import SafetyDecision

from .models import (
    GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED,
    GRADUATION_BREAKOUT_SETUP_NAME,
    GraduationBreakoutAssessment,
    GraduationBreakoutFinding,
    GraduationBreakoutPolicy,
    GraduationBreakoutReasonCode,
    GraduationContext,
    SetupState,
)


PUMP_GRADUATION_EVENT = "pump_graduation"
PUMP_FUN_BONDING_CURVE_VENUE = "pump_fun_bonding_curve"
PUMP_SWAP_VENUE = "pump_swap"


def assess_graduation_breakout(
    features: FeatureVector,
    graduation: GraduationContext | None,
    policy: GraduationBreakoutPolicy,
) -> GraduationBreakoutAssessment:
    if not isinstance(features, FeatureVector):
        raise TypeError("features must be a FeatureVector")
    if graduation is not None and not isinstance(graduation, GraduationContext):
        raise TypeError("graduation must be a GraduationContext or None")
    if not isinstance(policy, GraduationBreakoutPolicy):
        raise TypeError("policy must be a GraduationBreakoutPolicy")

    findings: list[GraduationBreakoutFinding] = []
    hard_blocked = False
    watch_evidence = False

    graduation_mint = graduation.mint if graduation is not None else None
    graduation_detected_at_unix_ms = (
        graduation.detected_at_unix_ms if graduation is not None else None
    )
    seconds_since_graduation: float | None = None

    # Stage 1: lifecycle and safety gates. These dominate state, but feature
    # confirmations are still evaluated later so rejected opportunities remain
    # measurable research data.
    if features.safety_decision is not SafetyDecision.PASS:
        hard_blocked = True
        findings.append(
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.SAFETY_NOT_PASS,
                message="B1 safety must be PASS before this setup can be ready",
                observed_value=features.safety_decision.value,
            )
        )

    if graduation is None:
        hard_blocked = True
        findings.append(
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.GRADUATION_NOT_VERIFIED,
                message="protocol-verified Pump graduation evidence is required",
            )
        )
    else:
        if graduation.event_type != PUMP_GRADUATION_EVENT:
            hard_blocked = True
            findings.append(
                GraduationBreakoutFinding(
                    code=GraduationBreakoutReasonCode.GRADUATION_EVENT_NOT_PUMP,
                    message="lifecycle event is not a verified Pump graduation",
                    observed_value=graduation.event_type,
                )
            )

        if (
            graduation.from_venue != PUMP_FUN_BONDING_CURVE_VENUE
            or graduation.to_venue != PUMP_SWAP_VENUE
        ):
            hard_blocked = True
            findings.append(
                GraduationBreakoutFinding(
                    code=GraduationBreakoutReasonCode.GRADUATION_VENUE_TRANSITION_INVALID,
                    message="graduation must transition Pump.fun bonding curve to PumpSwap",
                    observed_value=(
                        f"{graduation.from_venue}->{graduation.to_venue}"
                    ),
                )
            )

        if graduation.detected_at_unix_ms > features.as_of_unix_ms:
            hard_blocked = True
            findings.append(
                GraduationBreakoutFinding(
                    code=GraduationBreakoutReasonCode.GRADUATION_AFTER_AS_OF,
                    message="local graduation detection is later than decision time",
                    observed_value=graduation.detected_at_unix_ms,
                    threshold_value=features.as_of_unix_ms,
                )
            )
        else:
            seconds_since_graduation = (
                features.as_of_unix_ms - graduation.detected_at_unix_ms
            ) / 1000.0

    # Stage 2: decision-safe post-graduation age window. Equality at either
    # boundary is allowed.
    if seconds_since_graduation is not None:
        if seconds_since_graduation > policy.max_seconds_since_graduation:
            hard_blocked = True
            findings.append(
                GraduationBreakoutFinding(
                    code=GraduationBreakoutReasonCode.POST_GRADUATION_WINDOW_EXPIRED,
                    message="verified graduation is older than the setup window",
                    observed_value=seconds_since_graduation,
                    threshold_value=policy.max_seconds_since_graduation,
                )
            )
        elif seconds_since_graduation < policy.min_seconds_since_graduation:
            watch_evidence = True
            findings.append(
                GraduationBreakoutFinding(
                    code=GraduationBreakoutReasonCode.GRADUATION_TOO_RECENT,
                    message="graduation is too recent for the minimum evidence window",
                    observed_value=seconds_since_graduation,
                    threshold_value=policy.min_seconds_since_graduation,
                )
            )

    # Stage 3: freshness, executability and anti-chase hard gates.
    if features.source_age_ms > policy.max_source_age_ms:
        hard_blocked = True
        findings.append(
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.SOURCE_DATA_TOO_OLD,
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
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.LIQUIDITY_BELOW_MINIMUM,
                message="executable liquidity is below the setup minimum",
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
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
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
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.MOVE_TOO_EXTENDED,
                message="the one-minute move is already beyond the anti-chase ceiling",
                observed_value=features.return_1m_pct,
                threshold_value=policy.max_return_1m_pct,
            )
        )

    # Stage 4: required executability evidence that may arrive later.
    if features.liquidity_usd is None:
        watch_evidence = True
        findings.append(
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.LIQUIDITY_UNKNOWN,
                message="liquidity evidence is missing",
            )
        )

    if features.exit_price_impact_pct is None:
        watch_evidence = True
        findings.append(
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.EXIT_PRICE_IMPACT_UNKNOWN,
                message="exit price-impact evidence is missing",
            )
        )

    # Stage 5: eight equal-weight confirmations. B2 five-minute return and
    # 1m-vs-5m acceleration are intentionally excluded because their anchors can
    # straddle the pre/post-graduation regime boundary.
    confirmations_passed = 0
    confirmations_passed += _confirm_minimum(
        findings,
        features.tx_count_m5,
        policy.min_tx_count_m5,
        GraduationBreakoutReasonCode.TX_COUNT_M5_UNKNOWN,
        GraduationBreakoutReasonCode.TX_COUNT_M5_BELOW_MINIMUM,
        "five-minute transaction count",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.volume_velocity_ratio,
        policy.min_volume_velocity_ratio,
        GraduationBreakoutReasonCode.VOLUME_VELOCITY_UNKNOWN,
        GraduationBreakoutReasonCode.VOLUME_VELOCITY_BELOW_MINIMUM,
        "recent volume velocity",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.buy_fraction_m5,
        policy.min_buy_fraction_m5,
        GraduationBreakoutReasonCode.BUY_FRACTION_M5_UNKNOWN,
        GraduationBreakoutReasonCode.BUY_FRACTION_M5_BELOW_MINIMUM,
        "five-minute buy fraction",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.buy_pressure_acceleration,
        policy.min_buy_pressure_acceleration,
        GraduationBreakoutReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
        GraduationBreakoutReasonCode.BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM,
        "buy-pressure acceleration",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.return_1m_pct,
        policy.min_return_1m_pct,
        GraduationBreakoutReasonCode.RETURN_1M_UNKNOWN,
        GraduationBreakoutReasonCode.RETURN_1M_BELOW_MINIMUM,
        "one-minute return",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.liquidity_change_5m_pct,
        policy.min_liquidity_change_5m_pct,
        GraduationBreakoutReasonCode.LIQUIDITY_CHANGE_5M_UNKNOWN,
        GraduationBreakoutReasonCode.LIQUIDITY_CHANGE_5M_BELOW_MINIMUM,
        "five-minute liquidity change",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.distance_from_local_high_pct,
        policy.min_distance_from_local_high_pct,
        GraduationBreakoutReasonCode.DISTANCE_FROM_LOCAL_HIGH_UNKNOWN,
        GraduationBreakoutReasonCode.TOO_FAR_BELOW_LOCAL_HIGH,
        "distance from local high",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.range_position_pct,
        policy.min_range_position_pct,
        GraduationBreakoutReasonCode.RANGE_POSITION_UNKNOWN,
        GraduationBreakoutReasonCode.RANGE_POSITION_BELOW_MINIMUM,
        "local range position",
    )

    confirmation_score = (
        confirmations_passed / GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED
    ) * 100.0

    # Stage 6: hard blockers dominate, then temporary/missing evidence, then
    # confirmation completeness.
    if hard_blocked:
        state = SetupState.BLOCKED
    elif watch_evidence or (
        confirmations_passed < GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED
    ):
        state = SetupState.WATCH
    else:
        state = SetupState.READY
        findings.append(
            GraduationBreakoutFinding(
                code=GraduationBreakoutReasonCode.ALL_CONFIRMATIONS_PASSED,
                message="all Graduation/Breakout confirmations passed",
            )
        )

    return GraduationBreakoutAssessment(
        setup_name=GRADUATION_BREAKOUT_SETUP_NAME,
        policy_version=policy.version,
        feature_schema_version=features.schema_version,
        as_of_unix_ms=features.as_of_unix_ms,
        graduation_mint=graduation_mint,
        graduation_detected_at_unix_ms=graduation_detected_at_unix_ms,
        seconds_since_graduation=seconds_since_graduation,
        state=state,
        confirmation_score=confirmation_score,
        confirmations_passed=confirmations_passed,
        confirmations_required=GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED,
        findings=tuple(findings),
    )


def _confirm_minimum(
    findings: list[GraduationBreakoutFinding],
    observed: float | int | None,
    threshold: float | int,
    unknown_code: GraduationBreakoutReasonCode,
    below_code: GraduationBreakoutReasonCode,
    label: str,
) -> int:
    if observed is None:
        findings.append(
            GraduationBreakoutFinding(
                code=unknown_code,
                message=f"{label} is unknown",
                threshold_value=threshold,
            )
        )
        return 0
    if observed < threshold:
        findings.append(
            GraduationBreakoutFinding(
                code=below_code,
                message=f"{label} is below the configured confirmation threshold",
                observed_value=observed,
                threshold_value=threshold,
            )
        )
        return 0
    return 1
