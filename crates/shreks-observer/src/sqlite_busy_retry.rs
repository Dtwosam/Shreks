use std::{thread, time::Duration};

use rusqlite::ErrorCode;
use shreks_storage::StorageError;

const SQLITE_BUSY_MAX_ATTEMPTS: usize = 2;
const SQLITE_BUSY_RETRY_DELAY: Duration = Duration::from_millis(250);

/// Retry one operation once when the caller explicitly classifies its error as
/// transient SQLite writer contention. The underlying ShreksDb busy timeout is
/// unchanged; this is an additional bounded application-level recovery chance
/// for mandatory durability paths only.
pub(crate) fn retry_bounded<T, E, F, P>(
    mut operation: F,
    mut is_retryable: P,
) -> Result<T, E>
where
    F: FnMut() -> Result<T, E>,
    P: FnMut(&E) -> bool,
{
    let mut attempts = 1_usize;
    loop {
        match operation() {
            Err(error) if is_retryable(&error) && attempts < SQLITE_BUSY_MAX_ATTEMPTS => {
                attempts += 1;
                thread::sleep(SQLITE_BUSY_RETRY_DELAY);
            }
            result => return result,
        }
    }
}

/// Only SQLite's explicit writer-contention codes are retryable. Every other
/// storage error remains immediately fatal to preserve fail-closed semantics.
pub(crate) fn is_storage_sqlite_busy_or_locked(error: &StorageError) -> bool {
    matches!(
        error,
        StorageError::Sqlite(rusqlite::Error::SqliteFailure(sqlite_error, _))
            if matches!(
                sqlite_error.code,
                ErrorCode::DatabaseBusy | ErrorCode::DatabaseLocked
            )
    )
}

#[cfg(test)]
mod tests {
    use super::retry_bounded;

    #[test]
    fn persistent_retryable_error_stops_after_two_total_attempts() {
        let mut attempts = 0_usize;
        let result: Result<(), &'static str> = retry_bounded(
            || {
                attempts += 1;
                Err("busy")
            },
            |error| *error == "busy",
        );

        assert_eq!(result, Err("busy"));
        assert_eq!(attempts, 2);
    }

    #[test]
    fn non_retryable_error_is_returned_immediately() {
        let mut attempts = 0_usize;
        let result: Result<(), &'static str> = retry_bounded(
            || {
                attempts += 1;
                Err("corrupt")
            },
            |error| *error == "busy",
        );

        assert_eq!(result, Err("corrupt"));
        assert_eq!(attempts, 1);
    }
}
