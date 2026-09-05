use rusqlite::{params, OptionalExtension};

use crate::{ShreksDb, StorageError};

const BASIS_POINTS_DENOMINATOR: u128 = 10_000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpSwapEffectiveFeeEvidence {
    pub signature: String,
    pub ordinal: u32,
    pub is_buy: bool,
    pub market_quote_amount_raw: u64,
    pub user_quote_amount_raw: u64,
    pub signed_user_cost_quote_raw: i128,
    pub effective_fee_bps: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpSwapEffectiveFeeContextValue {
    pub source_sequence: u64,
    pub source_observed_at_unix_ms: i64,
    pub age_ms: u64,
    pub evidence: PumpSwapEffectiveFeeEvidence,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PumpSwapEffectiveFeeContext {
    Missing,
    Stale(PumpSwapEffectiveFeeContextValue),
    RateUnknown(PumpSwapEffectiveFeeContextValue),
    Available(PumpSwapEffectiveFeeContextValue),
}

impl ShreksDb {
    pub fn pump_swap_effective_fee_context(
        &self,
        mint: &str,
        quote_mint: &str,
        is_buy: bool,
        as_of_sequence: u64,
        as_of_observed_at_unix_ms: i64,
        maximum_age_ms: u64,
    ) -> Result<PumpSwapEffectiveFeeContext, StorageError> {
        if mint.trim().is_empty() || quote_mint.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "PumpSwap fee context requires non-empty mint and quote mint".to_owned(),
            ));
        }
        if as_of_sequence == 0 {
            return Err(StorageError::InvalidData(
                "PumpSwap fee context as-of sequence must be positive".to_owned(),
            ));
        }
        if as_of_observed_at_unix_ms < 0 {
            return Err(StorageError::InvalidData(
                "PumpSwap fee context as-of observation time must be non-negative".to_owned(),
            ));
        }

        let as_of_sequence = i64::try_from(as_of_sequence).map_err(|_| {
            StorageError::InvalidData(
                "PumpSwap fee context as-of sequence exceeds SQLite signed integer range"
                    .to_owned(),
            )
        })?;
        let kind = if is_buy { "buy" } else { "sell" };

        let selected = self
            .connection
            .query_row(
                r#"SELECT signature, ordinal, sequence, observed_at_unix_ms
                   FROM fast_events
                   WHERE mint = ?1
                     AND quote_mint = ?2
                     AND venue = 'pump_swap'
                     AND kind = ?3
                     AND sequence <= ?4
                     AND observed_at_unix_ms <= ?5
                   ORDER BY sequence DESC
                   LIMIT 1"#,
                params![
                    mint,
                    quote_mint,
                    kind,
                    as_of_sequence,
                    as_of_observed_at_unix_ms
                ],
                |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, i64>(1)?,
                        row.get::<_, i64>(2)?,
                        row.get::<_, i64>(3)?,
                    ))
                },
            )
            .optional()?;

        let Some((signature, ordinal, source_sequence, source_observed_at_unix_ms)) = selected else {
            return Ok(PumpSwapEffectiveFeeContext::Missing);
        };

        let ordinal = u32::try_from(ordinal).map_err(|_| {
            StorageError::InvalidData(
                "PumpSwap fee context canonical ordinal is outside u32 range".to_owned(),
            )
        })?;
        let source_sequence = u64::try_from(source_sequence).map_err(|_| {
            StorageError::InvalidData(
                "PumpSwap fee context canonical sequence was negative".to_owned(),
            )
        })?;
        let age_ms = as_of_observed_at_unix_ms
            .checked_sub(source_observed_at_unix_ms)
            .ok_or_else(|| {
                StorageError::InvalidData(
                    "PumpSwap fee context age arithmetic overflowed".to_owned(),
                )
            })?;
        let age_ms = u64::try_from(age_ms).map_err(|_| {
            StorageError::InvalidData(
                "PumpSwap fee context selected a future observation".to_owned(),
            )
        })?;

        let evidence = self
            .pump_swap_effective_fee_evidence(&signature, ordinal)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "PumpSwap canonical fee context source '{}' ordinal {} is missing raw evidence",
                    signature, ordinal
                ))
            })?;
        if evidence.is_buy != is_buy {
            return Err(StorageError::InvalidData(format!(
                "PumpSwap canonical fee context source '{}' ordinal {} side mismatches requested context",
                signature, ordinal
            )));
        }

        let value = PumpSwapEffectiveFeeContextValue {
            source_sequence,
            source_observed_at_unix_ms,
            age_ms,
            evidence,
        };

        if age_ms > maximum_age_ms {
            return Ok(PumpSwapEffectiveFeeContext::Stale(value));
        }
        if value.evidence.effective_fee_bps.is_none() {
            return Ok(PumpSwapEffectiveFeeContext::RateUnknown(value));
        }
        Ok(PumpSwapEffectiveFeeContext::Available(value))
    }

    pub fn pump_swap_effective_fee_evidence(
        &self,
        signature: &str,
        ordinal: u32,
    ) -> Result<Option<PumpSwapEffectiveFeeEvidence>, StorageError> {
        if signature.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "PumpSwap effective-fee signature must be non-empty".to_owned(),
            ));
        }

        let conflict_count: i64 = self.connection.query_row(
            r#"SELECT COUNT(*)
               FROM pump_swap_trade_evidence_conflicts
               WHERE signature = ?1 AND ordinal = ?2"#,
            params![signature, i64::from(ordinal)],
            |row| row.get(0),
        )?;
        if conflict_count != 0 {
            return Err(StorageError::InvalidData(format!(
                "PumpSwap effective-fee source '{}' ordinal {} is conflict-quarantined",
                signature, ordinal
            )));
        }

        let source = self
            .pump_swap_trade_evidence_for_signature(signature)?
            .into_iter()
            .find(|candidate| candidate.ordinal == ordinal);
        let Some(source) = source else {
            return Ok(None);
        };

        let market_quote = i128::from(source.quote_amount_raw);
        let user_quote = i128::from(source.user_quote_amount_raw);
        let signed_user_cost_quote_raw = if source.is_buy {
            user_quote
                .checked_sub(market_quote)
                .ok_or_else(|| {
                    StorageError::InvalidData(
                        "PumpSwap BUY user-cost delta overflowed".to_owned(),
                    )
                })?
        } else {
            market_quote
                .checked_sub(user_quote)
                .ok_or_else(|| {
                    StorageError::InvalidData(
                        "PumpSwap SELL user-cost delta overflowed".to_owned(),
                    )
                })?
        };

        let effective_fee_bps = exact_effective_fee_bps(
            signed_user_cost_quote_raw,
            source.quote_amount_raw,
        )?;

        Ok(Some(PumpSwapEffectiveFeeEvidence {
            signature: source.signature,
            ordinal: source.ordinal,
            is_buy: source.is_buy,
            market_quote_amount_raw: source.quote_amount_raw,
            user_quote_amount_raw: source.user_quote_amount_raw,
            signed_user_cost_quote_raw,
            effective_fee_bps,
        }))
    }
}

