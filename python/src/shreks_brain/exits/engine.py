from __future__ import annotations

from dataclasses import replace
import math

from shreks_brain.decision import DecisionAction
from shreks_brain.exits.models import (
    ExitAssessment,
    ExitExecutionContext,
    ExitFinding,
    ExitPolicy,
    ExitReasonCode,
    ExitRouteState,
    ExitState,
    TakeProfitLevel,
)
from shreks_brain.features import FeatureVector
from shreks_brain.paper import PaperPosition, PaperPositionState


_COMPARE_ABS_TOL = 1e-12

_TRIGGER_PRECEDENCE = (
    ExitReasonCode.GLOBAL_HALT_EXIT,
    ExitReasonCode.MAX_HOLD_EXIT,
    ExitReasonCode.LIQUIDITY_ROUTE_UNAVAILABLE,
    ExitReasonCode.LIQUIDITY_BELOW_MINIMUM,
    ExitReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
    ExitReasonCode.EXIT_CAPACITY_TOO_LOW,
    ExitReasonCode.HARD_STOP_TRIGGERED,
    ExitReasonCode.TRAILING_STOP_TRIGGERED,
    ExitReasonCode.WALLET_DISTRIBUTION_TRIGGERED,
    ExitReasonCode.FLOW_DETERIORATION_TRIGGERED,
    ExitReasonCode.MOMENTUM_DETERIORATION_TRIGGERED,
    ExitReasonCode.TAKE_PROFIT_TRIGGERED,
)


def create_exit_state(position: PaperPosition, policy: ExitPolicy) -> ExitState:
    """Initialize immutable C4 state from authoritative C3 position evidence."""

    if position.state is not PaperPositionState.OPEN:
        raise ValueError("create_exit_state requires an OPEN position")

    high_water_price = position.weighted_entry_price_usd
    high_water_at = position.opened_at_unix_ms
    if (
        position.last_mark_price_usd is not None
        and position.last_mark_at_unix_ms is not None
        and position.last_mark_price_usd > high_water_price
    ):
        high_water_price = position.last_mark_price_usd
        high_water_at = position.last_mark_at_unix_ms

    return ExitState(
        policy_version=policy.version,
        position_id=position.position_id,
        mint=position.mint,
        initialized_at_unix_ms=position.opened_at_unix_ms,
        last_evaluated_at_unix_ms=position.updated_at_unix_ms,
        high_water_price_usd=high_water_price,
        high_water_at_unix_ms=high_water_at,
        completed_take_profit_levels=frozenset(),
    )


