from dataclasses import replace

import pytest

from shreks_brain.features import FeatureVector
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import (
    FIRST_PULLBACK_CONFIRMATIONS_REQUIRED,
    FIRST_PULLBACK_SETUP_NAME,
    FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
    FRESH_LAUNCH_SETUP_NAME,
    GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED,
    GRADUATION_BREAKOUT_SETUP_NAME,
    FirstPullbackAssessment,
    FreshLaunchAssessment,
    GraduationBreakoutAssessment,
    SetupState,
)
from shreks_brain.scoring.engine import score_candidate
from shreks_brain.scoring.models import ScorePolicy, ScoreReasonCode


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


def _features(**overrides: object) -> FeatureVector:
    values: dict[str, object] = {
        "schema_version": "b2-v1",
        "as_of_unix_ms": 1_000_000,
        "source_observed_at_unix_ms": 995_000,
        "source_age_ms": 5_000,
        "safety_policy_version": "safety-test",
        "safety_decision": SafetyDecision.PASS,
        "token_age_seconds": 180.0,
        "price_usd": 0.01,
        "liquidity_usd": 55_000.0,
        "liquidity_change_5m_pct": 10.0,
        "exit_price_impact_pct": 4.5,
        "volume_m5_usd": 20_000.0,
        "volume_h1_usd": 80_000.0,
        "volume_velocity_ratio": 1.25,
        "tx_count_m5": 50,
        "tx_count_h1": 200,
        "buy_fraction_m5": 0.55,
        "buy_fraction_h1": 0.52,
        "buy_sell_ratio_m5": 1.22,
        "buy_sell_ratio_h1": 1.08,
        "buy_pressure_acceleration": 0.05,
        "return_1m_pct": 4.0,
        "return_5m_pct": 12.0,
        "return_15m_pct": 20.0,
        "momentum_acceleration_1m_vs_5m": 1.6,
        "distance_from_local_high_pct": -3.0,
        "range_position_pct": 80.0,
        "safety_soft_finding_count": 0,
        "safety_liquidity_weak": False,
        "safety_holder_concentration_elevated": False,
        "safety_creator_concentration_elevated": False,
        "safety_exit_price_impact_elevated": False,
        "missing_features": (),
    }
    values.update(overrides)
    return FeatureVector(**values)


def _fresh_setup(**overrides: object) -> FreshLaunchAssessment:
    values: dict[str, object] = {
        "setup_name": FRESH_LAUNCH_SETUP_NAME,
        "policy_version": "fresh-test",
        "feature_schema_version": "b2-v1",
        "as_of_unix_ms": 1_000_000,
        "state": SetupState.READY,
        "confirmation_score": 80.0,
        "confirmations_passed": 8,
        "confirmations_required": FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
        "findings": (),
    }
    values.update(overrides)
    return FreshLaunchAssessment(**values)


def _graduation_setup(**overrides: object) -> GraduationBreakoutAssessment:
    values: dict[str, object] = {
        "setup_name": GRADUATION_BREAKOUT_SETUP_NAME,
        "policy_version": "graduation-test",
        "feature_schema_version": "b2-v1",
        "as_of_unix_ms": 1_000_000,
        "graduation_mint": "Mint111",
        "graduation_detected_at_unix_ms": 900_000,
        "seconds_since_graduation": 100.0,
        "state": SetupState.READY,
        "confirmation_score": 80.0,
        "confirmations_passed": 7,
        "confirmations_required": GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED,
        "findings": (),
    }
    values.update(overrides)
    return GraduationBreakoutAssessment(**values)


def _pullback_setup(**overrides: object) -> FirstPullbackAssessment:
    values: dict[str, object] = {
        "setup_name": FIRST_PULLBACK_SETUP_NAME,
        "policy_version": "pullback-test",
        "feature_schema_version": "b2-v1",
        "as_of_unix_ms": 1_000_000,
        "state": SetupState.READY,
        "seconds_since_trough": 60.0,
        "impulse_return_pct": 40.0,
        "pullback_depth_pct": 20.0,
        "recovery_from_trough_pct": 10.0,
        "current_vs_peak_pct": -8.0,
        "liquidity_retention_pct": 90.0,
        "buy_fraction_improvement": 0.10,
        "confirmation_score": 80.0,
        "confirmations_passed": 8,
        "confirmations_required": FIRST_PULLBACK_CONFIRMATIONS_REQUIRED,
        "findings": (),
    }
    values.update(overrides)
    return FirstPullbackAssessment(**values)


