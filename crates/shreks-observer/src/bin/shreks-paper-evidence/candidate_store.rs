use std::{error::Error, fmt, path::Path};

use rusqlite::{params, Connection, OpenFlags, OptionalExtension};

const REQUIRED_TABLE_COLUMNS: &[(&str, &[&str])] = &[
    ("token_candidates", &["id", "mint"]),
    (
        "market_snapshots",
        &[
            "candidate_id",
            "observed_at_unix_ms",
            "source",
            "pair_created_at_unix_ms",
        ],
    ),
    (
        "token_holder_distributions",
        &["candidate_id", "observed_at_unix_ms"],
    ),
    (
        "token_mint_states",
        &["candidate_id", "provider", "observed_at_unix_ms"],
    ),
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvidenceProbeCandidate {
    pub candidate_id: i64,
    pub mint: String,
    pub latest_market_observed_at_unix_ms: i64,
}

#[derive(Debug)]
pub enum EvidenceCandidateStoreError {
    Sqlite(rusqlite::Error),
    InvalidData(String),
}

impl fmt::Display for EvidenceCandidateStoreError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Sqlite(error) => write!(formatter, "evidence candidate SQLite error: {error}"),
            Self::InvalidData(message) => write!(formatter, "invalid evidence candidate data: {message}"),
        }
    }
}

impl Error for EvidenceCandidateStoreError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Sqlite(error) => Some(error),
            Self::InvalidData(_) => None,
        }
    }
}

pub struct EvidenceCandidateStore {
    connection: Connection,
}

impl fmt::Debug for EvidenceCandidateStore {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("EvidenceCandidateStore")
            .finish_non_exhaustive()
    }
}

