use rusqlite::params;
use serde::Serialize;
use shreks_core::{
    label_future_paths, FastMarketKey, FuturePathCoverage, FuturePathDecision, FuturePathLabel,
    FuturePathObservation, DEFAULT_FUTURE_PATH_HORIZONS_MS, FUTURE_PATH_LABEL_VERSION,
};

use crate::{training_features::parse_training_venue, ShreksDb, StorageError};

pub const FAST_COVERED_FUTURE_PATH_POPULATION_SCHEMA_NAME: &str =
    "shreks.fast_covered_future_path_population";
pub const FAST_COVERED_FUTURE_PATH_POPULATION_SCHEMA_VERSION: u16 = 1;

const SAVEPOINT_NAME: &str = "shreks_fl4_covered_event_population";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FastCoveredFuturePathPopulationRequest {
    pub coverage_session_id: u64,
    pub from_observed_at_unix_ms: i64,
    pub through_observed_at_unix_ms: i64,
    pub maximum_decisions: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FastCoveredFuturePathPopulationReport {
    pub schema_name: String,
    pub schema_version: u16,
    pub future_path_label_version: u16,
    pub coverage_session_id: u64,
    pub coverage_provider: String,
    pub from_observed_at_unix_ms: i64,
    pub through_observed_at_unix_ms: i64,
    pub coverage_complete_through_unix_ms: i64,
    pub decision_count: u64,
    pub inserted_label_count: u64,
    pub already_existing_label_count: u64,
    pub min_decision_sequence: u64,
    pub max_decision_sequence: u64,
    pub horizons_ms: Vec<u64>,
}

#[derive(Debug)]
struct PreparedDecisionLabels {
    decision: FuturePathDecision,
    coverage: FuturePathCoverage,
    labels: Vec<FuturePathLabel>,
}

pub fn populate_fast_future_path_labels(
    db: &ShreksDb,
    request: &FastCoveredFuturePathPopulationRequest,
) -> Result<FastCoveredFuturePathPopulationReport, StorageError> {
    validate_request(request)?;

    let sessions = db.fast_realtime_coverage_sessions()?;
    let latest = sessions.last().ok_or_else(|| {
        StorageError::InvalidData(
            "covered FL4 population requires at least one realtime coverage session".to_owned(),
        )
    })?;
    let session = sessions
        .iter()
        .find(|candidate| candidate.session_id == request.coverage_session_id)
        .ok_or_else(|| {
            StorageError::InvalidData(format!(
                "realtime coverage session {} does not exist",
                request.coverage_session_id
            ))
        })?;
    if session.session_id == latest.session_id {
        return Err(StorageError::InvalidData(format!(
            "realtime coverage session {} is the latest mutable session",
            session.session_id
        )));
    }
    if request.from_observed_at_unix_ms < session.first_notification_observed_at_unix_ms
        || request.through_observed_at_unix_ms > session.last_notification_observed_at_unix_ms
    {
        return Err(StorageError::InvalidData(format!(
            "covered FL4 decision window [{}, {}] is not fully enclosed by coverage session {} [{}, {}]",
            request.from_observed_at_unix_ms,
            request.through_observed_at_unix_ms,
            session.session_id,
            session.first_notification_observed_at_unix_ms,
            session.last_notification_observed_at_unix_ms
        )));
    }

    let decision_count = count_window_events(db, request)?;
    if decision_count == 0 {
        return Err(StorageError::InvalidData(
            "covered FL4 decision window contains no canonical FastEvents".to_owned(),
        ));
    }
    if decision_count > request.maximum_decisions {
        return Err(StorageError::InvalidData(format!(
            "covered FL4 decision count {decision_count} exceeds explicit maximum {}",
            request.maximum_decisions
        )));
    }

    let coverage = FuturePathCoverage::new(
        session.last_notification_observed_at_unix_ms,
        true,
    )
    .map_err(|error| {
        StorageError::InvalidData(format!(
            "covered FL4 coverage construction failed: {error}"
        ))
    })?;
    let markets = markets_in_window(db, request)?;
    let prepared = prepare_labels(db, request, coverage, &markets)?;
    let prepared_count = u64::try_from(prepared.len()).map_err(|_| {
        StorageError::InvalidData(
            "covered FL4 prepared decision count exceeds u64".to_owned(),
        )
    })?;
    if prepared_count != decision_count {
        return Err(StorageError::InvalidData(format!(
            "covered FL4 canonical replay selected {prepared_count} decisions but SQL preflight counted {decision_count}"
        )));
    }

    let min_decision_sequence = prepared
        .iter()
        .map(|row| row.decision.sequence)
        .min()
        .expect("positive preflight count produces prepared decisions");
    let max_decision_sequence = prepared
        .iter()
        .map(|row| row.decision.sequence)
        .max()
        .expect("positive preflight count produces prepared decisions");

    db.connection
        .execute_batch(&format!("SAVEPOINT {SAVEPOINT_NAME};"))?;
    let write_result = write_prepared_labels(db, &prepared);
    let (inserted_label_count, already_existing_label_count) = match write_result {
        Ok(counts) => {
            db.connection
                .execute_batch(&format!("RELEASE {SAVEPOINT_NAME};"))?;
            counts
        }
        Err(error) => {
            let rollback = db.connection.execute_batch(&format!(
                "ROLLBACK TO {SAVEPOINT_NAME}; RELEASE {SAVEPOINT_NAME};"
            ));
            if let Err(rollback_error) = rollback {
                return Err(StorageError::InvalidData(format!(
                    "covered FL4 population failed: {error}; savepoint rollback also failed: {rollback_error}"
                )));
            }
            return Err(error);
        }
    };

    Ok(FastCoveredFuturePathPopulationReport {
        schema_name: FAST_COVERED_FUTURE_PATH_POPULATION_SCHEMA_NAME.to_owned(),
        schema_version: FAST_COVERED_FUTURE_PATH_POPULATION_SCHEMA_VERSION,
        future_path_label_version: FUTURE_PATH_LABEL_VERSION,
        coverage_session_id: session.session_id,
        coverage_provider: session.provider.as_str().to_owned(),
        from_observed_at_unix_ms: request.from_observed_at_unix_ms,
        through_observed_at_unix_ms: request.through_observed_at_unix_ms,
        coverage_complete_through_unix_ms: session.last_notification_observed_at_unix_ms,
        decision_count,
        inserted_label_count,
        already_existing_label_count,
        min_decision_sequence,
        max_decision_sequence,
        horizons_ms: DEFAULT_FUTURE_PATH_HORIZONS_MS.to_vec(),
    })
}

fn validate_request(
    request: &FastCoveredFuturePathPopulationRequest,
) -> Result<(), StorageError> {
    if request.coverage_session_id == 0 {
        return Err(StorageError::InvalidData(
            "covered FL4 coverage session id must be positive".to_owned(),
        ));
    }
    if request.from_observed_at_unix_ms < 0
        || request.through_observed_at_unix_ms < 0
        || request.from_observed_at_unix_ms > request.through_observed_at_unix_ms
    {
        return Err(StorageError::InvalidData(
            "covered FL4 decision observation bounds are invalid".to_owned(),
        ));
    }
    if request.maximum_decisions == 0 {
        return Err(StorageError::InvalidData(
            "covered FL4 maximum decisions must be positive".to_owned(),
        ));
    }
    Ok(())
}

fn count_window_events(
    db: &ShreksDb,
    request: &FastCoveredFuturePathPopulationRequest,
) -> Result<u64, StorageError> {
    let raw: i64 = db.connection.query_row(
        r#"SELECT COUNT(*)
           FROM fast_events
           WHERE observed_at_unix_ms >= ?1
             AND observed_at_unix_ms <= ?2"#,
        params![
            request.from_observed_at_unix_ms,
            request.through_observed_at_unix_ms
        ],
        |row| row.get(0),
    )?;
    u64::try_from(raw).map_err(|_| {
        StorageError::InvalidData(
            "covered FL4 canonical event count was negative".to_owned(),
        )
    })
}

fn markets_in_window(
    db: &ShreksDb,
    request: &FastCoveredFuturePathPopulationRequest,
) -> Result<Vec<FastMarketKey>, StorageError> {
    let mut statement = db.connection.prepare(
        r#"SELECT DISTINCT mint, quote_mint, venue
           FROM fast_events
           WHERE observed_at_unix_ms >= ?1
             AND observed_at_unix_ms <= ?2
           ORDER BY mint ASC, quote_mint ASC, venue ASC"#,
    )?;
    let raw = statement
        .query_map(
            params![
                request.from_observed_at_unix_ms,
                request.through_observed_at_unix_ms
            ],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            },
        )?
        .collect::<Result<Vec<_>, _>>()?;

    raw.into_iter()
        .map(|(mint, quote_mint, venue)| {
            let venue = parse_training_venue(&venue)?;
            FastMarketKey::new(mint, quote_mint, venue).map_err(|error| {
                StorageError::InvalidData(format!(
                    "covered FL4 market identity is invalid: {error}"
                ))
            })
        })
        .collect()
}

