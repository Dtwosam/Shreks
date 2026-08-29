use std::{
    error::Error,
    ffi::OsString,
    fmt, fs,
    path::{Path, PathBuf},
};

use rusqlite::{params, Connection, OpenFlags};

const REQUIRED_TABLE_COLUMNS: &[(&str, &[&str])] = &[
    (
        "pump_trade_evidence",
        &[
            "signature",
            "ordinal",
            "observed_at_unix_ms",
            "timestamp_unix_seconds",
        ],
    ),
    (
        "pump_swap_trade_evidence",
        &[
            "signature",
            "ordinal",
            "observed_at_unix_ms",
            "timestamp_unix_seconds",
        ],
    ),
    (
        "pump_trade_evidence_conflicts",
        &["signature", "ordinal", "observed_at_unix_ms"],
    ),
    (
        "pump_swap_trade_evidence_conflicts",
        &["signature", "ordinal", "observed_at_unix_ms"],
    ),
    (
        "fast_events",
        &[
            "sequence",
            "signature",
            "ordinal",
            "source_observed_at_unix_ms",
            "occurred_at_unix_ms",
            "observed_at_unix_ms",
        ],
    ),
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LatencySummary {
    pub samples: u64,
    pub p50_ms: Option<i64>,
    pub p95_ms: Option<i64>,
    pub p99_ms: Option<i64>,
    pub max_ms: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FastLaneAcceptanceReport {
    pub window_start_unix_ms: i64,
    pub as_of_unix_ms: i64,
    pub database_bytes: u64,
    pub wal_bytes: u64,
    pub pump_raw_events: u64,
    pub pumpswap_raw_events: u64,
    pub canonical_events: u64,
    pub pump_conflict_quarantine_total: u64,
    pub pumpswap_conflict_quarantine_total: u64,
    pub pump_conflict_quarantine_events: u64,
    pub pumpswap_conflict_quarantine_events: u64,
    pub pending_pump_events: u64,
    pub pending_pumpswap_events: u64,
    pub sequence_integrity_violations: u64,
    pub source_latency: LatencySummary,
    pub normalization_latency: LatencySummary,
    pub end_to_end_latency: LatencySummary,
}

#[derive(Debug)]
pub enum FastLaneAcceptanceError {
    Sqlite(rusqlite::Error),
    Io(std::io::Error),
    InvalidData(String),
}

impl fmt::Display for FastLaneAcceptanceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Sqlite(error) => write!(formatter, "Fast Lane acceptance SQLite error: {error}"),
            Self::Io(error) => write!(formatter, "Fast Lane acceptance filesystem error: {error}"),
            Self::InvalidData(message) => write!(formatter, "invalid Fast Lane acceptance data: {message}"),
        }
    }
}

impl Error for FastLaneAcceptanceError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Sqlite(error) => Some(error),
            Self::Io(error) => Some(error),
            Self::InvalidData(_) => None,
        }
    }
}

pub struct FastLaneAcceptanceStore {
    connection: Connection,
    path: PathBuf,
}

impl fmt::Debug for FastLaneAcceptanceStore {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("FastLaneAcceptanceStore")
            .field("path", &self.path)
            .finish_non_exhaustive()
    }
}

impl FastLaneAcceptanceStore {
    pub fn open(path: &Path) -> Result<Self, FastLaneAcceptanceError> {
        if path.as_os_str().is_empty() {
            return Err(FastLaneAcceptanceError::InvalidData(
                "database path must not be empty".to_owned(),
            ));
        }

        let connection = Connection::open_with_flags(
            path,
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )
        .map_err(|error| {
            FastLaneAcceptanceError::InvalidData(format!(
                "unable to open Fast Lane database read-only: {error}"
            ))
        })?;

        validate_schema(&connection)?;
        Ok(Self {
            connection,
            path: path.to_path_buf(),
        })
    }

