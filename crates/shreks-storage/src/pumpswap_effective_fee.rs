use rusqlite::params;

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

impl ShreksDb {
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
