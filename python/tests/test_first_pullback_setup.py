import pytest

from shreks_brain.features import FeatureVector
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups.first_pullback import assess_first_pullback
from shreks_brain.setups.models import (
    FIRST_PULLBACK_CONFIRMATIONS_REQUIRED,
    FirstPullbackPolicy,
    FirstPullbackReasonCode,
    PullbackContext,
    SetupState,
)


def policy(**overrides) -> FirstPullbackPolicy:
    values = {
        "version": "pullback-v1-test",
        "min_seconds_since_trough": 15.0,
        "max_seconds_since_trough": 600.0,
        "max_source_age_ms": 30_000,
        "min_structure_samples": 5,
        "min_initial_impulse_pct": 20.0,
        "min_pullback_depth_pct": 8.0,
        "max_pullback_depth_pct": 35.0,
        "min_recovery_from_trough_pct": 5.0,
        "min_current_vs_peak_pct": -10.0,
        "max_current_vs_peak_pct": 10.0,
        "min_liquidity_retention_pct": 70.0,
        "min_liquidity_usd": 50_000.0,
        "max_exit_price_impact_pct": 5.0,
        "min_tx_count_m5": 50,
        "min_volume_velocity_ratio": 1.2,
        "min_buy_fraction_m5": 0.60,
        "min_buy_fraction_improvement": 0.10,
        "min_buy_pressure_acceleration": 0.05,
        "min_return_1m_pct": 1.0,
        "max_return_1m_pct": 30.0,
    }
    values.update(overrides)
    return FirstPullbackPolicy(**values)


def pullback(**overrides) -> PullbackContext:
    values = {
        "impulse_started_at_unix_ms": 1_000_000,
        "peak_at_unix_ms": 1_120_000,
        "trough_at_unix_ms": 1_240_000,
        "impulse_start_price_usd": 1.0,
        "peak_price_usd": 1.5,
        "trough_price_usd": 1.2,
        "peak_liquidity_usd": 100_000.0,
        "trough_liquidity_usd": 80_000.0,
        "trough_buy_fraction_m5": 0.40,
        "sample_count": 8,
    }
    values.update(overrides)
    return PullbackContext(**values)


