use rusqlite::{params, Connection, OptionalExtension};
use shreks_core::{LifecycleEventKind, ProviderId, TokenLifecycleEvent, VenueId};

use crate::{PumpSignalStatus, ShreksDb, StorageError};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpMigrationSignalRecord {
    pub signature: String,
    pub slot: u64,
    pub observed_at_unix_ms: i64,
    pub status: PumpSignalStatus,
    pub attempt_count: u64,
    pub last_attempt_at_unix_ms: Option<i64>,
    pub last_error: Option<String>,
}

type RawLifecycleRow = (
    String,
    String,
    String,
    String,
    String,
    String,
    String,
    String,
    String,
    i64,
    Option<i64>,
);

impl ShreksDb {
    pub fn record_pump_migration_signal(
        &self,
        signature: &str,
        slot: u64,
        observed_at_unix_ms: i64,
    ) -> Result<(), StorageError> {
        validate_signature(signature)?;
        validate_timestamp(observed_at_unix_ms, "Pump migration observed_at_unix_ms")?;
        self.connection.execute(
            r#"INSERT INTO pump_migration_signals (
                   signature, slot, observed_at_unix_ms, status
               ) VALUES (?1, ?2, ?3, 'pending')
               ON CONFLICT(signature) DO UPDATE SET
                   observed_at_unix_ms = MIN(
                       pump_migration_signals.observed_at_unix_ms,
                       excluded.observed_at_unix_ms
                   )"#,
            params![signature, slot.to_string(), observed_at_unix_ms],
        )?;
        Ok(())
    }

    pub fn pending_pump_migration_signals(
        &self,
        limit: usize,
    ) -> Result<Vec<PumpMigrationSignalRecord>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("Pump migration pending-signal limit exceeds i64".to_owned())
        })?;
        let mut statement = self.connection.prepare(
            r#"SELECT signature, slot, observed_at_unix_ms, status, attempt_count,
                      last_attempt_at_unix_ms, last_error
               FROM pump_migration_signals
               WHERE status = 'pending'
               ORDER BY observed_at_unix_ms ASC, signature ASC
               LIMIT ?1"#,
        )?;
        let rows = statement
            .query_map([limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, i64>(4)?,
                    row.get::<_, Option<i64>>(5)?,
                    row.get::<_, Option<String>>(6)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter()
            .map(|(signature, slot, observed, status, attempts, last_attempt, last_error)| {
                Ok(PumpMigrationSignalRecord {
                    signature,
                    slot: parse_u64_text(&slot, "Pump migration signal slot")?,
                    observed_at_unix_ms: observed,
                    status: parse_status(&status)?,
                    attempt_count: u64::try_from(attempts).map_err(|_| {
                        StorageError::InvalidData(
                            "Pump migration attempt count was negative".to_owned(),
                        )
                    })?,
                    last_attempt_at_unix_ms: last_attempt,
                    last_error,
                })
            })
            .collect()
    }

    pub fn record_pump_migration_attempt(
        &self,
        signature: &str,
        attempted_at_unix_ms: i64,
        error: Option<&str>,
    ) -> Result<(), StorageError> {
        validate_signature(signature)?;
        validate_timestamp(attempted_at_unix_ms, "Pump migration attempted_at_unix_ms")?;
        let changed = self.connection.execute(
            r#"UPDATE pump_migration_signals
               SET attempt_count = attempt_count + 1,
                   last_attempt_at_unix_ms = ?2,
                   last_error = ?3
               WHERE signature = ?1 AND status = 'pending'"#,
            params![signature, attempted_at_unix_ms, error],
        )?;
        ensure_pending_changed(changed, signature, "record migration attempt")
    }

    pub fn complete_pump_migration(
        &self,
        signature: &str,
        attempted_at_unix_ms: i64,
        events: &[TokenLifecycleEvent],
    ) -> Result<usize, StorageError> {
        validate_signature(signature)?;
        validate_timestamp(attempted_at_unix_ms, "Pump migration attempted_at_unix_ms")?;
        if events.is_empty() {
            return Err(StorageError::InvalidData(
                "verified Pump migration must contain at least one lifecycle event".to_owned(),
            ));
        }
        for event in events {
            validate_event(signature, event)?;
        }

        let transaction = self.connection.unchecked_transaction()?;
        let status = transaction
            .query_row(
                "SELECT status FROM pump_migration_signals WHERE signature = ?1",
                [signature],
                |row| row.get::<_, String>(0),
            )
            .optional()?;
        let Some(status) = status else {
            return Err(StorageError::InvalidData(format!(
                "cannot complete Pump migration '{signature}': signal is missing"
            )));
        };

        match status.as_str() {
            "verified" => {
                let existing = lifecycle_events_for_signature(&transaction, signature)?;
                if canonical_events(existing) == canonical_events(events.to_vec()) {
                    return Ok(0);
                }
                return Err(StorageError::InvalidData(format!(
                    "cannot mutate verified Pump migration '{signature}' lifecycle truth"
                )));
            }
            "rejected" => {
                return Err(StorageError::InvalidData(format!(
                    "cannot complete rejected Pump migration '{signature}'"
                )));
            }
            "pending" => {}
            other => {
                return Err(StorageError::InvalidData(format!(
                    "unknown Pump migration status '{other}'"
                )));
            }
        }

        for event in events {
            transaction.execute(
                r#"INSERT INTO token_lifecycle_events (
                       event_type, provider, mint, quote_mint, from_venue, to_venue,
                       pool_address, signature, slot, detected_at_unix_ms, occurred_at_unix_ms
                   ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)"#,
                params![
                    event.kind.as_str(),
                    event.provider.as_str(),
                    event.mint,
                    event.quote_mint,
                    event.from_venue.as_str(),
                    event.to_venue.as_str(),
                    event.pool_address,
                    event.signature,
                    event.slot.to_string(),
                    event.detected_at_unix_ms,
                    event.occurred_at_unix_ms,
                ],
            )?;
        }

        let changed = transaction.execute(
            r#"UPDATE pump_migration_signals
               SET status = 'verified',
                   attempt_count = attempt_count + 1,
                   last_attempt_at_unix_ms = ?2,
                   last_error = NULL
               WHERE signature = ?1 AND status = 'pending'"#,
            params![signature, attempted_at_unix_ms],
        )?;
        ensure_pending_changed(changed, signature, "complete migration")?;
        transaction.commit()?;
        Ok(events.len())
    }

    pub fn mark_pump_migration_rejected(
        &self,
        signature: &str,
        attempted_at_unix_ms: i64,
        reason: &str,
    ) -> Result<(), StorageError> {
        validate_signature(signature)?;
        validate_timestamp(attempted_at_unix_ms, "Pump migration attempted_at_unix_ms")?;
        if reason.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "Pump migration rejection reason must not be empty".to_owned(),
            ));
        }
        let changed = self.connection.execute(
            r#"UPDATE pump_migration_signals
               SET status = 'rejected',
                   attempt_count = attempt_count + 1,
                   last_attempt_at_unix_ms = ?2,
                   last_error = ?3
               WHERE signature = ?1 AND status = 'pending'"#,
            params![signature, attempted_at_unix_ms, reason],
        )?;
        ensure_pending_changed(changed, signature, "reject migration")
    }

    pub fn lifecycle_events_for_mint(
        &self,
        mint: &str,
    ) -> Result<Vec<TokenLifecycleEvent>, StorageError> {
        if mint.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "lifecycle-event mint must not be empty".to_owned(),
            ));
        }
        query_lifecycle_events(
            &self.connection,
            r#"SELECT event_type, provider, mint, quote_mint, from_venue, to_venue,
                      pool_address, signature, slot, detected_at_unix_ms, occurred_at_unix_ms
               FROM token_lifecycle_events
               WHERE mint = ?1
               ORDER BY detected_at_unix_ms ASC, signature ASC, pool_address ASC"#,
            mint,
        )
    }
}

