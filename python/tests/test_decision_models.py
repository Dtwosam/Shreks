from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.decision.models import (
    DecisionAction,
    DecisionFinding,
    DecisionPolicy,
    DecisionReasonCode,
    SetupDecisionRule,
    TradeDecision,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import SetupState


def _rule(**overrides: object) -> SetupDecisionRule:
    values: dict[str, object] = {
        "setup_name": "fresh_launch_continuation",
        "enabled": True,
        "hot_min_score": 70.0,
        "normal_min_score": 75.0,
        "weak_min_score": 85.0,
    }
    values.update(overrides)
    return SetupDecisionRule(**values)


def _policy(**overrides: object) -> DecisionPolicy:
    values: dict[str, object] = {
        "version": "decision-v1-test",
        "required_score_policy_version": "score-v1-test",
        "setup_rules": (
            _rule(),
            _rule(
                setup_name="graduation_breakout",
                hot_min_score=65.0,
                normal_min_score=75.0,
                weak_min_score=90.0,
            ),
            _rule(
                setup_name="first_pullback",
                hot_min_score=72.0,
                normal_min_score=78.0,
                weak_min_score=88.0,
            ),
        ),
    }
    values.update(overrides)
    return DecisionPolicy(**values)


def _decision(**overrides: object) -> TradeDecision:
    values: dict[str, object] = {
        "policy_version": "decision-v1-test",
        "mint": "Mint111",
        "as_of_unix_ms": 1_000_000,
        "action": DecisionAction.ENTER,
        "score_policy_version": "score-v1-test",
        "feature_schema_version": "b2-v1",
        "safety_decision": SafetyDecision.PASS,
        "setup_name": "fresh_launch_continuation",
        "setup_policy_version": "fresh-test",
        "setup_state": SetupState.READY,
        "market_regime": MarketRegime.NORMAL,
        "total_score": 80.0,
        "required_score_threshold": 75.0,
        "findings": (
            DecisionFinding(
                code=DecisionReasonCode.ENTRY_APPROVED,
                message="entry may proceed to risk evaluation",
                observed_value=80.0,
                threshold_value=75.0,
            ),
        ),
    }
    values.update(overrides)
    return TradeDecision(**values)


def test_decision_action_order_is_stable() -> None:
    assert tuple(item.value for item in DecisionAction) == (
        "REJECT",
        "WATCH",
        "ENTER",
        "HOLD",
        "REDUCE",
        "EXIT",
    )


def test_reason_code_order_is_stable() -> None:
    assert tuple(item.value for item in DecisionReasonCode) == (
        "SCORE_POLICY_MISMATCH",
        "SAFETY_REJECTED",
        "SAFETY_INCOMPLETE",
        "SETUP_BLOCKED",
        "SETUP_WATCH",
        "SETUP_RULE_MISSING",
        "SETUP_DISABLED",
        "REGIME_DEAD",
        "REGIME_DISABLED",
        "TOTAL_SCORE_UNAVAILABLE",
        "TOTAL_SCORE_BELOW_THRESHOLD",
        "ENTRY_APPROVED",
    )


def test_setup_rule_is_frozen_and_allows_independent_regime_thresholds() -> None:
    rule = _rule(hot_min_score=90.0, normal_min_score=60.0, weak_min_score=None)
    assert rule.hot_min_score == 90.0
    assert rule.normal_min_score == 60.0
    assert rule.weak_min_score is None
    with pytest.raises(FrozenInstanceError):
        rule.enabled = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"setup_name": ""},
        {"enabled": 1},
        {"hot_min_score": -0.1},
        {"normal_min_score": 100.1},
        {"weak_min_score": math.inf},
        {"hot_min_score": math.nan},
    ],
)
def test_setup_rule_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _rule(**overrides)


def test_decision_policy_is_frozen_and_validates_unique_nonempty_rules() -> None:
    policy = _policy()
    assert len(policy.setup_rules) == 3
    with pytest.raises(FrozenInstanceError):
        policy.version = "mutated"  # type: ignore[misc]

    with pytest.raises(ValueError):
        _policy(version=" ")
    with pytest.raises(ValueError):
        _policy(required_score_policy_version="")
    with pytest.raises(ValueError):
        _policy(setup_rules=())
    with pytest.raises(ValueError):
        _policy(setup_rules=[_rule()])
    with pytest.raises(ValueError):
        _policy(setup_rules=(_rule(), "bad"))
    with pytest.raises(ValueError):
        _policy(setup_rules=(_rule(), _rule()))


def test_policy_has_no_production_default_instance() -> None:
    with pytest.raises(TypeError):
        DecisionPolicy()  # type: ignore[call-arg]


def test_decision_finding_is_frozen_and_validated() -> None:
    finding = DecisionFinding(
        code=DecisionReasonCode.TOTAL_SCORE_BELOW_THRESHOLD,
        message="score below threshold",
        observed_value=74.9,
        threshold_value=75.0,
    )
    with pytest.raises(FrozenInstanceError):
        finding.message = "mutated"  # type: ignore[misc]
    with pytest.raises(ValueError):
        DecisionFinding(code="bad", message="bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DecisionFinding(code=DecisionReasonCode.ENTRY_APPROVED, message=" ")
    with pytest.raises(ValueError):
        DecisionFinding(
            code=DecisionReasonCode.ENTRY_APPROVED,
            message="bad numeric",
            observed_value=math.inf,
        )


def test_trade_decision_accepts_full_six_action_vocabulary_for_future_reuse() -> None:
    for action in DecisionAction:
        decision = _decision(action=action)
        assert decision.action is action


def test_trade_decision_is_frozen_and_validated() -> None:
    decision = _decision()
    with pytest.raises(FrozenInstanceError):
        decision.action = DecisionAction.WATCH  # type: ignore[misc]

    for field_name in (
        "policy_version",
        "mint",
        "score_policy_version",
        "feature_schema_version",
        "setup_name",
        "setup_policy_version",
    ):
        with pytest.raises(ValueError):
            _decision(**{field_name: ""})

    with pytest.raises(ValueError):
        _decision(as_of_unix_ms=-1)
    with pytest.raises(ValueError):
        _decision(action="ENTER")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _decision(safety_decision="PASS")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _decision(setup_state="READY")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _decision(market_regime="NORMAL")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _decision(total_score=-0.1)
    with pytest.raises(ValueError):
        _decision(total_score=100.1)
    with pytest.raises(ValueError):
        _decision(required_score_threshold=math.inf)
    with pytest.raises(ValueError):
        _decision(findings=[])


def test_trade_decision_allows_unavailable_score_and_threshold_for_terminal_gates() -> None:
    decision = _decision(
        action=DecisionAction.WATCH,
        total_score=None,
        required_score_threshold=None,
    )
    assert decision.total_score is None
    assert decision.required_score_threshold is None


def test_trade_decision_has_no_risk_intent_or_execution_authority() -> None:
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
