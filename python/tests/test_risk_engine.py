from dataclasses import replace

import pytest

from shreks_brain.decision import (
    DecisionAction,
    DecisionFinding,
    DecisionReasonCode,
    TradeDecision,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk.engine import assess_entry_risk
from shreks_brain.risk.models import (
    RiskContext,
    RiskPolicy,
    RiskReasonCode,
    RiskState,
    TradeSide,
)
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import SetupState


def _decision() -> TradeDecision:
    return TradeDecision(
        policy_version="decision-v1-test",
        mint="Mint111",
        as_of_unix_ms=1_000_000,
        action=DecisionAction.ENTER,
        score_policy_version="score-v1-test",
        feature_schema_version="b2-v1",
        safety_decision=SafetyDecision.PASS,
        setup_name="fresh_launch_continuation",
        setup_policy_version="fresh-test",
        setup_state=SetupState.READY,
        market_regime=MarketRegime.NORMAL,
        total_score=80.0,
        required_score_threshold=75.0,
        findings=(
            DecisionFinding(
                code=DecisionReasonCode.ENTRY_APPROVED,
                message="entry threshold passed",
            ),
        ),
    )


def _policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-v1-test",
        required_decision_policy_version="decision-v1-test",
        required_feature_schema_version="b2-v1",
        target_position_notional_usd=500.0,
        max_notional_per_position_usd=1_000.0,
        max_capital_fraction_per_position=0.10,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=3_000.0,
        max_daily_realized_loss_usd=500.0,
        max_rolling_drawdown_pct=20.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=300,
        min_liquidity_usd=50_000.0,
        max_expected_price_impact_pct=5.0,
        max_slippage_bps=300,
        max_market_data_age_ms=30_000,
    )


