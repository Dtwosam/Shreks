from __future__ import annotations

from shreks_brain.features import FeatureVector
from shreks_brain.regime import RegimeAssessment
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import (
    FirstPullbackAssessment,
    FreshLaunchAssessment,
    GraduationBreakoutAssessment,
    SetupState,
)

from .models import ScoreAssessment, ScoreFinding, ScorePolicy, ScoreReasonCode


SetupAssessment = (
    FreshLaunchAssessment | GraduationBreakoutAssessment | FirstPullbackAssessment
)


def score_candidate(
    features: FeatureVector,
    setup: SetupAssessment,
    regime: RegimeAssessment,
    policy: ScorePolicy,
) -> ScoreAssessment:
    findings: list[ScoreFinding] = []

    compatibility_failed = False

    if features.schema_version != policy.required_feature_schema_version:
        compatibility_failed = True
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.FEATURE_SCHEMA_UNSUPPORTED,
                message="feature schema does not match scoring policy",
                observed_value=features.schema_version,
            )
        )

    if features.source_observed_at_unix_ms > features.as_of_unix_ms:
        compatibility_failed = True
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.FEATURE_SOURCE_AFTER_AS_OF,
                message="feature source observation is later than the decision timestamp",
                observed_value=features.source_observed_at_unix_ms,
                threshold_value=features.as_of_unix_ms,
            )
        )

    expected_source_age_ms = (
        features.as_of_unix_ms - features.source_observed_at_unix_ms
    )
    if features.source_age_ms != expected_source_age_ms:
        compatibility_failed = True
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.FEATURE_SOURCE_AGE_MISMATCH,
                message="feature source age does not match source/as-of timestamps",
                observed_value=features.source_age_ms,
                threshold_value=expected_source_age_ms,
            )
        )

    if setup.as_of_unix_ms != features.as_of_unix_ms:
        compatibility_failed = True
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.SETUP_AS_OF_MISMATCH,
                message="setup assessment timestamp does not match feature timestamp",
                observed_value=setup.as_of_unix_ms,
                threshold_value=features.as_of_unix_ms,
            )
        )

    if setup.feature_schema_version != features.schema_version:
        compatibility_failed = True
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.SETUP_FEATURE_SCHEMA_MISMATCH,
                message="setup assessment feature schema does not match feature vector",
                observed_value=setup.feature_schema_version,
            )
        )

    if regime.as_of_unix_ms != features.as_of_unix_ms:
        compatibility_failed = True
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.REGIME_AS_OF_MISMATCH,
                message="regime assessment timestamp does not match feature timestamp",
                observed_value=regime.as_of_unix_ms,
                threshold_value=features.as_of_unix_ms,
            )
        )

    if features.safety_decision is not SafetyDecision.PASS:
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.SAFETY_NOT_PASS_RESEARCH_ONLY,
                message="candidate score is research-only because safety did not pass",
                observed_value=features.safety_decision.value,
            )
        )

    if setup.state is not SetupState.READY:
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.SETUP_NOT_READY_RESEARCH_ONLY,
                message="candidate score is research-only because setup is not ready",
                observed_value=setup.state.value,
            )
        )

    safety_penalty = 0.0
    if features.safety_liquidity_weak:
        safety_penalty += policy.safety_liquidity_weak_penalty
    if features.safety_holder_concentration_elevated:
        safety_penalty += policy.safety_holder_concentration_elevated_penalty
    if features.safety_creator_concentration_elevated:
        safety_penalty += policy.safety_creator_concentration_elevated_penalty
    if features.safety_exit_price_impact_elevated:
        safety_penalty += policy.safety_exit_price_impact_elevated_penalty
    safety_quality_score = max(0.0, 100.0 - safety_penalty)

    money_flow_values: list[float] = []
    money_flow_complete = True

    if features.volume_velocity_ratio is None:
        money_flow_complete = False
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.VOLUME_VELOCITY_UNKNOWN,
                message="volume velocity is unavailable",
            )
        )
    else:
        money_flow_values.append(
            _normalize_up(
                features.volume_velocity_ratio,
                policy.volume_velocity_zero,
                policy.volume_velocity_full,
            )
        )

    if features.buy_fraction_m5 is None:
        money_flow_complete = False
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.BUY_FRACTION_M5_UNKNOWN,
                message="five-minute buy fraction is unavailable",
            )
        )
    else:
        money_flow_values.append(
            _normalize_up(
                features.buy_fraction_m5,
                policy.buy_fraction_m5_zero,
                policy.buy_fraction_m5_full,
            )
        )

    if features.buy_pressure_acceleration is None:
        money_flow_complete = False
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
                message="buy-pressure acceleration is unavailable",
            )
        )
    else:
        money_flow_values.append(
            _normalize_up(
                features.buy_pressure_acceleration,
                policy.buy_pressure_acceleration_zero,
                policy.buy_pressure_acceleration_full,
            )
        )

    money_flow_score = (
        _mean(tuple(money_flow_values)) if money_flow_complete else None
    )

    setup_quality_score = float(setup.confirmation_score)

    liquidity_values: list[float] = []
    liquidity_complete = True

    if features.liquidity_usd is None:
        liquidity_complete = False
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.LIQUIDITY_UNKNOWN,
                message="current liquidity is unavailable",
            )
        )
    else:
        liquidity_values.append(
            _normalize_up(
                features.liquidity_usd,
                policy.liquidity_usd_zero,
                policy.liquidity_usd_full,
            )
        )

    if features.exit_price_impact_pct is None:
        liquidity_complete = False
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.EXIT_PRICE_IMPACT_UNKNOWN,
                message="exit price impact is unavailable",
            )
        )
    else:
        liquidity_values.append(
            _normalize_inverse(
                features.exit_price_impact_pct,
                policy.exit_price_impact_full,
                policy.exit_price_impact_zero,
            )
        )

    liquidity_executability_score = (
        _mean(tuple(liquidity_values)) if liquidity_complete else None
    )

    if safety_penalty > 0.0:
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.SAFETY_SOFT_PENALTIES_APPLIED,
                message="one or more B2 soft-safety flags reduced safety quality",
                observed_value=safety_penalty,
            )
        )

    required_scores_available = True
    if policy.money_flow_weight > 0.0 and money_flow_score is None:
        required_scores_available = False
    if (
        policy.liquidity_executability_weight > 0.0
        and liquidity_executability_score is None
    ):
        required_scores_available = False

    total_score: float | None = None
    if not compatibility_failed and required_scores_available:
        total = (
            safety_quality_score * policy.safety_weight
            + setup_quality_score * policy.setup_quality_weight
        )
        if policy.money_flow_weight > 0.0:
            assert money_flow_score is not None
            total += money_flow_score * policy.money_flow_weight
        if policy.liquidity_executability_weight > 0.0:
            assert liquidity_executability_score is not None
            total += (
                liquidity_executability_score
                * policy.liquidity_executability_weight
            )
        total_score = min(100.0, max(0.0, total))

    if total_score is None:
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.TOTAL_SCORE_INCOMPLETE,
                message="total score is unavailable because required evidence is incomplete or incompatible",
            )
        )
    else:
        findings.append(
            ScoreFinding(
                code=ScoreReasonCode.TOTAL_SCORE_AVAILABLE,
                message="all positive-weight score families are available",
                observed_value=total_score,
            )
        )

    return ScoreAssessment(
        policy_version=policy.version,
        feature_schema_version=features.schema_version,
        as_of_unix_ms=features.as_of_unix_ms,
        source_observed_at_unix_ms=features.source_observed_at_unix_ms,
        safety_decision=features.safety_decision,
        setup_name=setup.setup_name,
        setup_policy_version=setup.policy_version,
        setup_state=setup.state,
        regime_policy_version=regime.policy_version,
        market_regime=regime.regime,
        safety_quality_score=safety_quality_score,
        money_flow_score=money_flow_score,
        setup_quality_score=setup_quality_score,
        liquidity_executability_score=liquidity_executability_score,
        total_score=total_score,
        findings=tuple(findings),
    )


def _normalize_up(value: float, zero: float, full: float) -> float:
    if value <= zero:
        return 0.0
    if value >= full:
        return 100.0
    return (value - zero) / (full - zero) * 100.0


def _normalize_inverse(value: float, full: float, zero: float) -> float:
    if value <= full:
        return 100.0
    if value >= zero:
        return 0.0
    return (zero - value) / (zero - full) * 100.0


def _mean(values: tuple[float, ...]) -> float:
    if not values:
        raise ValueError("values must not be empty")
    return sum(values) / len(values)
