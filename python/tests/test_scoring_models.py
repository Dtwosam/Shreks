from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.regime import MarketRegime
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import SetupState
from shreks_brain.scoring.models import (
    ScoreAssessment,
    ScoreFinding,
    ScorePolicy,
    ScoreReasonCode,
)


def _policy(**overrides: object) -> ScorePolicy:
    values: dict[str, object] = {
        "version": "score-v1-test",
        "required_feature_schema_version": "b2-v1",
        "safety_weight": 0.20,
        "money_flow_weight": 0.30,
        "setup_quality_weight": 0.30,
        "liquidity_executability_weight": 0.20,
        "safety_liquidity_weak_penalty": 20.0,
        "safety_holder_concentration_elevated_penalty": 25.0,
        "safety_creator_concentration_elevated_penalty": 15.0,
        "safety_exit_price_impact_elevated_penalty": 30.0,
        "volume_velocity_zero": 0.5,
        "volume_velocity_full": 2.0,
        "buy_fraction_m5_zero": 0.40,
        "buy_fraction_m5_full": 0.70,
        "buy_pressure_acceleration_zero": -0.10,
        "buy_pressure_acceleration_full": 0.20,
        "liquidity_usd_zero": 10_000.0,
        "liquidity_usd_full": 100_000.0,
        "exit_price_impact_full": 1.0,
        "exit_price_impact_zero": 8.0,
    }
    values.update(overrides)
    return ScorePolicy(**values)


def _assessment(**overrides: object) -> ScoreAssessment:
    values: dict[str, object] = {
        "policy_version": "score-v1-test",
        "feature_schema_version": "b2-v1",
        "as_of_unix_ms": 1_000_000,
        "source_observed_at_unix_ms": 995_000,
        "safety_decision": SafetyDecision.PASS,
        "setup_name": "fresh_launch_continuation",
        "setup_policy_version": "fresh-test",
        "setup_state": SetupState.READY,
        "regime_policy_version": "regime-test",
        "market_regime": MarketRegime.NORMAL,
        "safety_quality_score": 90.0,
        "money_flow_score": 75.0,
        "setup_quality_score": 80.0,
        "liquidity_executability_score": 70.0,
        "total_score": 78.5,
        "findings": (
            ScoreFinding(
                code=ScoreReasonCode.TOTAL_SCORE_AVAILABLE,
                message="all positive-weight score families are available",
            ),
        ),
    }
    values.update(overrides)
    return ScoreAssessment(**values)


def test_reason_code_order_is_stable() -> None:
    assert tuple(item.value for item in ScoreReasonCode) == (
        "FEATURE_SCHEMA_UNSUPPORTED",
        "FEATURE_SOURCE_AFTER_AS_OF",
        "FEATURE_SOURCE_AGE_MISMATCH",
        "SETUP_AS_OF_MISMATCH",
        "SETUP_FEATURE_SCHEMA_MISMATCH",
        "REGIME_AS_OF_MISMATCH",
        "SAFETY_NOT_PASS_RESEARCH_ONLY",
        "SETUP_NOT_READY_RESEARCH_ONLY",
        "VOLUME_VELOCITY_UNKNOWN",
        "BUY_FRACTION_M5_UNKNOWN",
        "BUY_PRESSURE_ACCELERATION_UNKNOWN",
        "LIQUIDITY_UNKNOWN",
        "EXIT_PRICE_IMPACT_UNKNOWN",
        "SAFETY_SOFT_PENALTIES_APPLIED",
        "TOTAL_SCORE_INCOMPLETE",
        "TOTAL_SCORE_AVAILABLE",
    )


def test_policy_is_frozen_and_accepts_explicit_ablation_weights() -> None:
    policy = _policy(
        safety_weight=0.0,
        money_flow_weight=0.4,
        setup_quality_weight=0.4,
        liquidity_executability_weight=0.2,
    )
    assert policy.safety_weight == 0.0
    with pytest.raises(FrozenInstanceError):
        policy.version = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize("field_name", ["version", "required_feature_schema_version"])
def test_policy_rejects_empty_strings(field_name: str) -> None:
    with pytest.raises(ValueError):
        _policy(**{field_name: "   "})


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        ("safety_weight", -0.01),
        ("money_flow_weight", 1.01),
        ("setup_quality_weight", math.inf),
        ("liquidity_executability_weight", math.nan),
    ],
)
def test_policy_rejects_invalid_weights(field_name: str, bad_value: float) -> None:
    with pytest.raises(ValueError):
        _policy(**{field_name: bad_value})