impl EvidenceCandidateStore {
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self, EvidenceCandidateStoreError> {
        let path = path.as_ref();
        if path.as_os_str().is_empty() {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "database path must not be empty".to_owned(),
            ));
        }

        let connection = Connection::open_with_flags(
            path,
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )
        .map_err(|error| {
            EvidenceCandidateStoreError::InvalidData(format!(
                "unable to open observer database read-only: {error}"
            ))
        })?;

        validate_schema(&connection)?;
        Ok(Self { connection })
    }

    pub fn recent_candidates(
        &self,
        as_of_unix_ms: i64,
        lookback_ms: i64,
        limit: usize,
    ) -> Result<Vec<EvidenceProbeCandidate>, EvidenceCandidateStoreError> {
        validate_window(as_of_unix_ms, lookback_ms)?;
        if limit == 0 {
            return Ok(Vec::new());
        }

        let minimum_observed_at_unix_ms = as_of_unix_ms.saturating_sub(lookback_ms).max(0);
        let sqlite_limit = sqlite_limit(limit)?;

        let mut statement = self
            .connection
            .prepare(
                r#"SELECT
                       tc.id,
                       tc.mint,
                       MAX(ms.observed_at_unix_ms) AS latest_market_observed_at_unix_ms
                   FROM token_candidates AS tc
                   JOIN market_snapshots AS ms ON ms.candidate_id = tc.id
                   WHERE ms.observed_at_unix_ms BETWEEN ?1 AND ?2
                   GROUP BY tc.id, tc.mint
                   ORDER BY latest_market_observed_at_unix_ms DESC, tc.id ASC
                   LIMIT ?3"#,
            )
            .map_err(EvidenceCandidateStoreError::Sqlite)?;

        let rows = statement
            .query_map(
                params![minimum_observed_at_unix_ms, as_of_unix_ms, sqlite_limit],
                |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, i64>(2)?,
                    ))
                },
            )
            .map_err(EvidenceCandidateStoreError::Sqlite)?;

        collect_candidates(rows, minimum_observed_at_unix_ms, as_of_unix_ms)
    }

    pub fn fresh_launch_candidates(
        &self,
        as_of_unix_ms: i64,
        current_market_lookback_ms: i64,
        max_pair_age_ms: i64,
        preferred_min_pair_age_ms: i64,
        market_sources: &[String],
        required_quote_mint: &str,
        limit: usize,
    ) -> Result<Vec<EvidenceProbeCandidate>, EvidenceCandidateStoreError> {
        validate_window(as_of_unix_ms, current_market_lookback_ms)?;
        validate_window(as_of_unix_ms, max_pair_age_ms)?;
        if preferred_min_pair_age_ms < 0 {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "preferred_min_pair_age_ms must be non-negative".to_owned(),
            ));
        }
        if preferred_min_pair_age_ms > max_pair_age_ms {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "preferred_min_pair_age_ms cannot exceed max_pair_age_ms".to_owned(),
            ));
        }
        validate_market_sources(market_sources)?;
        validate_required_quote_mint(required_quote_mint)?;
        validate_required_table(
            &self.connection,
            ("market_snapshots", &["base_mint", "quote_mint"]),
        )?;
        if limit == 0 {
            return Ok(Vec::new());
        }

        let current_market_cutoff = as_of_unix_ms
            .saturating_sub(current_market_lookback_ms)
            .max(0);
        let oldest_allowed_created_at_unix_ms =
            as_of_unix_ms.saturating_sub(max_pair_age_ms).max(0);
        let preferred_created_at_ceiling = as_of_unix_ms
            .saturating_sub(preferred_min_pair_age_ms)
            .max(0);

        let mut statement = self
            .connection
            .prepare(
                r#"SELECT
                       tc.id,
                       tc.mint,
                       MAX(ms.observed_at_unix_ms) AS latest_market_observed_at_unix_ms
                   FROM token_candidates AS tc
                   JOIN market_snapshots AS ms ON ms.candidate_id = tc.id
                   WHERE ms.observed_at_unix_ms BETWEEN ?1 AND ?2
                   GROUP BY tc.id, tc.mint
                   ORDER BY latest_market_observed_at_unix_ms DESC, tc.id ASC"#,
            )
            .map_err(EvidenceCandidateStoreError::Sqlite)?;

        let rows = statement
            .query_map(
                params![current_market_cutoff, as_of_unix_ms],
                |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, i64>(2)?,
                    ))
                },
            )
            .map_err(EvidenceCandidateStoreError::Sqlite)?;

        let candidates =
            collect_candidates(rows, current_market_cutoff, as_of_unix_ms)?;
        let mut eligible: Vec<(u8, EvidenceProbeCandidate)> = Vec::new();

        for candidate in candidates {
            let Some((current_observed_at_unix_ms, pair_created_at_unix_ms)) =
                current_market_snapshot_metadata(
                    &self.connection,
                    candidate.candidate_id,
                    &candidate.mint,
                    current_market_cutoff,
                    as_of_unix_ms,
                    market_sources,
                    required_quote_mint,
                )?
            else {
                continue;
            };

            if pair_created_at_unix_ms < oldest_allowed_created_at_unix_ms
                || pair_created_at_unix_ms > as_of_unix_ms
            {
                continue;
            }

            let age_priority =
                if pair_created_at_unix_ms <= preferred_created_at_ceiling {
                    0
                } else {
                    1
                };

            eligible.push((
                age_priority,
                EvidenceProbeCandidate {
                    candidate_id: candidate.candidate_id,
                    mint: candidate.mint,
                    latest_market_observed_at_unix_ms: current_observed_at_unix_ms,
                },
            ));
        }

        eligible.sort_by(|(left_priority, left), (right_priority, right)| {
            left_priority
                .cmp(right_priority)
                .then_with(|| {
                    right
                        .latest_market_observed_at_unix_ms
                        .cmp(&left.latest_market_observed_at_unix_ms)
                })
                .then_with(|| left.candidate_id.cmp(&right.candidate_id))
        });

        Ok(eligible
            .into_iter()
            .take(limit)
            .map(|(_, candidate)| candidate)
            .collect())
    }

    pub fn has_mint_state_since(
        &self,
        candidate_id: i64,
        minimum_observed_at_unix_ms: i64,
        as_of_unix_ms: i64,
    ) -> Result<bool, EvidenceCandidateStoreError> {
        if candidate_id <= 0 {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "candidate id must be positive".to_owned(),
            ));
        }
        if minimum_observed_at_unix_ms < 0 || as_of_unix_ms < 0 {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "mint-state freshness timestamps must be non-negative".to_owned(),
            ));
        }
        if minimum_observed_at_unix_ms > as_of_unix_ms {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "mint-state freshness minimum timestamp cannot exceed as_of_unix_ms".to_owned(),
            ));
        }

        validate_required_table(&self.connection, REQUIRED_TABLE_COLUMNS[3])?;
        let found = self
            .connection
            .query_row(
                r#"SELECT 1
                   FROM token_mint_states
                   WHERE candidate_id = ?1
                     AND provider = 'helius'
                     AND observed_at_unix_ms BETWEEN ?2 AND ?3
                   ORDER BY observed_at_unix_ms DESC
                   LIMIT 1"#,
                params![candidate_id, minimum_observed_at_unix_ms, as_of_unix_ms],
                |_| Ok(()),
            )
            .optional()
            .map_err(EvidenceCandidateStoreError::Sqlite)?;
        Ok(found.is_some())
    }

    pub fn has_holder_distribution_since(
        &self,
        candidate_id: i64,
        minimum_observed_at_unix_ms: i64,
        as_of_unix_ms: i64,
    ) -> Result<bool, EvidenceCandidateStoreError> {
        if candidate_id <= 0 {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "candidate id must be positive".to_owned(),
            ));
        }
        if minimum_observed_at_unix_ms < 0 || as_of_unix_ms < 0 {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "holder freshness timestamps must be non-negative".to_owned(),
            ));
        }
        if minimum_observed_at_unix_ms > as_of_unix_ms {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "holder freshness minimum timestamp cannot exceed as_of_unix_ms".to_owned(),
            ));
        }

        validate_required_table(&self.connection, REQUIRED_TABLE_COLUMNS[2])?;
        let found = self
            .connection
            .query_row(
                r#"SELECT 1
                   FROM token_holder_distributions
                   WHERE candidate_id = ?1
                     AND observed_at_unix_ms BETWEEN ?2 AND ?3
                   ORDER BY observed_at_unix_ms DESC
                   LIMIT 1"#,
                params![candidate_id, minimum_observed_at_unix_ms, as_of_unix_ms],
                |_| Ok(()),
            )
            .optional()
            .map_err(EvidenceCandidateStoreError::Sqlite)?;
        Ok(found.is_some())
    }
}

