use std::{error::Error, fmt};

use super::{ExecutionLegCostInput, FastLaneAction, FastMarketKey, FastMarketSnapshot};

pub const LONGER_RUNNER_EVIDENCE_VERSION: u16 = 1;
pub const LONGER_RUNNER_BASELINE_VERSION: u16 = 1;
const BASIS_POINTS_DENOMINATOR: f64 = 10_000.0;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LongerRunnerProtectiveState {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub hard_stop_triggered: bool,
    pub risk_limit_exit_required: bool,
    pub liquidity_exit_required: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LongerRunnerContinuationEvidence {
    pub version: u16,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub forecast_source_version: String,
    pub forecast_horizon_ms: u64,
    pub base_quantity: f64,
    pub current_executable_exit_price_quote: f64,
    pub expected_future_exit_price_quote: f64,
    pub downside_exit_price_quote: f64,
    pub current_exit_capacity_base: f64,
    pub expected_future_exit_capacity_base: f64,
    pub expected_holding_cost_quote: f64,
    pub current_exit_costs: ExecutionLegCostInput,
    pub future_exit_costs: ExecutionLegCostInput,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LongerRunnerPolicy {
    pub version: u16,
    pub downside_risk_weight: f64,
    pub min_risk_adjusted_continuation_bps_for_hold: f64,
    pub max_risk_adjusted_continuation_bps_for_sell: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LongerRunnerReason {
    ContinuationEvidenceUnavailable,
    HardStopTriggered,
    RiskLimitExitRequired,
    LiquidityExitRequired,
    CurrentExitCapacityInsufficient,
    FutureExitCapacityInsufficient,
    ContinuationAtOrAboveHoldThreshold,
    ContinuationAtOrBelowSellThreshold,
    ContinuationBetweenThresholds,
    HoldConditionsMet,
    ReduceConditionsMet,
    SellConditionsMet,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LongerRunnerAssessment {
    pub version: u16,
    pub policy_version: u16,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub action: FastLaneAction,
    pub reasons: Vec<LongerRunnerReason>,
    pub evidence_version: Option<u16>,
    pub forecast_source_version: Option<String>,
    pub forecast_horizon_ms: Option<u64>,
    pub base_quantity: Option<f64>,
    pub current_gross_exit_quote: Option<f64>,
    pub current_net_exit_quote: Option<f64>,
    pub expected_future_net_exit_quote: Option<f64>,
    pub downside_future_net_exit_quote: Option<f64>,
    pub expected_holding_cost_quote: Option<f64>,
    pub downside_loss_quote: Option<f64>,
    pub risk_penalty_quote: Option<f64>,
    pub gross_expected_continuation_quote: Option<f64>,
    pub risk_adjusted_continuation_quote: Option<f64>,
    pub risk_adjusted_continuation_bps: Option<f64>,
    pub current_exit_capacity_base: Option<f64>,
    pub expected_future_exit_capacity_base: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LongerRunnerError {
    InvalidPolicy(&'static str),
    InvalidSnapshot(&'static str),
    ProtectiveMarketMismatch,
    ProtectiveTimestampMismatch { snapshot: i64, protective: i64 },
    InvalidContinuation(&'static str),
    ContinuationMarketMismatch,
    ContinuationTimestampMismatch { snapshot: i64, continuation: i64 },
    InvalidExitCosts(&'static str),
    NonFiniteResult(&'static str),
}

impl fmt::Display for LongerRunnerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPolicy(field) => write!(formatter, "invalid longer-runner policy: {field}"),
            Self::InvalidSnapshot(field) => write!(formatter, "invalid longer-runner snapshot: {field}"),
            Self::ProtectiveMarketMismatch => formatter.write_str("longer-runner protective market does not match snapshot"),
            Self::ProtectiveTimestampMismatch { snapshot, protective } => write!(
                formatter,
                "longer-runner protective timestamp {protective} does not match snapshot {snapshot}"
            ),
            Self::InvalidContinuation(field) => write!(formatter, "invalid longer-runner continuation evidence: {field}"),
            Self::ContinuationMarketMismatch => formatter.write_str("longer-runner continuation market does not match snapshot"),
            Self::ContinuationTimestampMismatch { snapshot, continuation } => write!(
                formatter,
                "longer-runner continuation timestamp {continuation} does not match snapshot {snapshot}"
            ),
            Self::InvalidExitCosts(field) => write!(formatter, "invalid longer-runner exit costs: {field}"),
            Self::NonFiniteResult(field) => write!(formatter, "longer-runner calculation produced non-finite {field}"),
        }
    }
}

impl Error for LongerRunnerError {}

#[derive(Debug, Clone, Copy)]
struct ValidatedExitCosts {
    variable_bps: u32,
    fixed_quote: f64,
}

pub fn assess_longer_runner(
    snapshot: &FastMarketSnapshot,
    protective: &LongerRunnerProtectiveState,
    continuation: Option<&LongerRunnerContinuationEvidence>,
    policy: &LongerRunnerPolicy,
) -> Result<LongerRunnerAssessment, LongerRunnerError> {
    validate_policy(policy)?;
    if snapshot.as_of_unix_ms <= 0 {
        return Err(LongerRunnerError::InvalidSnapshot("as-of timestamp must be positive"));
    }
    if protective.market != snapshot.market {
        return Err(LongerRunnerError::ProtectiveMarketMismatch);
    }
    if protective.as_of_unix_ms != snapshot.as_of_unix_ms {
        return Err(LongerRunnerError::ProtectiveTimestampMismatch {
            snapshot: snapshot.as_of_unix_ms,
            protective: protective.as_of_unix_ms,
        });
    }

    let mut protective_reasons = Vec::with_capacity(4);
    if protective.hard_stop_triggered {
        protective_reasons.push(LongerRunnerReason::HardStopTriggered);
    }
    if protective.risk_limit_exit_required {
        protective_reasons.push(LongerRunnerReason::RiskLimitExitRequired);
    }
    if protective.liquidity_exit_required {
        protective_reasons.push(LongerRunnerReason::LiquidityExitRequired);
    }
    if !protective_reasons.is_empty() {
        protective_reasons.push(LongerRunnerReason::SellConditionsMet);
        return Ok(empty_assessment(
            snapshot,
            policy,
            FastLaneAction::Sell,
            protective_reasons,
        ));
    }

    let Some(continuation) = continuation else {
        return Ok(empty_assessment(
            snapshot,
            policy,
            FastLaneAction::Reduce,
            vec![
                LongerRunnerReason::ContinuationEvidenceUnavailable,
                LongerRunnerReason::ReduceConditionsMet,
            ],
        ));
    };

    validate_continuation_identity(snapshot, continuation)?;
    validate_continuation_values(continuation)?;
    let current_costs = validate_exit_costs(&continuation.current_exit_costs)?;
    let future_costs = validate_exit_costs(&continuation.future_exit_costs)?;

    if continuation.current_exit_capacity_base < continuation.base_quantity
        || continuation.expected_future_exit_capacity_base < continuation.base_quantity
    {
        let mut reasons = Vec::with_capacity(3);
        if continuation.current_exit_capacity_base < continuation.base_quantity {
            reasons.push(LongerRunnerReason::CurrentExitCapacityInsufficient);
        }
        if continuation.expected_future_exit_capacity_base < continuation.base_quantity {
            reasons.push(LongerRunnerReason::FutureExitCapacityInsufficient);
        }
        reasons.push(LongerRunnerReason::SellConditionsMet);
        return Ok(assessment_with_evidence(
            snapshot,
            policy,
            continuation,
            FastLaneAction::Sell,
            reasons,
            None,
        ));
    }

    let current_gross_exit_quote = finite_result(
        continuation.base_quantity * continuation.current_executable_exit_price_quote,
        "current gross exit quote",
    )?;
    let current_net_exit_quote = net_exit_quote(
        continuation.base_quantity,
        continuation.current_executable_exit_price_quote,
        current_costs,
        "current net exit quote",
    )?;
    let expected_future_net_exit_quote = net_exit_quote(
        continuation.base_quantity,
        continuation.expected_future_exit_price_quote,
        future_costs,
        "expected future net exit quote",
    )?;
    let downside_future_net_exit_quote = net_exit_quote(
        continuation.base_quantity,
        continuation.downside_exit_price_quote,
        future_costs,
        "downside future net exit quote",
    )?;

    let gross_expected_continuation_quote = finite_result(
        expected_future_net_exit_quote
            - current_net_exit_quote
            - continuation.expected_holding_cost_quote,
        "gross expected continuation quote",
    )?;
    let downside_loss_quote = finite_result(
        (current_net_exit_quote - downside_future_net_exit_quote).max(0.0),
        "downside loss quote",
    )?;
    let risk_penalty_quote = finite_result(
        downside_loss_quote * policy.downside_risk_weight,
        "risk penalty quote",
    )?;
    let risk_adjusted_continuation_quote = finite_result(
        gross_expected_continuation_quote - risk_penalty_quote,
        "risk-adjusted continuation quote",
    )?;
    let risk_adjusted_continuation_bps = finite_result(
        risk_adjusted_continuation_quote / current_gross_exit_quote * BASIS_POINTS_DENOMINATOR,
        "risk-adjusted continuation basis points",
    )?;

    let economics = ContinuationEconomics {
        current_gross_exit_quote,
        current_net_exit_quote,
        expected_future_net_exit_quote,
        downside_future_net_exit_quote,
        downside_loss_quote,
        risk_penalty_quote,
        gross_expected_continuation_quote,
        risk_adjusted_continuation_quote,
        risk_adjusted_continuation_bps,
    };

    let (action, reasons) = if risk_adjusted_continuation_bps
        <= policy.max_risk_adjusted_continuation_bps_for_sell
    {
        (
            FastLaneAction::Sell,
            vec![
                LongerRunnerReason::ContinuationAtOrBelowSellThreshold,
                LongerRunnerReason::SellConditionsMet,
            ],
        )
    } else if risk_adjusted_continuation_bps
        >= policy.min_risk_adjusted_continuation_bps_for_hold
    {
        (
            FastLaneAction::Hold,
            vec![
                LongerRunnerReason::ContinuationAtOrAboveHoldThreshold,
                LongerRunnerReason::HoldConditionsMet,
            ],
        )
    } else {
        (
            FastLaneAction::Reduce,
            vec![
                LongerRunnerReason::ContinuationBetweenThresholds,
                LongerRunnerReason::ReduceConditionsMet,
            ],
        )
    };

    Ok(assessment_with_evidence(
        snapshot,
        policy,
        continuation,
        action,
        reasons,
        Some(economics),
    ))
}

#[derive(Debug, Clone, Copy)]
struct ContinuationEconomics {
    current_gross_exit_quote: f64,
    current_net_exit_quote: f64,
    expected_future_net_exit_quote: f64,
    downside_future_net_exit_quote: f64,
    downside_loss_quote: f64,
    risk_penalty_quote: f64,
    gross_expected_continuation_quote: f64,
    risk_adjusted_continuation_quote: f64,
    risk_adjusted_continuation_bps: f64,
}

fn validate_policy(policy: &LongerRunnerPolicy) -> Result<(), LongerRunnerError> {
    if policy.version != LONGER_RUNNER_BASELINE_VERSION {
        return Err(LongerRunnerError::InvalidPolicy("unsupported policy version"));
    }
    if !policy.downside_risk_weight.is_finite() || policy.downside_risk_weight < 0.0 {
        return Err(LongerRunnerError::InvalidPolicy("downside risk weight must be finite and non-negative"));
    }
    if !policy.min_risk_adjusted_continuation_bps_for_hold.is_finite() {
        return Err(LongerRunnerError::InvalidPolicy("hold threshold must be finite"));
    }
    if !policy.max_risk_adjusted_continuation_bps_for_sell.is_finite() {
        return Err(LongerRunnerError::InvalidPolicy("sell threshold must be finite"));
    }
    if policy.max_risk_adjusted_continuation_bps_for_sell
        > policy.min_risk_adjusted_continuation_bps_for_hold
    {
        return Err(LongerRunnerError::InvalidPolicy("sell threshold must not exceed hold threshold"));
    }
    Ok(())
}

fn validate_continuation_identity(
    snapshot: &FastMarketSnapshot,
    continuation: &LongerRunnerContinuationEvidence,
) -> Result<(), LongerRunnerError> {
    if continuation.market != snapshot.market {
        return Err(LongerRunnerError::ContinuationMarketMismatch);
    }
    if continuation.as_of_unix_ms != snapshot.as_of_unix_ms {
        return Err(LongerRunnerError::ContinuationTimestampMismatch {
            snapshot: snapshot.as_of_unix_ms,
            continuation: continuation.as_of_unix_ms,
        });
    }
    Ok(())
}

fn validate_continuation_values(
    continuation: &LongerRunnerContinuationEvidence,
) -> Result<(), LongerRunnerError> {
    if continuation.version != LONGER_RUNNER_EVIDENCE_VERSION {
        return Err(LongerRunnerError::InvalidContinuation("unsupported evidence version"));
    }
    if continuation.forecast_source_version.trim().is_empty() {
        return Err(LongerRunnerError::InvalidContinuation("forecast source version must not be empty"));
    }
    if continuation.forecast_horizon_ms == 0 {
        return Err(LongerRunnerError::InvalidContinuation("forecast horizon must be positive"));
    }
    require_positive_finite(continuation.base_quantity, "base quantity")?;
    require_positive_finite(
        continuation.current_executable_exit_price_quote,
        "current executable exit price quote",
    )?;
    require_positive_finite(
        continuation.expected_future_exit_price_quote,
        "expected future exit price quote",
    )?;
    require_positive_finite(continuation.downside_exit_price_quote, "downside exit price quote")?;
    require_positive_finite(continuation.current_exit_capacity_base, "current exit capacity base")?;
    require_positive_finite(
        continuation.expected_future_exit_capacity_base,
        "expected future exit capacity base",
    )?;
    if !continuation.expected_holding_cost_quote.is_finite()
        || continuation.expected_holding_cost_quote < 0.0
    {
        return Err(LongerRunnerError::InvalidContinuation(
            "expected holding cost quote must be finite and non-negative",
        ));
    }
    Ok(())
}

fn validate_exit_costs(costs: &ExecutionLegCostInput) -> Result<ValidatedExitCosts, LongerRunnerError> {
    for (name, value) in [
        ("effective fee bps", costs.effective_fee_bps),
        ("expected impact bps", costs.expected_impact_bps),
        ("expected slippage bps", costs.expected_slippage_bps),
        ("expected latency bps", costs.expected_latency_bps),
    ] {
        if value > 10_000 {
            return Err(LongerRunnerError::InvalidExitCosts(name));
        }
    }

    let variable_bps = costs
        .effective_fee_bps
        .checked_add(costs.expected_impact_bps)
        .and_then(|value| value.checked_add(costs.expected_slippage_bps))
        .and_then(|value| value.checked_add(costs.expected_latency_bps))
        .ok_or(LongerRunnerError::InvalidExitCosts("combined variable bps overflow"))?;
    if variable_bps >= 10_000 {
        return Err(LongerRunnerError::InvalidExitCosts(
            "combined variable exit bps must be below 10000",
        ));
    }

    for (name, value) in [
        ("network fee quote", costs.network_fee_quote),
        ("priority fee quote", costs.priority_fee_quote),
        ("expected failure cost quote", costs.expected_failure_cost_quote),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(LongerRunnerError::InvalidExitCosts(name));
        }
    }

    let fixed_quote = finite_result(
        costs.network_fee_quote + costs.priority_fee_quote + costs.expected_failure_cost_quote,
        "fixed exit cost quote",
    )?;
    Ok(ValidatedExitCosts {
        variable_bps,
        fixed_quote,
    })
}

fn require_positive_finite(value: f64, field: &'static str) -> Result<(), LongerRunnerError> {
    if !value.is_finite() || value <= 0.0 {
        return Err(LongerRunnerError::InvalidContinuation(field));
    }
    Ok(())
}

fn net_exit_quote(
    base_quantity: f64,
    price_quote: f64,
    costs: ValidatedExitCosts,
    field: &'static str,
) -> Result<f64, LongerRunnerError> {
    let gross = finite_result(base_quantity * price_quote, field)?;
    let multiplier = 1.0 - f64::from(costs.variable_bps) / BASIS_POINTS_DENOMINATOR;
    finite_result(gross * multiplier - costs.fixed_quote, field)
}

fn finite_result(value: f64, field: &'static str) -> Result<f64, LongerRunnerError> {
    if !value.is_finite() {
        return Err(LongerRunnerError::NonFiniteResult(field));
    }
    Ok(value)
}

fn empty_assessment(
    snapshot: &FastMarketSnapshot,
    policy: &LongerRunnerPolicy,
    action: FastLaneAction,
    reasons: Vec<LongerRunnerReason>,
) -> LongerRunnerAssessment {
    LongerRunnerAssessment {
        version: LONGER_RUNNER_BASELINE_VERSION,
        policy_version: policy.version,
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        action,
        reasons,
        evidence_version: None,
        forecast_source_version: None,
        forecast_horizon_ms: None,
        base_quantity: None,
        current_gross_exit_quote: None,
        current_net_exit_quote: None,
        expected_future_net_exit_quote: None,
        downside_future_net_exit_quote: None,
        expected_holding_cost_quote: None,
        downside_loss_quote: None,
        risk_penalty_quote: None,
        gross_expected_continuation_quote: None,
        risk_adjusted_continuation_quote: None,
        risk_adjusted_continuation_bps: None,
        current_exit_capacity_base: None,
        expected_future_exit_capacity_base: None,
    }
}

fn assessment_with_evidence(
    snapshot: &FastMarketSnapshot,
    policy: &LongerRunnerPolicy,
    continuation: &LongerRunnerContinuationEvidence,
    action: FastLaneAction,
    reasons: Vec<LongerRunnerReason>,
    economics: Option<ContinuationEconomics>,
) -> LongerRunnerAssessment {
    LongerRunnerAssessment {
        version: LONGER_RUNNER_BASELINE_VERSION,
        policy_version: policy.version,
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        action,
        reasons,
        evidence_version: Some(continuation.version),
        forecast_source_version: Some(continuation.forecast_source_version.clone()),
        forecast_horizon_ms: Some(continuation.forecast_horizon_ms),
        base_quantity: Some(continuation.base_quantity),
        current_gross_exit_quote: economics.map(|value| value.current_gross_exit_quote),
        current_net_exit_quote: economics.map(|value| value.current_net_exit_quote),
        expected_future_net_exit_quote: economics.map(|value| value.expected_future_net_exit_quote),
        downside_future_net_exit_quote: economics.map(|value| value.downside_future_net_exit_quote),
        expected_holding_cost_quote: economics.map(|_| continuation.expected_holding_cost_quote),
        downside_loss_quote: economics.map(|value| value.downside_loss_quote),
        risk_penalty_quote: economics.map(|value| value.risk_penalty_quote),
        gross_expected_continuation_quote: economics.map(|value| value.gross_expected_continuation_quote),
        risk_adjusted_continuation_quote: economics.map(|value| value.risk_adjusted_continuation_quote),
        risk_adjusted_continuation_bps: economics.map(|value| value.risk_adjusted_continuation_bps),
        current_exit_capacity_base: Some(continuation.current_exit_capacity_base),
        expected_future_exit_capacity_base: Some(continuation.expected_future_exit_capacity_base),
    }
}