def _regime(**overrides: object) -> RegimeAssessment:
    values: dict[str, object] = {
        "policy_version": "regime-test",
        "as_of_unix_ms": 1_000_000,
        "source_observed_at_unix_ms": 990_000,
        "window_started_at_unix_ms": 630_000,
        "source_age_ms": 10_000,
        "window_seconds": 360.0,
        "candidate_count": 12,
        "candidate_rate_per_hour": 120.0,
        "executable_fraction": 0.75,
        "median_liquidity_usd": 80_000.0,
        "median_volume_m5_usd": 25_000.0,
        "base_regime": MarketRegime.NORMAL,
        "regime": MarketRegime.NORMAL,
        "performance_sample_count": None,
        "performance_net_expectancy_after_costs_pct": None,
        "performance_applied": False,
        "findings": (),
    }
    values.update(overrides)
    return RegimeAssessment(**values)


def _codes(result: object) -> tuple[ScoreReasonCode, ...]:
    return tuple(finding.code for finding in result.findings)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "features,setup,regime,expected_code",
    [
        (
            _features(schema_version="b2-v2"),
            _fresh_setup(feature_schema_version="b2-v2"),
            _regime(),
            ScoreReasonCode.FEATURE_SCHEMA_UNSUPPORTED,
        ),
        (
            _features(source_observed_at_unix_ms=1_000_001, source_age_ms=-1),
            _fresh_setup(),
            _regime(),
            ScoreReasonCode.FEATURE_SOURCE_AFTER_AS_OF,
        ),
        (
            _features(source_age_ms=6_000),
            _fresh_setup(),
            _regime(),
            ScoreReasonCode.FEATURE_SOURCE_AGE_MISMATCH,
        ),
        (
            _features(),
            _fresh_setup(as_of_unix_ms=999_999),
            _regime(),
            ScoreReasonCode.SETUP_AS_OF_MISMATCH,
        ),
        (
            _features(),
            _fresh_setup(feature_schema_version="other"),
            _regime(),
            ScoreReasonCode.SETUP_FEATURE_SCHEMA_MISMATCH,
        ),
        (
            _features(),
            _fresh_setup(),
            _regime(as_of_unix_ms=999_999),
            ScoreReasonCode.REGIME_AS_OF_MISMATCH,
        ),
    ],
)
def test_compatibility_failures_make_total_unavailable(
    features: FeatureVector,
    setup: FreshLaunchAssessment,
    regime: RegimeAssessment,
    expected_code: ScoreReasonCode,
) -> None:
    result = score_candidate(features, setup, regime, _policy())
    assert result.total_score is None
    assert expected_code in _codes(result)


@pytest.mark.parametrize(
    "volume_velocity,buy_fraction,buy_pressure,expected",
    [
        (0.5, 0.40, -0.10, 0.0),
        (2.0, 0.70, 0.20, 100.0),
        (1.25, 0.55, 0.05, 50.0),
        (0.1, 0.20, -0.50, 0.0),
        (3.0, 0.90, 0.50, 100.0),
    ],
)
def test_money_flow_normalization_is_clamped_piecewise_linear(
    volume_velocity: float,
    buy_fraction: float,
    buy_pressure: float,
    expected: float,
) -> None:
    result = score_candidate(
        _features(
            volume_velocity_ratio=volume_velocity,
            buy_fraction_m5=buy_fraction,
            buy_pressure_acceleration=buy_pressure,
        ),
        _fresh_setup(),
        _regime(),
        _policy(),
    )
    assert result.money_flow_score == pytest.approx(expected)


