use std::{error::Error, fmt};

pub const EXECUTION_ECONOMICS_VERSION: u16 = 1;
const BASIS_POINTS_DENOMINATOR: f64 = 10_000.0;

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionLegCostInput {
    pub effective_fee_bps: u32,
    pub expected_impact_bps: u32,
    pub expected_slippage_bps: u32,
    pub expected_latency_bps: u32,
    pub network_fee_quote: f64,
    pub priority_fee_quote: f64,
    pub expected_failure_cost_quote: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionCostModel {
    pub version: u16,
    pub entry: ExecutionLegCostInput,
    pub exit: ExecutionLegCostInput,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionTradeInput {
    pub base_quantity: f64,
    pub executable_entry_price_quote: f64,
    pub forecast_exit_price_quote: f64,
    pub exit_capacity_base: f64,
    pub required_edge_bps: u32,
    pub risk_margin_bps: u32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionEconomics {
    pub version: u16,
    pub entry_total_quote: f64,
    pub forecast_exit_net_quote: f64,
    pub forecast_net_pnl_quote: f64,
    pub break_even_exit_price_quote: f64,
    pub break_even_move_bps: f64,
    pub maximum_acceptable_entry_price_quote: f64,
    pub exit_capacity_base: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExecutionEconomicsError {
    InvalidModelVersion,
    BasisPointsOutOfRange { field: &'static str, value: u32 },
    BasisPointsOverflow { leg: &'static str },
    InvalidFixedCost { field: &'static str },
    ExitVariableCostTooHigh,
    InvalidTradeValue { field: &'static str },
    InsufficientExitCapacity,
    RequiredReturnOverflow,
    NonFiniteResult { field: &'static str },
    NoPositiveMaximumEntryPrice,
}

impl fmt::Display for ExecutionEconomicsError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidModelVersion => formatter
                .write_str("execution economics cost model version must be greater than zero"),
            Self::BasisPointsOutOfRange { field, value } => write!(
                formatter,
                "execution economics {field} must be <= 10000 basis points; got {value}"
            ),
            Self::BasisPointsOverflow { leg } => write!(
                formatter,
                "execution economics {leg} variable cost basis points overflow"
            ),
            Self::InvalidFixedCost { field } => write!(
                formatter,
                "execution economics {field} must be finite and non-negative"
            ),
            Self::ExitVariableCostTooHigh => formatter.write_str(
                "execution economics exit variable cost must be less than 10000 basis points",
            ),
            Self::InvalidTradeValue { field } => write!(
                formatter,
                "execution economics {field} must be finite and strictly positive"
            ),
            Self::InsufficientExitCapacity => formatter.write_str(
                "execution economics exit capacity is smaller than intended base quantity",
            ),
            Self::RequiredReturnOverflow => formatter.write_str(
                "execution economics required edge plus risk margin overflowed basis points",
            ),
            Self::NonFiniteResult { field } => write!(
                formatter,
                "execution economics calculation produced a non-finite {field}"
            ),
            Self::NoPositiveMaximumEntryPrice => formatter.write_str(
                "execution economics forecast leaves no positive acceptable entry price",
            ),
        }
    }
}

impl Error for ExecutionEconomicsError {}

impl ExecutionEconomics {
    pub fn assess(
        model: &ExecutionCostModel,
        trade: &ExecutionTradeInput,
    ) -> Result<Self, ExecutionEconomicsError> {
        if model.version == 0 {
            return Err(ExecutionEconomicsError::InvalidModelVersion);
        }

        require_positive_finite(trade.base_quantity, "base quantity")?;
        require_positive_finite(
            trade.executable_entry_price_quote,
            "executable entry price quote",
        )?;
        require_positive_finite(trade.forecast_exit_price_quote, "forecast exit price quote")?;
        require_positive_finite(trade.exit_capacity_base, "exit capacity base")?;
        if trade.exit_capacity_base < trade.base_quantity {
            return Err(ExecutionEconomicsError::InsufficientExitCapacity);
        }

        let entry = validate_leg(&model.entry, "entry")?;
        let exit = validate_leg(&model.exit, "exit")?;
        if exit.variable_bps >= 10_000 {
            return Err(ExecutionEconomicsError::ExitVariableCostTooHigh);
        }

        let entry_rate = f64::from(entry.variable_bps) / BASIS_POINTS_DENOMINATOR;
        let exit_rate = f64::from(exit.variable_bps) / BASIS_POINTS_DENOMINATOR;
        let exit_multiplier = 1.0 - exit_rate;

        let gross_entry_quote = finite_result(
            trade.base_quantity * trade.executable_entry_price_quote,
            "gross entry quote",
        )?;
        let entry_total_quote = finite_result(
            gross_entry_quote * (1.0 + entry_rate) + entry.fixed_quote,
            "entry total quote",
        )?;

        let gross_forecast_exit_quote = finite_result(
            trade.base_quantity * trade.forecast_exit_price_quote,
            "gross forecast exit quote",
        )?;
        let forecast_exit_net_quote = finite_result(
            gross_forecast_exit_quote * exit_multiplier - exit.fixed_quote,
            "forecast exit net quote",
        )?;
        let forecast_net_pnl_quote = finite_result(
            forecast_exit_net_quote - entry_total_quote,
            "forecast net pnl quote",
        )?;

        let break_even_denominator = finite_result(
            trade.base_quantity * exit_multiplier,
            "break-even denominator",
        )?;
        if break_even_denominator <= 0.0 {
            return Err(ExecutionEconomicsError::ExitVariableCostTooHigh);
        }
        let break_even_exit_price_quote = finite_result(
            (entry_total_quote + exit.fixed_quote) / break_even_denominator,
            "break-even exit price quote",
        )?;
        let break_even_move_bps = finite_result(
            (break_even_exit_price_quote / trade.executable_entry_price_quote - 1.0)
                * BASIS_POINTS_DENOMINATOR,
            "break-even move basis points",
        )?;

        let required_return_bps = trade
            .required_edge_bps
            .checked_add(trade.risk_margin_bps)
            .ok_or(ExecutionEconomicsError::RequiredReturnOverflow)?;
        let required_return_rate = f64::from(required_return_bps) / BASIS_POINTS_DENOMINATOR;
        let max_entry_total_quote = finite_result(
            forecast_exit_net_quote / (1.0 + required_return_rate),
            "maximum entry total quote",
        )?;
        let max_entry_numerator = finite_result(
            max_entry_total_quote - entry.fixed_quote,
            "maximum entry numerator",
        )?;
        let max_entry_denominator = finite_result(
            trade.base_quantity * (1.0 + entry_rate),
            "maximum entry denominator",
        )?;
        let maximum_acceptable_entry_price_quote = finite_result(
            max_entry_numerator / max_entry_denominator,
            "maximum acceptable entry price quote",
        )?;
        if maximum_acceptable_entry_price_quote <= 0.0 {
            return Err(ExecutionEconomicsError::NoPositiveMaximumEntryPrice);
        }

        Ok(Self {
            version: model.version,
            entry_total_quote,
            forecast_exit_net_quote,
            forecast_net_pnl_quote,
            break_even_exit_price_quote,
            break_even_move_bps,
            maximum_acceptable_entry_price_quote,
            exit_capacity_base: trade.exit_capacity_base,
        })
    }

    pub fn entry_price_is_acceptable(
        &self,
        current_executable_entry_price_quote: f64,
        current_exit_capacity_base: f64,
        intended_base_quantity: f64,
    ) -> Result<bool, ExecutionEconomicsError> {
        require_positive_finite(
            current_executable_entry_price_quote,
            "current executable entry price quote",
        )?;
        require_positive_finite(current_exit_capacity_base, "current exit capacity base")?;
        require_positive_finite(intended_base_quantity, "intended base quantity")?;

        if current_exit_capacity_base < intended_base_quantity {
            return Ok(false);
        }
        Ok(current_executable_entry_price_quote <= self.maximum_acceptable_entry_price_quote)
    }
}

#[derive(Debug, Clone, Copy)]
struct ValidatedLeg {
    variable_bps: u32,
    fixed_quote: f64,
}

fn validate_leg(
    leg: &ExecutionLegCostInput,
    leg_name: &'static str,
) -> Result<ValidatedLeg, ExecutionEconomicsError> {
    validate_bps("effective fee", leg.effective_fee_bps)?;
    validate_bps("expected impact", leg.expected_impact_bps)?;
    validate_bps("expected slippage", leg.expected_slippage_bps)?;
    validate_bps("expected latency", leg.expected_latency_bps)?;

    validate_fixed("network fee quote", leg.network_fee_quote)?;
    validate_fixed("priority fee quote", leg.priority_fee_quote)?;
    validate_fixed(
        "expected failure cost quote",
        leg.expected_failure_cost_quote,
    )?;

    let variable_bps = leg
        .effective_fee_bps
        .checked_add(leg.expected_impact_bps)
        .and_then(|value| value.checked_add(leg.expected_slippage_bps))
        .and_then(|value| value.checked_add(leg.expected_latency_bps))
        .ok_or(ExecutionEconomicsError::BasisPointsOverflow { leg: leg_name })?;

    let fixed_quote = finite_result(
        leg.network_fee_quote + leg.priority_fee_quote + leg.expected_failure_cost_quote,
        "fixed quote cost",
    )?;

    Ok(ValidatedLeg {
        variable_bps,
        fixed_quote,
    })
}

fn validate_bps(field: &'static str, value: u32) -> Result<(), ExecutionEconomicsError> {
    if value > 10_000 {
        return Err(ExecutionEconomicsError::BasisPointsOutOfRange { field, value });
    }
    Ok(())
}

fn validate_fixed(field: &'static str, value: f64) -> Result<(), ExecutionEconomicsError> {
    if !value.is_finite() || value < 0.0 {
        return Err(ExecutionEconomicsError::InvalidFixedCost { field });
    }
    Ok(())
}

fn require_positive_finite(value: f64, field: &'static str) -> Result<(), ExecutionEconomicsError> {
    if !value.is_finite() || value <= 0.0 {
        return Err(ExecutionEconomicsError::InvalidTradeValue { field });
    }
    Ok(())
}

fn finite_result(value: f64, field: &'static str) -> Result<f64, ExecutionEconomicsError> {
    if !value.is_finite() {
        return Err(ExecutionEconomicsError::NonFiniteResult { field });
    }
    Ok(value)
}