def assess_exit(
    position: PaperPosition,
    features: FeatureVector,
    context: ExitExecutionContext,
    state: ExitState,
    policy: ExitPolicy,
) -> ExitAssessment:
    """Return one deterministic HOLD/REDUCE/EXIT assessment without execution."""

    structural = _structural_gate(position, features, context, state, policy)
    if structural is not None:
        reason, position_age = structural
        return _hold(
            position,
            features,
            state,
            policy,
            reason,
            position_age_seconds=position_age,
        )

    as_of = features.as_of_unix_ms
    position_age_seconds = (as_of - position.opened_at_unix_ms) / 1000.0

    forced: dict[ExitReasonCode, ExitFinding] = {}
    if context.global_halt_active:
        forced[ExitReasonCode.GLOBAL_HALT_EXIT] = _finding(
            ExitReasonCode.GLOBAL_HALT_EXIT,
            observed_value="active",
        )
    if (
        policy.max_hold_seconds is not None
        and _at_least(position_age_seconds, float(policy.max_hold_seconds))
    ):
        forced[ExitReasonCode.MAX_HOLD_EXIT] = _finding(
            ExitReasonCode.MAX_HOLD_EXIT,
            observed_value=position_age_seconds,
            threshold_value=policy.max_hold_seconds,
        )

    evidence_failure = _evidence_quality_gate(features, context, policy)
    if evidence_failure is not None:
        if forced:
            findings = _ordered_findings(forced)
            primary = findings[0].code
            return _assessment(
                position=position,
                features=features,
                policy=policy,
                state=_advance_time(state, as_of),
                action=DecisionAction.EXIT,
                primary=primary,
                findings=_mark_primary(findings, primary),
                target_fraction=1.0,
                target_quantity=position.quantity,
                position_age_seconds=position_age_seconds,
            )
        return _hold(
            position,
            features,
            state,
            policy,
            evidence_failure,
            position_age_seconds=position_age_seconds,
        )

    current_price = features.price_usd
    assert current_price is not None and current_price > 0.0

    current_market_value = position.quantity * current_price
    price_return_pct = (
        current_price / position.weighted_entry_price_usd - 1.0
    ) * 100.0

    if current_price > state.high_water_price_usd:
        next_state = replace(
            state,
            last_evaluated_at_unix_ms=as_of,
            high_water_price_usd=current_price,
            high_water_at_unix_ms=as_of,
        )
    else:
        next_state = replace(state, last_evaluated_at_unix_ms=as_of)

    drawdown_pct = (
        current_price / next_state.high_water_price_usd - 1.0
    ) * 100.0
    capacity_fraction = _capacity_fraction(
        context.available_exit_notional_usd,
        current_market_value,
    )

    triggers = dict(forced)

    if context.route_state is ExitRouteState.UNAVAILABLE:
        triggers[ExitReasonCode.LIQUIDITY_ROUTE_UNAVAILABLE] = _finding(
            ExitReasonCode.LIQUIDITY_ROUTE_UNAVAILABLE,
            observed_value=context.route_state.value,
        )

    if (
        policy.min_liquidity_usd is not None
        and features.liquidity_usd is not None
        and _at_most(features.liquidity_usd, policy.min_liquidity_usd)
    ):
        triggers[ExitReasonCode.LIQUIDITY_BELOW_MINIMUM] = _finding(
            ExitReasonCode.LIQUIDITY_BELOW_MINIMUM,
            observed_value=features.liquidity_usd,
            threshold_value=policy.min_liquidity_usd,
        )

    if (
        policy.max_exit_price_impact_pct is not None
        and context.expected_exit_price_impact_pct is not None
        and _at_least(
            context.expected_exit_price_impact_pct,
            policy.max_exit_price_impact_pct,
        )
    ):
        triggers[ExitReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH] = _finding(
            ExitReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
            observed_value=context.expected_exit_price_impact_pct,
            threshold_value=policy.max_exit_price_impact_pct,
        )

    if (
        policy.min_exit_capacity_fraction is not None
        and capacity_fraction is not None
        and _at_most(capacity_fraction, policy.min_exit_capacity_fraction)
    ):
        triggers[ExitReasonCode.EXIT_CAPACITY_TOO_LOW] = _finding(
            ExitReasonCode.EXIT_CAPACITY_TOO_LOW,
            observed_value=capacity_fraction,
            threshold_value=policy.min_exit_capacity_fraction,
        )

    if (
        policy.hard_stop_loss_pct is not None
        and _at_most(price_return_pct, -policy.hard_stop_loss_pct)
    ):
        triggers[ExitReasonCode.HARD_STOP_TRIGGERED] = _finding(
            ExitReasonCode.HARD_STOP_TRIGGERED,
            observed_value=price_return_pct,
            threshold_value=-policy.hard_stop_loss_pct,
        )

    if (
        policy.trailing_activation_return_pct is not None
        and policy.trailing_stop_drawdown_pct is not None
    ):
        high_water_return_pct = (
            next_state.high_water_price_usd / position.weighted_entry_price_usd - 1.0
        ) * 100.0
        if (
            _at_least(high_water_return_pct, policy.trailing_activation_return_pct)
            and _at_most(drawdown_pct, -policy.trailing_stop_drawdown_pct)
        ):
            triggers[ExitReasonCode.TRAILING_STOP_TRIGGERED] = _finding(
                ExitReasonCode.TRAILING_STOP_TRIGGERED,
                observed_value=drawdown_pct,
                threshold_value=-policy.trailing_stop_drawdown_pct,
            )

    if policy.wallet_distribution_enabled and context.wallet_distribution_detected is True:
        triggers[ExitReasonCode.WALLET_DISTRIBUTION_TRIGGERED] = _finding(
            ExitReasonCode.WALLET_DISTRIBUTION_TRIGGERED,
            observed_value="detected",
        )

    if (
        policy.flow_exit_max_buy_fraction_m5 is not None
        and policy.flow_exit_max_buy_pressure_acceleration is not None
        and features.buy_fraction_m5 is not None
        and features.buy_pressure_acceleration is not None
        and _at_most(
            features.buy_fraction_m5,
            policy.flow_exit_max_buy_fraction_m5,
        )
        and _at_most(
            features.buy_pressure_acceleration,
            policy.flow_exit_max_buy_pressure_acceleration,
        )
    ):
        triggers[ExitReasonCode.FLOW_DETERIORATION_TRIGGERED] = _finding(
            ExitReasonCode.FLOW_DETERIORATION_TRIGGERED,
            observed_value=features.buy_fraction_m5,
            threshold_value=policy.flow_exit_max_buy_fraction_m5,
        )

    if (
        policy.momentum_exit_max_return_1m_pct is not None
        and policy.momentum_exit_max_return_5m_pct is not None
        and features.return_1m_pct is not None
        and features.return_5m_pct is not None
        and _at_most(
            features.return_1m_pct,
            policy.momentum_exit_max_return_1m_pct,
        )
        and _at_most(
            features.return_5m_pct,
            policy.momentum_exit_max_return_5m_pct,
        )
    ):
        triggers[ExitReasonCode.MOMENTUM_DETERIORATION_TRIGGERED] = _finding(
            ExitReasonCode.MOMENTUM_DETERIORATION_TRIGGERED,
            observed_value=features.return_1m_pct,
            threshold_value=policy.momentum_exit_max_return_1m_pct,
        )

    take_profit = _triggered_take_profit(
        policy.take_profit_levels,
        state.completed_take_profit_levels,
        price_return_pct,
    )
    if take_profit is not None:
        triggers[ExitReasonCode.TAKE_PROFIT_TRIGGERED] = _finding(
            ExitReasonCode.TAKE_PROFIT_TRIGGERED,
            observed_value=price_return_pct,
            threshold_value=take_profit.trigger_return_pct,
        )

    if not triggers:
        return _assessment(
            position=position,
            features=features,
            policy=policy,
            state=next_state,
            action=DecisionAction.HOLD,
            primary=ExitReasonCode.NO_EXIT_TRIGGERED,
            findings=(_finding(ExitReasonCode.NO_EXIT_TRIGGERED, primary=True),),
            target_fraction=0.0,
            target_quantity=0.0,
            position_age_seconds=position_age_seconds,
            current_price=current_price,
            current_market_value=current_market_value,
            price_return_pct=price_return_pct,
            drawdown_pct=drawdown_pct,
            capacity_fraction=capacity_fraction,
        )

    ordered = _ordered_findings(triggers)
    primary = ordered[0].code
    findings = _mark_primary(ordered, primary)

    if primary is ExitReasonCode.TAKE_PROFIT_TRIGGERED:
        assert take_profit is not None
        fraction = take_profit.reduce_fraction_of_current_quantity
        action = DecisionAction.EXIT if _close(fraction, 1.0) else DecisionAction.REDUCE
        quantity = position.quantity * fraction
    else:
        fraction = 1.0
        action = DecisionAction.EXIT
        quantity = position.quantity

    return _assessment(
        position=position,
        features=features,
        policy=policy,
        state=next_state,
        action=action,
        primary=primary,
        findings=findings,
        target_fraction=fraction,
        target_quantity=quantity,
        position_age_seconds=position_age_seconds,
        current_price=current_price,
        current_market_value=current_market_value,
        price_return_pct=price_return_pct,
        drawdown_pct=drawdown_pct,
        capacity_fraction=capacity_fraction,
        triggered_take_profit_level=take_profit.name if take_profit is not None else None,
    )