def vector(**overrides) -> FeatureVector:
    values = {
        "schema_version": "b2-v1",
        "as_of_unix_ms": 1_310_000,
        "source_observed_at_unix_ms": 1_300_000,
        "source_age_ms": 10_000,
        "safety_policy_version": "safety-v1",
        "safety_decision": SafetyDecision.PASS,
        "token_age_seconds": 900.0,
        "price_usd": 1.44,
        "liquidity_usd": 100_000.0,
        "liquidity_change_5m_pct": 5.0,
        "exit_price_impact_pct": 2.0,
        "volume_m5_usd": 20_000.0,
        "volume_h1_usd": 100_000.0,
        "volume_velocity_ratio": 2.4,
        "tx_count_m5": 100,
        "tx_count_h1": 500,
        "buy_fraction_m5": 0.65,
        "buy_fraction_h1": 0.55,
        "buy_sell_ratio_m5": 1.857142857,
        "buy_sell_ratio_h1": 1.222222222,
        "buy_pressure_acceleration": 0.10,
        "return_1m_pct": 4.0,
        "return_5m_pct": -5.0,
        "return_15m_pct": 30.0,
        "momentum_acceleration_1m_vs_5m": 5.0,
        "distance_from_local_high_pct": -4.0,
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


def codes(result):
    return [finding.code for finding in result.findings]


def test_canonical_first_pullback_is_ready_with_nine_confirmations():
    result = assess_first_pullback(vector(), pullback(), policy())

    assert result.state is SetupState.READY
    assert result.confirmations_passed == FIRST_PULLBACK_CONFIRMATIONS_REQUIRED
    assert result.confirmation_score == 100.0
    assert result.seconds_since_trough == 60.0
    assert result.impulse_return_pct == pytest.approx(50.0)
    assert result.pullback_depth_pct == pytest.approx(20.0)
    assert result.recovery_from_trough_pct == pytest.approx(20.0)
    assert result.current_vs_peak_pct == pytest.approx(-4.0)
    assert result.liquidity_retention_pct == pytest.approx(80.0)
    assert result.buy_fraction_improvement == pytest.approx(0.25)
    assert codes(result) == [FirstPullbackReasonCode.ALL_CONFIRMATIONS_PASSED]


def test_missing_pullback_context_is_watch_and_never_fabricates_structure():
    result = assess_first_pullback(vector(), None, policy())

    assert result.state is SetupState.WATCH
    assert result.seconds_since_trough is None
    assert result.impulse_return_pct is None
    assert result.pullback_depth_pct is None
    assert result.recovery_from_trough_pct is None
    assert result.current_vs_peak_pct is None
    assert result.liquidity_retention_pct is None
    assert result.buy_fraction_improvement is None
    assert result.confirmations_passed == 5
    assert FirstPullbackReasonCode.PULLBACK_NOT_OBSERVED in codes(result)


@pytest.mark.parametrize("decision", [SafetyDecision.REJECT, SafetyDecision.INCOMPLETE])
def test_safety_must_pass_even_when_pullback_confirmations_are_strong(decision):
    result = assess_first_pullback(
        vector(safety_decision=decision), pullback(), policy()
    )
    assert result.state is SetupState.BLOCKED
    assert result.confirmations_passed == 9
    assert FirstPullbackReasonCode.SAFETY_NOT_PASS in codes(result)


def test_future_trough_is_blocked_without_future_structure_leakage():
    result = assess_first_pullback(
        vector(as_of_unix_ms=1_310_000, source_observed_at_unix_ms=1_300_000),
        pullback(
            impulse_started_at_unix_ms=1_250_000,
            peak_at_unix_ms=1_300_000,
            trough_at_unix_ms=1_310_001,
        ),
        policy(),
    )

    assert result.state is SetupState.BLOCKED
    assert FirstPullbackReasonCode.PULLBACK_AFTER_AS_OF in codes(result)
    assert result.seconds_since_trough is None
    assert result.impulse_return_pct is None
    assert result.pullback_depth_pct is None
    assert result.recovery_from_trough_pct is None
    assert result.liquidity_retention_pct is None


def test_trough_newer_than_market_source_is_blocked_without_mixing_later_structure():
    result = assess_first_pullback(
        vector(as_of_unix_ms=1_310_000, source_observed_at_unix_ms=1_300_000),
        pullback(
            impulse_started_at_unix_ms=1_100_000,
            peak_at_unix_ms=1_200_000,
            trough_at_unix_ms=1_305_000,
        ),
        policy(),
    )

    assert result.state is SetupState.BLOCKED
    assert FirstPullbackReasonCode.PULLBACK_AFTER_MARKET_SOURCE in codes(result)
    assert result.seconds_since_trough is None
    assert result.impulse_return_pct is None
    assert result.pullback_depth_pct is None
    assert result.recovery_from_trough_pct is None


def test_insufficient_structure_samples_is_watch():
    result = assess_first_pullback(pullback=pullback(sample_count=4), features=vector(), policy=policy())
    assert result.state is SetupState.WATCH
    assert result.confirmations_passed == 9
    assert FirstPullbackReasonCode.INSUFFICIENT_STRUCTURE_SAMPLES in codes(result)


def test_minimum_trough_age_boundary_passes():
    result = assess_first_pullback(
        vector(source_observed_at_unix_ms=1_255_000, as_of_unix_ms=1_265_000),
        pullback(),
        policy(),
    )
    assert result.seconds_since_trough == 15.0
    assert result.state is SetupState.READY


def test_maximum_trough_age_boundary_passes():
    result = assess_first_pullback(
        vector(source_observed_at_unix_ms=1_840_000, as_of_unix_ms=1_850_000),
        pullback(),
        policy(),
    )
    assert result.seconds_since_trough == 600.0
    assert result.state is SetupState.READY


def test_too_recent_pullback_is_watch():
    result = assess_first_pullback(
        vector(source_observed_at_unix_ms=1_254_999, as_of_unix_ms=1_264_999),
        pullback(),
        policy(),
    )
    assert result.state is SetupState.WATCH
    assert FirstPullbackReasonCode.PULLBACK_TOO_RECENT in codes(result)


def test_expired_pullback_window_is_blocked():
    result = assess_first_pullback(
        vector(source_observed_at_unix_ms=1_840_001, as_of_unix_ms=1_850_001),
        pullback(),
        policy(),
    )
    assert result.state is SetupState.BLOCKED
    assert FirstPullbackReasonCode.PULLBACK_WINDOW_EXPIRED in codes(result)


def test_weak_initial_impulse_is_blocked():
    result = assess_first_pullback(vector(), pullback(), policy(min_initial_impulse_pct=51.0))
    assert result.state is SetupState.BLOCKED
    assert FirstPullbackReasonCode.INITIAL_IMPULSE_TOO_WEAK in codes(result)


def test_pullback_not_deep_enough_is_watch():
    result = assess_first_pullback(vector(), pullback(), policy(min_pullback_depth_pct=21.0))
    assert result.state is SetupState.WATCH
    assert FirstPullbackReasonCode.PULLBACK_NOT_DEEP_ENOUGH in codes(result)


def test_pullback_max_depth_boundary_passes_and_deeper_is_blocked():
    exact_depth = (1 - 1.2 / 1.5) * 100
    at_boundary = assess_first_pullback(
        vector(),
        pullback(),
        policy(max_pullback_depth_pct=exact_depth),
    )
    assert at_boundary.state is SetupState.READY

    too_deep = assess_first_pullback(
        vector(), pullback(), policy(max_pullback_depth_pct=19.9)
    )
    assert too_deep.state is SetupState.BLOCKED
    assert FirstPullbackReasonCode.PULLBACK_TOO_DEEP in codes(too_deep)


def test_price_below_recorded_trough_invalidates_context():
    result = assess_first_pullback(vector(price_usd=1.19), pullback(), policy())
    assert result.state is SetupState.BLOCKED
    assert FirstPullbackReasonCode.PULLBACK_LOW_BROKEN in codes(result)
    assert result.recovery_from_trough_pct is None


def test_breakout_too_far_above_old_peak_is_blocked():
    result = assess_first_pullback(vector(price_usd=1.70), pullback(), policy())
    assert result.state is SetupState.BLOCKED
    assert FirstPullbackReasonCode.BREAKOUT_TOO_EXTENDED in codes(result)
    assert result.current_vs_peak_pct > 10.0


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"source_age_ms": 30_001}, FirstPullbackReasonCode.SOURCE_DATA_TOO_OLD),
        ({"liquidity_usd": 49_999.0}, FirstPullbackReasonCode.LIQUIDITY_BELOW_MINIMUM),
        (
            {"exit_price_impact_pct": 5.01},
            FirstPullbackReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
        ),
        ({"return_1m_pct": 30.01}, FirstPullbackReasonCode.MOVE_TOO_EXTENDED),
    ],
)
def test_current_hard_market_gates_block(overrides, reason):
    result = assess_first_pullback(vector(**overrides), pullback(), policy())
    assert result.state is SetupState.BLOCKED
    assert reason in codes(result)


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("price_usd", FirstPullbackReasonCode.CURRENT_PRICE_UNKNOWN),
        ("liquidity_usd", FirstPullbackReasonCode.LIQUIDITY_UNKNOWN),
        ("exit_price_impact_pct", FirstPullbackReasonCode.EXIT_PRICE_IMPACT_UNKNOWN),
    ],
)
def test_missing_required_current_market_evidence_is_watch(field, reason):
    result = assess_first_pullback(vector(**{field: None}), pullback(), policy())
    assert result.state is SetupState.WATCH
    assert reason in codes(result)


