use shreks_core::{
    ExecutionCostModel, ExecutionLegCostInput, ExecutionTradeInput, FastBaselineKind,
    FastLaneAction, FastMarketKey, ImpulseScalpExecutionInput, ImpulseScalpPolicy,
    LongerRunnerPolicy, LongerRunnerProtectiveState, VenueId, WalletCohortPolicy,
    WalletCohortPositionInput, DEFAULT_FAST_WINDOWS_MS, EXECUTION_ECONOMICS_VERSION,
    IMPULSE_SCALP_BASELINE_VERSION, LONGER_RUNNER_BASELINE_VERSION,
    WALLET_COHORT_BASELINE_VERSION,
};
use shreks_storage::{
    evaluate_fast_deterministic_lifecycle_batch, FastBaselineCampaignInput,
    FastDeterministicLifecyclePolicy, FastDeterministicLifecyclePostureInput,
    FastDeterministicLifecycleRequest, FastTrainingFeatureRecord, FastTrainingWindowSummary,
    FAST_DETERMINISTIC_LIFECYCLE_VERSION, FAST_TRAINING_FEATURE_SCHEMA_NAME,
    FAST_TRAINING_FEATURE_SCHEMA_VERSION,
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
        local_high_observed_at_unix_ms: Some(980),
        local_low_price_quote: Some(0.0095),
        local_low_sequence: Some(30),
        local_low_observed_at_unix_ms: Some(960),
        post_high_low_price_quote: Some(0.0099),
        post_high_low_sequence: Some(41),
        post_high_low_observed_at_unix_ms: Some(990),
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

fn record(signature: &str, sequence: u64, at: i64) -> FastTrainingFeatureRecord {
    FastTrainingFeatureRecord {
        schema_name: FAST_TRAINING_FEATURE_SCHEMA_NAME,
        schema_version: FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        decision_signature: signature.to_owned(),
        decision_ordinal: 0,
        decision_sequence: sequence,
        mint: "mint-life".to_owned(),
        quote_mint: "quote-life".to_owned(),
        venue: "pump_fun_bonding_curve".to_owned(),
        decision_observed_at_unix_ms: at,
        decision_provider: "helius".to_owned(),
        decision_source_observed_at_unix_ms: at - 1,
        decision_occurred_at_unix_ms: at - 2,
        decision_slot: 100 + sequence,
        decision_event_kind: "buy".to_owned(),
        decision_actor: None,
        decision_executable_entry_price_quote: 0.01,
        decision_entry_total_quote: Some(1.01),
        snapshot_as_of_unix_ms: at,
        snapshot_last_sequence: Some(sequence),
        snapshot_last_price_quote: Some(0.0101),
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: windows(),
    }
}

fn market() -> FastMarketKey {
    FastMarketKey::new(
        "mint-life",
        "quote-life",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap()
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

fn impulse_execution(at: i64) -> ImpulseScalpExecutionInput {
    ImpulseScalpExecutionInput {
        market: market(),
        as_of_unix_ms: at,
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

fn wallet_policy() -> WalletCohortPolicy {
    WalletCohortPolicy {
        version: WALLET_COHORT_BASELINE_VERSION,
        min_support_wallet_count_for_ride: 2,
        min_confidence_weighted_support_for_ride: 1.0,
        min_independent_support_wallet_count_for_ride: 2,
        min_hold_horizon_wallet_weight_for_ride: 1.0,
        reduce_after_median_hold_ratio: 1.0,
        min_confidence_weighted_exit_for_reduce: 1.0,
        min_exit_pressure_ratio_for_reduce: 0.5,
        min_confidence_weighted_exit_for_sell: 2.0,
        min_exit_pressure_ratio_for_sell: 0.8,
        min_independent_exit_wallet_count_for_sell: 2,
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

fn lifecycle_policy(manager: FastBaselineKind) -> FastDeterministicLifecyclePolicy {
    FastDeterministicLifecyclePolicy {
        version: FAST_DETERMINISTIC_LIFECYCLE_VERSION,
        entry_baseline_kind: FastBaselineKind::ImpulseScalp,
        manager_baseline_kind: manager,
        entry_target_exposure_fraction: 0.8,
        reduce_remaining_fraction: 0.5,
    }
}

#[test]
fn valid_explicit_entry_and_manager_policy_evaluates() {
    let record = record("sig-a", 42, 1_100);
    let impulse = impulse_policy();

    let batch = evaluate_fast_deterministic_lifecycle_batch(
        &lifecycle_policy(FastBaselineKind::LongerRunner),
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Flat {
                input: FastBaselineCampaignInput::ImpulseScalp {
                    execution: None,
                    policy: &impulse,
                },
            },
        }],
    )
    .unwrap();

    assert_eq!(batch.version, FAST_DETERMINISTIC_LIFECYCLE_VERSION);
    assert_eq!(batch.policy.entry_baseline_kind, FastBaselineKind::ImpulseScalp);
    assert_eq!(batch.policy.manager_baseline_kind, FastBaselineKind::LongerRunner);
}

#[test]
fn invalid_entry_or_manager_family_fails_closed() {
    let record = record("sig-a", 42, 1_100);
    let impulse = impulse_policy();
    let mut policy = lifecycle_policy(FastBaselineKind::LongerRunner);
    policy.entry_baseline_kind = FastBaselineKind::WalletCohort;

    let error = evaluate_fast_deterministic_lifecycle_batch(
        &policy,
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Flat {
                input: FastBaselineCampaignInput::ImpulseScalp {
                    execution: None,
                    policy: &impulse,
                },
            },
        }],
    )
    .unwrap_err()
    .to_string();

    assert!(error.contains("entry") && error.contains("baseline"), "{error}");

    let mut policy = lifecycle_policy(FastBaselineKind::LongerRunner);
    policy.manager_baseline_kind = FastBaselineKind::MicroPullback;
    let error = evaluate_fast_deterministic_lifecycle_batch(
        &policy,
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Flat {
                input: FastBaselineCampaignInput::ImpulseScalp {
                    execution: None,
                    policy: &impulse,
                },
            },
        }],
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("manager") && error.contains("baseline"), "{error}");
}

#[test]
fn flat_buy_maps_to_explicit_entry_target() {
    let record = record("sig-buy", 42, 1_100);
    let impulse = impulse_policy();
    let execution = impulse_execution(1_100);

    let batch = evaluate_fast_deterministic_lifecycle_batch(
        &lifecycle_policy(FastBaselineKind::LongerRunner),
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Flat {
                input: FastBaselineCampaignInput::ImpulseScalp {
                    execution: Some(&execution),
                    policy: &impulse,
                },
            },
        }],
    )
    .unwrap();

    let decision = &batch.decisions[0];
    assert_eq!(decision.action, FastLaneAction::Buy);
    assert_eq!(decision.current_exposure_fraction, None);
    assert_eq!(decision.target_exposure_fraction, 0.8);
    assert_eq!(decision.component_kind, FastBaselineKind::ImpulseScalp);
}

