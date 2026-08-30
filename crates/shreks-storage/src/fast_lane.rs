use rusqlite::{params, OptionalExtension};
use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, ProviderId, VenueId,
};

use crate::{ShreksDb, StorageError};

const SYSTEM_SOL_MINT: &str = "11111111111111111111111111111111";
const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpTradeEvidenceWrite {
    pub provider: ProviderId,
    pub signature: String,
    pub ordinal: u32,
    pub slot: u64,
    pub observed_at_unix_ms: i64,
    pub mint: String,
    pub quote_mint: String,
    pub user: String,
    pub is_buy: bool,
    pub token_amount_raw: u64,
    pub sol_amount_raw: u64,
    pub quote_amount_raw: u64,
    pub timestamp_unix_seconds: i64,
    pub virtual_sol_reserves_raw: u64,
    pub virtual_token_reserves_raw: u64,
    pub real_sol_reserves_raw: u64,
    pub real_token_reserves_raw: u64,
    pub virtual_quote_reserves_raw: u64,
    pub real_quote_reserves_raw: u64,
    pub ix_name: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StoredFastEvent {
    pub event: FastEvent,
    pub source_observed_at_unix_ms: i64,
    pub base_decimals: u8,
    pub quote_decimals: u8,
}

impl ShreksDb {
    /// Persist one immutable Pump economic event.
    ///
    /// `(signature, ordinal)` is the canonical identity. Replaying the same
    /// economics is idempotent even when a later provider, confirmed fork slot,
    /// or local observation timestamp differs; the first stored provenance
    /// remains authoritative. A conflicting economic payload for an existing
    /// identity fails closed instead of overwriting training evidence.
    pub fn record_pump_trade_evidence(
        &self,
        evidence: &PumpTradeEvidenceWrite,
    ) -> Result<bool, StorageError> {
        validate_trade_evidence(evidence)?;

        let changed = self.connection.execute(
            r#"INSERT OR IGNORE INTO pump_trade_evidence (
                   signature, ordinal, provider, slot, observed_at_unix_ms,
                   mint, quote_mint, user, is_buy,
                   token_amount_raw, sol_amount_raw, quote_amount_raw,
                   timestamp_unix_seconds,
                   virtual_sol_reserves_raw, virtual_token_reserves_raw,
                   real_sol_reserves_raw, real_token_reserves_raw,
                   virtual_quote_reserves_raw, real_quote_reserves_raw,
                   ix_name
               ) VALUES (
                   ?1, ?2, ?3, ?4, ?5,
                   ?6, ?7, ?8, ?9,
                   ?10, ?11, ?12,
                   ?13,
                   ?14, ?15,
                   ?16, ?17,
                   ?18, ?19,
                   ?20
               )"#,
            params![
                evidence.signature,
                i64::from(evidence.ordinal),
                evidence.provider.as_str(),
                evidence.slot.to_string(),
                evidence.observed_at_unix_ms,
                evidence.mint,
                evidence.quote_mint,
                evidence.user,
                if evidence.is_buy { 1_i64 } else { 0_i64 },
                evidence.token_amount_raw.to_string(),
                evidence.sol_amount_raw.to_string(),
                evidence.quote_amount_raw.to_string(),
                evidence.timestamp_unix_seconds,
                evidence.virtual_sol_reserves_raw.to_string(),
                evidence.virtual_token_reserves_raw.to_string(),
                evidence.real_sol_reserves_raw.to_string(),
                evidence.real_token_reserves_raw.to_string(),
                evidence.virtual_quote_reserves_raw.to_string(),
                evidence.real_quote_reserves_raw.to_string(),
                evidence.ix_name,
            ],
        )?;

        if changed == 1 {
            return Ok(true);
        }

        let existing = self
            .pump_trade_evidence_by_identity(&evidence.signature, evidence.ordinal)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "Pump trade evidence '{}' ordinal {} disappeared after duplicate insert",
                    evidence.signature, evidence.ordinal
                ))
            })?;

        if same_economic_event(&existing, evidence) {
            return Ok(false);
        }

        Err(StorageError::InvalidData(format!(
            "conflicting Pump trade evidence for signature '{}' ordinal {}",
            evidence.signature, evidence.ordinal
        )))
    }

    pub fn pump_trade_evidence_for_signature(
        &self,
        signature: &str,
    ) -> Result<Vec<PumpTradeEvidenceWrite>, StorageError> {
        validate_nonempty(signature, "Pump trade signature")?;

        let mut statement = self.connection.prepare(
            r#"SELECT
                   provider, signature, ordinal, slot, observed_at_unix_ms,
                   mint, quote_mint, user, is_buy,
                   token_amount_raw, sol_amount_raw, quote_amount_raw,
                   timestamp_unix_seconds,
                   virtual_sol_reserves_raw, virtual_token_reserves_raw,
                   real_sol_reserves_raw, real_token_reserves_raw,
                   virtual_quote_reserves_raw, real_quote_reserves_raw,
                   ix_name
               FROM pump_trade_evidence
               WHERE signature = ?1
               ORDER BY ordinal ASC"#,
        )?;

        let rows = statement
            .query_map([signature], decode_trade_row)?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(decode_stored_trade).collect()
    }

    /// Return raw Pump events that have not yet been normalized into canonical
    /// FastEvents. The bounded oldest-first order is stable across restarts.
    pub fn pending_pump_trade_evidence(
        &self,
        limit: usize,
    ) -> Result<Vec<PumpTradeEvidenceWrite>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("Pump pending-trade limit exceeds i64".to_owned())
        })?;

        let mut statement = self.connection.prepare(
            r#"SELECT
                   p.provider, p.signature, p.ordinal, p.slot, p.observed_at_unix_ms,
                   p.mint, p.quote_mint, p.user, p.is_buy,
                   p.token_amount_raw, p.sol_amount_raw, p.quote_amount_raw,
                   p.timestamp_unix_seconds,
                   p.virtual_sol_reserves_raw, p.virtual_token_reserves_raw,
                   p.real_sol_reserves_raw, p.real_token_reserves_raw,
                   p.virtual_quote_reserves_raw, p.real_quote_reserves_raw,
                   p.ix_name
               FROM pump_trade_evidence AS p
               LEFT JOIN fast_events AS f
                 ON f.signature = p.signature AND f.ordinal = p.ordinal
               WHERE f.sequence IS NULL
               ORDER BY p.observed_at_unix_ms ASC, p.signature ASC, p.ordinal ASC
               LIMIT ?1"#,
        )?;
        let rows = statement
            .query_map([limit], decode_trade_row)?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(decode_stored_trade).collect()
    }

    /// Resolve one mint's verified decimals across all normalized candidate
    /// identities. Missing evidence stays unresolved; contradictory evidence
    /// fails closed instead of choosing a value by recency.
    pub fn verified_mint_decimals(&self, mint: &str) -> Result<Option<u8>, StorageError> {
        validate_nonempty(mint, "mint")?;

        let mut statement = self.connection.prepare(
            r#"SELECT DISTINCT s.decimals
               FROM token_mint_states AS s
               JOIN token_candidates AS c ON c.id = s.candidate_id
               WHERE c.mint = ?1
               ORDER BY s.decimals ASC"#,
        )?;
        let decimals = statement
            .query_map([mint], |row| row.get::<_, i64>(0))?
            .collect::<Result<Vec<_>, _>>()?;

        match decimals.as_slice() {
            [] => Ok(None),
            [value] => u8::try_from(*value)
                .map(Some)
                .map_err(|_| StorageError::InvalidData(format!(
                    "verified decimals for mint '{mint}' were outside u8 range"
                ))),
            values => Err(StorageError::InvalidData(format!(
                "contradictory verified decimals for mint '{mint}': {values:?}"
            ))),
        }
    }

    /// Return the next durable append sequence. Sequence is derived from the
    /// persisted journal, so restart cannot reset or renumber accepted events.
    pub fn next_fast_event_sequence(&self) -> Result<u64, StorageError> {
        let last: i64 = self.connection.query_row(
            "SELECT COALESCE(MAX(sequence), 0) FROM fast_events",
            [],
            |row| row.get(0),
        )?;
        let next = last.checked_add(1).ok_or_else(|| {
            StorageError::InvalidData("FastEvent sequence exhausted SQLite integer range".to_owned())
        })?;
        u64::try_from(next).map_err(|_| {
            StorageError::InvalidData("FastEvent next sequence was negative".to_owned())
        })
    }

    /// Append one canonical FastEvent linked to immutable venue-specific raw evidence.
    ///
    /// Canonical `observed_at_unix_ms` is the time the normalized event became
    /// usable. `source_observed_at_unix_ms` preserves the earlier raw websocket
    /// observation and must exactly match the immutable source row. Replaying
    /// the same identity is idempotent even if the caller proposes the next
    /// unused sequence; conflicting canonical economics fail closed.
    pub fn record_fast_event(
        &self,
        event: &FastEvent,
        source_observed_at_unix_ms: i64,
        base_decimals: u8,
        quote_decimals: u8,
    ) -> Result<bool, StorageError> {
        match event.market.venue {
            VenueId::PumpSwap => {
                return self.record_pump_swap_fast_event(
                    event,
                    source_observed_at_unix_ms,
                    base_decimals,
                    quote_decimals,
                );
            }
            VenueId::PumpFunBondingCurve => {}
            other => {
                return Err(StorageError::InvalidData(format!(
                    "FastEvent storage has no raw evidence source for venue '{}'",
                    other.as_str()
                )));
            }
        }

        if source_observed_at_unix_ms < 0 {
            return Err(StorageError::InvalidData(
                "FastEvent source observation timestamp must be non-negative".to_owned(),
            ));
        }
        if source_observed_at_unix_ms > event.observed_at_unix_ms {
            return Err(StorageError::InvalidData(format!(
                "FastEvent source observation {source_observed_at_unix_ms} is later than canonical observation {}",
                event.observed_at_unix_ms
            )));
        }

        let source = self
            .pump_trade_evidence_by_identity(&event.id.signature, event.id.ordinal)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "FastEvent source Pump evidence '{}' ordinal {} is missing",
                    event.id.signature, event.id.ordinal
                ))
            })?;
        if source.observed_at_unix_ms != source_observed_at_unix_ms {
            return Err(StorageError::InvalidData(format!(
                "FastEvent source observation mismatch for '{}' ordinal {}: stored {}, supplied {}",
                event.id.signature,
                event.id.ordinal,
                source.observed_at_unix_ms,
                source_observed_at_unix_ms
            )));
        }
        validate_pump_canonical_source(event, &source, base_decimals, quote_decimals)?;

        let sequence = i64::try_from(event.sequence).map_err(|_| {
            StorageError::InvalidData("FastEvent sequence exceeds SQLite integer range".to_owned())
        })?;
        let ordinal = i64::from(event.id.ordinal);
        let kind = fast_event_kind_str(event.kind);

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
                ordinal,
                event.provider.as_str(),
                event.slot.to_string(),
                source_observed_at_unix_ms,
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

        let existing = self
            .fast_event_by_identity(&event.id.signature, event.id.ordinal)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "FastEvent insert for '{}' ordinal {} collided with another sequence",
                    event.id.signature, event.id.ordinal
                ))
            })?;

        if same_canonical_event(
            &existing,
            event,
            source_observed_at_unix_ms,
            base_decimals,
            quote_decimals,
        ) {
            return Ok(false);
        }

        Err(StorageError::InvalidData(format!(
            "conflicting FastEvent for signature '{}' ordinal {}",
            event.id.signature, event.id.ordinal
        )))
    }

    /// Replay one market's canonical journal in durable sequence order.
    ///
    /// If any canonical identity in the requested market later entered the
    /// venue-specific conflict quarantine, replay fails closed. The immutable
    /// canonical journal is preserved for forensics, but ambiguous economics
    /// are never returned as trusted market state.
    pub fn fast_events_for_market(
        &self,
        mint: &str,
        quote_mint: &str,
        venue: VenueId,
    ) -> Result<Vec<StoredFastEvent>, StorageError> {
        validate_nonempty(mint, "FastEvent mint")?;
        validate_nonempty(quote_mint, "FastEvent quote mint")?;

        let quarantined_canonical: i64 = match venue {
            VenueId::PumpFunBondingCurve => self.connection.query_row(
                r#"SELECT COUNT(*)
                   FROM fast_events AS f
                   WHERE f.mint = ?1 AND f.quote_mint = ?2 AND f.venue = ?3
                     AND EXISTS (
                         SELECT 1
                         FROM pump_trade_evidence_conflicts AS c
                         WHERE c.signature = f.signature AND c.ordinal = f.ordinal
                     )"#,
                params![mint, quote_mint, venue.as_str()],
                |row| row.get(0),
            )?,
            VenueId::PumpSwap => self.connection.query_row(
                r#"SELECT COUNT(*)
                   FROM fast_events AS f
                   WHERE f.mint = ?1 AND f.quote_mint = ?2 AND f.venue = ?3
                     AND EXISTS (
                         SELECT 1
                         FROM pump_swap_trade_evidence_conflicts AS c
                         WHERE c.signature = f.signature AND c.ordinal = f.ordinal
                     )"#,
                params![mint, quote_mint, venue.as_str()],
                |row| row.get(0),
            )?,
            _ => 0,
        };
        if quarantined_canonical > 0 {
            return Err(StorageError::InvalidData(format!(
                "FastEvent market replay blocked by {quarantined_canonical} conflict-quarantined canonical identities for venue '{}'",
                venue.as_str()
            )));
        }

        let mut statement = self.connection.prepare(
            r#"SELECT
                   sequence, signature, ordinal, provider, slot,
                   source_observed_at_unix_ms, occurred_at_unix_ms, observed_at_unix_ms,
                   mint, quote_mint, venue, kind, actor,
                   base_quantity, quote_quantity, price_quote,
                   base_decimals, quote_decimals
               FROM fast_events
               WHERE mint = ?1 AND quote_mint = ?2 AND venue = ?3
               ORDER BY sequence ASC"#,
        )?;
        let rows = statement
            .query_map(params![mint, quote_mint, venue.as_str()], decode_fast_event_row)?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(decode_stored_fast_event).collect()
    }

    fn pump_trade_evidence_by_identity(
        &self,
        signature: &str,
        ordinal: u32,
    ) -> Result<Option<PumpTradeEvidenceWrite>, StorageError> {
        let raw = self
            .connection
            .query_row(
                r#"SELECT
                       provider, signature, ordinal, slot, observed_at_unix_ms,
                       mint, quote_mint, user, is_buy,
                       token_amount_raw, sol_amount_raw, quote_amount_raw,
                       timestamp_unix_seconds,
                       virtual_sol_reserves_raw, virtual_token_reserves_raw,
                       real_sol_reserves_raw, real_token_reserves_raw,
                       virtual_quote_reserves_raw, real_quote_reserves_raw,
                       ix_name
                   FROM pump_trade_evidence
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![signature, i64::from(ordinal)],
                decode_trade_row,
            )
            .optional()?;
        raw.map(decode_stored_trade).transpose()
    }

    fn fast_event_by_identity(
        &self,
        signature: &str,
        ordinal: u32,
    ) -> Result<Option<StoredFastEvent>, StorageError> {
        let raw = self
            .connection
            .query_row(
                r#"SELECT
                       sequence, signature, ordinal, provider, slot,
                       source_observed_at_unix_ms, occurred_at_unix_ms, observed_at_unix_ms,
                       mint, quote_mint, venue, kind, actor,
                       base_quantity, quote_quantity, price_quote,
                       base_decimals, quote_decimals
                   FROM fast_events
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![signature, i64::from(ordinal)],
                decode_fast_event_row,
            )
            .optional()?;
        raw.map(decode_stored_fast_event).transpose()
    }
}

