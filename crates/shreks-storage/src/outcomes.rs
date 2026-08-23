use rusqlite::{params, OptionalExtension};

use super::{ShreksDb, StorageError};

/// Approved future-outcome horizons from the Shreks master design.
pub const OUTCOME_HORIZONS_SECONDS: [u32; 7] = [60, 300, 900, 1_800, 3_600, 14_400, 86_400];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutcomeCheckpointStatus {
    Pending,
    Completed,
}

impl OutcomeCheckpointStatus {
    fn parse(value: &str) -> Result<Self, StorageError> {
        match value {
            "pending" => Ok(Self::Pending),
            "completed" => Ok(Self::Completed),
            other => Err(StorageError::InvalidData(format!(
                "unknown outcome checkpoint status '{other}'"
            ))),
        }
    }
}

/// Full durable representation of one candidate/horizon checkpoint.
#[derive(Debug, Clone, PartialEq)]
pub struct OutcomeCheckpointRecord {
    pub id: i64,
    pub candidate_id: i64,
    pub horizon_seconds: u32,
    pub due_at_unix_ms: i64,
    pub status: OutcomeCheckpointStatus,
    pub baseline_snapshot_id: Option<i64>,
    pub checkpoint_snapshot_id: Option<i64>,
    pub completed_at_unix_ms: Option<i64>,
    pub return_pct: Option<f64>,
    pub mfe_pct: Option<f64>,
    pub mae_pct: Option<f64>,
    pub liquidity_change_pct: Option<f64>,
    pub volume_m5_change_pct: Option<f64>,
    pub buys_m5_change: Option<i64>,
    pub sells_m5_change: Option<i64>,
    pub rug_or_dead_pool: Option<bool>,
    pub exitability: Option<String>,
}

/// Values written when one scheduled checkpoint has been measured. Snapshot
/// identifiers are mandatory so every metric remains traceable to source data;
/// metrics that the free-data path cannot support remain explicitly nullable.
#[derive(Debug, Clone, PartialEq)]
pub struct OutcomeCheckpointCompletion {
    pub baseline_snapshot_id: i64,
    pub checkpoint_snapshot_id: i64,
    pub completed_at_unix_ms: i64,
    pub return_pct: Option<f64>,
    pub mfe_pct: Option<f64>,
    pub mae_pct: Option<f64>,
    pub liquidity_change_pct: Option<f64>,
    pub volume_m5_change_pct: Option<f64>,
    pub buys_m5_change: Option<i64>,
    pub sells_m5_change: Option<i64>,
    pub rug_or_dead_pool: Option<bool>,
    pub exitability: Option<String>,
}

/// Minimal identity needed by the observer to revisit one due candidate.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DueOutcomeCheckpoint {
    pub candidate_id: i64,
    pub mint: String,
    pub horizon_seconds: u32,
    pub due_at_unix_ms: i64,
}

#[derive(Debug, Clone, Copy)]
struct MetricSnapshot {
    id: i64,
    observed_at_unix_ms: i64,
    price_usd: f64,
    liquidity_usd: Option<f64>,
    volume_m5_usd: Option<f64>,
    buys_m5: Option<i64>,
    sells_m5: Option<i64>,
}

