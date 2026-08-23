from dataclasses import FrozenInstanceError, fields, replace
import math

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.runtime import RuntimeMode
from shreks_brain.risk.models import (
    RiskAssessment,
    RiskContext,
    RiskFinding,
    RiskPolicy,
    RiskReasonCode,
    RiskState,
    TradeIntent,
    TradeSide,
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


def _intent() -> TradeIntent:
    return TradeIntent(
        mint="Mint111",
        side=TradeSide.BUY,
        requested_notional_usd=500.0,
        max_slippage_bps=300,
        strategy_name="fresh_launch_continuation",
        strategy_version="fresh-test",
        score_policy_version="score-v1-test",
        decision_policy_version="decision-v1-test",
        risk_policy_version="risk-v1-test",
        reason="ENTRY_APPROVED",
        idempotency_key="abc123",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=1_000_000,
    )


def _finding() -> RiskFinding:
    return RiskFinding(
        code=RiskReasonCode.RISK_APPROVED,
        message="all risk guardrails passed",
    )


def test_risk_enum_contract_is_stable() -> None:
    assert tuple(item.value for item in TradeSide) == ("BUY", "SELL")
    assert tuple(item.value for item in RiskState) == ("REJECTED", "APPROVED")
    assert tuple(item.value for item in RiskReasonCode) == (
        "DECISION_POLICY_MISMATCH",
        "FEATURE_SCHEMA_UNSUPPORTED",
        "DECISION_NOT_ENTER",
        "SAFETY_NOT_PASS",
        "SETUP_NOT_READY",
        "REGIME_DEAD",
        "TOTAL_SCORE_UNAVAILABLE",
        "CONTEXT_AS_OF_MISMATCH",
        "OBSERVE_MODE_NO_INTENTS",
        "HALTED_MODE",
        "LIVE_MODE_DISABLED",
        "KILL_SWITCH_ACTIVE",
        "DATA_HEALTH_UNKNOWN",
        "DATA_HEALTH_DEGRADED",
        "EXECUTION_HEALTH_UNKNOWN",
        "EXECUTION_HEALTH_DEGRADED",
        "TRADING_CAPITAL_UNKNOWN",
        "TRADING_CAPITAL_NON_POSITIVE",
        "OPEN_POSITION_COUNT_UNKNOWN",
        "MAX_POSITIONS_REACHED",
        "AGGREGATE_OPEN_RISK_UNKNOWN",
        "AGGREGATE_RISK_LIMIT_REACHED",
        "DAILY_REALIZED_PNL_UNKNOWN",
        "DAILY_LOSS_LIMIT_REACHED",
        "ROLLING_DRAWDOWN_UNKNOWN",
        "ROLLING_DRAWDOWN_LIMIT_REACHED",
        "CONSECUTIVE_LOSSES_UNKNOWN",
        "LOSS_COOLDOWN_TIME_UNKNOWN",
        "LOSS_COOLDOWN_TIME_AFTER_AS_OF",
        "LOSS_COOLDOWN_ACTIVE",
        "LIQUIDITY_UNKNOWN",
        "LIQUIDITY_BELOW_MINIMUM",
        "PRICE_IMPACT_UNKNOWN",
        "PRICE_IMPACT_NOTIONAL_UNKNOWN",
        "PRICE_IMPACT_NOTIONAL_TOO_SMALL",
        "PRICE_IMPACT_TOO_HIGH",
        "MARKET_DATA_AGE_UNKNOWN",
        "MARKET_DATA_TOO_OLD",
        "DUPLICATE_ACTIVE_INTENT",
        "RISK_APPROVED",
    )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("version", ""),
        ("required_decision_policy_version", " "),
        ("required_feature_schema_version", ""),
        ("target_position_notional_usd", 0.0),
        ("target_position_notional_usd", math.inf),
        ("max_notional_per_position_usd", 0.0),
        ("max_notional_per_position_usd", math.nan),
        ("max_capital_fraction_per_position", 0.0),
        ("max_capital_fraction_per_position", 1.01),
        ("max_simultaneous_positions", 0),
        ("max_simultaneous_positions", True),
        ("max_aggregate_open_risk_usd", 0.0),
        ("max_daily_realized_loss_usd", 0.0),
        ("max_rolling_drawdown_pct", 0.0),
        ("max_rolling_drawdown_pct", 100.01),
        ("cooldown_after_consecutive_losses", 0),
        ("cooldown_seconds", -1),
        ("min_liquidity_usd", -1.0),
        ("max_expected_price_impact_pct", -1.0),
        ("max_slippage_bps", -1),
        ("max_slippage_bps", 10_001),
        ("max_slippage_bps", 1.5),
        ("max_market_data_age_ms", -1),
    ),
)
def test_risk_policy_rejects_invalid_values(field_name: str, bad_value: object) -> None:
    with pytest.raises(ValueError):
        replace(_policy(), **{field_name: bad_value})


