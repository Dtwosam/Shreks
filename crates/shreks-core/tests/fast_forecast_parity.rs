use serde::Deserialize;
use shreks_core::{
    load_fast_forecast_champion_json, predict_fast_forecast, FastForecastArtifact,
    FastForecastChampion, FastForecastChampionMember, FastForecastChampionSelection,
    FastForecastFeatureTransform, FastForecastInferenceError, FastForecastModelFamily,
    FastForecastTarget, FastForecastTargetKind, FAST_FORECAST_FEATURE_COUNT,
    FAST_FORECAST_FEATURE_SCHEMA_VERSION,
};

const SPEC_JSON: &str = include_str!("fixtures/fl8_6_parity_spec.json");

#[derive(Debug, Deserialize)]
struct ParitySpec {
    schema_name: String,
    schema_version: u64,
    absolute_tolerance: f64,
    relative_tolerance: f64,
    common: CommonSpec,
    models: Vec<ModelSpec>,
    cases: Vec<CaseSpec>,
}

#[derive(Debug, Deserialize)]
struct CommonSpec {
    champion_version: String,
    decision_reference: String,
    decided_at_unix_ms: u64,
    reason: String,
    feature_schema_version: u64,
    training_bundle_fingerprint_sha256: String,
    future_path_label_version: u64,
    training_policy_version: String,
    training_row_count: u64,
    target_unavailable_row_count: u64,
    min_training_decision_observed_at_unix_ms: u64,
    max_training_decision_observed_at_unix_ms: u64,
    validation_policy_version: String,
    test_evaluation_policy_version: String,
    test_scored_observation_count: u64,
    test_target_unavailable_count: u64,
    transform: TransformSpec,
    champion_fingerprint_sha256: String,
}

#[derive(Debug, Deserialize)]
struct TransformSpec {
    imputation_median: f64,
    mean: f64,
    scale: f64,
}

#[derive(Debug, Deserialize)]
struct ModelSpec {
    member_key: String,
    model_version: String,
    model_family: String,
    target: String,
    target_kind: String,
    horizon_ms: u64,
    training_data_fingerprint_sha256: String,
    positive_row_count: Option<u64>,
    negative_row_count: Option<u64>,
    constant_prediction: Option<f64>,
    intercept: Option<f64>,
    coefficient_overrides: Vec<IndexedValue>,
    artifact_fingerprint_sha256: String,
    validation_run_fingerprint_sha256: String,
    test_evaluation_report_fingerprint_sha256: String,
}

