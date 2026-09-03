use std::{error::Error, fmt};

use crate::{LifecycleEventKind, TokenLifecycleEvent, VenueId};

use super::{
    ExecutionCostModel, ExecutionEconomics, ExecutionEconomicsError, ExecutionTradeInput,
    FastLaneAction, FastMarketKey, FastMarketSnapshot, FastWindowSummary,
};

pub const GRADUATION_FLOW_BASELINE_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq)]
pub struct GraduationFlowPolicy {
    pub version: u16,
    pub flow_window_ms: u64,
    pub max_graduation_age_ms: u64,
    pub min_pre_buy_count: u64,
    pub min_pre_quote_flow_velocity_per_second: f64,
    pub min_post_buy_count: u64,
    pub min_post_unique_buy_actors: u64,
    pub min_post_buy_arrival_rate_per_second: f64,
    pub max_post_sell_arrival_rate_per_second: f64,
    pub min_post_count_imbalance: f64,
    pub min_post_quote_flow_imbalance: f64,
    pub min_post_quote_flow_velocity_per_second: f64,
    pub min_post_quote_flow_acceleration_per_second2: f64,
    pub min_post_to_pre_velocity_ratio: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GraduationBoostContext {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub can_boost: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct GraduationFlowExecutionInput {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub cost_model: ExecutionCostModel,
    pub trade: ExecutionTradeInput,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum GraduationFlowReason {
    GraduationLifecycleUnavailable,
    GraduationTooOld,
    MissingPreWindow,
    MissingPostWindow,
    PreBuyCountBelowMinimum,
    PreVelocityBelowMinimum,
    PostBuyCountBelowMinimum,
    PostUniqueBuyActorsBelowMinimum,
    PostBuyArrivalBelowMinimum,
    PostSellArrivalAboveMaximum,
    PostCountImbalanceBelowMinimum,
    PostQuoteFlowImbalanceBelowMinimum,
    PostVelocityBelowMinimum,
    PostAccelerationBelowMinimum,
    PostVelocityRetentionBelowMinimum,
    ExecutionEconomicsUnavailable,
    InsufficientExitCapacity,
    ForecastNetPnlNotPositive,
    EntryPriceAboveMaximum,
    AllConditionsMet,
}

impl GraduationFlowReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::GraduationLifecycleUnavailable => "graduation_lifecycle_unavailable",
            Self::GraduationTooOld => "graduation_too_old",
            Self::MissingPreWindow => "missing_pre_window",
            Self::MissingPostWindow => "missing_post_window",
            Self::PreBuyCountBelowMinimum => "pre_buy_count_below_minimum",
            Self::PreVelocityBelowMinimum => "pre_velocity_below_minimum",
            Self::PostBuyCountBelowMinimum => "post_buy_count_below_minimum",
            Self::PostUniqueBuyActorsBelowMinimum => "post_unique_buy_actors_below_minimum",
            Self::PostBuyArrivalBelowMinimum => "post_buy_arrival_below_minimum",
            Self::PostSellArrivalAboveMaximum => "post_sell_arrival_above_maximum",
            Self::PostCountImbalanceBelowMinimum => "post_count_imbalance_below_minimum",
            Self::PostQuoteFlowImbalanceBelowMinimum => {
                "post_quote_flow_imbalance_below_minimum"
            }
            Self::PostVelocityBelowMinimum => "post_velocity_below_minimum",
            Self::PostAccelerationBelowMinimum => "post_acceleration_below_minimum",
            Self::PostVelocityRetentionBelowMinimum => {
                "post_velocity_retention_below_minimum"
            }
            Self::ExecutionEconomicsUnavailable => "execution_economics_unavailable",
            Self::InsufficientExitCapacity => "insufficient_exit_capacity",
            Self::ForecastNetPnlNotPositive => "forecast_net_pnl_not_positive",
            Self::EntryPriceAboveMaximum => "entry_price_above_maximum",
            Self::AllConditionsMet => "all_conditions_met",
        }
    }
}

