import pytest

from shreks_brain.features import FeatureVector
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups.graduation_breakout import assess_graduation_breakout
from shreks_brain.setups.models import (
    GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED,
    GraduationBreakoutPolicy,
    GraduationBreakoutReasonCode,
    GraduationContext,
    SetupState,
)


def policy(**overrides) -> GraduationBreakoutPolicy:
    values = {
        "version": "graduation-v1-test",
        "min_seconds_since_graduation": 30.0,
        "max_seconds_since_graduation": 900.0,
        "max_source_age_ms": 30_000,
        "min_liquidity_usd": 50_000.0,
        "max_exit_price_impact_pct": 5.0,
        "min_tx_count_m5": 50,
        "min_volume_velocity_ratio": 1.2,
        "min_buy_fraction_m5": 0.60,
        "min_buy_pressure_acceleration": 0.05,
        "min_return_1m_pct": 1.0,
        "max_return_1m_pct": 40.0,
        "min_liquidity_change_5m_pct": 0.0,
        "min_distance_from_local_high_pct": -15.0,
        "min_range_position_pct": 60.0,
    }
    values.update(overrides)
    return GraduationBreakoutPolicy(**values)


def graduation(**overrides) -> GraduationContext:
    values = {
        "event_type": "pump_graduation",
        "provider": "helius",
        "mint": "mint-a",
        "quote_mint": "So11111111111111111111111111111111111111112",
        "from_venue": "pump_fun_bonding_curve",
        "to_venue": "pump_swap",
        "pool_address": "pool-a",
        "signature": "sig-a",
        "slot": 123,
        "detected_at_unix_ms": 1_000_000,
        "occurred_at_unix_ms": 999_000,
    }
    values.update(overrides)
    return GraduationContext(**values)