fn lifecycle_events_for_signature(
    connection: &Connection,
    signature: &str,
) -> Result<Vec<TokenLifecycleEvent>, StorageError> {
    query_lifecycle_events(
        connection,
        r#"SELECT event_type, provider, mint, quote_mint, from_venue, to_venue,
                  pool_address, signature, slot, detected_at_unix_ms, occurred_at_unix_ms
           FROM token_lifecycle_events
           WHERE signature = ?1
           ORDER BY detected_at_unix_ms ASC, signature ASC, pool_address ASC, mint ASC"#,
        signature,
    )
}

fn query_lifecycle_events(
    connection: &Connection,
    sql: &str,
    value: &str,
) -> Result<Vec<TokenLifecycleEvent>, StorageError> {
    let mut statement = connection.prepare(sql)?;
    let rows = statement
        .query_map([value], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, String>(6)?,
                row.get::<_, String>(7)?,
                row.get::<_, String>(8)?,
                row.get::<_, i64>(9)?,
                row.get::<_, Option<i64>>(10)?,
            ))
        })?
        .collect::<Result<Vec<RawLifecycleRow>, _>>()?;
    rows.into_iter().map(decode_event).collect()
}

fn decode_event(row: RawLifecycleRow) -> Result<TokenLifecycleEvent, StorageError> {
    let (kind, provider, mint, quote, from, to, pool, signature, slot, detected, occurred) = row;
    Ok(TokenLifecycleEvent {
        kind: parse_kind(&kind)?,
        provider: parse_provider(&provider)?,
        mint,
        quote_mint: quote,
        from_venue: parse_venue(&from)?,
        to_venue: parse_venue(&to)?,
        pool_address: pool,
        signature,
        slot: parse_u64_text(&slot, "lifecycle-event slot")?,
        detected_at_unix_ms: detected,
        occurred_at_unix_ms: occurred,
    })
}

