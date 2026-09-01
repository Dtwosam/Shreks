use rusqlite::{params, OptionalExtension};
use shreks_core::{FastEvent, FastEventKind, ProviderId, VenueId};

use crate::{ShreksDb, StorageError};

const SYSTEM_SOL_MINT: &str = "11111111111111111111111111111111";
const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";
const PUMPSWAP_ORDINAL_NAMESPACE: u32 = 0x8000_0000;
const PUMPSWAP_MAX_LOG_INDEX: u32 = PUMPSWAP_ORDINAL_NAMESPACE - 1;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpSwapTradeEvidenceWrite {
    pub provider: ProviderId,
    pub signature: String,
    pub ordinal: u32,
    pub log_index: u32,
    pub slot: u64,
    pub observed_at_unix_ms: i64,
    pub pool: String,
    pub user: String,
    pub is_buy: bool,
    pub base_amount_raw: u64,
    pub quote_amount_raw: u64,
    pub user_quote_amount_raw: u64,
    pub timestamp_unix_seconds: i64,
    pub pool_base_reserves_raw: u64,
    pub pool_quote_reserves_raw: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpSwapMarket {
    pub mint: String,
    pub quote_mint: String,
    pub pool_address: String,
}

/// PumpSwap raw events share `(signature, ordinal)` with the canonical journal.
/// Reserve the high half of u32 for PumpSwap so one transaction can contain
/// bonding-curve and post-graduation events without identity collisions. The
/// original Solana log index remains stored separately for auditability.
pub fn pump_swap_event_ordinal(log_index: u32) -> Result<u32, StorageError> {
    if log_index > PUMPSWAP_MAX_LOG_INDEX {
        return Err(StorageError::InvalidData(format!(
            "PumpSwap log index {log_index} exceeds reserved ordinal namespace"
        )));
    }
    Ok(PUMPSWAP_ORDINAL_NAMESPACE | log_index)
}

impl ShreksDb {
    /// Persist one immutable PumpSwap economic event.
    ///
    /// `(signature, ordinal)` is the canonical identity. Replaying the same
    /// economics is idempotent even when a later provider, confirmed fork slot,
    /// or local observation timestamp differs; the first stored provenance
    /// remains authoritative. A conflicting economic payload still fails closed.
    pub fn record_pump_swap_trade_evidence(
        &self,
        evidence: &PumpSwapTradeEvidenceWrite,
    ) -> Result<bool, StorageError> {
        validate_evidence(evidence)?;

        let changed = self.connection.execute(
            r#"INSERT OR IGNORE INTO pump_swap_trade_evidence (
                   signature, ordinal, log_index, provider, slot, observed_at_unix_ms,
                   pool, user, is_buy,
                   base_amount_raw, quote_amount_raw, user_quote_amount_raw,
                   timestamp_unix_seconds, pool_base_reserves_raw, pool_quote_reserves_raw
               ) VALUES (
                   ?1, ?2, ?3, ?4, ?5, ?6,
                   ?7, ?8, ?9,
                   ?10, ?11, ?12,
                   ?13, ?14, ?15
               )"#,
            params![
                evidence.signature,
                i64::from(evidence.ordinal),
                i64::from(evidence.log_index),
                evidence.provider.as_str(),
                evidence.slot.to_string(),
                evidence.observed_at_unix_ms,
                evidence.pool,
                evidence.user,
                if evidence.is_buy { 1_i64 } else { 0_i64 },
                evidence.base_amount_raw.to_string(),
                evidence.quote_amount_raw.to_string(),
                evidence.user_quote_amount_raw.to_string(),
                evidence.timestamp_unix_seconds,
                evidence.pool_base_reserves_raw.to_string(),
                evidence.pool_quote_reserves_raw.to_string(),
            ],
        )?;

        if changed == 1 {
            return Ok(true);
        }

        let existing = self
            .pump_swap_trade_evidence_by_identity(&evidence.signature, evidence.ordinal)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "PumpSwap evidence '{}' ordinal {} disappeared after duplicate insert",
                    evidence.signature, evidence.ordinal
                ))
            })?;
        if same_economic_event(&existing, evidence) {
            return Ok(false);
        }

        Err(StorageError::InvalidData(format!(
            "conflicting PumpSwap evidence for signature '{}' ordinal {}",
            evidence.signature, evidence.ordinal
        )))
    }

    pub fn pump_swap_trade_evidence_for_signature(
        &self,
        signature: &str,
    ) -> Result<Vec<PumpSwapTradeEvidenceWrite>, StorageError> {
        validate_nonempty(signature, "PumpSwap signature")?;
        let mut statement = self.connection.prepare(
            r#"SELECT
                   provider, signature, ordinal, log_index, slot, observed_at_unix_ms,
                   pool, user, is_buy,
                   base_amount_raw, quote_amount_raw, user_quote_amount_raw,
                   timestamp_unix_seconds, pool_base_reserves_raw, pool_quote_reserves_raw
               FROM pump_swap_trade_evidence
               WHERE signature = ?1
               ORDER BY log_index ASC"#,
        )?;
        let rows = statement
            .query_map([signature], decode_row)?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(decode_stored).collect()
    }

    pub fn pending_pump_swap_trade_evidence(
        &self,
        limit: usize,
    ) -> Result<Vec<PumpSwapTradeEvidenceWrite>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("PumpSwap pending limit exceeds i64".to_owned())
        })?;
        let mut statement = self.connection.prepare(
            r#"SELECT
                   p.provider, p.signature, p.ordinal, p.log_index, p.slot, p.observed_at_unix_ms,
                   p.pool, p.user, p.is_buy,
                   p.base_amount_raw, p.quote_amount_raw, p.user_quote_amount_raw,
                   p.timestamp_unix_seconds, p.pool_base_reserves_raw, p.pool_quote_reserves_raw
               FROM pump_swap_trade_evidence AS p
               LEFT JOIN fast_events AS f
                 ON f.signature = p.signature AND f.ordinal = p.ordinal
               WHERE f.sequence IS NULL
               ORDER BY p.observed_at_unix_ms ASC, p.signature ASC, p.log_index ASC
               LIMIT ?1"#,
        )?;
        let rows = statement
            .query_map([limit], decode_row)?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(decode_stored).collect()
    }

    /// Return the oldest conflict-free PumpSwap rows whose verified lifecycle
    /// market and mint-decimal prerequisites are currently available. Pools
    /// with contradictory verified markets remain eligible so the existing
    /// resolver sees them and fails closed rather than silently skipping them.
    pub fn pending_normalizable_pump_swap_trade_evidence(
        &self,
        limit: usize,
    ) -> Result<Vec<PumpSwapTradeEvidenceWrite>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("PumpSwap normalizable pending limit exceeds i64".to_owned())
        })?;
        let mut statement = self.connection.prepare(
            r#"WITH distinct_markets AS (
                   SELECT DISTINCT pool_address, mint, quote_mint
                   FROM token_lifecycle_events
                   WHERE event_type = 'pump_graduation'
                     AND to_venue = 'pump_swap'
               ),
               market_counts AS (
                   SELECT pool_address, COUNT(*) AS market_count
                   FROM distinct_markets
                   GROUP BY pool_address
               ),
               eligible_pools AS (
                   SELECT pool_address
                   FROM market_counts
                   WHERE market_count <> 1

                   UNION

                   SELECT market.pool_address
                   FROM distinct_markets AS market
                   JOIN market_counts AS counts
                     ON counts.pool_address = market.pool_address
                   WHERE counts.market_count = 1
                     AND EXISTS (
                         SELECT 1
                         FROM token_candidates AS base_candidate
                         JOIN token_mint_states AS base_state
                           ON base_state.candidate_id = base_candidate.id
                         WHERE base_candidate.mint = market.mint
                     )
                     AND (
                         market.quote_mint = ?1
                         OR market.quote_mint = ?2
                         OR EXISTS (
                             SELECT 1
                             FROM token_candidates AS quote_candidate
                             JOIN token_mint_states AS quote_state
                               ON quote_state.candidate_id = quote_candidate.id
                             WHERE quote_candidate.mint = market.quote_mint
                         )
                     )
               )
               SELECT
                   p.provider, p.signature, p.ordinal, p.log_index, p.slot, p.observed_at_unix_ms,
                   p.pool, p.user, p.is_buy,
                   p.base_amount_raw, p.quote_amount_raw, p.user_quote_amount_raw,
                   p.timestamp_unix_seconds, p.pool_base_reserves_raw, p.pool_quote_reserves_raw
               FROM eligible_pools AS eligible
               JOIN pump_swap_trade_evidence AS p
                 ON p.pool = eligible.pool_address
               LEFT JOIN fast_events AS f
                 ON f.signature = p.signature AND f.ordinal = p.ordinal
               WHERE f.sequence IS NULL
                 AND NOT EXISTS (
                     SELECT 1
                     FROM pump_swap_trade_evidence_conflicts AS conflict
                     WHERE conflict.signature = p.signature
                       AND conflict.ordinal = p.ordinal
                 )
               ORDER BY p.observed_at_unix_ms ASC, p.signature ASC, p.log_index ASC
               LIMIT ?3"#,
        )?;
        let rows = statement
            .query_map(params![SYSTEM_SOL_MINT, WRAPPED_SOL_MINT, limit], decode_row)?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(decode_stored).collect()
    }

    /// Resolve a PumpSwap pool only from verified Pump graduation lifecycle
    /// evidence. Missing mapping stays unresolved; contradictory markets for
    /// one pool fail closed instead of choosing by recency.
    pub fn pump_swap_market_for_pool(
        &self,
        pool: &str,
    ) -> Result<Option<PumpSwapMarket>, StorageError> {
        validate_nonempty(pool, "PumpSwap pool")?;
        let mut statement = self.connection.prepare(
            r#"SELECT DISTINCT mint, quote_mint
               FROM token_lifecycle_events
               WHERE pool_address = ?1
                 AND event_type = 'pump_graduation'
                 AND to_venue = 'pump_swap'
               ORDER BY mint ASC, quote_mint ASC"#,
        )?;
        let rows = statement
            .query_map([pool], |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)))?
            .collect::<Result<Vec<_>, _>>()?;

        match rows.as_slice() {
            [] => Ok(None),
            [(mint, quote_mint)] => Ok(Some(PumpSwapMarket {
                mint: mint.clone(),
                quote_mint: quote_mint.clone(),
                pool_address: pool.to_owned(),
            })),
            values => Err(StorageError::InvalidData(format!(
                "contradictory PumpSwap lifecycle markets for pool '{pool}': {values:?}"
            ))),
        }
    }

    /// Append one PumpSwap canonical event while preserving the same journal
    /// sequence/idempotency contract as bonding-curve FastEvents.
    pub fn record_pump_swap_fast_event(
        &self,
        event: &FastEvent,
        source_observed_at_unix_ms: i64,
        base_decimals: u8,
        quote_decimals: u8,
    ) -> Result<bool, StorageError> {
        if event.market.venue != VenueId::PumpSwap {
            return Err(StorageError::InvalidData(
                "PumpSwap FastEvent writer requires pump_swap venue".to_owned(),
            ));
        }

        let source = self
            .pump_swap_trade_evidence_by_identity(&event.id.signature, event.id.ordinal)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "PumpSwap FastEvent source '{}' ordinal {} is missing",
                    event.id.signature, event.id.ordinal
                ))
            })?;
        if source.observed_at_unix_ms != source_observed_at_unix_ms {
            return Err(StorageError::InvalidData(format!(
                "PumpSwap FastEvent source observation mismatch for '{}' ordinal {}",
                event.id.signature, event.id.ordinal
            )));
        }
        let market = self.pump_swap_market_for_pool(&source.pool)?.ok_or_else(|| {
            StorageError::InvalidData(format!(
                "PumpSwap pool '{}' has no verified lifecycle market",
                source.pool
            ))
        })?;
        self.record_pump_swap_fast_event_from_source(
            event,
            &source,
            &market,
            base_decimals,
            quote_decimals,
        )
    }

    /// Append one PumpSwap canonical event from raw/lifecycle rows already
    /// selected in this connection's current transaction snapshot. Existing
    /// database triggers still require the raw identity and contiguous sequence.
    pub fn record_pump_swap_fast_event_from_source(
        &self,
        event: &FastEvent,
        source: &PumpSwapTradeEvidenceWrite,
        market: &PumpSwapMarket,
        base_decimals: u8,
        quote_decimals: u8,
    ) -> Result<bool, StorageError> {
        if event.market.venue != VenueId::PumpSwap {
            return Err(StorageError::InvalidData(
                "PumpSwap FastEvent writer requires pump_swap venue".to_owned(),
            ));
        }
        if event.id.signature != source.signature || event.id.ordinal != source.ordinal {
            return Err(StorageError::InvalidData(format!(
                "PumpSwap FastEvent identity does not match supplied source '{}' ordinal {}",
                source.signature, source.ordinal
            )));
        }
        if market.pool_address != source.pool {
            return Err(StorageError::InvalidData(format!(
                "PumpSwap verified market pool '{}' does not match source pool '{}'",
                market.pool_address, source.pool
            )));
        }
        if source.observed_at_unix_ms < 0 || source.observed_at_unix_ms > event.observed_at_unix_ms {
            return Err(StorageError::InvalidData(
                "PumpSwap FastEvent source observation timestamp is invalid".to_owned(),
            ));
        }
        validate_canonical_source(event, source, market, base_decimals, quote_decimals)?;

        let sequence = i64::try_from(event.sequence).map_err(|_| {
            StorageError::InvalidData("PumpSwap FastEvent sequence exceeds SQLite integer range".to_owned())
        })?;
        let kind = match event.kind {
            FastEventKind::Buy => "buy",
            FastEventKind::Sell => "sell",
        };
        let changed = self.connection.execute(
            r#"INSERT OR IGNORE INTO fast_events (
                   sequence, signature, ordinal, provider, slot,
                   source_observed_at_unix_ms, occurred_at_unix_ms, observed_at_unix_ms,
                   mint, quote_mint, venue, kind, actor,
                   base_quantity, quote_quantity, price_quote,
                   base_decimals, quote_decimals
               ) VALUES (
                   ?1, ?2, ?3, ?4, ?5,
                   ?6, ?7, ?8,
                   ?9, ?10, ?11, ?12, ?13,
                   ?14, ?15, ?16,
                   ?17, ?18
               )"#,
            params![
                sequence,
                event.id.signature,
                i64::from(event.id.ordinal),
                event.provider.as_str(),
                event.slot.to_string(),
                source.observed_at_unix_ms,
                event.occurred_at_unix_ms,
                event.observed_at_unix_ms,
                event.market.mint,
                event.market.quote_mint,
                event.market.venue.as_str(),
                kind,
                event.actor,
                event.base_quantity,
                event.quote_quantity,
                event.price_quote,
                i64::from(base_decimals),
                i64::from(quote_decimals),
            ],
        )?;
        if changed == 1 {
            return Ok(true);
        }

        let existing = self.connection.query_row(
            r#"SELECT
                   sequence, provider, slot, source_observed_at_unix_ms,
                   occurred_at_unix_ms, observed_at_unix_ms,
                   mint, quote_mint, venue, kind, actor,
                   base_quantity, quote_quantity, price_quote,
                   base_decimals, quote_decimals
               FROM fast_events
               WHERE signature = ?1 AND ordinal = ?2"#,
            params![event.id.signature, i64::from(event.id.ordinal)],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?, row.get::<_, String>(1)?, row.get::<_, String>(2)?,
                    row.get::<_, i64>(3)?, row.get::<_, i64>(4)?, row.get::<_, i64>(5)?,
                    row.get::<_, String>(6)?, row.get::<_, String>(7)?, row.get::<_, String>(8)?,
                    row.get::<_, String>(9)?, row.get::<_, Option<String>>(10)?,
                    row.get::<_, f64>(11)?, row.get::<_, f64>(12)?, row.get::<_, f64>(13)?,
                    row.get::<_, i64>(14)?, row.get::<_, i64>(15)?,
                ))
            },
        ).optional()?;

        let Some(existing) = existing else {
            return Err(StorageError::InvalidData(format!(
                "PumpSwap FastEvent insert for '{}' ordinal {} collided with another sequence",
                event.id.signature, event.id.ordinal
            )));
        };
        let same = existing.1 == event.provider.as_str()
            && existing.2 == event.slot.to_string()
            && existing.3 == source.observed_at_unix_ms
            && existing.4 == event.occurred_at_unix_ms
            && existing.5 == event.observed_at_unix_ms
            && existing.6 == event.market.mint
            && existing.7 == event.market.quote_mint
            && existing.8 == event.market.venue.as_str()
            && existing.9 == kind
            && existing.10 == event.actor
            && existing.11 == event.base_quantity
            && existing.12 == event.quote_quantity
            && existing.13 == event.price_quote
            && existing.14 == i64::from(base_decimals)
            && existing.15 == i64::from(quote_decimals);
        if same {
            return Ok(false);
        }

        Err(StorageError::InvalidData(format!(
            "conflicting PumpSwap FastEvent for signature '{}' ordinal {}",
            event.id.signature, event.id.ordinal
        )))
    }

    fn pump_swap_trade_evidence_by_identity(
        &self,
        signature: &str,
        ordinal: u32,
    ) -> Result<Option<PumpSwapTradeEvidenceWrite>, StorageError> {
        let raw = self.connection.query_row(
            r#"SELECT
                   provider, signature, ordinal, log_index, slot, observed_at_unix_ms,
                   pool, user, is_buy,
                   base_amount_raw, quote_amount_raw, user_quote_amount_raw,
                   timestamp_unix_seconds, pool_base_reserves_raw, pool_quote_reserves_raw
               FROM pump_swap_trade_evidence
               WHERE signature = ?1 AND ordinal = ?2"#,
            params![signature, i64::from(ordinal)],
            decode_row,
        ).optional()?;
        raw.map(decode_stored).transpose()
    }
}

