use shreks_core::{
    assess_continuous_action, assess_continuous_action_from_champion,
    decode_fast_campaign_decision_batch_json, encode_fast_campaign_decision_results_json,
    evaluate_fast_campaign_decision_batch, predict_fast_forecast, FastActionConstraints,
    FastActionForecastSet, FastActionPositionState, FastCampaignActionConstraintsWire, FastCampaignContinuousActionPolicyWire,
    FastCampaignDecisionBatchWire, FastCampaignDecisionError, FastCampaignDecisionPositionWire,
    FastCampaignDecisionRequestWire, FastCampaignReduceExecutionCostWire,
    FastContinuousActionPolicy, FastForecastArtifact, FastForecastChampion,
    FastForecastChampionMember, FastForecastChampionSelection, FastForecastModelFamily,
    FastForecastTarget, FastForecastTargetKind, FastLaneAction, FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME, FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
    FAST_FORECAST_FEATURE_COUNT, FAST_FORECAST_FEATURE_SCHEMA_VERSION,
};

const HORIZON: u64 = 1_000;

fn artifact(
    target: FastForecastTarget,
    target_kind: FastForecastTargetKind,
    model_family: FastForecastModelFamily,
    prediction: f64,
) -> FastForecastArtifact {
    FastForecastArtifact {
        schema_name: "shreks.fast_lane_forecast_baseline".to_owned(),
        schema_version: 1,
        model_version: format!("fixture-{target:?}"),
        model_family,
        target,
        target_kind,
        horizon_ms: HORIZON,
        feature_schema_version: FAST_FORECAST_FEATURE_SCHEMA_VERSION,
        training_policy_version: "fixture-training".to_owned(),
        training_bundle_fingerprint_sha256: "1".repeat(64),
        future_path_label_version: 1,
        training_row_count: 10,
        target_unavailable_row_count: 0,
        positive_row_count: if target_kind == FastForecastTargetKind::Binary {
            Some(5)
        } else {
            None
        },
        negative_row_count: if target_kind == FastForecastTargetKind::Binary {
            Some(5)
        } else {
            None
        },
        min_training_decision_observed_at_unix_ms: 1,
        max_training_decision_observed_at_unix_ms: 10,
        training_data_fingerprint_sha256: "2".repeat(64),
        feature_transforms: vec![],
        coefficients: vec![],
        intercept: None,
        constant_prediction: Some(prediction),
        artifact_fingerprint_sha256: "3".repeat(64),
    }
}

fn member(target: FastForecastTarget, prediction: f64) -> FastForecastChampionMember {
    let (kind, family) = match target {
        FastForecastTarget::ReversalOccurred
        | FastForecastTarget::RouteUnavailabilityObserved => (
            FastForecastTargetKind::Binary,
            FastForecastModelFamily::PriorClassifier,
        ),
        _ => (
            FastForecastTargetKind::Continuous,
            FastForecastModelFamily::MeanRegressor,
        ),
    };
    FastForecastChampionMember {
        member_key: format!("{target}@{HORIZON}ms"),
        forecast_artifact: artifact(target, kind, family, prediction),
        validation_policy_version: "validation-v1".to_owned(),
        validation_run_fingerprint_sha256: "4".repeat(64),
        test_evaluation_policy_version: "test-v1".to_owned(),
        test_evaluation_report_fingerprint_sha256: "5".repeat(64),
        test_scored_observation_count: 10,
        test_target_unavailable_count: 0,
    }
}

fn champion() -> FastForecastChampion {
    let mut members = vec![
        member(FastForecastTarget::EndpointCostAdjustedReturnBps, 120.0),
        member(FastForecastTarget::EndpointReturnBps, 140.0),
        member(FastForecastTarget::MaeBps, -20.0),
        member(FastForecastTarget::ReversalOccurred, 0.1),
        member(FastForecastTarget::RouteUnavailabilityObserved, 0.05),
    ];
    members.sort_by(|left, right| left.member_key.cmp(&right.member_key));
    FastForecastChampion {
        schema_name: "shreks.fast_lane_forecast_champion".to_owned(),
        schema_version: 1,
        champion_version: "champion-fixture-v1".to_owned(),
        selection: FastForecastChampionSelection {
            decision_reference: "fixture".to_owned(),
            decided_at_unix_ms: 10,
            reason: "fixture".to_owned(),
        },
        feature_schema_version: FAST_FORECAST_FEATURE_SCHEMA_VERSION,
        training_bundle_fingerprint_sha256: "1".repeat(64),
        future_path_label_version: 1,
        members,
        champion_fingerprint_sha256: "a".repeat(64),
    }
}

