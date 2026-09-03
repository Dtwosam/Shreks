from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.exits import (
    ExitExecutionContext,
    ExitPolicy,
    ExitReasonCode,
    ExitRouteState,
    TakeProfitLevel,
)
from shreks_brain.fast_paper import (
    FAST_PAPER_POSITION_ACTION_VERSION,
    FAST_PAPER_PROTECTIVE_EXIT_VERSION,
    FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperEventOutcome,
    FastPaperMaterialUpdate,
    FastPaperPositionActionApproval,
    FastPaperPositionActionPolicy,
    FastPaperPositionOutcome,
    FastPaperPositionQuote,
    FastPaperProtectiveExitError,
    FastPaperProtectiveExitPolicy,
    apply_fast_paper_position_action,
    create_fast_paper_loop_state,
    create_fast_paper_position_action_state,
    create_fast_paper_protective_exit_state,
    run_fast_paper_protective_event,
)
from shreks_brain.features import FEATURE_SCHEMA_VERSION, FeatureVector
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerUpdateState,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
)
from shreks_brain.risk import FAST_LANE_SCORE_POLICY_SENTINEL, TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision


MINT = "mint-a"
QUOTE_MINT = "quote-a"
MARKET_KEY = "pump:mint-a:quote-a"
T0 = 1_000


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-fl7.6",
        assumed_latency_ms=0,
        max_quote_lag_ms=5_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
    )


def _open_ledger() -> PaperLedger:
    ledger = create_paper_ledger(10_000.0, T0)
    intent = TradeIntent(
        mint=MINT,
        side=TradeSide.BUY,
        requested_notional_usd=1_000.0,
        max_slippage_bps=500,
        strategy_name="fixture",
        strategy_version="1",
        score_policy_version=FAST_LANE_SCORE_POLICY_SENTINEL,
        decision_policy_version="assessment-v1",
        risk_policy_version="risk-v1",
        reason="open-position",
        idempotency_key="open-mint-a",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=T0,
    )
    quote = PaperQuote(
        provider="fixture",
        mint=MINT,
        observed_at_unix_ms=T0 + 100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=10.0,
        execution_price_usd=10.0,
        quoted_notional_usd=1_000.0,
        available_notional_usd=1_000.0,
    )
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=T0 + 100,
            processed_intent_keys=ledger.processed_intent_keys,
            quote=quote,
        ),
        _fill_policy(),
    )
    update = apply_paper_execution(ledger, intent, execution)
    assert update.state is PaperLedgerUpdateState.APPLIED
    return update.ledger


def _position(ledger: PaperLedger):
    open_positions = tuple(
        position for position in ledger.positions if position.state is PaperPositionState.OPEN
    )
    assert len(open_positions) == 1
    return open_positions[0]


def _c4_policy(**changes) -> ExitPolicy:
    policy = ExitPolicy(
        version="c4-protective-v1",
        required_feature_schema_version=FEATURE_SCHEMA_VERSION,
        max_market_data_age_ms=1_000,
        max_execution_evidence_age_ms=1_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(),
        trailing_activation_return_pct=20.0,
        trailing_stop_drawdown_pct=5.0,
        max_hold_seconds=3_600,
        flow_exit_max_buy_fraction_m5=None,
        flow_exit_max_buy_pressure_acceleration=None,
        momentum_exit_max_return_1m_pct=None,
        momentum_exit_max_return_5m_pct=None,
        min_liquidity_usd=5_000.0,
        max_exit_price_impact_pct=5.0,
        min_exit_capacity_fraction=0.5,
        wallet_distribution_enabled=False,
    )
    return replace(policy, **changes)


def _protective_policy(**c4_changes) -> FastPaperProtectiveExitPolicy:
    return FastPaperProtectiveExitPolicy(
        version="protective-v1",
        exit_policy=_c4_policy(**c4_changes),
    )


