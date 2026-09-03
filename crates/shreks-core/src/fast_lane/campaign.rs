use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    error::Error,
    fmt,
};

use super::{
    assess_continuous_action, predict_fast_forecast, FastActionCandidateAssessment,
    FastActionConstraints, FastActionForecastSet, FastActionPositionState,
    FastContinuousActionAssessment, FastContinuousActionError, FastContinuousActionPolicy,
    FastContinuousActionReason, FastForecastChampion, FastForecastInferenceError,
    FastForecastTarget, FastHorizonActionEvidence, FastLaneAction, FastReduceExecutionCost,
    FAST_FORECAST_FEATURE_COUNT,
};

pub const FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME: &str =
    "shreks.fast_campaign_decision_batch";
pub const FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME: &str =
    "shreks.fast_campaign_decision_results";
pub const FAST_CAMPAIGN_DECISION_SCHEMA_VERSION: u16 = 1;

#[derive(Debug)]
pub enum FastCampaignDecisionError {
    Json(String),
    InvalidRequest(String),
    Forecast(FastForecastInferenceError),
    Action(FastContinuousActionError),
    ResultFingerprintMismatch,
}

impl fmt::Display for FastCampaignDecisionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(message) => write!(formatter, "campaign JSON error: {message}"),
            Self::InvalidRequest(message) => write!(formatter, "invalid campaign request: {message}"),
            Self::Forecast(error) => write!(formatter, "campaign forecast failed: {error}"),
            Self::Action(error) => write!(formatter, "campaign action failed: {error}"),
            Self::ResultFingerprintMismatch => {
                formatter.write_str("campaign result fingerprint mismatch")
            }
        }
    }
}

impl Error for FastCampaignDecisionError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Forecast(error) => Some(error),
            Self::Action(error) => Some(error),
            _ => None,
        }
    }
}

impl From<FastForecastInferenceError> for FastCampaignDecisionError {
    fn from(value: FastForecastInferenceError) -> Self {
        Self::Forecast(value)
    }
}