#[derive(Debug, Deserialize)]
struct IndexedValue {
    index: usize,
    value: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct CaseSpec {
    case_id: String,
    default_value: Option<f64>,
    overrides: Vec<IndexedValue>,
    expected: Vec<ExpectedSpec>,
}

#[derive(Debug, Deserialize)]
struct ExpectedSpec {
    member_key: String,
    predicted_value: f64,
    positive_at_half: Option<bool>,
}

fn spec() -> ParitySpec {
    serde_json::from_str(SPEC_JSON).expect("parity spec must be valid JSON")
}

fn family(value: &str) -> FastForecastModelFamily {
    match value {
        "MEAN_REGRESSOR" => FastForecastModelFamily::MeanRegressor,
        "RIDGE_REGRESSION" => FastForecastModelFamily::RidgeRegression,
        "PRIOR_CLASSIFIER" => FastForecastModelFamily::PriorClassifier,
        "LOGISTIC_REGRESSION" => FastForecastModelFamily::LogisticRegression,
        other => panic!("unexpected family {other}"),
    }
}

fn target(value: &str) -> FastForecastTarget {
    match value {
        "endpoint_return_bps" => FastForecastTarget::EndpointReturnBps,
        "mfe_bps" => FastForecastTarget::MfeBps,
        "mae_bps" => FastForecastTarget::MaeBps,
        "best_cost_adjusted_return_bps" => FastForecastTarget::BestCostAdjustedReturnBps,
        "endpoint_cost_adjusted_return_bps" => {
            FastForecastTarget::EndpointCostAdjustedReturnBps
        }
        "reversal_occurred" => FastForecastTarget::ReversalOccurred,
        "route_unavailability_observed" => FastForecastTarget::RouteUnavailabilityObserved,
        other => panic!("unexpected target {other}"),
    }
}

fn target_kind(value: &str) -> FastForecastTargetKind {
    match value {
        "continuous" => FastForecastTargetKind::Continuous,
        "binary" => FastForecastTargetKind::Binary,
        other => panic!("unexpected target kind {other}"),
    }
}

fn feature_names() -> Vec<String> {
    let top = [
        "decision.executable_entry_price_quote",
        "decision.entry_total_quote",
        "snapshot.last_price_quote",
        "decision.is_buy",
        "decision.is_sell",
        "venue.pump_fun_bonding_curve",
        "venue.pump_swap",
        "decision.actor_present",
        "reserve.present",
        "reserve.is_pump_curve",
        "reserve.is_pump_swap_pool",
        "reserve.virtual_base_reserve_raw",
        "reserve.virtual_quote_reserve_raw",
        "reserve.real_base_reserve_raw",
        "reserve.real_quote_reserve_raw",
        "reserve.pool_base_reserve_raw",
        "reserve.pool_quote_reserve_raw",
        "reserve.base_decimals",
        "reserve.quote_decimals",
        "lifecycle.present",
        "lifecycle.detected_age_ms",
        "lifecycle.occurred_age_ms",
    ];
    let window_fields = [
        "buy_count",
        "sell_count",
        "unique_buy_actors",
        "unique_sell_actors",
        "buy_arrival_rate_per_second",
        "sell_arrival_rate_per_second",
        "count_imbalance",
        "buy_base_quantity",
        "sell_base_quantity",
        "buy_quote_quantity",
        "sell_quote_quantity",
        "net_quote_quantity",
        "quote_flow_imbalance",
        "quote_flow_velocity_per_second",
        "quote_flow_acceleration_per_second2",
        "local_high_price_quote",
        "local_low_price_quote",
        "post_high_low_price_quote",
        "last_price_quote",
        "drawdown_from_local_high",
        "recovery_from_local_low",
    ];
    let windows = [100_u64, 250, 500, 1_000, 2_000, 5_000, 10_000];
    let mut result = top.iter().map(|value| (*value).to_string()).collect::<Vec<_>>();
    for window in windows {
        for field in window_fields {
            result.push(format!("w{window}.{field}"));
        }
    }
    assert_eq!(result.len(), FAST_FORECAST_FEATURE_COUNT);
    result
}

fn build_champion(spec: &ParitySpec) -> FastForecastChampion {
    assert_eq!(spec.schema_name, "shreks.fast_lane_forecast_parity_spec");
    assert_eq!(spec.schema_version, 1);
    assert_eq!(spec.common.feature_schema_version, FAST_FORECAST_FEATURE_SCHEMA_VERSION);
    let names = feature_names();
    let mut members = Vec::new();
    for model in &spec.models {
        let model_family = family(&model.model_family);
        let trained = matches!(
            model_family,
            FastForecastModelFamily::RidgeRegression
                | FastForecastModelFamily::LogisticRegression
        );
        let (feature_transforms, coefficients) = if trained {
            let transforms = names
                .iter()
                .map(|name| FastForecastFeatureTransform {
                    feature_name: name.clone(),
                    imputation_median: spec.common.transform.imputation_median,
                    mean: spec.common.transform.mean,
                    scale: spec.common.transform.scale,
                })
                .collect::<Vec<_>>();
            let mut coefficients = vec![0.0; FAST_FORECAST_FEATURE_COUNT];
            for override_value in &model.coefficient_overrides {
                coefficients[override_value.index] = override_value
                    .value
                    .expect("coefficient override cannot be null");
            }
            (transforms, coefficients)
        } else {
            (Vec::new(), Vec::new())
        };
        let artifact = FastForecastArtifact {
            schema_name: "shreks.fast_lane_forecast_baseline".to_string(),
            schema_version: 1,
            model_version: model.model_version.clone(),
            model_family,
            target: target(&model.target),
            target_kind: target_kind(&model.target_kind),
            horizon_ms: model.horizon_ms,
            feature_schema_version: spec.common.feature_schema_version,
            training_policy_version: spec.common.training_policy_version.clone(),
            training_bundle_fingerprint_sha256: spec
                .common
                .training_bundle_fingerprint_sha256
                .clone(),
            future_path_label_version: spec.common.future_path_label_version,
            training_row_count: spec.common.training_row_count,
            target_unavailable_row_count: spec.common.target_unavailable_row_count,
            positive_row_count: model.positive_row_count,
            negative_row_count: model.negative_row_count,
            min_training_decision_observed_at_unix_ms: spec
                .common
                .min_training_decision_observed_at_unix_ms,
            max_training_decision_observed_at_unix_ms: spec
                .common
                .max_training_decision_observed_at_unix_ms,
            training_data_fingerprint_sha256: model.training_data_fingerprint_sha256.clone(),
            feature_transforms,
            coefficients,
            intercept: model.intercept,
            constant_prediction: model.constant_prediction,
            artifact_fingerprint_sha256: model.artifact_fingerprint_sha256.clone(),
        };
        members.push(FastForecastChampionMember {
            member_key: model.member_key.clone(),
            forecast_artifact: artifact,
            validation_policy_version: spec.common.validation_policy_version.clone(),
            validation_run_fingerprint_sha256: model.validation_run_fingerprint_sha256.clone(),
            test_evaluation_policy_version: spec.common.test_evaluation_policy_version.clone(),
            test_evaluation_report_fingerprint_sha256: model
                .test_evaluation_report_fingerprint_sha256
                .clone(),
            test_scored_observation_count: spec.common.test_scored_observation_count,
            test_target_unavailable_count: spec.common.test_target_unavailable_count,
        });
    }
    FastForecastChampion {
        schema_name: "shreks.fast_lane_forecast_champion".to_string(),
        schema_version: 1,
        champion_version: spec.common.champion_version.clone(),
        selection: FastForecastChampionSelection {
            decision_reference: spec.common.decision_reference.clone(),
            decided_at_unix_ms: spec.common.decided_at_unix_ms,
            reason: spec.common.reason.clone(),
        },
        feature_schema_version: spec.common.feature_schema_version,
        training_bundle_fingerprint_sha256: spec.common.training_bundle_fingerprint_sha256.clone(),
        future_path_label_version: spec.common.future_path_label_version,
        members,
        champion_fingerprint_sha256: spec.common.champion_fingerprint_sha256.clone(),
    }
}

fn raw_features(case: &CaseSpec) -> Vec<Option<f64>> {
    let mut values = vec![case.default_value; FAST_FORECAST_FEATURE_COUNT];
    for override_value in &case.overrides {
        values[override_value.index] = override_value.value;
    }
    values
}

fn model_for_key<'a>(spec: &'a ParitySpec, key: &str) -> &'a ModelSpec {
    spec.models
        .iter()
        .find(|model| model.member_key == key)
        .expect("expected member must exist")
}

