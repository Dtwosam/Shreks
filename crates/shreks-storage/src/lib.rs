//! Operational SQLite storage for Shreks.

use std::{
    error::Error,
    fmt, fs,
    path::Path,
    time::{Duration, SystemTime, SystemTimeError, UNIX_EPOCH},
};

use rusqlite::{params, Connection, OptionalExtension};
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderHealthState, ProviderId, TokenMintState,
    TransactionWindow,
};

const BUSY_TIMEOUT_MS: u64 = 5_000;

struct Migration {
    version: i64,
    name: &'static str,
    sql: &'static str,
}

const MIGRATIONS: &[Migration] = &[
    Migration {
        version: 1,
        name: "operational",
        sql: include_str!("../migrations/0001_operational.sql"),
    },
    Migration {
        version: 2,
        name: "observer_normalization",
        sql: include_str!("../migrations/0002_observer_normalization.sql"),
    },
];

/// Read-only operational diagnostics for a Shreks database connection.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DatabaseDiagnostics {
    pub journal_mode: String,
    pub foreign_keys_enabled: bool,
    pub schema_version: i64,
}

/// Errors produced while opening, validating, migrating, or writing Shreks
/// operational storage.
#[derive(Debug)]
pub enum StorageError {
    Io(std::io::Error),
    Sqlite(rusqlite::Error),
    Clock(SystemTimeError),
    InvalidData(String),
}

impl fmt::Display for StorageError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "storage filesystem error: {error}"),
            Self::Sqlite(error) => write!(formatter, "storage SQLite error: {error}"),
            Self::Clock(error) => write!(formatter, "storage clock error: {error}"),
            Self::InvalidData(message) => write!(formatter, "storage rejected invalid data: {message}"),
        }
    }
}

impl Error for StorageError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Sqlite(error) => Some(error),
            Self::Clock(error) => Some(error),
            Self::InvalidData(_) => None,
        }
    }
}

impl From<std::io::Error> for StorageError {
    fn from(error: std::io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<rusqlite::Error> for StorageError {
    fn from(error: rusqlite::Error) -> Self {
        Self::Sqlite(error)
    }
}

impl From<SystemTimeError> for StorageError {
    fn from(error: SystemTimeError) -> Self {
        Self::Clock(error)
    }
}

/// Owns one configured connection to the operational Shreks SQLite database.
pub struct ShreksDb {
    connection: Connection,
}

impl ShreksDb {
    /// Open or create a file-backed Shreks database and bring it to the latest
    /// known schema version before returning it to the caller.
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self, StorageError> {
        let path = path.as_ref();
        if let Some(parent) = path.parent().filter(|parent| !parent.as_os_str().is_empty()) {
            fs::create_dir_all(parent)?;
        }

        let mut connection = Connection::open(path)?;
        configure_connection(&connection)?;
        apply_migrations(&mut connection)?;

        Ok(Self { connection })
    }

    /// Report configuration and migration state without exposing the raw
    /// SQLite connection to callers.
    pub fn diagnostics(&self) -> Result<DatabaseDiagnostics, StorageError> {
        let journal_mode = self
            .connection
            .query_row("PRAGMA journal_mode", [], |row| row.get::<_, String>(0))?;
        let foreign_keys: i64 = self
            .connection
            .query_row("PRAGMA foreign_keys", [], |row| row.get(0))?;
        let schema_version: i64 = self.connection.query_row(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations",
            [],
            |row| row.get(0),
        )?;

        Ok(DatabaseDiagnostics {
            journal_mode,
            foreign_keys_enabled: foreign_keys == 1,
            schema_version,
        })
    }

    /// Persist a discovered candidate without creating duplicate rows for the
    /// same mint/pair/source identity. The earliest discovery timestamp wins;
    /// later venue information may enrich an existing row.
    pub fn upsert_candidate(&self, candidate: &DiscoveredToken) -> Result<i64, StorageError> {
        if candidate.mint.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "candidate mint must not be empty".to_owned(),
            ));
        }

