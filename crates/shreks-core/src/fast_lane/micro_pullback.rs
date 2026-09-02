use std::{error::Error, fmt};

use super::{
    ExecutionCostModel, ExecutionEconomics, ExecutionEconomicsError, ExecutionTradeInput,
    FastLaneAction, FastMarketKey, FastMarketSnapshot, FastWindowSummary,
};

pub const MICRO_PULLBACK_BASELINE_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq)]
pub struct MicroPullbackPolicy {
    pub version: u16,
    pub reclaim_window_ms: u64,
    pub structure_window_ms: u64,
    pub min_impulse_move_fraction: f64,
    pub min_pullback_depth_fraction: f64,
    pub max_pullback_depth_fraction: f64,
    pub min_reclaim_fraction: f64,
    pub min_reclaim_buy_count: u64,
    pub min_reclaim_unique_buy_actors: u64,
    pub min_reclaim_buy_arrival_rate_per_second: f64,
    pub max_reclaim_sell_arrival_rate_per_second: f64,
    pub min_reclaim_count_imbalance: f64,
    pub min_reclaim_quote_flow_imbalance: f64,
    pub min_reclaim_quote_flow_velocity_per_second: f64,
    pub min_reclaim_quote_flow_acceleration_per_second2: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MicroPullbackExecutionInput {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub cost_model: ExecutionCostModel,
    pub trade: ExecutionTradeInput,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum MicroPullbackReason {
    MissingStructureWindow,
    MissingReclaimWindow,
    MissingOrderedImpulseLow,
    MissingPostHighTrough,
    ReclaimNotAfterTrough,
    ImpulseMoveBelowMinimum,
    PullbackTooShallow,
    PullbackTooDeep,
    ReclaimFractionBelowMinimum,
    ReclaimBuyCountBelowMinimum,
    ReclaimUniqueBuyActorsBelowMinimum,
    ReclaimBuyArrivalBelowMinimum,
    ReclaimSellArrivalAboveMaximum,
    ReclaimCountImbalanceBelowMinimum,
    ReclaimQuoteFlowImbalanceBelowMinimum,
    ReclaimVelocityBelowMinimum,
    ReclaimAccelerationBelowMinimum,
    ExecutionEconomicsUnavailable,
    InsufficientExitCapacity,
    ForecastNetPnlNotPositive,
    EntryPriceAboveMaximum,
    AllConditionsMet,
}

impl MicroPullbackReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MissingStructureWindow => "missing_structure_window",
            Self::MissingReclaimWindow => "missing_reclaim_window",
            Self::MissingOrderedImpulseLow => "missing_ordered_impulse_low",
            Self::MissingPostHighTrough => "missing_post_high_trough",
            Self::ReclaimNotAfterTrough => "reclaim_not_after_trough",
            Self::ImpulseMoveBelowMinimum => "impulse_move_below_minimum",
            Self::PullbackTooShallow => "pullback_too_shallow",
            Self::PullbackTooDeep => "pullback_too_deep",
            Self::ReclaimFractionBelowMinimum => "reclaim_fraction_below_minimum",
            Self::ReclaimBuyCountBelowMinimum => "reclaim_buy_count_below_minimum",
            Self::ReclaimUniqueBuyActorsBelowMinimum => {
                "reclaim_unique_buy_actors_below_minimum"
            }
            Self::ReclaimBuyArrivalBelowMinimum => "reclaim_buy_arrival_below_minimum",
            Self::ReclaimSellArrivalAboveMaximum => "reclaim_sell_arrival_above_maximum",
            Self::ReclaimCountImbalanceBelowMinimum => "reclaim_count_imbalance_below_minimum",
            Self::ReclaimQuoteFlowImbalanceBelowMinimum => {
                "reclaim_quote_flow_imbalance_below_minimum"
            }
            Self::ReclaimVelocityBelowMinimum => "reclaim_velocity_below_minimum",
            Self::ReclaimAccelerationBelowMinimum => "reclaim_acceleration_below_minimum",
            Self::ExecutionEconomicsUnavailable => "execution_economics_unavailable",
            Self::InsufficientExitCapacity => "insufficient_exit_capacity",
            Self::ForecastNetPnlNotPositive => "forecast_net_pnl_not_positive",
            Self::EntryPriceAboveMaximum => "entry_price_above_maximum",
            Self::AllConditionsMet => "all_conditions_met",
        }
    }
}