    pub fn report(
        &self,
        window_start_unix_ms: i64,
        as_of_unix_ms: i64,
    ) -> Result<FastLaneAcceptanceReport, FastLaneAcceptanceError> {
        validate_window(window_start_unix_ms, as_of_unix_ms)?;

        let pump_raw_events = window_count(
            &self.connection,
            "SELECT COUNT(*) FROM pump_trade_evidence WHERE observed_at_unix_ms >= ?1 AND observed_at_unix_ms < ?2",
            window_start_unix_ms,
            as_of_unix_ms,
            "Pump raw event count",
        )?;
        let pumpswap_raw_events = window_count(
            &self.connection,
            "SELECT COUNT(*) FROM pump_swap_trade_evidence WHERE observed_at_unix_ms >= ?1 AND observed_at_unix_ms < ?2",
            window_start_unix_ms,
            as_of_unix_ms,
            "PumpSwap raw event count",
        )?;
        let canonical_events = window_count(
            &self.connection,
            "SELECT COUNT(*) FROM fast_events WHERE observed_at_unix_ms >= ?1 AND observed_at_unix_ms < ?2",
            window_start_unix_ms,
            as_of_unix_ms,
            "canonical FastEvent count",
        )?;
        let pump_conflict_quarantine_total = count_query(
            &self.connection,
            "SELECT COUNT(*) FROM pump_trade_evidence_conflicts",
            "Pump conflict quarantine total",
        )?;
        let pumpswap_conflict_quarantine_total = count_query(
            &self.connection,
            "SELECT COUNT(*) FROM pump_swap_trade_evidence_conflicts",
            "PumpSwap conflict quarantine total",
        )?;
        let pump_conflict_quarantine_events = window_count(
            &self.connection,
            "SELECT COUNT(*) FROM pump_trade_evidence_conflicts WHERE observed_at_unix_ms >= ?1 AND observed_at_unix_ms < ?2",
            window_start_unix_ms,
            as_of_unix_ms,
            "Pump conflict quarantine window count",
        )?;
        let pumpswap_conflict_quarantine_events = window_count(
            &self.connection,
            "SELECT COUNT(*) FROM pump_swap_trade_evidence_conflicts WHERE observed_at_unix_ms >= ?1 AND observed_at_unix_ms < ?2",
            window_start_unix_ms,
            as_of_unix_ms,
            "PumpSwap conflict quarantine window count",
        )?;

        let pending_pump_events = count_query(
            &self.connection,
            r#"SELECT COUNT(*)
               FROM pump_trade_evidence AS p
               LEFT JOIN fast_events AS f
                 ON f.signature = p.signature AND f.ordinal = p.ordinal
               WHERE f.sequence IS NULL"#,
            "pending Pump event count",
        )?;
        let pending_pumpswap_events = count_query(
            &self.connection,
            r#"SELECT COUNT(*)
               FROM pump_swap_trade_evidence AS p
               LEFT JOIN fast_events AS f
                 ON f.signature = p.signature AND f.ordinal = p.ordinal
               WHERE f.sequence IS NULL"#,
            "pending PumpSwap event count",
        )?;

        let mut source_latencies = raw_source_latencies(
            &self.connection,
            "pump_trade_evidence",
            window_start_unix_ms,
            as_of_unix_ms,
        )?;
        source_latencies.extend(raw_source_latencies(
            &self.connection,
            "pump_swap_trade_evidence",
            window_start_unix_ms,
            as_of_unix_ms,
        )?);

        let (normalization_latencies, end_to_end_latencies) = canonical_latencies(
            &self.connection,
            window_start_unix_ms,
            as_of_unix_ms,
        )?;

        let database_bytes = fs::metadata(&self.path)
            .map_err(FastLaneAcceptanceError::Io)?
            .len();
        let wal_path = wal_path(&self.path);
        let wal_bytes = match fs::metadata(&wal_path) {
            Ok(metadata) => metadata.len(),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => 0,
            Err(error) => return Err(FastLaneAcceptanceError::Io(error)),
        };

        Ok(FastLaneAcceptanceReport {
            window_start_unix_ms,
            as_of_unix_ms,
            database_bytes,
            wal_bytes,
            pump_raw_events,
            pumpswap_raw_events,
            canonical_events,
            pump_conflict_quarantine_total,
            pumpswap_conflict_quarantine_total,
            pump_conflict_quarantine_events,
            pumpswap_conflict_quarantine_events,
            pending_pump_events,
            pending_pumpswap_events,
            sequence_integrity_violations: sequence_integrity_violations(&self.connection)?,
            source_latency: latency_summary(source_latencies)?,
            normalization_latency: latency_summary(normalization_latencies)?,
            end_to_end_latency: latency_summary(end_to_end_latencies)?,
        })
    }
}

fn validate_window(
    window_start_unix_ms: i64,
    as_of_unix_ms: i64,
) -> Result<(), FastLaneAcceptanceError> {
    if window_start_unix_ms < 0 || as_of_unix_ms < 0 {
        return Err(FastLaneAcceptanceError::InvalidData(
            "acceptance window timestamps must be non-negative".to_owned(),
        ));
    }
    if as_of_unix_ms <= window_start_unix_ms {
        return Err(FastLaneAcceptanceError::InvalidData(
            "acceptance as-of timestamp must be later than window start".to_owned(),
        ));
    }
    Ok(())
}