type RawTradeRow = (
    String,
    String,
    i64,
    String,
    i64,
    String,
    String,
    String,
    i64,
    String,
    String,
    String,
    i64,
    String,
    String,
    String,
    String,
    String,
    String,
    String,
);

type RawFastEventRow = (
    i64,
    String,
    i64,
    String,
    String,
    i64,
    i64,
    i64,
    String,
    String,
    String,
    String,
    Option<String>,
    f64,
    f64,
    f64,
    i64,
    i64,
);

fn decode_trade_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<RawTradeRow> {
    Ok((
        row.get(0)?,
        row.get(1)?,
        row.get(2)?,
        row.get(3)?,
        row.get(4)?,
        row.get(5)?,
        row.get(6)?,
        row.get(7)?,
        row.get(8)?,
        row.get(9)?,
        row.get(10)?,
        row.get(11)?,
        row.get(12)?,
        row.get(13)?,
        row.get(14)?,
        row.get(15)?,
        row.get(16)?,
        row.get(17)?,
        row.get(18)?,
        row.get(19)?,
    ))
}

fn decode_fast_event_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<RawFastEventRow> {
    Ok((
        row.get(0)?,
        row.get(1)?,
        row.get(2)?,
        row.get(3)?,
        row.get(4)?,
        row.get(5)?,
        row.get(6)?,
        row.get(7)?,
        row.get(8)?,
        row.get(9)?,
        row.get(10)?,
        row.get(11)?,
        row.get(12)?,
        row.get(13)?,
        row.get(14)?,
        row.get(15)?,
        row.get(16)?,
        row.get(17)?,
    ))
}