type RawPumpSwapRow = (
    String, String, i64, i64, String, i64,
    String, String, i64,
    String, String, String,
    i64, String, String,
);

fn decode_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<RawPumpSwapRow> {
    Ok((
        row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?, row.get(5)?,
        row.get(6)?, row.get(7)?, row.get(8)?,
        row.get(9)?, row.get(10)?, row.get(11)?,
        row.get(12)?, row.get(13)?, row.get(14)?,
    ))
}

fn decode_stored(raw: RawPumpSwapRow) -> Result<PumpSwapTradeEvidenceWrite, StorageError> {
    let (
        provider, signature, ordinal, log_index, slot, observed_at_unix_ms,
        pool, user, is_buy,
        base_amount_raw, quote_amount_raw, user_quote_amount_raw,
        timestamp_unix_seconds, pool_base_reserves_raw, pool_quote_reserves_raw,
    ) = raw;
    Ok(PumpSwapTradeEvidenceWrite {
        provider: parse_provider(&provider)?,
        signature,
        ordinal: u32::try_from(ordinal).map_err(|_| StorageError::InvalidData(
            "PumpSwap ordinal was outside u32 range".to_owned()
        ))?,
        log_index: u32::try_from(log_index).map_err(|_| StorageError::InvalidData(
            "PumpSwap log index was outside u32 range".to_owned()
        ))?,
        slot: parse_u64(&slot, "PumpSwap slot")?,
        observed_at_unix_ms,
        pool,
        user,
        is_buy: match is_buy {
            0 => false,
            1 => true,
            other => return Err(StorageError::InvalidData(format!(
                "PumpSwap is_buy stored invalid value {other}"
            ))),
        },
        base_amount_raw: parse_u64(&base_amount_raw, "PumpSwap base_amount_raw")?,
        quote_amount_raw: parse_u64(&quote_amount_raw, "PumpSwap quote_amount_raw")?,
        user_quote_amount_raw: parse_u64(&user_quote_amount_raw, "PumpSwap user_quote_amount_raw")?,
        timestamp_unix_seconds,
        pool_base_reserves_raw: parse_u64(&pool_base_reserves_raw, "PumpSwap pool_base_reserves_raw")?,
        pool_quote_reserves_raw: parse_u64(&pool_quote_reserves_raw, "PumpSwap pool_quote_reserves_raw")?,
    })
}

