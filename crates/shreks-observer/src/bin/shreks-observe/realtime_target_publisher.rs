use std::{
    error::Error,
    fmt,
    path::{Path, PathBuf},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use tokio::{
    sync::watch,
    time::MissedTickBehavior,
};

use crate::realtime_targets::{load_verified_pumpswap_targets, RealtimeTargetError};

pub const PUMPSWAP_TARGET_REFRESH_INTERVAL: Duration = Duration::from_secs(5);

#[derive(Debug)]
pub enum RealtimeTargetPublisherError {
    ClockBeforeUnixEpoch,
    ClockOverflow,
    Target(RealtimeTargetError),
    WatchClosed,
}

impl fmt::Display for RealtimeTargetPublisherError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ClockBeforeUnixEpoch => formatter.write_str(
                "PumpSwap realtime target publisher clock is before the Unix epoch",
            ),
            Self::ClockOverflow => formatter.write_str(
                "PumpSwap realtime target publisher clock exceeds i64 milliseconds",
            ),
            Self::Target(error) => write!(formatter, "PumpSwap realtime target refresh failed: {error}"),
            Self::WatchClosed => formatter.write_str(
                "PumpSwap realtime target publisher has no active realtime consumer",
            ),
        }
    }
}

impl Error for RealtimeTargetPublisherError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Target(error) => Some(error),
            Self::ClockBeforeUnixEpoch | Self::ClockOverflow | Self::WatchClosed => None,
        }
    }
}

impl From<RealtimeTargetError> for RealtimeTargetPublisherError {
    fn from(error: RealtimeTargetError) -> Self {
        Self::Target(error)
    }
}

/// Refresh the canonical bounded PumpSwap target set from verified durable
/// migration evidence. Query failure leaves the last published target set
/// untouched; unchanged canonical sets do not advance the watch version.
pub fn refresh_pumpswap_realtime_targets(
    db_path: &Path,
    as_of_unix_ms: i64,
    max_age_ms: i64,
    max_count: usize,
    sender: &watch::Sender<Vec<String>>,
) -> Result<bool, RealtimeTargetPublisherError> {
    let targets = load_verified_pumpswap_targets(
        db_path,
        as_of_unix_ms,
        max_age_ms,
        max_count,
    )?;

    if sender.borrow().as_slice() == targets.as_slice() {
        return Ok(false);
    }

    sender
        .send(targets)
        .map_err(|_| RealtimeTargetPublisherError::WatchClosed)?;
    Ok(true)
}

/// Periodically publish the verified bounded PumpSwap target set. The first
/// interval tick is immediate, so realtime startup can establish its initial
/// scope without waiting one refresh period. Any clock/query/watch failure is
/// returned to the owning observer so the realtime evidence lane can fail
/// closed rather than continue on stale or unknown scope.
pub async fn run_pumpswap_realtime_target_publisher(
    db_path: PathBuf,
    max_age_ms: i64,
    max_count: usize,
    sender: watch::Sender<Vec<String>>,
) -> Result<(), RealtimeTargetPublisherError> {
    let mut ticker = tokio::time::interval(PUMPSWAP_TARGET_REFRESH_INTERVAL);
    ticker.set_missed_tick_behavior(MissedTickBehavior::Skip);

    loop {
        ticker.tick().await;
        let as_of_unix_ms = unix_time_ms()?;
        refresh_pumpswap_realtime_targets(
            &db_path,
            as_of_unix_ms,
            max_age_ms,
            max_count,
            &sender,
        )?;
    }
}

fn unix_time_ms() -> Result<i64, RealtimeTargetPublisherError> {
    let elapsed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| RealtimeTargetPublisherError::ClockBeforeUnixEpoch)?;
    i64::try_from(elapsed.as_millis()).map_err(|_| RealtimeTargetPublisherError::ClockOverflow)
}