fn decode_stored_trade(raw: RawTradeRow) -> Result<PumpTradeEvidenceWrite, StorageError> {
    let (
        provider,
        signature,
        ordinal,
        slot,
        observed_at_unix_ms,
        mint,
        quote_mint,
        user,
        is_buy,
        token_amount_raw,
        sol_amount_raw,
        quote_amount_raw,
        timestamp_unix_seconds,
        virtual_sol_reserves_raw,
        virtual_token_reserves_raw,
        real_sol_reserves_raw,
        real_token_reserves_raw,
        virtual_quote_reserves_raw,
        real_quote_reserves_raw,
        ix_name,
    ) = raw;

    let ordinal = u32::try_from(ordinal).map_err(|_| {
        StorageError::InvalidData("Pump trade ordinal was outside u32 range".to_owned())
    })?;
    let is_buy = match is_buy {
        0 => false,
        1 => true,
        other => {
            return Err(StorageError::InvalidData(format!(
                "Pump trade is_buy stored invalid value {other}"
            )))
        }
    };

    Ok(PumpTradeEvidenceWrite {
        provider: parse_provider_id(&provider)?,
        signature,
        ordinal,
        slot: parse_u64_text(&slot, "Pump trade slot")?,
        observed_at_unix_ms,
        mint,
        quote_mint,
        user,
        is_buy,
        token_amount_raw: parse_u64_text(&token_amount_raw, "Pump trade token_amount_raw")?,
        sol_amount_raw: parse_u64_text(&sol_amount_raw, "Pump trade sol_amount_raw")?,
        quote_amount_raw: parse_u64_text(&quote_amount_raw, "Pump trade quote_amount_raw")?,
        timestamp_unix_seconds,
        virtual_sol_reserves_raw: parse_u64_text(
            &virtual_sol_reserves_raw,
            "Pump trade virtual_sol_reserves_raw",
        )?,
        virtual_token_reserves_raw: parse_u64_text(
            &virtual_token_reserves_raw,
            "Pump trade virtual_token_reserves_raw",
        )?,
        real_sol_reserves_raw: parse_u64_text(
            &real_sol_reserves_raw,
            "Pump trade real_sol_reserves_raw",
        )?,
        real_token_reserves_raw: parse_u64_text(
            &real_token_reserves_raw,
            "Pump trade real_token_reserves_raw",
        )?,
        virtual_quote_reserves_raw: parse_u64_text(
            &virtual_quote_reserves_raw,
            "Pump trade virtual_quote_reserves_raw",
        )?,
        real_quote_reserves_raw: parse_u64_text(
            &real_quote_reserves_raw,
            "Pump trade real_quote_reserves_raw",
        )?,
        ix_name,
    })
}