fn validate_evidence(evidence: &PumpSwapTradeEvidenceWrite) -> Result<(), StorageError> {
    validate_nonempty(&evidence.signature, "PumpSwap signature")?;
    validate_nonempty(&evidence.pool, "PumpSwap pool")?;
    validate_nonempty(&evidence.user, "PumpSwap user")?;
    if evidence.ordinal != pump_swap_event_ordinal(evidence.log_index)? {
        return Err(StorageError::InvalidData(
            "PumpSwap ordinal does not match reserved log-index mapping".to_owned(),
        ));
    }
    if evidence.observed_at_unix_ms < 0 || evidence.timestamp_unix_seconds < 0 {
        return Err(StorageError::InvalidData(
            "PumpSwap timestamps must be non-negative".to_owned(),
        ));
    }
    if evidence.base_amount_raw == 0 || evidence.quote_amount_raw == 0 || evidence.user_quote_amount_raw == 0 {
        return Err(StorageError::InvalidData(
            "PumpSwap executed quantities must be non-zero".to_owned(),
        ));
    }
    Ok(())
}

fn validate_canonical_source(
    event: &FastEvent,
    source: &PumpSwapTradeEvidenceWrite,
    market: &PumpSwapMarket,
    base_decimals: u8,
    quote_decimals: u8,
) -> Result<(), StorageError> {
    let expected_quote_mint = if market.quote_mint == SYSTEM_SOL_MINT || market.quote_mint == WRAPPED_SOL_MINT {
        WRAPPED_SOL_MINT
    } else {
        market.quote_mint.as_str()
    };
    let occurred_at_unix_ms = source.timestamp_unix_seconds.checked_mul(1_000).ok_or_else(|| {
        StorageError::InvalidData(format!(
            "PumpSwap FastEvent source timestamp overflow for '{}' ordinal {}",
            source.signature, source.ordinal
        ))
    })?;
    let base_scale = 10_f64.powi(i32::from(base_decimals));
    let quote_scale = 10_f64.powi(i32::from(quote_decimals));
    if !base_scale.is_finite() || base_scale <= 0.0 || !quote_scale.is_finite() || quote_scale <= 0.0 {
        return Err(StorageError::InvalidData(format!(
            "PumpSwap FastEvent decimal scale is invalid for '{}' ordinal {}",
            source.signature, source.ordinal
        )));
    }
    let base_quantity = source.base_amount_raw as f64 / base_scale;
    let quote_quantity = source.quote_amount_raw as f64 / quote_scale;
    let price_quote = quote_quantity / base_quantity;
    let expected_kind = if source.is_buy {
        FastEventKind::Buy
    } else {
        FastEventKind::Sell
    };

    if event.provider != source.provider
        || event.market.mint != market.mint
        || event.market.quote_mint != expected_quote_mint
        || event.kind != expected_kind
        || event.actor.as_deref() != Some(source.user.as_str())
        || event.slot != source.slot
        || event.occurred_at_unix_ms != occurred_at_unix_ms
        || event.base_quantity != base_quantity
        || event.quote_quantity != quote_quantity
        || event.price_quote != price_quote
    {
        return Err(StorageError::InvalidData(format!(
            "PumpSwap FastEvent payload does not match immutable source '{}' ordinal {} and verified pool '{}' lifecycle",
            source.signature, source.ordinal, source.pool
        )));
    }

    Ok(())
}

