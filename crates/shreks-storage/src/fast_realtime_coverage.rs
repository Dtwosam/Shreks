use rusqlite::{params, OptionalExtension};
use shreks_core::ProviderId;

use crate::{fast_baseline_hydration::parse_provider, ShreksDb, StorageError};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FastRealtimeCoverageSession {
    pub session_id: u64,
    pub provider: ProviderId,
    pub process_session_sequence: u64,
    pub first_notification_observed_at_unix_ms: i64,
    pub last_notification_observed_at_unix_ms: i64,
    pub first_notification_slot: u64,
    pub last_notification_slot: u64,
    pub first_notification_signature: String,
    pub last_notification_signature: String,
    pub notification_count: u64,
}

impl ShreksDb {
    pub fn begin_fast_realtime_coverage_session(
        &self,
        provider: ProviderId,
        process_session_sequence: u64,
        observed_at_unix_ms: i64,
        slot: u64,
        signature: &str,
    ) -> Result<FastRealtimeCoverageSession, StorageError> {
        validate_sample(
            process_session_sequence,
            observed_at_unix_ms,
            signature,
        )?;
        let process_session_sequence =
            u64_to_i64(process_session_sequence, "coverage process session sequence")?;

        self.connection.execute(
            r#"INSERT INTO fast_realtime_coverage_sessions (
                   provider,
                   process_session_sequence,
                   first_notification_observed_at_unix_ms,
                   last_notification_observed_at_unix_ms,
                   first_notification_slot,
                   last_notification_slot,
                   first_notification_signature,
                   last_notification_signature,
                   notification_count
               ) VALUES (?1, ?2, ?3, ?3, ?4, ?4, ?5, ?5, 1)"#,
            params![
                provider.as_str(),
                process_session_sequence,
                observed_at_unix_ms,
                slot.to_string(),
                signature,
            ],
        )?;

        let session_id = i64_to_u64(
            self.connection.last_insert_rowid(),
            "coverage session id",
        )?;
        self.fast_realtime_coverage_session(session_id)?
            .ok_or_else(|| {
                StorageError::InvalidData(
                    "new realtime coverage session disappeared after insert".to_owned(),
                )
            })
    }

    pub fn extend_fast_realtime_coverage_session(
        &self,
        session_id: u64,
        provider: ProviderId,
        process_session_sequence: u64,
        observed_at_unix_ms: i64,
        slot: u64,
        signature: &str,
    ) -> Result<FastRealtimeCoverageSession, StorageError> {
        validate_sample(
            process_session_sequence,
            observed_at_unix_ms,
            signature,
        )?;
        let existing = self
            .fast_realtime_coverage_session(session_id)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "realtime coverage session {session_id} does not exist"
                ))
            })?;
        if existing.provider != provider
            || existing.process_session_sequence != process_session_sequence
        {
            return Err(StorageError::InvalidData(
                "realtime coverage session identity changed during extension".to_owned(),
            ));
        }
        if observed_at_unix_ms < existing.last_notification_observed_at_unix_ms {
            return Err(StorageError::InvalidData(
                "realtime coverage notification time moved backward".to_owned(),
            ));
        }
        if existing.notification_count == u64::MAX {
            return Err(StorageError::InvalidData(
                "realtime coverage notification count overflowed".to_owned(),
            ));
        }

        let changed = self.connection.execute(
            r#"UPDATE fast_realtime_coverage_sessions
               SET last_notification_observed_at_unix_ms = ?2,
                   last_notification_slot = ?3,
                   last_notification_signature = ?4,
                   notification_count = notification_count + 1
               WHERE session_id = ?1"#,
            params![
                u64_to_i64(session_id, "coverage session id")?,
                observed_at_unix_ms,
                slot.to_string(),
                signature,
            ],
        )?;
        if changed != 1 {
            return Err(StorageError::InvalidData(format!(
                "realtime coverage session {session_id} disappeared during extension"
            )));
        }

        self.fast_realtime_coverage_session(session_id)?
            .ok_or_else(|| {
                StorageError::InvalidData(
                    "realtime coverage session disappeared after extension".to_owned(),
                )
            })
    }

    pub fn fast_realtime_coverage_sessions(
        &self,
    ) -> Result<Vec<FastRealtimeCoverageSession>, StorageError> {
        let mut statement = self.connection.prepare(
            r#"SELECT
                   session_id,
                   provider,
                   process_session_sequence,
                   first_notification_observed_at_unix_ms,
                   last_notification_observed_at_unix_ms,
                   first_notification_slot,
                   last_notification_slot,
                   first_notification_signature,
                   last_notification_signature,
                   notification_count
               FROM fast_realtime_coverage_sessions
               ORDER BY session_id ASC"#,
        )?;
        let rows = statement
            .query_map([], decode_session)?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(validate_decoded_session).collect()
    }

    fn fast_realtime_coverage_session(
        &self,
        session_id: u64,
    ) -> Result<Option<FastRealtimeCoverageSession>, StorageError> {
        let raw = self
            .connection
            .query_row(
                r#"SELECT
                       session_id,
                       provider,
                       process_session_sequence,
                       first_notification_observed_at_unix_ms,
                       last_notification_observed_at_unix_ms,
                       first_notification_slot,
                       last_notification_slot,
                       first_notification_signature,
                       last_notification_signature,
                       notification_count
                   FROM fast_realtime_coverage_sessions
                   WHERE session_id = ?1"#,
                [u64_to_i64(session_id, "coverage session id")?],
                decode_session,
            )
            .optional()?;
        raw.map(validate_decoded_session).transpose()
    }
}