fn current_market_snapshot_metadata(
    connection: &Connection,
    candidate_id: i64,
    candidate_mint: &str,
    minimum_observed_at_unix_ms: i64,
    as_of_unix_ms: i64,
    market_sources: &[String],
    required_quote_mint: &str,
) -> Result<Option<(i64, i64)>, EvidenceCandidateStoreError> {
    for source in market_sources {
        let row = connection
            .query_row(
                r#"SELECT observed_at_unix_ms, pair_created_at_unix_ms
                   FROM market_snapshots
                   WHERE candidate_id = ?1
                     AND source = ?2
                     AND base_mint = ?3
                     AND quote_mint = ?4
                     AND observed_at_unix_ms BETWEEN ?5 AND ?6
                     AND pair_created_at_unix_ms IS NOT NULL
                     AND pair_created_at_unix_ms <= observed_at_unix_ms
                   ORDER BY observed_at_unix_ms DESC, id ASC
                   LIMIT 1"#,
                params![
                    candidate_id,
                    source,
                    candidate_mint,
                    required_quote_mint,
                    minimum_observed_at_unix_ms,
                    as_of_unix_ms,
                ],
                |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?)),
            )
            .optional()
            .map_err(EvidenceCandidateStoreError::Sqlite)?;

        if row.is_some() {
            return Ok(row);
        }
    }

    Ok(None)
}

fn validate_required_quote_mint(
    required_quote_mint: &str,
) -> Result<(), EvidenceCandidateStoreError> {
    if required_quote_mint.trim().is_empty() {
        return Err(EvidenceCandidateStoreError::InvalidData(
            "required_quote_mint must not be blank".to_owned(),
        ));
    }
    Ok(())
}