fn validate_schema(connection: &Connection) -> Result<(), FastLaneAcceptanceError> {
    for (table, required_columns) in REQUIRED_TABLE_COLUMNS {
        let exists: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?1",
                [*table],
                |row| row.get(0),
            )
            .map_err(FastLaneAcceptanceError::Sqlite)?;
        if exists != 1 {
            return Err(FastLaneAcceptanceError::InvalidData(format!(
                "Fast Lane database missing required table {table}"
            )));
        }

        let pragma = format!("PRAGMA table_info({table})");
        let mut statement = connection
            .prepare(&pragma)
            .map_err(FastLaneAcceptanceError::Sqlite)?;
        let columns = statement
            .query_map([], |row| row.get::<_, String>(1))
            .map_err(FastLaneAcceptanceError::Sqlite)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(FastLaneAcceptanceError::Sqlite)?;

        for required in *required_columns {
            if !columns.iter().any(|column| column == required) {
                return Err(FastLaneAcceptanceError::InvalidData(format!(
                    "Fast Lane database table {table} missing required column {required}"
                )));
            }
        }
    }
    Ok(())
}

fn window_count(
    connection: &Connection,
    sql: &str,
    window_start_unix_ms: i64,
    as_of_unix_ms: i64,
    field: &str,
) -> Result<u64, FastLaneAcceptanceError> {
    let value: i64 = connection
        .query_row(sql, params![window_start_unix_ms, as_of_unix_ms], |row| row.get(0))
        .map_err(FastLaneAcceptanceError::Sqlite)?;
    nonnegative_u64(value, field)
}

fn count_query(
    connection: &Connection,
    sql: &str,
    field: &str,
) -> Result<u64, FastLaneAcceptanceError> {
    let value: i64 = connection
        .query_row(sql, [], |row| row.get(0))
        .map_err(FastLaneAcceptanceError::Sqlite)?;
    nonnegative_u64(value, field)
}

fn nonnegative_u64(value: i64, field: &str) -> Result<u64, FastLaneAcceptanceError> {
    u64::try_from(value).map_err(|_| {
        FastLaneAcceptanceError::InvalidData(format!("{field} was negative or outside u64 range"))
    })
}

fn raw_source_latencies(
    connection: &Connection,
    table: &str,
    window_start_unix_ms: i64,
    as_of_unix_ms: i64,
) -> Result<Vec<i64>, FastLaneAcceptanceError> {
    let sql = match table {
        "pump_trade_evidence" => {
            "SELECT observed_at_unix_ms, timestamp_unix_seconds FROM pump_trade_evidence WHERE observed_at_unix_ms >= ?1 AND observed_at_unix_ms < ?2"
        }
        "pump_swap_trade_evidence" => {
            "SELECT observed_at_unix_ms, timestamp_unix_seconds FROM pump_swap_trade_evidence WHERE observed_at_unix_ms >= ?1 AND observed_at_unix_ms < ?2"
        }
        _ => {
            return Err(FastLaneAcceptanceError::InvalidData(
                "unsupported raw Fast Lane evidence table".to_owned(),
            ));
        }
    };

    let mut statement = connection
        .prepare(sql)
        .map_err(FastLaneAcceptanceError::Sqlite)?;
    let rows = statement
        .query_map(params![window_start_unix_ms, as_of_unix_ms], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?))
        })
        .map_err(FastLaneAcceptanceError::Sqlite)?;

    let mut latencies = Vec::new();
    for row in rows {
        let (source_observed_at_unix_ms, timestamp_unix_seconds) =
            row.map_err(FastLaneAcceptanceError::Sqlite)?;
        if source_observed_at_unix_ms < 0 || timestamp_unix_seconds < 0 {
            return Err(FastLaneAcceptanceError::InvalidData(format!(
                "{table} contains a negative timing field"
            )));
        }
        let occurred_at_unix_ms = timestamp_unix_seconds.checked_mul(1_000).ok_or_else(|| {
            FastLaneAcceptanceError::InvalidData(format!(
                "{table} chain occurrence timestamp overflows milliseconds"
            ))
        })?;
        latencies.push(checked_latency(
            source_observed_at_unix_ms,
            occurred_at_unix_ms,
            &format!("{table} source latency"),
        )?);
    }
    Ok(latencies)
}