fn decode_stored_fast_event(raw: RawFastEventRow) -> Result<StoredFastEvent, StorageError> {
    let (
        sequence,
        signature,
        ordinal,
        provider,
        slot,
        source_observed_at_unix_ms,
        occurred_at_unix_ms,
        observed_at_unix_ms,
        mint,
        quote_mint,
        venue,
        kind,
        actor,
        base_quantity,
        quote_quantity,
        price_quote,
        base_decimals,
        quote_decimals,
    ) = raw;

    let sequence = u64::try_from(sequence).map_err(|_| {
        StorageError::InvalidData("stored FastEvent sequence was not positive u64".to_owned())
    })?;
    let ordinal = u32::try_from(ordinal).map_err(|_| {
        StorageError::InvalidData("stored FastEvent ordinal was outside u32 range".to_owned())
    })?;
    let base_decimals = u8::try_from(base_decimals).map_err(|_| {
        StorageError::InvalidData("stored FastEvent base decimals were outside u8 range".to_owned())
    })?;
    let quote_decimals = u8::try_from(quote_decimals).map_err(|_| {
        StorageError::InvalidData("stored FastEvent quote decimals were outside u8 range".to_owned())
    })?;
    let id = FastEventId::new(signature, ordinal).map_err(|error| {
        StorageError::InvalidData(format!("stored FastEvent identity is invalid: {error}"))
    })?;
    let market = FastMarketKey::new(mint, quote_mint, parse_venue_id(&venue)?).map_err(|error| {
        StorageError::InvalidData(format!("stored FastEvent market is invalid: {error}"))
    })?;
    let event = FastEvent::new(
        id,
        sequence,
        parse_provider_id(&provider)?,
        market,
        parse_fast_event_kind(&kind)?,
        actor,
        parse_u64_text(&slot, "FastEvent slot")?,
        occurred_at_unix_ms,
        observed_at_unix_ms,
        base_quantity,
        quote_quantity,
        price_quote,
    )
    .map_err(|error| {
        StorageError::InvalidData(format!("stored FastEvent economics are invalid: {error}"))
    })?;

    Ok(StoredFastEvent {
        event,
        source_observed_at_unix_ms,
        base_decimals,
        quote_decimals,
    })
}