fn exact_effective_fee_bps(
    signed_user_cost_quote_raw: i128,
    market_quote_amount_raw: u64,
) -> Result<Option<u32>, StorageError> {
    if signed_user_cost_quote_raw < 0 {
        return Ok(None);
    }

    let delta = u128::try_from(signed_user_cost_quote_raw).map_err(|_| {
        StorageError::InvalidData(
            "PumpSwap effective-fee raw delta is outside u128 range".to_owned(),
        )
    })?;
    let market_quote = u128::from(market_quote_amount_raw);
    if market_quote == 0 {
        return Err(StorageError::InvalidData(
            "PumpSwap effective-fee market quote amount must be positive".to_owned(),
        ));
    }

    let numerator = delta
        .checked_mul(BASIS_POINTS_DENOMINATOR)
        .ok_or_else(|| {
            StorageError::InvalidData(
                "PumpSwap effective-fee basis-point numerator overflowed".to_owned(),
            )
        })?;
    if numerator % market_quote != 0 {
        return Ok(None);
    }

    let exact = numerator / market_quote;
    let exact = u32::try_from(exact).map_err(|_| {
        StorageError::InvalidData(
            "PumpSwap exact effective fee basis points exceed u32".to_owned(),
        )
    })?;
    Ok(Some(exact))
}