impl fmt::Display for GraduationFlowReason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct GraduationFlowAssessment {
    pub version: u16,
    pub policy_version: u16,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub action: FastLaneAction,
    pub reasons: Vec<GraduationFlowReason>,
    pub flow_window_ms: u64,
    pub graduation_detected_at_unix_ms: Option<i64>,
    pub graduation_age_ms: Option<u64>,
    pub pre_buy_count: Option<u64>,
    pub pre_quote_flow_velocity_per_second: Option<f64>,
    pub post_buy_count: Option<u64>,
    pub post_unique_buy_actors: Option<u64>,
    pub post_buy_arrival_rate_per_second: Option<f64>,
    pub post_sell_arrival_rate_per_second: Option<f64>,
    pub post_count_imbalance: Option<f64>,
    pub post_quote_flow_imbalance: Option<f64>,
    pub post_quote_flow_velocity_per_second: Option<f64>,
    pub post_quote_flow_acceleration_per_second2: Option<f64>,
    pub post_to_pre_velocity_ratio: Option<f64>,
    pub can_boost: Option<bool>,
    pub intended_base_quantity: Option<f64>,
    pub executable_entry_price_quote: Option<f64>,
    pub forecast_exit_price_quote: Option<f64>,
    pub exit_capacity_base: Option<f64>,
    pub forecast_net_pnl_quote: Option<f64>,
    pub break_even_move_bps: Option<f64>,
    pub maximum_acceptable_entry_price_quote: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GraduationFlowError {
    InvalidPolicy(&'static str),
    InvalidSnapshot(&'static str),
    InvalidVenueTransition,
    MarketIdentityMismatch,
    SnapshotTimestampMismatch { pre: i64, post: i64 },
    LifecycleMismatch,
    BoostMarketMismatch,
    BoostTimestampMismatch { snapshot: i64, boost: i64 },
    ExecutionMarketMismatch,
    ExecutionTimestampMismatch { snapshot: i64, execution: i64 },
    ExecutionEconomics(ExecutionEconomicsError),
}

impl fmt::Display for GraduationFlowError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPolicy(field) => {
                write!(formatter, "FL6.4 graduation flow policy is invalid: {field}")
            }
            Self::InvalidSnapshot(field) => {
                write!(formatter, "FL6.4 graduation flow snapshot is invalid: {field}")
            }
            Self::InvalidVenueTransition => formatter.write_str(
                "FL6.4 requires Pump bonding-curve pre-state and PumpSwap post-state",
            ),
            Self::MarketIdentityMismatch => formatter.write_str(
                "FL6.4 pre/post snapshots do not describe the same mint and quote mint",
            ),
            Self::SnapshotTimestampMismatch { pre, post } => write!(
                formatter,
                "FL6.4 pre/post decision timestamps differ: pre {pre}, post {post}"
            ),
            Self::LifecycleMismatch => formatter.write_str(
                "FL6.4 pre/post snapshots carry conflicting graduation lifecycle truth",
            ),
            Self::BoostMarketMismatch => formatter.write_str(
                "FL6.4 boost context market does not match the post-migration market",
            ),
            Self::BoostTimestampMismatch { snapshot, boost } => write!(
                formatter,
                "FL6.4 boost context timestamp {boost} does not match snapshot timestamp {snapshot}"
            ),
            Self::ExecutionMarketMismatch => formatter.write_str(
                "FL6.4 execution evidence market does not match the post-migration market",
            ),
            Self::ExecutionTimestampMismatch { snapshot, execution } => write!(
                formatter,
                "FL6.4 execution evidence timestamp {execution} does not match snapshot timestamp {snapshot}"
            ),
            Self::ExecutionEconomics(error) => {
                write!(formatter, "FL6.4 execution economics failed closed: {error}")
            }
        }
    }
}

impl Error for GraduationFlowError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::ExecutionEconomics(error) => Some(error),
            _ => None,
        }
    }
}

