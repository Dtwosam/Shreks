use rusqlite::{params, OptionalExtension};
use shreks_core::PairMarketData;

use super::{ShreksDb, StorageError};

pub const PATH_CADENCE_VERSION: &str = "lifecycle_v0";
const FIRST_SAMPLE_OFFSET_MS: i64 = 30_000;
const PATH_LIFECYCLE_MS: i64 = 86_400_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PathSamplingStatus {
    Active,
    Completed,
}

impl PathSamplingStatus {
    fn parse(value: &str) -> Result<Self, StorageError> {
        match value {
            "active" => Ok(Self::Active),
            "completed" => Ok(Self::Completed),
            other => Err(StorageError::InvalidData(format!(
                "unknown path sampling status '{other}'"
            ))),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PathSamplingRecord {
    pub candidate_id: i64,
    pub next_due_at_unix_ms: Option<i64>,
    pub last_sample_at_unix_ms: Option<i64>,
    pub sample_count: u64,
    pub status: PathSamplingStatus,
    pub cadence_version: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DuePathSample {
    pub candidate_id: i64,
    pub mint: String,
    pub due_at_unix_ms: i64,
}

/// Lifecycle-v0 adaptive market-observation cadence.
///
/// The returned value is the target number of seconds after the most recent
/// successful path sample. `None` means the candidate is outside the V0
/// observation lifecycle and should not be adaptively sampled.
pub const fn path_sampling_interval_seconds(age_ms: i64) -> Option<u32> {
    if age_ms < 0 {
        None
    } else if age_ms < 300_000 {
        Some(30)
    } else if age_ms < 900_000 {
        Some(60)
    } else if age_ms < 1_800_000 {
        Some(120)
    } else if age_ms < 3_600_000 {
        Some(300)
    } else if age_ms < 14_400_000 {
        Some(900)
    } else if age_ms < PATH_LIFECYCLE_MS {
        Some(3_600)
    } else {
        None
    }
}

impl ShreksDb {
    /// Insert one normalized market snapshot and report whether SQLite created
    /// a new durable row. This distinguishes fresh adaptive evidence from an
    /// idempotent duplicate that `INSERT OR IGNORE` intentionally discards.
    pub fn insert_market_snapshot_if_new(
        &self,
        candidate_id: i64,
        snapshot: &PairMarketData,
    ) -> Result<bool, StorageError> {
        self.insert_market_snapshot(candidate_id, snapshot)?;
        Ok(self.connection.changes() == 1)
    }

    /// Create the one lifecycle-v0 adaptive schedule for a candidate.
    /// Repeated calls are idempotent and never move an existing schedule.
    pub fn ensure_path_sampling(
        &self,
        candidate_id: i64,
        discovered_at_unix_ms: i64,
    ) -> Result<(), StorageError> {
        if candidate_id <= 0 {
            return Err(StorageError::InvalidData(
                "path sampling candidate_id must be positive".to_owned(),
            ));
        }

        let first_due = discovered_at_unix_ms
            .checked_add(FIRST_SAMPLE_OFFSET_MS)
            .ok_or_else(|| {
                StorageError::InvalidData(
                    "path sampling first due timestamp overflow".to_owned(),
                )
            })?;

        self.connection.execute(
            r#"INSERT OR IGNORE INTO candidate_path_sampling (
                   candidate_id, next_due_at_unix_ms, last_sample_at_unix_ms,
                   sample_count, status, cadence_version
               ) VALUES (?1, ?2, NULL, 0, 'active', ?3)"#,
            params![candidate_id, first_due, PATH_CADENCE_VERSION],
        )?;
        Ok(())
    }

    /// Load one candidate's adaptive path schedule.
    pub fn path_sampling(
        &self,
        candidate_id: i64,
    ) -> Result<Option<PathSamplingRecord>, StorageError> {
        if candidate_id <= 0 {
            return Err(StorageError::InvalidData(
                "path sampling candidate_id must be positive".to_owned(),
            ));
        }

        let raw = self
            .connection
            .query_row(
                r#"SELECT candidate_id, next_due_at_unix_ms, last_sample_at_unix_ms,
                          sample_count, status, cadence_version
                   FROM candidate_path_sampling
                   WHERE candidate_id = ?1"#,
                [candidate_id],
                |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, Option<i64>>(1)?,
                        row.get::<_, Option<i64>>(2)?,
                        row.get::<_, i64>(3)?,
                        row.get::<_, String>(4)?,
                        row.get::<_, String>(5)?,
                    ))
                },
            )
            .optional()?;

        raw.map(
            |(
                candidate_id,
                next_due_at_unix_ms,
                last_sample_at_unix_ms,
                sample_count,
                status,
                cadence_version,
            )| {
                let sample_count = u64::try_from(sample_count).map_err(|_| {
                    StorageError::InvalidData(
                        "path sampling sample_count was negative".to_owned(),
                    )
                })?;
                Ok(PathSamplingRecord {
                    candidate_id,
                    next_due_at_unix_ms,
                    last_sample_at_unix_ms,
                    sample_count,
                    status: PathSamplingStatus::parse(&status)?,
                    cadence_version,
                })
            },
        )
        .transpose()
    }

