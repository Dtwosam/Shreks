from dataclasses import fields

from shreks_brain.decision import (
    DecisionAction,
    DecisionFinding,
    DecisionPolicy,
    DecisionReasonCode,
    TradeDecision,
    decide_entry,
)
from shreks_brain.features import FeatureVector
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.risk import (
    RiskAssessment,
    RiskContext,
    RiskFinding,
    RiskPolicy,
    RiskReasonCode,
    RiskState,
    TradeIntent,
    TradeSide,
    assess_entry_risk,
)
from shreks_brain.runtime import RuntimeMode, parse_runtime_mode
from shreks_brain.safety import SafetyDecision, SafetyAssessment
from shreks_brain.scoring import ScoreAssessment, ScorePolicy, score_candidate
from shreks_brain.setups import SetupState, assess_fresh_launch


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


def test_risk_public_api_builds_stable_trade_intent() -> None:
    assert callable(assess_entry_risk)
    result = assess_entry_risk(
        _decision(), _context(), _policy(), RuntimeMode.PAPER
    )
    assert isinstance(result, RiskAssessment)
    assert result.state is RiskState.APPROVED
    assert isinstance(result.intent, TradeIntent)
    assert result.intent.side is TradeSide.BUY
    assert result.findings[0].code is RiskReasonCode.RISK_APPROVED
    assert isinstance(result.findings[0], RiskFinding)


def test_previous_brain_entry_points_remain_importable() -> None:
    assert RuntimeMode.PAPER.value == "paper"
    assert callable(parse_runtime_mode)
    assert SafetyDecision.PASS.value == "PASS"
    assert SafetyAssessment is not None
    assert FeatureVector is not None
    assert SetupState.READY.value == "READY"
    assert callable(assess_fresh_launch)
    assert MarketRegime.NORMAL.value == "NORMAL"
    assert RegimeAssessment is not None
    assert ScoreAssessment is not None
    assert ScorePolicy is not None
    assert callable(score_candidate)
    assert DecisionPolicy is not None
    assert callable(decide_entry)


def test_trade_intent_public_contract_has_no_execution_secret_or_outcome_state() -> None:
    names = {field.name for field in fields(TradeIntent)}
    assert names == {
        "mint",
        "side",
        "requested_notional_usd",
        "max_slippage_bps",
        "strategy_name",
        "strategy_version",
        "score_policy_version",
        "decision_policy_version",
        "risk_policy_version",
        "reason",
        "idempotency_key",
        "execution_mode",
        "as_of_unix_ms",
    }
    forbidden = {
        "route",
        "quote",
        "fill",
        "transaction",
        "signature",
        "private_key",
        "seed_phrase",
        "wallet_secret",
        "realized_pnl",
        "unrealized_pnl",
    }
    assert names.isdisjoint(forbidden)
