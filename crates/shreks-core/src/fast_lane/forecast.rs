use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{error::Error, fmt};

pub const FAST_FORECAST_FEATURE_SCHEMA_VERSION: u64 = 1;
pub const FAST_FORECAST_FEATURE_COUNT: usize = 169;

const CHAMPION_SCHEMA_NAME: &str = "shreks.fast_lane_forecast_champion";
const CHAMPION_SCHEMA_VERSION: u64 = 1;
const ARTIFACT_SCHEMA_NAME: &str = "shreks.fast_lane_forecast_baseline";
const ARTIFACT_SCHEMA_VERSION: u64 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FastForecastModelFamily {
    #[serde(rename = "MEAN_REGRESSOR")]
    MeanRegressor,
    #[serde(rename = "RIDGE_REGRESSION")]
    RidgeRegression,
    #[serde(rename = "PRIOR_CLASSIFIER")]
    PriorClassifier,
    #[serde(rename = "LOGISTIC_REGRESSION")]
    LogisticRegression,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FastForecastTarget {
    #[serde(rename = "endpoint_return_bps")]
    EndpointReturnBps,
    #[serde(rename = "mfe_bps")]
    MfeBps,
    #[serde(rename = "mae_bps")]
    MaeBps,
    #[serde(rename = "best_cost_adjusted_return_bps")]
    BestCostAdjustedReturnBps,
    #[serde(rename = "endpoint_cost_adjusted_return_bps")]
    EndpointCostAdjustedReturnBps,
    #[serde(rename = "reversal_occurred")]
    ReversalOccurred,
    #[serde(rename = "route_unavailability_observed")]
    RouteUnavailabilityObserved,
}

impl FastForecastTarget {
    fn as_str(self) -> &'static str {
        match self {
            Self::EndpointReturnBps => "endpoint_return_bps",
            Self::MfeBps => "mfe_bps",
            Self::MaeBps => "mae_bps",
            Self::BestCostAdjustedReturnBps => "best_cost_adjusted_return_bps",
            Self::EndpointCostAdjustedReturnBps => "endpoint_cost_adjusted_return_bps",
            Self::ReversalOccurred => "reversal_occurred",
            Self::RouteUnavailabilityObserved => "route_unavailability_observed",
        }
    }

    fn kind(self) -> FastForecastTargetKind {
        match self {
            Self::ReversalOccurred | Self::RouteUnavailabilityObserved => {
                FastForecastTargetKind::Binary
            }
            _ => FastForecastTargetKind::Continuous,
        }
    }
}

