use std::{error::Error, fmt};

use super::{
    ExecutionCostModel, ExecutionEconomics, ExecutionEconomicsError, ExecutionTradeInput,
    FastMarketKey, FastMarketSnapshot, FastWindowSummary,
};

pub const IMPULSE_SCALP_BASELINE_VERSION: u16 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FastLaneAction {
    Buy,
    Skip,
    Hold,
    Reduce,
    Sell,
}

impl FastLaneAction {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Buy => "BUY",
            Self::Skip => "SKIP",
            Self::Hold => "HOLD",
            Self::Reduce => "REDUCE",
            Self::Sell => "SELL",
        }
    }
}

impl fmt::Display for FastLaneAction {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ImpulseScalpPolicy {
    pub version: u16,
    pub signal_window_ms: u64,
    pub context_window_ms: u64,
    pub min_buy_count: u64,
    pub min_unique_buy_actors: u64,
    pub min_count_imbalance: f64,
    pub min_quote_flow_imbalance: f64,
    pub min_quote_flow_velocity_per_second: f64,
    pub min_quote_flow_acceleration_per_second2: f64,
    pub min_velocity_expansion_ratio: f64,
    pub min_recovery_from_local_low: f64,
    pub max_drawdown_from_local_high: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ImpulseScalpExecutionInput {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub cost_model: ExecutionCostModel,
    pub trade: ExecutionTradeInput,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ImpulseScalpReason {
    MissingSignalWindow,
    MissingContextWindow,
    BuyCountBelowMinimum,
    UniqueBuyActorsBelowMinimum,
    CountImbalanceBelowMinimum,
    QuoteFlowImbalanceBelowMinimum,
    QuoteFlowVelocityBelowMinimum,
    QuoteFlowAccelerationBelowMinimum,
    VelocityExpansionBelowMinimum,
    RecoveryBelowMinimum,
    DrawdownAboveMaximum,
    ExecutionEconomicsUnavailable,
    InsufficientExitCapacity,
    ForecastNetPnlNotPositive,
    EntryPriceAboveMaximum,
    AllConditionsMet,
}

impl ImpulseScalpReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MissingSignalWindow => "missing_signal_window",
            Self::MissingContextWindow => "missing_context_window",
            Self::BuyCountBelowMinimum => "buy_count_below_minimum",
            Self::UniqueBuyActorsBelowMinimum => "unique_buy_actors_below_minimum",
            Self::CountImbalanceBelowMinimum => "count_imbalance_below_minimum",
            Self::QuoteFlowImbalanceBelowMinimum => "quote_flow_imbalance_below_minimum",
            Self::QuoteFlowVelocityBelowMinimum => "quote_flow_velocity_below_minimum",
            Self::QuoteFlowAccelerationBelowMinimum => "quote_flow_acceleration_below_minimum",
            Self::VelocityExpansionBelowMinimum => "velocity_expansion_below_minimum",
            Self::RecoveryBelowMinimum => "recovery_below_minimum",
            Self::DrawdownAboveMaximum => "drawdown_above_maximum",
            Self::ExecutionEconomicsUnavailable => "execution_economics_unavailable",
            Self::InsufficientExitCapacity => "insufficient_exit_capacity",
            Self::ForecastNetPnlNotPositive => "forecast_net_pnl_not_positive",
            Self::EntryPriceAboveMaximum => "entry_price_above_maximum",
            Self::AllConditionsMet => "all_conditions_met",
        }
    }
}

impl fmt::Display for ImpulseScalpReason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ImpulseScalpAssessment {
    pub version: u16,
    pub policy_version: u16,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub action: FastLaneAction,
    pub reasons: Vec<ImpulseScalpReason>,
    pub signal_window_ms: u64,
    pub context_window_ms: u64,
    pub intended_base_quantity: Option<f64>,
    pub executable_entry_price_quote: Option<f64>,
    pub forecast_exit_price_quote: Option<f64>,
    pub exit_capacity_base: Option<f64>,
    pub forecast_net_pnl_quote: Option<f64>,
    pub break_even_move_bps: Option<f64>,
    pub maximum_acceptable_entry_price_quote: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ImpulseScalpError {
    InvalidPolicy(&'static str),
    InvalidSnapshot(&'static str),
    ExecutionMarketMismatch,
    ExecutionTimestampMismatch { snapshot: i64, execution: i64 },
    ExecutionEconomics(ExecutionEconomicsError),
}

impl fmt::Display for ImpulseScalpError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPolicy(field) => write!(
                formatter,
                "FL6.1 impulse scalp policy is invalid: {field}"
            ),
            Self::InvalidSnapshot(field) => write!(
                formatter,
                "FL6.1 impulse scalp snapshot is invalid: {field}"
            ),
            Self::ExecutionMarketMismatch => formatter.write_str(
                "FL6.1 execution evidence market does not match the point-in-time snapshot",
            ),
            Self::ExecutionTimestampMismatch { snapshot, execution } => write!(
                formatter,
                "FL6.1 execution evidence timestamp {execution} does not match snapshot timestamp {snapshot}"
            ),
            Self::ExecutionEconomics(error) => {
                write!(formatter, "FL6.1 execution economics failed closed: {error}")
            }
        }
    }
}