def vector(**overrides) -> FeatureVector:
    values = {
        "schema_version": "b2-v1",
        "as_of_unix_ms": 1_100_000,
        "source_observed_at_unix_ms": 1_090_000,
        "source_age_ms": 10_000,
        "safety_policy_version": "safety-v1",
        "safety_decision": SafetyDecision.PASS,
        "token_age_seconds": 600.0,
        "price_usd": 1.0,
        "liquidity_usd": 100_000.0,
        "liquidity_change_5m_pct": 10.0,
        "exit_price_impact_pct": 2.0,
        "volume_m5_usd": 20_000.0,
        "volume_h1_usd": 100_000.0,
        "volume_velocity_ratio": 2.4,
        "tx_count_m5": 100,
        "tx_count_h1": 500,
        "buy_fraction_m5": 0.75,
        "buy_fraction_h1": 0.60,
        "buy_sell_ratio_m5": 3.0,
        "buy_sell_ratio_h1": 1.5,
        "buy_pressure_acceleration": 0.15,
        "return_1m_pct": 4.0,
        "return_5m_pct": 20.0,
        "return_15m_pct": 30.0,
        "momentum_acceleration_1m_vs_5m": 0.0,
        "distance_from_local_high_pct": -5.0,
        "range_position_pct": 85.0,
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


def test_valid_verified_graduation_with_all_confirmations_is_ready():
    result = assess_graduation_breakout(vector(), graduation(), policy())

    assert result.state is SetupState.READY
    assert result.confirmations_passed == GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED
    assert result.confirmation_score == 100.0
    assert result.graduation_mint == "mint-a"
    assert result.graduation_detected_at_unix_ms == 1_000_000
    assert result.seconds_since_graduation == 100.0
    assert codes(result) == [GraduationBreakoutReasonCode.ALL_CONFIRMATIONS_PASSED]


def test_missing_graduation_is_blocked_but_preserves_feature_confirmation_score():
    result = assess_graduation_breakout(vector(), None, policy())

    assert result.state is SetupState.BLOCKED
    assert result.graduation_mint is None
    assert result.graduation_detected_at_unix_ms is None
    assert result.seconds_since_graduation is None
    assert result.confirmations_passed == 8
    assert result.confirmation_score == 100.0
    assert codes(result) == [GraduationBreakoutReasonCode.GRADUATION_NOT_VERIFIED]


def test_wrong_lifecycle_event_is_blocked():
    result = assess_graduation_breakout(
        vector(), graduation(event_type="pump_creation"), policy()
    )
    assert result.state is SetupState.BLOCKED
    assert GraduationBreakoutReasonCode.GRADUATION_EVENT_NOT_PUMP in codes(result)


@pytest.mark.parametrize(
    "overrides",
    [
        {"from_venue": "other_solana"},
        {"to_venue": "meteora_dlmm"},
        {"from_venue": "pump_swap", "to_venue": "pump_fun_bonding_curve"},
    ],
)
def test_wrong_venue_transition_is_blocked(overrides):
    result = assess_graduation_breakout(vector(), graduation(**overrides), policy())
    assert result.state is SetupState.BLOCKED
    assert GraduationBreakoutReasonCode.GRADUATION_VENUE_TRANSITION_INVALID in codes(
        result
    )


def test_future_local_detection_is_blocked_without_exposing_negative_age():
    result = assess_graduation_breakout(
        vector(as_of_unix_ms=1_100_000),
        graduation(detected_at_unix_ms=1_100_001),
        policy(),
    )

    assert result.state is SetupState.BLOCKED
    assert result.seconds_since_graduation is None
    assert GraduationBreakoutReasonCode.GRADUATION_AFTER_AS_OF in codes(result)


def test_optional_block_time_never_changes_decision_time_or_state():
    features = vector()
    configured = policy()
    early = assess_graduation_breakout(
        features,
        graduation(occurred_at_unix_ms=100_000),
        configured,
    )
    future_metadata = assess_graduation_breakout(
        features,
        graduation(occurred_at_unix_ms=9_000_000),
        configured,
    )

    assert early == future_metadata
    assert early.seconds_since_graduation == 100.0


@pytest.mark.parametrize("decision", [SafetyDecision.REJECT, SafetyDecision.INCOMPLETE])
def test_safety_must_pass_even_when_all_confirmations_are_strong(decision):
    result = assess_graduation_breakout(
        vector(safety_decision=decision), graduation(), policy()
    )

    assert result.state is SetupState.BLOCKED
    assert result.confirmations_passed == 8
    assert GraduationBreakoutReasonCode.SAFETY_NOT_PASS in codes(result)


def test_minimum_graduation_age_boundary_passes():
    result = assess_graduation_breakout(
        vector(as_of_unix_ms=1_030_000), graduation(), policy()
    )
    assert result.state is SetupState.READY
    assert result.seconds_since_graduation == 30.0


def test_maximum_graduation_age_boundary_passes():
    result = assess_graduation_breakout(
        vector(as_of_unix_ms=1_900_000), graduation(), policy()
    )
    assert result.state is SetupState.READY
    assert result.seconds_since_graduation == 900.0


def test_too_recent_graduation_is_watch():
    result = assess_graduation_breakout(
        vector(as_of_unix_ms=1_029_999), graduation(), policy()
    )
    assert result.state is SetupState.WATCH
    assert GraduationBreakoutReasonCode.GRADUATION_TOO_RECENT in codes(result)


def test_expired_post_graduation_window_is_blocked():
    result = assess_graduation_breakout(
        vector(as_of_unix_ms=1_900_001), graduation(), policy()
    )
    assert result.state is SetupState.BLOCKED
    assert GraduationBreakoutReasonCode.POST_GRADUATION_WINDOW_EXPIRED in codes(
        result
    )


def test_stale_source_is_blocked():
    result = assess_graduation_breakout(
        vector(source_age_ms=30_001), graduation(), policy()
    )
    assert result.state is SetupState.BLOCKED
    assert GraduationBreakoutReasonCode.SOURCE_DATA_TOO_OLD in codes(result)


def test_known_liquidity_below_minimum_is_blocked():
    result = assess_graduation_breakout(
        vector(liquidity_usd=49_999.99), graduation(), policy()
    )
    assert result.state is SetupState.BLOCKED
    assert GraduationBreakoutReasonCode.LIQUIDITY_BELOW_MINIMUM in codes(result)


def test_known_exit_price_impact_above_maximum_is_blocked():
    result = assess_graduation_breakout(
        vector(exit_price_impact_pct=5.01), graduation(), policy()
    )
    assert result.state is SetupState.BLOCKED
    assert GraduationBreakoutReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH in codes(result)


def test_excessive_one_minute_move_is_anti_chase_blocked():
    result = assess_graduation_breakout(
        vector(return_1m_pct=40.01), graduation(), policy()
    )
    assert result.state is SetupState.BLOCKED
    assert GraduationBreakoutReasonCode.MOVE_TOO_EXTENDED in codes(result)
    assert result.confirmations_passed == 8


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("liquidity_usd", GraduationBreakoutReasonCode.LIQUIDITY_UNKNOWN),
        (
            "exit_price_impact_pct",
            GraduationBreakoutReasonCode.EXIT_PRICE_IMPACT_UNKNOWN,
        ),
    ],
)
def test_missing_executability_evidence_is_watch(field, reason):
    result = assess_graduation_breakout(vector(**{field: None}), graduation(), policy())
    assert result.state is SetupState.WATCH
    assert reason in codes(result)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        (
            "tx_count_m5",
            49,
            GraduationBreakoutReasonCode.TX_COUNT_M5_BELOW_MINIMUM,
        ),
        (
            "volume_velocity_ratio",
            1.19,
            GraduationBreakoutReasonCode.VOLUME_VELOCITY_BELOW_MINIMUM,
        ),
        (
            "buy_fraction_m5",
            0.59,
            GraduationBreakoutReasonCode.BUY_FRACTION_M5_BELOW_MINIMUM,
        ),
        (
            "buy_pressure_acceleration",
            0.04,
            GraduationBreakoutReasonCode.BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM,
        ),
        (
            "return_1m_pct",
            0.99,
            GraduationBreakoutReasonCode.RETURN_1M_BELOW_MINIMUM,
        ),
        (
            "liquidity_change_5m_pct",
            -0.01,
            GraduationBreakoutReasonCode.LIQUIDITY_CHANGE_5M_BELOW_MINIMUM,
        ),
        (
            "distance_from_local_high_pct",
            -15.01,
            GraduationBreakoutReasonCode.TOO_FAR_BELOW_LOCAL_HIGH,
        ),
        (
            "range_position_pct",
            59.99,
            GraduationBreakoutReasonCode.RANGE_POSITION_BELOW_MINIMUM,
        ),
    ],
)
def test_each_failed_confirmation_is_watch_with_seven_of_eight(field, value, reason):
    result = assess_graduation_breakout(
        vector(**{field: value}), graduation(), policy()
    )
    assert result.state is SetupState.WATCH
    assert result.confirmations_passed == 7
    assert result.confirmation_score == 87.5
    assert reason in codes(result)


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("tx_count_m5", GraduationBreakoutReasonCode.TX_COUNT_M5_UNKNOWN),
        (
            "volume_velocity_ratio",
            GraduationBreakoutReasonCode.VOLUME_VELOCITY_UNKNOWN,
        ),
        ("buy_fraction_m5", GraduationBreakoutReasonCode.BUY_FRACTION_M5_UNKNOWN),
        (
            "buy_pressure_acceleration",
            GraduationBreakoutReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
        ),
        ("return_1m_pct", GraduationBreakoutReasonCode.RETURN_1M_UNKNOWN),
        (
            "liquidity_change_5m_pct",
            GraduationBreakoutReasonCode.LIQUIDITY_CHANGE_5M_UNKNOWN,
        ),
        (
            "distance_from_local_high_pct",
            GraduationBreakoutReasonCode.DISTANCE_FROM_LOCAL_HIGH_UNKNOWN,
        ),
        ("range_position_pct", GraduationBreakoutReasonCode.RANGE_POSITION_UNKNOWN),
    ],
)
def test_each_missing_confirmation_is_watch_and_never_zero_filled(field, reason):
    result = assess_graduation_breakout(
        vector(**{field: None}), graduation(), policy()
    )
    assert result.state is SetupState.WATCH
    assert result.confirmations_passed == 7
    assert result.confirmation_score == 87.5
    assert reason in codes(result)


