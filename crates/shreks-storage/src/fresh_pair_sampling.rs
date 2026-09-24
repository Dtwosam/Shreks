use rusqlite::params;

use crate::{ShreksDb, StorageError};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FreshPairSamplingTarget {
    pub candidate_id: i64,
    pub mint: String,
    pub newest_pair_created_at_unix_ms: i64,
}

impl ShreksDb {
    /// Return candidates with a recently created, internally time-consistent
    /// DexScreener pair whose token-pair view is older than the requested
    /// freshness target.
    ///
    /// This selector is outcome-neutral. It uses only pair creation timestamps
    /// and market observation freshness so recently created markets can remain
    /// observable even when the broad research sampler is backlogged.
    pub fn fresh_pair_mints_needing_dexscreener_snapshot(
        &self,
        as_of_unix_ms: i64,
        pair_lookback_ms: i64,
        freshness_target_ms: i64,
        limit: usize,
    ) -> Result<Vec<FreshPairSamplingTarget>, StorageError> {
        if as_of_unix_ms < 0 {
            return Err(StorageError::InvalidData(
                "fresh-pair sampling as-of timestamp must be nonnegative".to_owned(),
            ));
        }
        if pair_lookback_ms <= 0 {
            return Err(StorageError::InvalidData(
                "fresh-pair sampling lookback must be positive".to_owned(),
            ));
        }
        if freshness_target_ms <= 0 {
            return Err(StorageError::InvalidData(
                "fresh-pair sampling freshness target must be positive".to_owned(),
            ));
        }
        if limit == 0 {
            return Ok(Vec::new());
        }

        let pair_floor = as_of_unix_ms.saturating_sub(pair_lookback_ms).max(0);
        let freshness_floor = as_of_unix_ms
            .saturating_sub(freshness_target_ms)
            .max(0);
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("fresh-pair sampling limit exceeds i64".to_owned())
        })?;

        let mut statement = self.connection.prepare(
            r#"WITH fresh_pairs AS (
                   SELECT
                       candidate.id AS candidate_id,
                       candidate.mint AS mint,
                       MAX(snapshot.pair_created_at_unix_ms)
                           AS newest_pair_created_at_unix_ms
                   FROM token_candidates AS candidate
                   JOIN market_snapshots AS snapshot
                     ON snapshot.candidate_id = candidate.id
                    AND snapshot.base_mint = candidate.mint
                   WHERE snapshot.source = 'dexscreener'
                     AND snapshot.observed_at_unix_ms BETWEEN ?1 AND ?2
                     AND snapshot.pair_created_at_unix_ms IS NOT NULL
                     AND snapshot.pair_created_at_unix_ms BETWEEN ?1 AND ?2
                     AND snapshot.pair_created_at_unix_ms
                         <= snapshot.observed_at_unix_ms
                   GROUP BY candidate.id, candidate.mint
               )
               SELECT
                   fresh_pairs.candidate_id,
                   fresh_pairs.mint,
                   fresh_pairs.newest_pair_created_at_unix_ms
               FROM fresh_pairs
               WHERE NOT EXISTS (
                   SELECT 1
                   FROM market_snapshots AS current
                   WHERE current.candidate_id = fresh_pairs.candidate_id
                     AND current.source = 'dexscreener'
                     AND current.base_mint = fresh_pairs.mint
                     AND current.observed_at_unix_ms BETWEEN ?3 AND ?2
               )
               ORDER BY
                   fresh_pairs.newest_pair_created_at_unix_ms DESC,
                   fresh_pairs.candidate_id ASC
               LIMIT ?4"#,
        )?;

        let rows = statement
            .query_map(
                params![pair_floor, as_of_unix_ms, freshness_floor, limit],
                |row| {
                    Ok(FreshPairSamplingTarget {
                        candidate_id: row.get(0)?,
                        mint: row.get(1)?,
                        newest_pair_created_at_unix_ms: row.get(2)?,
                    })
                },
            )?
            .collect::<Result<Vec<_>, _>>()?;

        for row in &rows {
            if row.candidate_id <= 0 || row.mint.trim().is_empty() {
                return Err(StorageError::InvalidData(
                    "fresh-pair sampling selector returned invalid candidate identity".to_owned(),
                ));
            }
            if row.newest_pair_created_at_unix_ms < pair_floor
                || row.newest_pair_created_at_unix_ms > as_of_unix_ms
            {
                return Err(StorageError::InvalidData(
                    "fresh-pair sampling selector returned invalid pair timestamp".to_owned(),
                ));
            }
        }

        Ok(rows)
    }
}