def _context() -> RiskContext:
    return RiskContext(
        as_of_unix_ms=1_000_000,
        trading_capital_usd=10_000.0,
        open_position_count=1,
        aggregate_open_risk_usd=1_000.0,
        daily_realized_pnl_usd=-100.0,
        rolling_drawdown_pct=5.0,
        consecutive_losses=1,
        last_loss_at_unix_ms=900_000,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=2.0,
        price_impact_notional_usd=5_000.0,
        market_data_age_ms=5_000,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _assess(
    *,
    decision: TradeDecision | None = None,
    context: RiskContext | None = None,
    policy: RiskPolicy | None = None,
    mode: RuntimeMode = RuntimeMode.PAPER,
):
    return assess_entry_risk(
        decision or _decision(),
        context or _context(),
        policy or _policy(),
        mode,
    )


def _assert_rejected(result, reason: RiskReasonCode) -> None:
    assert result.state is RiskState.REJECTED
    assert result.requested_notional_usd is None
    assert result.idempotency_key is None
    assert result.intent is None
    assert tuple(f.code for f in result.findings) == (reason,)


def test_canonical_paper_entry_is_risk_approved_at_target_size() -> None:
    result = _assess()

    assert result.state is RiskState.APPROVED
    assert result.requested_notional_usd == 500.0
    assert result.intent is not None
    assert result.intent.requested_notional_usd == 500.0
    assert result.intent.side is TradeSide.BUY
    assert tuple(f.code for f in result.findings) == (RiskReasonCode.RISK_APPROVED,)


@pytest.mark.parametrize(
    ("decision", "context", "policy", "mode", "reason"),
    (
        (
            replace(_decision(), policy_version="other-decision"),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.DECISION_POLICY_MISMATCH,
        ),
        (
            replace(_decision(), feature_schema_version="other-schema"),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.FEATURE_SCHEMA_UNSUPPORTED,
        ),
        (
            replace(_decision(), action=DecisionAction.WATCH),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.DECISION_NOT_ENTER,
        ),
        (
            replace(_decision(), safety_decision=SafetyDecision.REJECT),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.SAFETY_NOT_PASS,
        ),
        (
            replace(_decision(), safety_decision=SafetyDecision.INCOMPLETE),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.SAFETY_NOT_PASS,
        ),
        (
            replace(_decision(), setup_state=SetupState.WATCH),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.SETUP_NOT_READY,
        ),
        (
            replace(_decision(), setup_state=SetupState.BLOCKED),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.SETUP_NOT_READY,
        ),
        (
            replace(_decision(), market_regime=MarketRegime.DEAD),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.REGIME_DEAD,
        ),
        (
            replace(_decision(), total_score=None),
            _context(),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.TOTAL_SCORE_UNAVAILABLE,
        ),
        (
            _decision(),
            replace(_context(), as_of_unix_ms=999_999),
            _policy(),
            RuntimeMode.PAPER,
            RiskReasonCode.CONTEXT_AS_OF_MISMATCH,
        ),
        (
            _decision(),
            _context(),
            _policy(),
            RuntimeMode.OBSERVE,
            RiskReasonCode.OBSERVE_MODE_NO_INTENTS,
        ),
        (
            _decision(),
            _context(),
            _policy(),
            RuntimeMode.HALTED,
            RiskReasonCode.HALTED_MODE,
        ),
        (
            _decision(),
            _context(),
            _policy(),
            RuntimeMode.LIVE,
            RiskReasonCode.LIVE_MODE_DISABLED,
        ),
    ),
)
def test_upstream_and_runtime_gates_fail_closed(
    decision: TradeDecision,
    context: RiskContext,
    policy: RiskPolicy,
    mode: RuntimeMode,
    reason: RiskReasonCode,
) -> None:
    _assert_rejected(
        assess_entry_risk(decision, context, policy, mode),
        reason,
    )


def test_upstream_precedence_stops_at_first_failure() -> None:
    decision = replace(
        _decision(),
        policy_version="wrong",
        feature_schema_version="wrong",
        action=DecisionAction.WATCH,
        safety_decision=SafetyDecision.REJECT,
        setup_state=SetupState.BLOCKED,
        market_regime=MarketRegime.DEAD,
        total_score=None,
    )
    context = replace(_context(), as_of_unix_ms=123)
    result = _assess(decision=decision, context=context, mode=RuntimeMode.LIVE)
    _assert_rejected(result, RiskReasonCode.DECISION_POLICY_MISMATCH)


@pytest.mark.parametrize(
    ("context", "reason"),
    (
        (replace(_context(), kill_switch_active=True), RiskReasonCode.KILL_SWITCH_ACTIVE),
        (replace(_context(), data_healthy=None), RiskReasonCode.DATA_HEALTH_UNKNOWN),
        (replace(_context(), data_healthy=False), RiskReasonCode.DATA_HEALTH_DEGRADED),
        (
            replace(_context(), execution_healthy=None),
            RiskReasonCode.EXECUTION_HEALTH_UNKNOWN,
        ),
        (
            replace(_context(), execution_healthy=False),
            RiskReasonCode.EXECUTION_HEALTH_DEGRADED,
        ),
    ),
)
def test_global_and_health_gates(context: RiskContext, reason: RiskReasonCode) -> None:
    _assert_rejected(_assess(context=context), reason)


def test_kill_switch_precedes_unknown_health() -> None:
    result = _assess(
        context=replace(
            _context(),
            kill_switch_active=True,
            data_healthy=None,
            execution_healthy=None,
        )
    )
    _assert_rejected(result, RiskReasonCode.KILL_SWITCH_ACTIVE)


@pytest.mark.parametrize(
    ("context", "reason"),
    (
        (replace(_context(), trading_capital_usd=None), RiskReasonCode.TRADING_CAPITAL_UNKNOWN),
        (replace(_context(), trading_capital_usd=0.0), RiskReasonCode.TRADING_CAPITAL_NON_POSITIVE),
        (
            replace(_context(), open_position_count=None),
            RiskReasonCode.OPEN_POSITION_COUNT_UNKNOWN,
        ),
        (replace(_context(), open_position_count=5), RiskReasonCode.MAX_POSITIONS_REACHED),
        (
            replace(_context(), aggregate_open_risk_usd=None),
            RiskReasonCode.AGGREGATE_OPEN_RISK_UNKNOWN,
        ),
        (
            replace(_context(), aggregate_open_risk_usd=3_000.0),
            RiskReasonCode.AGGREGATE_RISK_LIMIT_REACHED,
        ),
        (
            replace(_context(), daily_realized_pnl_usd=None),
            RiskReasonCode.DAILY_REALIZED_PNL_UNKNOWN,
        ),
        (
            replace(_context(), daily_realized_pnl_usd=-500.0),
            RiskReasonCode.DAILY_LOSS_LIMIT_REACHED,
        ),
        (
            replace(_context(), rolling_drawdown_pct=None),
            RiskReasonCode.ROLLING_DRAWDOWN_UNKNOWN,
        ),
        (
            replace(_context(), rolling_drawdown_pct=20.0),
            RiskReasonCode.ROLLING_DRAWDOWN_LIMIT_REACHED,
        ),
        (
            replace(_context(), consecutive_losses=None),
            RiskReasonCode.CONSECUTIVE_LOSSES_UNKNOWN,
        ),
        (
            replace(_context(), consecutive_losses=3, last_loss_at_unix_ms=None),
            RiskReasonCode.LOSS_COOLDOWN_TIME_UNKNOWN,
        ),
        (
            replace(_context(), consecutive_losses=3, last_loss_at_unix_ms=1_000_001),
            RiskReasonCode.LOSS_COOLDOWN_TIME_AFTER_AS_OF,
        ),
        (
            replace(_context(), consecutive_losses=3, last_loss_at_unix_ms=700_001),
            RiskReasonCode.LOSS_COOLDOWN_ACTIVE,
        ),
    ),
)
def test_portfolio_loss_and_cooldown_gates(
    context: RiskContext, reason: RiskReasonCode
) -> None:
    _assert_rejected(_assess(context=context), reason)


def test_portfolio_and_cooldown_allowed_boundaries_pass() -> None:
    result = _assess(
        context=replace(
            _context(),
            open_position_count=4,
            aggregate_open_risk_usd=2_999.0,
            daily_realized_pnl_usd=-499.99,
            rolling_drawdown_pct=19.999,
            consecutive_losses=3,
            last_loss_at_unix_ms=700_000,
            price_impact_notional_usd=5_000.0,
        ),
        policy=replace(_policy(), target_position_notional_usd=0.5),
    )
    assert result.state is RiskState.APPROVED


def test_zero_second_cooldown_needs_no_last_loss_timestamp() -> None:
    result = _assess(
        context=replace(_context(), consecutive_losses=99, last_loss_at_unix_ms=None),
        policy=replace(_policy(), cooldown_seconds=0),
    )
    assert result.state is RiskState.APPROVED


@pytest.mark.parametrize(
    ("policy", "context", "expected"),
    (
        (
            replace(
                _policy(),
                target_position_notional_usd=2_000.0,
                max_notional_per_position_usd=1_000.0,
                max_capital_fraction_per_position=0.50,
                max_aggregate_open_risk_usd=10_000.0,
            ),
            _context(),
            1_000.0,
        ),
        (
            replace(
                _policy(),
                target_position_notional_usd=2_000.0,
                max_notional_per_position_usd=2_000.0,
                max_capital_fraction_per_position=0.10,
                max_aggregate_open_risk_usd=10_000.0,
            ),
            replace(_context(), trading_capital_usd=4_000.0),
            400.0,
        ),
        (
            replace(
                _policy(),
                target_position_notional_usd=2_000.0,
                max_notional_per_position_usd=2_000.0,
                max_capital_fraction_per_position=0.50,
                max_aggregate_open_risk_usd=3_000.0,
            ),
            replace(_context(), aggregate_open_risk_usd=2_900.0),
            100.0,
        ),
        (_policy(), _context(), 500.0),
    ),
)
def test_deterministic_sizing_uses_most_conservative_cap(
    policy: RiskPolicy,
    context: RiskContext,
    expected: float,
) -> None:
    result = _assess(policy=policy, context=context)
    assert result.state is RiskState.APPROVED
    assert result.requested_notional_usd == pytest.approx(expected)


def test_strategy_score_does_not_change_risk_size_once_entry_is_eligible() -> None:
    low = _assess(decision=replace(_decision(), total_score=75.0))
    high = _assess(decision=replace(_decision(), total_score=100.0))
    assert low.requested_notional_usd == high.requested_notional_usd == 500.0


@pytest.mark.parametrize(
    ("context", "reason"),
    (
        (replace(_context(), liquidity_usd=None), RiskReasonCode.LIQUIDITY_UNKNOWN),
        (
            replace(_context(), liquidity_usd=49_999.99),
            RiskReasonCode.LIQUIDITY_BELOW_MINIMUM,
        ),
        (
            replace(_context(), expected_price_impact_pct=None),
            RiskReasonCode.PRICE_IMPACT_UNKNOWN,
        ),
        (
            replace(_context(), price_impact_notional_usd=None),
            RiskReasonCode.PRICE_IMPACT_NOTIONAL_UNKNOWN,
        ),
        (
            replace(_context(), price_impact_notional_usd=499.99),
            RiskReasonCode.PRICE_IMPACT_NOTIONAL_TOO_SMALL,
        ),
        (
            replace(_context(), expected_price_impact_pct=5.0001),
            RiskReasonCode.PRICE_IMPACT_TOO_HIGH,
        ),
        (
            replace(_context(), market_data_age_ms=None),
            RiskReasonCode.MARKET_DATA_AGE_UNKNOWN,
        ),
        (
            replace(_context(), market_data_age_ms=30_001),
            RiskReasonCode.MARKET_DATA_TOO_OLD,
        ),
    ),
)
def test_executability_gates(context: RiskContext, reason: RiskReasonCode) -> None:
    _assert_rejected(_assess(context=context), reason)


def test_executability_allowed_boundaries_pass() -> None:
    result = _assess(
        context=replace(
            _context(),
            liquidity_usd=50_000.0,
            expected_price_impact_pct=5.0,
            price_impact_notional_usd=500.0,
            market_data_age_ms=30_000,
        )
    )
    assert result.state is RiskState.APPROVED


def test_price_impact_notional_must_cover_final_risk_sized_amount() -> None:
    too_small = _assess(context=replace(_context(), price_impact_notional_usd=499.99))
    _assert_rejected(too_small, RiskReasonCode.PRICE_IMPACT_NOTIONAL_TOO_SMALL)

    covered = _assess(context=replace(_context(), price_impact_notional_usd=500.0))
    assert covered.state is RiskState.APPROVED


def test_duplicate_active_intent_is_rejected_with_same_deterministic_key() -> None:
    approved = _assess()
    assert approved.idempotency_key is not None

    duplicate = _assess(
        context=replace(
            _context(), active_intent_keys=frozenset({approved.idempotency_key})
        )
    )
    _assert_rejected(duplicate, RiskReasonCode.DUPLICATE_ACTIVE_INTENT)


def test_idempotency_key_is_stable_and_excludes_risk_policy_version() -> None:
    base = _assess()
    changed_risk_version = _assess(policy=replace(_policy(), version="risk-v2-test"))

    assert base.idempotency_key is not None
    assert changed_risk_version.idempotency_key == base.idempotency_key
    assert _assess().idempotency_key == base.idempotency_key


@pytest.mark.parametrize(
    ("decision", "mode"),
    (
        (replace(_decision(), mint="OtherMint"), RuntimeMode.PAPER),
        (replace(_decision(), as_of_unix_ms=1_000_001), RuntimeMode.PAPER),
        (
            replace(_decision(), setup_policy_version="fresh-v2"),
            RuntimeMode.PAPER,
        ),
        (replace(_decision(), policy_version="decision-v2"), RuntimeMode.PAPER),
        (_decision(), RuntimeMode.SHADOW),
    ),
)
def test_idempotency_key_changes_when_trade_identity_changes(
    decision: TradeDecision, mode: RuntimeMode
) -> None:
    policy = _policy()
    context = _context()
    if decision.policy_version != policy.required_decision_policy_version:
        policy = replace(
            policy, required_decision_policy_version=decision.policy_version
        )
    if decision.as_of_unix_ms != context.as_of_unix_ms:
        context = replace(context, as_of_unix_ms=decision.as_of_unix_ms)

    base = _assess()
    changed = assess_entry_risk(decision, context, policy, mode)
    assert changed.state is RiskState.APPROVED
    assert changed.idempotency_key != base.idempotency_key


@pytest.mark.parametrize("mode", (RuntimeMode.PAPER, RuntimeMode.SHADOW))
def test_approved_intent_preserves_stable_audit_contract(mode: RuntimeMode) -> None:
    result = _assess(mode=mode)
    intent = result.intent
    assert intent is not None
    assert intent.side is TradeSide.BUY
    assert intent.reason == "ENTRY_APPROVED"
    assert intent.strategy_name == "fresh_launch_continuation"
    assert intent.strategy_version == "fresh-test"
    assert intent.score_policy_version == "score-v1-test"
    assert intent.decision_policy_version == "decision-v1-test"
    assert intent.risk_policy_version == "risk-v1-test"
    assert intent.max_slippage_bps == 300
    assert intent.execution_mode is mode
    assert intent.as_of_unix_ms == 1_000_000
    assert intent.idempotency_key == result.idempotency_key


@pytest.mark.parametrize(
    ("mode", "reason"),
    (
        (RuntimeMode.OBSERVE, RiskReasonCode.OBSERVE_MODE_NO_INTENTS),
        (RuntimeMode.HALTED, RiskReasonCode.HALTED_MODE),
        (RuntimeMode.LIVE, RiskReasonCode.LIVE_MODE_DISABLED),
    ),
)
def test_non_paper_non_shadow_modes_never_create_intents(
    mode: RuntimeMode, reason: RiskReasonCode
) -> None:
    result = _assess(mode=mode)
    _assert_rejected(result, reason)


def test_downstream_precedence_returns_only_earliest_terminal_reason() -> None:
    context = replace(
        _context(),
        kill_switch_active=True,
        data_healthy=None,
        execution_healthy=None,
        trading_capital_usd=None,
        open_position_count=None,
        aggregate_open_risk_usd=None,
        daily_realized_pnl_usd=None,
        rolling_drawdown_pct=None,
        consecutive_losses=None,
        liquidity_usd=None,
        expected_price_impact_pct=None,
        price_impact_notional_usd=None,
        market_data_age_ms=None,
    )
    result = _assess(context=context)
    _assert_rejected(result, RiskReasonCode.KILL_SWITCH_ACTIVE)


def test_equal_inputs_return_equal_assessments() -> None:
    assert _assess() == _assess()
