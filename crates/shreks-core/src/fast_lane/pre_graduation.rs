use std::{error::Error, fmt};

use crate::{LifecycleEventKind, VenueId};

use super::{
    ExecutionCostModel, ExecutionEconomics, ExecutionEconomicsError, ExecutionTradeInput,
    FastLaneAction, FastMarketKey, FastMarketSnapshot, FastReserveContext, FastWindowSummary,
};

pub const PRE_GRADUATION_BASELINE_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq)]
pub struct PreGraduationPolicy {
    pub version: u16,
    pub signal_window_ms: u64,
    pub context_window_ms: u64,
    pub graduation_target_real_base_reserve_raw: u64,
    pub maximum_pre_graduation_real_base_reserve_raw: u64,
    pub min_buy_count: u64,
    pub min_unique_buy_actors: u64,
    pub min_buy_arrival_rate_per_second: f64,
    pub min_count_imbalance: f64,
    pub min_quote_flow_imbalance: f64,
    pub min_quote_flow_velocity_per_second: f64,
    pub min_quote_flow_acceleration_per_second2: f64,
    pub min_velocity_expansion_ratio: f64,
    pub min_buy_participation_of_remaining: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PreGraduationExecutionInput {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub cost_model: ExecutionCostModel,
    pub trade: ExecutionTradeInput,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PreGraduationReason {
    NotPumpBondingCurve,
    AlreadyGraduated,
    MissingSignalWindow,
    MissingContextWindow,
    PumpCurveReserveUnavailable,
    GraduationTargetReached,
    TooFarFromGraduation,
    BuyCountBelowMinimum,
    UniqueBuyActorsBelowMinimum,
    BuyArrivalBelowMinimum,
    CountImbalanceBelowMinimum,
    QuoteFlowImbalanceBelowMinimum,
    QuoteFlowVelocityBelowMinimum,
    QuoteFlowAccelerationBelowMinimum,
    VelocityExpansionBelowMinimum,
    BuyParticipationBelowMinimum,
    ExecutionEconomicsUnavailable,
    InsufficientExitCapacity,
    ForecastNetPnlNotPositive,
    EntryPriceAboveMaximum,
    AllConditionsMet,
}

impl PreGraduationReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::NotPumpBondingCurve => "not_pump_bonding_curve",
            Self::AlreadyGraduated => "already_graduated",
            Self::MissingSignalWindow => "missing_signal_window",
            Self::MissingContextWindow => "missing_context_window",
            Self::PumpCurveReserveUnavailable => "pump_curve_reserve_unavailable",
            Self::GraduationTargetReached => "graduation_target_reached",
            Self::TooFarFromGraduation => "too_far_from_graduation",
            Self::BuyCountBelowMinimum => "buy_count_below_minimum",
            Self::UniqueBuyActorsBelowMinimum => "unique_buy_actors_below_minimum",
            Self::BuyArrivalBelowMinimum => "buy_arrival_below_minimum",
            Self::CountImbalanceBelowMinimum => "count_imbalance_below_minimum",
            Self::QuoteFlowImbalanceBelowMinimum => "quote_flow_imbalance_below_minimum",
            Self::QuoteFlowVelocityBelowMinimum => "quote_flow_velocity_below_minimum",
            Self::QuoteFlowAccelerationBelowMinimum => "quote_flow_acceleration_below_minimum",
            Self::VelocityExpansionBelowMinimum => "velocity_expansion_below_minimum",
            Self::BuyParticipationBelowMinimum => "buy_participation_below_minimum",
            Self::ExecutionEconomicsUnavailable => "execution_economics_unavailable",
            Self::InsufficientExitCapacity => "insufficient_exit_capacity",
            Self::ForecastNetPnlNotPositive => "forecast_net_pnl_not_positive",
            Self::EntryPriceAboveMaximum => "entry_price_above_maximum",
            Self::AllConditionsMet => "all_conditions_met",
        }
    }
}