def _features(
    *,
    as_of: int = 1_200,
    price: float | None = 10.0,
    liquidity: float | None = 10_000.0,
    source_observed_at: int | None = None,
) -> FeatureVector:
    if source_observed_at is None:
        source_observed_at = as_of
    return FeatureVector(
        schema_version=FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source_observed_at,
        source_age_ms=max(0, as_of - source_observed_at),
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=10.0,
        price_usd=price,
        liquidity_usd=liquidity,
        liquidity_change_5m_pct=None,
        exit_price_impact_pct=None,
        volume_m5_usd=None,
        volume_h1_usd=None,
        volume_velocity_ratio=None,
        tx_count_m5=None,
        tx_count_h1=None,
        buy_fraction_m5=None,
        buy_fraction_h1=None,
        buy_sell_ratio_m5=None,
        buy_sell_ratio_h1=None,
        buy_pressure_acceleration=None,
        return_1m_pct=None,
        return_5m_pct=None,
        return_15m_pct=None,
        momentum_acceleration_1m_vs_5m=None,
        distance_from_local_high_pct=None,
        range_position_pct=None,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )


def _context(
    *,
    as_of: int = 1_200,
    observed_at: int | None = None,
    route_state: ExitRouteState = ExitRouteState.AVAILABLE,
    available_exit_notional_usd: float | None = 1_000.0,
    expected_exit_price_impact_pct: float | None = 1.0,
    price_impact_notional_usd: float | None = 1_000.0,
    global_halt_active: bool = False,
) -> ExitExecutionContext:
    if observed_at is None:
        observed_at = as_of
    return ExitExecutionContext(
        as_of_unix_ms=as_of,
        observed_at_unix_ms=observed_at,
        route_state=route_state,
        available_exit_notional_usd=available_exit_notional_usd,
        expected_exit_price_impact_pct=expected_exit_price_impact_pct,
        price_impact_notional_usd=price_impact_notional_usd,
        wallet_distribution_detected=None,
        global_halt_active=global_halt_active,
    )


def _update(
    *,
    event_id: str = "event-1",
    sequence: int = 1,
    as_of: int = 1_200,
    material: bool = True,
) -> FastPaperMaterialUpdate:
    return FastPaperMaterialUpdate(
        source_event_id=event_id,
        market_key=MARKET_KEY,
        source_sequence=sequence,
        as_of_unix_ms=as_of,
        state_version="fast-state-v1",
        is_material=material,
        material_reason="position-state-changed" if material else None,
    )


def _assessment(
    update: FastPaperMaterialUpdate,
    action: FastPaperAction,
    *,
    reasons: tuple[str, ...] = ("strategy-condition",),
) -> FastPaperActionAssessment:
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=update.source_event_id,
        market_key=update.market_key,
        source_sequence=update.source_sequence,
        as_of_unix_ms=update.as_of_unix_ms,
        strategy_family="longer-runner",
        strategy_version="1",
        action=action,
        reasons=reasons,
    )


def _approval(
    ledger: PaperLedger,
    update: FastPaperMaterialUpdate,
    action: FastPaperAction,
    *,
    target: float | None = None,
    reasons: tuple[str, ...] = ("strategy-condition",),
) -> FastPaperPositionActionApproval:
    position = _position(ledger)
    if action is FastPaperAction.REDUCE and target is None:
        target = position.quantity / 4.0
    if action is FastPaperAction.SELL and target is None:
        target = position.quantity
    return FastPaperPositionActionApproval(
        version=FAST_PAPER_POSITION_ACTION_VERSION,
        assessment=_assessment(update, action, reasons=reasons),
        position_id=position.position_id,
        mint=position.mint,
        quote_mint=QUOTE_MINT,
        state_version=update.state_version,
        target_base_quantity=target,
    )