fn validate_window(
    as_of_unix_ms: i64,
    lookback_ms: i64,
) -> Result<(), EvidenceCandidateStoreError> {
    if as_of_unix_ms < 0 {
        return Err(EvidenceCandidateStoreError::InvalidData(
            "as_of_unix_ms must be non-negative".to_owned(),
        ));
    }
    if lookback_ms <= 0 {
        return Err(EvidenceCandidateStoreError::InvalidData(
            "lookback_ms must be positive".to_owned(),
        ));
    }
    Ok(())
}

fn validate_market_sources(market_sources: &[String]) -> Result<(), EvidenceCandidateStoreError> {
    if market_sources.is_empty() {
        return Err(EvidenceCandidateStoreError::InvalidData(
            "market_sources must not be empty".to_owned(),
        ));
    }
    for (index, source) in market_sources.iter().enumerate() {
        if source.trim().is_empty() {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "market_sources must not contain blank values".to_owned(),
            ));
        }
        if market_sources[..index].iter().any(|existing| existing == source) {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "market_sources must not contain duplicates".to_owned(),
            ));
        }
    }
    Ok(())
}

fn sqlite_limit(limit: usize) -> Result<i64, EvidenceCandidateStoreError> {
    i64::try_from(limit).map_err(|_| {
        EvidenceCandidateStoreError::InvalidData(
            "candidate limit exceeds SQLite signed integer range".to_owned(),
        )
    })
}

fn collect_candidates<M>(
    rows: M,
    minimum_observed_at_unix_ms: i64,
    as_of_unix_ms: i64,
) -> Result<Vec<EvidenceProbeCandidate>, EvidenceCandidateStoreError>
where
    M: Iterator<Item = Result<(i64, String, i64), rusqlite::Error>>,
{
    let mut candidates = Vec::new();
    for row in rows {
        let (candidate_id, mint, latest_market_observed_at_unix_ms) =
            row.map_err(EvidenceCandidateStoreError::Sqlite)?;
        if candidate_id <= 0 {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "candidate id must be positive".to_owned(),
            ));
        }
        if mint.trim().is_empty() {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "candidate mint must not be blank".to_owned(),
            ));
        }
        if latest_market_observed_at_unix_ms < minimum_observed_at_unix_ms
            || latest_market_observed_at_unix_ms > as_of_unix_ms
        {
            return Err(EvidenceCandidateStoreError::InvalidData(
                "candidate market timestamp is outside the requested point-in-time window"
                    .to_owned(),
            ));
        }
        candidates.push(EvidenceProbeCandidate {
            candidate_id,
            mint,
            latest_market_observed_at_unix_ms,
        });
    }
    Ok(candidates)
}

fn validate_schema(connection: &Connection) -> Result<(), EvidenceCandidateStoreError> {
    for required in &REQUIRED_TABLE_COLUMNS[..2] {
        validate_required_table(connection, *required)?;
    }
    Ok(())
}

fn validate_required_table(
    connection: &Connection,
    (table, required_columns): (&str, &[&str]),
) -> Result<(), EvidenceCandidateStoreError> {
    let exists: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?1",
            [table],
            |row| row.get(0),
        )
        .map_err(EvidenceCandidateStoreError::Sqlite)?;
    if exists != 1 {
        return Err(EvidenceCandidateStoreError::InvalidData(format!(
            "observer database missing required table {table}"
        )));
    }

    let pragma = format!("PRAGMA table_info({table})");
    let mut statement = connection
        .prepare(&pragma)
        .map_err(EvidenceCandidateStoreError::Sqlite)?;
    let columns = statement
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(EvidenceCandidateStoreError::Sqlite)?
        .collect::<Result<Vec<_>, _>>()
        .map_err(EvidenceCandidateStoreError::Sqlite)?;

    for required in required_columns {
        if !columns.iter().any(|column| column == required) {
            return Err(EvidenceCandidateStoreError::InvalidData(format!(
                "observer database table {table} missing required column {required}"
            )));
        }
    }
    Ok(())
}
