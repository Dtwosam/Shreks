from __future__ import annotations

import hashlib

from shreks_brain.decision import DecisionAction, TradeDecision
from shreks_brain.regime import MarketRegime
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import SetupState

from .models import (
    RiskAssessment,
    RiskContext,
    RiskFinding,
    RiskPolicy,
    RiskReasonCode,
    RiskState,
    TradeIntent,
    TradeSide,
)


def assess_entry_risk(
    decision: TradeDecision,
    context: RiskContext,
    policy: RiskPolicy,
    execution_mode: RuntimeMode,
) -> RiskAssessment:
    """Risk-size one pre-entry decision without performing I/O or execution."""

    if not isinstance(decision, TradeDecision):
        raise ValueError("decision must be a TradeDecision")
    if not isinstance(context, RiskContext):
        raise ValueError("context must be a RiskContext")
    if not isinstance(policy, RiskPolicy):
        raise ValueError("policy must be a RiskPolicy")
    if not isinstance(execution_mode, RuntimeMode):
        raise ValueError("execution_mode must be a RuntimeMode")

    if decision.policy_version != policy.required_decision_policy_version:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.DECISION_POLICY_MISMATCH,
            "decision policy version does not match the risk policy requirement",
        )
    if decision.feature_schema_version != policy.required_feature_schema_version:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.FEATURE_SCHEMA_UNSUPPORTED,
            "decision feature schema is not supported by the risk policy",
        )
    if decision.action is not DecisionAction.ENTER:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.DECISION_NOT_ENTER,
            "risk assessment only accepts ENTER decisions",
        )
    if decision.safety_decision is not SafetyDecision.PASS:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.SAFETY_NOT_PASS,
            "safety decision is not PASS",
        )
    if decision.setup_state is not SetupState.READY:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.SETUP_NOT_READY,
            "setup state is not READY",
        )
    if decision.market_regime is MarketRegime.DEAD:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.REGIME_DEAD,
            "DEAD market regime cannot open a new position",
        )
    if decision.total_score is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.TOTAL_SCORE_UNAVAILABLE,
            "entry decision has no total score",
        )
    if context.as_of_unix_ms != decision.as_of_unix_ms:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.CONTEXT_AS_OF_MISMATCH,
            "risk context timestamp does not match the entry decision",
        )

    if execution_mode is RuntimeMode.OBSERVE:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.OBSERVE_MODE_NO_INTENTS,
            "observe mode cannot create trade intents",
        )
    if execution_mode is RuntimeMode.HALTED:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.HALTED_MODE,
            "halted mode cannot create trade intents",
        )
    if execution_mode is RuntimeMode.LIVE:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.LIVE_MODE_DISABLED,
            "live trade-intent creation is disabled in Phase B",
        )

    if context.kill_switch_active:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.KILL_SWITCH_ACTIVE,
            "global kill switch is active",
        )
    if context.operator_entry_halt_active:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.OPERATOR_ENTRY_HALT_ACTIVE,
            "operator entry halt is active",
        )
    if context.data_healthy is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.DATA_HEALTH_UNKNOWN,
            "data health is unknown",
        )
    if not context.data_healthy:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.DATA_HEALTH_DEGRADED,
            "data health is degraded",
        )
    if context.execution_healthy is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.EXECUTION_HEALTH_UNKNOWN,
            "execution health is unknown",
        )
    if not context.execution_healthy:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.EXECUTION_HEALTH_DEGRADED,
            "execution health is degraded",
        )

    if context.trading_capital_usd is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.TRADING_CAPITAL_UNKNOWN,
            "trading capital is unknown",
        )
    if context.trading_capital_usd <= 0.0:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.TRADING_CAPITAL_NON_POSITIVE,
            "trading capital is not positive",
        )
    if context.open_position_count is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.OPEN_POSITION_COUNT_UNKNOWN,
            "open position count is unknown",
        )
    if context.open_position_count >= policy.max_simultaneous_positions:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.MAX_POSITIONS_REACHED,
            "maximum simultaneous positions reached",
        )
    if context.aggregate_open_risk_usd is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.AGGREGATE_OPEN_RISK_UNKNOWN,
            "aggregate open risk is unknown",
        )
    if context.aggregate_open_risk_usd >= policy.max_aggregate_open_risk_usd:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.AGGREGATE_RISK_LIMIT_REACHED,
            "aggregate open-risk limit reached",
        )
    if context.daily_realized_pnl_usd is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.DAILY_REALIZED_PNL_UNKNOWN,
            "daily realized PnL is unknown",
        )
    if context.daily_realized_pnl_usd <= -policy.max_daily_realized_loss_usd:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.DAILY_LOSS_LIMIT_REACHED,
            "daily realized-loss limit reached",
        )
    if context.rolling_drawdown_pct is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.ROLLING_DRAWDOWN_UNKNOWN,
            "rolling drawdown is unknown",
        )
    if context.rolling_drawdown_pct >= policy.max_rolling_drawdown_pct:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.ROLLING_DRAWDOWN_LIMIT_REACHED,
            "rolling drawdown limit reached",
        )
    if context.consecutive_losses is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.CONSECUTIVE_LOSSES_UNKNOWN,
            "consecutive-loss count is unknown",
        )

    if (
        policy.cooldown_seconds > 0
        and context.consecutive_losses >= policy.cooldown_after_consecutive_losses
    ):
        if context.last_loss_at_unix_ms is None:
            return _reject(
                decision,
                policy,
                execution_mode,
                RiskReasonCode.LOSS_COOLDOWN_TIME_UNKNOWN,
                "last-loss timestamp is required while loss cooldown applies",
            )
        if context.last_loss_at_unix_ms > context.as_of_unix_ms:
            return _reject(
                decision,
                policy,
                execution_mode,
                RiskReasonCode.LOSS_COOLDOWN_TIME_AFTER_AS_OF,
                "last-loss timestamp is after the risk assessment time",
            )
        elapsed_ms = context.as_of_unix_ms - context.last_loss_at_unix_ms
        if elapsed_ms < policy.cooldown_seconds * 1_000:
            return _reject(
                decision,
                policy,
                execution_mode,
                RiskReasonCode.LOSS_COOLDOWN_ACTIVE,
                "consecutive-loss cooldown is still active",
            )

    requested_notional_usd = _requested_notional(context, policy)

    if context.liquidity_usd is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.LIQUIDITY_UNKNOWN,
            "liquidity is unknown",
        )
    if context.liquidity_usd < policy.min_liquidity_usd:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.LIQUIDITY_BELOW_MINIMUM,
            "liquidity is below the configured minimum",
        )
    if context.expected_price_impact_pct is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.PRICE_IMPACT_UNKNOWN,
            "expected entry price impact is unknown",
        )
    if context.price_impact_notional_usd is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.PRICE_IMPACT_NOTIONAL_UNKNOWN,
            "price-impact estimate notional is unknown",
        )
    if context.price_impact_notional_usd < requested_notional_usd:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.PRICE_IMPACT_NOTIONAL_TOO_SMALL,
            "price-impact estimate does not cover the risk-sized entry notional",
        )
    if context.expected_price_impact_pct > policy.max_expected_price_impact_pct:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.PRICE_IMPACT_TOO_HIGH,
            "expected entry price impact exceeds the configured maximum",
        )
    if context.market_data_age_ms is None:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.MARKET_DATA_AGE_UNKNOWN,
            "market data age is unknown",
        )
    if context.market_data_age_ms > policy.max_market_data_age_ms:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.MARKET_DATA_TOO_OLD,
            "market data is older than the configured maximum",
        )

    idempotency_key = _entry_idempotency_key(decision, execution_mode)
    if idempotency_key in context.active_intent_keys:
        return _reject(
            decision,
            policy,
            execution_mode,
            RiskReasonCode.DUPLICATE_ACTIVE_INTENT,
            "an active intent already exists for this entry idea",
        )

    intent = TradeIntent(
        mint=decision.mint,
        side=TradeSide.BUY,
        requested_notional_usd=requested_notional_usd,
        max_slippage_bps=policy.max_slippage_bps,
        strategy_name=decision.setup_name,
        strategy_version=decision.setup_policy_version,
        score_policy_version=decision.score_policy_version,
        decision_policy_version=decision.policy_version,
        risk_policy_version=policy.version,
        reason=DecisionReasonCodeValue.ENTRY_APPROVED,
        idempotency_key=idempotency_key,
        execution_mode=execution_mode,
        as_of_unix_ms=decision.as_of_unix_ms,
    )
    return RiskAssessment(
        policy_version=policy.version,
        mint=decision.mint,
        as_of_unix_ms=decision.as_of_unix_ms,
        state=RiskState.APPROVED,
        decision_action=decision.action,
        execution_mode=execution_mode,
        requested_notional_usd=requested_notional_usd,
        idempotency_key=idempotency_key,
        findings=(
            RiskFinding(
                code=RiskReasonCode.RISK_APPROVED,
                message="all configured risk guardrails passed",
            ),
        ),
        intent=intent,
    )


