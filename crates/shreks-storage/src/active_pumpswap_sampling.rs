use rusqlite::params;

use crate::{ShreksDb, StorageError};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActivePumpSwapMint {
    pub mint: String,
    pub last_event_at_unix_ms: i64,
}

impl ShreksDb {
    /// Return recently active canonical PumpSwap mints whose latest persisted
    /// DexScreener PumpSwap snapshot is older than the requested freshness
    /// target.
    ///
    /// This selector is outcome-neutral. It uses only current FastEvent
    /// activity and market-observation timestamps so the observer can spend
    /// scarce public-provider capacity on markets that are actually producing
    /// decision opportunities.
    pub fn active_pump_swap_mints_needing_dexscreener_snapshot(
        &self,
        as_of_unix_ms: i64,
        activity_lookback_ms: i64,
        freshness_target_ms: i64,
        limit: usize,
    ) -> Result<Vec<ActivePumpSwapMint>, StorageError> {
        if as_of_unix_ms < 0 {
            return Err(StorageError::InvalidData(
                "active PumpSwap sampling as-of timestamp must be nonnegative".to_owned(),
            ));
        }
        if activity_lookback_ms <= 0 {
            return Err(StorageError::InvalidData(
                "active PumpSwap sampling lookback must be positive".to_owned(),
            ));
        }
        if freshness_target_ms <= 0 {
            return Err(StorageError::InvalidData(
                "active PumpSwap sampling freshness target must be positive".to_owned(),
            ));
        }
        if limit == 0 {
            return Ok(Vec::new());
        }

        let activity_floor = as_of_unix_ms
            .saturating_sub(activity_lookback_ms)
            .max(0);
        let freshness_floor = as_of_unix_ms
            .saturating_sub(freshness_target_ms)
            .max(0);
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData(
                "active PumpSwap sampling limit exceeds i64".to_owned(),
            )
        })?;

        let mut statement = self.connection.prepare(
            r#"WITH active AS (
                   SELECT
                       mint,
                       MAX(observed_at_unix_ms) AS last_event_at_unix_ms
                   FROM fast_events
                   WHERE venue = 'pump_swap'
                     AND observed_at_unix_ms >= ?1
                     AND observed_at_unix_ms <= ?2
                   GROUP BY mint
               )
               SELECT
                   active.mint,
                   active.last_event_at_unix_ms
               FROM active
               WHERE NOT EXISTS (
                   SELECT 1
                   FROM market_snapshots AS snapshot
                   WHERE snapshot.base_mint = active.mint
                     AND snapshot.source = 'dexscreener'
                     AND snapshot.venue = 'pump_swap'
                     AND snapshot.observed_at_unix_ms >= ?3
                     AND snapshot.observed_at_unix_ms <= ?2
               )
               ORDER BY
                   active.last_event_at_unix_ms DESC,
                   active.mint ASC
               LIMIT ?4"#,
        )?;

        let rows = statement
            .query_map(
                params![
                    activity_floor,
                    as_of_unix_ms,
                    freshness_floor,
                    limit,
                ],
                |row| {
                    Ok(ActivePumpSwapMint {
                        mint: row.get(0)?,
                        last_event_at_unix_ms: row.get(1)?,
                    })
                },
            )?
            .collect::<Result<Vec<_>, _>>()?;

        for row in &rows {
            if row.mint.trim().is_empty() {
                return Err(StorageError::InvalidData(
                    "active PumpSwap sampling selector returned blank mint".to_owned(),
                ));
            }
            if row.last_event_at_unix_ms < activity_floor
                || row.last_event_at_unix_ms > as_of_unix_ms
            {
                return Err(StorageError::InvalidData(
                    "active PumpSwap sampling selector returned invalid event timestamp"
                        .to_owned(),
                ));
            }
        }

        Ok(rows)
    }
}