fn prepare_labels(
    db: &ShreksDb,
    request: &FastCoveredFuturePathPopulationRequest,
    coverage: FuturePathCoverage,
    markets: &[FastMarketKey],
) -> Result<Vec<PreparedDecisionLabels>, StorageError> {
    let maximum_horizon_ms = *DEFAULT_FUTURE_PATH_HORIZONS_MS
        .last()
        .expect("sealed FL4 default horizons are non-empty");
    let maximum_horizon_ms = i64::try_from(maximum_horizon_ms).map_err(|_| {
        StorageError::InvalidData(
            "covered FL4 maximum horizon exceeds i64 milliseconds".to_owned(),
        )
    })?;
    let mut prepared = Vec::new();

    for market in markets {
        let replay = db.fast_events_for_market(
            &market.mint,
            &market.quote_mint,
            market.venue,
        )?;

        for stored in replay.iter().filter(|stored| {
            stored.event.observed_at_unix_ms >= request.from_observed_at_unix_ms
                && stored.event.observed_at_unix_ms <= request.through_observed_at_unix_ms
        }) {
            let decision = FuturePathDecision::new(
                stored.event.market.clone(),
                stored.event.id.clone(),
                stored.event.sequence,
                stored.event.observed_at_unix_ms,
                stored.event.price_quote,
            )
            .map_err(|error| {
                StorageError::InvalidData(format!(
                    "covered FL4 decision construction failed: {error}"
                ))
            })?;
            let observation_end = decision
                .observed_at_unix_ms
                .checked_add(maximum_horizon_ms)
                .ok_or_else(|| {
                    StorageError::InvalidData(
                        "covered FL4 future observation timestamp overflowed".to_owned(),
                    )
                })?;
            let observations = replay
                .iter()
                .filter(|candidate| {
                    candidate.event.sequence > decision.sequence
                        && candidate.event.observed_at_unix_ms
                            > decision.observed_at_unix_ms
                        && candidate.event.observed_at_unix_ms <= observation_end
                })
                .map(|candidate| FuturePathObservation::from_event(candidate.event.clone()))
                .collect::<Vec<_>>();
            let labels = label_future_paths(
                &decision,
                &observations,
                coverage,
                &DEFAULT_FUTURE_PATH_HORIZONS_MS,
            )
            .map_err(|error| {
                StorageError::InvalidData(format!(
                    "covered FL4 label generation failed: {error}"
                ))
            })?;

            prepared.push(PreparedDecisionLabels {
                decision,
                coverage,
                labels,
            });
        }
    }

    prepared.sort_by(|left, right| {
        left.decision
            .sequence
            .cmp(&right.decision.sequence)
            .then_with(|| {
                left.decision
                    .event_id
                    .signature
                    .cmp(&right.decision.event_id.signature)
            })
            .then_with(|| {
                left.decision
                    .event_id
                    .ordinal
                    .cmp(&right.decision.event_id.ordinal)
            })
    });
    Ok(prepared)
}

fn write_prepared_labels(
    db: &ShreksDb,
    prepared: &[PreparedDecisionLabels],
) -> Result<(u64, u64), StorageError> {
    let mut inserted = 0_u64;
    let mut existing = 0_u64;

    for row in prepared {
        for label in &row.labels {
            if db.record_future_path_label(&row.decision, row.coverage, label)? {
                inserted = inserted.checked_add(1).ok_or_else(|| {
                    StorageError::InvalidData(
                        "covered FL4 inserted label count overflowed".to_owned(),
                    )
                })?;
            } else {
                existing = existing.checked_add(1).ok_or_else(|| {
                    StorageError::InvalidData(
                        "covered FL4 existing label count overflowed".to_owned(),
                    )
                })?;
            }
        }
    }

    Ok((inserted, existing))
}
