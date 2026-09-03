use std::{cmp::Ordering, error::Error, fmt};

use super::{FastForecastPrediction, FastForecastTarget, FastLaneAction};

pub const CONTINUOUS_ACTION_POLICY_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq)]
pub struct FastActionForecastSet {
    pub champion_version: String,
    pub champion_fingerprint_sha256: String,
    pub predictions: Vec<FastForecastPrediction>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastContinuousActionPolicy {
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
    pub missing_forecast_open_action: FastLaneAction,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastReduceExecutionCost {
    pub target_exposure_fraction: f64,
    pub execution_cost_bps: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastActionConstraints {
    pub max_exposure_fraction: f64,
    pub buy_economically_allowed: bool,
    pub expected_future_exit_cost_bps: f64,
    pub reduce_execution_costs: Vec<FastReduceExecutionCost>,
    pub sell_executable: bool,
    pub sell_now_cost_bps: f64,
    pub force_sell: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub enum FastActionPositionState {
    Flat,
    Open { current_exposure_fraction: f64 },
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastHorizonActionEvidence {
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

#[derive(Debug, Clone, PartialEq)]
pub struct FastActionCandidateAssessment {
    pub action: FastLaneAction,
    pub horizon_ms: Option<u64>,
    pub target_exposure_fraction: f64,
    pub reward_bps: f64,
    pub risk_bps: f64,
    pub execution_cost_penalty_bps: f64,
    pub comparison_value_bps: f64,
    pub eligible: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FastContinuousActionReason {
    BuySelected,
    SkipSelected,
    HoldSelected,
    ReduceSelected,
    SellSelected,
    ForecastEvidenceIncomplete,
    ForceSell,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastContinuousActionAssessment {
    pub policy_version: u16,
    pub champion_version: String,
    pub champion_fingerprint_sha256: String,
    pub position_state: FastActionPositionState,
    pub action: FastLaneAction,
    pub reason: FastContinuousActionReason,
    pub selected_horizon_ms: Option<u64>,
    pub current_exposure_fraction: f64,
    pub target_exposure_fraction: f64,
    pub selected_reward_bps: f64,
    pub selected_risk_bps: f64,
    pub selected_execution_cost_bps: f64,
    pub selected_value_bps: f64,
    pub horizon_evidence: Vec<FastHorizonActionEvidence>,
    pub candidates: Vec<FastActionCandidateAssessment>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastContinuousActionError {
    InvalidForecastSet(String),
    InvalidPolicy(String),
    InvalidConstraints(String),
    InvalidPosition(String),
    ForceSellUnavailable,
    MissingForecastSafeActionUnavailable { action: FastLaneAction },
    NoLegalOpenAction,
    NonFiniteResult,
}

impl fmt::Display for FastContinuousActionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidForecastSet(message) => {
                write!(formatter, "invalid continuous-action forecast set: {message}")
            }
            Self::InvalidPolicy(message) => {
                write!(formatter, "invalid continuous-action policy: {message}")
            }
            Self::InvalidConstraints(message) => {
                write!(formatter, "invalid continuous-action constraints: {message}")
            }
            Self::InvalidPosition(message) => {
                write!(formatter, "invalid continuous-action position: {message}")
            }
            Self::ForceSellUnavailable => formatter.write_str(
                "continuous-action force-sell is active but current sell execution is unavailable",
            ),
            Self::MissingForecastSafeActionUnavailable { action } => write!(
                formatter,
                "continuous-action missing-forecast safe action {action} is unavailable"
            ),
            Self::NoLegalOpenAction => formatter.write_str(
                "continuous-action open position has no eligible executable action",
            ),
            Self::NonFiniteResult => formatter.write_str(
                "continuous-action calculation produced a non-finite result",
            ),
        }
    }
}

impl Error for FastContinuousActionError {}

pub fn assess_continuous_action(
    policy: &FastContinuousActionPolicy,
    forecasts: &FastActionForecastSet,
    position: &FastActionPositionState,
    constraints: &FastActionConstraints,
) -> Result<FastContinuousActionAssessment, FastContinuousActionError> {
    validate_policy(policy)?;
    validate_forecasts(forecasts)?;
    validate_constraints(constraints)?;
    validate_position(position)?;

    let horizon_evidence = build_horizon_evidence(policy, forecasts)?;
    match position {
        FastActionPositionState::Flat => {
            assess_flat(policy, forecasts, constraints, horizon_evidence)
        }
        FastActionPositionState::Open {
            current_exposure_fraction,
        } => assess_open(
            policy,
            forecasts,
            *current_exposure_fraction,
            constraints,
            horizon_evidence,
        ),
    }
}

fn assess_flat(
    policy: &FastContinuousActionPolicy,
    forecasts: &FastActionForecastSet,
    constraints: &FastActionConstraints,
    horizon_evidence: Vec<FastHorizonActionEvidence>,
) -> Result<FastContinuousActionAssessment, FastContinuousActionError> {
    let skip = FastActionCandidateAssessment {
        action: FastLaneAction::Skip,
        horizon_ms: None,
        target_exposure_fraction: 0.0,
        reward_bps: 0.0,
        risk_bps: 0.0,
        execution_cost_penalty_bps: 0.0,
        comparison_value_bps: 0.0,
        eligible: true,
    };

    if horizon_evidence.is_empty() {
        return assessment_from_selected(
            policy,
            forecasts,
            FastActionPositionState::Flat,
            FastContinuousActionReason::ForecastEvidenceIncomplete,
            skip.clone(),
            horizon_evidence,
            vec![skip],
        );
    }

    let mut candidates = vec![skip];
    for evidence in &horizon_evidence {
        for &exposure in &policy.entry_exposure_candidates {
            if exposure > constraints.max_exposure_fraction {
                continue;
            }
            let value = finite(
                exposure * evidence.entry_cost_adjusted_return_bps
                    - exposure * exposure * evidence.risk_bps,
            )?;
            candidates.push(FastActionCandidateAssessment {
                action: FastLaneAction::Buy,
                horizon_ms: Some(evidence.horizon_ms),
                target_exposure_fraction: exposure,
                reward_bps: evidence.entry_cost_adjusted_return_bps,
                risk_bps: evidence.risk_bps,
                execution_cost_penalty_bps: 0.0,
                comparison_value_bps: value,
                eligible: constraints.buy_economically_allowed
                    && value >= policy.minimum_buy_value_bps,
            });
        }
    }

    let selected = best_eligible_candidate(&candidates)
        .expect("SKIP is always an eligible flat candidate")
        .clone();
    let reason = if selected.action == FastLaneAction::Buy {
        FastContinuousActionReason::BuySelected
    } else {
        FastContinuousActionReason::SkipSelected
    };
    assessment_from_selected(
        policy,
        forecasts,
        FastActionPositionState::Flat,
        reason,
        selected,
        horizon_evidence,
        candidates,
    )
}

fn assess_open(
    policy: &FastContinuousActionPolicy,
    forecasts: &FastActionForecastSet,
    current_exposure: f64,
    constraints: &FastActionConstraints,
    horizon_evidence: Vec<FastHorizonActionEvidence>,
) -> Result<FastContinuousActionAssessment, FastContinuousActionError> {
    let position = FastActionPositionState::Open {
        current_exposure_fraction: current_exposure,
    };

    if constraints.force_sell {
        if !constraints.sell_executable {
            return Err(FastContinuousActionError::ForceSellUnavailable);
        }
        let selected = sell_candidate(current_exposure, constraints)?;
        return assessment_from_selected(
            policy,
            forecasts,
            position,
            FastContinuousActionReason::ForceSell,
            selected.clone(),
            horizon_evidence,
            vec![selected],
        );
    }

    if horizon_evidence.is_empty() {
        return assess_missing_open_forecast(
            policy,
            forecasts,
            position,
            current_exposure,
            constraints,
            horizon_evidence,
        );
    }

    let mut candidates = Vec::new();
    if current_exposure <= constraints.max_exposure_fraction {
        for evidence in &horizon_evidence {
            let reward = finite(
                evidence.raw_endpoint_return_bps - constraints.expected_future_exit_cost_bps,
            )?;
            let value = retained_value(current_exposure, reward, evidence.risk_bps)?;
            candidates.push(FastActionCandidateAssessment {
                action: FastLaneAction::Hold,
                horizon_ms: Some(evidence.horizon_ms),
                target_exposure_fraction: current_exposure,
                reward_bps: reward,
                risk_bps: evidence.risk_bps,
                execution_cost_penalty_bps: 0.0,
                comparison_value_bps: value,
                eligible: value >= policy.minimum_hold_value_bps,
            });
        }
    }

    for &target in &policy.reduce_target_exposure_candidates {
        if target >= current_exposure || target > constraints.max_exposure_fraction {
            continue;
        }
        let Some(cost) = exact_reduce_cost(constraints, target) else {
            continue;
        };
        let execution_penalty = finite((current_exposure - target) * cost.execution_cost_bps)?;
        for evidence in &horizon_evidence {
            let reward = finite(
                evidence.raw_endpoint_return_bps - constraints.expected_future_exit_cost_bps,
            )?;
            let retained = retained_value(target, reward, evidence.risk_bps)?;
            let value = finite(retained - execution_penalty)?;
            candidates.push(FastActionCandidateAssessment {
                action: FastLaneAction::Reduce,
                horizon_ms: Some(evidence.horizon_ms),
                target_exposure_fraction: target,
                reward_bps: reward,
                risk_bps: evidence.risk_bps,
                execution_cost_penalty_bps: execution_penalty,
                comparison_value_bps: value,
                eligible: true,
            });
        }
    }

    if constraints.sell_executable {
        candidates.push(sell_candidate(current_exposure, constraints)?);
    }

    let Some(selected) = best_eligible_candidate(&candidates).cloned() else {
        return Err(FastContinuousActionError::NoLegalOpenAction);
    };
    let reason = match selected.action {
        FastLaneAction::Hold => FastContinuousActionReason::HoldSelected,
        FastLaneAction::Reduce => FastContinuousActionReason::ReduceSelected,
        FastLaneAction::Sell => FastContinuousActionReason::SellSelected,
        _ => return Err(FastContinuousActionError::NoLegalOpenAction),
    };
    assessment_from_selected(
        policy,
        forecasts,
        position,
        reason,
        selected,
        horizon_evidence,
        candidates,
    )
}

fn assess_missing_open_forecast(
    policy: &FastContinuousActionPolicy,
    forecasts: &FastActionForecastSet,
    position: FastActionPositionState,
    current_exposure: f64,
    constraints: &FastActionConstraints,
    horizon_evidence: Vec<FastHorizonActionEvidence>,
) -> Result<FastContinuousActionAssessment, FastContinuousActionError> {
    let selected = match policy.missing_forecast_open_action {
        FastLaneAction::Reduce => {
            let target = policy
                .reduce_target_exposure_candidates
                .iter()
                .copied()
                .filter(|target| {
                    *target < current_exposure
                        && *target <= constraints.max_exposure_fraction
                        && exact_reduce_cost(constraints, *target).is_some()
                })
                .max_by(|left, right| left.total_cmp(right))
                .ok_or(
                    FastContinuousActionError::MissingForecastSafeActionUnavailable {
                        action: FastLaneAction::Reduce,
                    },
                )?;
            let cost = exact_reduce_cost(constraints, target)
                .expect("filtered reduction target has exact execution cost");
            let execution_penalty = finite((current_exposure - target) * cost.execution_cost_bps)?;
            FastActionCandidateAssessment {
                action: FastLaneAction::Reduce,
                horizon_ms: None,
                target_exposure_fraction: target,
                reward_bps: 0.0,
                risk_bps: 0.0,
                execution_cost_penalty_bps: execution_penalty,
                comparison_value_bps: -execution_penalty,
                eligible: true,
            }
        }
        FastLaneAction::Sell => {
            if !constraints.sell_executable {
                return Err(
                    FastContinuousActionError::MissingForecastSafeActionUnavailable {
                        action: FastLaneAction::Sell,
                    },
                );
            }
            sell_candidate(current_exposure, constraints)?
        }
        _ => {
            return Err(FastContinuousActionError::InvalidPolicy(
                "missing_forecast_open_action must be REDUCE or SELL".to_string(),
            ))
        }
    };

    assessment_from_selected(
        policy,
        forecasts,
        position,
        FastContinuousActionReason::ForecastEvidenceIncomplete,
        selected.clone(),
        horizon_evidence,
        vec![selected],
    )
}

fn sell_candidate(
    current_exposure: f64,
    constraints: &FastActionConstraints,
) -> Result<FastActionCandidateAssessment, FastContinuousActionError> {
    let cost = finite(current_exposure * constraints.sell_now_cost_bps)?;
    Ok(FastActionCandidateAssessment {
        action: FastLaneAction::Sell,
        horizon_ms: None,
        target_exposure_fraction: 0.0,
        reward_bps: 0.0,
        risk_bps: 0.0,
        execution_cost_penalty_bps: cost,
        comparison_value_bps: -cost,
        eligible: true,
    })
}

fn retained_value(
    exposure: f64,
    reward_bps: f64,
    risk_bps: f64,
) -> Result<f64, FastContinuousActionError> {
    finite(exposure * reward_bps - exposure * exposure * risk_bps)
}

fn assessment_from_selected(
    policy: &FastContinuousActionPolicy,
    forecasts: &FastActionForecastSet,
    position_state: FastActionPositionState,
    reason: FastContinuousActionReason,
    selected: FastActionCandidateAssessment,
    mut horizon_evidence: Vec<FastHorizonActionEvidence>,
    mut candidates: Vec<FastActionCandidateAssessment>,
) -> Result<FastContinuousActionAssessment, FastContinuousActionError> {
    horizon_evidence.sort_by_key(|evidence| evidence.horizon_ms);
    candidates.sort_by(canonical_candidate_order);
    let current_exposure_fraction = match position_state {
        FastActionPositionState::Flat => 0.0,
        FastActionPositionState::Open {
            current_exposure_fraction,
        } => current_exposure_fraction,
    };
    Ok(FastContinuousActionAssessment {
        policy_version: policy.version,
        champion_version: forecasts.champion_version.clone(),
        champion_fingerprint_sha256: forecasts.champion_fingerprint_sha256.clone(),
        position_state,
        action: selected.action,
        reason,
        selected_horizon_ms: selected.horizon_ms,
        current_exposure_fraction,
        target_exposure_fraction: selected.target_exposure_fraction,
        selected_reward_bps: selected.reward_bps,
        selected_risk_bps: selected.risk_bps,
        selected_execution_cost_bps: selected.execution_cost_penalty_bps,
        selected_value_bps: selected.comparison_value_bps,
        horizon_evidence,
        candidates,
    })
}

fn build_horizon_evidence(
    policy: &FastContinuousActionPolicy,
    forecasts: &FastActionForecastSet,
) -> Result<Vec<FastHorizonActionEvidence>, FastContinuousActionError> {
    #[derive(Clone)]
    struct PartialEvidence {
        horizon_ms: u64,
        entry: FastForecastPrediction,
        endpoint: FastForecastPrediction,
        mae: FastForecastPrediction,
        reversal: FastForecastPrediction,
        route: FastForecastPrediction,
        adverse_excursion_bps: f64,
        base_risk_bps: f64,
    }

    let mut complete = Vec::new();
    for &horizon_ms in &policy.horizons_ms {
        let Some(entry) = find_prediction(
            forecasts,
            FastForecastTarget::EndpointCostAdjustedReturnBps,
            horizon_ms,
        ) else {
            continue;
        };
        let Some(endpoint) = find_prediction(
            forecasts,
            FastForecastTarget::EndpointReturnBps,
            horizon_ms,
        ) else {
            continue;
        };
        let Some(mae) = find_prediction(forecasts, FastForecastTarget::MaeBps, horizon_ms) else {
            continue;
        };
        let Some(reversal) = find_prediction(
            forecasts,
            FastForecastTarget::ReversalOccurred,
            horizon_ms,
        ) else {
            continue;
        };
        let Some(route) = find_prediction(
            forecasts,
            FastForecastTarget::RouteUnavailabilityObserved,
            horizon_ms,
        ) else {
            continue;
        };

        let adverse_excursion_bps = (-mae.predicted_value).max(0.0);
        let base_risk_bps = finite(
            policy.adverse_excursion_weight * adverse_excursion_bps
                + policy.reversal_penalty_bps * reversal.predicted_value
                + policy.route_unavailability_penalty_bps * route.predicted_value,
        )?;
        complete.push(PartialEvidence {
            horizon_ms,
            entry: entry.clone(),
            endpoint: endpoint.clone(),
            mae: mae.clone(),
            reversal: reversal.clone(),
            route: route.clone(),
            adverse_excursion_bps,
            base_risk_bps,
        });
    }

    if complete.is_empty() {
        return Ok(Vec::new());
    }
    let min_endpoint = complete
        .iter()
        .map(|value| value.endpoint.predicted_value)
        .fold(f64::INFINITY, f64::min);
    let max_endpoint = complete
        .iter()
        .map(|value| value.endpoint.predicted_value)
        .fold(f64::NEG_INFINITY, f64::max);
    let disagreement_bps = finite(max_endpoint - min_endpoint)?;
    let uncertainty_penalty = finite(policy.horizon_disagreement_weight * disagreement_bps)?;

    complete
        .into_iter()
        .map(|value| {
            let risk_bps = finite(value.base_risk_bps + uncertainty_penalty)?;
            Ok(FastHorizonActionEvidence {
                horizon_ms: value.horizon_ms,
                entry_cost_adjusted_return_model_version: value.entry.model_version,
                endpoint_return_model_version: value.endpoint.model_version,
                mae_model_version: value.mae.model_version,
                reversal_model_version: value.reversal.model_version,
                route_unavailability_model_version: value.route.model_version,
                entry_cost_adjusted_return_bps: value.entry.predicted_value,
                raw_endpoint_return_bps: value.endpoint.predicted_value,
                mae_bps: value.mae.predicted_value,
                adverse_excursion_bps: value.adverse_excursion_bps,
                reversal_probability: value.reversal.predicted_value,
                route_unavailability_probability: value.route.predicted_value,
                disagreement_bps,
                risk_bps,
            })
        })
        .collect()
}

fn find_prediction(
    forecasts: &FastActionForecastSet,
    target: FastForecastTarget,
    horizon_ms: u64,
) -> Option<&FastForecastPrediction> {
    forecasts
        .predictions
        .iter()
        .find(|prediction| prediction.target == target && prediction.horizon_ms == horizon_ms)
}

fn exact_reduce_cost(
    constraints: &FastActionConstraints,
    target_exposure_fraction: f64,
) -> Option<&FastReduceExecutionCost> {
    constraints
        .reduce_execution_costs
        .iter()
        .find(|cost| cost.target_exposure_fraction == target_exposure_fraction)
}

fn best_eligible_candidate(
    candidates: &[FastActionCandidateAssessment],
) -> Option<&FastActionCandidateAssessment> {
    let mut best: Option<&FastActionCandidateAssessment> = None;
    for candidate in candidates.iter().filter(|candidate| candidate.eligible) {
        if best.is_none_or(|current| candidate_is_better(candidate, current)) {
            best = Some(candidate);
        }
    }
    best
}

fn candidate_is_better(
    incoming: &FastActionCandidateAssessment,
    current: &FastActionCandidateAssessment,
) -> bool {
    match incoming
        .comparison_value_bps
        .total_cmp(&current.comparison_value_bps)
    {
        Ordering::Greater => return true,
        Ordering::Less => return false,
        Ordering::Equal => {}
    }
    match incoming
        .target_exposure_fraction
        .total_cmp(&current.target_exposure_fraction)
    {
        Ordering::Less => return true,
        Ordering::Greater => return false,
        Ordering::Equal => {}
    }
    match compare_horizon(incoming.horizon_ms, current.horizon_ms) {
        Ordering::Less => return true,
        Ordering::Greater => return false,
        Ordering::Equal => {}
    }
    incoming.action.as_str() < current.action.as_str()
}

fn canonical_candidate_order(
    left: &FastActionCandidateAssessment,
    right: &FastActionCandidateAssessment,
) -> Ordering {
    left.action
        .as_str()
        .cmp(right.action.as_str())
        .then_with(|| {
            left.target_exposure_fraction
                .total_cmp(&right.target_exposure_fraction)
        })
        .then_with(|| compare_horizon(left.horizon_ms, right.horizon_ms))
}

fn compare_horizon(left: Option<u64>, right: Option<u64>) -> Ordering {
    match (left, right) {
        (None, None) => Ordering::Equal,
        (None, Some(_)) => Ordering::Less,
        (Some(_), None) => Ordering::Greater,
        (Some(left), Some(right)) => left.cmp(&right),
    }
}

fn validate_forecasts(
    forecasts: &FastActionForecastSet,
) -> Result<(), FastContinuousActionError> {
    if forecasts.champion_version.trim().is_empty() {
        return Err(FastContinuousActionError::InvalidForecastSet(
            "champion_version must be non-empty".to_string(),
        ));
    }
    if !is_sha256(&forecasts.champion_fingerprint_sha256) {
        return Err(FastContinuousActionError::InvalidForecastSet(
            "champion fingerprint must be lowercase SHA-256 hex".to_string(),
        ));
    }
    if forecasts.predictions.is_empty() {
        return Err(FastContinuousActionError::InvalidForecastSet(
            "predictions cannot be empty".to_string(),
        ));
    }
    for (index, prediction) in forecasts.predictions.iter().enumerate() {
        if prediction.model_version.trim().is_empty() {
            return Err(FastContinuousActionError::InvalidForecastSet(
                "prediction model_version must be non-empty".to_string(),
            ));
        }
        if prediction.horizon_ms == 0 {
            return Err(FastContinuousActionError::InvalidForecastSet(
                "prediction horizon must be positive".to_string(),
            ));
        }
        if !prediction.predicted_value.is_finite() {
            return Err(FastContinuousActionError::InvalidForecastSet(
                "prediction values must be finite".to_string(),
            ));
        }
        if matches!(
            prediction.target,
            FastForecastTarget::ReversalOccurred
                | FastForecastTarget::RouteUnavailabilityObserved
        ) && !(0.0..=1.0).contains(&prediction.predicted_value)
        {
            return Err(FastContinuousActionError::InvalidForecastSet(
                "binary forecast probabilities must be within [0,1]".to_string(),
            ));
        }
        if forecasts.predictions[index + 1..].iter().any(|other| {
            other.target == prediction.target && other.horizon_ms == prediction.horizon_ms
        }) {
            return Err(FastContinuousActionError::InvalidForecastSet(
                "duplicate target/horizon prediction".to_string(),
            ));
        }
    }
    Ok(())
}

fn validate_policy(policy: &FastContinuousActionPolicy) -> Result<(), FastContinuousActionError> {
    if policy.version != CONTINUOUS_ACTION_POLICY_VERSION {
        return Err(FastContinuousActionError::InvalidPolicy(
            "policy version is incompatible".to_string(),
        ));
    }
    if policy.horizons_ms.is_empty()
        || policy.horizons_ms[0] == 0
        || policy
            .horizons_ms
            .windows(2)
            .any(|window| window[0] == 0 || window[1] <= window[0])
    {
        return Err(FastContinuousActionError::InvalidPolicy(
            "horizons must be positive and strictly increasing".to_string(),
        ));
    }
    validate_exposure_vector(
        &policy.entry_exposure_candidates,
        true,
        "entry_exposure_candidates",
    )?;
    validate_exposure_vector(
        &policy.reduce_target_exposure_candidates,
        false,
        "reduce_target_exposure_candidates",
    )?;
    if policy.missing_forecast_open_action == FastLaneAction::Reduce
        && policy.reduce_target_exposure_candidates.is_empty()
    {
        return Err(FastContinuousActionError::InvalidPolicy(
            "REDUCE missing-forecast fallback requires reduction targets".to_string(),
        ));
    }
    if !matches!(
        policy.missing_forecast_open_action,
        FastLaneAction::Reduce | FastLaneAction::Sell
    ) {
        return Err(FastContinuousActionError::InvalidPolicy(
            "missing_forecast_open_action must be REDUCE or SELL".to_string(),
        ));
    }
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
            return Err(FastContinuousActionError::InvalidPolicy(format!(
                "{name} must be finite and non-negative"
            )));
        }
    }
    Ok(())
}

fn validate_exposure_vector(
    values: &[f64],
    require_non_empty: bool,
    name: &str,
) -> Result<(), FastContinuousActionError> {
    if require_non_empty && values.is_empty() {
        return Err(FastContinuousActionError::InvalidPolicy(format!(
            "{name} cannot be empty"
        )));
    }
    for value in values {
        if !value.is_finite() || *value <= 0.0 || *value >= 1.0 + f64::EPSILON {
            return Err(FastContinuousActionError::InvalidPolicy(format!(
                "{name} values are outside the permitted exposure interval"
            )));
        }
    }
    if name == "reduce_target_exposure_candidates" && values.iter().any(|value| *value >= 1.0) {
        return Err(FastContinuousActionError::InvalidPolicy(format!(
            "{name} values must be below 1"
        )));
    }
    if values
        .windows(2)
        .any(|window| window[1].total_cmp(&window[0]) != Ordering::Greater)
    {
        return Err(FastContinuousActionError::InvalidPolicy(format!(
            "{name} must be strictly increasing"
        )));
    }
    Ok(())
}

fn validate_constraints(
    constraints: &FastActionConstraints,
) -> Result<(), FastContinuousActionError> {
    if !constraints.max_exposure_fraction.is_finite()
        || !(0.0..=1.0).contains(&constraints.max_exposure_fraction)
    {
        return Err(FastContinuousActionError::InvalidConstraints(
            "max_exposure_fraction must be finite within [0,1]".to_string(),
        ));
    }
    for (name, value) in [
        (
            "expected_future_exit_cost_bps",
            constraints.expected_future_exit_cost_bps,
        ),
        ("sell_now_cost_bps", constraints.sell_now_cost_bps),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(FastContinuousActionError::InvalidConstraints(format!(
                "{name} must be finite and non-negative"
            )));
        }
    }
    let mut previous: Option<f64> = None;
    for cost in &constraints.reduce_execution_costs {
        if !cost.target_exposure_fraction.is_finite()
            || cost.target_exposure_fraction <= 0.0
            || cost.target_exposure_fraction >= 1.0
        {
            return Err(FastContinuousActionError::InvalidConstraints(
                "reduction target exposure must be finite within (0,1)".to_string(),
            ));
        }
        if !cost.execution_cost_bps.is_finite() || cost.execution_cost_bps < 0.0 {
            return Err(FastContinuousActionError::InvalidConstraints(
                "reduction execution cost must be finite and non-negative".to_string(),
            ));
        }
        if previous.is_some_and(|value| {
            cost.target_exposure_fraction.total_cmp(&value) != Ordering::Greater
        }) {
            return Err(FastContinuousActionError::InvalidConstraints(
                "reduction execution costs must be strictly ordered by target exposure"
                    .to_string(),
            ));
        }
        previous = Some(cost.target_exposure_fraction);
    }
    Ok(())
}

fn validate_position(
    position: &FastActionPositionState,
) -> Result<(), FastContinuousActionError> {
    if let FastActionPositionState::Open {
        current_exposure_fraction,
    } = position
    {
        if !current_exposure_fraction.is_finite()
            || *current_exposure_fraction <= 0.0
            || *current_exposure_fraction > 1.0
        {
            return Err(FastContinuousActionError::InvalidPosition(
                "open exposure must be finite within (0,1]".to_string(),
            ));
        }
    }
    Ok(())
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn finite(value: f64) -> Result<f64, FastContinuousActionError> {
    if value.is_finite() {
        Ok(value)
    } else {
        Err(FastContinuousActionError::NonFiniteResult)
    }
}