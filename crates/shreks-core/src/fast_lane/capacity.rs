use std::{error::Error, fmt};

use super::FastReserveContext;

#[derive(Debug, Clone, PartialEq)]
pub struct ExitProjection {
    pub base_quantity_raw: u64,
    pub quote_output_raw: u64,
    pub base_quantity: f64,
    pub quote_output: f64,
    pub average_price_quote: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExitCapacity {
    pub maximum_base_quantity_raw: u64,
    pub maximum_base_quantity: f64,
    pub boundary_quote_output_raw: u64,
    pub boundary_quote_output: f64,
    pub boundary_average_price_quote: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExitCapacityError {
    ZeroBaseQuantity,
    InvalidMinimumAverageExitPrice,
    MissingPumpSwapVirtualQuoteReserve,
    NonPositiveBaseReserve,
    NonPositiveEffectiveQuoteReserve,
    PhysicalQuoteReserveExhausted,
    ImpossibleMinimumAveragePrice,
    ArithmeticOverflow,
    InvalidReserveScale,
}

impl fmt::Display for ExitCapacityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ZeroBaseQuantity => formatter.write_str("exit base quantity must be positive"),
            Self::InvalidMinimumAverageExitPrice => formatter.write_str(
                "minimum average exit price must be finite and strictly positive",
            ),
            Self::MissingPumpSwapVirtualQuoteReserve => formatter.write_str(
                "PumpSwap exit capacity requires authoritative virtual quote reserve evidence",
            ),
            Self::NonPositiveBaseReserve => {
                formatter.write_str("exit capacity base reserve must be positive")
            }
            Self::NonPositiveEffectiveQuoteReserve => formatter.write_str(
                "exit capacity effective quote reserve must be positive",
            ),
            Self::PhysicalQuoteReserveExhausted => formatter.write_str(
                "projected exit exceeds the physical quote reserve",
            ),
            Self::ImpossibleMinimumAveragePrice => formatter.write_str(
                "no positive exit quantity satisfies the minimum average exit price",
            ),
            Self::ArithmeticOverflow => {
                formatter.write_str("exit capacity integer arithmetic overflowed")
            }
            Self::InvalidReserveScale => formatter.write_str(
                "exit capacity reserve decimals produced an invalid numeric scale",
            ),
        }
    }
}

impl Error for ExitCapacityError {}

#[derive(Debug, Clone, Copy)]
struct ReserveView {
    base_reserve_raw: u64,
    effective_quote_reserve_raw: u64,
    physical_quote_reserve_raw: u64,
    base_decimals: u8,
    quote_decimals: u8,
}

pub fn project_exit(
    reserves: &FastReserveContext,
    base_quantity_raw: u64,
) -> Result<ExitProjection, ExitCapacityError> {
    if base_quantity_raw == 0 {
        return Err(ExitCapacityError::ZeroBaseQuantity);
    }
    let view = reserve_view(reserves)?;
    project_view(view, base_quantity_raw)
}