fn canonical_latencies(
    connection: &Connection,
    window_start_unix_ms: i64,
    as_of_unix_ms: i64,
) -> Result<(Vec<i64>, Vec<i64>), FastLaneAcceptanceError> {
    let mut statement = connection
        .prepare(
            r#"SELECT observed_at_unix_ms, source_observed_at_unix_ms, occurred_at_unix_ms
               FROM fast_events
               WHERE observed_at_unix_ms >= ?1 AND observed_at_unix_ms < ?2"#,
        )
        .map_err(FastLaneAcceptanceError::Sqlite)?;
    let rows = statement
        .query_map(params![window_start_unix_ms, as_of_unix_ms], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })
        .map_err(FastLaneAcceptanceError::Sqlite)?;

    let mut normalization = Vec::new();
    let mut end_to_end = Vec::new();
    for row in rows {
        let (observed_at_unix_ms, source_observed_at_unix_ms, occurred_at_unix_ms) =
            row.map_err(FastLaneAcceptanceError::Sqlite)?;
        if observed_at_unix_ms < 0 || source_observed_at_unix_ms < 0 || occurred_at_unix_ms < 0 {
            return Err(FastLaneAcceptanceError::InvalidData(
                "canonical FastEvent contains a negative timing field".to_owned(),
            ));
        }
        normalization.push(checked_latency(
            observed_at_unix_ms,
            source_observed_at_unix_ms,
            "canonical normalization latency",
        )?);
        end_to_end.push(checked_latency(
            observed_at_unix_ms,
            occurred_at_unix_ms,
            "canonical end-to-end latency",
        )?);
    }
    Ok((normalization, end_to_end))
}

fn checked_latency(
    later_unix_ms: i64,
    earlier_unix_ms: i64,
    field: &str,
) -> Result<i64, FastLaneAcceptanceError> {
    let latency = later_unix_ms.checked_sub(earlier_unix_ms).ok_or_else(|| {
        FastLaneAcceptanceError::InvalidData(format!("{field} subtraction overflowed"))
    })?;
    if latency < 0 {
        return Err(FastLaneAcceptanceError::InvalidData(format!(
            "{field} must not be negative"
        )));
    }
    Ok(latency)
}

fn latency_summary(mut values: Vec<i64>) -> Result<LatencySummary, FastLaneAcceptanceError> {
    if values.is_empty() {
        return Ok(LatencySummary {
            samples: 0,
            p50_ms: None,
            p95_ms: None,
            p99_ms: None,
            max_ms: None,
        });
    }

    values.sort_unstable();
    let samples = u64::try_from(values.len()).map_err(|_| {
        FastLaneAcceptanceError::InvalidData(
            "latency sample count exceeds u64 range".to_owned(),
        )
    })?;
    Ok(LatencySummary {
        samples,
        p50_ms: Some(nearest_rank(&values, 50)),
        p95_ms: Some(nearest_rank(&values, 95)),
        p99_ms: Some(nearest_rank(&values, 99)),
        max_ms: values.last().copied(),
    })
}

fn nearest_rank(values: &[i64], percentile: u8) -> i64 {
    debug_assert!(!values.is_empty());
    debug_assert!((1..=100).contains(&percentile));
    let numerator = u128::from(percentile) * values.len() as u128;
    let rank = numerator.div_ceil(100).max(1);
    let index = usize::try_from(rank - 1).expect("nearest-rank index originates from slice length");
    values[index.min(values.len() - 1)]
}

fn sequence_integrity_violations(
    connection: &Connection,
) -> Result<u64, FastLaneAcceptanceError> {
    let mut statement = connection
        .prepare("SELECT sequence FROM fast_events ORDER BY sequence ASC")
        .map_err(FastLaneAcceptanceError::Sqlite)?;
    let rows = statement
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(FastLaneAcceptanceError::Sqlite)?;

    let mut violations = 0_u64;
    let mut previous: Option<i64> = None;
    for row in rows {
        let sequence = row.map_err(FastLaneAcceptanceError::Sqlite)?;
        match previous {
            None => {
                if sequence != 1 {
                    violations = violations.checked_add(1).ok_or_else(|| {
                        FastLaneAcceptanceError::InvalidData(
                            "sequence integrity violation count overflowed".to_owned(),
                        )
                    })?;
                }
            }
            Some(previous_sequence) => {
                let expected = previous_sequence.checked_add(1).ok_or_else(|| {
                    FastLaneAcceptanceError::InvalidData(
                        "canonical sequence exceeds SQLite signed integer range".to_owned(),
                    )
                })?;
                if sequence != expected {
                    violations = violations.checked_add(1).ok_or_else(|| {
                        FastLaneAcceptanceError::InvalidData(
                            "sequence integrity violation count overflowed".to_owned(),
                        )
                    })?;
                }
            }
        }
        previous = Some(sequence);
    }
    Ok(violations)
}

fn wal_path(path: &Path) -> PathBuf {
    let mut value: OsString = path.as_os_str().to_os_string();
    value.push("-wal");
    PathBuf::from(value)
}
