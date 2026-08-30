use std::{collections::HashSet, error::Error, fmt, path::Path};

use rusqlite::{Connection, OpenFlags};

#[derive(Debug)]
pub enum RealtimeTargetError {
    InvalidData(String),
    Sqlite(rusqlite::Error),
}

impl fmt::Display for RealtimeTargetError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidData(message) => formatter.write_str(message),
            Self::Sqlite(error) => write!(formatter, "PumpSwap realtime target SQLite error: {error}"),
        }
    }
}

impl Error for RealtimeTargetError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::InvalidData(_) => None,
            Self::Sqlite(error) => Some(error),
        }
    }
}

impl From<rusqlite::Error> for RealtimeTargetError {
    fn from(error: rusqlite::Error) -> Self {
        Self::Sqlite(error)
    }
}

/// Read a deterministic bounded set of verified PumpSwap pool identities from
/// existing immutable Pump graduation evidence. The interval is
/// `[as_of_unix_ms - max_age_ms, as_of_unix_ms)` so evidence observed exactly
/// at the as-of boundary belongs to the next refresh. This function never
/// migrates or writes the operational database.
pub fn load_verified_pumpswap_targets(
    db_path: &Path,
    as_of_unix_ms: i64,
    max_age_ms: i64,
    max_count: usize,
) -> Result<Vec<String>, RealtimeTargetError> {
    if as_of_unix_ms < 0 {
        return Err(RealtimeTargetError::InvalidData(
            "PumpSwap realtime target as_of_unix_ms must not be negative".to_owned(),
        ));
    }
    if max_age_ms <= 0 {
        return Err(RealtimeTargetError::InvalidData(
            "PumpSwap realtime target max_age_ms must be positive".to_owned(),
        ));
    }
    if max_count == 0 {
        return Err(RealtimeTargetError::InvalidData(
            "PumpSwap realtime target max_count must be positive".to_owned(),
        ));
    }

    let minimum_detected_at_unix_ms = as_of_unix_ms.saturating_sub(max_age_ms).max(0);
    let connection = Connection::open_with_flags(db_path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let mut statement = connection.prepare(
        r#"SELECT pool_address
           FROM token_lifecycle_events
           WHERE event_type = 'pump_graduation'
             AND detected_at_unix_ms >= ?1
             AND detected_at_unix_ms < ?2
           ORDER BY detected_at_unix_ms DESC, signature ASC, pool_address ASC"#,
    )?;

    let mut rows = statement.query((minimum_detected_at_unix_ms, as_of_unix_ms))?;
    let mut seen = HashSet::with_capacity(max_count);
    let mut targets = Vec::with_capacity(max_count);
    while let Some(row) = rows.next()? {
        let pool: String = row.get(0)?;
        let pool = pool.trim();
        if pool.is_empty() {
            return Err(RealtimeTargetError::InvalidData(
                "verified Pump graduation contained a blank pool address".to_owned(),
            ));
        }
        if seen.insert(pool.to_owned()) {
            targets.push(pool.to_owned());
            if targets.len() == max_count {
                break;
            }
        }
    }

    Ok(targets)
}