def _run(
    *,
    ledger: PaperLedger,
    update: FastPaperMaterialUpdate,
    action: FastPaperAction = FastPaperAction.HOLD,
    target: float | None = None,
    features: FeatureVector | None = None,
    context: ExitExecutionContext | None = None,
    loop_state=None,
    protective_state=None,
    policy: FastPaperProtectiveExitPolicy | None = None,
    reasons: tuple[str, ...] = ("strategy-condition",),
):
    position = _position(ledger)
    if features is None:
        features = _features(as_of=update.as_of_unix_ms)
    if context is None:
        context = _context(as_of=update.as_of_unix_ms)
    if loop_state is None:
        loop_state = create_fast_paper_loop_state()
    if policy is None:
        policy = _protective_policy()
    if protective_state is None:
        protective_state = create_fast_paper_protective_exit_state(position, policy)

    original = _approval(
        ledger,
        update,
        action,
        target=target,
        reasons=reasons,
    )
    calls = {"count": 0}

    def evaluator(material_update: FastPaperMaterialUpdate):
        calls["count"] += 1
        assert material_update == update
        return original

    result = run_fast_paper_protective_event(
        state=loop_state,
        update=update,
        position=position,
        features=features,
        context=context,
        protective_state=protective_state,
        protective_policy=policy,
        strategy_evaluator=evaluator,
    )
    return result, original, calls


def test_fl7_6_public_versions_are_stable() -> None:
    assert FAST_PAPER_PROTECTIVE_EXIT_VERSION == "fl7.6-v1"
    assert FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY == "protective-risk"


def test_protective_policy_rejects_strategy_style_c4_rules() -> None:
    base = _c4_policy()
    forbidden = (
        replace(
            base,
            take_profit_levels=(TakeProfitLevel("tp1", 20.0, 0.5),),
        ),
        replace(base, wallet_distribution_enabled=True),
        replace(
            base,
            flow_exit_max_buy_fraction_m5=0.4,
            flow_exit_max_buy_pressure_acceleration=-0.1,
        ),
        replace(
            base,
            momentum_exit_max_return_1m_pct=-3.0,
            momentum_exit_max_return_5m_pct=-5.0,
        ),
    )
    for exit_policy in forbidden:
        with pytest.raises(ValueError, match="protective"):
            FastPaperProtectiveExitPolicy(
                version="protective-v1",
                exit_policy=exit_policy,
            )


def test_no_protective_trigger_preserves_strategy_hold_exactly() -> None:
    ledger = _open_ledger()
    update = _update()
    result, original, calls = _run(ledger=ledger, update=update)

    assert calls["count"] == 1
    assert result.event_result.outcome is FastPaperEventOutcome.ASSESSED
    assert result.strategy_approval is original
    assert result.applied_approval is original
    assert result.event_result.assessment is original.assessment
    assert result.protective_triggered is False
    assert result.protective_assessment is not None
    assert result.next_protective_state == result.protective_assessment.next_state


def test_no_protective_trigger_preserves_explicit_reduce_quantity() -> None:
    ledger = _open_ledger()
    update = _update()
    position = _position(ledger)
    target = position.quantity * 0.2
    result, original, _ = _run(
        ledger=ledger,
        update=update,
        action=FastPaperAction.REDUCE,
        target=target,
    )

    assert result.applied_approval is original
    assert result.applied_approval.target_base_quantity == target
    assert result.applied_approval.assessment.action is FastPaperAction.REDUCE


