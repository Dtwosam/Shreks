from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import math

from shreks_brain.runtime import RuntimeMode

from .models import (
    RiskContext,
    RiskFinding,
    RiskPolicy,
    RiskReasonCode,
    RiskState,
    TradeIntent,
    TradeSide,
)


FAST_LANE_SCORE_POLICY_SENTINEL = "not-applicable:fast-lane"
_FAST_LANE_RISK_KEY_VERSION = "fl7.2-entry-risk-v1"
_ARITH_REL_TOL = 1e-12
_ARITH_ABS_TOL = 1e-9


class FastEntryRiskReasonCode(StrEnum):
    REQUESTED_NOTIONAL_EXCEEDS_RISK_CAP = "REQUESTED_NOTIONAL_EXCEEDS_RISK_CAP"


@dataclass(frozen=True, slots=True)
class FastEntryRiskFinding:
    code: FastEntryRiskReasonCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, FastEntryRiskReasonCode):
            raise ValueError("code must be FastEntryRiskReasonCode")
        _require_non_empty_string("message", self.message)


@dataclass(frozen=True, slots=True)
class FastEntryRiskRequest:
    mint: str
    source_event_id: str
    decision_at_unix_ms: int
    evaluated_at_unix_ms: int
    strategy_name: str
    strategy_version: str
    action_assessment_version: str
    state_version: str
    requested_notional_usd: float

    def __post_init__(self) -> None:
        for name in (
            "mint",
            "source_event_id",
            "strategy_name",
            "strategy_version",
            "action_assessment_version",
            "state_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("decision_at_unix_ms", self.decision_at_unix_ms)
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        if self.evaluated_at_unix_ms < self.decision_at_unix_ms:
            raise ValueError("evaluated_at_unix_ms must not precede decision_at_unix_ms")
        _require_positive_finite("requested_notional_usd", self.requested_notional_usd)


@dataclass(frozen=True, slots=True)
class FastEntryRiskAssessment:
    policy_version: str
    mint: str
    source_event_id: str
    decision_at_unix_ms: int
    evaluated_at_unix_ms: int
    state: RiskState
    execution_mode: RuntimeMode
    requested_notional_usd: float
    approved_notional_usd: float | None
    idempotency_key: str | None
    findings: tuple[RiskFinding | FastEntryRiskFinding, ...]
    intent: TradeIntent | None

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("mint", self.mint)
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_non_negative_int("decision_at_unix_ms", self.decision_at_unix_ms)
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        if self.evaluated_at_unix_ms < self.decision_at_unix_ms:
            raise ValueError("risk evaluation cannot precede decision timestamp")
        if not isinstance(self.state, RiskState):
            raise ValueError("state must be RiskState")
        if not isinstance(self.execution_mode, RuntimeMode):
            raise ValueError("execution_mode must be RuntimeMode")
        _require_positive_finite("requested_notional_usd", self.requested_notional_usd)
        if not isinstance(self.findings, tuple) or len(self.findings) != 1:
            raise ValueError("findings must contain exactly one risk finding")
        finding = self.findings[0]
        if not isinstance(finding, (RiskFinding, FastEntryRiskFinding)):
            raise ValueError("findings must contain a supported risk finding")

        if self.state is RiskState.REJECTED:
            if self.approved_notional_usd is not None:
                raise ValueError("rejected Fast Lane risk cannot approve notional")
            if self.idempotency_key is not None or self.intent is not None:
                raise ValueError("rejected Fast Lane risk cannot carry an intent")
            if isinstance(finding, RiskFinding) and finding.code is RiskReasonCode.RISK_APPROVED:
                raise ValueError("rejected Fast Lane risk cannot be RISK_APPROVED")
            return

        if self.approved_notional_usd is None:
            raise ValueError("approved Fast Lane risk requires approved_notional_usd")
        _require_positive_finite("approved_notional_usd", self.approved_notional_usd)
        if not math.isclose(
            self.approved_notional_usd,
            self.requested_notional_usd,
            rel_tol=_ARITH_REL_TOL,
            abs_tol=_ARITH_ABS_TOL,
        ):
            raise ValueError("Fast Lane risk may not silently resize requested notional")
        if self.idempotency_key is None:
            raise ValueError("approved Fast Lane risk requires idempotency_key")
        _require_non_empty_string("idempotency_key", self.idempotency_key)
        if self.intent is None:
            raise ValueError("approved Fast Lane risk requires TradeIntent")
        if not isinstance(finding, RiskFinding) or finding.code is not RiskReasonCode.RISK_APPROVED:
            raise ValueError("approved Fast Lane risk requires preserved RISK_APPROVED finding")
        if self.intent.mint != self.mint:
            raise ValueError("intent mint must match Fast Lane risk assessment")
        if self.intent.as_of_unix_ms != self.decision_at_unix_ms:
            raise ValueError("intent timestamp must retain original Fast Lane decision time")
        if self.intent.execution_mode is not self.execution_mode:
            raise ValueError("intent execution mode must match Fast Lane risk assessment")
        if not math.isclose(
            self.intent.requested_notional_usd,
            self.approved_notional_usd,
            rel_tol=_ARITH_REL_TOL,
            abs_tol=_ARITH_ABS_TOL,
        ):
            raise ValueError("intent notional must match approved Fast Lane notional")
        if self.intent.idempotency_key != self.idempotency_key:
            raise ValueError("intent key must match Fast Lane risk assessment")
        if self.intent.risk_policy_version != self.policy_version:
            raise ValueError("intent risk version must match Fast Lane risk assessment")


def assess_fast_entry_risk(
    request: FastEntryRiskRequest,
    context: RiskContext,
    policy: RiskPolicy,
    execution_mode: RuntimeMode,
) -> FastEntryRiskAssessment:
    """Apply preserved entry guardrails to one exact Fast Lane PAPER notional.

    Unlike the legacy risk entrypoint, this function does not construct or
    require a legacy setup/score TradeDecision. It approves the exact requested
    notional or rejects it; it never silently resizes the Rust-assessed trade.
    """

    if not isinstance(request, FastEntryRiskRequest):
        raise ValueError("request must be FastEntryRiskRequest")
    if not isinstance(context, RiskContext):
        raise ValueError("context must be RiskContext")
    if not isinstance(policy, RiskPolicy):
        raise ValueError("policy must be RiskPolicy")
    if not isinstance(execution_mode, RuntimeMode):
        raise ValueError("execution_mode must be RuntimeMode")

    if request.action_assessment_version != policy.required_decision_policy_version:
        return _reject(
            request,
            policy,
            execution_mode,
            RiskReasonCode.DECISION_POLICY_MISMATCH,
            "Fast Lane action-assessment version does not match risk policy requirement",
        )
    if request.state_version != policy.required_feature_schema_version:
        return _reject(
            request,
            policy,
            execution_mode,
            RiskReasonCode.FEATURE_SCHEMA_UNSUPPORTED,
            "Fast Lane state version is not supported by risk policy",
        )
    if context.as_of_unix_ms != request.evaluated_at_unix_ms:
        return _reject(
            request,
            policy,
            execution_mode,
            RiskReasonCode.CONTEXT_AS_OF_MISMATCH,
            "risk context timestamp does not match Fast Lane risk evaluation time",
        )

    if execution_mode is RuntimeMode.OBSERVE:
        return _reject(
            request,
            policy,
            execution_mode,
            RiskReasonCode.OBSERVE_MODE_NO_INTENTS,
            "observe mode cannot create trade intents",
        )
    if execution_mode is RuntimeMode.HALTED:
        return _reject(
            request,
            policy,
            execution_mode,
            RiskReasonCode.HALTED_MODE,
            "halted mode cannot create trade intents",
        )
    if execution_mode is RuntimeMode.LIVE:
        return _reject(
            request,
            policy,
            execution_mode,
            RiskReasonCode.LIVE_MODE_DISABLED,
            "live trade-intent creation remains disabled",
        )

    checks = (
        (
            context.kill_switch_active,
            RiskReasonCode.KILL_SWITCH_ACTIVE,
            "global kill switch is active",
        ),
        (
            context.operator_entry_halt_active,
            RiskReasonCode.OPERATOR_ENTRY_HALT_ACTIVE,
            "operator entry halt is active",
        ),
    )
    for active, reason, message in checks:
        if active:
            return _reject(request, policy, execution_mode, reason, message)

    if context.data_healthy is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.DATA_HEALTH_UNKNOWN, "data health is unknown")
    if not context.data_healthy:
        return _reject(request, policy, execution_mode, RiskReasonCode.DATA_HEALTH_DEGRADED, "data health is degraded")
    if context.execution_healthy is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.EXECUTION_HEALTH_UNKNOWN, "execution health is unknown")
    if not context.execution_healthy:
        return _reject(request, policy, execution_mode, RiskReasonCode.EXECUTION_HEALTH_DEGRADED, "execution health is degraded")

    if context.trading_capital_usd is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.TRADING_CAPITAL_UNKNOWN, "trading capital is unknown")
    if context.trading_capital_usd <= 0.0:
        return _reject(request, policy, execution_mode, RiskReasonCode.TRADING_CAPITAL_NON_POSITIVE, "trading capital is not positive")
    if context.open_position_count is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.OPEN_POSITION_COUNT_UNKNOWN, "open position count is unknown")
    if context.open_position_count >= policy.max_simultaneous_positions:
        return _reject(request, policy, execution_mode, RiskReasonCode.MAX_POSITIONS_REACHED, "maximum simultaneous positions reached")
    if context.aggregate_open_risk_usd is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.AGGREGATE_OPEN_RISK_UNKNOWN, "aggregate open risk is unknown")
    if context.aggregate_open_risk_usd >= policy.max_aggregate_open_risk_usd:
        return _reject(request, policy, execution_mode, RiskReasonCode.AGGREGATE_RISK_LIMIT_REACHED, "aggregate open-risk limit reached")
    if context.daily_realized_pnl_usd is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.DAILY_REALIZED_PNL_UNKNOWN, "daily realized PnL is unknown")
    if context.daily_realized_pnl_usd <= -policy.max_daily_realized_loss_usd:
        return _reject(request, policy, execution_mode, RiskReasonCode.DAILY_LOSS_LIMIT_REACHED, "daily realized-loss limit reached")
    if context.rolling_drawdown_pct is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.ROLLING_DRAWDOWN_UNKNOWN, "rolling drawdown is unknown")
    if context.rolling_drawdown_pct >= policy.max_rolling_drawdown_pct:
        return _reject(request, policy, execution_mode, RiskReasonCode.ROLLING_DRAWDOWN_LIMIT_REACHED, "rolling drawdown limit reached")
    if context.consecutive_losses is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.CONSECUTIVE_LOSSES_UNKNOWN, "consecutive-loss count is unknown")

    if policy.cooldown_seconds > 0 and context.consecutive_losses >= policy.cooldown_after_consecutive_losses:
        if context.last_loss_at_unix_ms is None:
            return _reject(request, policy, execution_mode, RiskReasonCode.LOSS_COOLDOWN_TIME_UNKNOWN, "last-loss timestamp is required while cooldown applies")
        if context.last_loss_at_unix_ms > context.as_of_unix_ms:
            return _reject(request, policy, execution_mode, RiskReasonCode.LOSS_COOLDOWN_TIME_AFTER_AS_OF, "last-loss timestamp is after risk evaluation time")
        elapsed_ms = context.as_of_unix_ms - context.last_loss_at_unix_ms
        if elapsed_ms < policy.cooldown_seconds * 1_000:
            return _reject(request, policy, execution_mode, RiskReasonCode.LOSS_COOLDOWN_ACTIVE, "consecutive-loss cooldown is still active")

    if context.liquidity_usd is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.LIQUIDITY_UNKNOWN, "liquidity is unknown")
    if context.liquidity_usd < policy.min_liquidity_usd:
        return _reject(request, policy, execution_mode, RiskReasonCode.LIQUIDITY_BELOW_MINIMUM, "liquidity is below configured minimum")
    if context.expected_price_impact_pct is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.PRICE_IMPACT_UNKNOWN, "expected entry price impact is unknown")
    if context.price_impact_notional_usd is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.PRICE_IMPACT_NOTIONAL_UNKNOWN, "price-impact estimate notional is unknown")
    if context.price_impact_notional_usd < request.requested_notional_usd:
        return _reject(request, policy, execution_mode, RiskReasonCode.PRICE_IMPACT_NOTIONAL_TOO_SMALL, "price-impact estimate does not cover exact Fast Lane entry notional")
    if context.expected_price_impact_pct > policy.max_expected_price_impact_pct:
        return _reject(request, policy, execution_mode, RiskReasonCode.PRICE_IMPACT_TOO_HIGH, "expected entry price impact exceeds configured maximum")
    if context.market_data_age_ms is None:
        return _reject(request, policy, execution_mode, RiskReasonCode.MARKET_DATA_AGE_UNKNOWN, "market data age is unknown")
    if context.market_data_age_ms > policy.max_market_data_age_ms:
        return _reject(request, policy, execution_mode, RiskReasonCode.MARKET_DATA_TOO_OLD, "market data is older than configured maximum")

    risk_cap = _requested_notional_cap(context, policy)
    if request.requested_notional_usd > risk_cap and not math.isclose(
        request.requested_notional_usd,
        risk_cap,
        rel_tol=_ARITH_REL_TOL,
        abs_tol=_ARITH_ABS_TOL,
    ):
        return _reject(
            request,
            policy,
            execution_mode,
            FastEntryRiskReasonCode.REQUESTED_NOTIONAL_EXCEEDS_RISK_CAP,
            "exact Fast Lane entry notional exceeds current preserved risk cap",
        )

    idempotency_key = _entry_idempotency_key(request, execution_mode)
    if idempotency_key in context.active_intent_keys:
        return _reject(request, policy, execution_mode, RiskReasonCode.DUPLICATE_ACTIVE_INTENT, "an active intent already exists for this Fast Lane BUY")

    intent = TradeIntent(
        mint=request.mint,
        side=TradeSide.BUY,
        requested_notional_usd=request.requested_notional_usd,
        max_slippage_bps=policy.max_slippage_bps,
        strategy_name=request.strategy_name,
        strategy_version=request.strategy_version,
        score_policy_version=FAST_LANE_SCORE_POLICY_SENTINEL,
        decision_policy_version=request.action_assessment_version,
        risk_policy_version=policy.version,
        reason="FAST_LANE_BUY_RISK_APPROVED",
        idempotency_key=idempotency_key,
        execution_mode=execution_mode,
        as_of_unix_ms=request.decision_at_unix_ms,
    )
    return FastEntryRiskAssessment(
        policy_version=policy.version,
        mint=request.mint,
        source_event_id=request.source_event_id,
        decision_at_unix_ms=request.decision_at_unix_ms,
        evaluated_at_unix_ms=request.evaluated_at_unix_ms,
        state=RiskState.APPROVED,
        execution_mode=execution_mode,
        requested_notional_usd=request.requested_notional_usd,
        approved_notional_usd=request.requested_notional_usd,
        idempotency_key=idempotency_key,
        findings=(RiskFinding(RiskReasonCode.RISK_APPROVED, "all configured Fast Lane entry risk guardrails passed"),),
        intent=intent,
    )


