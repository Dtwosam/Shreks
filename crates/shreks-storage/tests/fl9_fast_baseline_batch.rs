use shreks_core::{
    FastBaselineKind, FastBaselinePosture, FastBaselineReplayAssessment, FastMarketKey,
    ImpulseScalpPolicy, LongerRunnerPolicy, LongerRunnerProtectiveState, VenueId,
    DEFAULT_FAST_WINDOWS_MS, IMPULSE_SCALP_BASELINE_VERSION, LONGER_RUNNER_BASELINE_VERSION,
};
use shreks_storage::{
    evaluate_fast_baseline_campaign_batch, FastBaselineCampaignInput,
    FastBaselineCampaignRequest, FastTrainingFeatureRecord, FastTrainingWindowSummary,
    FAST_BASELINE_CAMPAIGN_BATCH_VERSION, FAST_TRAINING_FEATURE_SCHEMA_NAME,
    FAST_TRAINING_FEATURE_SCHEMA_VERSION,
};

fn window(window_ms: u64) -> FastTrainingWindowSummary {
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
        local_high_price_quote: None,
        local_high_sequence: None,
        local_high_observed_at_unix_ms: None,
        local_low_price_quote: None,
        local_low_sequence: None,
        local_low_observed_at_unix_ms: None,
        post_high_low_price_quote: None,
        post_high_low_sequence: None,
        post_high_low_observed_at_unix_ms: None,
        last_price_quote: Some(0.01),
        drawdown_from_local_high: 0.0,
        recovery_from_local_low: 0.0,
    }
}

fn record(signature: &str, sequence: u64, at: i64) -> FastTrainingFeatureRecord {
    FastTrainingFeatureRecord {
        schema_name: FAST_TRAINING_FEATURE_SCHEMA_NAME,
        schema_version: FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        decision_signature: signature.to_owned(),
        decision_ordinal: 0,
        decision_sequence: sequence,
        mint: "mint-batch".to_owned(),
        quote_mint: "quote-batch".to_owned(),
        venue: "pump_fun_bonding_curve".to_owned(),
        decision_observed_at_unix_ms: at,
        decision_provider: "helius".to_owned(),
        decision_source_observed_at_unix_ms: at - 1,
        decision_occurred_at_unix_ms: at - 2,
        decision_slot: 100 + sequence,
        decision_event_kind: "buy".to_owned(),
        decision_actor: None,
        decision_executable_entry_price_quote: 0.01,
        decision_entry_total_quote: Some(1.0),
        snapshot_as_of_unix_ms: at,
        snapshot_last_sequence: Some(sequence),
        snapshot_last_price_quote: Some(0.01),
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: DEFAULT_FAST_WINDOWS_MS.iter().map(|w| window(*w)).collect(),
    }
}