@pytest.mark.parametrize(
    ("features", "context", "policy", "expected_reason"),
    (
        (
            _features(price=8.9),
            _context(),
            _protective_policy(),
            ExitReasonCode.HARD_STOP_TRIGGERED,
        ),
        (
            _features(),
            _context(route_state=ExitRouteState.UNAVAILABLE),
            _protective_policy(),
            ExitReasonCode.LIQUIDITY_ROUTE_UNAVAILABLE,
        ),
        (
            _features(liquidity=4_000.0),
            _context(),
            _protective_policy(),
            ExitReasonCode.LIQUIDITY_BELOW_MINIMUM,
        ),
        (
            _features(),
            _context(expected_exit_price_impact_pct=6.0),
            _protective_policy(),
            ExitReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
        ),
        (
            _features(),
            _context(available_exit_notional_usd=400.0),
            _protective_policy(),
            ExitReasonCode.EXIT_CAPACITY_TOO_LOW,
        ),
    ),
)
def test_protective_risk_trigger_overrides_hold_with_full_sell(
    features: FeatureVector,
    context: ExitExecutionContext,
    policy: FastPaperProtectiveExitPolicy,
    expected_reason: ExitReasonCode,
) -> None:
    ledger = _open_ledger()
    update = _update(as_of=features.as_of_unix_ms)
    position = _position(ledger)
    result, original, _ = _run(
        ledger=ledger,
        update=update,
        features=features,
        context=context,
        policy=policy,
        reasons=("hold-for-continuation",),
    )

    assert result.protective_triggered is True
    assert result.strategy_approval is original
    assert result.applied_approval is not None
    assert result.applied_approval is not original
    assert result.applied_approval.target_base_quantity == position.quantity
    final = result.applied_approval.assessment
    assert final.action is FastPaperAction.SELL
    assert final.strategy_family == FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY
    assert final.strategy_version == policy.version
    assert final.reasons[0] == f"protective:{expected_reason.value}"
    assert "strategy_action:HOLD" in final.reasons
    assert "strategy:hold-for-continuation" in final.reasons
    assert result.event_result.assessment == final


def test_trailing_stop_overrides_strategy_reduce_after_high_water_update() -> None:
    ledger = _open_ledger()
    first_update = _update(event_id="event-high", sequence=1, as_of=1_200)
    first, _, _ = _run(
        ledger=ledger,
        update=first_update,
        features=_features(as_of=1_200, price=12.5),
        context=_context(as_of=1_200, available_exit_notional_usd=1_250.0),
    )
    assert first.protective_triggered is False
    assert first.next_protective_state.high_water_price_usd == 12.5

    second_update = _update(event_id="event-drawdown", sequence=2, as_of=1_300)
    second, strategy, _ = _run(
        ledger=ledger,
        update=second_update,
        action=FastPaperAction.REDUCE,
        target=_position(ledger).quantity * 0.25,
        features=_features(as_of=1_300, price=11.5),
        context=_context(as_of=1_300, available_exit_notional_usd=1_150.0),
        loop_state=first.event_result.next_state,
        protective_state=first.next_protective_state,
    )

    assert strategy.assessment.action is FastPaperAction.REDUCE
    assert second.protective_triggered is True
    assert second.applied_approval is not None
    assert second.applied_approval.assessment.action is FastPaperAction.SELL
    assert second.applied_approval.assessment.reasons[0] == (
        "protective:TRAILING_STOP_TRIGGERED"
    )


def test_max_hold_forces_sell_even_when_ordinary_evidence_is_stale() -> None:
    ledger = _open_ledger()
    update = _update(as_of=2_500)
    policy = _protective_policy(
        max_hold_seconds=1,
        max_market_data_age_ms=10,
        max_execution_evidence_age_ms=10,
    )
    result, _, _ = _run(
        ledger=ledger,
        update=update,
        features=_features(as_of=2_500, source_observed_at=1_000),
        context=_context(as_of=2_500, observed_at=1_000),
        policy=policy,
    )

    assert result.protective_triggered is True
    assert result.applied_approval is not None
    assert result.applied_approval.assessment.reasons[0] == "protective:MAX_HOLD_EXIT"


def test_global_halt_forces_sell_even_when_ordinary_evidence_is_stale() -> None:
    ledger = _open_ledger()
    update = _update(as_of=1_500)
    policy = _protective_policy(
        max_market_data_age_ms=10,
        max_execution_evidence_age_ms=10,
    )
    result, _, _ = _run(
        ledger=ledger,
        update=update,
        features=_features(as_of=1_500, source_observed_at=1_000),
        context=_context(
            as_of=1_500,
            observed_at=1_000,
            global_halt_active=True,
        ),
        policy=policy,
    )

    assert result.protective_triggered is True
    assert result.applied_approval is not None
    assert result.applied_approval.assessment.reasons[0] == "protective:GLOBAL_HALT_EXIT"