impl fmt::Display for MicroPullbackReason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct MicroPullbackAssessment {
    pub version: u16,
    pub policy_version: u16,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub action: FastLaneAction,
    pub reasons: Vec<MicroPullbackReason>,
    pub reclaim_window_ms: u64,
    pub structure_window_ms: u64,
    pub impulse_move_fraction: Option<f64>,
    pub pullback_depth_fraction: Option<f64>,
    pub reclaim_fraction: Option<f64>,
    pub intended_base_quantity: Option<f64>,
    pub executable_entry_price_quote: Option<f64>,
    pub forecast_exit_price_quote: Option<f64>,
    pub exit_capacity_base: Option<f64>,
    pub forecast_net_pnl_quote: Option<f64>,
    pub break_even_move_bps: Option<f64>,
    pub maximum_acceptable_entry_price_quote: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MicroPullbackError {
    InvalidPolicy(&'static str),
    InvalidSnapshot(&'static str),
    ExecutionMarketMismatch,
    ExecutionTimestampMismatch { snapshot: i64, execution: i64 },
    ExecutionEconomics(ExecutionEconomicsError),
}

impl fmt::Display for MicroPullbackError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPolicy(field) => {
                write!(formatter, "FL6.2 micro pullback policy is invalid: {field}")
            }
            Self::InvalidSnapshot(field) => {
                write!(formatter, "FL6.2 micro pullback snapshot is invalid: {field}")
            }
            Self::ExecutionMarketMismatch => formatter.write_str(
                "FL6.2 execution evidence market does not match the point-in-time snapshot",
            ),
            Self::ExecutionTimestampMismatch { snapshot, execution } => write!(
                formatter,
                "FL6.2 execution evidence timestamp {execution} does not match snapshot timestamp {snapshot}"
            ),
            Self::ExecutionEconomics(error) => {
                write!(formatter, "FL6.2 execution economics failed closed: {error}")
            }
        }
    }
}

impl Error for MicroPullbackError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::ExecutionEconomics(error) => Some(error),
            _ => None,
        }
    }
}

