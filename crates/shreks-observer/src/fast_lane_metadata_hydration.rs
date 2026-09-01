#[path = "sqlite_busy_retry.rs"]
mod sqlite_busy_retry;

use std::collections::HashMap;

use shreks_core::ProviderId;
use sqlite_busy_retry::{is_storage_sqlite_busy_or_locked, retry_bounded};

use crate::{
    record_adapter_failure, record_synthetic_failure, CycleHealth, Observer, ObserverCycleReport,
    ObserverError, PacingLane,
};

const FAST_LANE_METADATA_HYDRATION_BUDGET: usize = 64;

impl Observer {
    /// Hydrate only the verified mint-state prerequisite needed by canonical
    /// fast-lane normalization, using the public Solana chain adapter only.
    ///
    /// Raw evidence remains the restart-safe queue. The selector prioritizes
    /// fresh active mints while reserving bounded capacity for historical debt.
    /// This fixed per-cycle budget is sized to outrun the production FL1 mint
    /// arrival rate while the public Solana provider's own 4-RPS pacing ceiling
    /// still prevents an unbounded RPC burst. Provider failures are isolated in
    /// normal observer health state. Candidate identity and verified mint state
    /// are persisted together after the provider call, using the same bounded
    /// SQLite BUSY/LOCKED recovery as other hot write paths. If that bounded
    /// recovery is exhausted, metadata enrichment is safely deferred: raw
    /// evidence remains durable and canonicalization continues to fail closed
    /// until a later cycle can persist the verified state. Non-contention
    /// storage and integrity failures remain fatal. No market, strategy,
    /// signing, execution, or paid-provider authority is introduced here.
    pub(crate) async fn hydrate_fast_lane_mint_metadata(
        &mut self,
        report: &mut ObserverCycleReport,
        health: &mut HashMap<ProviderId, CycleHealth>,
    ) -> Result<(), ObserverError> {
        let Some(provider) = self
            .chain_providers
            .iter()
            .find(|provider| provider.provider_id() == ProviderId::SolanaPublic)
            .cloned()
        else {
            return Ok(());
        };
        let provider_id = ProviderId::SolanaPublic;
        self.ensure_health(health, provider_id)?;

        let candidates = self
            .db
            .fast_lane_mints_missing_state(FAST_LANE_METADATA_HYDRATION_BUDGET)?;
        for candidate in candidates {
            self.pacer.wait(PacingLane::Chain(provider_id)).await;

            match provider.token_mint_state(&candidate.mint).await {
                Ok(state) => {
                    health
                        .get_mut(&provider_id)
                        .expect("health initialized before provider call")
                        .record_success();
                    if state.provider != provider_id || state.mint != candidate.mint {
                        report.provider_failures = report.provider_failures.saturating_add(1);
                        record_synthetic_failure(
                            health,
                            provider_id,
                            format!(
                                "fast-lane mint-state identity mismatch for requested mint {}",
                                candidate.mint
                            ),
                        );
                        continue;
                    }

                    match retry_bounded(
                        || self.db.persist_fast_lane_mint_state(&candidate, &state),
                        is_storage_sqlite_busy_or_locked,
                    ) {
                        Ok(()) => {
                            report.mint_states_stored =
                                report.mint_states_stored.saturating_add(1);
                        }
                        Err(error) if is_storage_sqlite_busy_or_locked(&error) => {
                            // Metadata is derived enrichment. The immutable raw
                            // event remains the restart-safe queue, so exhausted
                            // writer contention must not take down broad capture.
                            // A later cycle will select this mint again because no
                            // verified mint state became durable.
                            continue;
                        }
                        Err(error) => return Err(error.into()),
                    }
                }
                Err(error) => {
                    report.provider_failures = report.provider_failures.saturating_add(1);
                    record_adapter_failure(health, provider_id, &error);
                }
            }
        }

        Ok(())
    }
}
