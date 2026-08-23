//! Restart-safe, observe-only orchestration for Shreks.
//!
//! This crate is intentionally incapable of creating or executing trade
//! intents. Its only responsibilities are provider orchestration, normalized
//! persistence, and operational provider-health tracking.

use std::{
    collections::{HashMap, HashSet},
    error::Error,
    fmt,
    sync::Arc,
    time::{SystemTime, SystemTimeError, UNIX_EPOCH},
};

use shreks_core::{DiscoveredToken, ProviderHealthState, ProviderId};
use shreks_providers::{
    ChainDataProvider, DiscoveryProvider, MarketDataProvider, ProviderError, ProviderErrorKind,
};
use shreks_storage::{ShreksDb, StorageError};

/// Summary of one finite observer pass.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ObserverCycleReport {
    pub discovery_items_seen: usize,
    pub candidates_processed: usize,
    pub market_snapshots_stored: usize,
    pub mint_states_stored: usize,
    pub provider_failures: usize,
}

/// Fatal observer errors. Provider failures are deliberately not fatal; they
/// are recorded as provider health and reflected in the cycle report.
#[derive(Debug)]
pub enum ObserverError {
    Storage(StorageError),
    Clock(SystemTimeError),
    ClockOverflow,
}

impl fmt::Display for ObserverError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Storage(error) => write!(formatter, "observer storage error: {error}"),
            Self::Clock(error) => write!(formatter, "observer clock error: {error}"),
            Self::ClockOverflow => formatter.write_str("observer clock exceeds i64 milliseconds"),
        }
    }
}

impl Error for ObserverError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Storage(error) => Some(error),
            Self::Clock(error) => Some(error),
            Self::ClockOverflow => None,
        }
    }
}

impl From<StorageError> for ObserverError {
    fn from(error: StorageError) -> Self {
        Self::Storage(error)
    }
}

#[derive(Debug, Clone)]
struct CycleHealth {
    state: ProviderHealthState,
    failures: u64,
    detail: Option<String>,
}

impl CycleHealth {
    fn healthy() -> Self {
        Self {
            state: ProviderHealthState::Healthy,
            failures: 0,
            detail: None,
        }
    }

    fn record_failure(&mut self, error: &ProviderError) {
        self.failures = self.failures.saturating_add(1);
        let next = error.health_state();
        if health_severity(next) >= health_severity(self.state) {
            self.state = next;
            self.detail = Some(truncate_detail(&error.message));
        }
    }
}

/// Observe-only orchestrator. Provider trait objects make the same path usable
/// with deterministic test doubles and real free-tier adapters.
pub struct Observer {
    db: ShreksDb,
    discovery_providers: Vec<Arc<dyn DiscoveryProvider>>,
    market_providers: Vec<Arc<dyn MarketDataProvider>>,
    chain_providers: Vec<Arc<dyn ChainDataProvider>>,
}

impl Observer {
    pub fn new(db: ShreksDb) -> Self {
        Self {
            db,
            discovery_providers: Vec::new(),
            market_providers: Vec::new(),
            chain_providers: Vec::new(),
        }
    }

    pub fn with_discovery_provider(mut self, provider: Arc<dyn DiscoveryProvider>) -> Self {
        self.discovery_providers.push(provider);
        self
    }

    pub fn with_market_provider(mut self, provider: Arc<dyn MarketDataProvider>) -> Self {
        self.market_providers.push(provider);
        self
    }

    pub fn with_chain_provider(mut self, provider: Arc<dyn ChainDataProvider>) -> Self {
        self.chain_providers.push(provider);
        self
    }

    /// Run exactly one observation pass.
    ///
    /// Provider failures are isolated from one another. Storage/clock failures
    /// are fatal because continuing without durable state would break audit and
    /// restart guarantees.
    pub async fn run_cycle(&mut self) -> Result<ObserverCycleReport, ObserverError> {
        let mut report = ObserverCycleReport::default();
        let mut health: HashMap<ProviderId, CycleHealth> = HashMap::new();
        let mut candidates = Vec::new();
        let mut seen_candidate_ids = HashSet::new();

        for provider in &self.discovery_providers {
            let provider_id = provider.provider_id();
            match provider.discover().await {
                Ok(items) => {
                    health.entry(provider_id).or_insert_with(CycleHealth::healthy);
                    report.discovery_items_seen = report.discovery_items_seen.saturating_add(items.len());

                    for candidate in items {
                        if candidate.source != provider_id {
                            report.provider_failures = report.provider_failures.saturating_add(1);
                            record_synthetic_failure(
                                &mut health,
                                provider_id,
                                format!(
                                    "discovery item source {} did not match provider {}",
                                    candidate.source, provider_id
                                ),
                            );
                            continue;
                        }

                        let candidate_id = self.db.upsert_candidate(&candidate)?;
                        if seen_candidate_ids.insert(candidate_id) {
                            candidates.push((candidate_id, candidate));
                        }
                    }
                }
                Err(error) => {
                    report.provider_failures = report.provider_failures.saturating_add(1);
                    record_failure(&mut health, &error);
                }
            }
        }

        report.candidates_processed = candidates.len();

        for (candidate_id, candidate) in &candidates {
            self.observe_market_data(
                *candidate_id,
                candidate,
                &mut report,
                &mut health,
            )
            .await?;
            self.observe_chain_data(
                *candidate_id,
                candidate,
                &mut report,
                &mut health,
            )
            .await?;
        }

        let observed_at = unix_time_ms()?;
        for (provider, state) in health {
            self.db.upsert_provider_health(
                provider,
                state.state,
                observed_at,
                None,
                state.detail.as_deref(),
                state.failures,
            )?;
        }

        Ok(report)
    }