impl fmt::Display for FastForecastTarget {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FastForecastTargetKind {
    #[serde(rename = "continuous")]
    Continuous,
    #[serde(rename = "binary")]
    Binary,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastForecastFeatureTransform {
    pub feature_name: String,
    pub imputation_median: f64,
    pub mean: f64,
    pub scale: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastForecastArtifact {
    pub schema_name: String,
    pub schema_version: u64,
    pub model_version: String,
    pub model_family: FastForecastModelFamily,
    pub target: FastForecastTarget,
    pub target_kind: FastForecastTargetKind,
    pub horizon_ms: u64,
    pub feature_schema_version: u64,
    pub training_policy_version: String,
    pub training_bundle_fingerprint_sha256: String,
    pub future_path_label_version: u64,
    pub training_row_count: u64,
    pub target_unavailable_row_count: u64,
    pub positive_row_count: Option<u64>,
    pub negative_row_count: Option<u64>,
    pub min_training_decision_observed_at_unix_ms: u64,
    pub max_training_decision_observed_at_unix_ms: u64,
    pub training_data_fingerprint_sha256: String,
    pub feature_transforms: Vec<FastForecastFeatureTransform>,
    pub coefficients: Vec<f64>,
    pub intercept: Option<f64>,
    pub constant_prediction: Option<f64>,
    pub artifact_fingerprint_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastForecastChampionSelection {
    pub decision_reference: String,
    pub decided_at_unix_ms: u64,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastForecastChampionMember {
    pub member_key: String,
    pub forecast_artifact: FastForecastArtifact,
    pub validation_policy_version: String,
    pub validation_run_fingerprint_sha256: String,
    pub test_evaluation_policy_version: String,
    pub test_evaluation_report_fingerprint_sha256: String,
    pub test_scored_observation_count: u64,
    pub test_target_unavailable_count: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastForecastChampion {
    pub schema_name: String,
    pub schema_version: u64,
    pub champion_version: String,
    pub selection: FastForecastChampionSelection,
    pub feature_schema_version: u64,
    pub training_bundle_fingerprint_sha256: String,
    pub future_path_label_version: u64,
    pub members: Vec<FastForecastChampionMember>,
    pub champion_fingerprint_sha256: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastForecastPrediction {
    pub model_version: String,
    pub target: FastForecastTarget,
    pub horizon_ms: u64,
    pub predicted_value: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum FastForecastInferenceError {
    Json(String),
    InvalidChampion(String),
    ChampionFingerprintMismatch,
    FeatureVectorLength { expected: usize, actual: usize },
    NonFiniteFeature { index: usize },
    MissingMember { target: FastForecastTarget, horizon_ms: u64 },
    NonFinitePrediction,
}

impl fmt::Display for FastForecastInferenceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(message) => write!(formatter, "forecast champion JSON error: {message}"),
            Self::InvalidChampion(message) => {
                write!(formatter, "invalid forecast champion: {message}")
            }
            Self::ChampionFingerprintMismatch => {
                formatter.write_str("forecast champion fingerprint mismatch")
            }
            Self::FeatureVectorLength { expected, actual } => write!(
                formatter,
                "forecast feature vector length mismatch: expected {expected}, got {actual}"
            ),
            Self::NonFiniteFeature { index } => {
                write!(formatter, "forecast feature at index {index} is non-finite")
            }
            Self::MissingMember { target, horizon_ms } => write!(
                formatter,
                "forecast champion has no exact member for {target}@{horizon_ms}ms"
            ),
            Self::NonFinitePrediction => formatter.write_str("forecast prediction is non-finite"),
        }
    }
}

impl Error for FastForecastInferenceError {}

pub fn load_fast_forecast_champion_json(
    input: &str,
) -> Result<FastForecastChampion, FastForecastInferenceError> {
    let champion: FastForecastChampion = serde_json::from_str(input)
        .map_err(|error| FastForecastInferenceError::Json(error.to_string()))?;
    validate_champion(&champion)?;
    let expected = champion_fingerprint_sha256(&champion)?;
    if expected != champion.champion_fingerprint_sha256 {
        return Err(FastForecastInferenceError::ChampionFingerprintMismatch);
    }
    Ok(champion)
}

pub fn predict_fast_forecast(
    champion: &FastForecastChampion,
    target: FastForecastTarget,
    horizon_ms: u64,
    raw_features: &[Option<f64>],
) -> Result<FastForecastPrediction, FastForecastInferenceError> {
    if raw_features.len() != FAST_FORECAST_FEATURE_COUNT {
        return Err(FastForecastInferenceError::FeatureVectorLength {
            expected: FAST_FORECAST_FEATURE_COUNT,
            actual: raw_features.len(),
        });
    }
    for (index, value) in raw_features.iter().enumerate() {
        if value.is_some_and(|scalar| !scalar.is_finite()) {
            return Err(FastForecastInferenceError::NonFiniteFeature { index });
        }
    }

    let member = champion
        .members
        .iter()
        .find(|member| {
            member.forecast_artifact.target == target
                && member.forecast_artifact.horizon_ms == horizon_ms
        })
        .ok_or(FastForecastInferenceError::MissingMember { target, horizon_ms })?;
    let artifact = &member.forecast_artifact;

    let predicted = match artifact.model_family {
        FastForecastModelFamily::MeanRegressor | FastForecastModelFamily::PriorClassifier => {
            artifact.constant_prediction.ok_or_else(|| {
                FastForecastInferenceError::InvalidChampion(
                    "naive forecast artifact is missing constant_prediction".to_string(),
                )
            })?
        }
        FastForecastModelFamily::RidgeRegression
        | FastForecastModelFamily::LogisticRegression => {
            let intercept = artifact.intercept.ok_or_else(|| {
                FastForecastInferenceError::InvalidChampion(
                    "trained forecast artifact is missing intercept".to_string(),
                )
            })?;
            let mut sum = 0.0_f64;
            let mut correction = 0.0_f64;
            for (index, ((raw, transform), coefficient)) in raw_features
                .iter()
                .zip(artifact.feature_transforms.iter())
                .zip(artifact.coefficients.iter())
                .enumerate()
            {
                let scalar = raw.unwrap_or(transform.imputation_median);
                let transformed = (scalar - transform.mean) / transform.scale;
                if !transformed.is_finite() {
                    return Err(FastForecastInferenceError::NonFiniteFeature { index });
                }
                let term = coefficient * transformed;
                if !term.is_finite() {
                    return Err(FastForecastInferenceError::NonFinitePrediction);
                }
                let next = sum + term;
                if sum.abs() >= term.abs() {
                    correction += (sum - next) + term;
                } else {
                    correction += (term - next) + sum;
                }
                sum = next;
            }
            let score = (sum + correction) + intercept;
            if !score.is_finite() {
                return Err(FastForecastInferenceError::NonFinitePrediction);
            }
            if artifact.model_family == FastForecastModelFamily::LogisticRegression {
                stable_sigmoid(score)
            } else {
                score
            }
        }
    };

    if !predicted.is_finite() {
        return Err(FastForecastInferenceError::NonFinitePrediction);
    }
    if artifact.target_kind == FastForecastTargetKind::Binary && !(0.0..=1.0).contains(&predicted)
    {
        return Err(FastForecastInferenceError::NonFinitePrediction);
    }
    Ok(FastForecastPrediction {
        model_version: artifact.model_version.clone(),
        target: artifact.target,
        horizon_ms: artifact.horizon_ms,
        predicted_value: predicted,
    })
}

fn stable_sigmoid(score: f64) -> f64 {
    if score >= 0.0 {
        let z = (-score).exp();
        1.0 / (1.0 + z)
    } else {
        let z = score.exp();
        z / (1.0 + z)
    }
}

fn validate_champion(champion: &FastForecastChampion) -> Result<(), FastForecastInferenceError> {
    require(
        champion.schema_name == CHAMPION_SCHEMA_NAME,
        "champion schema_name is incompatible",
    )?;
    require(
        champion.schema_version == CHAMPION_SCHEMA_VERSION,
        "champion schema_version is incompatible",
    )?;
    require_non_empty(&champion.champion_version, "champion_version")?;
    require_non_empty(&champion.selection.decision_reference, "selection decision_reference")?;
    require_non_empty(&champion.selection.reason, "selection reason")?;
    require(
        champion.feature_schema_version == FAST_FORECAST_FEATURE_SCHEMA_VERSION,
        "champion feature_schema_version is incompatible",
    )?;
    require_sha256(
        &champion.training_bundle_fingerprint_sha256,
        "training_bundle_fingerprint_sha256",
    )?;
    require(
        champion.future_path_label_version > 0,
        "future_path_label_version must be positive",
    )?;
    require_sha256(
        &champion.champion_fingerprint_sha256,
        "champion_fingerprint_sha256",
    )?;
    require(!champion.members.is_empty(), "champion members cannot be empty")?;

    let expected_names = expected_feature_names();
    let mut previous_key: Option<&str> = None;
    for member in &champion.members {
        if let Some(previous) = previous_key {
            require(
                previous < member.member_key.as_str(),
                "champion members must be unique and in lexical member_key order",
            )?;
        }
        previous_key = Some(&member.member_key);
        validate_member(member, champion, &expected_names)?;
    }
    Ok(())
}

fn validate_member(
    member: &FastForecastChampionMember,
    champion: &FastForecastChampion,
    expected_names: &[String],
) -> Result<(), FastForecastInferenceError> {
    let artifact = &member.forecast_artifact;
    let expected_key = format!("{}@{}ms", artifact.target.as_str(), artifact.horizon_ms);
    require(member.member_key == expected_key, "member_key contradicts artifact target/horizon")?;
    require_non_empty(&member.validation_policy_version, "validation_policy_version")?;
    require_sha256(
        &member.validation_run_fingerprint_sha256,
        "validation_run_fingerprint_sha256",
    )?;
    require_non_empty(
        &member.test_evaluation_policy_version,
        "test_evaluation_policy_version",
    )?;
    require_sha256(
        &member.test_evaluation_report_fingerprint_sha256,
        "test_evaluation_report_fingerprint_sha256",
    )?;
    require(
        member.test_scored_observation_count > 0,
        "test_scored_observation_count must be positive",
    )?;

    require(
        artifact.schema_name == ARTIFACT_SCHEMA_NAME,
        "artifact schema_name is incompatible",
    )?;
    require(
        artifact.schema_version == ARTIFACT_SCHEMA_VERSION,
        "artifact schema_version is incompatible",
    )?;
    require_non_empty(&artifact.model_version, "model_version")?;
    require(
        artifact.target_kind == artifact.target.kind(),
        "artifact target_kind contradicts target",
    )?;
    let continuous_family = matches!(
        artifact.model_family,
        FastForecastModelFamily::MeanRegressor | FastForecastModelFamily::RidgeRegression
    );
    require(
        continuous_family == (artifact.target_kind == FastForecastTargetKind::Continuous),
        "artifact model_family contradicts target kind",
    )?;
    require(artifact.horizon_ms > 0, "artifact horizon_ms must be positive")?;
    require(
        artifact.feature_schema_version == FAST_FORECAST_FEATURE_SCHEMA_VERSION,
        "artifact feature_schema_version is incompatible",
    )?;
    require(
        artifact.feature_schema_version == champion.feature_schema_version,
        "artifact feature schema differs from champion",
    )?;
    require_non_empty(&artifact.training_policy_version, "training_policy_version")?;
    require_sha256(
        &artifact.training_bundle_fingerprint_sha256,
        "artifact training_bundle_fingerprint_sha256",
    )?;
    require(
        artifact.training_bundle_fingerprint_sha256
            == champion.training_bundle_fingerprint_sha256,
        "artifact training bundle differs from champion",
    )?;
    require(
        artifact.future_path_label_version == champion.future_path_label_version,
        "artifact future-path label version differs from champion",
    )?;
    require(artifact.training_row_count > 0, "training_row_count must be positive")?;
    require(
        artifact.min_training_decision_observed_at_unix_ms
            <= artifact.max_training_decision_observed_at_unix_ms,
        "artifact training timestamp range is invalid",
    )?;
    require_sha256(
        &artifact.training_data_fingerprint_sha256,
        "training_data_fingerprint_sha256",
    )?;
    require_sha256(
        &artifact.artifact_fingerprint_sha256,
        "artifact_fingerprint_sha256",
    )?;

    if artifact.target_kind == FastForecastTargetKind::Binary {
        let positive = artifact.positive_row_count.ok_or_else(|| invalid("binary artifact missing positive_row_count"))?;
        let negative = artifact.negative_row_count.ok_or_else(|| invalid("binary artifact missing negative_row_count"))?;
        require(
            positive + negative == artifact.training_row_count,
            "binary class counts do not reconcile",
        )?;
    } else {
        require(
            artifact.positive_row_count.is_none() && artifact.negative_row_count.is_none(),
            "continuous artifact cannot carry binary class counts",
        )?;
    }

    let trained = matches!(
        artifact.model_family,
        FastForecastModelFamily::RidgeRegression | FastForecastModelFamily::LogisticRegression
    );
    if trained {
        require(
            artifact.feature_transforms.len() == FAST_FORECAST_FEATURE_COUNT,
            "trained artifact transform count is incompatible",
        )?;
        require(
            artifact.coefficients.len() == FAST_FORECAST_FEATURE_COUNT,
            "trained artifact coefficient count is incompatible",
        )?;
        for (index, transform) in artifact.feature_transforms.iter().enumerate() {
            require(
                transform.feature_name == expected_names[index],
                "trained artifact feature transform order is incompatible",
            )?;
            require_finite(transform.imputation_median, "imputation_median")?;
            require_finite(transform.mean, "transform mean")?;
            require_finite(transform.scale, "transform scale")?;
            require(transform.scale > 0.0, "transform scale must be positive")?;
            require_finite(artifact.coefficients[index], "coefficient")?;
        }
        let intercept = artifact.intercept.ok_or_else(|| invalid("trained artifact missing intercept"))?;
        require_finite(intercept, "intercept")?;
        require(
            artifact.constant_prediction.is_none(),
            "trained artifact cannot carry constant_prediction",
        )?;
    } else {
        require(
            artifact.feature_transforms.is_empty() && artifact.coefficients.is_empty(),
            "naive artifact cannot carry transforms or coefficients",
        )?;
        require(artifact.intercept.is_none(), "naive artifact cannot carry intercept")?;
        let constant = artifact
            .constant_prediction
            .ok_or_else(|| invalid("naive artifact missing constant_prediction"))?;
        require_finite(constant, "constant_prediction")?;
        if artifact.target_kind == FastForecastTargetKind::Binary {
            require(
                (0.0..=1.0).contains(&constant),
                "binary constant_prediction must lie in [0, 1]",
            )?;
        }
    }
    Ok(())
}

fn champion_fingerprint_sha256(
    champion: &FastForecastChampion,
) -> Result<String, FastForecastInferenceError> {
    let mut value = serde_json::to_value(champion)
        .map_err(|error| FastForecastInferenceError::Json(error.to_string()))?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| invalid("champion serialization must be an object"))?;
    object.remove("champion_fingerprint_sha256");
    let canonical = canonicalize_value(value)?;
    let encoded = serde_json::to_vec(&canonical)
        .map_err(|error| FastForecastInferenceError::Json(error.to_string()))?;
    let digest = Sha256::digest(encoded);
    Ok(hex_lower(&digest))
}

fn canonicalize_value(value: Value) -> Result<Value, FastForecastInferenceError> {
    match value {
        Value::Null | Value::Bool(_) | Value::String(_) => Ok(value),
        Value::Number(number) => {
            if number.as_i64().is_some() || number.as_u64().is_some() {
                return Ok(Value::Number(number));
            }
            let scalar = number
                .as_f64()
                .ok_or_else(|| invalid("champion numeric value is incompatible"))?;
            require_finite(scalar, "champion fingerprint float")?;
            let mut map = serde_json::Map::new();
            map.insert("float_hex".to_string(), Value::String(python_float_hex(scalar)?));
            Ok(Value::Object(map))
        }
        Value::Array(values) => values
            .into_iter()
            .map(canonicalize_value)
            .collect::<Result<Vec<_>, _>>()
            .map(Value::Array),
        Value::Object(values) => {
            let mut result = serde_json::Map::new();
            for (key, item) in values {
                result.insert(key, canonicalize_value(item)?);
            }
            Ok(Value::Object(result))
        }
    }
}

fn python_float_hex(value: f64) -> Result<String, FastForecastInferenceError> {
    require_finite(value, "float.hex input")?;
    let bits = value.to_bits();
    let negative = (bits >> 63) != 0;
    let magnitude = bits & 0x7fff_ffff_ffff_ffff;
    let prefix = if negative { "-" } else { "" };
    if magnitude == 0 {
        return Ok(format!("{prefix}0x0.0p+0"));
    }
    let exponent_bits = ((magnitude >> 52) & 0x7ff) as i32;
    let fraction = magnitude & 0x000f_ffff_ffff_ffff;
    if exponent_bits == 0 {
        Ok(format!("{prefix}0x0.{fraction:013x}p-1022"))
    } else {
        let exponent = exponent_bits - 1023;
        Ok(format!("{prefix}0x1.{fraction:013x}p{exponent:+}"))
    }
}

fn expected_feature_names() -> Vec<String> {
    const TOP: [&str; 22] = [
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
    const WINDOW_FIELDS: [&str; 21] = [
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
    const WINDOWS: [u64; 7] = [100, 250, 500, 1_000, 2_000, 5_000, 10_000];

    let mut result = TOP.iter().map(|name| (*name).to_string()).collect::<Vec<_>>();
    for window in WINDOWS {
        for field in WINDOW_FIELDS {
            result.push(format!("w{window}.{field}"));
        }
    }
    debug_assert_eq!(result.len(), FAST_FORECAST_FEATURE_COUNT);
    result
}

fn require(condition: bool, message: &str) -> Result<(), FastForecastInferenceError> {
    if condition {
        Ok(())
    } else {
        Err(invalid(message))
    }
}

fn require_non_empty(value: &str, name: &str) -> Result<(), FastForecastInferenceError> {
    require(!value.trim().is_empty(), &format!("{name} must be non-empty"))
}

fn require_sha256(value: &str, name: &str) -> Result<(), FastForecastInferenceError> {
    require(
        value.len() == 64
            && value.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)),
        &format!("{name} must be lowercase SHA-256 hex"),
    )
}

fn require_finite(value: f64, name: &str) -> Result<(), FastForecastInferenceError> {
    require(value.is_finite(), &format!("{name} must be finite"))
}

fn invalid(message: &str) -> FastForecastInferenceError {
    FastForecastInferenceError::InvalidChampion(message.to_string())
}

fn hex_lower(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        result.push(HEX[(byte >> 4) as usize] as char);
        result.push(HEX[(byte & 0x0f) as usize] as char);
    }
    result
}