type RawSession = (
    i64,
    String,
    i64,
    i64,
    i64,
    String,
    String,
    String,
    String,
    i64,
);

fn decode_session(row: &rusqlite::Row<'_>) -> rusqlite::Result<RawSession> {
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
    ))
}

fn validate_decoded_session(raw: RawSession) -> Result<FastRealtimeCoverageSession, StorageError> {
    let session = FastRealtimeCoverageSession {
        session_id: i64_to_u64(raw.0, "coverage session id")?,
        provider: parse_provider(&raw.1)?,
        process_session_sequence: i64_to_u64(
            raw.2,
            "coverage process session sequence",
        )?,
        first_notification_observed_at_unix_ms: raw.3,
        last_notification_observed_at_unix_ms: raw.4,
        first_notification_slot: parse_u64_text(
            &raw.5,
            "coverage first notification slot",
        )?,
        last_notification_slot: parse_u64_text(
            &raw.6,
            "coverage last notification slot",
        )?,
        first_notification_signature: raw.7,
        last_notification_signature: raw.8,
        notification_count: i64_to_u64(raw.9, "coverage notification count")?,
    };

    validate_sample(
        session.process_session_sequence,
        session.first_notification_observed_at_unix_ms,
        &session.first_notification_signature,
    )?;
    validate_sample(
        session.process_session_sequence,
        session.last_notification_observed_at_unix_ms,
        &session.last_notification_signature,
    )?;
    if session.last_notification_observed_at_unix_ms
        < session.first_notification_observed_at_unix_ms
        || session.notification_count == 0
    {
        return Err(StorageError::InvalidData(
            "stored realtime coverage session is internally inconsistent".to_owned(),
        ));
    }
    Ok(session)
}

fn validate_sample(
    process_session_sequence: u64,
    observed_at_unix_ms: i64,
    signature: &str,
) -> Result<(), StorageError> {
    if process_session_sequence == 0 {
        return Err(StorageError::InvalidData(
            "coverage process session sequence must be positive".to_owned(),
        ));
    }
    if observed_at_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "coverage notification timestamp must be non-negative".to_owned(),
        ));
    }
    if signature.trim().is_empty() {
        return Err(StorageError::InvalidData(
            "coverage notification signature must not be empty".to_owned(),
        ));
    }
    Ok(())
}

fn parse_u64_text(value: &str, field: &str) -> Result<u64, StorageError> {
    value.parse::<u64>().map_err(|error| {
        StorageError::InvalidData(format!(
            "{field} is not u64 decimal text: {error}"
        ))
    })
}

fn u64_to_i64(value: u64, field: &str) -> Result<i64, StorageError> {
    i64::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!(
            "{field} exceeds SQLite signed integer range"
        ))
    })
}

fn i64_to_u64(value: i64, field: &str) -> Result<u64, StorageError> {
    u64::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!("{field} was negative"))
    })
}