fn validate_trade_evidence(evidence: &PumpTradeEvidenceWrite) -> Result<(), StorageError> {
    validate_nonempty(&evidence.signature, "Pump trade signature")?;
    validate_nonempty(&evidence.mint, "Pump trade mint")?;
    validate_nonempty(&evidence.quote_mint, "Pump trade quote mint")?;
    validate_nonempty(&evidence.user, "Pump trade user")?;
    validate_nonempty(&evidence.ix_name, "Pump trade instruction name")?;

    if evidence.observed_at_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "Pump trade observation timestamp must be non-negative".to_owned(),
        ));
    }
    if evidence.timestamp_unix_seconds < 0 {
        return Err(StorageError::InvalidData(
            "Pump trade chain timestamp must be non-negative".to_owned(),
        ));
    }
    Ok(())
}

fn validate_pump_canonical_source(
    event: &FastEvent,
    source: &PumpTradeEvidenceWrite,
    base_decimals: u8,
    quote_decimals: u8,
) -> Result<(), StorageError> {
    let is_sol_quote = source.quote_mint == SYSTEM_SOL_MINT || source.quote_mint == WRAPPED_SOL_MINT;
    let expected_quote_mint = if is_sol_quote {
        WRAPPED_SOL_MINT
    } else {
        source.quote_mint.as_str()
    };
    let expected_quote_raw = if is_sol_quote {
        source.sol_amount_raw
    } else {
        source.quote_amount_raw
    };
    if source.token_amount_raw == 0 || expected_quote_raw == 0 {
        return Err(StorageError::InvalidData(format!(
            "FastEvent source Pump evidence '{}' ordinal {} has non-positive economics",
            source.signature, source.ordinal
        )));
    }

    let occurred_at_unix_ms = source
        .timestamp_unix_seconds
        .checked_mul(1_000)
        .ok_or_else(|| {
            StorageError::InvalidData(format!(
                "FastEvent source Pump timestamp overflow for '{}' ordinal {}",
                source.signature, source.ordinal
            ))
        })?;
    let base_scale = 10_f64.powi(i32::from(base_decimals));
    let quote_scale = 10_f64.powi(i32::from(quote_decimals));
    if !base_scale.is_finite()
        || base_scale <= 0.0
        || !quote_scale.is_finite()
        || quote_scale <= 0.0
    {
        return Err(StorageError::InvalidData(format!(
            "FastEvent decimal scale is invalid for '{}' ordinal {}",
            source.signature, source.ordinal
        )));
    }
    let base_quantity = source.token_amount_raw as f64 / base_scale;
    let quote_quantity = expected_quote_raw as f64 / quote_scale;
    let price_quote = quote_quantity / base_quantity;
    let expected_kind = if source.is_buy {
        FastEventKind::Buy
    } else {
        FastEventKind::Sell
    };

    if event.provider != source.provider
        || event.market.mint != source.mint
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
            "FastEvent payload does not match immutable Pump evidence '{}' ordinal {}",
            source.signature, source.ordinal
        )));
    }

    Ok(())
}