pub fn maximum_exit_capacity(
    reserves: &FastReserveContext,
    minimum_average_exit_price_quote: f64,
) -> Result<ExitCapacity, ExitCapacityError> {
    if !minimum_average_exit_price_quote.is_finite()
        || minimum_average_exit_price_quote <= 0.0
    {
        return Err(ExitCapacityError::InvalidMinimumAverageExitPrice);
    }

    let view = reserve_view(reserves)?;
    let (base_scale, quote_scale) = decimal_scales(view.base_decimals, view.quote_decimals)?;
    let minimum_raw_price = minimum_average_exit_price_quote * quote_scale / base_scale;
    if !minimum_raw_price.is_finite() || minimum_raw_price <= 0.0 {
        return Err(ExitCapacityError::InvalidReserveScale);
    }

    let spot_raw = view.effective_quote_reserve_raw as f64 / view.base_reserve_raw as f64;
    if !spot_raw.is_finite() || minimum_raw_price >= spot_raw {
        return Err(ExitCapacityError::ImpossibleMinimumAveragePrice);
    }

    let maximum_quote_output_raw = view
        .effective_quote_reserve_raw
        .saturating_sub(1)
        .min(view.physical_quote_reserve_raw);
    if maximum_quote_output_raw == 0 {
        return Err(ExitCapacityError::PhysicalQuoteReserveExhausted);
    }

    // Under x*y=k with a base-token sell x, the continuous average raw price is
    // q/(b+x). Therefore the boundary quote output is q - b*r. Integer AMM
    // output is floor(q*x/(b+x)); start at the continuous boundary and walk
    // downward only to reconcile integer granularity. Every returned candidate
    // is re-projected through the exact integer formula before acceptance.
    let continuous_boundary_quote = view.effective_quote_reserve_raw as f64
        - view.base_reserve_raw as f64 * minimum_raw_price;
    if !continuous_boundary_quote.is_finite() || continuous_boundary_quote <= 0.0 {
        return Err(ExitCapacityError::ImpossibleMinimumAveragePrice);
    }

    let candidate_quote = continuous_boundary_quote
        .ceil()
        .min(maximum_quote_output_raw as f64);
    if !candidate_quote.is_finite() || candidate_quote < 1.0 {
        return Err(ExitCapacityError::ImpossibleMinimumAveragePrice);
    }
    let mut quote_output_raw = if candidate_quote >= u64::MAX as f64 {
        maximum_quote_output_raw
    } else {
        candidate_quote as u64
    };

    const MAX_GRANULARITY_RECONCILIATION_STEPS: usize = 4_096;
    for _ in 0..MAX_GRANULARITY_RECONCILIATION_STEPS {
        if quote_output_raw == 0 {
            break;
        }
        if let Some(base_quantity_raw) = maximum_quantity_for_quote_bucket(
            view,
            quote_output_raw,
            minimum_raw_price,
        )? {
            let projection = project_view(view, base_quantity_raw)?;
            if projection.average_price_quote >= minimum_average_exit_price_quote {
                return Ok(ExitCapacity {
                    maximum_base_quantity_raw: projection.base_quantity_raw,
                    maximum_base_quantity: projection.base_quantity,
                    boundary_quote_output_raw: projection.quote_output_raw,
                    boundary_quote_output: projection.quote_output,
                    boundary_average_price_quote: projection.average_price_quote,
                });
            }
        }
        quote_output_raw -= 1;
    }

    Err(ExitCapacityError::ImpossibleMinimumAveragePrice)
}

fn reserve_view(reserves: &FastReserveContext) -> Result<ReserveView, ExitCapacityError> {
    let view = match reserves {
        FastReserveContext::PumpCurve {
            virtual_base_reserve_raw,
            virtual_quote_reserve_raw,
            real_quote_reserve_raw,
            base_decimals,
            quote_decimals,
            ..
        } => ReserveView {
            base_reserve_raw: *virtual_base_reserve_raw,
            effective_quote_reserve_raw: *virtual_quote_reserve_raw,
            physical_quote_reserve_raw: *real_quote_reserve_raw,
            base_decimals: *base_decimals,
            quote_decimals: *quote_decimals,
        },
        FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw,
            pool_quote_reserve_raw,
            virtual_quote_reserve_raw,
            base_decimals,
            quote_decimals,
        } => {
            let virtual_quote_reserve_raw = virtual_quote_reserve_raw
                .ok_or(ExitCapacityError::MissingPumpSwapVirtualQuoteReserve)?;
            let effective_quote_reserve_raw = i128::from(*pool_quote_reserve_raw)
                .checked_add(virtual_quote_reserve_raw)
                .ok_or(ExitCapacityError::ArithmeticOverflow)?;
            if effective_quote_reserve_raw <= 0 {
                return Err(ExitCapacityError::NonPositiveEffectiveQuoteReserve);
            }
            let effective_quote_reserve_raw = u64::try_from(effective_quote_reserve_raw)
                .map_err(|_| ExitCapacityError::ArithmeticOverflow)?;
            ReserveView {
                base_reserve_raw: *pool_base_reserve_raw,
                effective_quote_reserve_raw,
                physical_quote_reserve_raw: *pool_quote_reserve_raw,
                base_decimals: *base_decimals,
                quote_decimals: *quote_decimals,
            }
        }
    };

    if view.base_reserve_raw == 0 {
        return Err(ExitCapacityError::NonPositiveBaseReserve);
    }
    if view.effective_quote_reserve_raw == 0 {
        return Err(ExitCapacityError::NonPositiveEffectiveQuoteReserve);
    }
    Ok(view)
}