impl From<FastContinuousActionError> for FastCampaignDecisionError {
    fn from(value: FastContinuousActionError) -> Self {
        Self::Action(value)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignContinuousActionPolicyWire {
    pub version: u16,
    pub horizons_ms: Vec<u64>,
    pub entry_exposure_candidates: Vec<f64>,
    pub reduce_target_exposure_candidates: Vec<f64>,
    pub adverse_excursion_weight: f64,
    pub reversal_penalty_bps: f64,
    pub route_unavailability_penalty_bps: f64,
    pub horizon_disagreement_weight: f64,
    pub minimum_buy_value_bps: f64,
    pub minimum_hold_value_bps: f64,
    pub missing_forecast_open_action: String,
}

impl From<FastContinuousActionPolicy> for FastCampaignContinuousActionPolicyWire {
    fn from(value: FastContinuousActionPolicy) -> Self {
        Self {
            version: value.version,
            horizons_ms: value.horizons_ms,
            entry_exposure_candidates: value.entry_exposure_candidates,
            reduce_target_exposure_candidates: value.reduce_target_exposure_candidates,
            adverse_excursion_weight: value.adverse_excursion_weight,
            reversal_penalty_bps: value.reversal_penalty_bps,
            route_unavailability_penalty_bps: value.route_unavailability_penalty_bps,
            horizon_disagreement_weight: value.horizon_disagreement_weight,
            minimum_buy_value_bps: value.minimum_buy_value_bps,
            minimum_hold_value_bps: value.minimum_hold_value_bps,
            missing_forecast_open_action: value.missing_forecast_open_action.as_str().to_owned(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignReduceExecutionCostWire {
    pub target_exposure_fraction: f64,
    pub execution_cost_bps: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignActionConstraintsWire {
    pub max_exposure_fraction: f64,
    pub buy_economically_allowed: bool,
    pub expected_future_exit_cost_bps: f64,
    pub reduce_execution_costs: Vec<FastCampaignReduceExecutionCostWire>,
    pub sell_executable: bool,
    pub sell_now_cost_bps: f64,
    pub force_sell: bool,
}

impl From<FastActionConstraints> for FastCampaignActionConstraintsWire {
    fn from(value: FastActionConstraints) -> Self {
        Self {
            max_exposure_fraction: value.max_exposure_fraction,
            buy_economically_allowed: value.buy_economically_allowed,
            expected_future_exit_cost_bps: value.expected_future_exit_cost_bps,
            reduce_execution_costs: value
                .reduce_execution_costs
                .into_iter()
                .map(|cost| FastCampaignReduceExecutionCostWire {
                    target_exposure_fraction: cost.target_exposure_fraction,
                    execution_cost_bps: cost.execution_cost_bps,
                })
                .collect(),
            sell_executable: value.sell_executable,
            sell_now_cost_bps: value.sell_now_cost_bps,
            force_sell: value.force_sell,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", deny_unknown_fields)]
pub enum FastCampaignDecisionPositionWire {
    #[serde(rename = "FLAT")]
    Flat,
    #[serde(rename = "OPEN")]
    Open { current_exposure_fraction: f64 },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignDecisionRequestWire {
    pub source_event_id: String,
    pub market_key: String,
    pub source_sequence: u64,
    pub as_of_unix_ms: i64,
    pub features: Vec<Option<f64>>,
    pub position: FastCampaignDecisionPositionWire,
    pub constraints: FastCampaignActionConstraintsWire,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignDecisionBatchWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub policy: FastCampaignContinuousActionPolicyWire,
    pub decisions: Vec<FastCampaignDecisionRequestWire>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignHorizonEvidenceWire {
    pub horizon_ms: u64,
    pub entry_cost_adjusted_return_model_version: String,
    pub endpoint_return_model_version: String,
    pub mae_model_version: String,
    pub reversal_model_version: String,
    pub route_unavailability_model_version: String,
    pub entry_cost_adjusted_return_bps: f64,
    pub raw_endpoint_return_bps: f64,
    pub mae_bps: f64,
    pub adverse_excursion_bps: f64,
    pub reversal_probability: f64,
    pub route_unavailability_probability: f64,
    pub disagreement_bps: f64,
    pub risk_bps: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignActionCandidateWire {
    pub action: String,
    pub horizon_ms: Option<u64>,
    pub target_exposure_fraction: f64,
    pub reward_bps: f64,
    pub risk_bps: f64,
    pub execution_cost_penalty_bps: f64,
    pub comparison_value_bps: f64,
    pub eligible: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignDecisionResultWire {
    pub source_event_id: String,
    pub market_key: String,
    pub source_sequence: u64,
    pub as_of_unix_ms: i64,
    pub policy_version: u16,
    pub action: String,
    pub reason: String,
    pub selected_horizon_ms: Option<u64>,
    pub current_exposure_fraction: f64,
    pub target_exposure_fraction: f64,
    pub selected_reward_bps: f64,
    pub selected_risk_bps: f64,
    pub selected_execution_cost_bps: f64,
    pub selected_value_bps: f64,
    pub horizon_evidence: Vec<FastCampaignHorizonEvidenceWire>,
    pub candidates: Vec<FastCampaignActionCandidateWire>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastCampaignDecisionResultsWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub champion_version: String,
    pub champion_fingerprint_sha256: String,
    pub decisions: Vec<FastCampaignDecisionResultWire>,
    pub batch_fingerprint_sha256: String,
}

pub fn assess_continuous_action_from_champion(
    champion: &FastForecastChampion,
    raw_features: &[Option<f64>],
    policy: &FastContinuousActionPolicy,
    position: &FastActionPositionState,
    constraints: &FastActionConstraints,
) -> Result<FastContinuousActionAssessment, FastCampaignDecisionError> {
    const TARGETS: [FastForecastTarget; 5] = [
        FastForecastTarget::EndpointCostAdjustedReturnBps,
        FastForecastTarget::EndpointReturnBps,
        FastForecastTarget::MaeBps,
        FastForecastTarget::ReversalOccurred,
        FastForecastTarget::RouteUnavailabilityObserved,
    ];

    let mut predictions = Vec::with_capacity(policy.horizons_ms.len() * TARGETS.len());
    for &horizon_ms in &policy.horizons_ms {
        for target in TARGETS {
            predictions.push(predict_fast_forecast(
                champion,
                target,
                horizon_ms,
                raw_features,
            )?);
        }
    }

    let forecasts = FastActionForecastSet {
        champion_version: champion.champion_version.clone(),
        champion_fingerprint_sha256: champion.champion_fingerprint_sha256.clone(),
        predictions,
    };
    Ok(assess_continuous_action(
        policy,
        &forecasts,
        position,
        constraints,
    )?)
}

pub fn decode_fast_campaign_decision_batch_json(
    input: &str,
) -> Result<FastCampaignDecisionBatchWire, FastCampaignDecisionError> {
    let batch: FastCampaignDecisionBatchWire = serde_json::from_str(input)
        .map_err(|error| FastCampaignDecisionError::Json(error.to_string()))?;
    validate_batch(&batch)?;
    Ok(batch)
}

pub fn evaluate_fast_campaign_decision_batch(
    champion: &FastForecastChampion,
    batch: &FastCampaignDecisionBatchWire,
) -> Result<FastCampaignDecisionResultsWire, FastCampaignDecisionError> {
    validate_batch(batch)?;
    let policy = policy_from_wire(&batch.policy)?;
    let mut decisions = Vec::with_capacity(batch.decisions.len());

    for request in &batch.decisions {
        let position = position_from_wire(&request.position)?;
        let constraints = constraints_from_wire(&request.constraints)?;
        let assessment = assess_continuous_action_from_champion(
            champion,
            &request.features,
            &policy,
            &position,
            &constraints,
        )?;
        decisions.push(result_from_assessment(request, &assessment));
    }

    let mut results = FastCampaignDecisionResultsWire {
        schema_name: FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME.to_owned(),
        schema_version: FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        champion_version: champion.champion_version.clone(),
        champion_fingerprint_sha256: champion.champion_fingerprint_sha256.clone(),
        decisions,
        batch_fingerprint_sha256: "0".repeat(64),
    };
    results.batch_fingerprint_sha256 = results_fingerprint_sha256(&results)?;
    Ok(results)
}

pub fn encode_fast_campaign_decision_results_json(
    results: &FastCampaignDecisionResultsWire,
) -> Result<String, FastCampaignDecisionError> {
    validate_results(results)?;
    let expected = results_fingerprint_sha256(results)?;
    if expected != results.batch_fingerprint_sha256 {
        return Err(FastCampaignDecisionError::ResultFingerprintMismatch);
    }
    let value = serde_json::to_value(results)
        .map_err(|error| FastCampaignDecisionError::Json(error.to_string()))?;
    serde_json::to_string(&value)
        .map_err(|error| FastCampaignDecisionError::Json(error.to_string()))
}

fn validate_batch(batch: &FastCampaignDecisionBatchWire) -> Result<(), FastCampaignDecisionError> {
    if batch.schema_name != FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME {
        return invalid("schema_name is incompatible");
    }
    if batch.schema_version != FAST_CAMPAIGN_DECISION_SCHEMA_VERSION {
        return invalid("schema_version is incompatible");
    }
    validate_policy_wire(&batch.policy)?;
    if batch.decisions.is_empty() {
        return invalid("decisions cannot be empty");
    }

    let mut ids = HashSet::new();
    let mut latest_by_market: HashMap<&str, (u64, i64)> = HashMap::new();
    for decision in &batch.decisions {
        require_non_empty("source_event_id", &decision.source_event_id)?;
        require_non_empty("market_key", &decision.market_key)?;
        if !ids.insert(decision.source_event_id.as_str()) {
            return invalid("duplicate source_event_id");
        }
        if decision.source_sequence == 0 {
            return invalid("source_sequence must be positive");
        }
        if decision.as_of_unix_ms < 0 {
            return invalid("as_of_unix_ms must be non-negative");
        }
        if decision.features.len() != FAST_FORECAST_FEATURE_COUNT {
            return invalid("features must contain exactly 169 values");
        }
        if decision
            .features
            .iter()
            .flatten()
            .any(|value| !value.is_finite())
        {
            return invalid("features must be finite when present");
        }
        validate_position_wire(&decision.position)?;
        validate_constraints_wire(&decision.constraints)?;

        if let Some((previous_sequence, previous_time)) =
            latest_by_market.get(decision.market_key.as_str())
        {
            if decision.source_sequence <= *previous_sequence {
                return invalid("per-market source sequence must strictly increase");
            }
            if decision.as_of_unix_ms < *previous_time {
                return invalid("per-market observation time cannot move backward");
            }
        }
        latest_by_market.insert(
            decision.market_key.as_str(),
            (decision.source_sequence, decision.as_of_unix_ms),
        );
    }
    Ok(())
}

fn validate_policy_wire(
    policy: &FastCampaignContinuousActionPolicyWire,
) -> Result<(), FastCampaignDecisionError> {
    if policy.version == 0 {
        return invalid("policy version must be positive");
    }
    if policy.horizons_ms.is_empty()
        || policy.horizons_ms[0] == 0
        || policy
            .horizons_ms
            .windows(2)
            .any(|window| window[1] <= window[0])
    {
        return invalid("policy horizons must be positive and strictly increasing");
    }
    validate_exposure_vector(
        "entry_exposure_candidates",
        &policy.entry_exposure_candidates,
        true,
        false,
    )?;
    validate_exposure_vector(
        "reduce_target_exposure_candidates",
        &policy.reduce_target_exposure_candidates,
        false,
        true,
    )?;
    for (name, value) in [
        ("adverse_excursion_weight", policy.adverse_excursion_weight),
        ("reversal_penalty_bps", policy.reversal_penalty_bps),
        (
            "route_unavailability_penalty_bps",
            policy.route_unavailability_penalty_bps,
        ),
        (
            "horizon_disagreement_weight",
            policy.horizon_disagreement_weight,
        ),
        ("minimum_buy_value_bps", policy.minimum_buy_value_bps),
        ("minimum_hold_value_bps", policy.minimum_hold_value_bps),
    ] {
        if !value.is_finite() || value < 0.0 {
            return invalid(&format!("{name} must be finite and non-negative"));
        }
    }
    if !matches!(
        policy.missing_forecast_open_action.as_str(),
        "REDUCE" | "SELL"
    ) {
        return invalid("missing_forecast_open_action must be REDUCE or SELL");
    }
    if policy.missing_forecast_open_action == "REDUCE"
        && policy.reduce_target_exposure_candidates.is_empty()
    {
        return invalid("REDUCE fallback requires at least one reduction target");
    }
    Ok(())
}

fn validate_exposure_vector(
    name: &str,
    values: &[f64],
    require_non_empty: bool,
    require_below_one: bool,
) -> Result<(), FastCampaignDecisionError> {
    if require_non_empty && values.is_empty() {
        return invalid(&format!("{name} cannot be empty"));
    }
    for &value in values {
        if !value.is_finite()
            || value <= 0.0
            || value > 1.0
            || (require_below_one && value >= 1.0)
        {
            return invalid(&format!("{name} contains invalid exposure"));
        }
    }
    if values
        .windows(2)
        .any(|window| window[1].total_cmp(&window[0]) != std::cmp::Ordering::Greater)
    {
        return invalid(&format!("{name} must be strictly increasing"));
    }
    Ok(())
}

fn validate_position_wire(
    position: &FastCampaignDecisionPositionWire,
) -> Result<(), FastCampaignDecisionError> {
    if let FastCampaignDecisionPositionWire::Open {
        current_exposure_fraction,
    } = position
    {
        if !current_exposure_fraction.is_finite()
            || *current_exposure_fraction <= 0.0
            || *current_exposure_fraction > 1.0
        {
            return invalid("OPEN current_exposure_fraction must be within (0,1]");
        }
    }
    Ok(())
}

fn validate_constraints_wire(
    constraints: &FastCampaignActionConstraintsWire,
) -> Result<(), FastCampaignDecisionError> {
    if !constraints.max_exposure_fraction.is_finite()
        || !(0.0..=1.0).contains(&constraints.max_exposure_fraction)
    {
        return invalid("max_exposure_fraction must lie within [0,1]");
    }
    for (name, value) in [
        (
            "expected_future_exit_cost_bps",
            constraints.expected_future_exit_cost_bps,
        ),
        ("sell_now_cost_bps", constraints.sell_now_cost_bps),
    ] {
        if !value.is_finite() || value < 0.0 {
            return invalid(&format!("{name} must be finite and non-negative"));
        }
    }
    let mut previous_target: Option<f64> = None;
    for cost in &constraints.reduce_execution_costs {
        if !cost.target_exposure_fraction.is_finite()
            || cost.target_exposure_fraction < 0.0
            || cost.target_exposure_fraction >= 1.0
            || !cost.execution_cost_bps.is_finite()
            || cost.execution_cost_bps < 0.0
        {
            return invalid("reduce execution costs contain invalid values");
        }
        if previous_target.is_some_and(|previous| cost.target_exposure_fraction <= previous) {
            return invalid("reduce execution costs must be in strictly increasing target order");
        }
        previous_target = Some(cost.target_exposure_fraction);
    }
    if constraints.force_sell && !constraints.sell_executable {
        return invalid("force_sell requires sell_executable");
    }
    Ok(())
}

fn policy_from_wire(
    policy: &FastCampaignContinuousActionPolicyWire,
) -> Result<FastContinuousActionPolicy, FastCampaignDecisionError> {
    validate_policy_wire(policy)?;
    let missing_forecast_open_action = match policy.missing_forecast_open_action.as_str() {
        "REDUCE" => FastLaneAction::Reduce,
        "SELL" => FastLaneAction::Sell,
        _ => return invalid("missing_forecast_open_action must be REDUCE or SELL"),
    };
    Ok(FastContinuousActionPolicy {
        version: policy.version,
        horizons_ms: policy.horizons_ms.clone(),
        entry_exposure_candidates: policy.entry_exposure_candidates.clone(),
        reduce_target_exposure_candidates: policy.reduce_target_exposure_candidates.clone(),
        adverse_excursion_weight: policy.adverse_excursion_weight,
        reversal_penalty_bps: policy.reversal_penalty_bps,
        route_unavailability_penalty_bps: policy.route_unavailability_penalty_bps,
        horizon_disagreement_weight: policy.horizon_disagreement_weight,
        minimum_buy_value_bps: policy.minimum_buy_value_bps,
        minimum_hold_value_bps: policy.minimum_hold_value_bps,
        missing_forecast_open_action,
    })
}

fn position_from_wire(
    position: &FastCampaignDecisionPositionWire,
) -> Result<FastActionPositionState, FastCampaignDecisionError> {
    validate_position_wire(position)?;
    Ok(match position {
        FastCampaignDecisionPositionWire::Flat => FastActionPositionState::Flat,
        FastCampaignDecisionPositionWire::Open {
            current_exposure_fraction,
        } => FastActionPositionState::Open {
            current_exposure_fraction: *current_exposure_fraction,
        },
    })
}

fn constraints_from_wire(
    constraints: &FastCampaignActionConstraintsWire,
) -> Result<FastActionConstraints, FastCampaignDecisionError> {
    validate_constraints_wire(constraints)?;
    Ok(FastActionConstraints {
        max_exposure_fraction: constraints.max_exposure_fraction,
        buy_economically_allowed: constraints.buy_economically_allowed,
        expected_future_exit_cost_bps: constraints.expected_future_exit_cost_bps,
        reduce_execution_costs: constraints
            .reduce_execution_costs
            .iter()
            .map(|cost| FastReduceExecutionCost {
                target_exposure_fraction: cost.target_exposure_fraction,
                execution_cost_bps: cost.execution_cost_bps,
            })
            .collect(),
        sell_executable: constraints.sell_executable,
        sell_now_cost_bps: constraints.sell_now_cost_bps,
        force_sell: constraints.force_sell,
    })
}

fn result_from_assessment(
    request: &FastCampaignDecisionRequestWire,
    assessment: &FastContinuousActionAssessment,
) -> FastCampaignDecisionResultWire {
    FastCampaignDecisionResultWire {
        source_event_id: request.source_event_id.clone(),
        market_key: request.market_key.clone(),
        source_sequence: request.source_sequence,
        as_of_unix_ms: request.as_of_unix_ms,
        policy_version: assessment.policy_version,
        action: assessment.action.as_str().to_owned(),
        reason: reason_str(assessment.reason).to_owned(),
        selected_horizon_ms: assessment.selected_horizon_ms,
        current_exposure_fraction: assessment.current_exposure_fraction,
        target_exposure_fraction: assessment.target_exposure_fraction,
        selected_reward_bps: assessment.selected_reward_bps,
        selected_risk_bps: assessment.selected_risk_bps,
        selected_execution_cost_bps: assessment.selected_execution_cost_bps,
        selected_value_bps: assessment.selected_value_bps,
        horizon_evidence: assessment
            .horizon_evidence
            .iter()
            .map(horizon_wire)
            .collect(),
        candidates: assessment.candidates.iter().map(candidate_wire).collect(),
    }
}

fn horizon_wire(value: &FastHorizonActionEvidence) -> FastCampaignHorizonEvidenceWire {
    FastCampaignHorizonEvidenceWire {
        horizon_ms: value.horizon_ms,
        entry_cost_adjusted_return_model_version: value
            .entry_cost_adjusted_return_model_version
            .clone(),
        endpoint_return_model_version: value.endpoint_return_model_version.clone(),
        mae_model_version: value.mae_model_version.clone(),
        reversal_model_version: value.reversal_model_version.clone(),
        route_unavailability_model_version: value.route_unavailability_model_version.clone(),
        entry_cost_adjusted_return_bps: value.entry_cost_adjusted_return_bps,
        raw_endpoint_return_bps: value.raw_endpoint_return_bps,
        mae_bps: value.mae_bps,
        adverse_excursion_bps: value.adverse_excursion_bps,
        reversal_probability: value.reversal_probability,
        route_unavailability_probability: value.route_unavailability_probability,
        disagreement_bps: value.disagreement_bps,
        risk_bps: value.risk_bps,
    }
}

fn candidate_wire(value: &FastActionCandidateAssessment) -> FastCampaignActionCandidateWire {
    FastCampaignActionCandidateWire {
        action: value.action.as_str().to_owned(),
        horizon_ms: value.horizon_ms,
        target_exposure_fraction: value.target_exposure_fraction,
        reward_bps: value.reward_bps,
        risk_bps: value.risk_bps,
        execution_cost_penalty_bps: value.execution_cost_penalty_bps,
        comparison_value_bps: value.comparison_value_bps,
        eligible: value.eligible,
    }
}

fn reason_str(reason: FastContinuousActionReason) -> &'static str {
    match reason {
        FastContinuousActionReason::BuySelected => "BUY_SELECTED",
        FastContinuousActionReason::SkipSelected => "SKIP_SELECTED",
        FastContinuousActionReason::HoldSelected => "HOLD_SELECTED",
        FastContinuousActionReason::ReduceSelected => "REDUCE_SELECTED",
        FastContinuousActionReason::SellSelected => "SELL_SELECTED",
        FastContinuousActionReason::ForecastEvidenceIncomplete => "FORECAST_EVIDENCE_INCOMPLETE",
        FastContinuousActionReason::ForceSell => "FORCE_SELL",
    }
}

fn validate_results(
    results: &FastCampaignDecisionResultsWire,
) -> Result<(), FastCampaignDecisionError> {
    if results.schema_name != FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME {
        return invalid("result schema_name is incompatible");
    }
    if results.schema_version != FAST_CAMPAIGN_DECISION_SCHEMA_VERSION {
        return invalid("result schema_version is incompatible");
    }
    require_non_empty("champion_version", &results.champion_version)?;
    require_sha256(
        "champion_fingerprint_sha256",
        &results.champion_fingerprint_sha256,
    )?;
    require_sha256("batch_fingerprint_sha256", &results.batch_fingerprint_sha256)?;
    if results.decisions.is_empty() {
        return invalid("result decisions cannot be empty");
    }
    for decision in &results.decisions {
        require_non_empty("result source_event_id", &decision.source_event_id)?;
        require_non_empty("result market_key", &decision.market_key)?;
        if decision.source_sequence == 0 || decision.as_of_unix_ms < 0 {
            return invalid("result identity is invalid");
        }
        for value in [
            decision.current_exposure_fraction,
            decision.target_exposure_fraction,
            decision.selected_reward_bps,
            decision.selected_risk_bps,
            decision.selected_execution_cost_bps,
            decision.selected_value_bps,
        ] {
            if !value.is_finite() {
                return invalid("result numeric values must be finite");
            }
        }
    }
    Ok(())
}

fn results_fingerprint_sha256(
    results: &FastCampaignDecisionResultsWire,
) -> Result<String, FastCampaignDecisionError> {
    let mut value = serde_json::to_value(results)
        .map_err(|error| FastCampaignDecisionError::Json(error.to_string()))?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| FastCampaignDecisionError::InvalidRequest(
            "result serialization must be an object".to_owned(),
        ))?;
    object.remove("batch_fingerprint_sha256");
    let payload = serde_json::to_vec(&value)
        .map_err(|error| FastCampaignDecisionError::Json(error.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(payload)))
}

fn require_non_empty(name: &str, value: &str) -> Result<(), FastCampaignDecisionError> {
    if value.trim().is_empty() {
        return invalid(&format!("{name} must be non-empty"));
    }
    Ok(())
}

fn require_sha256(name: &str, value: &str) -> Result<(), FastCampaignDecisionError> {
    if value.len() != 64
        || value != value.to_ascii_lowercase()
        || value
            .bytes()
            .any(|byte| !byte.is_ascii_hexdigit())
    {
        return invalid(&format!("{name} must be lowercase SHA-256 hex"));
    }
    Ok(())
}

fn invalid<T>(message: &str) -> Result<T, FastCampaignDecisionError> {
    Err(FastCampaignDecisionError::InvalidRequest(message.to_owned()))
}