pub fn assess_micro_pullback(
    snapshot: &FastMarketSnapshot,
    execution: Option<&MicroPullbackExecutionInput>,
    policy: &MicroPullbackPolicy,
) -> Result<MicroPullbackAssessment, MicroPullbackError> {
    validate_policy(policy)?;
    if snapshot.as_of_unix_ms < 0 {
        return Err(MicroPullbackError::InvalidSnapshot(
            "as_of_unix_ms must be non-negative",
        ));
    }

    let structure = snapshot.window(policy.structure_window_ms);
    let reclaim = snapshot.window(policy.reclaim_window_ms);
    if let Some(window) = structure {
        validate_window(window, "structure window contains invalid numeric state")?;
    }
    if let Some(window) = reclaim {
        validate_window(window, "reclaim window contains invalid numeric state")?;
    }

    let mut reasons = Vec::new();
    let mut impulse_move_fraction = None;
    let mut pullback_depth_fraction = None;
    let mut reclaim_fraction = None;

    match structure {
        None => reasons.push(MicroPullbackReason::MissingStructureWindow),
        Some(structure) => {
            let ordered_impulse = match (
                structure.local_low_price_quote,
                structure.local_low_sequence,
                structure.local_high_price_quote,
                structure.local_high_sequence,
            ) {
                (Some(low), Some(low_sequence), Some(high), Some(high_sequence))
                    if low_sequence < high_sequence && high > low =>
                {
                    let impulse = (high - low) / low;
                    impulse_move_fraction = Some(impulse);
                    if impulse < policy.min_impulse_move_fraction {
                        reasons.push(MicroPullbackReason::ImpulseMoveBelowMinimum);
                    }
                    Some((high, high_sequence))
                }
                _ => {
                    reasons.push(MicroPullbackReason::MissingOrderedImpulseLow);
                    None
                }
            };

            if let Some((high, high_sequence)) = ordered_impulse {
                match (
                    structure.post_high_low_price_quote,
                    structure.post_high_low_sequence,
                ) {
                    (Some(trough), Some(trough_sequence)) if trough_sequence > high_sequence => {
                        let pullback = (high - trough) / high;
                        pullback_depth_fraction = Some(pullback);
                        if pullback < policy.min_pullback_depth_fraction {
                            reasons.push(MicroPullbackReason::PullbackTooShallow);
                        }
                        if pullback > policy.max_pullback_depth_fraction {
                            reasons.push(MicroPullbackReason::PullbackTooDeep);
                        }

                        let latest_after_trough = snapshot
                            .last_sequence
                            .is_some_and(|last_sequence| last_sequence > trough_sequence);
                        if !latest_after_trough {
                            reasons.push(MicroPullbackReason::ReclaimNotAfterTrough);
                        } else if let Some(last) = structure.last_price_quote {
                            let pullback_range = high - trough;
                            if pullback_range > 0.0 {
                                if last < trough {
                                    return Err(MicroPullbackError::InvalidSnapshot(
                                        "last structure price is below the recorded post-high trough",
                                    ));
                                }
                                let reclaimed = (last - trough) / pullback_range;
                                reclaim_fraction = Some(reclaimed);
                                if reclaimed < policy.min_reclaim_fraction {
                                    reasons.push(MicroPullbackReason::ReclaimFractionBelowMinimum);
                                }
                            }
                        }
                    }
                    _ => reasons.push(MicroPullbackReason::MissingPostHighTrough),
                }
            }
        }
    }

    match reclaim {
        None => reasons.push(MicroPullbackReason::MissingReclaimWindow),
        Some(reclaim) => {
            if reclaim.buy_count < policy.min_reclaim_buy_count {
                reasons.push(MicroPullbackReason::ReclaimBuyCountBelowMinimum);
            }
            if reclaim.unique_buy_actors < policy.min_reclaim_unique_buy_actors {
                reasons.push(MicroPullbackReason::ReclaimUniqueBuyActorsBelowMinimum);
            }
            if reclaim.buy_arrival_rate_per_second
                < policy.min_reclaim_buy_arrival_rate_per_second
            {
                reasons.push(MicroPullbackReason::ReclaimBuyArrivalBelowMinimum);
            }
            if reclaim.sell_arrival_rate_per_second
                > policy.max_reclaim_sell_arrival_rate_per_second
            {
                reasons.push(MicroPullbackReason::ReclaimSellArrivalAboveMaximum);
            }
            if reclaim.count_imbalance < policy.min_reclaim_count_imbalance {
                reasons.push(MicroPullbackReason::ReclaimCountImbalanceBelowMinimum);
            }
            if reclaim.quote_flow_imbalance < policy.min_reclaim_quote_flow_imbalance {
                reasons.push(MicroPullbackReason::ReclaimQuoteFlowImbalanceBelowMinimum);
            }
            if reclaim.quote_flow_velocity_per_second
                < policy.min_reclaim_quote_flow_velocity_per_second
            {
                reasons.push(MicroPullbackReason::ReclaimVelocityBelowMinimum);
            }
            if reclaim.quote_flow_acceleration_per_second2
                < policy.min_reclaim_quote_flow_acceleration_per_second2
            {
                reasons.push(MicroPullbackReason::ReclaimAccelerationBelowMinimum);
            }
        }
    }

    let mut intended_base_quantity = None;
    let mut executable_entry_price_quote = None;
    let mut forecast_exit_price_quote = None;
    let mut exit_capacity_base = None;
    let mut forecast_net_pnl_quote = None;
    let mut break_even_move_bps = None;
    let mut maximum_acceptable_entry_price_quote = None;

    match execution {
        None => reasons.push(MicroPullbackReason::ExecutionEconomicsUnavailable),
        Some(execution) => {
            if execution.market != snapshot.market {
                return Err(MicroPullbackError::ExecutionMarketMismatch);
            }
            if execution.as_of_unix_ms != snapshot.as_of_unix_ms {
                return Err(MicroPullbackError::ExecutionTimestampMismatch {
                    snapshot: snapshot.as_of_unix_ms,
                    execution: execution.as_of_unix_ms,
                });
            }

            intended_base_quantity = Some(execution.trade.base_quantity);
            executable_entry_price_quote = Some(execution.trade.executable_entry_price_quote);
            forecast_exit_price_quote = Some(execution.trade.forecast_exit_price_quote);
            exit_capacity_base = Some(execution.trade.exit_capacity_base);

            match ExecutionEconomics::assess(&execution.cost_model, &execution.trade) {
                Ok(economics) => {
                    forecast_net_pnl_quote = Some(economics.forecast_net_pnl_quote);
                    break_even_move_bps = Some(economics.break_even_move_bps);
                    maximum_acceptable_entry_price_quote =
                        Some(economics.maximum_acceptable_entry_price_quote);

                    if economics.forecast_net_pnl_quote <= 0.0 {
                        reasons.push(MicroPullbackReason::ForecastNetPnlNotPositive);
                    }
                    if execution.trade.executable_entry_price_quote
                        > economics.maximum_acceptable_entry_price_quote
                    {
                        reasons.push(MicroPullbackReason::EntryPriceAboveMaximum);
                    }
                }
                Err(ExecutionEconomicsError::InsufficientExitCapacity) => {
                    reasons.push(MicroPullbackReason::InsufficientExitCapacity);
                }
                Err(error) => return Err(MicroPullbackError::ExecutionEconomics(error)),
            }
        }
    }

    canonicalize_reason_order(&mut reasons);
    let action = if reasons.is_empty() {
        reasons.push(MicroPullbackReason::AllConditionsMet);
        FastLaneAction::Buy
    } else {
        FastLaneAction::Skip
    };

    Ok(MicroPullbackAssessment {
        version: MICRO_PULLBACK_BASELINE_VERSION,
        policy_version: policy.version,
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        action,
        reasons,
        reclaim_window_ms: policy.reclaim_window_ms,
        structure_window_ms: policy.structure_window_ms,
        impulse_move_fraction,
        pullback_depth_fraction,
        reclaim_fraction,
        intended_base_quantity,
        executable_entry_price_quote,
        forecast_exit_price_quote,
        exit_capacity_base,
        forecast_net_pnl_quote,
        break_even_move_bps,
        maximum_acceptable_entry_price_quote,
    })
}