fn impulse_policy() -> ImpulseScalpPolicy {
    ImpulseScalpPolicy {
        version: IMPULSE_SCALP_BASELINE_VERSION,
        signal_window_ms: 500,
        context_window_ms: 2_000,
        min_buy_count: 1,
        min_unique_buy_actors: 1,
        min_count_imbalance: 0.1,
        min_quote_flow_imbalance: 0.1,
        min_quote_flow_velocity_per_second: 0.1,
        min_quote_flow_acceleration_per_second2: 0.1,
        min_velocity_expansion_ratio: 1.0,
        min_recovery_from_local_low: 0.01,
        max_drawdown_from_local_high: 1.0,
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

fn market() -> FastMarketKey {
    FastMarketKey::new(
        "mint-batch",
        "quote-batch",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap()
}

#[test]
fn ordered_batch_preserves_input_order_and_population_identity() {
    let first = record("sig-a", 1, 1_000);
    let second = record("sig-b", 2, 1_100);
    let policy = impulse_policy();

    let requests = [
        FastBaselineCampaignRequest {
            record: &first,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
        FastBaselineCampaignRequest {
            record: &second,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
    ];

    let batch = evaluate_fast_baseline_campaign_batch(&requests).unwrap();

    assert_eq!(batch.version, FAST_BASELINE_CAMPAIGN_BATCH_VERSION);
    assert_eq!(batch.baseline_kind, FastBaselineKind::ImpulseScalp);
    assert_eq!(batch.baseline_version, IMPULSE_SCALP_BASELINE_VERSION);
    assert_eq!(batch.decisions.len(), 2);
    assert_eq!(batch.decisions[0].source_event_id, "sig-a:0");
    assert_eq!(batch.decisions[1].source_event_id, "sig-b:0");
    assert_eq!(batch.decisions[0].source_sequence, 1);
    assert_eq!(batch.decisions[1].source_sequence, 2);
}

#[test]
fn wrong_posture_row_remains_in_batch_as_not_applicable() {
    let first = record("sig-a", 1, 1_000);
    let second = record("sig-b", 2, 1_100);
    let policy = impulse_policy();

    let requests = [
        FastBaselineCampaignRequest {
            record: &first,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
        FastBaselineCampaignRequest {
            record: &second,
            posture: FastBaselinePosture::Open,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
    ];

    let batch = evaluate_fast_baseline_campaign_batch(&requests).unwrap();

    assert_eq!(batch.decisions.len(), 2);
    assert!(matches!(
        batch.decisions[1].assessment,
        FastBaselineReplayAssessment::NotApplicable(_)
    ));
}

#[test]
fn duplicate_source_event_identity_is_rejected() {
    let first = record("sig-a", 1, 1_000);
    let duplicate = record("sig-a", 2, 1_100);
    let policy = impulse_policy();

    let requests = [
        FastBaselineCampaignRequest {
            record: &first,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
        FastBaselineCampaignRequest {
            record: &duplicate,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
    ];

    let error = evaluate_fast_baseline_campaign_batch(&requests)
        .unwrap_err()
        .to_string();
    assert!(error.contains("duplicate"), "{error}");
}

#[test]
fn per_market_sequence_regression_is_rejected() {
    let first = record("sig-a", 2, 1_000);
    let second = record("sig-b", 1, 1_100);
    let policy = impulse_policy();

    let requests = [
        FastBaselineCampaignRequest {
            record: &first,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
        FastBaselineCampaignRequest {
            record: &second,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
    ];

    let error = evaluate_fast_baseline_campaign_batch(&requests)
        .unwrap_err()
        .to_string();
    assert!(error.contains("sequence"), "{error}");
}

#[test]
fn per_market_timestamp_regression_is_rejected() {
    let first = record("sig-a", 1, 1_100);
    let second = record("sig-b", 2, 1_000);
    let policy = impulse_policy();

    let requests = [
        FastBaselineCampaignRequest {
            record: &first,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
        FastBaselineCampaignRequest {
            record: &second,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
    ];

    let error = evaluate_fast_baseline_campaign_batch(&requests)
        .unwrap_err()
        .to_string();
    assert!(error.contains("timestamp"), "{error}");
}

#[test]
fn mixed_baseline_kinds_are_rejected() {
    let first = record("sig-a", 1, 1_000);
    let second = record("sig-b", 2, 1_100);
    let impulse = impulse_policy();
    let runner = runner_policy();
    let protective = LongerRunnerProtectiveState {
        market: market(),
        as_of_unix_ms: 1_100,
        hard_stop_triggered: false,
        risk_limit_exit_required: false,
        liquidity_exit_required: false,
    };

    let requests = [
        FastBaselineCampaignRequest {
            record: &first,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &impulse,
            },
        },
        FastBaselineCampaignRequest {
            record: &second,
            posture: FastBaselinePosture::Open,
            input: FastBaselineCampaignInput::LongerRunner {
                protective: &protective,
                continuation: None,
                policy: &runner,
            },
        },
    ];

    let error = evaluate_fast_baseline_campaign_batch(&requests)
        .unwrap_err()
        .to_string();
    assert!(error.contains("mixed") || error.contains("baseline kind"), "{error}");
}

#[test]
fn identical_batch_evaluation_is_deterministic() {
    let first = record("sig-a", 1, 1_000);
    let second = record("sig-b", 2, 1_100);
    let policy = impulse_policy();

    let requests = [
        FastBaselineCampaignRequest {
            record: &first,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
        FastBaselineCampaignRequest {
            record: &second,
            posture: FastBaselinePosture::Flat,
            input: FastBaselineCampaignInput::ImpulseScalp {
                execution: None,
                policy: &policy,
            },
        },
    ];

    let first_result = evaluate_fast_baseline_campaign_batch(&requests).unwrap();
    let second_result = evaluate_fast_baseline_campaign_batch(&requests).unwrap();

    assert_eq!(first_result, second_result);
}

#[test]
fn baseline_batch_source_has_no_external_execution_authority() {
    let source = include_str!("../src/fast_baseline_batch.rs");

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
            "baseline batch must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "evaluate_fast_baseline_campaign",
        "source_event_id",
        "market_key",
        "source_sequence",
        "as_of_unix_ms",
        "baseline_kind",
    ] {
        assert!(
            source.contains(required),
            "baseline batch must preserve required evidence/order seam: {required}"
        );
    }
}