impl ShreksDb {
    /// Idempotently schedule all approved future-outcome horizons for a
    /// candidate. All due timestamps are validated before any row is written.
    pub fn ensure_outcome_checkpoints(
        &self,
        candidate_id: i64,
        discovered_at_unix_ms: i64,
    ) -> Result<(), StorageError> {
        if candidate_id <= 0 {
            return Err(StorageError::InvalidData(
                "outcome candidate_id must be positive".to_owned(),
            ));
        }

        let due_times = OUTCOME_HORIZONS_SECONDS
            .iter()
            .map(|horizon| {
                let offset_ms = i64::from(*horizon)
                    .checked_mul(1_000)
                    .ok_or_else(|| StorageError::InvalidData("outcome horizon overflow".to_owned()))?;
                discovered_at_unix_ms.checked_add(offset_ms).ok_or_else(|| {
                    StorageError::InvalidData(format!(
                        "outcome due timestamp overflow for {horizon}s horizon"
                    ))
                })
            })
            .collect::<Result<Vec<_>, _>>()?;

        let transaction = self.connection.unchecked_transaction()?;
        for (horizon, due_at_unix_ms) in OUTCOME_HORIZONS_SECONDS.iter().zip(due_times) {
            transaction.execute(
                r#"INSERT OR IGNORE INTO candidate_outcome_checkpoints (
                       candidate_id, horizon_seconds, due_at_unix_ms, status
                   ) VALUES (?1, ?2, ?3, 'pending')"#,
                params![candidate_id, i64::from(*horizon), due_at_unix_ms],
            )?;
        }
        transaction.commit()?;
        Ok(())
    }

    /// Return all checkpoints for one candidate ordered by approved horizon.
    pub fn outcome_checkpoints(
        &self,
        candidate_id: i64,
    ) -> Result<Vec<OutcomeCheckpointRecord>, StorageError> {
        let mut statement = self.connection.prepare(
            r#"SELECT
                   id, candidate_id, horizon_seconds, due_at_unix_ms, status,
                   baseline_snapshot_id, checkpoint_snapshot_id, completed_at_unix_ms,
                   return_pct, mfe_pct, mae_pct, liquidity_change_pct,
                   volume_m5_change_pct, buys_m5_change, sells_m5_change,
                   rug_or_dead_pool, exitability
               FROM candidate_outcome_checkpoints
               WHERE candidate_id = ?1
               ORDER BY horizon_seconds ASC"#,
        )?;

        let raw = statement
            .query_map([candidate_id], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i64>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, Option<i64>>(5)?,
                    row.get::<_, Option<i64>>(6)?,
                    row.get::<_, Option<i64>>(7)?,
                    row.get::<_, Option<f64>>(8)?,
                    row.get::<_, Option<f64>>(9)?,
                    row.get::<_, Option<f64>>(10)?,
                    row.get::<_, Option<f64>>(11)?,
                    row.get::<_, Option<f64>>(12)?,
                    row.get::<_, Option<i64>>(13)?,
                    row.get::<_, Option<i64>>(14)?,
                    row.get::<_, Option<i64>>(15)?,
                    row.get::<_, Option<String>>(16)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        raw.into_iter()
            .map(
                |(
                    id,
                    candidate_id,
                    horizon_seconds,
                    due_at_unix_ms,
                    status,
                    baseline_snapshot_id,
                    checkpoint_snapshot_id,
                    completed_at_unix_ms,
                    return_pct,
                    mfe_pct,
                    mae_pct,
                    liquidity_change_pct,
                    volume_m5_change_pct,
                    buys_m5_change,
                    sells_m5_change,
                    rug_or_dead_pool,
                    exitability,
                )| {
                    Ok(OutcomeCheckpointRecord {
                        id,
                        candidate_id,
                        horizon_seconds: parse_horizon(horizon_seconds)?,
                        due_at_unix_ms,
                        status: OutcomeCheckpointStatus::parse(&status)?,
                        baseline_snapshot_id,
                        checkpoint_snapshot_id,
                        completed_at_unix_ms,
                        return_pct,
                        mfe_pct,
                        mae_pct,
                        liquidity_change_pct,
                        volume_m5_change_pct,
                        buys_m5_change,
                        sells_m5_change,
                        rug_or_dead_pool: rug_or_dead_pool.map(|value| value != 0),
                        exitability,
                    })
                },
            )
            .collect()
    }

    /// Return due pending checkpoint rows in deterministic order. A zero limit
    /// is a valid no-op and never reaches SQLite with an invalid LIMIT value.
    pub fn due_outcome_checkpoints(
        &self,
        now_unix_ms: i64,
        limit: usize,
    ) -> Result<Vec<DueOutcomeCheckpoint>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("outcome due limit exceeds i64".to_owned())
        })?;

        let mut statement = self.connection.prepare(
            r#"SELECT o.candidate_id, c.mint, o.horizon_seconds, o.due_at_unix_ms
               FROM candidate_outcome_checkpoints o
               JOIN token_candidates c ON c.id = o.candidate_id
               WHERE o.status = 'pending' AND o.due_at_unix_ms <= ?1
               ORDER BY o.due_at_unix_ms ASC, o.candidate_id ASC, o.horizon_seconds ASC
               LIMIT ?2"#,
        )?;

        let raw = statement
            .query_map(params![now_unix_ms, limit], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i64>(3)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        raw.into_iter()
            .map(|(candidate_id, mint, horizon_seconds, due_at_unix_ms)| {
                Ok(DueOutcomeCheckpoint {
                    candidate_id,
                    mint,
                    horizon_seconds: parse_horizon(horizon_seconds)?,
                    due_at_unix_ms,
                })
            })
            .collect()
    }

    /// Finalize every pending checkpoint for one candidate that is due and has
    /// a usable post-due price snapshot. Only snapshots observed no later than
    /// `completed_at_unix_ms` participate, preventing future-dated provider
    /// data from leaking into the outcome label.
    pub fn finalize_due_outcome_checkpoints(
        &self,
        candidate_id: i64,
        completed_at_unix_ms: i64,
    ) -> Result<usize, StorageError> {
        if candidate_id <= 0 {
            return Err(StorageError::InvalidData(
                "outcome candidate_id must be positive".to_owned(),
            ));
        }

        let discovered_at_unix_ms = self
            .connection
            .query_row(
                "SELECT discovered_at_unix_ms FROM token_candidates WHERE id = ?1",
                [candidate_id],
                |row| row.get::<_, i64>(0),
            )
            .optional()?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "outcome candidate {candidate_id} does not exist"
                ))
            })?;

        let baseline = self.load_baseline_metric_snapshot(
            candidate_id,
            discovered_at_unix_ms,
            completed_at_unix_ms,
        )?;
        let Some(baseline) = baseline else {
            return Ok(0);
        };

        let pending = {
            let mut statement = self.connection.prepare(
                r#"SELECT horizon_seconds, due_at_unix_ms
                   FROM candidate_outcome_checkpoints
                   WHERE candidate_id = ?1
                     AND status = 'pending'
                     AND due_at_unix_ms <= ?2
                   ORDER BY horizon_seconds ASC"#,
            )?;
            let rows = statement
                .query_map(params![candidate_id, completed_at_unix_ms], |row| {
                    Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?))
                })?
                .collect::<Result<Vec<_>, _>>()?;
            rows
        };

        let mut completed = 0usize;
        for (raw_horizon, due_at_unix_ms) in pending {
            let horizon_seconds = parse_horizon(raw_horizon)?;
            let checkpoint = self.load_checkpoint_metric_snapshot(
                candidate_id,
                due_at_unix_ms,
                completed_at_unix_ms,
            )?;
            let Some(checkpoint) = checkpoint else {
                continue;
            };

            let return_pct = finite_percentage_change(checkpoint.price_usd, baseline.price_usd);
            let Some(return_pct) = return_pct else {
                continue;
            };
            let (mfe_pct, mae_pct) = self.excursions_between(
                candidate_id,
                &baseline,
                checkpoint.observed_at_unix_ms,
            )?;

            let completion = OutcomeCheckpointCompletion {
                baseline_snapshot_id: baseline.id,
                checkpoint_snapshot_id: checkpoint.id,
                completed_at_unix_ms,
                return_pct: Some(return_pct),
                mfe_pct,
                mae_pct,
                liquidity_change_pct: endpoint_percentage_change(
                    checkpoint.liquidity_usd,
                    baseline.liquidity_usd,
                ),
                volume_m5_change_pct: endpoint_percentage_change(
                    checkpoint.volume_m5_usd,
                    baseline.volume_m5_usd,
                ),
                buys_m5_change: endpoint_integer_change(checkpoint.buys_m5, baseline.buys_m5),
                sells_m5_change: endpoint_integer_change(checkpoint.sells_m5, baseline.sells_m5),
                rug_or_dead_pool: None,
                exitability: None,
            };

            self.complete_outcome_checkpoint(candidate_id, horizon_seconds, &completion)?;
            completed = completed.saturating_add(1);
        }

        Ok(completed)
    }

    /// Complete one pending checkpoint exactly once. Both evidence snapshots
    /// must belong to the checkpoint candidate, preventing cross-token metric
    /// contamination when many candidates are measured concurrently.
    pub fn complete_outcome_checkpoint(
        &self,
        candidate_id: i64,
        horizon_seconds: u32,
        completion: &OutcomeCheckpointCompletion,
    ) -> Result<(), StorageError> {
        if candidate_id <= 0 {
            return Err(StorageError::InvalidData(
                "outcome candidate_id must be positive".to_owned(),
            ));
        }
        parse_horizon(i64::from(horizon_seconds))?;
        if completion.baseline_snapshot_id <= 0 || completion.checkpoint_snapshot_id <= 0 {
            return Err(StorageError::InvalidData(
                "outcome snapshot ids must be positive".to_owned(),
            ));
        }

        let transaction = self.connection.unchecked_transaction()?;
        let status = transaction
            .query_row(
                r#"SELECT status
                   FROM candidate_outcome_checkpoints
                   WHERE candidate_id = ?1 AND horizon_seconds = ?2"#,
                params![candidate_id, i64::from(horizon_seconds)],
                |row| row.get::<_, String>(0),
            )
            .optional()?;

        match status.as_deref() {
            Some("pending") => {}
            Some("completed") => {
                return Err(StorageError::InvalidData(format!(
                    "outcome checkpoint for candidate {candidate_id} at {horizon_seconds}s is already completed"
                )));
            }
            Some(other) => {
                return Err(StorageError::InvalidData(format!(
                    "unknown outcome checkpoint status '{other}'"
                )));
            }
            None => {
                return Err(StorageError::InvalidData(format!(
                    "outcome checkpoint for candidate {candidate_id} at {horizon_seconds}s does not exist"
                )));
            }
        }

        for (label, snapshot_id) in [
            ("baseline", completion.baseline_snapshot_id),
            ("checkpoint", completion.checkpoint_snapshot_id),
        ] {
            let owner = transaction
                .query_row(
                    "SELECT candidate_id FROM market_snapshots WHERE id = ?1",
                    [snapshot_id],
                    |row| row.get::<_, i64>(0),
                )
                .optional()?;
            match owner {
                Some(owner) if owner == candidate_id => {}
                Some(owner) => {
                    return Err(StorageError::InvalidData(format!(
                        "outcome {label} snapshot {snapshot_id} belongs to candidate {owner}, not candidate {candidate_id}"
                    )));
                }
                None => {
                    return Err(StorageError::InvalidData(format!(
                        "outcome {label} snapshot {snapshot_id} does not exist for candidate {candidate_id}"
                    )));
                }
            }
        }

        let changed = transaction.execute(
            r#"UPDATE candidate_outcome_checkpoints
               SET status = 'completed',
                   baseline_snapshot_id = ?3,
                   checkpoint_snapshot_id = ?4,
                   completed_at_unix_ms = ?5,
                   return_pct = ?6,
                   mfe_pct = ?7,
                   mae_pct = ?8,
                   liquidity_change_pct = ?9,
                   volume_m5_change_pct = ?10,
                   buys_m5_change = ?11,
                   sells_m5_change = ?12,
                   rug_or_dead_pool = ?13,
                   exitability = ?14
               WHERE candidate_id = ?1
                 AND horizon_seconds = ?2
                 AND status = 'pending'"#,
            params![
                candidate_id,
                i64::from(horizon_seconds),
                completion.baseline_snapshot_id,
                completion.checkpoint_snapshot_id,
                completion.completed_at_unix_ms,
                completion.return_pct,
                completion.mfe_pct,
                completion.mae_pct,
                completion.liquidity_change_pct,
                completion.volume_m5_change_pct,
                completion.buys_m5_change,
                completion.sells_m5_change,
                completion.rug_or_dead_pool.map(i64::from),
                completion.exitability,
            ],
        )?;
        if changed != 1 {
            return Err(StorageError::InvalidData(format!(
                "outcome checkpoint for candidate {candidate_id} at {horizon_seconds}s changed concurrently"
            )));
        }

        transaction.commit()?;
        Ok(())
    }

    fn load_baseline_metric_snapshot(
        &self,
        candidate_id: i64,
        discovered_at_unix_ms: i64,
        completed_at_unix_ms: i64,
    ) -> Result<Option<MetricSnapshot>, StorageError> {
        self.connection
            .query_row(
                r#"SELECT id, observed_at_unix_ms, price_usd, liquidity_usd,
                          volume_m5_usd, buys_m5, sells_m5
                   FROM market_snapshots
                   WHERE candidate_id = ?1
                     AND observed_at_unix_ms >= ?2
                     AND observed_at_unix_ms <= ?3
                     AND price_usd IS NOT NULL
                     AND price_usd > 0
                   ORDER BY observed_at_unix_ms ASC, id ASC
                   LIMIT 1"#,
                params![candidate_id, discovered_at_unix_ms, completed_at_unix_ms],
                metric_snapshot_from_row,
            )
            .optional()
            .map_err(StorageError::from)
    }

    fn load_checkpoint_metric_snapshot(
        &self,
        candidate_id: i64,
        due_at_unix_ms: i64,
        completed_at_unix_ms: i64,
    ) -> Result<Option<MetricSnapshot>, StorageError> {
        self.connection
            .query_row(
                r#"SELECT id, observed_at_unix_ms, price_usd, liquidity_usd,
                          volume_m5_usd, buys_m5, sells_m5
                   FROM market_snapshots
                   WHERE candidate_id = ?1
                     AND observed_at_unix_ms >= ?2
                     AND observed_at_unix_ms <= ?3
                     AND price_usd IS NOT NULL
                   ORDER BY observed_at_unix_ms DESC, id DESC
                   LIMIT 1"#,
                params![candidate_id, due_at_unix_ms, completed_at_unix_ms],
                metric_snapshot_from_row,
            )
            .optional()
            .map_err(StorageError::from)
    }

    fn excursions_between(
        &self,
        candidate_id: i64,
        baseline: &MetricSnapshot,
        checkpoint_observed_at_unix_ms: i64,
    ) -> Result<(Option<f64>, Option<f64>), StorageError> {
        let mut statement = self.connection.prepare(
            r#"SELECT price_usd
               FROM market_snapshots
               WHERE candidate_id = ?1
                 AND observed_at_unix_ms >= ?2
                 AND observed_at_unix_ms <= ?3
                 AND price_usd IS NOT NULL
               ORDER BY observed_at_unix_ms ASC, id ASC"#,
        )?;
        let prices = statement
            .query_map(
                params![
                    candidate_id,
                    baseline.observed_at_unix_ms,
                    checkpoint_observed_at_unix_ms
                ],
                |row| row.get::<_, f64>(0),
            )?
            .collect::<Result<Vec<_>, _>>()?;

        let mut mfe: Option<f64> = None;
        let mut mae: Option<f64> = None;
        for price in prices {
            let Some(change) = finite_percentage_change(price, baseline.price_usd) else {
                continue;
            };
            mfe = Some(mfe.map_or(change, |current| current.max(change)));
            mae = Some(mae.map_or(change, |current| current.min(change)));
        }
        Ok((mfe, mae))
    }
}