fn validate_policy(policy: &MicroPullbackPolicy) -> Result<(), MicroPullbackError> {
    if policy.version != MICRO_PULLBACK_BASELINE_VERSION {
        return Err(MicroPullbackError::InvalidPolicy(
            "unsupported policy version",
        ));
    }
    if policy.reclaim_window_ms == 0 || policy.structure_window_ms == 0 {
        return Err(MicroPullbackError::InvalidPolicy(
            "configured windows must be positive",
        ));
    }
    if policy.reclaim_window_ms >= policy.structure_window_ms {
        return Err(MicroPullbackError::InvalidPolicy(
            "reclaim_window_ms must be smaller than structure_window_ms",
        ));
    }
    if policy.min_reclaim_buy_count == 0 || policy.min_reclaim_unique_buy_actors == 0 {
        return Err(MicroPullbackError::InvalidPolicy(
            "reclaim participation counts must be positive",
        ));
    }

    validate_positive_fraction(
        policy.min_impulse_move_fraction,
        "min_impulse_move_fraction must be finite and within (0, 1]",
    )?;
    validate_unit_interval(
        policy.min_pullback_depth_fraction,
        "min_pullback_depth_fraction must be finite and within [0, 1]",
    )?;
    validate_unit_interval(
        policy.max_pullback_depth_fraction,
        "max_pullback_depth_fraction must be finite and within [0, 1]",
    )?;
    if policy.min_pullback_depth_fraction > policy.max_pullback_depth_fraction {
        return Err(MicroPullbackError::InvalidPolicy(
            "minimum pullback depth cannot exceed maximum pullback depth",
        ));
    }
    validate_unit_interval(
        policy.min_reclaim_fraction,
        "min_reclaim_fraction must be finite and within [0, 1]",
    )?;
    validate_positive_finite(
        policy.min_reclaim_buy_arrival_rate_per_second,
        "min_reclaim_buy_arrival_rate_per_second must be positive and finite",
    )?;
    validate_non_negative_finite(
        policy.max_reclaim_sell_arrival_rate_per_second,
        "max_reclaim_sell_arrival_rate_per_second must be non-negative and finite",
    )?;
    validate_unit_interval(
        policy.min_reclaim_count_imbalance,
        "min_reclaim_count_imbalance must be finite and within [0, 1]",
    )?;
    validate_unit_interval(
        policy.min_reclaim_quote_flow_imbalance,
        "min_reclaim_quote_flow_imbalance must be finite and within [0, 1]",
    )?;
    validate_positive_finite(
        policy.min_reclaim_quote_flow_velocity_per_second,
        "min_reclaim_quote_flow_velocity_per_second must be positive and finite",
    )?;
    validate_positive_finite(
        policy.min_reclaim_quote_flow_acceleration_per_second2,
        "min_reclaim_quote_flow_acceleration_per_second2 must be positive and finite",
    )?;
    Ok(())
}