def test_missing_pullback_liquidity_makes_retention_unknown():
    for ctx in (
        pullback(peak_liquidity_usd=None),
        pullback(trough_liquidity_usd=None),
        pullback(peak_liquidity_usd=0.0),
    ):
        result = assess_first_pullback(vector(), ctx, policy())
        assert result.state is SetupState.WATCH
        assert result.liquidity_retention_pct is None
        assert FirstPullbackReasonCode.LIQUIDITY_RETENTION_UNKNOWN in codes(result)


def test_missing_trough_buy_fraction_makes_absorption_unknown():
    result = assess_first_pullback(
        vector(), pullback(trough_buy_fraction_m5=None), policy()
    )
    assert result.state is SetupState.WATCH
    assert result.buy_fraction_improvement is None
    assert FirstPullbackReasonCode.TROUGH_BUY_FRACTION_UNKNOWN in codes(result)
    assert FirstPullbackReasonCode.BUY_FRACTION_IMPROVEMENT_UNKNOWN in codes(result)


@pytest.mark.parametrize(
    ("policy_overrides", "reason"),
    [
        (
            {"min_recovery_from_trough_pct": 20.01},
            FirstPullbackReasonCode.RECOVERY_FROM_TROUGH_BELOW_MINIMUM,
        ),
        (
            {"min_current_vs_peak_pct": -3.99},
            FirstPullbackReasonCode.CURRENT_VS_PEAK_BELOW_MINIMUM,
        ),
        (
            {"min_liquidity_retention_pct": 80.01},
            FirstPullbackReasonCode.LIQUIDITY_RETENTION_BELOW_MINIMUM,
        ),
        ({"min_tx_count_m5": 101}, FirstPullbackReasonCode.TX_COUNT_M5_BELOW_MINIMUM),
        (
            {"min_volume_velocity_ratio": 2.41},
            FirstPullbackReasonCode.VOLUME_VELOCITY_BELOW_MINIMUM,
        ),
        (
            {"min_buy_fraction_m5": 0.651},
            FirstPullbackReasonCode.BUY_FRACTION_M5_BELOW_MINIMUM,
        ),
        (
            {"min_buy_fraction_improvement": 0.251},
            FirstPullbackReasonCode.BUY_FRACTION_IMPROVEMENT_BELOW_MINIMUM,
        ),
        (
            {"min_buy_pressure_acceleration": 0.101},
            FirstPullbackReasonCode.BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM,
        ),
        ({"min_return_1m_pct": 4.01}, FirstPullbackReasonCode.RETURN_1M_BELOW_MINIMUM),
    ],
)
def test_each_failed_confirmation_is_watch_with_eight_of_nine(policy_overrides, reason):
    result = assess_first_pullback(vector(), pullback(), policy(**policy_overrides))
    assert result.state is SetupState.WATCH
    assert result.confirmations_passed == 8
    assert result.confirmation_score == pytest.approx(8 / 9 * 100)
    assert reason in codes(result)


