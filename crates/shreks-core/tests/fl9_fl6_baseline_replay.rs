use shreks_core::{
    assess_impulse_scalp, assess_longer_runner, replay_fast_baseline, ExecutionCostModel,
    ExecutionLegCostInput, ExecutionTradeInput, FastBaselineKind, FastBaselinePosture,
    FastBaselineReplayAssessment, FastBaselineReplayInput, FastLaneAction, FastMarketKey,
    FastMarketSnapshot, FastWindowSummary, ImpulseScalpExecutionInput, ImpulseScalpPolicy,
    LongerRunnerPolicy, LongerRunnerProtectiveState, VenueId, EXECUTION_ECONOMICS_VERSION,
    FAST_BASELINE_REPLAY_VERSION, IMPULSE_SCALP_BASELINE_VERSION, LONGER_RUNNER_BASELINE_VERSION,
};

fn market() -> FastMarketKey {
    FastMarketKey::new("mint-replay", "quote-replay", VenueId::PumpFunBondingCurve).unwrap()
}

fn window(window_ms: u64) -> FastWindowSummary {
    FastWindowSummary {
        window_ms,
        buy_count: 0,
        sell_count: 0,
        unique_buy_actors: 0,
        unique_sell_actors: 0,
        buy_arrival_rate_per_second: 0.0,
        sell_arrival_rate_per_second: 0.0,
        count_imbalance: 0.0,
        buy_base_quantity: 0.0,
        sell_base_quantity: 0.0,
        buy_quote_quantity: 0.0,
        sell_quote_quantity: 0.0,
        net_quote_quantity: 0.0,
        quote_flow_imbalance: 0.0,
        quote_flow_velocity_per_second: 0.0,
        quote_flow_acceleration_per_second2: 0.0,
        local_high_price_quote: Some(0.0102),
        local_high_sequence: Some(40),
        local_high_observed_at_unix_ms: Some(9_800),
        local_low_price_quote: Some(0.0095),
        local_low_sequence: Some(30),
        local_low_observed_at_unix_ms: Some(9_600),
        post_high_low_price_quote: Some(0.0099),
        post_high_low_sequence: Some(41),
        post_high_low_observed_at_unix_ms: Some(9_900),
        last_price_quote: Some(0.0101),
        drawdown_from_local_high: 0.009_803_921_568_627_45,
        recovery_from_local_low: 0.063_157_894_736_842_1,
    }
}

fn signal_window() -> FastWindowSummary {
    let mut value = window(500);
    value.buy_count = 8;
    value.sell_count = 2;
    value.unique_buy_actors = 6;
    value.unique_sell_actors = 2;
    value.buy_arrival_rate_per_second = 16.0;
    value.sell_arrival_rate_per_second = 4.0;
    value.count_imbalance = 0.6;
    value.buy_quote_quantity = 4.5;
    value.sell_quote_quantity = 0.8;
    value.net_quote_quantity = 3.7;
    value.quote_flow_imbalance = 3.7 / 5.3;
    value.quote_flow_velocity_per_second = 7.4;
    value.quote_flow_acceleration_per_second2 = 12.0;
    value
}

fn context_window() -> FastWindowSummary {
    let mut value = window(2_000);
    value.buy_count = 12;
    value.sell_count = 8;
    value.unique_buy_actors = 8;
    value.unique_sell_actors = 6;
    value.count_imbalance = 0.2;
    value.buy_quote_quantity = 7.0;
    value.sell_quote_quantity = 3.0;
    value.net_quote_quantity = 4.0;
    value.quote_flow_imbalance = 0.4;
    value.quote_flow_velocity_per_second = 2.0;
    value.quote_flow_acceleration_per_second2 = 1.0;
    value
}

fn snapshot() -> FastMarketSnapshot {
    FastMarketSnapshot {
        market: market(),
        as_of_unix_ms: 10_000,
        last_sequence: Some(42),
        last_price_quote: Some(0.0101),
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: vec![signal_window(), context_window()],
    }
}

fn impulse_policy() -> ImpulseScalpPolicy {
    ImpulseScalpPolicy {
        version: IMPULSE_SCALP_BASELINE_VERSION,
        signal_window_ms: 500,
        context_window_ms: 2_000,
        min_buy_count: 5,
        min_unique_buy_actors: 4,
        min_count_imbalance: 0.50,
        min_quote_flow_imbalance: 0.50,
        min_quote_flow_velocity_per_second: 3.0,
        min_quote_flow_acceleration_per_second2: 5.0,
        min_velocity_expansion_ratio: 2.0,
        min_recovery_from_local_low: 0.02,
        max_drawdown_from_local_high: 0.03,
    }
}

fn leg() -> ExecutionLegCostInput {
    ExecutionLegCostInput {
        effective_fee_bps: 50,
        expected_impact_bps: 20,
        expected_slippage_bps: 20,
        expected_latency_bps: 10,
        network_fee_quote: 0.0001,
        priority_fee_quote: 0.0,
        expected_failure_cost_quote: 0.0,
    }
}

fn impulse_execution() -> ImpulseScalpExecutionInput {
    ImpulseScalpExecutionInput {
        market: market(),
        as_of_unix_ms: 10_000,
        cost_model: ExecutionCostModel {
            version: EXECUTION_ECONOMICS_VERSION,
            entry: leg(),
            exit: leg(),
        },
        trade: ExecutionTradeInput {
            base_quantity: 100.0,
            executable_entry_price_quote: 0.0100,
            forecast_exit_price_quote: 0.0120,
            exit_capacity_base: 125.0,
            required_edge_bps: 200,
            risk_margin_bps: 100,
        },
    }
}