impl fmt::Display for PreGraduationReason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct PreGraduationAssessment {
    pub version: u16,
    pub policy_version: u16,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub action: FastLaneAction,
    pub reasons: Vec<PreGraduationReason>,
    pub signal_window_ms: u64,
    pub context_window_ms: u64,
    pub current_real_base_reserve_raw: Option<u64>,
    pub distance_to_graduation_raw: Option<u64>,
    pub reserve_base_decimals: Option<u8>,
    pub buy_participation_of_remaining: Option<f64>,
    pub velocity_expansion_ratio: Option<f64>,
    pub intended_base_quantity: Option<f64>,
    pub executable_entry_price_quote: Option<f64>,
    pub forecast_exit_price_quote: Option<f64>,
    pub exit_capacity_base: Option<f64>,
    pub forecast_net_pnl_quote: Option<f64>,
    pub break_even_move_bps: Option<f64>,
    pub maximum_acceptable_entry_price_quote: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PreGraduationError {
    InvalidPolicy(&'static str),
    InvalidSnapshot(&'static str),
    ExecutionMarketMismatch,
    ExecutionTimestampMismatch { snapshot: i64, execution: i64 },
    ExecutionEconomics(ExecutionEconomicsError),
}

impl fmt::Display for PreGraduationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPolicy(field) => write!(
                formatter,
                "FL6.3 pre-graduation policy is invalid: {field}"
            ),
            Self::InvalidSnapshot(field) => write!(
                formatter,
                "FL6.3 pre-graduation snapshot is invalid: {field}"
            ),
            Self::ExecutionMarketMismatch => formatter.write_str(
                "FL6.3 execution evidence market does not match the point-in-time snapshot",
            ),
            Self::ExecutionTimestampMismatch { snapshot, execution } => write!(
                formatter,
                "FL6.3 execution evidence timestamp {execution} does not match snapshot timestamp {snapshot}"
            ),
            Self::ExecutionEconomics(error) => {
                write!(formatter, "FL6.3 execution economics failed closed: {error}")
            }
        }
    }
}

impl Error for PreGraduationError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::ExecutionEconomics(error) => Some(error),
            _ => None,
        }
    }
}