pub fn assess_graduation_flow(
    pre_snapshot: &FastMarketSnapshot,
    post_snapshot: &FastMarketSnapshot,
    boost_context: Option<&GraduationBoostContext>,
    execution: Option<&GraduationFlowExecutionInput>,
    policy: &GraduationFlowPolicy,
) -> Result<GraduationFlowAssessment, GraduationFlowError> {
    validate_policy(policy)?;
    validate_snapshot_pair(pre_snapshot, post_snapshot)?;

    let as_of_unix_ms = post_snapshot.as_of_unix_ms;
    let mut reasons = Vec::new();

    let lifecycle = resolve_lifecycle(pre_snapshot, post_snapshot)?;
    let mut graduation_detected_at_unix_ms = None;
    let mut graduation_age_ms = None;
    if let Some(lifecycle) = lifecycle {
        validate_lifecycle(lifecycle, pre_snapshot, post_snapshot)?;
        graduation_detected_at_unix_ms = Some(lifecycle.detected_at_unix_ms);
        let age_i64 = as_of_unix_ms
            .checked_sub(lifecycle.detected_at_unix_ms)
            .ok_or(GraduationFlowError::InvalidSnapshot(
                "graduation age underflowed decision timestamp",
            ))?;
        let age = u64::try_from(age_i64).map_err(|_| {
            GraduationFlowError::InvalidSnapshot(
                "graduation detection is after the decision timestamp",
            )
        })?;
        graduation_age_ms = Some(age);
        if age > policy.max_graduation_age_ms {
            reasons.push(GraduationFlowReason::GraduationTooOld);
        }
    } else {
        reasons.push(GraduationFlowReason::GraduationLifecycleUnavailable);
    }

    let pre_window = pre_snapshot.window(policy.flow_window_ms);
    let post_window = post_snapshot.window(policy.flow_window_ms);
    if let Some(window) = pre_window {
        validate_window(window, "pre-graduation flow window contains invalid numeric state")?;
    }
    if let Some(window) = post_window {
        validate_window(window, "post-graduation flow window contains invalid numeric state")?;
    }

    let mut pre_buy_count = None;
    let mut pre_quote_flow_velocity_per_second = None;
    match pre_window {
        None => reasons.push(GraduationFlowReason::MissingPreWindow),
        Some(window) => {
            pre_buy_count = Some(window.buy_count);
            pre_quote_flow_velocity_per_second = Some(window.quote_flow_velocity_per_second);
            if window.buy_count < policy.min_pre_buy_count {
                reasons.push(GraduationFlowReason::PreBuyCountBelowMinimum);
            }
            if window.quote_flow_velocity_per_second
                < policy.min_pre_quote_flow_velocity_per_second
            {
                reasons.push(GraduationFlowReason::PreVelocityBelowMinimum);
            }
        }
    }

    let mut post_buy_count = None;
    let mut post_unique_buy_actors = None;
    let mut post_buy_arrival_rate_per_second = None;
    let mut post_sell_arrival_rate_per_second = None;
    let mut post_count_imbalance = None;
    let mut post_quote_flow_imbalance = None;
    let mut post_quote_flow_velocity_per_second = None;
    let mut post_quote_flow_acceleration_per_second2 = None;
    match post_window {
        None => reasons.push(GraduationFlowReason::MissingPostWindow),
        Some(window) => {
            post_buy_count = Some(window.buy_count);
            post_unique_buy_actors = Some(window.unique_buy_actors);
            post_buy_arrival_rate_per_second = Some(window.buy_arrival_rate_per_second);
            post_sell_arrival_rate_per_second = Some(window.sell_arrival_rate_per_second);
            post_count_imbalance = Some(window.count_imbalance);
            post_quote_flow_imbalance = Some(window.quote_flow_imbalance);
            post_quote_flow_velocity_per_second = Some(window.quote_flow_velocity_per_second);
            post_quote_flow_acceleration_per_second2 =
                Some(window.quote_flow_acceleration_per_second2);

            if window.buy_count < policy.min_post_buy_count {
                reasons.push(GraduationFlowReason::PostBuyCountBelowMinimum);
            }
            if window.unique_buy_actors < policy.min_post_unique_buy_actors {
                reasons.push(GraduationFlowReason::PostUniqueBuyActorsBelowMinimum);
            }
            if window.buy_arrival_rate_per_second < policy.min_post_buy_arrival_rate_per_second {
                reasons.push(GraduationFlowReason::PostBuyArrivalBelowMinimum);
            }
            if window.sell_arrival_rate_per_second > policy.max_post_sell_arrival_rate_per_second {
                reasons.push(GraduationFlowReason::PostSellArrivalAboveMaximum);
            }
            if window.count_imbalance < policy.min_post_count_imbalance {
                reasons.push(GraduationFlowReason::PostCountImbalanceBelowMinimum);
            }
            if window.quote_flow_imbalance < policy.min_post_quote_flow_imbalance {
                reasons.push(GraduationFlowReason::PostQuoteFlowImbalanceBelowMinimum);
            }
            if window.quote_flow_velocity_per_second
                < policy.min_post_quote_flow_velocity_per_second
            {
                reasons.push(GraduationFlowReason::PostVelocityBelowMinimum);
            }
            if window.quote_flow_acceleration_per_second2
                < policy.min_post_quote_flow_acceleration_per_second2
            {
                reasons.push(GraduationFlowReason::PostAccelerationBelowMinimum);
            }
        }
    }

    let mut post_to_pre_velocity_ratio = None;
    if let (Some(pre_window), Some(post_window)) = (pre_window, post_window) {
        if pre_window.quote_flow_velocity_per_second > 0.0 {
            let ratio = post_window.quote_flow_velocity_per_second
                / pre_window.quote_flow_velocity_per_second;
            if !ratio.is_finite() {
                return Err(GraduationFlowError::InvalidSnapshot(
                    "post/pre flow velocity ratio is not finite",
                ));
            }
            post_to_pre_velocity_ratio = Some(ratio);
            if ratio < policy.min_post_to_pre_velocity_ratio {
                reasons.push(GraduationFlowReason::PostVelocityRetentionBelowMinimum);
            }
        }
    }

    let can_boost = match boost_context {
        None => None,
        Some(boost) => {
            if boost.market != post_snapshot.market {
                return Err(GraduationFlowError::BoostMarketMismatch);
            }
            if boost.as_of_unix_ms != as_of_unix_ms {
                return Err(GraduationFlowError::BoostTimestampMismatch {
                    snapshot: as_of_unix_ms,
                    boost: boost.as_of_unix_ms,
                });
            }
            Some(boost.can_boost)
        }
    };

    let mut intended_base_quantity = None;
    let mut executable_entry_price_quote = None;
    let mut forecast_exit_price_quote = None;
    let mut exit_capacity_base = None;
    let mut forecast_net_pnl_quote = None;
    let mut break_even_move_bps = None;
    let mut maximum_acceptable_entry_price_quote = None;

    match execution {
        None => reasons.push(GraduationFlowReason::ExecutionEconomicsUnavailable),
        Some(execution) => {
            if execution.market != post_snapshot.market {
                return Err(GraduationFlowError::ExecutionMarketMismatch);
            }
            if execution.as_of_unix_ms != as_of_unix_ms {
                return Err(GraduationFlowError::ExecutionTimestampMismatch {
                    snapshot: as_of_unix_ms,
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
                        reasons.push(GraduationFlowReason::ForecastNetPnlNotPositive);
                    }
                    if execution.trade.executable_entry_price_quote
                        > economics.maximum_acceptable_entry_price_quote
                    {
                        reasons.push(GraduationFlowReason::EntryPriceAboveMaximum);
                    }
                }
                Err(ExecutionEconomicsError::InsufficientExitCapacity) => {
                    reasons.push(GraduationFlowReason::InsufficientExitCapacity);
                }
                Err(error) => return Err(GraduationFlowError::ExecutionEconomics(error)),
            }
        }
    }

    canonicalize_reason_order(&mut reasons);
    let action = if reasons.is_empty() {
        reasons.push(GraduationFlowReason::AllConditionsMet);
        FastLaneAction::Buy
    } else {
        FastLaneAction::Skip
    };

    Ok(GraduationFlowAssessment {
        version: GRADUATION_FLOW_BASELINE_VERSION,
        policy_version: policy.version,
        market: post_snapshot.market.clone(),
        as_of_unix_ms,
        action,
        reasons,
        flow_window_ms: policy.flow_window_ms,
        graduation_detected_at_unix_ms,
        graduation_age_ms,
        pre_buy_count,
        pre_quote_flow_velocity_per_second,
        post_buy_count,
        post_unique_buy_actors,
        post_buy_arrival_rate_per_second,
        post_sell_arrival_rate_per_second,
        post_count_imbalance,
        post_quote_flow_imbalance,
        post_quote_flow_velocity_per_second,
        post_quote_flow_acceleration_per_second2,
        post_to_pre_velocity_ratio,
        can_boost,
        intended_base_quantity,
        executable_entry_price_quote,
        forecast_exit_price_quote,
        exit_capacity_base,
        forecast_net_pnl_quote,
        break_even_move_bps,
        maximum_acceptable_entry_price_quote,
    })
}