fn same_economic_event(
    stored: &PumpTradeEvidenceWrite,
    incoming: &PumpTradeEvidenceWrite,
) -> bool {
    stored.signature == incoming.signature
        && stored.ordinal == incoming.ordinal
        && stored.mint == incoming.mint
        && stored.quote_mint == incoming.quote_mint
        && stored.user == incoming.user
        && stored.is_buy == incoming.is_buy
        && stored.token_amount_raw == incoming.token_amount_raw
        && stored.sol_amount_raw == incoming.sol_amount_raw
        && stored.quote_amount_raw == incoming.quote_amount_raw
        && stored.timestamp_unix_seconds == incoming.timestamp_unix_seconds
        && stored.virtual_sol_reserves_raw == incoming.virtual_sol_reserves_raw
        && stored.virtual_token_reserves_raw == incoming.virtual_token_reserves_raw
        && stored.real_sol_reserves_raw == incoming.real_sol_reserves_raw
        && stored.real_token_reserves_raw == incoming.real_token_reserves_raw
        && stored.virtual_quote_reserves_raw == incoming.virtual_quote_reserves_raw
        && stored.real_quote_reserves_raw == incoming.real_quote_reserves_raw
        && stored.ix_name == incoming.ix_name
}

fn same_canonical_event(
    stored: &StoredFastEvent,
    incoming: &FastEvent,
    source_observed_at_unix_ms: i64,
    base_decimals: u8,
    quote_decimals: u8,
) -> bool {
    let existing = &stored.event;
    existing.id == incoming.id
        && existing.provider == incoming.provider
        && existing.market == incoming.market
        && existing.kind == incoming.kind
        && existing.actor == incoming.actor
        && existing.slot == incoming.slot
        && existing.occurred_at_unix_ms == incoming.occurred_at_unix_ms
        && existing.observed_at_unix_ms == incoming.observed_at_unix_ms
        && existing.base_quantity == incoming.base_quantity
        && existing.quote_quantity == incoming.quote_quantity
        && existing.price_quote == incoming.price_quote
        && stored.source_observed_at_unix_ms == source_observed_at_unix_ms
        && stored.base_decimals == base_decimals
        && stored.quote_decimals == quote_decimals
}