fn policy() -> FastContinuousActionPolicy {
    FastContinuousActionPolicy {
        version: 1,
        horizons_ms: vec![HORIZON],
        entry_exposure_candidates: vec![0.5, 1.0],
        reduce_target_exposure_candidates: vec![0.5],
        adverse_excursion_weight: 1.0,
        reversal_penalty_bps: 100.0,
        route_unavailability_penalty_bps: 100.0,
        horizon_disagreement_weight: 1.0,
        minimum_buy_value_bps: 1.0,
        minimum_hold_value_bps: 1.0,
        missing_forecast_open_action: FastLaneAction::Sell,
    }
}

fn constraints() -> FastActionConstraints {
    FastActionConstraints {
        max_exposure_fraction: 1.0,
        buy_economically_allowed: true,
        expected_future_exit_cost_bps: 10.0,
        reduce_execution_costs: vec![],
        sell_executable: true,
        sell_now_cost_bps: 10.0,
        force_sell: false,
    }
}

fn features() -> Vec<Option<f64>> {
    vec![Some(1.0); FAST_FORECAST_FEATURE_COUNT]
}

#[test]
fn champion_composition_matches_manual_forecast_set_and_policy() {
    let champion = champion();
    let raw = features();

    let targets = [
        FastForecastTarget::EndpointCostAdjustedReturnBps,
        FastForecastTarget::EndpointReturnBps,
        FastForecastTarget::MaeBps,
        FastForecastTarget::ReversalOccurred,
        FastForecastTarget::RouteUnavailabilityObserved,
    ];
    let predictions = targets
        .into_iter()
        .map(|target| predict_fast_forecast(&champion, target, HORIZON, &raw).unwrap())
        .collect();
    let manual = FastActionForecastSet {
        champion_version: champion.champion_version.clone(),
        champion_fingerprint_sha256: champion.champion_fingerprint_sha256.clone(),
        predictions,
    };
    let expected = assess_continuous_action(
        &policy(),
        &manual,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .unwrap();

    let actual = assess_continuous_action_from_champion(
        &champion,
        &raw,
        &policy(),
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .unwrap();

    assert_eq!(actual, expected);
    assert_eq!(actual.champion_version, "champion-fixture-v1");
    assert_eq!(actual.champion_fingerprint_sha256, "a".repeat(64));
}

#[test]
fn missing_exact_required_member_fails_closed() {
    let mut champion = champion();
    champion
        .members
        .retain(|value| value.forecast_artifact.target != FastForecastTarget::MaeBps);

    let error = assess_continuous_action_from_champion(
        &champion,
        &features(),
        &policy(),
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .unwrap_err();

    assert!(matches!(error, FastCampaignDecisionError::Forecast(_)));
    assert!(error.to_string().contains("mae_bps"));
}

#[test]
fn malformed_feature_vector_fails_closed() {
    let short = vec![Some(1.0); FAST_FORECAST_FEATURE_COUNT - 1];
    let error = assess_continuous_action_from_champion(
        &champion(),
        &short,
        &policy(),
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .unwrap_err();
    assert!(matches!(error, FastCampaignDecisionError::Forecast(_)));

    let mut nonfinite = features();
    nonfinite[3] = Some(f64::NAN);
    let error = assess_continuous_action_from_champion(
        &champion(),
        &nonfinite,
        &policy(),
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .unwrap_err();
    assert!(matches!(error, FastCampaignDecisionError::Forecast(_)));
}

#[test]
fn strict_batch_wire_preserves_identity_and_evaluates_in_order() {
    assert_eq!(
        FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME,
        "shreks.fast_campaign_decision_batch"
    );
    assert_eq!(
        FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
        "shreks.fast_campaign_decision_results"
    );
    assert_eq!(FAST_CAMPAIGN_DECISION_SCHEMA_VERSION, 1);

    let batch = FastCampaignDecisionBatchWire {
        schema_name: FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME.to_owned(),
        schema_version: FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        policy: FastCampaignContinuousActionPolicyWire::from(policy()),
        decisions: vec![
            FastCampaignDecisionRequestWire {
                source_event_id: "sig-a:0".to_owned(),
                market_key: "pump_fun_bonding_curve:mint-a:quote".to_owned(),
                source_sequence: 1,
                as_of_unix_ms: 1_000,
                features: features(),
                position: FastCampaignDecisionPositionWire::Flat,
                constraints: FastCampaignActionConstraintsWire::from(constraints()),
            },
            FastCampaignDecisionRequestWire {
                source_event_id: "sig-b:0".to_owned(),
                market_key: "pump_fun_bonding_curve:mint-a:quote".to_owned(),
                source_sequence: 2,
                as_of_unix_ms: 1_001,
                features: features(),
                position: FastCampaignDecisionPositionWire::Flat,
                constraints: FastCampaignActionConstraintsWire {
                    max_exposure_fraction: 1.0,
                    buy_economically_allowed: true,
                    expected_future_exit_cost_bps: 10.0,
                    reduce_execution_costs: vec![FastCampaignReduceExecutionCostWire {
                        target_exposure_fraction: 0.5,
                        execution_cost_bps: 20.0,
                    }],
                    sell_executable: true,
                    sell_now_cost_bps: 10.0,
                    force_sell: false,
                },
            },
        ],
    };

    let payload = serde_json::to_string(&batch).unwrap();
    let decoded = decode_fast_campaign_decision_batch_json(&payload).unwrap();
    assert_eq!(decoded, batch);

    let results = evaluate_fast_campaign_decision_batch(&champion(), &decoded).unwrap();
    assert_eq!(results.decisions.len(), 2);
    assert_eq!(results.decisions[0].source_event_id, "sig-a:0");
    assert_eq!(results.decisions[1].source_sequence, 2);
    assert_eq!(results.champion_version, "champion-fixture-v1");

    let encoded = encode_fast_campaign_decision_results_json(&results).unwrap();
    assert_eq!(
        encoded,
        encode_fast_campaign_decision_results_json(&results).unwrap()
    );
    assert!(encoded.contains(&results.batch_fingerprint_sha256));
}

#[test]
fn batch_wire_rejects_unknown_duplicate_and_regressing_identity() {
    let unknown = r#"{
        "schema_name":"shreks.fast_campaign_decision_batch",
        "schema_version":1,
        "policy":{},
        "decisions":[],
        "unexpected":true
    }"#;
    assert!(decode_fast_campaign_decision_batch_json(unknown).is_err());

    let request = FastCampaignDecisionRequestWire {
        source_event_id: "dup:0".to_owned(),
        market_key: "pump:mint:quote".to_owned(),
        source_sequence: 2,
        as_of_unix_ms: 2_000,
        features: features(),
        position: FastCampaignDecisionPositionWire::Flat,
        constraints: FastCampaignActionConstraintsWire::from(constraints()),
    };
    let duplicate = FastCampaignDecisionBatchWire {
        schema_name: FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME.to_owned(),
        schema_version: FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        policy: FastCampaignContinuousActionPolicyWire::from(policy()),
        decisions: vec![request.clone(), request],
    };
    let payload = serde_json::to_string(&duplicate).unwrap();
    assert!(decode_fast_campaign_decision_batch_json(&payload).is_err());

    let regressing = FastCampaignDecisionBatchWire {
        schema_name: FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME.to_owned(),
        schema_version: FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        policy: FastCampaignContinuousActionPolicyWire::from(policy()),
        decisions: vec![
            FastCampaignDecisionRequestWire {
                source_event_id: "a:0".to_owned(),
                market_key: "pump:mint:quote".to_owned(),
                source_sequence: 2,
                as_of_unix_ms: 2_000,
                features: features(),
                position: FastCampaignDecisionPositionWire::Flat,
                constraints: FastCampaignActionConstraintsWire::from(constraints()),
            },
            FastCampaignDecisionRequestWire {
                source_event_id: "b:0".to_owned(),
                market_key: "pump:mint:quote".to_owned(),
                source_sequence: 1,
                as_of_unix_ms: 2_001,
                features: features(),
                position: FastCampaignDecisionPositionWire::Flat,
                constraints: FastCampaignActionConstraintsWire::from(constraints()),
            },
        ],
    };
    let payload = serde_json::to_string(&regressing).unwrap();
    assert!(decode_fast_campaign_decision_batch_json(&payload).is_err());
}