fn validate_policy(policy: &GraduationFlowPolicy) -> Result<(), GraduationFlowError> {
    if policy.version != GRADUATION_FLOW_BASELINE_VERSION {
        return Err(GraduationFlowError::InvalidPolicy(
            "unsupported policy version",
        ));
    }
    if policy.flow_window_ms == 0 {
        return Err(GraduationFlowError::InvalidPolicy(
            "flow_window_ms must be positive",
        ));
    }
    if policy.max_graduation_age_ms == 0 {
        return Err(GraduationFlowError::InvalidPolicy(
            "max_graduation_age_ms must be positive",
        ));
    }
    if policy.min_pre_buy_count == 0
        || policy.min_post_buy_count == 0
        || policy.min_post_unique_buy_actors == 0
    {
        return Err(GraduationFlowError::InvalidPolicy(
            "participation counts must be positive",
        ));
    }
    validate_positive_finite(
        policy.min_pre_quote_flow_velocity_per_second,
        "min_pre_quote_flow_velocity_per_second must be positive and finite",
    )?;
    validate_positive_finite(
        policy.min_post_buy_arrival_rate_per_second,
        "min_post_buy_arrival_rate_per_second must be positive and finite",
    )?;
    validate_non_negative_finite(
        policy.max_post_sell_arrival_rate_per_second,
        "max_post_sell_arrival_rate_per_second must be non-negative and finite",
    )?;
    validate_unit_interval(
        policy.min_post_count_imbalance,
        "min_post_count_imbalance must be finite and within [0, 1]",
    )?;
    validate_unit_interval(
        policy.min_post_quote_flow_imbalance,
        "min_post_quote_flow_imbalance must be finite and within [0, 1]",
    )?;
    validate_positive_finite(
        policy.min_post_quote_flow_velocity_per_second,
        "min_post_quote_flow_velocity_per_second must be positive and finite",
    )?;
    validate_positive_finite(
        policy.min_post_quote_flow_acceleration_per_second2,
        "min_post_quote_flow_acceleration_per_second2 must be positive and finite",
    )?;
    validate_positive_finite(
        policy.min_post_to_pre_velocity_ratio,
        "min_post_to_pre_velocity_ratio must be positive and finite",
    )?;
    Ok(())
}