impl Error for ImpulseScalpError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::ExecutionEconomics(error) => Some(error),
            _ => None,
        }
    }
}

pub fn assess_impulse_scalp(
    snapshot: &FastMarketSnapshot,
    execution: Option<&ImpulseScalpExecutionInput>,
    policy: &ImpulseScalpPolicy,
) -> Result<ImpulseScalpAssessment, ImpulseScalpError> {
    validate_policy(policy)?;
    if snapshot.as_of_unix_ms < 0 {
        return Err(ImpulseScalpError::InvalidSnapshot(
            "as_of_unix_ms must be non-negative",
        ));
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

    match signal {
        None => reasons.push(ImpulseScalpReason::MissingSignalWindow),
        Some(signal) => {
            if signal.buy_count < policy.min_buy_count {
                reasons.push(ImpulseScalpReason::BuyCountBelowMinimum);
            }
            if signal.unique_buy_actors < policy.min_unique_buy_actors {
                reasons.push(ImpulseScalpReason::UniqueBuyActorsBelowMinimum);
            }
            if signal.count_imbalance < policy.min_count_imbalance {
                reasons.push(ImpulseScalpReason::CountImbalanceBelowMinimum);
            }
            if signal.quote_flow_imbalance < policy.min_quote_flow_imbalance {
                reasons.push(ImpulseScalpReason::QuoteFlowImbalanceBelowMinimum);
            }
            if signal.quote_flow_velocity_per_second
                < policy.min_quote_flow_velocity_per_second
            {
                reasons.push(ImpulseScalpReason::QuoteFlowVelocityBelowMinimum);
            }
            if signal.quote_flow_acceleration_per_second2
                < policy.min_quote_flow_acceleration_per_second2
            {
                reasons.push(ImpulseScalpReason::QuoteFlowAccelerationBelowMinimum);
            }
            if signal.recovery_from_local_low < policy.min_recovery_from_local_low {
                reasons.push(ImpulseScalpReason::RecoveryBelowMinimum);
            }
            if signal.drawdown_from_local_high > policy.max_drawdown_from_local_high {
                reasons.push(ImpulseScalpReason::DrawdownAboveMaximum);
            }
        }
    }

    match context {
        None => reasons.push(ImpulseScalpReason::MissingContextWindow),
        Some(context) => {
            if let Some(signal) = signal {
                let required_signal_velocity = if context.quote_flow_velocity_per_second > 0.0 {
                    context.quote_flow_velocity_per_second
                        * policy.min_velocity_expansion_ratio
                } else {
                    0.0
                };
                if signal.quote_flow_velocity_per_second < required_signal_velocity {
                    // Keep velocity-expansion after all absolute flow checks and before
                    // the path reasons in the externally stable reason order.
                    insert_velocity_expansion_reason(&mut reasons);
                }
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
        None => reasons.push(ImpulseScalpReason::ExecutionEconomicsUnavailable),
        Some(execution) => {
            if execution.market != snapshot.market {
                return Err(ImpulseScalpError::ExecutionMarketMismatch);
            }
            if execution.as_of_unix_ms != snapshot.as_of_unix_ms {
                return Err(ImpulseScalpError::ExecutionTimestampMismatch {
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
                        reasons.push(ImpulseScalpReason::ForecastNetPnlNotPositive);
                    }
                    if execution.trade.executable_entry_price_quote
                        > economics.maximum_acceptable_entry_price_quote
                    {
                        reasons.push(ImpulseScalpReason::EntryPriceAboveMaximum);
                    }
                }
                Err(ExecutionEconomicsError::InsufficientExitCapacity) => {
                    reasons.push(ImpulseScalpReason::InsufficientExitCapacity);
                }
                Err(error) => return Err(ImpulseScalpError::ExecutionEconomics(error)),
            }
        }
    }

    // The signal reasons are appended in stable semantic order except for
    // velocity expansion, which depends on both windows. Reorder only that one
    // dependent reason so callers receive a canonical sequence.
    canonicalize_reason_order(&mut reasons);

    let action = if reasons.is_empty() {
        reasons.push(ImpulseScalpReason::AllConditionsMet);
        FastLaneAction::Buy
    } else {
        FastLaneAction::Skip
    };

    Ok(ImpulseScalpAssessment {
        version: IMPULSE_SCALP_BASELINE_VERSION,
        policy_version: policy.version,
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        action,
        reasons,
        signal_window_ms: policy.signal_window_ms,
        context_window_ms: policy.context_window_ms,
        intended_base_quantity,
        executable_entry_price_quote,
        forecast_exit_price_quote,
        exit_capacity_base,
        forecast_net_pnl_quote,
        break_even_move_bps,
        maximum_acceptable_entry_price_quote,
    })
}

fn validate_policy(policy: &ImpulseScalpPolicy) -> Result<(), ImpulseScalpError> {
    if policy.version != IMPULSE_SCALP_BASELINE_VERSION {
        return Err(ImpulseScalpError::InvalidPolicy(
            "unsupported policy version",
        ));
    }
    if policy.signal_window_ms == 0 {
        return Err(ImpulseScalpError::InvalidPolicy(
            "signal_window_ms must be positive",
        ));
    }
    if policy.context_window_ms == 0 {
        return Err(ImpulseScalpError::InvalidPolicy(
            "context_window_ms must be positive",
        ));
    }
    if policy.signal_window_ms >= policy.context_window_ms {
        return Err(ImpulseScalpError::InvalidPolicy(
            "signal_window_ms must be smaller than context_window_ms",
        ));
    }
    if policy.min_buy_count == 0 {
        return Err(ImpulseScalpError::InvalidPolicy(
            "min_buy_count must be positive",
        ));
    }
    if policy.min_unique_buy_actors == 0 {
        return Err(ImpulseScalpError::InvalidPolicy(
            "min_unique_buy_actors must be positive",
        ));
    }
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
        return Err(ImpulseScalpError::InvalidPolicy(
            "min_velocity_expansion_ratio must be finite and at least 1",
        ));
    }
    if !policy.min_recovery_from_local_low.is_finite()
        || policy.min_recovery_from_local_low < 0.0
    {
        return Err(ImpulseScalpError::InvalidPolicy(
            "min_recovery_from_local_low must be finite and non-negative",
        ));
    }
    validate_unit_interval(
        policy.max_drawdown_from_local_high,
        "max_drawdown_from_local_high must be finite and within [0, 1]",
    )?;
    Ok(())
}

fn validate_positive_finite(value: f64, message: &'static str) -> Result<(), ImpulseScalpError> {
    if !value.is_finite() || value <= 0.0 {
        return Err(ImpulseScalpError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_unit_interval(value: f64, message: &'static str) -> Result<(), ImpulseScalpError> {
    if !value.is_finite() || !(0.0..=1.0).contains(&value) {
        return Err(ImpulseScalpError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_window(
    window: &FastWindowSummary,
    message: &'static str,
) -> Result<(), ImpulseScalpError> {
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
        return Err(ImpulseScalpError::InvalidSnapshot(message));
    }
    if window.drawdown_from_local_high < 0.0 || window.recovery_from_local_low < 0.0 {
        return Err(ImpulseScalpError::InvalidSnapshot(message));
    }
    if let Some(value) = window.local_high_price_quote {
        if !value.is_finite() || value <= 0.0 {
            return Err(ImpulseScalpError::InvalidSnapshot(message));
        }
    }
    if let Some(value) = window.local_low_price_quote {
        if !value.is_finite() || value <= 0.0 {
            return Err(ImpulseScalpError::InvalidSnapshot(message));
        }
    }
    if let Some(value) = window.last_price_quote {
        if !value.is_finite() || value <= 0.0 {
            return Err(ImpulseScalpError::InvalidSnapshot(message));
        }
    }
    Ok(())
}

fn insert_velocity_expansion_reason(reasons: &mut Vec<ImpulseScalpReason>) {
    reasons.push(ImpulseScalpReason::VelocityExpansionBelowMinimum);
}

fn canonicalize_reason_order(reasons: &mut Vec<ImpulseScalpReason>) {
    const ORDER: [ImpulseScalpReason; 15] = [
        ImpulseScalpReason::MissingSignalWindow,
        ImpulseScalpReason::MissingContextWindow,
        ImpulseScalpReason::BuyCountBelowMinimum,
        ImpulseScalpReason::UniqueBuyActorsBelowMinimum,
        ImpulseScalpReason::CountImbalanceBelowMinimum,
        ImpulseScalpReason::QuoteFlowImbalanceBelowMinimum,
        ImpulseScalpReason::QuoteFlowVelocityBelowMinimum,
        ImpulseScalpReason::QuoteFlowAccelerationBelowMinimum,
        ImpulseScalpReason::VelocityExpansionBelowMinimum,
        ImpulseScalpReason::RecoveryBelowMinimum,
        ImpulseScalpReason::DrawdownAboveMaximum,
        ImpulseScalpReason::ExecutionEconomicsUnavailable,
        ImpulseScalpReason::InsufficientExitCapacity,
        ImpulseScalpReason::ForecastNetPnlNotPositive,
        ImpulseScalpReason::EntryPriceAboveMaximum,
    ];
    reasons.sort_by_key(|reason| {
        ORDER
            .iter()
            .position(|candidate| candidate == reason)
            .unwrap_or(ORDER.len())
    });
    reasons.dedup();
}