fn metric_snapshot_from_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<MetricSnapshot> {
    Ok(MetricSnapshot {
        id: row.get(0)?,
        observed_at_unix_ms: row.get(1)?,
        price_usd: row.get(2)?,
        liquidity_usd: row.get(3)?,
        volume_m5_usd: row.get(4)?,
        buys_m5: row.get(5)?,
        sells_m5: row.get(6)?,
    })
}

fn finite_percentage_change(current: f64, baseline: f64) -> Option<f64> {
    if !current.is_finite() || !baseline.is_finite() || baseline <= 0.0 {
        return None;
    }
    let change = ((current - baseline) / baseline) * 100.0;
    change.is_finite().then_some(change)
}

fn endpoint_percentage_change(current: Option<f64>, baseline: Option<f64>) -> Option<f64> {
    finite_percentage_change(current?, baseline?)
}

fn endpoint_integer_change(current: Option<i64>, baseline: Option<i64>) -> Option<i64> {
    current?.checked_sub(baseline?)
}

fn parse_horizon(value: i64) -> Result<u32, StorageError> {
    let horizon = u32::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!("outcome horizon is outside u32 range: {value}"))
    })?;
    if !OUTCOME_HORIZONS_SECONDS.contains(&horizon) {
        return Err(StorageError::InvalidData(format!(
            "unsupported outcome horizon: {horizon}"
        )));
    }
    Ok(horizon)
}