#[test]
fn flat_skip_maps_to_zero_target() {
    let record = record("sig-skip", 42, 1_100);
    let impulse = impulse_policy();

    let batch = evaluate_fast_deterministic_lifecycle_batch(
        &lifecycle_policy(FastBaselineKind::LongerRunner),
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Flat {
                input: FastBaselineCampaignInput::ImpulseScalp {
                    execution: None,
                    policy: &impulse,
                },
            },
        }],
    )
    .unwrap();

    assert_eq!(batch.decisions[0].action, FastLaneAction::Skip);
    assert_eq!(batch.decisions[0].target_exposure_fraction, 0.0);
}

#[test]
fn open_hold_preserves_authoritative_current_exposure() {
    let record = record("sig-hold", 42, 1_100);
    let wallet = wallet_policy();
    let position = WalletCohortPositionInput {
        market: market(),
        as_of_unix_ms: 1_000,
        opened_at_unix_ms: 900,
    };

    let batch = evaluate_fast_deterministic_lifecycle_batch(
        &lifecycle_policy(FastBaselineKind::WalletCohort),
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Open {
                current_exposure_fraction: 0.75,
                input: FastBaselineCampaignInput::WalletCohort {
                    evidence: None,
                    position: &position,
                    policy: &wallet,
                },
            },
        }],
    )
    .unwrap();

    let decision = &batch.decisions[0];
    assert_eq!(decision.action, FastLaneAction::Hold);
    assert_eq!(decision.current_exposure_fraction, Some(0.75));
    assert_eq!(decision.target_exposure_fraction, 0.75);
}

#[test]
fn open_reduce_applies_explicit_remaining_fraction() {
    let record = record("sig-reduce", 42, 1_100);
    let runner = runner_policy();
    let protective = LongerRunnerProtectiveState {
        market: market(),
        as_of_unix_ms: 1_000,
        hard_stop_triggered: false,
        risk_limit_exit_required: false,
        liquidity_exit_required: false,
    };

    let batch = evaluate_fast_deterministic_lifecycle_batch(
        &lifecycle_policy(FastBaselineKind::LongerRunner),
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Open {
                current_exposure_fraction: 0.8,
                input: FastBaselineCampaignInput::LongerRunner {
                    protective: &protective,
                    continuation: None,
                    policy: &runner,
                },
            },
        }],
    )
    .unwrap();

    let decision = &batch.decisions[0];
    assert_eq!(decision.action, FastLaneAction::Reduce);
    assert_eq!(decision.current_exposure_fraction, Some(0.8));
    assert_eq!(decision.target_exposure_fraction, 0.4);
}