@pytest.mark.parametrize(
    "liquidity,exit_impact,expected",
    [
        (10_000.0, 8.0, 0.0),
        (100_000.0, 1.0, 100.0),
        (55_000.0, 4.5, 50.0),
        (1_000.0, 20.0, 0.0),
        (200_000.0, 0.1, 100.0),
    ],
)
def test_liquidity_and_exitability_normalization_is_clamped(
    liquidity: float, exit_impact: float, expected: float
) -> None:
    result = score_candidate(
        _features(liquidity_usd=liquidity, exit_price_impact_pct=exit_impact),
        _fresh_setup(),
        _regime(),
        _policy(),
    )
    assert result.liquidity_executability_score == pytest.approx(expected)


@pytest.mark.parametrize(
    "flag_name,expected",
    [
        ("safety_liquidity_weak", 80.0),
        ("safety_holder_concentration_elevated", 75.0),
        ("safety_creator_concentration_elevated", 85.0),
        ("safety_exit_price_impact_elevated", 70.0),
    ],
)
def test_each_soft_safety_flag_applies_only_its_explicit_penalty(
    flag_name: str, expected: float
) -> None:
    result = score_candidate(
        _features(**{flag_name: True}), _fresh_setup(), _regime(), _policy()
    )
    assert result.safety_quality_score == expected
    assert ScoreReasonCode.SAFETY_SOFT_PENALTIES_APPLIED in _codes(result)


def test_soft_safety_penalties_sum_and_clamp_at_zero() -> None:
    result = score_candidate(
        _features(
            safety_liquidity_weak=True,
            safety_holder_concentration_elevated=True,
            safety_creator_concentration_elevated=True,
            safety_exit_price_impact_elevated=True,
        ),
        _fresh_setup(),
        _regime(),
        _policy(
            safety_liquidity_weak_penalty=40.0,
            safety_holder_concentration_elevated_penalty=40.0,
            safety_creator_concentration_elevated_penalty=40.0,
            safety_exit_price_impact_elevated_penalty=40.0,
        ),
    )
    assert result.safety_quality_score == 0.0


def test_soft_finding_count_is_not_double_counted() -> None:
    base = score_candidate(_features(), _fresh_setup(), _regime(), _policy())
    counted = score_candidate(
        _features(safety_soft_finding_count=99),
        _fresh_setup(),
        _regime(),
        _policy(),
    )
    assert counted.safety_quality_score == base.safety_quality_score == 100.0
    assert counted.total_score == base.total_score


def test_canonical_family_scores_and_weighted_total_are_exact() -> None:
    result = score_candidate(_features(), _fresh_setup(), _regime(), _policy())
    assert result.safety_quality_score == 100.0
    assert result.money_flow_score == pytest.approx(50.0)
    assert result.setup_quality_score == 80.0
    assert result.liquidity_executability_score == pytest.approx(50.0)
    assert result.total_score == pytest.approx(69.0)
    assert _codes(result)[-1] is ScoreReasonCode.TOTAL_SCORE_AVAILABLE


@pytest.mark.parametrize(
    "field_name,reason",
    [
        ("volume_velocity_ratio", ScoreReasonCode.VOLUME_VELOCITY_UNKNOWN),
        ("buy_fraction_m5", ScoreReasonCode.BUY_FRACTION_M5_UNKNOWN),
        (
            "buy_pressure_acceleration",
            ScoreReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
        ),
    ],
)
def test_missing_money_flow_evidence_never_zero_fills(
    field_name: str, reason: ScoreReasonCode
) -> None:
    result = score_candidate(
        _features(**{field_name: None}), _fresh_setup(), _regime(), _policy()
    )
    assert result.money_flow_score is None
    assert result.total_score is None
    assert reason in _codes(result)
    assert _codes(result)[-1] is ScoreReasonCode.TOTAL_SCORE_INCOMPLETE


@pytest.mark.parametrize(
    "field_name,reason",
    [
        ("liquidity_usd", ScoreReasonCode.LIQUIDITY_UNKNOWN),
        ("exit_price_impact_pct", ScoreReasonCode.EXIT_PRICE_IMPACT_UNKNOWN),
    ],
)
def test_missing_liquidity_execution_evidence_never_zero_fills(
    field_name: str, reason: ScoreReasonCode
) -> None:
    result = score_candidate(
        _features(**{field_name: None}), _fresh_setup(), _regime(), _policy()
    )
    assert result.liquidity_executability_score is None
    assert result.total_score is None
    assert reason in _codes(result)


