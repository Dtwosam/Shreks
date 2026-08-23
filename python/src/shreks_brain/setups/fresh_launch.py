from __future__ import annotations

from shreks_brain.features import FeatureVector
from shreks_brain.safety import SafetyDecision

from .models import (
    FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
    FRESH_LAUNCH_SETUP_NAME,
    FreshLaunchAssessment,
    FreshLaunchPolicy,
    FreshLaunchReasonCode,
    SetupFinding,
    SetupState,
)


def assess_fresh_launch(
    features: FeatureVector,
    policy: FreshLaunchPolicy,
) -> FreshLaunchAssessment:
    if not isinstance(features, FeatureVector):
        raise TypeError("features must be a FeatureVector")
    if not isinstance(policy, FreshLaunchPolicy):
        raise TypeError("policy must be a FreshLaunchPolicy")

    findings: list[SetupFinding] = []
    hard_blocked = False
    watch_evidence = False

    # Stage 1: hard gates. These are state-dominant but do not short-circuit
    # confirmation evaluation because blocked candidates remain research data.
    if features.safety_decision is not SafetyDecision.PASS:
        hard_blocked = True
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.SAFETY_NOT_PASS,
                message="B1 safety must be PASS before this setup can be ready",
                observed_value=features.safety_decision.value,
            )
        )

    if (
        features.token_age_seconds is not None
        and features.token_age_seconds > policy.max_age_seconds
    ):
        hard_blocked = True
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.SETUP_WINDOW_EXPIRED,
                message="token is older than the Fresh Launch setup window",
                observed_value=features.token_age_seconds,
                threshold_value=policy.max_age_seconds,
            )
        )

    if features.source_age_ms > policy.max_source_age_ms:
        hard_blocked = True
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.SOURCE_DATA_TOO_OLD,
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
            SetupFinding(
                code=FreshLaunchReasonCode.LIQUIDITY_BELOW_MINIMUM,
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
            SetupFinding(
                code=FreshLaunchReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
                message="estimated exit price impact exceeds the setup ceiling",
                observed_value=features.exit_price_impact_pct,
                threshold_value=policy.max_exit_price_impact_pct,
            )
        )

    if (
        features.return_5m_pct is not None
        and features.return_5m_pct > policy.max_return_5m_pct
    ):
        hard_blocked = True
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.MOVE_TOO_EXTENDED,
                message="the five-minute move is already beyond the anti-chase ceiling",
                observed_value=features.return_5m_pct,
                threshold_value=policy.max_return_5m_pct,
            )
        )

    # Stage 2: age and required executability evidence. These can improve with
    # time/new observations, so they produce WATCH rather than BLOCKED.
    if features.token_age_seconds is None:
        watch_evidence = True
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.TOKEN_AGE_UNKNOWN,
                message="token age is unknown",
            )
        )
    elif features.token_age_seconds < policy.min_age_seconds:
        watch_evidence = True
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.SETUP_TOO_YOUNG,
                message="token is still younger than the minimum evidence window",
                observed_value=features.token_age_seconds,
                threshold_value=policy.min_age_seconds,
            )
        )

    if features.liquidity_usd is None:
        watch_evidence = True
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.LIQUIDITY_UNKNOWN,
                message="liquidity evidence is missing",
            )
        )

    if features.exit_price_impact_pct is None:
        watch_evidence = True
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.EXIT_PRICE_IMPACT_UNKNOWN,
                message="exit price-impact evidence is missing",
            )
        )

    # Stage 3: nine equal-weight continuation confirmations.
    confirmations_passed = 0
    confirmations_passed += _confirm_minimum(
        findings,
        features.tx_count_m5,
        policy.min_tx_count_m5,
        FreshLaunchReasonCode.TX_COUNT_M5_UNKNOWN,
        FreshLaunchReasonCode.TX_COUNT_M5_BELOW_MINIMUM,
        "five-minute transaction count",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.volume_velocity_ratio,
        policy.min_volume_velocity_ratio,
        FreshLaunchReasonCode.VOLUME_VELOCITY_UNKNOWN,
        FreshLaunchReasonCode.VOLUME_VELOCITY_BELOW_MINIMUM,
        "recent volume velocity",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.buy_fraction_m5,
        policy.min_buy_fraction_m5,
        FreshLaunchReasonCode.BUY_FRACTION_M5_UNKNOWN,
        FreshLaunchReasonCode.BUY_FRACTION_M5_BELOW_MINIMUM,
        "five-minute buy fraction",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.buy_pressure_acceleration,
        policy.min_buy_pressure_acceleration,
        FreshLaunchReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
        FreshLaunchReasonCode.BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM,
        "buy-pressure acceleration",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.return_1m_pct,
        policy.min_return_1m_pct,
        FreshLaunchReasonCode.RETURN_1M_UNKNOWN,
        FreshLaunchReasonCode.RETURN_1M_BELOW_MINIMUM,
        "one-minute return",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.return_5m_pct,
        policy.min_return_5m_pct,
        FreshLaunchReasonCode.RETURN_5M_UNKNOWN,
        FreshLaunchReasonCode.RETURN_5M_BELOW_MINIMUM,
        "five-minute return",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.liquidity_change_5m_pct,
        policy.min_liquidity_change_5m_pct,
        FreshLaunchReasonCode.LIQUIDITY_CHANGE_5M_UNKNOWN,
        FreshLaunchReasonCode.LIQUIDITY_CHANGE_5M_BELOW_MINIMUM,
        "five-minute liquidity change",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.distance_from_local_high_pct,
        policy.min_distance_from_local_high_pct,
        FreshLaunchReasonCode.DISTANCE_FROM_LOCAL_HIGH_UNKNOWN,
        FreshLaunchReasonCode.TOO_FAR_BELOW_LOCAL_HIGH,
        "distance from local high",
    )
    confirmations_passed += _confirm_minimum(
        findings,
        features.range_position_pct,
        policy.min_range_position_pct,
        FreshLaunchReasonCode.RANGE_POSITION_UNKNOWN,
        FreshLaunchReasonCode.RANGE_POSITION_BELOW_MINIMUM,
        "local range position",
    )

    confirmation_score = (
        confirmations_passed / FRESH_LAUNCH_CONFIRMATIONS_REQUIRED
    ) * 100.0

    # Stage 4: resolve state with hard blockers dominant.
    if hard_blocked:
        state = SetupState.BLOCKED
    elif watch_evidence or confirmations_passed < FRESH_LAUNCH_CONFIRMATIONS_REQUIRED:
        state = SetupState.WATCH
    else:
        state = SetupState.READY
        findings.append(
            SetupFinding(
                code=FreshLaunchReasonCode.ALL_CONFIRMATIONS_PASSED,
                message="all Fresh Launch continuation confirmations passed",
            )
        )

    return FreshLaunchAssessment(
        setup_name=FRESH_LAUNCH_SETUP_NAME,
        policy_version=policy.version,
        feature_schema_version=features.schema_version,
        as_of_unix_ms=features.as_of_unix_ms,
        state=state,
        confirmation_score=confirmation_score,
        confirmations_passed=confirmations_passed,
        confirmations_required=FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
        findings=tuple(findings),
    )


def _confirm_minimum(
    findings: list[SetupFinding],
    observed: float | int | None,
    threshold: float | int,
    unknown_code: FreshLaunchReasonCode,
    below_code: FreshLaunchReasonCode,
    label: str,
) -> int:
    if observed is None:
        findings.append(
            SetupFinding(
                code=unknown_code,
                message=f"{label} is unknown",
                threshold_value=threshold,
            )
        )
        return 0
    if observed < threshold:
        findings.append(
            SetupFinding(
                code=below_code,
                message=f"{label} is below the configured confirmation threshold",
                observed_value=observed,
                threshold_value=threshold,
            )
        )
        return 0
    return 1