#[test]
fn open_sell_targets_zero() {
    let record = record("sig-sell", 42, 1_100);
    let runner = runner_policy();
    let protective = LongerRunnerProtectiveState {
        market: market(),
        as_of_unix_ms: 1_000,
        hard_stop_triggered: true,
        risk_limit_exit_required: false,
        liquidity_exit_required: false,
    };

    let batch = evaluate_fast_deterministic_lifecycle_batch(
        &lifecycle_policy(FastBaselineKind::LongerRunner),
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Open {
                current_exposure_fraction: 0.8,
                input: FastBaselineCampaignInput::LongerRunner {
                    protective: &protective,
                    continuation: None,
                    policy: &runner,
                },
            },
        }],
    )
    .unwrap();

    assert_eq!(batch.decisions[0].action, FastLaneAction::Sell);
    assert_eq!(batch.decisions[0].target_exposure_fraction, 0.0);
}

#[test]
fn wrong_component_family_for_posture_fails_closed() {
    let record = record("sig-wrong", 42, 1_100);
    let wallet = wallet_policy();
    let position = WalletCohortPositionInput {
        market: market(),
        as_of_unix_ms: 1_000,
        opened_at_unix_ms: 900,
    };

    let error = evaluate_fast_deterministic_lifecycle_batch(
        &lifecycle_policy(FastBaselineKind::LongerRunner),
        &[FastDeterministicLifecycleRequest {
            record: &record,
            posture: FastDeterministicLifecyclePostureInput::Open {
                current_exposure_fraction: 0.8,
                input: FastBaselineCampaignInput::WalletCohort {
                    evidence: None,
                    position: &position,
                    policy: &wallet,
                },
            },
        }],
    )
    .unwrap_err()
    .to_string();

    assert!(error.contains("component") || error.contains("manager"), "{error}");
}

#[test]
fn duplicate_and_per_market_order_regressions_fail_closed() {
    let first = record("same", 42, 1_100);
    let duplicate = record("same", 43, 1_200);
    let regressed_sequence = record("seq", 41, 1_200);
    let regressed_time = record("time", 43, 1_000);
    let impulse = impulse_policy();
    let policy = lifecycle_policy(FastBaselineKind::LongerRunner);

    let request = |record| FastDeterministicLifecycleRequest {
        record,
        posture: FastDeterministicLifecyclePostureInput::Flat {
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &impulse,
            },
        },
    };

    let error = evaluate_fast_deterministic_lifecycle_batch(
        &policy,
        &[request(&first), request(&duplicate)],
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("duplicate"), "{error}");

    let error = evaluate_fast_deterministic_lifecycle_batch(
        &policy,
        &[request(&first), request(&regressed_sequence)],
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("sequence"), "{error}");

    let error = evaluate_fast_deterministic_lifecycle_batch(
        &policy,
        &[request(&first), request(&regressed_time)],
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("timestamp"), "{error}");
}

#[test]
fn identical_lifecycle_batch_is_deterministic() {
    let first = record("sig-a", 42, 1_100);
    let second = record("sig-b", 43, 1_200);
    let impulse = impulse_policy();
    let policy = lifecycle_policy(FastBaselineKind::LongerRunner);
    let requests = [
        FastDeterministicLifecycleRequest {
            record: &first,
            posture: FastDeterministicLifecyclePostureInput::Flat {
                input: FastBaselineCampaignInput::ImpulseScalp {
                    execution: None,
                    policy: &impulse,
                },
            },
        },
        FastDeterministicLifecycleRequest {
            record: &second,
            posture: FastDeterministicLifecyclePostureInput::Flat {
                input: FastBaselineCampaignInput::ImpulseScalp {
                    execution: None,
                    policy: &impulse,
                },
            },
        },
    ];

    let a = evaluate_fast_deterministic_lifecycle_batch(&policy, &requests).unwrap();
    let b = evaluate_fast_deterministic_lifecycle_batch(&policy, &requests).unwrap();
    assert_eq!(a, b);
}

#[test]
fn deterministic_lifecycle_source_has_no_external_execution_authority() {
    let source = include_str!("../src/fast_deterministic_lifecycle.rs");

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
            "deterministic lifecycle must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "evaluate_fast_baseline_campaign",
        "entry_baseline_kind",
        "manager_baseline_kind",
        "entry_target_exposure_fraction",
        "reduce_remaining_fraction",
        "current_exposure_fraction",
        "target_exposure_fraction",
    ] {
        assert!(
            source.contains(required),
            "deterministic lifecycle must preserve explicit composition field: {required}"
        );
    }
}