def acknowledge_exit_fill(
    state: ExitState,
    decision: ExitAssessment,
    before_position: PaperPosition,
    after_position: PaperPosition,
) -> ExitState:
    """Advance a take-profit level only after C3 proves enough quantity was sold."""

    if state.position_id != decision.position_id:
        raise ValueError("state position_id must match decision")
    if state.mint != decision.mint:
        raise ValueError("state mint must match decision")
    if state.policy_version != decision.policy_version:
        raise ValueError("state policy_version must match decision policy")
    if before_position.position_id != decision.position_id:
        raise ValueError("before position_id must match decision")
    if after_position.position_id != decision.position_id:
        raise ValueError("after position_id must match decision")
    if before_position.mint != decision.mint or after_position.mint != decision.mint:
        raise ValueError("before/after mint must match decision mint")
    if before_position.state is not PaperPositionState.OPEN:
        raise ValueError("before position must be OPEN")
    if after_position.quantity > before_position.quantity and not _close(
        after_position.quantity, before_position.quantity
    ):
        raise ValueError("after quantity cannot increase during exit acknowledgement")

    if (
        decision.primary_reason is not ExitReasonCode.TAKE_PROFIT_TRIGGERED
        or decision.action is DecisionAction.HOLD
    ):
        return state

    level = decision.triggered_take_profit_level
    if level is None:
        raise ValueError("take-profit decision requires triggered_take_profit_level")
    if level in state.completed_take_profit_levels:
        return state

    actual_reduction = before_position.quantity - after_position.quantity
    completed = after_position.state is PaperPositionState.CLOSED or _at_least(
        actual_reduction,
        decision.target_quantity,
    )
    if not completed:
        return state

    return replace(
        state,
        completed_take_profit_levels=(
            state.completed_take_profit_levels | frozenset({level})
        ),
    )