def test_risk_policy_accepts_boundaries_and_is_frozen() -> None:
    policy = replace(
        _policy(),
        max_capital_fraction_per_position=1.0,
        max_rolling_drawdown_pct=100.0,
        cooldown_seconds=0,
        min_liquidity_usd=0.0,
        max_expected_price_impact_pct=0.0,
        max_slippage_bps=0,
        max_market_data_age_ms=0,
    )
    assert policy.max_capital_fraction_per_position == 1.0
    with pytest.raises(FrozenInstanceError):
        policy.version = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field_name",
    (
        "trading_capital_usd",
        "open_position_count",
        "aggregate_open_risk_usd",
        "daily_realized_pnl_usd",
        "rolling_drawdown_pct",
        "consecutive_losses",
        "last_loss_at_unix_ms",
        "liquidity_usd",
        "expected_price_impact_pct",
        "price_impact_notional_usd",
        "market_data_age_ms",
        "data_healthy",
        "execution_healthy",
    ),
)
def test_risk_context_preserves_missing_optional_evidence(field_name: str) -> None:
    context = replace(_context(), **{field_name: None})
    assert getattr(context, field_name) is None


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("as_of_unix_ms", -1),
        ("trading_capital_usd", -1.0),
        ("trading_capital_usd", math.inf),
        ("open_position_count", -1),
        ("open_position_count", True),
        ("aggregate_open_risk_usd", -1.0),
        ("daily_realized_pnl_usd", math.nan),
        ("rolling_drawdown_pct", -0.1),
        ("rolling_drawdown_pct", 100.1),
        ("consecutive_losses", -1),
        ("last_loss_at_unix_ms", -1),
        ("liquidity_usd", -1.0),
        ("expected_price_impact_pct", -1.0),
        ("price_impact_notional_usd", -1.0),
        ("market_data_age_ms", -1),
        ("data_healthy", "yes"),
        ("execution_healthy", 1),
        ("kill_switch_active", 1),
        ("active_intent_keys", set()),
        ("active_intent_keys", frozenset({""})),
    ),
)
def test_risk_context_rejects_invalid_present_values(
    field_name: str, bad_value: object
) -> None:
    with pytest.raises(ValueError):
        replace(_context(), **{field_name: bad_value})


def test_risk_context_is_frozen() -> None:
    context = _context()
    with pytest.raises(FrozenInstanceError):
        context.kill_switch_active = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("mint", ""),
        ("side", "BUY"),
        ("requested_notional_usd", 0.0),
        ("requested_notional_usd", math.inf),
        ("max_slippage_bps", -1),
        ("max_slippage_bps", 10_001),
        ("strategy_name", ""),
        ("strategy_version", ""),
        ("score_policy_version", ""),
        ("decision_policy_version", ""),
        ("risk_policy_version", ""),
        ("reason", ""),
        ("idempotency_key", ""),
        ("execution_mode", "paper"),
        ("as_of_unix_ms", -1),
    ),
)
def test_trade_intent_rejects_invalid_values(field_name: str, bad_value: object) -> None:
    with pytest.raises(ValueError):
        replace(_intent(), **{field_name: bad_value})