fn runner_policy() -> LongerRunnerPolicy {
    LongerRunnerPolicy {
        version: LONGER_RUNNER_BASELINE_VERSION,
        downside_risk_weight: 1.0,
        min_risk_adjusted_continuation_bps_for_hold: 100.0,
        max_risk_adjusted_continuation_bps_for_sell: -100.0,
    }
}

fn protective() -> LongerRunnerProtectiveState {
    LongerRunnerProtectiveState {
        market: market(),
        as_of_unix_ms: 10_000,
        hard_stop_triggered: false,
        risk_limit_exit_required: false,
        liquidity_exit_required: false,
    }
}

#[test]
fn flat_impulse_replay_delegates_to_the_sealed_baseline_exactly() {
    let snapshot = snapshot();
    let execution = impulse_execution();
    let policy = impulse_policy();
    let expected = assess_impulse_scalp(&snapshot, Some(&execution), &policy).unwrap();

    let replay = replay_fast_baseline(
        FastBaselinePosture::Flat,
        FastBaselineReplayInput::ImpulseScalp {
            snapshot: &snapshot,
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(replay.version(), FAST_BASELINE_REPLAY_VERSION);
    assert_eq!(replay.baseline_kind(), FastBaselineKind::ImpulseScalp);
    assert_eq!(replay.baseline_version(), IMPULSE_SCALP_BASELINE_VERSION);
    assert_eq!(replay.action(), Some(FastLaneAction::Buy));
    assert_eq!(replay.market(), &market());
    assert_eq!(replay.as_of_unix_ms(), 10_000);

    match replay {
        FastBaselineReplayAssessment::ImpulseScalp(actual) => assert_eq!(actual, expected),
        other => panic!("expected exact impulse assessment, got {other:?}"),
    }
}

#[test]
fn entry_baseline_on_open_posture_is_explicitly_not_applicable() {
    let snapshot = snapshot();
    let execution = impulse_execution();
    let policy = impulse_policy();

    let replay = replay_fast_baseline(
        FastBaselinePosture::Open,
        FastBaselineReplayInput::ImpulseScalp {
            snapshot: &snapshot,
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(replay.action(), None);
    match replay {
        FastBaselineReplayAssessment::NotApplicable(value) => {
            assert_eq!(value.version, FAST_BASELINE_REPLAY_VERSION);
            assert_eq!(value.baseline_kind, FastBaselineKind::ImpulseScalp);
            assert_eq!(value.baseline_version, IMPULSE_SCALP_BASELINE_VERSION);
            assert_eq!(value.actual_posture, FastBaselinePosture::Open);
            assert_eq!(value.required_posture, FastBaselinePosture::Flat);
            assert_eq!(value.market, market());
            assert_eq!(value.as_of_unix_ms, 10_000);
        }
        other => panic!("expected not-applicable assessment, got {other:?}"),
    }
}

#[test]
fn open_position_baseline_on_flat_posture_is_explicitly_not_applicable() {
    let snapshot = snapshot();
    let protective = protective();
    let policy = runner_policy();

    let replay = replay_fast_baseline(
        FastBaselinePosture::Flat,
        FastBaselineReplayInput::LongerRunner {
            snapshot: &snapshot,
            protective: &protective,
            continuation: None,
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(replay.baseline_kind(), FastBaselineKind::LongerRunner);
    assert_eq!(replay.baseline_version(), LONGER_RUNNER_BASELINE_VERSION);
    assert_eq!(replay.action(), None);
    match replay {
        FastBaselineReplayAssessment::NotApplicable(value) => {
            assert_eq!(value.actual_posture, FastBaselinePosture::Flat);
            assert_eq!(value.required_posture, FastBaselinePosture::Open);
        }
        other => panic!("expected not-applicable assessment, got {other:?}"),
    }
}

#[test]
fn open_longer_runner_replay_preserves_missing_continuation_reduce_behavior() {
    let snapshot = snapshot();
    let protective = protective();
    let policy = runner_policy();
    let expected = assess_longer_runner(&snapshot, &protective, None, &policy).unwrap();

    let replay = replay_fast_baseline(
        FastBaselinePosture::Open,
        FastBaselineReplayInput::LongerRunner {
            snapshot: &snapshot,
            protective: &protective,
            continuation: None,
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(replay.action(), Some(FastLaneAction::Reduce));
    match replay {
        FastBaselineReplayAssessment::LongerRunner(actual) => assert_eq!(actual, expected),
        other => panic!("expected exact longer-runner assessment, got {other:?}"),
    }
}

#[test]
fn replay_is_deterministic_for_identical_inputs() {
    let snapshot = snapshot();
    let execution = impulse_execution();
    let policy = impulse_policy();

    let first = replay_fast_baseline(
        FastBaselinePosture::Flat,
        FastBaselineReplayInput::ImpulseScalp {
            snapshot: &snapshot,
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap();
    let second = replay_fast_baseline(
        FastBaselinePosture::Flat,
        FastBaselineReplayInput::ImpulseScalp {
            snapshot: &snapshot,
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(first, second);
}

#[test]
fn baseline_replay_source_has_no_external_or_execution_authority() {
    let source = include_str!("../src/fast_lane/baseline_replay.rs");

    for forbidden in [
        "reqwest",
        "rusqlite",
        "std::fs",
        "std::net",
        "tokio",
        "Paper",
        "TradeIntent",
        "RuntimeMode::Live",
        "sign",
        "submit",
        "provider",
    ] {
        assert!(
            !source.contains(forbidden),
            "baseline replay must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "assess_impulse_scalp",
        "assess_micro_pullback",
        "assess_pre_graduation_acceleration",
        "assess_graduation_flow",
        "assess_wallet_cohort_ride_fade",
        "assess_longer_runner",
    ] {
        assert!(
            source.contains(required),
            "baseline replay must delegate to sealed evaluator: {required}"
        );
    }
}
