use shreks_core::{
    replay_fast_baseline, ExecutionCostModel, ExecutionLegCostInput, ExecutionTradeInput,
    FastBaselineKind, FastBaselinePosture, FastBaselineReplayAssessment, FastBaselineReplayInput,
    FastLaneAction, FastMarketKey, FastMarketSnapshot, FastWindowSummary, GraduationFlowPolicy,
    ImpulseScalpExecutionInput, ImpulseScalpPolicy, LongerRunnerPolicy,
    LongerRunnerProtectiveState, VenueId, DEFAULT_FAST_WINDOWS_MS, EXECUTION_ECONOMICS_VERSION,
    GRADUATION_FLOW_BASELINE_VERSION, IMPULSE_SCALP_BASELINE_VERSION,
    LONGER_RUNNER_BASELINE_VERSION,
};
use shreks_storage::{
    evaluate_fast_baseline_campaign, hydrate_fast_baseline_snapshot, FastBaselineCampaignInput,
    FastTrainingFeatureRecord, FastTrainingReserveContext, FastTrainingWindowSummary,
    FAST_BASELINE_CAMPAIGN_VERSION, FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION,
    FAST_TRAINING_FEATURE_SCHEMA_NAME, FAST_TRAINING_FEATURE_SCHEMA_VERSION,
};

