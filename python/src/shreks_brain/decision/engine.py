from __future__ import annotations

from shreks_brain.regime import MarketRegime
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScoreAssessment
from shreks_brain.setups import SetupState

from .models import (
    DecisionAction,
    DecisionFinding,
    DecisionPolicy,
    DecisionReasonCode,
    SetupDecisionRule,
    TradeDecision,
)


def decide_entry(
    mint: str,
    score: ScoreAssessment,
    policy: DecisionPolicy,
) -> TradeDecision:
    if score.policy_version != policy.required_score_policy_version:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.REJECT,
            reason=DecisionReasonCode.SCORE_POLICY_MISMATCH,
            message="score policy version does not match decision policy",
            observed_value=score.policy_version,
        )

    if score.safety_decision is SafetyDecision.REJECT:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.REJECT,
            reason=DecisionReasonCode.SAFETY_REJECTED,
            message="B1 safety rejected the candidate",
            observed_value=score.safety_decision.value,
        )

    if score.safety_decision is SafetyDecision.INCOMPLETE:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.WATCH,
            reason=DecisionReasonCode.SAFETY_INCOMPLETE,
            message="critical safety evidence is incomplete",
            observed_value=score.safety_decision.value,
        )

    if score.setup_state is SetupState.BLOCKED:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.REJECT,
            reason=DecisionReasonCode.SETUP_BLOCKED,
            message="setup is blocked",
            observed_value=score.setup_state.value,
        )

    if score.setup_state is SetupState.WATCH:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.WATCH,
            reason=DecisionReasonCode.SETUP_WATCH,
            message="setup is not yet ready",
            observed_value=score.setup_state.value,
        )

    rule = _find_rule(score.setup_name, policy)
    if rule is None:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.REJECT,
            reason=DecisionReasonCode.SETUP_RULE_MISSING,
            message="no decision rule exists for this setup",
            observed_value=score.setup_name,
        )

    if not rule.enabled:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.REJECT,
            reason=DecisionReasonCode.SETUP_DISABLED,
            message="this setup is disabled by decision policy",
            observed_value=score.setup_name,
        )

    if score.market_regime is MarketRegime.DEAD:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.REJECT,
            reason=DecisionReasonCode.REGIME_DEAD,
            message="new entries are disabled in a DEAD market regime",
            observed_value=score.market_regime.value,
        )

    threshold = _threshold_for_regime(rule, score.market_regime)
    if threshold is None:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.WATCH,
            reason=DecisionReasonCode.REGIME_DISABLED,
            message="this setup is disabled in the current market regime",
            observed_value=score.market_regime.value,
        )

    if score.total_score is None:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.WATCH,
            reason=DecisionReasonCode.TOTAL_SCORE_UNAVAILABLE,
            message="total candidate score is unavailable",
            threshold=threshold,
        )

    if score.total_score < threshold:
        return _decision(
            mint,
            score,
            policy,
            action=DecisionAction.WATCH,
            reason=DecisionReasonCode.TOTAL_SCORE_BELOW_THRESHOLD,
            message="total candidate score is below the active setup/regime threshold",
            observed_value=score.total_score,
            threshold=threshold,
        )

    return _decision(
        mint,
        score,
        policy,
        action=DecisionAction.ENTER,
        reason=DecisionReasonCode.ENTRY_APPROVED,
        message="candidate may proceed to the risk engine",
        observed_value=score.total_score,
        threshold=threshold,
    )


def _find_rule(setup_name: str, policy: DecisionPolicy) -> SetupDecisionRule | None:
    for rule in policy.setup_rules:
        if rule.setup_name == setup_name:
            return rule
    return None


def _threshold_for_regime(
    rule: SetupDecisionRule,
    regime: MarketRegime,
) -> float | None:
    if regime is MarketRegime.HOT:
        return rule.hot_min_score
    if regime is MarketRegime.NORMAL:
        return rule.normal_min_score
    if regime is MarketRegime.WEAK:
        return rule.weak_min_score
    return None


def _decision(
    mint: str,
    score: ScoreAssessment,
    policy: DecisionPolicy,
    *,
    action: DecisionAction,
    reason: DecisionReasonCode,
    message: str,
    observed_value: float | int | str | None = None,
    threshold: float | None = None,
) -> TradeDecision:
    finding = DecisionFinding(
        code=reason,
        message=message,
        observed_value=observed_value,
        threshold_value=threshold,
    )
    return TradeDecision(
        policy_version=policy.version,
        mint=mint,
        as_of_unix_ms=score.as_of_unix_ms,
        action=action,
        score_policy_version=score.policy_version,
        feature_schema_version=score.feature_schema_version,
        safety_decision=score.safety_decision,
        setup_name=score.setup_name,
        setup_policy_version=score.setup_policy_version,
        setup_state=score.setup_state,
        market_regime=score.market_regime,
        total_score=score.total_score,
        required_score_threshold=threshold,
        findings=(finding,),
    )