pub fn assess_pre_graduation_acceleration(
    snapshot: &FastMarketSnapshot,
    execution: Option<&PreGraduationExecutionInput>,
    policy: &PreGraduationPolicy,
) -> Result<PreGraduationAssessment, PreGraduationError> {
    validate_policy(policy)?;
    if snapshot.as_of_unix_ms < 0 {
        return Err(PreGraduationError::InvalidSnapshot(
            "as_of_unix_ms must be non-negative",
        ));
    }

    if let Some(lifecycle) = snapshot.last_lifecycle_event.as_ref() {
        if lifecycle.detected_at_unix_ms > snapshot.as_of_unix_ms {
            return Err(PreGraduationError::InvalidSnapshot(
                "lifecycle evidence is after snapshot as_of_unix_ms",
            ));
        }
    }

    let signal = snapshot.window(policy.signal_window_ms);
    let context = snapshot.window(policy.context_window_ms);
    if let Some(window) = signal {
        validate_window(window, "signal window contains invalid numeric state")?;
    }
    if let Some(window) = context {
        validate_window(window, "context window contains invalid numeric state")?;
    }

    let mut reasons = Vec::new();

    if snapshot.market.venue != VenueId::PumpFunBondingCurve {
        reasons.push(PreGraduationReason::NotPumpBondingCurve);
    }

    if snapshot
        .last_lifecycle_event
        .as_ref()
        .is_some_and(|event| event.kind == LifecycleEventKind::PumpGraduation)
    {
        reasons.push(PreGraduationReason::AlreadyGraduated);
    }

    match signal {
        None => reasons.push(PreGraduationReason::MissingSignalWindow),
        Some(signal) => {
            if signal.buy_count < policy.min_buy_count {
                reasons.push(PreGraduationReason::BuyCountBelowMinimum);
            }
            if signal.unique_buy_actors < policy.min_unique_buy_actors {
                reasons.push(PreGraduationReason::UniqueBuyActorsBelowMinimum);
            }
            if signal.buy_arrival_rate_per_second < policy.min_buy_arrival_rate_per_second {
                reasons.push(PreGraduationReason::BuyArrivalBelowMinimum);
            }
            if signal.count_imbalance < policy.min_count_imbalance {
                reasons.push(PreGraduationReason::CountImbalanceBelowMinimum);
            }
            if signal.quote_flow_imbalance < policy.min_quote_flow_imbalance {
                reasons.push(PreGraduationReason::QuoteFlowImbalanceBelowMinimum);
            }
            if signal.quote_flow_velocity_per_second
                < policy.min_quote_flow_velocity_per_second
            {
                reasons.push(PreGraduationReason::QuoteFlowVelocityBelowMinimum);
            }
            if signal.quote_flow_acceleration_per_second2
                < policy.min_quote_flow_acceleration_per_second2
            {
                reasons.push(PreGraduationReason::QuoteFlowAccelerationBelowMinimum);
            }
        }
    }

    let mut velocity_expansion_ratio = None;
    match context {
        None => reasons.push(PreGraduationReason::MissingContextWindow),
        Some(context) => {
            if let Some(signal) = signal {
                if context.quote_flow_velocity_per_second > 0.0 {
                    let ratio = signal.quote_flow_velocity_per_second
                        / context.quote_flow_velocity_per_second;
                    velocity_expansion_ratio = Some(ratio);
                    if ratio < policy.min_velocity_expansion_ratio {
                        reasons.push(PreGraduationReason::VelocityExpansionBelowMinimum);
                    }
                }
            }
        }
    }

    let mut current_real_base_reserve_raw = None;
    let mut distance_to_graduation_raw = None;
    let mut reserve_base_decimals = None;
    let mut buy_participation_of_remaining = None;

    match snapshot.last_reserve_context.as_ref() {
        Some(FastReserveContext::PumpCurve {
            real_base_reserve_raw,
            base_decimals,
            ..
        }) if snapshot.market.venue == VenueId::PumpFunBondingCurve => {
            let current = *real_base_reserve_raw;
            current_real_base_reserve_raw = Some(current);
            reserve_base_decimals = Some(*base_decimals);

            if current <= policy.graduation_target_real_base_reserve_raw {
                reasons.push(PreGraduationReason::GraduationTargetReached);
            } else {
                let distance = current - policy.graduation_target_real_base_reserve_raw;
                distance_to_graduation_raw = Some(distance);

                if current > policy.maximum_pre_graduation_real_base_reserve_raw {
                    reasons.push(PreGraduationReason::TooFarFromGraduation);
                }

                if let Some(signal) = signal {
                    let divisor = 10_f64.powi(i32::from(*base_decimals));
                    let normalized_distance = distance as f64 / divisor;
                    if !normalized_distance.is_finite() || normalized_distance <= 0.0 {
                        return Err(PreGraduationError::InvalidSnapshot(
                            "configured remaining curve distance cannot be normalized",
                        ));
                    }
                    let participation = signal.buy_base_quantity / normalized_distance;
                    if !participation.is_finite() || participation < 0.0 {
                        return Err(PreGraduationError::InvalidSnapshot(
                            "buy participation of remaining curve distance is invalid",
                        ));
                    }
                    buy_participation_of_remaining = Some(participation);
                    if participation < policy.min_buy_participation_of_remaining {
                        reasons.push(PreGraduationReason::BuyParticipationBelowMinimum);
                    }
                }
            }
        }
        _ => reasons.push(PreGraduationReason::PumpCurveReserveUnavailable),
    }

    let mut intended_base_quantity = None;
    let mut executable_entry_price_quote = None;
    let mut forecast_exit_price_quote = None;
    let mut exit_capacity_base = None;
    let mut forecast_net_pnl_quote = None;
    let mut break_even_move_bps = None;
    let mut maximum_acceptable_entry_price_quote = None;

    match execution {
        None => reasons.push(PreGraduationReason::ExecutionEconomicsUnavailable),
        Some(execution) => {
            if execution.market != snapshot.market {
                return Err(PreGraduationError::ExecutionMarketMismatch);
            }
            if execution.as_of_unix_ms != snapshot.as_of_unix_ms {
                return Err(PreGraduationError::ExecutionTimestampMismatch {
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
                        reasons.push(PreGraduationReason::ForecastNetPnlNotPositive);
                    }
                    if execution.trade.executable_entry_price_quote
                        > economics.maximum_acceptable_entry_price_quote
                    {
                        reasons.push(PreGraduationReason::EntryPriceAboveMaximum);
                    }
                }
                Err(ExecutionEconomicsError::InsufficientExitCapacity) => {
                    reasons.push(PreGraduationReason::InsufficientExitCapacity);
                }
                Err(error) => return Err(PreGraduationError::ExecutionEconomics(error)),
            }
        }
    }

    canonicalize_reason_order(&mut reasons);
    let action = if reasons.is_empty() {
        reasons.push(PreGraduationReason::AllConditionsMet);
        FastLaneAction::Buy
    } else {
        FastLaneAction::Skip
    };

    Ok(PreGraduationAssessment {
        version: PRE_GRADUATION_BASELINE_VERSION,
        policy_version: policy.version,
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        action,
        reasons,
        signal_window_ms: policy.signal_window_ms,
        context_window_ms: policy.context_window_ms,
        current_real_base_reserve_raw,
        distance_to_graduation_raw,
        reserve_base_decimals,
        buy_participation_of_remaining,
        velocity_expansion_ratio,
        intended_base_quantity,
        executable_entry_price_quote,
        forecast_exit_price_quote,
        exit_capacity_base,
        forecast_net_pnl_quote,
        break_even_move_bps,
        maximum_acceptable_entry_price_quote,
    })
}