fn validate_positive_fraction(value: f64, message: &'static str) -> Result<(), MicroPullbackError> {
    if !value.is_finite() || value <= 0.0 || value > 1.0 {
        return Err(MicroPullbackError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_unit_interval(value: f64, message: &'static str) -> Result<(), MicroPullbackError> {
    if !value.is_finite() || !(0.0..=1.0).contains(&value) {
        return Err(MicroPullbackError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_positive_finite(value: f64, message: &'static str) -> Result<(), MicroPullbackError> {
    if !value.is_finite() || value <= 0.0 {
        return Err(MicroPullbackError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_non_negative_finite(
    value: f64,
    message: &'static str,
) -> Result<(), MicroPullbackError> {
    if !value.is_finite() || value < 0.0 {
        return Err(MicroPullbackError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_window(
    window: &FastWindowSummary,
    message: &'static str,
) -> Result<(), MicroPullbackError> {
    let numeric = [
        window.buy_arrival_rate_per_second,
        window.sell_arrival_rate_per_second,
        window.count_imbalance,
        window.buy_base_quantity,
        window.sell_base_quantity,
        window.buy_quote_quantity,
        window.sell_quote_quantity,
        window.net_quote_quantity,
        window.quote_flow_imbalance,
        window.quote_flow_velocity_per_second,
        window.quote_flow_acceleration_per_second2,
        window.drawdown_from_local_high,
        window.recovery_from_local_low,
    ];
    if numeric.iter().any(|value| !value.is_finite()) {
        return Err(MicroPullbackError::InvalidSnapshot(message));
    }
    if window.drawdown_from_local_high < 0.0 || window.recovery_from_local_low < 0.0 {
        return Err(MicroPullbackError::InvalidSnapshot(message));
    }

    for price in [
        window.local_high_price_quote,
        window.local_low_price_quote,
        window.post_high_low_price_quote,
        window.last_price_quote,
    ]
    .into_iter()
    .flatten()
    {
        if !price.is_finite() || price <= 0.0 {
            return Err(MicroPullbackError::InvalidSnapshot(message));
        }
    }

    for observed_at in [
        window.local_high_observed_at_unix_ms,
        window.local_low_observed_at_unix_ms,
        window.post_high_low_observed_at_unix_ms,
    ]
    .into_iter()
    .flatten()
    {
        if observed_at < 0 {
            return Err(MicroPullbackError::InvalidSnapshot(message));
        }
    }
    Ok(())
}

fn canonicalize_reason_order(reasons: &mut Vec<MicroPullbackReason>) {
    const ORDER: [MicroPullbackReason; 21] = [
        MicroPullbackReason::MissingStructureWindow,
        MicroPullbackReason::MissingReclaimWindow,
        MicroPullbackReason::MissingOrderedImpulseLow,
        MicroPullbackReason::MissingPostHighTrough,
        MicroPullbackReason::ReclaimNotAfterTrough,
        MicroPullbackReason::ImpulseMoveBelowMinimum,
        MicroPullbackReason::PullbackTooShallow,
        MicroPullbackReason::PullbackTooDeep,
        MicroPullbackReason::ReclaimFractionBelowMinimum,
        MicroPullbackReason::ReclaimBuyCountBelowMinimum,
        MicroPullbackReason::ReclaimUniqueBuyActorsBelowMinimum,
        MicroPullbackReason::ReclaimBuyArrivalBelowMinimum,
        MicroPullbackReason::ReclaimSellArrivalAboveMaximum,
        MicroPullbackReason::ReclaimCountImbalanceBelowMinimum,
        MicroPullbackReason::ReclaimQuoteFlowImbalanceBelowMinimum,
        MicroPullbackReason::ReclaimVelocityBelowMinimum,
        MicroPullbackReason::ReclaimAccelerationBelowMinimum,
        MicroPullbackReason::ExecutionEconomicsUnavailable,
        MicroPullbackReason::InsufficientExitCapacity,
        MicroPullbackReason::ForecastNetPnlNotPositive,
        MicroPullbackReason::EntryPriceAboveMaximum,
    ];
    reasons.sort_by_key(|reason| {
        ORDER
            .iter()
            .position(|candidate| candidate == reason)
            .unwrap_or(ORDER.len())
    });
    reasons.dedup();
}