def test_missing_zero_weight_family_does_not_block_or_renormalize_total() -> None:
    policy = _policy(
        safety_weight=0.30,
        money_flow_weight=0.0,
        setup_quality_weight=0.40,
        liquidity_executability_weight=0.30,
    )
    result = score_candidate(
        _features(volume_velocity_ratio=None), _fresh_setup(), _regime(), policy
    )
    assert result.money_flow_score is None
    assert result.total_score == pytest.approx(77.0)
    assert _codes(result)[-1] is ScoreReasonCode.TOTAL_SCORE_AVAILABLE


@pytest.mark.parametrize("decision", [SafetyDecision.REJECT, SafetyDecision.INCOMPLETE])
def test_non_pass_safety_can_be_scored_for_research_without_reclassification(
    decision: SafetyDecision,
) -> None:
    result = score_candidate(
        _features(safety_decision=decision), _fresh_setup(), _regime(), _policy()
    )
    assert result.total_score == pytest.approx(69.0)
    assert result.safety_decision is decision
    assert ScoreReasonCode.SAFETY_NOT_PASS_RESEARCH_ONLY in _codes(result)


@pytest.mark.parametrize("state", [SetupState.BLOCKED, SetupState.WATCH])
def test_non_ready_setup_can_be_scored_for_research_without_reclassification(
    state: SetupState,
) -> None:
    result = score_candidate(
        _features(), _fresh_setup(state=state), _regime(), _policy()
    )
    assert result.total_score == pytest.approx(69.0)
    assert result.setup_state is state
    assert ScoreReasonCode.SETUP_NOT_READY_RESEARCH_ONLY in _codes(result)


@pytest.mark.parametrize("market_regime", list(MarketRegime))
def test_regime_is_carried_as_context_but_not_weighted(
    market_regime: MarketRegime,
) -> None:
    result = score_candidate(
        _features(),
        _fresh_setup(),
        _regime(regime=market_regime),
        _policy(),
    )
    assert result.market_regime is market_regime
    assert result.total_score == pytest.approx(69.0)


@pytest.mark.parametrize(
    "setup",
    [_fresh_setup(), _graduation_setup(), _pullback_setup()],
    ids=["fresh_launch", "graduation_breakout", "first_pullback"],
)
def test_all_current_setup_families_pass_through_confirmation_quality(
    setup: FreshLaunchAssessment | GraduationBreakoutAssessment | FirstPullbackAssessment,
) -> None:
    result = score_candidate(_features(), setup, _regime(), _policy())
    assert result.setup_quality_score == setup.confirmation_score == 80.0
    assert result.setup_name == setup.setup_name
    assert result.setup_policy_version == setup.policy_version
    assert result.setup_state is setup.state


def test_findings_have_deterministic_stage_order() -> None:
    result = score_candidate(
        _features(
            safety_decision=SafetyDecision.REJECT,
            volume_velocity_ratio=None,
            buy_fraction_m5=None,
            exit_price_impact_pct=None,
        ),
        _fresh_setup(state=SetupState.WATCH),
        _regime(),
        _policy(),
    )
    assert _codes(result) == (
        ScoreReasonCode.SAFETY_NOT_PASS_RESEARCH_ONLY,
        ScoreReasonCode.SETUP_NOT_READY_RESEARCH_ONLY,
        ScoreReasonCode.VOLUME_VELOCITY_UNKNOWN,
        ScoreReasonCode.BUY_FRACTION_M5_UNKNOWN,
        ScoreReasonCode.EXIT_PRICE_IMPACT_UNKNOWN,
        ScoreReasonCode.TOTAL_SCORE_INCOMPLETE,
    )


def test_equal_inputs_return_equal_assessments() -> None:
    first = score_candidate(_features(), _fresh_setup(), _regime(), _policy())
    second = score_candidate(_features(), _fresh_setup(), _regime(), _policy())
    assert first == second
