use rusqlite::{params, OptionalExtension};
use shreks_core::{FastReserveContext, VenueId};

use crate::{
    PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb, StorageError, StoredFastEvent,
};

const SYSTEM_SOL_MINT: &str = "11111111111111111111111111111111";
const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";

pub fn pump_reserve_context_from_source(
    source: &PumpTradeEvidenceWrite,
    base_decimals: u8,
    quote_decimals: u8,
) -> FastReserveContext {
    let quote_is_sol = source.quote_mint == SYSTEM_SOL_MINT || source.quote_mint == WRAPPED_SOL_MINT;
    FastReserveContext::PumpCurve {
        virtual_base_reserve_raw: source.virtual_token_reserves_raw,
        virtual_quote_reserve_raw: if quote_is_sol {
            source.virtual_sol_reserves_raw
        } else {
            source.virtual_quote_reserves_raw
        },
        real_base_reserve_raw: source.real_token_reserves_raw,
        real_quote_reserve_raw: if quote_is_sol {
            source.real_sol_reserves_raw
        } else {
            source.real_quote_reserves_raw
        },
        base_decimals,
        quote_decimals,
    }
}

pub fn pump_swap_reserve_context_from_source(
    source: &PumpSwapTradeEvidenceWrite,
    base_decimals: u8,
    quote_decimals: u8,
) -> FastReserveContext {
    FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: source.pool_base_reserves_raw,
        pool_quote_reserve_raw: source.pool_quote_reserves_raw,
        virtual_quote_reserve_raw: None,
        base_decimals,
        quote_decimals,
    }
}

impl ShreksDb {
    /// Replay one canonical market with reserve state reconstructed from the
    /// immutable venue-specific raw evidence referenced by every FastEvent.
    ///
    /// Reserve context is intentionally not trusted from the canonical caller
    /// payload and is not duplicated into `fast_events`. The raw source row
    /// remains the single durable authority, so historical replay and newly
    /// normalized state derive the same exact integer reserve snapshot.
    pub fn fast_events_for_market_with_reserve_context(
        &self,
        mint: &str,
        quote_mint: &str,
        venue: VenueId,
    ) -> Result<Vec<StoredFastEvent>, StorageError> {
        let mut stored = self.fast_events_for_market(mint, quote_mint, venue)?;

        for row in &mut stored {
            let context = match row.event.market.venue {
                VenueId::PumpFunBondingCurve => self.pump_reserve_context_for_stored(row)?,
                VenueId::PumpSwap => self.pump_swap_reserve_context_for_stored(row)?,
                _ => continue,
            };
            row.event = row
                .event
                .clone()
                .with_reserve_context(context)
                .map_err(|error| {
                    StorageError::InvalidData(format!(
                        "stored FastEvent reserve context is invalid for '{}' ordinal {}: {error}",
                        row.event.id.signature, row.event.id.ordinal
                    ))
                })?;
        }

        Ok(stored)
    }

    fn pump_reserve_context_for_stored(
        &self,
        stored: &StoredFastEvent,
    ) -> Result<FastReserveContext, StorageError> {
        type RawPumpReserve = (String, String, String, String, String, String, String);

        let raw: Option<RawPumpReserve> = self
            .connection
            .query_row(
                r#"SELECT
                       quote_mint,
                       virtual_sol_reserves_raw,
                       virtual_token_reserves_raw,
                       real_sol_reserves_raw,
                       real_token_reserves_raw,
                       virtual_quote_reserves_raw,
                       real_quote_reserves_raw
                   FROM pump_trade_evidence
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![
                    stored.event.id.signature,
                    i64::from(stored.event.id.ordinal)
                ],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                        row.get(6)?,
                    ))
                },
            )
            .optional()?;

        let Some((
            raw_quote_mint,
            virtual_sol,
            virtual_token,
            real_sol,
            real_token,
            virtual_quote,
            real_quote,
        )) = raw
        else {
            return Err(StorageError::InvalidData(format!(
                "stored Pump FastEvent '{}' ordinal {} is missing immutable source evidence",
                stored.event.id.signature, stored.event.id.ordinal
            )));
        };

        let source = PumpTradeEvidenceWrite {
            provider: stored.event.provider,
            signature: stored.event.id.signature.clone(),
            ordinal: stored.event.id.ordinal,
            slot: stored.event.slot,
            observed_at_unix_ms: stored.source_observed_at_unix_ms,
            mint: stored.event.market.mint.clone(),
            quote_mint: raw_quote_mint,
            user: stored.event.actor.clone().unwrap_or_else(|| "source-replay".to_owned()),
            is_buy: matches!(stored.event.kind, shreks_core::FastEventKind::Buy),
            token_amount_raw: 0,
            sol_amount_raw: 0,
            quote_amount_raw: 0,
            timestamp_unix_seconds: 0,
            virtual_sol_reserves_raw: parse_u64_text(&virtual_sol, "Pump virtual SOL reserves")?,
            virtual_token_reserves_raw: parse_u64_text(
                &virtual_token,
                "Pump virtual token reserves",
            )?,
            real_sol_reserves_raw: parse_u64_text(&real_sol, "Pump real SOL reserves")?,
            real_token_reserves_raw: parse_u64_text(&real_token, "Pump real token reserves")?,
            virtual_quote_reserves_raw: parse_u64_text(
                &virtual_quote,
                "Pump virtual quote reserves",
            )?,
            real_quote_reserves_raw: parse_u64_text(&real_quote, "Pump real quote reserves")?,
            ix_name: "source-replay".to_owned(),
        };

        Ok(pump_reserve_context_from_source(
            &source,
            stored.base_decimals,
            stored.quote_decimals,
        ))
    }

    fn pump_swap_reserve_context_for_stored(
        &self,
        stored: &StoredFastEvent,
    ) -> Result<FastReserveContext, StorageError> {
        let raw: Option<(String, String)> = self
            .connection
            .query_row(
                r#"SELECT pool_base_reserves_raw, pool_quote_reserves_raw
                   FROM pump_swap_trade_evidence
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![
                    stored.event.id.signature,
                    i64::from(stored.event.id.ordinal)
                ],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;

        let Some((pool_base, pool_quote)) = raw else {
            return Err(StorageError::InvalidData(format!(
                "stored PumpSwap FastEvent '{}' ordinal {} is missing immutable source evidence",
                stored.event.id.signature, stored.event.id.ordinal
            )));
        };

        let virtual_quote_reserve_raw = self
            .pump_swap_execution_economics(
                &stored.event.id.signature,
                stored.event.id.ordinal,
            )?
            .and_then(|economics| economics.virtual_quote_reserves_raw);

        Ok(FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw: parse_u64_text(&pool_base, "PumpSwap pool base reserves")?,
            pool_quote_reserve_raw: parse_u64_text(&pool_quote, "PumpSwap pool quote reserves")?,
            virtual_quote_reserve_raw,
            base_decimals: stored.base_decimals,
            quote_decimals: stored.quote_decimals,
        })
    }
}

fn parse_u64_text(value: &str, field: &str) -> Result<u64, StorageError> {
    value.parse::<u64>().map_err(|error| {
        StorageError::InvalidData(format!("{field} is not u64 decimal text: {error}"))
    })
}