fn canonical_events(mut events: Vec<TokenLifecycleEvent>) -> Vec<TokenLifecycleEvent> {
    events.sort_by(|left, right| {
        (
            left.detected_at_unix_ms,
            left.signature.as_str(),
            left.pool_address.as_str(),
            left.mint.as_str(),
            left.quote_mint.as_str(),
            left.kind.as_str(),
            left.provider.as_str(),
            left.from_venue.as_str(),
            left.to_venue.as_str(),
            left.slot,
            left.occurred_at_unix_ms,
        )
            .cmp(&(
                right.detected_at_unix_ms,
                right.signature.as_str(),
                right.pool_address.as_str(),
                right.mint.as_str(),
                right.quote_mint.as_str(),
                right.kind.as_str(),
                right.provider.as_str(),
                right.from_venue.as_str(),
                right.to_venue.as_str(),
                right.slot,
                right.occurred_at_unix_ms,
            ))
    });
    events
}

fn validate_event(signature: &str, event: &TokenLifecycleEvent) -> Result<(), StorageError> {
    if event.kind != LifecycleEventKind::PumpGraduation {
        return Err(StorageError::InvalidData(
            "unsupported lifecycle event kind".to_owned(),
        ));
    }
    if event.signature != signature {
        return Err(StorageError::InvalidData(format!(
            "lifecycle event signature must equal Pump migration signal '{signature}'"
        )));
    }
    for (value, field) in [
        (event.mint.as_str(), "mint"),
        (event.quote_mint.as_str(), "quote mint"),
        (event.pool_address.as_str(), "pool address"),
    ] {
        if value.trim().is_empty() {
            return Err(StorageError::InvalidData(format!(
                "Pump graduation lifecycle event {field} must not be empty"
            )));
        }
    }
    if event.from_venue != VenueId::PumpFunBondingCurve || event.to_venue != VenueId::PumpSwap {
        return Err(StorageError::InvalidData(
            "Pump graduation lifecycle event must transition Pump.fun bonding curve -> PumpSwap"
                .to_owned(),
        ));
    }
    validate_timestamp(event.detected_at_unix_ms, "lifecycle detected_at_unix_ms")?;
    if let Some(value) = event.occurred_at_unix_ms {
        validate_timestamp(value, "lifecycle occurred_at_unix_ms")?;
    }
    Ok(())
}

fn validate_signature(signature: &str) -> Result<(), StorageError> {
    if signature.trim().is_empty() {
        return Err(StorageError::InvalidData(
            "Pump migration signature must not be empty".to_owned(),
        ));
    }
    Ok(())
}

fn validate_timestamp(value: i64, field: &str) -> Result<(), StorageError> {
    if value < 0 {
        return Err(StorageError::InvalidData(format!("{field} must not be negative")));
    }
    Ok(())
}

fn ensure_pending_changed(
    changed: usize,
    signature: &str,
    operation: &str,
) -> Result<(), StorageError> {
    if changed == 0 {
        return Err(StorageError::InvalidData(format!(
            "cannot {operation} Pump migration '{signature}': signal is missing or no longer pending"
        )));
    }
    Ok(())
}

fn parse_u64_text(value: &str, field: &str) -> Result<u64, StorageError> {
    value.parse::<u64>().map_err(|error| {
        StorageError::InvalidData(format!("{field} is not u64 decimal text: {error}"))
    })
}

fn parse_status(value: &str) -> Result<PumpSignalStatus, StorageError> {
    match value {
        "pending" => Ok(PumpSignalStatus::Pending),
        "verified" => Ok(PumpSignalStatus::Verified),
        "rejected" => Ok(PumpSignalStatus::Rejected),
        other => Err(StorageError::InvalidData(format!(
            "unknown Pump migration status '{other}'"
        ))),
    }
}

fn parse_kind(value: &str) -> Result<LifecycleEventKind, StorageError> {
    match value {
        "pump_graduation" => Ok(LifecycleEventKind::PumpGraduation),
        other => Err(StorageError::InvalidData(format!(
            "unknown lifecycle event type '{other}'"
        ))),
    }
}

fn parse_provider(value: &str) -> Result<ProviderId, StorageError> {
    match value {
        "dexscreener" => Ok(ProviderId::DexScreener),
        "helius" => Ok(ProviderId::Helius),
        "jupiter" => Ok(ProviderId::Jupiter),
        "meteora" => Ok(ProviderId::Meteora),
        other => Err(StorageError::InvalidData(format!(
            "unknown lifecycle provider '{other}'"
        ))),
    }
}

fn parse_venue(value: &str) -> Result<VenueId, StorageError> {
    match value {
        "pump_fun_bonding_curve" => Ok(VenueId::PumpFunBondingCurve),
        "pump_swap" => Ok(VenueId::PumpSwap),
        "meteora_dlmm" => Ok(VenueId::MeteoraDlmm),
        "meteora_damm_v2" => Ok(VenueId::MeteoraDammV2),
        "other_solana" => Ok(VenueId::OtherSolana),
        other => Err(StorageError::InvalidData(format!(
            "unknown lifecycle venue '{other}'"
        ))),
    }
}