fn same_economic_event(
    stored: &PumpSwapTradeEvidenceWrite,
    incoming: &PumpSwapTradeEvidenceWrite,
) -> bool {
    stored.signature == incoming.signature
        && stored.ordinal == incoming.ordinal
        && stored.log_index == incoming.log_index
        && stored.pool == incoming.pool
        && stored.user == incoming.user
        && stored.is_buy == incoming.is_buy
        && stored.base_amount_raw == incoming.base_amount_raw
        && stored.quote_amount_raw == incoming.quote_amount_raw
        && stored.user_quote_amount_raw == incoming.user_quote_amount_raw
        && stored.timestamp_unix_seconds == incoming.timestamp_unix_seconds
        && stored.pool_base_reserves_raw == incoming.pool_base_reserves_raw
        && stored.pool_quote_reserves_raw == incoming.pool_quote_reserves_raw
}

fn validate_nonempty(value: &str, field: &str) -> Result<(), StorageError> {
    if value.trim().is_empty() {
        return Err(StorageError::InvalidData(format!("{field} must not be empty")));
    }
    Ok(())
}

fn parse_u64(value: &str, field: &str) -> Result<u64, StorageError> {
    value.parse::<u64>().map_err(|error| {
        StorageError::InvalidData(format!("{field} is not u64 decimal text: {error}"))
    })
}

fn parse_provider(value: &str) -> Result<ProviderId, StorageError> {
    match value {
        "dexscreener" => Ok(ProviderId::DexScreener),
        "helius" => Ok(ProviderId::Helius),
        "alchemy" => Ok(ProviderId::Alchemy),
        "chainstack" => Ok(ProviderId::Chainstack),
        "solana_public" => Ok(ProviderId::SolanaPublic),
        "jupiter" => Ok(ProviderId::Jupiter),
        "meteora" => Ok(ProviderId::Meteora),
        other => Err(StorageError::InvalidData(format!(
            "unknown provider id '{other}' in PumpSwap storage"
        ))),
    }
}