def test_c4_precedence_and_reason_order_are_preserved() -> None:
    ledger = _open_ledger()
    update = _update(as_of=2_500)
    result, _, _ = _run(
        ledger=ledger,
        update=update,
        features=_features(as_of=2_500, price=8.0, liquidity=4_000.0),
        context=_context(
            as_of=2_500,
            route_state=ExitRouteState.UNAVAILABLE,
            available_exit_notional_usd=200.0,
            expected_exit_price_impact_pct=8.0,
            global_halt_active=True,
        ),
        policy=_protective_policy(max_hold_seconds=1),
        reasons=("original-a", "original-b"),
    )

    assert result.protective_assessment is not None
    assert result.protective_assessment.primary_reason is ExitReasonCode.GLOBAL_HALT_EXIT
    assert result.applied_approval is not None
    reasons = result.applied_approval.assessment.reasons
    assert reasons[0] == "protective:GLOBAL_HALT_EXIT"
    assert reasons.index("protective:MAX_HOLD_EXIT") < reasons.index(
        "protective:LIQUIDITY_ROUTE_UNAVAILABLE"
    )
    assert reasons.index("protective:LIQUIDITY_ROUTE_UNAVAILABLE") < reasons.index(
        "protective:HARD_STOP_TRIGGERED"
    )
    assert reasons[-3:] == (
        "strategy_action:HOLD",
        "strategy:original-a",
        "strategy:original-b",
    )


def test_non_material_update_does_not_invoke_strategy_or_move_protective_state() -> None:
    ledger = _open_ledger()
    update = _update(material=False)
    position = _position(ledger)
    policy = _protective_policy()
    protective_state = create_fast_paper_protective_exit_state(position, policy)
    calls = {"count": 0}

    def evaluator(_: FastPaperMaterialUpdate):
        calls["count"] += 1
        return _approval(ledger, _update(), FastPaperAction.HOLD)

    result = run_fast_paper_protective_event(
        state=create_fast_paper_loop_state(),
        update=update,
        position=position,
        features=_features(),
        context=_context(),
        protective_state=protective_state,
        protective_policy=policy,
        strategy_evaluator=evaluator,
    )

    assert calls["count"] == 0
    assert result.event_result.outcome is FastPaperEventOutcome.IGNORED_NON_MATERIAL
    assert result.strategy_approval is None
    assert result.applied_approval is None
    assert result.protective_assessment is None
    assert result.next_protective_state is protective_state
    assert result.protective_triggered is False


def test_exact_replay_does_not_reinvoke_strategy_or_move_protective_state() -> None:
    ledger = _open_ledger()
    update = _update()
    position = _position(ledger)
    policy = _protective_policy()
    initial_state = create_fast_paper_protective_exit_state(position, policy)
    calls = {"count": 0}

    def evaluator(material_update: FastPaperMaterialUpdate):
        calls["count"] += 1
        return _approval(ledger, material_update, FastPaperAction.HOLD)

    first = run_fast_paper_protective_event(
        state=create_fast_paper_loop_state(),
        update=update,
        position=position,
        features=_features(price=12.0),
        context=_context(available_exit_notional_usd=1_200.0),
        protective_state=initial_state,
        protective_policy=policy,
        strategy_evaluator=evaluator,
    )
    assert calls["count"] == 1

    replay = run_fast_paper_protective_event(
        state=first.event_result.next_state,
        update=update,
        position=position,
        features=_features(price=8.0),
        context=_context(),
        protective_state=first.next_protective_state,
        protective_policy=policy,
        strategy_evaluator=evaluator,
    )

    assert calls["count"] == 1
    assert replay.event_result.outcome is FastPaperEventOutcome.REPLAYED
    assert replay.strategy_approval is None
    assert replay.applied_approval is None
    assert replay.protective_assessment is None
    assert replay.next_protective_state is first.next_protective_state
    assert replay.protective_triggered is False