def test_missing_current_price_removes_both_price_structure_confirmations():
    result = assess_first_pullback(vector(price_usd=None), pullback(), policy())
    assert result.confirmations_passed == 7
    assert FirstPullbackReasonCode.RECOVERY_FROM_TROUGH_UNKNOWN in codes(result)
    assert FirstPullbackReasonCode.CURRENT_VS_PEAK_UNKNOWN in codes(result)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"tx_count_m5": None}, FirstPullbackReasonCode.TX_COUNT_M5_UNKNOWN),
        (
            {"volume_velocity_ratio": None},
            FirstPullbackReasonCode.VOLUME_VELOCITY_UNKNOWN,
        ),
        (
            {"buy_pressure_acceleration": None},
            FirstPullbackReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
        ),
        ({"return_1m_pct": None}, FirstPullbackReasonCode.RETURN_1M_UNKNOWN),
    ],
)
def test_independent_missing_current_confirmation_is_unknown(overrides, reason):
    result = assess_first_pullback(vector(**overrides), pullback(), policy())
    assert result.state is SetupState.WATCH
    assert result.confirmations_passed == 8
    assert reason in codes(result)


def test_missing_current_buy_fraction_removes_buy_level_and_absorption_confirmations():
    result = assess_first_pullback(vector(buy_fraction_m5=None), pullback(), policy())
    assert result.state is SetupState.WATCH
    assert result.confirmations_passed == 7
    assert FirstPullbackReasonCode.BUY_FRACTION_M5_UNKNOWN in codes(result)
    assert FirstPullbackReasonCode.BUY_FRACTION_IMPROVEMENT_UNKNOWN in codes(result)


def test_seller_absorption_metric_is_current_buy_fraction_minus_trough_fraction():
    result = assess_first_pullback(
        vector(buy_fraction_m5=0.61),
        pullback(trough_buy_fraction_m5=0.55),
        policy(min_buy_fraction_improvement=0.05),
    )
    assert result.buy_fraction_improvement == pytest.approx(0.06)
    assert result.state is SetupState.READY


