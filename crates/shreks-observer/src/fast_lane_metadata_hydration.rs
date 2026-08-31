use std::collections::HashMap;

use shreks_core::ProviderId;

use crate::{
    record_adapter_failure, record_synthetic_failure, CycleHealth, Observer, ObserverCycleReport,
    ObserverError, PacingLane,
};

const FAST_LANE_METADATA_HYDRATION_BUDGET: usize = 8;

impl Observer {
    /// Hydrate only the verified mint-state prerequisite needed by canonical
    /// fast-lane normalization, using the public Solana chain adapter only.
    ///
    /// Raw evidence remains the restart-safe queue. The selector prioritizes
    /// fresh active mints and this fixed per-cycle budget prevents metadata
    /// catch-up from monopolizing the public RPC lane. Provider failures are
    /// isolated in normal observer health state; storage/integrity failures stay
    /// fatal. No market, strategy, signing, execution, or paid-provider authority
    /// is introduced here.
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
            let candidate_id = self.db.upsert_candidate(&candidate)?;
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

                    self.db.insert_mint_state(candidate_id, &state)?;
                    report.mint_states_stored = report.mint_states_stored.saturating_add(1);
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