fn validate_policy(policy: &PreGraduationPolicy) -> Result<(), PreGraduationError> {
    if policy.version != PRE_GRADUATION_BASELINE_VERSION {
        return Err(PreGraduationError::InvalidPolicy(
            "unsupported policy version",
        ));
    }
    if policy.signal_window_ms == 0 || policy.context_window_ms == 0 {
        return Err(PreGraduationError::InvalidPolicy(
            "configured windows must be positive",
        ));
    }
    if policy.signal_window_ms >= policy.context_window_ms {
        return Err(PreGraduationError::InvalidPolicy(
            "signal_window_ms must be smaller than context_window_ms",
        ));
    }
    if policy.graduation_target_real_base_reserve_raw
        >= policy.maximum_pre_graduation_real_base_reserve_raw
    {
        return Err(PreGraduationError::InvalidPolicy(
            "graduation target reserve must be below maximum pre-graduation reserve",
        ));
    }
    if policy.min_buy_count == 0 || policy.min_unique_buy_actors == 0 {
        return Err(PreGraduationError::InvalidPolicy(
            "buy participation counts must be positive",
        ));
    }
    validate_positive_finite(
        policy.min_buy_arrival_rate_per_second,
        "min_buy_arrival_rate_per_second must be positive and finite",
    )?;
    validate_unit_interval(
        policy.min_count_imbalance,
        "min_count_imbalance must be finite and within [0, 1]",
    )?;
    validate_unit_interval(
        policy.min_quote_flow_imbalance,
        "min_quote_flow_imbalance must be finite and within [0, 1]",
    )?;
    validate_positive_finite(
        policy.min_quote_flow_velocity_per_second,
        "min_quote_flow_velocity_per_second must be positive and finite",
    )?;
    validate_positive_finite(
        policy.min_quote_flow_acceleration_per_second2,
        "min_quote_flow_acceleration_per_second2 must be positive and finite",
    )?;
    if !policy.min_velocity_expansion_ratio.is_finite()
        || policy.min_velocity_expansion_ratio < 1.0
    {
        return Err(PreGraduationError::InvalidPolicy(
            "min_velocity_expansion_ratio must be finite and at least 1",
        ));
    }
    validate_positive_finite(
        policy.min_buy_participation_of_remaining,
        "min_buy_participation_of_remaining must be positive and finite",
    )?;
    Ok(())
}

fn validate_positive_finite(value: f64, message: &'static str) -> Result<(), PreGraduationError> {
    if !value.is_finite() || value <= 0.0 {
        return Err(PreGraduationError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_unit_interval(value: f64, message: &'static str) -> Result<(), PreGraduationError> {
    if !value.is_finite() || !(0.0..=1.0).contains(&value) {
        return Err(PreGraduationError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_window(
    window: &FastWindowSummary,
    message: &'static str,
) -> Result<(), PreGraduationError> {
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
        return Err(PreGraduationError::InvalidSnapshot(message));
    }
    if window.buy_base_quantity < 0.0
        || window.sell_base_quantity < 0.0
        || window.buy_quote_quantity < 0.0
        || window.sell_quote_quantity < 0.0
        || window.buy_arrival_rate_per_second < 0.0
        || window.sell_arrival_rate_per_second < 0.0
    {
        return Err(PreGraduationError::InvalidSnapshot(message));
    }
    Ok(())
}

fn canonicalize_reason_order(reasons: &mut Vec<PreGraduationReason>) {
    const ORDER: [PreGraduationReason; 20] = [
        PreGraduationReason::NotPumpBondingCurve,
        PreGraduationReason::AlreadyGraduated,
        PreGraduationReason::MissingSignalWindow,
        PreGraduationReason::MissingContextWindow,
        PreGraduationReason::PumpCurveReserveUnavailable,
        PreGraduationReason::GraduationTargetReached,
        PreGraduationReason::TooFarFromGraduation,
        PreGraduationReason::BuyCountBelowMinimum,
        PreGraduationReason::UniqueBuyActorsBelowMinimum,
        PreGraduationReason::BuyArrivalBelowMinimum,
        PreGraduationReason::CountImbalanceBelowMinimum,
        PreGraduationReason::QuoteFlowImbalanceBelowMinimum,
        PreGraduationReason::QuoteFlowVelocityBelowMinimum,
        PreGraduationReason::QuoteFlowAccelerationBelowMinimum,
        PreGraduationReason::VelocityExpansionBelowMinimum,
        PreGraduationReason::BuyParticipationBelowMinimum,
        PreGraduationReason::ExecutionEconomicsUnavailable,
        PreGraduationReason::InsufficientExitCapacity,
        PreGraduationReason::ForecastNetPnlNotPositive,
        PreGraduationReason::EntryPriceAboveMaximum,
    ];
    reasons.sort_by_key(|reason| {
        ORDER
            .iter()
            .position(|candidate| candidate == reason)
            .unwrap_or(ORDER.len())
    });
    reasons.dedup();
}