def test_equality_at_confirmation_thresholds_passes():
    impulse = (1.5 / 1.0 - 1) * 100
    depth = (1 - 1.2 / 1.5) * 100
    recovery = (1.44 / 1.2 - 1) * 100
    current_vs_peak = (1.44 / 1.5 - 1) * 100
    retention = 80_000.0 / 100_000.0 * 100
    improvement = 0.65 - 0.40

    configured = policy(
        min_initial_impulse_pct=impulse,
        min_pullback_depth_pct=depth,
        max_pullback_depth_pct=depth,
        min_recovery_from_trough_pct=recovery,
        min_current_vs_peak_pct=current_vs_peak,
        max_current_vs_peak_pct=current_vs_peak,
        min_liquidity_retention_pct=retention,
        min_liquidity_usd=100_000.0,
        max_exit_price_impact_pct=2.0,
        min_tx_count_m5=100,
        min_volume_velocity_ratio=2.4,
        min_buy_fraction_m5=0.65,
        min_buy_fraction_improvement=improvement,
        min_buy_pressure_acceleration=0.10,
        min_return_1m_pct=4.0,
        max_return_1m_pct=4.0,
        max_source_age_ms=10_000,
        min_structure_samples=8,
    )

    result = assess_first_pullback(vector(), pullback(), configured)
    assert result.state is SetupState.READY
    assert result.confirmations_passed == 9


def test_blocked_candidate_keeps_confirmation_evidence_for_research():
    result = assess_first_pullback(
        vector(safety_decision=SafetyDecision.REJECT), pullback(), policy()
    )
    assert result.state is SetupState.BLOCKED
    assert result.confirmations_passed == 9
    assert result.confirmation_score == 100.0


def test_multi_finding_order_is_deterministic():
    result = assess_first_pullback(
        vector(
            safety_decision=SafetyDecision.REJECT,
            source_age_ms=30_001,
            liquidity_usd=49_000.0,
            exit_price_impact_pct=6.0,
            return_1m_pct=31.0,
            price_usd=None,
            tx_count_m5=None,
            volume_velocity_ratio=None,
            buy_fraction_m5=None,
            buy_pressure_acceleration=None,
        ),
        pullback(
            peak_liquidity_usd=None,
            trough_buy_fraction_m5=None,
            sample_count=4,
        ),
        policy(min_pullback_depth_pct=21.0),
    )

    assert codes(result) == [
        FirstPullbackReasonCode.SAFETY_NOT_PASS,
        FirstPullbackReasonCode.INSUFFICIENT_STRUCTURE_SAMPLES,
        FirstPullbackReasonCode.PULLBACK_NOT_DEEP_ENOUGH,
        FirstPullbackReasonCode.SOURCE_DATA_TOO_OLD,
        FirstPullbackReasonCode.LIQUIDITY_BELOW_MINIMUM,
        FirstPullbackReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
        FirstPullbackReasonCode.MOVE_TOO_EXTENDED,
        FirstPullbackReasonCode.CURRENT_PRICE_UNKNOWN,
        FirstPullbackReasonCode.LIQUIDITY_RETENTION_UNKNOWN,
        FirstPullbackReasonCode.TROUGH_BUY_FRACTION_UNKNOWN,
        FirstPullbackReasonCode.RECOVERY_FROM_TROUGH_UNKNOWN,
        FirstPullbackReasonCode.CURRENT_VS_PEAK_UNKNOWN,
        FirstPullbackReasonCode.LIQUIDITY_RETENTION_UNKNOWN,
        FirstPullbackReasonCode.TX_COUNT_M5_UNKNOWN,
        FirstPullbackReasonCode.VOLUME_VELOCITY_UNKNOWN,
        FirstPullbackReasonCode.BUY_FRACTION_M5_UNKNOWN,
        FirstPullbackReasonCode.BUY_FRACTION_IMPROVEMENT_UNKNOWN,
        FirstPullbackReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
    ]


def test_repeated_evaluation_is_equal():
    first = assess_first_pullback(vector(), pullback(), policy())
    second = assess_first_pullback(vector(), pullback(), policy())
    assert first == second
