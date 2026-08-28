use rusqlite::{params, OptionalExtension};
use shreks_core::ProviderId;

use crate::{ShreksDb, StorageError};

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

impl ShreksDb {
    /// Persist one immutable Pump economic event.
    ///
    /// `(signature, ordinal)` is the canonical identity. Replaying the same
    /// economics is idempotent even when the later local observation timestamp
    /// differs; the first observation time remains authoritative. A conflicting
    /// payload for an existing identity fails closed instead of overwriting
    /// training evidence.
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

fn same_economic_event(
    stored: &PumpTradeEvidenceWrite,
    incoming: &PumpTradeEvidenceWrite,
) -> bool {
    stored.provider == incoming.provider
        && stored.signature == incoming.signature
        && stored.ordinal == incoming.ordinal
        && stored.slot == incoming.slot
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
        "jupiter" => Ok(ProviderId::Jupiter),
        "meteora" => Ok(ProviderId::Meteora),
        other => Err(StorageError::InvalidData(format!(
            "unknown provider id '{other}' in Pump trade evidence"
        ))),
    }
}
