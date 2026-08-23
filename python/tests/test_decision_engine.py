from dataclasses import replace

import pytest

from shreks_brain.decision.engine import decide_entry
from shreks_brain.decision.models import (
    DecisionAction,
    DecisionPolicy,
    DecisionReasonCode,
    SetupDecisionRule,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScoreAssessment
from shreks_brain.setups import (
    FIRST_PULLBACK_SETUP_NAME,
    FRESH_LAUNCH_SETUP_NAME,
    GRADUATION_BREAKOUT_SETUP_NAME,
    SetupState,
)


def _score(**overrides: object) -> ScoreAssessment:
    values: dict[str, object] = {
        "policy_version": "score-v1-test",
        "feature_schema_version": "b2-v1",
        "as_of_unix_ms": 1_000_000,
        "source_observed_at_unix_ms": 995_000,
        "safety_decision": SafetyDecision.PASS,
        "setup_name": FRESH_LAUNCH_SETUP_NAME,
        "setup_policy_version": "fresh-test",
        "setup_state": SetupState.READY,
        "regime_policy_version": "regime-test",
        "market_regime": MarketRegime.NORMAL,
        "safety_quality_score": 100.0,
        "money_flow_score": 70.0,
        "setup_quality_score": 80.0,
        "liquidity_executability_score": 75.0,
        "total_score": 80.0,
        "findings": (),
    }
    values.update(overrides)
    return ScoreAssessment(**values)


def _rule(
    setup_name: str,
    *,
    enabled: bool = True,
    hot: float | None,
    normal: float | None,
    weak: float | None,
) -> SetupDecisionRule:
    return SetupDecisionRule(
        setup_name=setup_name,
        enabled=enabled,
        hot_min_score=hot,
        normal_min_score=normal,
        weak_min_score=weak,
    )


def _policy(**overrides: object) -> DecisionPolicy:
    values: dict[str, object] = {
        "version": "decision-v1-test",
        "required_score_policy_version": "score-v1-test",
        "setup_rules": (
            _rule(FRESH_LAUNCH_SETUP_NAME, hot=70.0, normal=75.0, weak=85.0),
            _rule(
                GRADUATION_BREAKOUT_SETUP_NAME,
                hot=65.0,
                normal=75.0,
                weak=90.0,
            ),
            _rule(FIRST_PULLBACK_SETUP_NAME, hot=72.0, normal=78.0, weak=88.0),
        ),
    }
    values.update(overrides)
    return DecisionPolicy(**values)


def _decision(
    score: ScoreAssessment | None = None,
    policy: DecisionPolicy | None = None,
):
    return decide_entry("Mint111", score or _score(), policy or _policy())


def _only_code(result) -> DecisionReasonCode:
    assert len(result.findings) == 1
    return result.findings[0].code


def test_score_policy_mismatch_rejects_before_every_other_gate() -> None:
    score = _score(
        policy_version="other-score",
        safety_decision=SafetyDecision.INCOMPLETE,
        setup_state=SetupState.WATCH,
        market_regime=MarketRegime.DEAD,
        total_score=None,
    )
    result = _decision(score=score)
    assert result.action is DecisionAction.REJECT
    assert _only_code(result) is DecisionReasonCode.SCORE_POLICY_MISMATCH
    assert result.required_score_threshold is None


def test_safety_reject_is_hard_reject() -> None:
    result = _decision(score=_score(safety_decision=SafetyDecision.REJECT))
    assert result.action is DecisionAction.REJECT
    assert _only_code(result) is DecisionReasonCode.SAFETY_REJECTED


def test_safety_incomplete_watches_instead_of_guessing() -> None:
    result = _decision(score=_score(safety_decision=SafetyDecision.INCOMPLETE))
    assert result.action is DecisionAction.WATCH
    assert _only_code(result) is DecisionReasonCode.SAFETY_INCOMPLETE


def test_setup_blocked_is_rejected() -> None:
    result = _decision(score=_score(setup_state=SetupState.BLOCKED))
    assert result.action is DecisionAction.REJECT
    assert _only_code(result) is DecisionReasonCode.SETUP_BLOCKED


def test_setup_watch_remains_watch() -> None:
    result = _decision(score=_score(setup_state=SetupState.WATCH))
    assert result.action is DecisionAction.WATCH
    assert _only_code(result) is DecisionReasonCode.SETUP_WATCH


def test_missing_setup_rule_rejects_without_fallback() -> None:
    policy = _policy(
        setup_rules=(
            _rule(GRADUATION_BREAKOUT_SETUP_NAME, hot=1.0, normal=1.0, weak=1.0),
        )
    )
    result = _decision(policy=policy)
    assert result.action is DecisionAction.REJECT
    assert _only_code(result) is DecisionReasonCode.SETUP_RULE_MISSING
    assert result.required_score_threshold is None


def test_disabled_setup_rejects() -> None:
    policy = _policy(
        setup_rules=(
            _rule(
                FRESH_LAUNCH_SETUP_NAME,
                enabled=False,
                hot=70.0,
                normal=75.0,
                weak=85.0,
            ),
        )
    )
    result = _decision(policy=policy)
    assert result.action is DecisionAction.REJECT
    assert _only_code(result) is DecisionReasonCode.SETUP_DISABLED


def test_dead_regime_never_enters() -> None:
    result = _decision(score=_score(market_regime=MarketRegime.DEAD, total_score=100.0))
    assert result.action is DecisionAction.REJECT
    assert _only_code(result) is DecisionReasonCode.REGIME_DEAD
    assert result.required_score_threshold is None


@pytest.mark.parametrize(
    "regime,rule_kwargs",
    [
        (MarketRegime.HOT, {"hot": None, "normal": 75.0, "weak": 85.0}),
        (MarketRegime.NORMAL, {"hot": 70.0, "normal": None, "weak": 85.0}),
        (MarketRegime.WEAK, {"hot": 70.0, "normal": 75.0, "weak": None}),
    ],
)
def test_none_regime_threshold_disables_entry_without_rejecting_candidate(
    regime: MarketRegime, rule_kwargs: dict[str, float | None]
) -> None:
    policy = _policy(
        setup_rules=(
            _rule(FRESH_LAUNCH_SETUP_NAME, **rule_kwargs),
        )
    )
    result = _decision(score=_score(market_regime=regime), policy=policy)
    assert result.action is DecisionAction.WATCH
    assert _only_code(result) is DecisionReasonCode.REGIME_DISABLED
    assert result.required_score_threshold is None


def test_missing_total_score_watches_after_policy_and_regime_gates() -> None:
    result = _decision(score=_score(total_score=None))
    assert result.action is DecisionAction.WATCH
    assert _only_code(result) is DecisionReasonCode.TOTAL_SCORE_UNAVAILABLE
    assert result.required_score_threshold == 75.0


@pytest.mark.parametrize(
    "regime,expected_threshold",
    [
        (MarketRegime.HOT, 70.0),
        (MarketRegime.NORMAL, 75.0),
        (MarketRegime.WEAK, 85.0),
    ],
)
def test_regime_selects_exact_setup_specific_threshold(
    regime: MarketRegime, expected_threshold: float
) -> None:
    result = _decision(
        score=_score(market_regime=regime, total_score=expected_threshold)
    )
    assert result.action is DecisionAction.ENTER
    assert result.required_score_threshold == expected_threshold
    assert _only_code(result) is DecisionReasonCode.ENTRY_APPROVED


def test_score_below_threshold_watches() -> None:
    result = _decision(score=_score(total_score=74.999))
    assert result.action is DecisionAction.WATCH
    assert _only_code(result) is DecisionReasonCode.TOTAL_SCORE_BELOW_THRESHOLD
    assert result.required_score_threshold == 75.0


def test_threshold_equality_passes() -> None:
    result = _decision(score=_score(total_score=75.0))
    assert result.action is DecisionAction.ENTER
    assert _only_code(result) is DecisionReasonCode.ENTRY_APPROVED


def test_score_above_threshold_enters() -> None:
    result = _decision(score=_score(total_score=95.0))
    assert result.action is DecisionAction.ENTER
    assert _only_code(result) is DecisionReasonCode.ENTRY_APPROVED


@pytest.mark.parametrize(
    "setup_name,policy_version,normal_threshold",
    [
        (FRESH_LAUNCH_SETUP_NAME, "fresh-test", 75.0),
        (GRADUATION_BREAKOUT_SETUP_NAME, "graduation-test", 75.0),
        (FIRST_PULLBACK_SETUP_NAME, "pullback-test", 78.0),
    ],
)
def test_each_current_setup_uses_its_own_rule(
    setup_name: str, policy_version: str, normal_threshold: float
) -> None:
    result = _decision(
        score=_score(
            setup_name=setup_name,
            setup_policy_version=policy_version,
            total_score=normal_threshold,
        )
    )
    assert result.action is DecisionAction.ENTER
    assert result.setup_name == setup_name
    assert result.setup_policy_version == policy_version
    assert result.required_score_threshold == normal_threshold


def test_decision_copies_candidate_and_score_context_exactly() -> None:
    score = _score(total_score=88.0, market_regime=MarketRegime.HOT)
    result = decide_entry("MintABC", score, _policy())
    assert result.mint == "MintABC"
    assert result.as_of_unix_ms == score.as_of_unix_ms
    assert result.score_policy_version == score.policy_version
    assert result.feature_schema_version == score.feature_schema_version
    assert result.safety_decision is score.safety_decision
    assert result.setup_name == score.setup_name
    assert result.setup_policy_version == score.setup_policy_version
    assert result.setup_state is score.setup_state
    assert result.market_regime is score.market_regime
    assert result.total_score == score.total_score


def test_entry_evaluator_never_emits_open_position_actions() -> None:
    scenarios = (
        _score(policy_version="other"),
        _score(safety_decision=SafetyDecision.REJECT),
        _score(safety_decision=SafetyDecision.INCOMPLETE),
        _score(setup_state=SetupState.BLOCKED),
        _score(setup_state=SetupState.WATCH),
        _score(market_regime=MarketRegime.DEAD),
        _score(total_score=None),
        _score(total_score=70.0),
        _score(total_score=80.0),
    )
    for score in scenarios:
        result = _decision(score=score)
        assert result.action in {
            DecisionAction.REJECT,
            DecisionAction.WATCH,
            DecisionAction.ENTER,
        }
        assert result.action not in {
            DecisionAction.HOLD,
            DecisionAction.REDUCE,
            DecisionAction.EXIT,
        }


def test_equal_inputs_return_equal_decisions() -> None:
    assert _decision() == _decision()