fn validate_snapshot_pair(
    pre_snapshot: &FastMarketSnapshot,
    post_snapshot: &FastMarketSnapshot,
) -> Result<(), GraduationFlowError> {
    if pre_snapshot.as_of_unix_ms < 0 || post_snapshot.as_of_unix_ms < 0 {
        return Err(GraduationFlowError::InvalidSnapshot(
            "snapshot timestamps must be non-negative",
        ));
    }
    if pre_snapshot.market.venue != VenueId::PumpFunBondingCurve
        || post_snapshot.market.venue != VenueId::PumpSwap
    {
        return Err(GraduationFlowError::InvalidVenueTransition);
    }
    if pre_snapshot.market.mint != post_snapshot.market.mint
        || pre_snapshot.market.quote_mint != post_snapshot.market.quote_mint
    {
        return Err(GraduationFlowError::MarketIdentityMismatch);
    }
    if pre_snapshot.as_of_unix_ms != post_snapshot.as_of_unix_ms {
        return Err(GraduationFlowError::SnapshotTimestampMismatch {
            pre: pre_snapshot.as_of_unix_ms,
            post: post_snapshot.as_of_unix_ms,
        });
    }
    Ok(())
}

fn resolve_lifecycle<'a>(
    pre_snapshot: &'a FastMarketSnapshot,
    post_snapshot: &'a FastMarketSnapshot,
) -> Result<Option<&'a TokenLifecycleEvent>, GraduationFlowError> {
    match (
        pre_snapshot.last_lifecycle_event.as_ref(),
        post_snapshot.last_lifecycle_event.as_ref(),
    ) {
        (None, None) | (Some(_), None) | (None, Some(_)) => Ok(None),
        (Some(pre), Some(post)) if pre == post => Ok(Some(pre)),
        (Some(_), Some(_)) => Err(GraduationFlowError::LifecycleMismatch),
    }
}