class DecisionReasonCodeValue:
    """Stable string bridge without importing decision finding internals."""

    ENTRY_APPROVED = "ENTRY_APPROVED"


def _requested_notional(context: RiskContext, policy: RiskPolicy) -> float:
    assert context.trading_capital_usd is not None
    assert context.aggregate_open_risk_usd is not None
    capital_fraction_cap = (
        context.trading_capital_usd * policy.max_capital_fraction_per_position
    )
    remaining_aggregate_risk = (
        policy.max_aggregate_open_risk_usd - context.aggregate_open_risk_usd
    )
    return min(
        policy.target_position_notional_usd,
        policy.max_notional_per_position_usd,
        capital_fraction_cap,
        remaining_aggregate_risk,
    )


def _entry_idempotency_key(
    decision: TradeDecision, execution_mode: RuntimeMode
) -> str:
    payload = "\n".join(
        (
            "entry-v1",
            execution_mode.value,
            decision.mint,
            str(decision.as_of_unix_ms),
            decision.setup_name,
            decision.setup_policy_version,
            decision.score_policy_version,
            decision.policy_version,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reject(
    decision: TradeDecision,
    policy: RiskPolicy,
    execution_mode: RuntimeMode,
    reason: RiskReasonCode,
    message: str,
) -> RiskAssessment:
    return RiskAssessment(
        policy_version=policy.version,
        mint=decision.mint,
        as_of_unix_ms=decision.as_of_unix_ms,
        state=RiskState.REJECTED,
        decision_action=decision.action,
        execution_mode=execution_mode,
        requested_notional_usd=None,
        idempotency_key=None,
        findings=(RiskFinding(code=reason, message=message),),
        intent=None,
    )
