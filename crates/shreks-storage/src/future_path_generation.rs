use shreks_core::{
    label_future_paths, FuturePathCoverage, FuturePathDecision, FuturePathLabel,
    FuturePathObservation,
};

use super::{ShreksDb, StorageError};

impl ShreksDb {
    /// Return canonical future observations for one exact decision through an
    /// inclusive canonical observation-time boundary.
    ///
    /// This deliberately reuses `fast_events_for_market`, including its
    /// source-conflict quarantine checks, so FL4 cannot create a second trust
    /// policy for ambiguous canonical evidence. Occurrence time is not used as
    /// the future-information clock.
    pub fn future_path_observations_for_decision(
        &self,
        decision: &FuturePathDecision,
        through_observed_at_unix_ms: i64,
    ) -> Result<Vec<FuturePathObservation>, StorageError> {
        if through_observed_at_unix_ms < decision.observed_at_unix_ms {
            return Err(StorageError::InvalidData(format!(
                "future-path observation boundary {} precedes decision observation {}",
                through_observed_at_unix_ms, decision.observed_at_unix_ms
            )));
        }

        let replay = self.fast_events_for_market(
            &decision.market.mint,
            &decision.market.quote_mint,
            decision.market.venue,
        )?;

        let canonical_decision = replay
            .iter()
            .find(|stored| stored.event.sequence == decision.sequence)
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "future-path decision sequence {} is missing from canonical market replay",
                    decision.sequence
                ))
            })?;
        if canonical_decision.event.id != decision.event_id
            || canonical_decision.event.market != decision.market
            || canonical_decision.event.observed_at_unix_ms != decision.observed_at_unix_ms
            || canonical_decision.event.price_quote != decision.executable_entry_price_quote
        {
            return Err(StorageError::InvalidData(format!(
                "future-path decision '{}' ordinal {} does not match canonical market replay",
                decision.event_id.signature, decision.event_id.ordinal
            )));
        }

        Ok(replay
            .into_iter()
            .filter(|stored| {
                stored.event.sequence > decision.sequence
                    && stored.event.observed_at_unix_ms > decision.observed_at_unix_ms
                    && stored.event.observed_at_unix_ms <= through_observed_at_unix_ms
            })
            .map(|stored| FuturePathObservation::from_event(stored.event))
            .collect())
    }

    /// Generate price/path labels from canonical future FastEvents. Route,
    /// capacity, and execution-economics annotations remain unknown here; a
    /// caller may attach authoritative source-backed annotations before using
    /// the pure core labeler when that evidence exists.
    pub fn generate_future_path_labels_for_decision(
        &self,
        decision: &FuturePathDecision,
        coverage: FuturePathCoverage,
        horizons_ms: &[u64],
    ) -> Result<Vec<FuturePathLabel>, StorageError> {
        let maximum_horizon_ms = horizons_ms.iter().copied().max().ok_or_else(|| {
            StorageError::InvalidData("future-path horizons must not be empty".to_owned())
        })?;
        let maximum_horizon_ms = i64::try_from(maximum_horizon_ms).map_err(|_| {
            StorageError::InvalidData(
                "future-path maximum horizon exceeds i64 milliseconds".to_owned(),
            )
        })?;
        let through_observed_at_unix_ms = decision
            .observed_at_unix_ms
            .checked_add(maximum_horizon_ms)
            .ok_or_else(|| {
                StorageError::InvalidData("future-path horizon timestamp overflowed".to_owned())
            })?;

        let observations = self.future_path_observations_for_decision(
            decision,
            through_observed_at_unix_ms,
        )?;
        label_future_paths(decision, &observations, coverage, horizons_ms).map_err(|error| {
            StorageError::InvalidData(format!("future-path label generation failed: {error}"))
        })
    }
}