def _requested_notional_cap(context: RiskContext, policy: RiskPolicy) -> float:
    assert context.trading_capital_usd is not None
    assert context.aggregate_open_risk_usd is not None
    capital_fraction_cap = context.trading_capital_usd * policy.max_capital_fraction_per_position
    remaining_aggregate_risk = policy.max_aggregate_open_risk_usd - context.aggregate_open_risk_usd
    return min(
        policy.target_position_notional_usd,
        policy.max_notional_per_position_usd,
        capital_fraction_cap,
        remaining_aggregate_risk,
    )


def _entry_idempotency_key(request: FastEntryRiskRequest, execution_mode: RuntimeMode) -> str:
    payload = "\n".join(
        (
            _FAST_LANE_RISK_KEY_VERSION,
            execution_mode.value,
            request.source_event_id,
            request.mint,
            str(request.decision_at_unix_ms),
            request.strategy_name,
            request.strategy_version,
            request.action_assessment_version,
            request.state_version,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reject(
    request: FastEntryRiskRequest,
    policy: RiskPolicy,
    execution_mode: RuntimeMode,
    reason: RiskReasonCode | FastEntryRiskReasonCode,
    message: str,
) -> FastEntryRiskAssessment:
    finding: RiskFinding | FastEntryRiskFinding
    if isinstance(reason, FastEntryRiskReasonCode):
        finding = FastEntryRiskFinding(reason, message)
    else:
        finding = RiskFinding(reason, message)
    return FastEntryRiskAssessment(
        policy_version=policy.version,
        mint=request.mint,
        source_event_id=request.source_event_id,
        decision_at_unix_ms=request.decision_at_unix_ms,
        evaluated_at_unix_ms=request.evaluated_at_unix_ms,
        state=RiskState.REJECTED,
        execution_mode=execution_mode,
        requested_notional_usd=request.requested_notional_usd,
        approved_notional_usd=None,
        idempotency_key=None,
        findings=(finding,),
        intent=None,
    )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and strictly positive")