def test_trade_intent_is_stable_and_has_no_execution_or_outcome_authority() -> None:
    intent = _intent()
    assert intent.side is TradeSide.BUY
    assert intent.execution_mode is RuntimeMode.PAPER
    names = {field.name for field in fields(TradeIntent)}
    forbidden = {
        "route",
        "quote",
        "fill",
        "transaction",
        "signature",
        "private_key",
        "secret",
        "wallet_secret",
        "realized_pnl",
        "unrealized_pnl",
    }
    assert names.isdisjoint(forbidden)
    with pytest.raises(FrozenInstanceError):
        intent.reason = "mutated"  # type: ignore[misc]


def test_risk_finding_requires_stable_reason_and_message() -> None:
    with pytest.raises(ValueError):
        RiskFinding(code="RISK_APPROVED", message="x")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RiskFinding(code=RiskReasonCode.RISK_APPROVED, message="")


def test_approved_assessment_requires_matching_intent_context() -> None:
    intent = _intent()
    assessment = RiskAssessment(
        policy_version="risk-v1-test",
        mint="Mint111",
        as_of_unix_ms=1_000_000,
        state=RiskState.APPROVED,
        decision_action=DecisionAction.ENTER,
        execution_mode=RuntimeMode.PAPER,
        requested_notional_usd=500.0,
        idempotency_key="abc123",
        findings=(_finding(),),
        intent=intent,
    )
    assert assessment.intent == intent

    with pytest.raises(ValueError):
        replace(assessment, requested_notional_usd=None)
    with pytest.raises(ValueError):
        replace(assessment, idempotency_key=None)
    with pytest.raises(ValueError):
        replace(assessment, intent=None)
    with pytest.raises(ValueError):
        replace(assessment, mint="OtherMint")
    with pytest.raises(ValueError):
        replace(assessment, requested_notional_usd=499.0)


def test_rejected_assessment_cannot_carry_size_key_or_intent() -> None:
    rejected_finding = RiskFinding(
        code=RiskReasonCode.KILL_SWITCH_ACTIVE,
        message="global kill switch is active",
    )
    assessment = RiskAssessment(
        policy_version="risk-v1-test",
        mint="Mint111",
        as_of_unix_ms=1_000_000,
        state=RiskState.REJECTED,
        decision_action=DecisionAction.ENTER,
        execution_mode=RuntimeMode.PAPER,
        requested_notional_usd=None,
        idempotency_key=None,
        findings=(rejected_finding,),
        intent=None,
    )
    assert assessment.intent is None

    with pytest.raises(ValueError):
        replace(assessment, requested_notional_usd=1.0)
    with pytest.raises(ValueError):
        replace(assessment, idempotency_key="abc")
    with pytest.raises(ValueError):
        replace(assessment, intent=_intent())


def test_risk_assessment_requires_exact_types_and_is_frozen() -> None:
    assessment = RiskAssessment(
        policy_version="risk-v1-test",
        mint="Mint111",
        as_of_unix_ms=1_000_000,
        state=RiskState.REJECTED,
        decision_action=DecisionAction.ENTER,
        execution_mode=RuntimeMode.PAPER,
        requested_notional_usd=None,
        idempotency_key=None,
        findings=(
            RiskFinding(
                code=RiskReasonCode.KILL_SWITCH_ACTIVE,
                message="global kill switch is active",
            ),
        ),
        intent=None,
    )
    with pytest.raises(ValueError):
        replace(assessment, state="REJECTED")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(assessment, decision_action="ENTER")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(assessment, execution_mode="paper")  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        assessment.mint = "mutated"  # type: ignore[misc]