    async fn observe_market_data(
        &self,
        candidate_id: i64,
        candidate: &DiscoveredToken,
        report: &mut ObserverCycleReport,
        health: &mut HashMap<ProviderId, CycleHealth>,
    ) -> Result<(), ObserverError> {
        for provider in &self.market_providers {
            let provider_id = provider.provider_id();
            match provider.token_pairs(&candidate.mint).await {
                Ok(snapshots) => {
                    health.entry(provider_id).or_insert_with(CycleHealth::healthy);
                    for snapshot in snapshots {
                        if snapshot.provider != provider_id {
                            report.provider_failures = report.provider_failures.saturating_add(1);
                            record_synthetic_failure(
                                health,
                                provider_id,
                                format!(
                                    "market snapshot provider {} did not match adapter {}",
                                    snapshot.provider, provider_id
                                ),
                            );
                            continue;
                        }
                        if snapshot.base_mint != candidate.mint
                            && snapshot.quote_mint != candidate.mint
                        {
                            report.provider_failures = report.provider_failures.saturating_add(1);
                            record_synthetic_failure(
                                health,
                                provider_id,
                                format!(
                                    "market snapshot pair {} did not contain requested mint {}",
                                    snapshot.pair_address, candidate.mint
                                ),
                            );
                            continue;
                        }

                        self.db.insert_market_snapshot(candidate_id, &snapshot)?;
                        report.market_snapshots_stored =
                            report.market_snapshots_stored.saturating_add(1);
                    }
                }
                Err(error) => {
                    report.provider_failures = report.provider_failures.saturating_add(1);
                    record_failure(health, &error);
                }
            }
        }
        Ok(())
    }

    async fn observe_chain_data(
        &self,
        candidate_id: i64,
        candidate: &DiscoveredToken,
        report: &mut ObserverCycleReport,
        health: &mut HashMap<ProviderId, CycleHealth>,
    ) -> Result<(), ObserverError> {
        for provider in &self.chain_providers {
            let provider_id = provider.provider_id();
            match provider.token_mint_state(&candidate.mint).await {
                Ok(state) => {
                    health.entry(provider_id).or_insert_with(CycleHealth::healthy);
                    if state.provider != provider_id || state.mint != candidate.mint {
                        report.provider_failures = report.provider_failures.saturating_add(1);
                        record_synthetic_failure(
                            health,
                            provider_id,
                            format!(
                                "mint-state identity mismatch for requested mint {}",
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
                    record_failure(health, &error);
                }
            }
        }
        Ok(())
    }
}

fn record_failure(health: &mut HashMap<ProviderId, CycleHealth>, error: &ProviderError) {
    health
        .entry(error.provider)
        .or_insert_with(CycleHealth::healthy)
        .record_failure(error);
}

fn record_synthetic_failure(
    health: &mut HashMap<ProviderId, CycleHealth>,
    provider: ProviderId,
    message: String,
) {
    let error = ProviderError::new(provider, ProviderErrorKind::InvalidResponse, message);
    record_failure(health, &error);
}

fn health_severity(state: ProviderHealthState) -> u8 {
    match state {
        ProviderHealthState::Healthy => 0,
        ProviderHealthState::Degraded => 1,
        ProviderHealthState::RateLimited => 2,
        ProviderHealthState::Unavailable => 3,
    }
}

fn truncate_detail(message: &str) -> String {
    const MAX_CHARS: usize = 512;
    message.chars().take(MAX_CHARS).collect()
}

fn unix_time_ms() -> Result<i64, ObserverError> {
    let elapsed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(ObserverError::Clock)?;
    i64::try_from(elapsed.as_millis()).map_err(|_| ObserverError::ClockOverflow)
}