def _structural_gate(
    position: PaperPosition,
    features: FeatureVector,
    context: ExitExecutionContext,
    state: ExitState,
    policy: ExitPolicy,
) -> tuple[ExitReasonCode, float | None] | None:
    if features.schema_version != policy.required_feature_schema_version:
        return ExitReasonCode.FEATURE_SCHEMA_MISMATCH, _position_age(features, position)
    if position.state is not PaperPositionState.OPEN:
        return ExitReasonCode.POSITION_NOT_OPEN, _position_age(features, position)
    if state.position_id != position.position_id:
        return ExitReasonCode.STATE_POSITION_MISMATCH, _position_age(features, position)
    if state.mint != position.mint:
        return ExitReasonCode.STATE_MINT_MISMATCH, _position_age(features, position)
    if state.policy_version != policy.version:
        return ExitReasonCode.STATE_POLICY_MISMATCH, _position_age(features, position)
    if features.as_of_unix_ms != context.as_of_unix_ms:
        return ExitReasonCode.AS_OF_MISMATCH, _position_age(features, position)
    as_of = features.as_of_unix_ms
    if as_of < position.opened_at_unix_ms or as_of < state.initialized_at_unix_ms:
        return ExitReasonCode.CONTEXT_BEFORE_POSITION, None
    if state.last_evaluated_at_unix_ms > as_of or state.high_water_at_unix_ms > as_of:
        return ExitReasonCode.STATE_AFTER_AS_OF, _position_age(features, position)
    return None


def _evidence_quality_gate(
    features: FeatureVector,
    context: ExitExecutionContext,
    policy: ExitPolicy,
) -> ExitReasonCode | None:
    as_of = features.as_of_unix_ms
    if features.source_observed_at_unix_ms > as_of:
        return ExitReasonCode.MARKET_SOURCE_AFTER_AS_OF
    if as_of - features.source_observed_at_unix_ms > policy.max_market_data_age_ms:
        return ExitReasonCode.MARKET_SOURCE_TOO_OLD
    if context.observed_at_unix_ms > as_of:
        return ExitReasonCode.EXECUTION_EVIDENCE_AFTER_AS_OF
    if as_of - context.observed_at_unix_ms > policy.max_execution_evidence_age_ms:
        return ExitReasonCode.EXECUTION_EVIDENCE_TOO_OLD
    if features.price_usd is None or features.price_usd <= 0.0:
        return ExitReasonCode.CURRENT_PRICE_UNAVAILABLE
    return None