def test_policy_requires_weights_to_sum_to_one() -> None:
    with pytest.raises(ValueError):
        _policy(liquidity_executability_weight=0.21)


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        ("safety_liquidity_weak_penalty", -1.0),
        ("safety_holder_concentration_elevated_penalty", 101.0),
        ("safety_creator_concentration_elevated_penalty", math.inf),
        ("safety_exit_price_impact_elevated_penalty", math.nan),
    ],
)
def test_policy_rejects_invalid_safety_penalties(
    field_name: str, bad_value: float
) -> None:
    with pytest.raises(ValueError):
        _policy(**{field_name: bad_value})


@pytest.mark.parametrize(
    "overrides",
    [
        {"volume_velocity_full": 0.5},
        {"buy_fraction_m5_full": 0.40},
        {"buy_pressure_acceleration_full": -0.10},
        {"liquidity_usd_full": 10_000.0},
        {"exit_price_impact_zero": 1.0},
    ],
)
def test_policy_requires_strict_normalization_ranges(
    overrides: dict[str, float]
) -> None:
    with pytest.raises(ValueError):
        _policy(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"buy_fraction_m5_zero": -0.01},
        {"buy_fraction_m5_full": 1.01},
        {"liquidity_usd_zero": -1.0},
        {"exit_price_impact_full": -1.0},
        {"volume_velocity_zero": math.inf},
        {"buy_pressure_acceleration_zero": math.nan},
    ],
)
def test_policy_rejects_invalid_normalization_values(
    overrides: dict[str, float]
) -> None:
    with pytest.raises(ValueError):
        _policy(**overrides)


def test_score_finding_is_frozen_and_validated() -> None:
    finding = ScoreFinding(
        code=ScoreReasonCode.TOTAL_SCORE_AVAILABLE,
        message="score available",
        observed_value=75.0,
        threshold_value=50.0,
    )
    with pytest.raises(FrozenInstanceError):
        finding.message = "mutated"  # type: ignore[misc]
    with pytest.raises(ValueError):
        ScoreFinding(code="bad", message="bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ScoreFinding(code=ScoreReasonCode.TOTAL_SCORE_AVAILABLE, message=" ")
    with pytest.raises(ValueError):
        ScoreFinding(
            code=ScoreReasonCode.TOTAL_SCORE_AVAILABLE,
            message="bad numeric",
            observed_value=math.inf,
        )


def test_score_assessment_is_frozen_and_accepts_missing_family_scores() -> None:
    assessment = _assessment(money_flow_score=None, total_score=None)
    assert assessment.money_flow_score is None
    assert assessment.total_score is None
    with pytest.raises(FrozenInstanceError):
        assessment.total_score = 1.0  # type: ignore[misc]


def test_score_assessment_preserves_future_source_for_evaluator_audit() -> None:
    assessment = _assessment(source_observed_at_unix_ms=1_000_001, total_score=None)
    assert assessment.source_observed_at_unix_ms > assessment.as_of_unix_ms


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        ("policy_version", ""),
        ("feature_schema_version", ""),
        ("setup_name", ""),
        ("setup_policy_version", ""),
        ("regime_policy_version", ""),
        ("as_of_unix_ms", -1),
        ("source_observed_at_unix_ms", -1),
        ("safety_quality_score", -0.01),
        ("money_flow_score", 100.01),
        ("setup_quality_score", math.inf),
        ("liquidity_executability_score", math.nan),
        ("total_score", 100.01),
    ],
)
def test_score_assessment_rejects_invalid_fields(
    field_name: str, bad_value: object
) -> None:
    with pytest.raises(ValueError):
        _assessment(**{field_name: bad_value})


def test_score_assessment_requires_enum_values_and_tuple_findings() -> None:
    with pytest.raises(ValueError):
        _assessment(safety_decision="PASS")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _assessment(setup_state="READY")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _assessment(market_regime="NORMAL")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _assessment(findings=[])


def test_score_assessment_has_no_wallet_decision_risk_execution_or_outcome_authority() -> None:
    field_names = {field.name for field in fields(ScoreAssessment)}
    forbidden = {
        "wallet_quality",
        "wallet_quality_score",
        "confidence",
        "win_probability",
        "expected_return",
        "entry_threshold",
        "trade_decision",
        "trade_intent",
        "side",
        "notional",
        "position_size",
        "risk",
        "wallet",
        "order",
        "fill",
        "signer",
        "transaction",
        "realized_pnl",
        "mfe_pct",
        "mae_pct",
    }
    assert field_names.isdisjoint(forbidden)


def test_policy_has_no_production_default_instance_behavior() -> None:
    # Construction is intentionally impossible without every explicit threshold/weight.
    with pytest.raises(TypeError):
        ScorePolicy()  # type: ignore[call-arg]