fn fast_event_kind_str(kind: FastEventKind) -> &'static str {
    match kind {
        FastEventKind::Buy => "buy",
        FastEventKind::Sell => "sell",
    }
}

fn parse_fast_event_kind(value: &str) -> Result<FastEventKind, StorageError> {
    match value {
        "buy" => Ok(FastEventKind::Buy),
        "sell" => Ok(FastEventKind::Sell),
        other => Err(StorageError::InvalidData(format!(
            "unknown stored FastEvent kind '{other}'"
        ))),
    }
}

fn parse_venue_id(value: &str) -> Result<VenueId, StorageError> {
    match value {
        "pump_fun_bonding_curve" => Ok(VenueId::PumpFunBondingCurve),
        "pump_swap" => Ok(VenueId::PumpSwap),
        "meteora_dlmm" => Ok(VenueId::MeteoraDlmm),
        "meteora_damm_v2" => Ok(VenueId::MeteoraDammV2),
        "other_solana" => Ok(VenueId::OtherSolana),
        other => Err(StorageError::InvalidData(format!(
            "unknown venue id '{other}' in FastEvent storage"
        ))),
    }
}

fn validate_nonempty(value: &str, field: &str) -> Result<(), StorageError> {
    if value.trim().is_empty() {
        return Err(StorageError::InvalidData(format!(
            "{field} must not be empty"
        )));
    }
    Ok(())
}

fn parse_u64_text(value: &str, field: &str) -> Result<u64, StorageError> {
    value.parse::<u64>().map_err(|error| {
        StorageError::InvalidData(format!("{field} is not u64 decimal text: {error}"))
    })
}

fn parse_provider_id(value: &str) -> Result<ProviderId, StorageError> {
    match value {
        "dexscreener" => Ok(ProviderId::DexScreener),
        "helius" => Ok(ProviderId::Helius),
        "alchemy" => Ok(ProviderId::Alchemy),
        "chainstack" => Ok(ProviderId::Chainstack),
        "solana_public" => Ok(ProviderId::SolanaPublic),
        "jupiter" => Ok(ProviderId::Jupiter),
        "meteora" => Ok(ProviderId::Meteora),
        other => Err(StorageError::InvalidData(format!(
            "unknown provider id '{other}' in Fast Lane storage"
        ))),
    }
}