fn empty_window(window_ms: u64) -> FastTrainingWindowSummary {
    FastTrainingWindowSummary {
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

fn strong_signal_window() -> FastTrainingWindowSummary {
    let mut value = empty_window(500);
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

fn context_window() -> FastTrainingWindowSummary {
    let mut value = empty_window(2_000);
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

fn windows() -> Vec<FastTrainingWindowSummary> {
    DEFAULT_FAST_WINDOWS_MS
        .iter()
        .map(|window_ms| match *window_ms {
            500 => strong_signal_window(),
            2_000 => context_window(),
            other => empty_window(other),
        })
        .collect()
}

fn record(venue: &str) -> FastTrainingFeatureRecord {
    FastTrainingFeatureRecord {
        schema_name: FAST_TRAINING_FEATURE_SCHEMA_NAME,
        schema_version: FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        decision_signature: "sig-campaign".to_owned(),
        decision_ordinal: 3,
        decision_sequence: 42,
        mint: "mint-campaign".to_owned(),
        quote_mint: "quote-campaign".to_owned(),
        venue: venue.to_owned(),
        decision_observed_at_unix_ms: 10_000,
        decision_provider: "helius".to_owned(),
        decision_source_observed_at_unix_ms: 9_990,
        decision_occurred_at_unix_ms: 9_900,
        decision_slot: 777,
        decision_event_kind: "buy".to_owned(),
        decision_actor: Some("wallet-a".to_owned()),
        decision_executable_entry_price_quote: 0.0100,
        decision_entry_total_quote: Some(1.01),
        snapshot_as_of_unix_ms: 10_000,
        snapshot_last_sequence: Some(42),
        snapshot_last_price_quote: Some(0.0101),
        last_reserve_context: match venue {
            "pump_fun_bonding_curve" => Some(FastTrainingReserveContext::PumpCurve {
                virtual_base_reserve_raw: 1_000_000,
                virtual_quote_reserve_raw: 2_000_000,
                real_base_reserve_raw: 900_000,
                real_quote_reserve_raw: 1_800_000,
                base_decimals: 6,
                quote_decimals: 9,
            }),
            "pump_swap" => Some(FastTrainingReserveContext::PumpSwapPool {
                pool_base_reserve_raw: 500_000,
                pool_quote_reserve_raw: 800_000,
                virtual_quote_reserve_raw: Some(100_000),
                base_decimals: 6,
                quote_decimals: 9,
            }),
            other => panic!("unsupported fixture venue {other}"),
        },
        last_lifecycle_event: None,
        windows: windows(),
    }
}

fn market(venue: VenueId) -> FastMarketKey {
    FastMarketKey::new("mint-campaign", "quote-campaign", venue).unwrap()
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
        market: market(VenueId::PumpFunBondingCurve),
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

fn runner_policy() -> LongerRunnerPolicy {
    LongerRunnerPolicy {
        version: LONGER_RUNNER_BASELINE_VERSION,
        downside_risk_weight: 1.0,
        min_risk_adjusted_continuation_bps_for_hold: 100.0,
        max_risk_adjusted_continuation_bps_for_sell: -100.0,
    }
}

fn graduation_policy() -> GraduationFlowPolicy {
    GraduationFlowPolicy {
        version: GRADUATION_FLOW_BASELINE_VERSION,
        flow_window_ms: 500,
        max_graduation_age_ms: 5_000,
        min_pre_buy_count: 1,
        min_pre_quote_flow_velocity_per_second: 0.1,
        min_post_buy_count: 1,
        min_post_unique_buy_actors: 1,
        min_post_buy_arrival_rate_per_second: 0.1,
        max_post_sell_arrival_rate_per_second: 100.0,
        min_post_count_imbalance: 0.0,
        min_post_quote_flow_imbalance: 0.0,
        min_post_quote_flow_velocity_per_second: 0.1,
        min_post_quote_flow_acceleration_per_second2: 0.0,
        min_post_to_pre_velocity_ratio: 0.1,
    }
}

fn pre_graduation_snapshot() -> FastMarketSnapshot {
    let source = strong_signal_window();
    FastMarketSnapshot {
        market: market(VenueId::PumpFunBondingCurve),
        as_of_unix_ms: 10_000,
        last_sequence: Some(41),
        last_price_quote: Some(0.0100),
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: vec![FastWindowSummary {
            window_ms: source.window_ms,
            buy_count: source.buy_count,
            sell_count: source.sell_count,
            unique_buy_actors: source.unique_buy_actors,
            unique_sell_actors: source.unique_sell_actors,
            buy_arrival_rate_per_second: source.buy_arrival_rate_per_second,
            sell_arrival_rate_per_second: source.sell_arrival_rate_per_second,
            count_imbalance: source.count_imbalance,
            buy_base_quantity: source.buy_base_quantity,
            sell_base_quantity: source.sell_base_quantity,
            buy_quote_quantity: source.buy_quote_quantity,
            sell_quote_quantity: source.sell_quote_quantity,
            net_quote_quantity: source.net_quote_quantity,
            quote_flow_imbalance: source.quote_flow_imbalance,
            quote_flow_velocity_per_second: source.quote_flow_velocity_per_second,
            quote_flow_acceleration_per_second2: source.quote_flow_acceleration_per_second2,
            local_high_price_quote: source.local_high_price_quote,
            local_high_sequence: source.local_high_sequence,
            local_high_observed_at_unix_ms: source.local_high_observed_at_unix_ms,
            local_low_price_quote: source.local_low_price_quote,
            local_low_sequence: source.local_low_sequence,
            local_low_observed_at_unix_ms: source.local_low_observed_at_unix_ms,
            post_high_low_price_quote: source.post_high_low_price_quote,
            post_high_low_sequence: source.post_high_low_sequence,
            post_high_low_observed_at_unix_ms: source.post_high_low_observed_at_unix_ms,
            last_price_quote: source.last_price_quote,
            drawdown_from_local_high: source.drawdown_from_local_high,
            recovery_from_local_low: source.recovery_from_local_low,
        }],
    }
}

#[test]
fn impulse_campaign_preserves_exact_population_identity_and_direct_replay() {
    let record = record("pump_fun_bonding_curve");
    let execution = impulse_execution();
    let policy = impulse_policy();
    let hydration = hydrate_fast_baseline_snapshot(&record).unwrap();
    let expected = replay_fast_baseline(
        FastBaselinePosture::Flat,
        FastBaselineReplayInput::ImpulseScalp {
            snapshot: &hydration.snapshot,
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap();

    let actual = evaluate_fast_baseline_campaign(
        &record,
        FastBaselinePosture::Flat,
        FastBaselineCampaignInput::ImpulseScalp {
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(actual.version, FAST_BASELINE_CAMPAIGN_VERSION);
    assert_eq!(
        actual.hydration_version,
        FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION
    );
    assert_eq!(actual.source_event_id, "sig-campaign:3");
    assert_eq!(
        actual.market_key,
        "pump_fun_bonding_curve:mint-campaign:quote-campaign"
    );
    assert_eq!(actual.source_sequence, 42);
    assert_eq!(actual.as_of_unix_ms, 10_000);
    assert_eq!(actual.posture, FastBaselinePosture::Flat);
    assert_eq!(actual.baseline_kind, FastBaselineKind::ImpulseScalp);
    assert_eq!(actual.baseline_version, IMPULSE_SCALP_BASELINE_VERSION);
    assert_eq!(actual.assessment, expected);
    assert_eq!(actual.assessment.action(), Some(FastLaneAction::Buy));
}

#[test]
fn wrong_posture_remains_explicitly_not_applicable_on_same_population() {
    let record = record("pump_fun_bonding_curve");
    let policy = impulse_policy();

    let actual = evaluate_fast_baseline_campaign(
        &record,
        FastBaselinePosture::Open,
        FastBaselineCampaignInput::ImpulseScalp {
            execution: None,
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(actual.source_event_id, "sig-campaign:3");
    assert_eq!(actual.assessment.action(), None);
    assert!(matches!(
        actual.assessment,
        FastBaselineReplayAssessment::NotApplicable(_)
    ));
}

#[test]
fn applicable_execution_identity_mismatch_fails_closed_through_replay_error() {
    let record = record("pump_fun_bonding_curve");
    let mut execution = impulse_execution();
    execution.market = FastMarketKey::new(
        "different-mint",
        "quote-campaign",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap();
    let policy = impulse_policy();

    let error = evaluate_fast_baseline_campaign(
        &record,
        FastBaselinePosture::Flat,
        FastBaselineCampaignInput::ImpulseScalp {
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap_err()
    .to_string();

    assert!(error.contains("market"), "{error}");
    assert!(error.contains("execution"), "{error}");
}

#[test]
fn longer_runner_open_missing_continuation_preserves_sealed_reduce_behavior() {
    let record = record("pump_fun_bonding_curve");
    let hydration = hydrate_fast_baseline_snapshot(&record).unwrap();
    let protective = LongerRunnerProtectiveState {
        market: hydration.snapshot.market.clone(),
        as_of_unix_ms: hydration.snapshot.as_of_unix_ms,
        hard_stop_triggered: false,
        risk_limit_exit_required: false,
        liquidity_exit_required: false,
    };
    let policy = runner_policy();

    let expected = replay_fast_baseline(
        FastBaselinePosture::Open,
        FastBaselineReplayInput::LongerRunner {
            snapshot: &hydration.snapshot,
            protective: &protective,
            continuation: None,
            policy: &policy,
        },
    )
    .unwrap();

    let actual = evaluate_fast_baseline_campaign(
        &record,
        FastBaselinePosture::Open,
        FastBaselineCampaignInput::LongerRunner {
            protective: &protective,
            continuation: None,
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(actual.assessment, expected);
    assert_eq!(actual.assessment.action(), Some(FastLaneAction::Reduce));
}

#[test]
fn graduation_flow_uses_explicit_pre_snapshot_and_hydrated_row_as_post_snapshot() {
    let record = record("pump_swap");
    let hydration = hydrate_fast_baseline_snapshot(&record).unwrap();
    let pre_snapshot = pre_graduation_snapshot();
    let policy = graduation_policy();

    let expected = replay_fast_baseline(
        FastBaselinePosture::Flat,
        FastBaselineReplayInput::GraduationFlow {
            pre_snapshot: &pre_snapshot,
            post_snapshot: &hydration.snapshot,
            boost_context: None,
            execution: None,
            policy: &policy,
        },
    )
    .unwrap();

    let actual = evaluate_fast_baseline_campaign(
        &record,
        FastBaselinePosture::Flat,
        FastBaselineCampaignInput::GraduationFlow {
            pre_snapshot: &pre_snapshot,
            boost_context: None,
            execution: None,
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(actual.market_key, "pump_swap:mint-campaign:quote-campaign");
    assert_eq!(actual.baseline_kind, FastBaselineKind::GraduationFlow);
    assert_eq!(actual.assessment, expected);
    assert_eq!(actual.assessment.market().venue, VenueId::PumpSwap);
}

#[test]
fn campaign_composition_is_deterministic() {
    let record = record("pump_fun_bonding_curve");
    let execution = impulse_execution();
    let policy = impulse_policy();

    let first = evaluate_fast_baseline_campaign(
        &record,
        FastBaselinePosture::Flat,
        FastBaselineCampaignInput::ImpulseScalp {
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap();
    let second = evaluate_fast_baseline_campaign(
        &record,
        FastBaselinePosture::Flat,
        FastBaselineCampaignInput::ImpulseScalp {
            execution: Some(&execution),
            policy: &policy,
        },
    )
    .unwrap();

    assert_eq!(first, second);
}

#[test]
fn baseline_campaign_source_has_no_io_paper_or_live_authority() {
    let source = include_str!("../src/fast_baseline_campaign.rs");

    for forbidden in [
        "rusqlite",
        "reqwest",
        "std::fs",
        "std::net",
        "shreks_providers",
        "FuturePathLabel",
        "Counterfactual",
        "FastPaper",
        "PaperLedger",
        "RiskContext",
        "TradeIntent",
        "RuntimeMode::Live",
        "Signer",
        "submit_transaction",
        "registry",
        "promote",
    ] {
        assert!(
            !source.contains(forbidden),
            "baseline campaign must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "hydrate_fast_baseline_snapshot",
        "replay_fast_baseline",
        "FastBaselineReplayInput::ImpulseScalp",
        "FastBaselineReplayInput::MicroPullback",
        "FastBaselineReplayInput::PreGraduation",
        "FastBaselineReplayInput::GraduationFlow",
        "FastBaselineReplayInput::WalletCohort",
        "FastBaselineReplayInput::LongerRunner",
        "pre_snapshot",
    ] {
        assert!(
            source.contains(required),
            "baseline campaign must preserve required composition seam: {required}"
        );
    }
}