def test_equality_at_every_numerical_threshold_passes():
    configured = policy()
    features = vector(
        source_age_ms=configured.max_source_age_ms,
        liquidity_usd=configured.min_liquidity_usd,
        exit_price_impact_pct=configured.max_exit_price_impact_pct,
        tx_count_m5=configured.min_tx_count_m5,
        volume_velocity_ratio=configured.min_volume_velocity_ratio,
        buy_fraction_m5=configured.min_buy_fraction_m5,
        buy_pressure_acceleration=configured.min_buy_pressure_acceleration,
        return_1m_pct=configured.min_return_1m_pct,
        liquidity_change_5m_pct=configured.min_liquidity_change_5m_pct,
        distance_from_local_high_pct=configured.min_distance_from_local_high_pct,
        range_position_pct=configured.min_range_position_pct,
        as_of_unix_ms=1_030_000,
    )

    result = assess_graduation_breakout(features, graduation(), configured)

    assert result.state is SetupState.READY
    assert result.confirmations_passed == 8


def test_maximum_return_boundary_is_allowed_by_anti_chase_gate():
    configured = policy()
    result = assess_graduation_breakout(
        vector(return_1m_pct=configured.max_return_1m_pct),
        graduation(),
        configured,
    )
    assert result.state is SetupState.READY