    /// Return active adaptive schedules whose target time has arrived.
    pub fn due_path_samples(
        &self,
        now_unix_ms: i64,
        limit: usize,
    ) -> Result<Vec<DuePathSample>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("path sampling due limit exceeds i64".to_owned())
        })?;

        let mut statement = self.connection.prepare(
            r#"SELECT p.candidate_id, c.mint, p.next_due_at_unix_ms
               FROM candidate_path_sampling p
               JOIN token_candidates c ON c.id = p.candidate_id
               WHERE p.status = 'active'
                 AND p.next_due_at_unix_ms IS NOT NULL
                 AND p.next_due_at_unix_ms <= ?1
               ORDER BY p.next_due_at_unix_ms ASC, p.candidate_id ASC
               LIMIT ?2"#,
        )?;

        let rows = statement
            .query_map(params![now_unix_ms, limit], |row| {
                Ok(DuePathSample {
                    candidate_id: row.get(0)?,
                    mint: row.get(1)?,
                    due_at_unix_ms: row.get(2)?,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(rows)
    }

    /// Advance one active adaptive schedule after a real market observation.
    ///
    /// The next target is always computed from the actual successful sample
    /// timestamp. Missed historical intervals are never replayed. When the
    /// next target would reach or cross the 24-hour lifecycle boundary, the
    /// schedule becomes terminal instead of scheduling another request.
    pub fn advance_path_sampling(
        &self,
        candidate_id: i64,
        sampled_at_unix_ms: i64,
    ) -> Result<(), StorageError> {
        if candidate_id <= 0 {
            return Err(StorageError::InvalidData(
                "path sampling candidate_id must be positive".to_owned(),
            ));
        }

        let transaction = self.connection.unchecked_transaction()?;
        let current = transaction
            .query_row(
                r#"SELECT c.discovered_at_unix_ms, p.status
                   FROM candidate_path_sampling p
                   JOIN token_candidates c ON c.id = p.candidate_id
                   WHERE p.candidate_id = ?1"#,
                [candidate_id],
                |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?)),
            )
            .optional()?;

        let Some((discovered_at_unix_ms, status)) = current else {
            return Err(StorageError::InvalidData(format!(
                "path sampling schedule missing for candidate {candidate_id}"
            )));
        };
        if status == "completed" {
            return Err(StorageError::InvalidData(format!(
                "path sampling schedule for candidate {candidate_id} is already completed"
            )));
        }
        if status != "active" {
            return Err(StorageError::InvalidData(format!(
                "unknown path sampling status '{status}'"
            )));
        }
        if sampled_at_unix_ms < discovered_at_unix_ms {
            return Err(StorageError::InvalidData(
                "path sample timestamp is before discovery".to_owned(),
            ));
        }

        let age_ms = sampled_at_unix_ms
            .checked_sub(discovered_at_unix_ms)
            .ok_or_else(|| {
                StorageError::InvalidData("path sampling age calculation overflow".to_owned())
            })?;
        let lifecycle_end = discovered_at_unix_ms
            .checked_add(PATH_LIFECYCLE_MS)
            .ok_or_else(|| {
                StorageError::InvalidData("path sampling lifecycle timestamp overflow".to_owned())
            })?;

        let next_due = path_sampling_interval_seconds(age_ms)
            .map(|seconds| {
                sampled_at_unix_ms
                    .checked_add(i64::from(seconds) * 1_000)
                    .ok_or_else(|| {
                        StorageError::InvalidData(
                            "path sampling next due timestamp overflow".to_owned(),
                        )
                    })
            })
            .transpose()?;

        let should_complete = next_due.is_none_or(|next_due| next_due >= lifecycle_end);
        let changed = if should_complete {
            transaction.execute(
                r#"UPDATE candidate_path_sampling
                   SET next_due_at_unix_ms = NULL,
                       last_sample_at_unix_ms = ?2,
                       sample_count = sample_count + 1,
                       status = 'completed'
                   WHERE candidate_id = ?1 AND status = 'active'"#,
                params![candidate_id, sampled_at_unix_ms],
            )?
        } else {
            transaction.execute(
                r#"UPDATE candidate_path_sampling
                   SET next_due_at_unix_ms = ?2,
                       last_sample_at_unix_ms = ?3,
                       sample_count = sample_count + 1
                   WHERE candidate_id = ?1 AND status = 'active'"#,
                params![candidate_id, next_due, sampled_at_unix_ms],
            )?
        };

        if changed != 1 {
            return Err(StorageError::InvalidData(format!(
                "cannot advance path sampling for candidate {candidate_id}: schedule is no longer active"
            )));
        }

        transaction.commit()?;
        Ok(())
    }
}