        let pair_address = candidate.pair_address.as_deref().unwrap_or("");
        let venue = candidate.venue.map(|value| value.as_str());
        let created_at = unix_time_ms()?;

        self.connection.execute(
            r#"INSERT INTO token_candidates (
                   mint, pair_address, discovery_source, discovered_at_unix_ms, created_at_unix_ms, venue
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
               ON CONFLICT(mint, pair_address, discovery_source) DO UPDATE SET
                   venue = COALESCE(excluded.venue, token_candidates.venue),
                   discovered_at_unix_ms = MIN(token_candidates.discovered_at_unix_ms, excluded.discovered_at_unix_ms)"#,
            params![
                candidate.mint,
                pair_address,
                candidate.source.as_str(),
                candidate.discovered_at_unix_ms,
                created_at,
                venue,
            ],
        )?;

        let id = self.connection.query_row(
            "SELECT id FROM token_candidates WHERE mint = ?1 AND pair_address = ?2 AND discovery_source = ?3",
            params![candidate.mint, pair_address, candidate.source.as_str()],
            |row| row.get(0),
        )?;
        Ok(id)
    }

    /// Persist one provider-neutral pair snapshot. Duplicate observations of
    /// the same candidate/provider/pair/timestamp are ignored safely.
    pub fn insert_market_snapshot(
        &self,
        candidate_id: i64,
        snapshot: &PairMarketData,
    ) -> Result<(), StorageError> {
        if snapshot.chain_id != "solana" {
            return Err(StorageError::InvalidData(format!(
                "market snapshot chain must be solana; got {}",
                snapshot.chain_id
            )));
        }
        if snapshot.pair_address.trim().is_empty()
            || snapshot.base_mint.trim().is_empty()
            || snapshot.quote_mint.trim().is_empty()
        {
            return Err(StorageError::InvalidData(
                "market snapshot requires pair, base mint, and quote mint".to_owned(),
            ));
        }

        validate_optional_decimal_text(snapshot.price_native.as_deref(), "price_native")?;
        let price_usd = parse_optional_decimal_text(snapshot.price_usd.as_deref(), "price_usd")?;
        let liquidity_usd = validate_optional_nonnegative_f64(snapshot.liquidity_usd, "liquidity_usd")?;
        let volume_5m = validate_optional_nonnegative_f64(snapshot.volume_5m, "volume_5m")?;
        let volume_1h = validate_optional_nonnegative_f64(snapshot.volume_1h, "volume_1h")?;
        let volume_6h = validate_optional_nonnegative_f64(snapshot.volume_6h, "volume_6h")?;
        let volume_24h = validate_optional_nonnegative_f64(snapshot.volume_24h, "volume_24h")?;
        let fdv_usd = validate_optional_nonnegative_f64(snapshot.fdv_usd, "fdv_usd")?;
        let market_cap_usd =
            validate_optional_nonnegative_f64(snapshot.market_cap_usd, "market_cap_usd")?;

        let m5 = transaction_window(&snapshot.transactions, "m5");
        let h1 = transaction_window(&snapshot.transactions, "h1");
        let buys_m5 = optional_u64_as_i64(m5.map(|window| window.buys), "buys_m5")?;
        let sells_m5 = optional_u64_as_i64(m5.map(|window| window.sells), "sells_m5")?;
        let buys_h1 = optional_u64_as_i64(h1.map(|window| window.buys), "buys_h1")?;
        let sells_h1 = optional_u64_as_i64(h1.map(|window| window.sells), "sells_h1")?;

        self.connection.execute(
            r#"INSERT OR IGNORE INTO market_snapshots (
                   candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
                   venue, pair_address, dex_id, base_mint, quote_mint, price_native, price_usd,
                   market_cap_usd, fdv_usd, liquidity_usd, volume_m5_usd, volume_h1_usd,
                   volume_h6_usd, volume_h24_usd, buys_m5, sells_m5, buys_h1, sells_h1,
                   pair_created_at_unix_ms
               ) VALUES (
                   ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15,
                   ?16, ?17, ?18, ?19, ?20, ?21, ?22, ?23
               )"#,
            params![
                candidate_id,
                snapshot.observed_at_unix_ms,
                snapshot.provider.as_str(),
                snapshot.observed_at_unix_ms,
                snapshot.venue.as_str(),
                snapshot.pair_address,
                snapshot.dex_id,
                snapshot.base_mint,
                snapshot.quote_mint,
                snapshot.price_native,
                price_usd,
                market_cap_usd,
                fdv_usd,
                liquidity_usd,
                volume_5m,
                volume_1h,
                volume_6h,
                volume_24h,
                buys_m5,
                sells_m5,
                buys_h1,
                sells_h1,
                snapshot.pair_created_at_unix_ms,
            ],
        )?;
        Ok(())
    }

    /// Persist parsed Solana mint state while preserving full unsigned values
    /// as decimal text instead of narrowing them into SQLite's signed INTEGER.
    pub fn insert_mint_state(
        &self,
        candidate_id: i64,
        state: &TokenMintState,
    ) -> Result<(), StorageError> {
        if state.mint.trim().is_empty() || state.owner_program.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "mint state requires mint and owner program".to_owned(),
            ));
        }

        self.connection.execute(
            r#"INSERT OR IGNORE INTO token_mint_states (
                   candidate_id, provider, owner_program, supply, decimals, mint_authority,
                   freeze_authority, slot, observed_at_unix_ms
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)"#,
            params![
                candidate_id,
                state.provider.as_str(),
                state.owner_program,
                state.supply.to_string(),
                i64::from(state.decimals),
                state.mint_authority,
                state.freeze_authority,
                state.slot.to_string(),
                state.observed_at_unix_ms,
            ],
        )?;
        Ok(())
    }

    /// Upsert the latest health state for one provider.
    pub fn upsert_provider_health(
        &self,
        provider: ProviderId,
        state: ProviderHealthState,
        observed_at_unix_ms: i64,
        latency_ms: Option<u64>,
        detail: Option<&str>,
        consecutive_failures: u64,
    ) -> Result<(), StorageError> {
        let latency_ms = optional_u64_as_i64(latency_ms, "provider latency_ms")?;
        let consecutive_failures = u64_as_i64(consecutive_failures, "provider consecutive_failures")?;

        self.connection.execute(
            r#"INSERT INTO provider_health (
                   provider, status, observed_at_unix_ms, latency_ms, detail, consecutive_failures
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
               ON CONFLICT(provider) DO UPDATE SET
                   status = excluded.status,
                   observed_at_unix_ms = excluded.observed_at_unix_ms,
                   latency_ms = excluded.latency_ms,
                   detail = excluded.detail,
                   consecutive_failures = excluded.consecutive_failures"#,
            params![
                provider.as_str(),
                state.as_str(),
                observed_at_unix_ms,
                latency_ms,
                detail,
                consecutive_failures,
            ],
        )?;
        Ok(())
    }

    /// Replace a provider stream checkpoint atomically.
    pub fn set_ingestion_checkpoint(
        &self,
        provider: ProviderId,
        stream: &str,
        cursor: Option<&str>,
    ) -> Result<(), StorageError> {
        if stream.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "ingestion checkpoint stream must not be empty".to_owned(),
            ));
        }

        self.connection.execute(
            r#"INSERT INTO ingestion_checkpoints (provider, stream, cursor, updated_at_unix_ms)
               VALUES (?1, ?2, ?3, ?4)
               ON CONFLICT(provider, stream) DO UPDATE SET
                   cursor = excluded.cursor,
                   updated_at_unix_ms = excluded.updated_at_unix_ms"#,
            params![provider.as_str(), stream, cursor, unix_time_ms()?],
        )?;
        Ok(())
    }

    /// Load a previously persisted provider stream checkpoint.
    pub fn ingestion_checkpoint(
        &self,
        provider: ProviderId,
        stream: &str,
    ) -> Result<Option<String>, StorageError> {
        if stream.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "ingestion checkpoint stream must not be empty".to_owned(),
            ));
        }

        let cursor = self
            .connection
            .query_row(
                "SELECT cursor FROM ingestion_checkpoints WHERE provider = ?1 AND stream = ?2",
                params![provider.as_str(), stream],
                |row| row.get::<_, Option<String>>(0),
            )
            .optional()?;
        Ok(cursor.flatten())
    }
}