def test_multi_finding_order_is_deterministic_and_matches_evaluation_order():
    result = assess_graduation_breakout(
        vector(
            safety_decision=SafetyDecision.REJECT,
            source_age_ms=30_001,
            liquidity_usd=49_000.0,
            exit_price_impact_pct=6.0,
            return_1m_pct=41.0,
            tx_count_m5=None,
            volume_velocity_ratio=None,
            buy_fraction_m5=None,
            buy_pressure_acceleration=None,
            liquidity_change_5m_pct=None,
            distance_from_local_high_pct=None,
            range_position_pct=None,
        ),
        graduation(
            event_type="other",
            from_venue="other_solana",
            to_venue="meteora_dlmm",
            detected_at_unix_ms=1_100_001,
        ),
        policy(),
    )

    assert codes(result) == [
        GraduationBreakoutReasonCode.SAFETY_NOT_PASS,
        GraduationBreakoutReasonCode.GRADUATION_EVENT_NOT_PUMP,
        GraduationBreakoutReasonCode.GRADUATION_VENUE_TRANSITION_INVALID,
        GraduationBreakoutReasonCode.GRADUATION_AFTER_AS_OF,
        GraduationBreakoutReasonCode.SOURCE_DATA_TOO_OLD,
        GraduationBreakoutReasonCode.LIQUIDITY_BELOW_MINIMUM,
        GraduationBreakoutReasonCode.EXIT_PRICE_IMPACT_TOO_HIGH,
        GraduationBreakoutReasonCode.MOVE_TOO_EXTENDED,
        GraduationBreakoutReasonCode.TX_COUNT_M5_UNKNOWN,
        GraduationBreakoutReasonCode.VOLUME_VELOCITY_UNKNOWN,
        GraduationBreakoutReasonCode.BUY_FRACTION_M5_UNKNOWN,
        GraduationBreakoutReasonCode.BUY_PRESSURE_ACCELERATION_UNKNOWN,
        GraduationBreakoutReasonCode.LIQUIDITY_CHANGE_5M_UNKNOWN,
        GraduationBreakoutReasonCode.DISTANCE_FROM_LOCAL_HIGH_UNKNOWN,
        GraduationBreakoutReasonCode.RANGE_POSITION_UNKNOWN,
    ]


def test_repeated_evaluation_is_equal():
    first = assess_graduation_breakout(vector(), graduation(), policy())
    second = assess_graduation_breakout(vector(), graduation(), policy())
    assert first == second


def test_cross_regime_five_minute_momentum_fields_do_not_change_b4b_decision():
    low = assess_graduation_breakout(
        vector(return_5m_pct=-90.0, momentum_acceleration_1m_vs_5m=-100.0),
        graduation(),
        policy(),
    )
    high = assess_graduation_breakout(
        vector(return_5m_pct=1_000.0, momentum_acceleration_1m_vs_5m=1_000.0),
        graduation(),
        policy(),
    )

    assert low == high
    assert low.state is SetupState.READY
