from dataclasses import fields

from shreks_brain.decision import (
    DecisionAction,
    DecisionFinding,
    DecisionPolicy,
    DecisionReasonCode,
    SetupDecisionRule,
    TradeDecision,
    decide_entry,
)
from shreks_brain.features import FeatureVector
from shreks_brain.regime import MarketRegime, assess_regime
from shreks_brain.safety import SafetyDecision, assess_safety
from shreks_brain.scoring import ScoreAssessment, score_candidate
from shreks_brain.setups import (
    FRESH_LAUNCH_SETUP_NAME,
    SetupState,
    assess_first_pullback,
    assess_fresh_launch,
    assess_graduation_breakout,
)


def _score() -> ScoreAssessment:
    return ScoreAssessment(
        policy_version="score-v1-test",
        feature_schema_version="b2-v1",
        as_of_unix_ms=1_000_000,
        source_observed_at_unix_ms=995_000,
        safety_decision=SafetyDecision.PASS,
        setup_name=FRESH_LAUNCH_SETUP_NAME,
        setup_policy_version="fresh-test",
        setup_state=SetupState.READY,
        regime_policy_version="regime-test",
        market_regime=MarketRegime.NORMAL,
        safety_quality_score=100.0,
        money_flow_score=80.0,
        setup_quality_score=90.0,
        liquidity_executability_score=80.0,
        total_score=85.0,
        findings=(),
    )


def _policy() -> DecisionPolicy:
    return DecisionPolicy(
        version="decision-v1-test",
        required_score_policy_version="score-v1-test",
        setup_rules=(
            SetupDecisionRule(
                setup_name=FRESH_LAUNCH_SETUP_NAME,
                enabled=True,
                hot_min_score=70.0,
                normal_min_score=80.0,
                weak_min_score=90.0,
            ),
        ),
    )


def test_decision_public_api_returns_trade_decision() -> None:
    assert callable(decide_entry)
    result = decide_entry("Mint111", _score(), _policy())
    assert isinstance(result, TradeDecision)
    assert result.action is DecisionAction.ENTER
    assert DecisionFinding is not None
    assert DecisionReasonCode.ENTRY_APPROVED in tuple(
        finding.code for finding in result.findings
    )


def test_existing_brain_public_entry_points_remain_importable() -> None:
    assert FeatureVector is not None
    assert callable(assess_safety)
    assert callable(assess_regime)
    assert callable(assess_fresh_launch)
    assert callable(assess_graduation_breakout)
    assert callable(assess_first_pullback)
    assert callable(score_candidate)


def test_trade_decision_public_surface_has_no_risk_intent_or_execution_authority() -> None:
    field_names = {field.name for field in fields(TradeDecision)}
    forbidden = {
        "trade_intent",
        "side",
        "requested_size",
        "quantity",
        "notional",
        "capital_pct",
        "position_size",
        "slippage",
        "slippage_ceiling",
        "idempotency_key",
        "execution_mode",
        "risk",
        "wallet",
        "signer",
        "order",
        "fill",
        "transaction",
        "realized_pnl",
        "position_quantity",
    }
    assert field_names.isdisjoint(forbidden)