fn configure_connection(connection: &Connection) -> Result<(), StorageError> {
    connection.query_row("PRAGMA journal_mode = WAL", [], |row| row.get::<_, String>(0))?;
    connection.busy_timeout(Duration::from_millis(BUSY_TIMEOUT_MS))?;
    connection.execute_batch(
        "PRAGMA foreign_keys = ON;\n\
         PRAGMA synchronous = NORMAL;",
    )?;

    Ok(())
}

fn apply_migrations(connection: &mut Connection) -> Result<(), StorageError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_migrations (\n\
             version INTEGER PRIMARY KEY,\n\
             name TEXT NOT NULL,\n\
             applied_at_unix_ms INTEGER NOT NULL\n\
         );",
    )?;

    for migration in MIGRATIONS {
        let applied: i64 = connection.query_row(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?1",
            [migration.version],
            |row| row.get(0),
        )?;

        if applied != 0 {
            continue;
        }

        let transaction = connection.transaction()?;
        transaction.execute_batch(migration.sql)?;
        transaction.execute(
            "INSERT INTO schema_migrations (version, name, applied_at_unix_ms) VALUES (?1, ?2, ?3)",
            params![migration.version, migration.name, unix_time_ms()?],
        )?;
        transaction.commit()?;
    }

    Ok(())
}

