//! Operational SQLite storage for Shreks.

use std::{
    error::Error,
    fmt, fs,
    path::Path,
    time::{SystemTime, SystemTimeError, UNIX_EPOCH},
};

use rusqlite::{params, Connection};

const BUSY_TIMEOUT_MS: u64 = 5_000;

struct Migration {
    version: i64,
    name: &'static str,
    sql: &'static str,
}

const MIGRATIONS: &[Migration] = &[Migration {
    version: 1,
    name: "operational",
    sql: include_str!("../migrations/0001_operational.sql"),
}];

/// Read-only operational diagnostics for a Shreks database connection.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DatabaseDiagnostics {
    pub journal_mode: String,
    pub foreign_keys_enabled: bool,
    pub schema_version: i64,
}

/// Errors produced while opening or migrating Shreks operational storage.
#[derive(Debug)]
pub enum StorageError {
    Io(std::io::Error),
    Sqlite(rusqlite::Error),
    Clock(SystemTimeError),
}

impl fmt::Display for StorageError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "storage filesystem error: {error}"),
            Self::Sqlite(error) => write!(formatter, "storage SQLite error: {error}"),
            Self::Clock(error) => write!(formatter, "storage clock error: {error}"),
        }
    }
}

impl Error for StorageError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Sqlite(error) => Some(error),
            Self::Clock(error) => Some(error),
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
}

fn configure_connection(connection: &Connection) -> Result<(), StorageError> {
    connection.query_row("PRAGMA journal_mode = WAL", [], |row| row.get::<_, String>(0))?;
    connection.execute_batch(
        "PRAGMA foreign_keys = ON;\n\
         PRAGMA synchronous = NORMAL;\n\
         PRAGMA busy_timeout = 5000;",
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

fn unix_time_ms() -> Result<i64, StorageError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH)?;
    Ok(elapsed.as_millis() as i64)
}

#[cfg(test)]
mod tests {
    use super::BUSY_TIMEOUT_MS;

    #[test]
    fn busy_timeout_is_five_seconds() {
        assert_eq!(BUSY_TIMEOUT_MS, 5_000);
    }
}