fn project_view(
    view: ReserveView,
    base_quantity_raw: u64,
) -> Result<ExitProjection, ExitCapacityError> {
    let numerator = u128::from(view.effective_quote_reserve_raw)
        .checked_mul(u128::from(base_quantity_raw))
        .ok_or(ExitCapacityError::ArithmeticOverflow)?;
    let denominator = u128::from(view.base_reserve_raw)
        .checked_add(u128::from(base_quantity_raw))
        .ok_or(ExitCapacityError::ArithmeticOverflow)?;
    let quote_output_raw = numerator / denominator;
    let quote_output_raw = u64::try_from(quote_output_raw)
        .map_err(|_| ExitCapacityError::ArithmeticOverflow)?;

    if quote_output_raw > view.physical_quote_reserve_raw {
        return Err(ExitCapacityError::PhysicalQuoteReserveExhausted);
    }

    let (base_scale, quote_scale) = decimal_scales(view.base_decimals, view.quote_decimals)?;
    let base_quantity = base_quantity_raw as f64 / base_scale;
    let quote_output = quote_output_raw as f64 / quote_scale;
    let average_price_quote = quote_output / base_quantity;
    if !base_quantity.is_finite()
        || base_quantity <= 0.0
        || !quote_output.is_finite()
        || !average_price_quote.is_finite()
    {
        return Err(ExitCapacityError::InvalidReserveScale);
    }

    Ok(ExitProjection {
        base_quantity_raw,
        quote_output_raw,
        base_quantity,
        quote_output,
        average_price_quote,
    })
}

fn maximum_quantity_for_quote_bucket(
    view: ReserveView,
    quote_output_raw: u64,
    minimum_raw_price: f64,
) -> Result<Option<u64>, ExitCapacityError> {
    if quote_output_raw == 0
        || quote_output_raw >= view.effective_quote_reserve_raw
        || quote_output_raw > view.physical_quote_reserve_raw
    {
        return Ok(None);
    }

    let q = u128::from(view.effective_quote_reserve_raw);
    let b = u128::from(view.base_reserve_raw);
    let y = u128::from(quote_output_raw);

    let lower_numerator = y
        .checked_mul(b)
        .ok_or(ExitCapacityError::ArithmeticOverflow)?;
    let lower_denominator = q
        .checked_sub(y)
        .ok_or(ExitCapacityError::ArithmeticOverflow)?;
    let lower = ceil_div(lower_numerator, lower_denominator)?;

    let upper_bucket = if quote_output_raw + 1 >= view.effective_quote_reserve_raw {
        u128::from(u64::MAX)
    } else {
        let next_y = y
            .checked_add(1)
            .ok_or(ExitCapacityError::ArithmeticOverflow)?;
        let numerator = next_y
            .checked_mul(b)
            .ok_or(ExitCapacityError::ArithmeticOverflow)?;
        let denominator = q
            .checked_sub(next_y)
            .ok_or(ExitCapacityError::ArithmeticOverflow)?;
        ceil_div(numerator, denominator)?
            .checked_sub(1)
            .ok_or(ExitCapacityError::ArithmeticOverflow)?
    };

    let upper_average_f64 = (quote_output_raw as f64 / minimum_raw_price).floor();
    if !upper_average_f64.is_finite() || upper_average_f64 < 1.0 {
        return Ok(None);
    }
    let upper_average = if upper_average_f64 >= u64::MAX as f64 {
        u128::from(u64::MAX)
    } else {
        upper_average_f64 as u128
    };

    let upper = upper_bucket.min(upper_average).min(u128::from(u64::MAX));
    if upper < lower || lower == 0 {
        return Ok(None);
    }

    Ok(Some(
        u64::try_from(upper).map_err(|_| ExitCapacityError::ArithmeticOverflow)?,
    ))
}

fn ceil_div(numerator: u128, denominator: u128) -> Result<u128, ExitCapacityError> {
    if denominator == 0 {
        return Err(ExitCapacityError::ArithmeticOverflow);
    }
    let quotient = numerator / denominator;
    let remainder = numerator % denominator;
    quotient
        .checked_add(u128::from(remainder != 0))
        .ok_or(ExitCapacityError::ArithmeticOverflow)
}

fn decimal_scales(
    base_decimals: u8,
    quote_decimals: u8,
) -> Result<(f64, f64), ExitCapacityError> {
    let base_scale = 10_f64.powi(i32::from(base_decimals));
    let quote_scale = 10_f64.powi(i32::from(quote_decimals));
    if !base_scale.is_finite()
        || base_scale <= 0.0
        || !quote_scale.is_finite()
        || quote_scale <= 0.0
    {
        return Err(ExitCapacityError::InvalidReserveScale);
    }
    Ok((base_scale, quote_scale))
}