fn transaction_window<'a>(
    windows: &'a [TransactionWindow],
    name: &str,
) -> Option<&'a TransactionWindow> {
    windows.iter().find(|window| window.window == name)
}

fn validate_optional_decimal_text(value: Option<&str>, field: &str) -> Result<(), StorageError> {
    if let Some(value) = value {
        let parsed = parse_decimal_text(value, field)?;
        if parsed < 0.0 {
            return Err(StorageError::InvalidData(format!(
                "{field} must not be negative"
            )));
        }
    }
    Ok(())
}

fn parse_optional_decimal_text(
    value: Option<&str>,
    field: &str,
) -> Result<Option<f64>, StorageError> {
    value
        .map(|value| {
            let parsed = parse_decimal_text(value, field)?;
            if parsed < 0.0 {
                return Err(StorageError::InvalidData(format!(
                    "{field} must not be negative"
                )));
            }
            Ok(parsed)
        })
        .transpose()
}

fn parse_decimal_text(value: &str, field: &str) -> Result<f64, StorageError> {
    let parsed = value.parse::<f64>().map_err(|error| {
        StorageError::InvalidData(format!("{field} is not numeric: {error}"))
    })?;
    if !parsed.is_finite() {
        return Err(StorageError::InvalidData(format!(
            "{field} must be finite"
        )));
    }
    Ok(parsed)
}

fn validate_optional_nonnegative_f64(
    value: Option<f64>,
    field: &str,
) -> Result<Option<f64>, StorageError> {
    if let Some(value) = value {
        if !value.is_finite() || value < 0.0 {
            return Err(StorageError::InvalidData(format!(
                "{field} must be finite and nonnegative"
            )));
        }
    }
    Ok(value)
}

fn optional_u64_as_i64(value: Option<u64>, field: &str) -> Result<Option<i64>, StorageError> {
    value.map(|value| u64_as_i64(value, field)).transpose()
}

fn u64_as_i64(value: u64, field: &str) -> Result<i64, StorageError> {
    i64::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!("{field} exceeds SQLite signed integer range"))
    })
}

fn unix_time_ms() -> Result<i64, StorageError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH)?;
    i64::try_from(elapsed.as_millis()).map_err(|_| {
        StorageError::InvalidData("system clock exceeds i64 milliseconds".to_owned())
    })
}

#[cfg(test)]
mod tests {
    use super::BUSY_TIMEOUT_MS;

    #[test]
    fn busy_timeout_is_five_seconds() {
        assert_eq!(BUSY_TIMEOUT_MS, 5_000);
    }
}