fn validate_lifecycle(
    lifecycle: &TokenLifecycleEvent,
    pre_snapshot: &FastMarketSnapshot,
    post_snapshot: &FastMarketSnapshot,
) -> Result<(), GraduationFlowError> {
    if lifecycle.kind != LifecycleEventKind::PumpGraduation {
        return Err(GraduationFlowError::InvalidSnapshot(
            "lifecycle event is not Pump graduation",
        ));
    }
    if lifecycle.from_venue != VenueId::PumpFunBondingCurve
        || lifecycle.to_venue != VenueId::PumpSwap
    {
        return Err(GraduationFlowError::InvalidVenueTransition);
    }
    if lifecycle.mint != pre_snapshot.market.mint
        || lifecycle.quote_mint != pre_snapshot.market.quote_mint
        || lifecycle.mint != post_snapshot.market.mint
        || lifecycle.quote_mint != post_snapshot.market.quote_mint
    {
        return Err(GraduationFlowError::MarketIdentityMismatch);
    }
    if lifecycle.detected_at_unix_ms < 0
        || lifecycle.detected_at_unix_ms > post_snapshot.as_of_unix_ms
    {
        return Err(GraduationFlowError::InvalidSnapshot(
            "graduation detection timestamp is outside the decision clock",
        ));
    }
    if lifecycle
        .occurred_at_unix_ms
        .is_some_and(|occurred| occurred < 0 || occurred > post_snapshot.as_of_unix_ms)
    {
        return Err(GraduationFlowError::InvalidSnapshot(
            "graduation occurrence timestamp is outside the decision clock",
        ));
    }
    Ok(())
}

fn validate_window(
    window: &FastWindowSummary,
    message: &'static str,
) -> Result<(), GraduationFlowError> {
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
        return Err(GraduationFlowError::InvalidSnapshot(message));
    }
    if window.buy_arrival_rate_per_second < 0.0
        || window.sell_arrival_rate_per_second < 0.0
        || window.buy_base_quantity < 0.0
        || window.sell_base_quantity < 0.0
        || window.buy_quote_quantity < 0.0
        || window.sell_quote_quantity < 0.0
    {
        return Err(GraduationFlowError::InvalidSnapshot(message));
    }
    Ok(())
}

fn validate_positive_finite(
    value: f64,
    message: &'static str,
) -> Result<(), GraduationFlowError> {
    if !value.is_finite() || value <= 0.0 {
        return Err(GraduationFlowError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_non_negative_finite(
    value: f64,
    message: &'static str,
) -> Result<(), GraduationFlowError> {
    if !value.is_finite() || value < 0.0 {
        return Err(GraduationFlowError::InvalidPolicy(message));
    }
    Ok(())
}

fn validate_unit_interval(
    value: f64,
    message: &'static str,
) -> Result<(), GraduationFlowError> {
    if !value.is_finite() || !(0.0..=1.0).contains(&value) {
        return Err(GraduationFlowError::InvalidPolicy(message));
    }
    Ok(())
}

fn canonicalize_reason_order(reasons: &mut Vec<GraduationFlowReason>) {
    const ORDER: [GraduationFlowReason; 19] = [
        GraduationFlowReason::GraduationLifecycleUnavailable,
        GraduationFlowReason::GraduationTooOld,
        GraduationFlowReason::MissingPreWindow,
        GraduationFlowReason::MissingPostWindow,
        GraduationFlowReason::PreBuyCountBelowMinimum,
        GraduationFlowReason::PreVelocityBelowMinimum,
        GraduationFlowReason::PostBuyCountBelowMinimum,
        GraduationFlowReason::PostUniqueBuyActorsBelowMinimum,
        GraduationFlowReason::PostBuyArrivalBelowMinimum,
        GraduationFlowReason::PostSellArrivalAboveMaximum,
        GraduationFlowReason::PostCountImbalanceBelowMinimum,
        GraduationFlowReason::PostQuoteFlowImbalanceBelowMinimum,
        GraduationFlowReason::PostVelocityBelowMinimum,
        GraduationFlowReason::PostAccelerationBelowMinimum,
        GraduationFlowReason::PostVelocityRetentionBelowMinimum,
        GraduationFlowReason::ExecutionEconomicsUnavailable,
        GraduationFlowReason::InsufficientExitCapacity,
        GraduationFlowReason::ForecastNetPnlNotPositive,
        GraduationFlowReason::EntryPriceAboveMaximum,
    ];
    reasons.sort_by_key(|reason| {
        ORDER
            .iter()
            .position(|candidate| candidate == reason)
            .unwrap_or(ORDER.len())
    });
    reasons.dedup();
}
