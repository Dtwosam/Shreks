from __future__ import annotations

from dataclasses import replace

from shreks_brain.decision import (
    DecisionAction,
    DecisionFinding,
    DecisionReasonCode,
    TradeDecision,
)
from shreks_brain.observer_campaign.assembler import _exit_execution_context
from shreks_brain.risk.engine import assess_entry_risk
from shreks_brain.risk.models import (
    RiskContext,
    RiskPolicy,
    RiskReasonCode,
    RiskState,
)
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision
from shreks_brain.regime import MarketRegime
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
        operator_entry_halt_active=False,
    )


def _reason(context: RiskContext) -> RiskReasonCode:
    result = assess_entry_risk(_decision(), context, _policy(), RuntimeMode.PAPER)
    assert result.state is RiskState.REJECTED
    assert result.intent is None
    return result.findings[0].code


def test_operator_entry_halt_blocks_only_new_entries_with_stable_reason() -> None:
    context = replace(_context(), operator_entry_halt_active=True)
    assert _reason(context) is RiskReasonCode.OPERATOR_ENTRY_HALT_ACTIVE


def test_emergency_kill_retains_existing_kill_switch_precedence() -> None:
    context = replace(
        _context(),
        operator_entry_halt_active=True,
        kill_switch_active=True,
    )
    assert _reason(context) is RiskReasonCode.KILL_SWITCH_ACTIVE


def test_legacy_context_default_remains_entry_eligible() -> None:
    context = replace(_context(), operator_entry_halt_active=False)
    result = assess_entry_risk(_decision(), context, _policy(), RuntimeMode.PAPER)
    assert result.state is RiskState.APPROVED


def test_entry_halt_does_not_fabricate_global_exit_halt() -> None:
    context = _exit_execution_context(
        1_000_000,
        999_900,
        None,
        None,
        False,
        operator_entry_halt_active=True,
        operator_kill_switch_active=False,
    )
    assert context.global_halt_active is False


def test_emergency_kill_feeds_existing_global_halt_exit_path() -> None:
    context = _exit_execution_context(
        1_000_000,
        999_900,
        None,
        None,
        False,
        operator_entry_halt_active=True,
        operator_kill_switch_active=True,
    )
    assert context.global_halt_active is True