#[test]
fn rust_loader_reproduces_python_champion_fingerprint() {
    let spec = spec();
    let champion = build_champion(&spec);
    let json = serde_json::to_string(&champion).expect("test champion must serialize");
    let loaded = load_fast_forecast_champion_json(&json).expect("sealed champion must load");
    assert_eq!(
        loaded.champion_fingerprint_sha256,
        spec.common.champion_fingerprint_sha256
    );
    assert_eq!(loaded.members.len(), 4);
}

#[test]
fn all_four_model_families_match_python_reference_cases() {
    let spec = spec();
    let json = serde_json::to_string(&build_champion(&spec)).expect("champion must serialize");
    let champion = load_fast_forecast_champion_json(&json).expect("champion must load");

    for case in &spec.cases {
        let raw = raw_features(case);
        for expected in &case.expected {
            let model = model_for_key(&spec, &expected.member_key);
            let prediction = predict_fast_forecast(
                &champion,
                target(&model.target),
                model.horizon_ms,
                &raw,
            )
            .unwrap_or_else(|error| panic!("{} {} failed: {error}", case.case_id, expected.member_key));
            let tolerance = spec.absolute_tolerance
                + spec.relative_tolerance * expected.predicted_value.abs();
            assert!(
                (prediction.predicted_value - expected.predicted_value).abs() <= tolerance,
                "{} {} expected {}, got {}",
                case.case_id,
                expected.member_key,
                expected.predicted_value,
                prediction.predicted_value,
            );
            if let Some(positive) = expected.positive_at_half {
                assert_eq!(prediction.predicted_value >= 0.5, positive);
            }
        }
    }
}

#[test]
fn tampered_champion_fails_closed_on_fingerprint() {
    let spec = spec();
    let json = serde_json::to_string(&build_champion(&spec)).expect("champion must serialize");
    let tampered = json.replacen("\"constant_prediction\":12.5", "\"constant_prediction\":13.5", 1);
    assert!(matches!(
        load_fast_forecast_champion_json(&tampered),
        Err(FastForecastInferenceError::ChampionFingerprintMismatch)
    ));
}

#[test]
fn unknown_json_field_fails_closed() {
    let spec = spec();
    let json = serde_json::to_string(&build_champion(&spec)).expect("champion must serialize");
    let drifted = format!("{{\"unexpected\":1,{}", &json[1..]);
    assert!(matches!(
        load_fast_forecast_champion_json(&drifted),
        Err(FastForecastInferenceError::Json(_))
    ));
}

#[test]
fn exact_member_lookup_has_no_horizon_fallback() {
    let spec = spec();
    let json = serde_json::to_string(&build_champion(&spec)).expect("champion must serialize");
    let champion = load_fast_forecast_champion_json(&json).expect("champion must load");
    let raw = vec![Some(0.0); FAST_FORECAST_FEATURE_COUNT];
    assert!(matches!(
        predict_fast_forecast(&champion, FastForecastTarget::MfeBps, 251, &raw),
        Err(FastForecastInferenceError::MissingMember { .. })
    ));
}

#[test]
fn wrong_feature_count_and_non_finite_inputs_fail_closed() {
    let spec = spec();
    let json = serde_json::to_string(&build_champion(&spec)).expect("champion must serialize");
    let champion = load_fast_forecast_champion_json(&json).expect("champion must load");
    let short = vec![Some(0.0); FAST_FORECAST_FEATURE_COUNT - 1];
    assert!(matches!(
        predict_fast_forecast(&champion, FastForecastTarget::MfeBps, 250, &short),
        Err(FastForecastInferenceError::FeatureVectorLength { .. })
    ));

    let mut non_finite = vec![Some(0.0); FAST_FORECAST_FEATURE_COUNT];
    non_finite[3] = Some(f64::NAN);
    assert!(matches!(
        predict_fast_forecast(
            &champion,
            FastForecastTarget::MfeBps,
            250,
            &non_finite,
        ),
        Err(FastForecastInferenceError::NonFiniteFeature { index: 3 })
    ));
}
