use rusqlite::params;
use shreks_core::ProviderId;

use crate::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
    StorageError,
};

const SYSTEM_SOL_MINT: &str = "11111111111111111111111111111111";
const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EvidenceWriteOutcome {
    Inserted,
    Duplicate,
    QuarantinedConflict,
}

impl ShreksDb {
    pub fn record_pump_trade_evidence_or_quarantine(
        &self,
        evidence: &PumpTradeEvidenceWrite,
    ) -> Result<EvidenceWriteOutcome, StorageError> {
        validate_pump_trade_evidence(evidence)?;

        match self.record_pump_trade_evidence(evidence) {
            Ok(true) => Ok(EvidenceWriteOutcome::Inserted),
            Ok(false) => Ok(EvidenceWriteOutcome::Duplicate),
            Err(error @ StorageError::InvalidData(_)) => {
                let existing = self
                    .pump_trade_evidence_for_signature(&evidence.signature)?
                    .into_iter()
                    .find(|stored| stored.ordinal == evidence.ordinal);
                let Some(existing) = existing else {
                    return Err(error);
                };
                if same_pump_economics(&existing, evidence) {
                    return Err(error);
                }

                self.connection.execute(
                    r#"INSERT OR IGNORE INTO pump_trade_evidence_conflicts (
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
                Ok(EvidenceWriteOutcome::QuarantinedConflict)
            }
            Err(error) => Err(error),
        }
    }

    pub fn record_pump_swap_trade_evidence_or_quarantine(
        &self,
        evidence: &PumpSwapTradeEvidenceWrite,
    ) -> Result<EvidenceWriteOutcome, StorageError> {
        validate_pumpswap_trade_evidence(evidence)?;

        match self.record_pump_swap_trade_evidence(evidence) {
            Ok(true) => Ok(EvidenceWriteOutcome::Inserted),
            Ok(false) => Ok(EvidenceWriteOutcome::Duplicate),
            Err(error @ StorageError::InvalidData(_)) => {
                let existing = self
                    .pump_swap_trade_evidence_for_signature(&evidence.signature)?
                    .into_iter()
                    .find(|stored| stored.ordinal == evidence.ordinal);
                let Some(existing) = existing else {
                    return Err(error);
                };
                if same_pumpswap_economics(&existing, evidence) {
                    return Err(error);
                }

                self.connection.execute(
                    r#"INSERT OR IGNORE INTO pump_swap_trade_evidence_conflicts (
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
                Ok(EvidenceWriteOutcome::QuarantinedConflict)
            }
            Err(error) => Err(error),
        }
    }

    pub fn pump_quarantined_conflict_count(&self) -> Result<u64, StorageError> {
        count_rows(&self.connection, "pump_trade_evidence_conflicts")
    }

    pub fn pumpswap_quarantined_conflict_count(&self) -> Result<u64, StorageError> {
        count_rows(&self.connection, "pump_swap_trade_evidence_conflicts")
    }

    /// Return the oldest conflict-free Pump rows whose normalization metadata
    /// is currently available. Unresolved rows remain durable in the generic
    /// pending backlog and become eligible automatically when metadata arrives.
    pub fn pending_unambiguous_pump_trade_evidence(
        &self,
        limit: usize,
    ) -> Result<Vec<PumpTradeEvidenceWrite>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = sqlite_limit(limit, "Pump unambiguous pending-trade limit")?;
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
                 AND NOT EXISTS (
                     SELECT 1
                     FROM pump_trade_evidence_conflicts AS c
                     WHERE c.signature = p.signature AND c.ordinal = p.ordinal
                 )
                 AND EXISTS (
                     SELECT 1
                     FROM token_candidates AS base_candidate
                     JOIN token_mint_states AS base_state
                       ON base_state.candidate_id = base_candidate.id
                     WHERE base_candidate.mint = p.mint
                 )
                 AND (
                     p.quote_mint = ?1
                     OR p.quote_mint = ?2
                     OR EXISTS (
                         SELECT 1
                         FROM token_candidates AS quote_candidate
                         JOIN token_mint_states AS quote_state
                           ON quote_state.candidate_id = quote_candidate.id
                         WHERE quote_candidate.mint = p.quote_mint
                     )
                 )
               ORDER BY p.observed_at_unix_ms ASC, p.signature ASC, p.ordinal ASC
               LIMIT ?3"#,
        )?;
        let rows = statement
            .query_map(params![SYSTEM_SOL_MINT, WRAPPED_SOL_MINT, limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, i64>(4)?,
                    row.get::<_, String>(5)?,
                    row.get::<_, String>(6)?,
                    row.get::<_, String>(7)?,
                    row.get::<_, i64>(8)?,
                    row.get::<_, String>(9)?,
                    row.get::<_, String>(10)?,
                    row.get::<_, String>(11)?,
                    row.get::<_, i64>(12)?,
                    row.get::<_, String>(13)?,
                    row.get::<_, String>(14)?,
                    row.get::<_, String>(15)?,
                    row.get::<_, String>(16)?,
                    row.get::<_, String>(17)?,
                    row.get::<_, String>(18)?,
                    row.get::<_, String>(19)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        rows.into_iter().map(decode_pump_row).collect()
    }

    pub fn pending_unambiguous_pump_swap_trade_evidence(
        &self,
        limit: usize,
    ) -> Result<Vec<PumpSwapTradeEvidenceWrite>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = sqlite_limit(limit, "PumpSwap unambiguous pending-trade limit")?;
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
                 AND NOT EXISTS (
                     SELECT 1
                     FROM pump_swap_trade_evidence_conflicts AS c
                     WHERE c.signature = p.signature AND c.ordinal = p.ordinal
                 )
               ORDER BY p.observed_at_unix_ms ASC, p.signature ASC, p.log_index ASC
               LIMIT ?1"#,
        )?;
        let rows = statement
            .query_map([limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i64>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, i64>(5)?,
                    row.get::<_, String>(6)?,
                    row.get::<_, String>(7)?,
                    row.get::<_, i64>(8)?,
                    row.get::<_, String>(9)?,
                    row.get::<_, String>(10)?,
                    row.get::<_, String>(11)?,
                    row.get::<_, i64>(12)?,
                    row.get::<_, String>(13)?,
                    row.get::<_, String>(14)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(decode_pumpswap_row).collect()
    }
}

fn validate_pump_trade_evidence(evidence: &PumpTradeEvidenceWrite) -> Result<(), StorageError> {
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

fn validate_pumpswap_trade_evidence(
    evidence: &PumpSwapTradeEvidenceWrite,
) -> Result<(), StorageError> {
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
    if evidence.base_amount_raw == 0
        || evidence.quote_amount_raw == 0
        || evidence.user_quote_amount_raw == 0
    {
        return Err(StorageError::InvalidData(
            "PumpSwap executed quantities must be non-zero".to_owned(),
        ));
    }
    Ok(())
}

fn same_pump_economics(stored: &PumpTradeEvidenceWrite, incoming: &PumpTradeEvidenceWrite) -> bool {
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

fn same_pumpswap_economics(
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

fn count_rows(connection: &rusqlite::Connection, table: &str) -> Result<u64, StorageError> {
    let sql = match table {
        "pump_trade_evidence_conflicts" => "SELECT COUNT(*) FROM pump_trade_evidence_conflicts",
        "pump_swap_trade_evidence_conflicts" => {
            "SELECT COUNT(*) FROM pump_swap_trade_evidence_conflicts"
        }
        _ => {
            return Err(StorageError::InvalidData(
                "unsupported conflict count table".to_owned(),
            ))
        }
    };
    let count: i64 = connection.query_row(sql, [], |row| row.get(0))?;
    u64::try_from(count)
        .map_err(|_| StorageError::InvalidData("conflict count was negative".to_owned()))
}

fn sqlite_limit(limit: usize, field: &str) -> Result<i64, StorageError> {
    i64::try_from(limit).map_err(|_| StorageError::InvalidData(format!("{field} exceeds i64")))
}

fn validate_nonempty(value: &str, field: &str) -> Result<(), StorageError> {
    if value.trim().is_empty() {
        return Err(StorageError::InvalidData(format!("{field} must not be empty")));
    }
    Ok(())
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
            "unknown provider id '{other}' in conflict quarantine storage"
        ))),
    }
}

fn parse_u64(value: &str, field: &str) -> Result<u64, StorageError> {
    value.parse::<u64>().map_err(|error| {
        StorageError::InvalidData(format!("{field} is not u64 decimal text: {error}"))
    })
}

#[allow(clippy::type_complexity)]
fn decode_pump_row(
    raw: (
        String, String, i64, String, i64,
        String, String, String, i64,
        String, String, String, i64,
        String, String, String, String, String, String, String,
    ),
) -> Result<PumpTradeEvidenceWrite, StorageError> {
    let (
        provider, signature, ordinal, slot, observed_at_unix_ms,
        mint, quote_mint, user, is_buy,
        token_amount_raw, sol_amount_raw, quote_amount_raw, timestamp_unix_seconds,
        virtual_sol_reserves_raw, virtual_token_reserves_raw,
        real_sol_reserves_raw, real_token_reserves_raw,
        virtual_quote_reserves_raw, real_quote_reserves_raw, ix_name,
    ) = raw;
    Ok(PumpTradeEvidenceWrite {
        provider: parse_provider(&provider)?,
        signature,
        ordinal: u32::try_from(ordinal).map_err(|_| {
            StorageError::InvalidData("Pump trade ordinal was outside u32 range".to_owned())
        })?,
        slot: parse_u64(&slot, "Pump trade slot")?,
        observed_at_unix_ms,
        mint,
        quote_mint,
        user,
        is_buy: match is_buy {
            0 => false,
            1 => true,
            other => {
                return Err(StorageError::InvalidData(format!(
                    "Pump trade is_buy stored invalid value {other}"
                )))
            }
        },
        token_amount_raw: parse_u64(&token_amount_raw, "Pump trade token_amount_raw")?,
        sol_amount_raw: parse_u64(&sol_amount_raw, "Pump trade sol_amount_raw")?,
        quote_amount_raw: parse_u64(&quote_amount_raw, "Pump trade quote_amount_raw")?,
        timestamp_unix_seconds,
        virtual_sol_reserves_raw: parse_u64(
            &virtual_sol_reserves_raw,
            "Pump trade virtual_sol_reserves_raw",
        )?,
        virtual_token_reserves_raw: parse_u64(
            &virtual_token_reserves_raw,
            "Pump trade virtual_token_reserves_raw",
        )?,
        real_sol_reserves_raw: parse_u64(
            &real_sol_reserves_raw,
            "Pump trade real_sol_reserves_raw",
        )?,
        real_token_reserves_raw: parse_u64(
            &real_token_reserves_raw,
            "Pump trade real_token_reserves_raw",
        )?,
        virtual_quote_reserves_raw: parse_u64(
            &virtual_quote_reserves_raw,
            "Pump trade virtual_quote_reserves_raw",
        )?,
        real_quote_reserves_raw: parse_u64(
            &real_quote_reserves_raw,
            "Pump trade real_quote_reserves_raw",
        )?,
        ix_name,
    })
}

#[allow(clippy::type_complexity)]
fn decode_pumpswap_row(
    raw: (
        String, String, i64, i64, String, i64,
        String, String, i64,
        String, String, String,
        i64, String, String,
    ),
) -> Result<PumpSwapTradeEvidenceWrite, StorageError> {
    let (
        provider, signature, ordinal, log_index, slot, observed_at_unix_ms,
        pool, user, is_buy,
        base_amount_raw, quote_amount_raw, user_quote_amount_raw,
        timestamp_unix_seconds, pool_base_reserves_raw, pool_quote_reserves_raw,
    ) = raw;
    Ok(PumpSwapTradeEvidenceWrite {
        provider: parse_provider(&provider)?,
        signature,
        ordinal: u32::try_from(ordinal).map_err(|_| {
            StorageError::InvalidData("PumpSwap ordinal was outside u32 range".to_owned())
        })?,
        log_index: u32::try_from(log_index).map_err(|_| {
            StorageError::InvalidData("PumpSwap log index was outside u32 range".to_owned())
        })?,
        slot: parse_u64(&slot, "PumpSwap slot")?,
        observed_at_unix_ms,
        pool,
        user,
        is_buy: match is_buy {
            0 => false,
            1 => true,
            other => {
                return Err(StorageError::InvalidData(format!(
                    "PumpSwap is_buy stored invalid value {other}"
                )))
            }
        },
        base_amount_raw: parse_u64(&base_amount_raw, "PumpSwap base_amount_raw")?,
        quote_amount_raw: parse_u64(&quote_amount_raw, "PumpSwap quote_amount_raw")?,
        user_quote_amount_raw: parse_u64(
            &user_quote_amount_raw,
            "PumpSwap user_quote_amount_raw",
        )?,
        timestamp_unix_seconds,
        pool_base_reserves_raw: parse_u64(
            &pool_base_reserves_raw,
            "PumpSwap pool_base_reserves_raw",
        )?,
        pool_quote_reserves_raw: parse_u64(
            &pool_quote_reserves_raw,
            "PumpSwap pool_quote_reserves_raw",
        )?,
    })
}