def test_strategy_approval_must_match_triggering_update_before_override() -> None:
    ledger = _open_ledger()
    update = _update()
    position = _position(ledger)
    policy = _protective_policy()
    protective_state = create_fast_paper_protective_exit_state(position, policy)
    wrong_update = _update(event_id="wrong-event")

    def evaluator(_: FastPaperMaterialUpdate):
        return _approval(ledger, wrong_update, FastPaperAction.HOLD)

    with pytest.raises(FastPaperProtectiveExitError, match="source_event_id"):
        run_fast_paper_protective_event(
            state=create_fast_paper_loop_state(),
            update=update,
            position=position,
            features=_features(price=8.0),
            context=_context(),
            protective_state=protective_state,
            protective_policy=policy,
            strategy_evaluator=evaluator,
        )


def test_protective_evidence_clock_must_match_triggering_update() -> None:
    ledger = _open_ledger()
    update = _update(as_of=1_200)
    position = _position(ledger)
    policy = _protective_policy()
    protective_state = create_fast_paper_protective_exit_state(position, policy)

    with pytest.raises(FastPaperProtectiveExitError, match="FeatureVector"):
        run_fast_paper_protective_event(
            state=create_fast_paper_loop_state(),
            update=update,
            position=position,
            features=_features(as_of=1_201),
            context=_context(as_of=1_200),
            protective_state=protective_state,
            protective_policy=policy,
            strategy_evaluator=lambda material_update: _approval(
                ledger,
                material_update,
                FastPaperAction.HOLD,
            ),
        )


def test_protective_result_never_creates_buy_or_skip_for_open_position() -> None:
    ledger = _open_ledger()
    for price in (10.0, 8.0):
        update = _update(event_id=f"event-{price}")
        result, _, _ = _run(
            ledger=ledger,
            update=update,
            features=_features(price=price),
        )
        assert result.event_result.assessment is not None
        assert result.event_result.assessment.action in (
            FastPaperAction.HOLD,
            FastPaperAction.REDUCE,
            FastPaperAction.SELL,
        )


def test_protective_sell_approval_executes_directly_through_fl7_4_c1_c3() -> None:
    ledger = _open_ledger()
    update = _update(as_of=1_200)
    protected, _, _ = _run(
        ledger=ledger,
        update=update,
        features=_features(as_of=1_200, price=8.5),
        context=_context(as_of=1_200, available_exit_notional_usd=850.0),
    )
    approval = protected.applied_approval
    assert approval is not None
    assert approval.assessment.action is FastPaperAction.SELL

    position = _position(ledger)
    state = create_fast_paper_position_action_state(
        position.position_id,
        ledger.as_of_unix_ms,
    )
    result = apply_fast_paper_position_action(
        state=state,
        approval=approval,
        ledger=ledger,
        quote=FastPaperPositionQuote(
            provider="fixture",
            mint=MINT,
            quote_mint=QUOTE_MINT,
            observed_at_unix_ms=1_200,
            state=PaperQuoteState.EXECUTABLE,
            reference_price_quote=8.5,
            execution_price_quote=8.5,
            quoted_base_quantity=position.quantity,
            available_base_quantity=position.quantity,
            quote_to_usd_rate=1.0,
        ),
        fill_policy=_fill_policy(),
        policy=FastPaperPositionActionPolicy(
            version="fl7.4-policy-v1",
            max_slippage_bps=500,
        ),
        evaluated_at_unix_ms=1_200,
    )

    assert result.outcome is FastPaperPositionOutcome.SOLD
    closed = next(
        item for item in result.next_ledger.positions if item.position_id == position.position_id
    )
    assert closed.state is PaperPositionState.CLOSED