def _position_age(features: FeatureVector, position: PaperPosition) -> float | None:
    if features.as_of_unix_ms < position.opened_at_unix_ms:
        return None
    return (features.as_of_unix_ms - position.opened_at_unix_ms) / 1000.0


def _capacity_fraction(
    available_exit_notional_usd: float | None,
    current_market_value_usd: float,
) -> float | None:
    if available_exit_notional_usd is None or current_market_value_usd <= 0.0:
        return None
    return min(1.0, available_exit_notional_usd / current_market_value_usd)


def _triggered_take_profit(
    levels: tuple[TakeProfitLevel, ...],
    completed: frozenset[str],
    price_return_pct: float,
) -> TakeProfitLevel | None:
    for level in levels:
        if level.name in completed:
            continue
        if _at_least(price_return_pct, level.trigger_return_pct):
            return level
        break
    return None


def _hold(
    position: PaperPosition,
    features: FeatureVector,
    state: ExitState,
    policy: ExitPolicy,
    reason: ExitReasonCode,
    *,
    position_age_seconds: float | None,
) -> ExitAssessment:
    return _assessment(
        position=position,
        features=features,
        policy=policy,
        state=state,
        action=DecisionAction.HOLD,
        primary=reason,
        findings=(_finding(reason, primary=True),),
        target_fraction=0.0,
        target_quantity=0.0,
        position_age_seconds=position_age_seconds,
    )


def _assessment(
    *,
    position: PaperPosition,
    features: FeatureVector,
    policy: ExitPolicy,
    state: ExitState,
    action: DecisionAction,
    primary: ExitReasonCode,
    findings: tuple[ExitFinding, ...],
    target_fraction: float,
    target_quantity: float,
    position_age_seconds: float | None,
    current_price: float | None = None,
    current_market_value: float | None = None,
    price_return_pct: float | None = None,
    drawdown_pct: float | None = None,
    capacity_fraction: float | None = None,
    triggered_take_profit_level: str | None = None,
) -> ExitAssessment:
    return ExitAssessment(
        policy_version=policy.version,
        feature_schema_version=features.schema_version,
        position_id=position.position_id,
        mint=position.mint,
        as_of_unix_ms=features.as_of_unix_ms,
        action=action,
        primary_reason=primary,
        target_reduction_fraction=target_fraction,
        target_quantity=target_quantity,
        position_age_seconds=position_age_seconds,
        current_price_usd=current_price,
        current_market_value_usd=current_market_value,
        price_return_pct=price_return_pct,
        drawdown_from_high_water_pct=drawdown_pct,
        exit_capacity_fraction=capacity_fraction,
        triggered_take_profit_level=triggered_take_profit_level,
        next_state=state,
        findings=findings,
    )


def _advance_time(state: ExitState, as_of_unix_ms: int) -> ExitState:
    if as_of_unix_ms <= state.last_evaluated_at_unix_ms:
        return state
    return replace(state, last_evaluated_at_unix_ms=as_of_unix_ms)


def _finding(
    code: ExitReasonCode,
    *,
    primary: bool = False,
    observed_value: float | int | str | None = None,
    threshold_value: float | int | None = None,
) -> ExitFinding:
    return ExitFinding(
        code=code,
        message=code.value.replace("_", " ").lower(),
        primary=primary,
        observed_value=observed_value,
        threshold_value=threshold_value,
    )


def _ordered_findings(
    triggers: dict[ExitReasonCode, ExitFinding],
) -> tuple[ExitFinding, ...]:
    return tuple(triggers[code] for code in _TRIGGER_PRECEDENCE if code in triggers)


def _mark_primary(
    findings: tuple[ExitFinding, ...],
    primary: ExitReasonCode,
) -> tuple[ExitFinding, ...]:
    return tuple(replace(finding, primary=finding.code is primary) for finding in findings)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=_COMPARE_ABS_TOL)


def _at_most(value: float, threshold: float) -> bool:
    return value < threshold or _close(value, threshold)


def _at_least(value: float, threshold: float) -> bool:
    return value > threshold or _close(value, threshold)
