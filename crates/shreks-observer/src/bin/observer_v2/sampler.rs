use std::{
    error::Error,
    fmt,
    future::Future,
    sync::Arc,
    time::{Duration, SystemTime, SystemTimeError, UNIX_EPOCH},
};

use shreks_core::{ProviderHealthState, ProviderId};
use shreks_providers::{DiscoveryProvider, MarketDataProvider, ProviderError};
use shreks_storage::{ShreksDb, StorageError};
use tokio::time::{sleep, Instant};

use super::sampling::{
    representative_sample, ActivityClass, SamplingError, SamplingPolicy, SamplingRegistry,
    TrackedCandidate,
};

const REGISTRY_STREAM: &str = "observer_v2_registry_v1";
const DISCOVERY_INTERVAL_MS: i64 = 30_000;
const RUNTIME_LOOP_INTERVAL: Duration = Duration::from_secs(1);

/// One market provider plus an optional request budget used by the high-resolution sampler.
pub struct SamplerProvider {
    provider: Arc<dyn MarketDataProvider>,
    min_request_interval: Option<Duration>,
    last_request_at: Option<Instant>,
    consecutive_failures: u64,
}

impl SamplerProvider {
    /// Construct an unpaced provider for deterministic tests. Production callers
    /// should use `paced` with the configured free-tier request budget.
    pub fn unpaced(provider: Arc<dyn MarketDataProvider>) -> Self {
        Self {
            provider,
            min_request_interval: None,
            last_request_at: None,
            consecutive_failures: 0,
        }
    }

    pub fn paced(
        provider: Arc<dyn MarketDataProvider>,
        requests_per_second: u32,
    ) -> Result<Self, SamplerError> {
        if requests_per_second == 0 {
            return Err(SamplerError::InvalidData(
                "market provider requests_per_second must be positive".to_owned(),
            ));
        }
        Ok(Self {
            provider,
            min_request_interval: Some(Duration::from_secs_f64(
                1.0 / f64::from(requests_per_second),
            )),
            last_request_at: None,
            consecutive_failures: 0,
        })
    }

    fn provider_id(&self) -> ProviderId {
        self.provider.provider_id()
    }

    async fn token_pairs(
        &mut self,
        token_mint: &str,
    ) -> Result<Vec<shreks_core::PairMarketData>, ProviderError> {
        if let (Some(minimum), Some(last)) = (self.min_request_interval, self.last_request_at) {
            let elapsed = last.elapsed();
            if elapsed < minimum {
                sleep(minimum - elapsed).await;
            }
        }
        self.last_request_at = Some(Instant::now());
        self.provider.token_pairs(token_mint).await
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SamplerCycleReport {
    pub discovered_candidate_count: usize,
    pub sampled_candidate_count: usize,
    pub persisted_snapshot_count: usize,
    pub market_provider_failure_count: usize,
    pub completed_checkpoint_count: usize,
}

pub struct HighResolutionSampler {
    db: ShreksDb,
    discovery: Option<Arc<dyn DiscoveryProvider>>,
    market: Vec<SamplerProvider>,
    policy: SamplingPolicy,
    registry: SamplingRegistry,
    next_discovery_at_unix_ms: i64,
    discovery_consecutive_failures: u64,
}

impl HighResolutionSampler {
    pub fn new(
        db: ShreksDb,
        discovery: Option<Arc<dyn DiscoveryProvider>>,
        market: Vec<SamplerProvider>,
        policy: SamplingPolicy,
    ) -> Result<Self, SamplerError> {
        if market.is_empty() {
            return Err(SamplerError::InvalidData(
                "Observer V2 requires at least one market provider".to_owned(),
            ));
        }
        Ok(Self {
            db,
            discovery,
            market,
            policy,
            registry: SamplingRegistry::default(),
            next_discovery_at_unix_ms: 0,
            discovery_consecutive_failures: 0,
        })
    }

    pub fn registry(&self) -> &SamplingRegistry {
        &self.registry
    }

    pub fn restore_registry(&mut self) -> Result<(), SamplerError> {
        let Some(encoded) = self
            .db
            .ingestion_checkpoint(ProviderId::DexScreener, REGISTRY_STREAM)?
        else {
            return Ok(());
        };
        self.registry = SamplingRegistry::decode(&encoded)?;
        Ok(())
    }

    pub async fn run_cycle_at(
        &mut self,
        now_unix_ms: i64,
    ) -> Result<SamplerCycleReport, SamplerError> {
        if now_unix_ms < 0 {
            return Err(SamplerError::InvalidData(
                "Observer V2 cycle timestamp must be nonnegative".to_owned(),
            ));
        }

        let mut report = SamplerCycleReport::default();
        self.run_discovery_if_due(now_unix_ms, &mut report).await?;
        self.registry.expire(now_unix_ms, &self.policy);

        let due = self.registry.due_candidates(now_unix_ms);
        for candidate in due {
            self.sample_candidate(&candidate, now_unix_ms, &mut report)
                .await?;
        }

        self.flush_registry()?;
        Ok(report)
    }

    pub async fn run_until_shutdown<F>(&mut self, shutdown: F) -> Result<u64, SamplerError>
    where
        F: Future<Output = ()>,
    {
        tokio::pin!(shutdown);
        let mut cycles = 0_u64;
        loop {
            tokio::select! {
                _ = &mut shutdown => {
                    self.flush_registry()?;
                    return Ok(cycles);
                }
                _ = sleep(RUNTIME_LOOP_INTERVAL) => {
                    self.run_cycle_at(unix_time_ms()?).await?;
                    cycles = cycles.saturating_add(1);
                }
            }
        }
    }

    fn flush_registry(&self) -> Result<(), SamplerError> {
        let encoded = self.registry.encode();
        self.db.set_ingestion_checkpoint(
            ProviderId::DexScreener,
            REGISTRY_STREAM,
            Some(&encoded),
        )?;
        Ok(())
    }

    async fn run_discovery_if_due(
        &mut self,
        now_unix_ms: i64,
        report: &mut SamplerCycleReport,
    ) -> Result<(), SamplerError> {
        if now_unix_ms < self.next_discovery_at_unix_ms {
            return Ok(());
        }
        self.next_discovery_at_unix_ms = now_unix_ms.saturating_add(DISCOVERY_INTERVAL_MS);

        let Some(discovery) = self.discovery.as_ref().cloned() else {
            return Ok(());
        };
        let provider = discovery.provider_id();
        match discovery.discover().await {
            Ok(candidates) => {
                self.discovery_consecutive_failures = 0;
                self.db.upsert_provider_health(
                    provider,
                    ProviderHealthState::Healthy,
                    now_unix_ms,
                    None,
                    None,
                    0,
                )?;
                for candidate in candidates {
                    if candidate.source != provider {
                        return Err(SamplerError::InvalidData(format!(
                            "discovery provider {provider} returned candidate {} with source {}",
                            candidate.mint, candidate.source
                        )));
                    }
                    let candidate_id = self.db.upsert_candidate(&candidate)?;
                    self.db.ensure_outcome_checkpoints(
                        candidate_id,
                        candidate.discovered_at_unix_ms,
                    )?;
                    if !self.registry.contains_candidate_id(candidate_id) {
                        self.registry.register(TrackedCandidate::new(
                            candidate_id,
                            candidate.mint.clone(),
                            candidate.discovered_at_unix_ms,
                        )?)?;
                        report.discovered_candidate_count =
                            report.discovered_candidate_count.saturating_add(1);
                    }
                }
            }
            Err(error) => {
                self.discovery_consecutive_failures =
                    self.discovery_consecutive_failures.saturating_add(1);
                self.record_provider_error(
                    &error,
                    now_unix_ms,
                    self.discovery_consecutive_failures,
                )?;
            }
        }
        Ok(())
    }

    async fn sample_candidate(
        &mut self,
        candidate: &TrackedCandidate,
        now_unix_ms: i64,
        report: &mut SamplerCycleReport,
    ) -> Result<(), SamplerError> {
        report.sampled_candidate_count = report.sampled_candidate_count.saturating_add(1);
        let mut snapshots = Vec::new();
        let mut any_provider_success = false;

        for index in 0..self.market.len() {
            let provider_id = self.market[index].provider_id();
            let result = self.market[index].token_pairs(&candidate.mint).await;
            match result {
                Ok(provider_snapshots) => {
                    any_provider_success = true;
                    self.market[index].consecutive_failures = 0;
                    self.db.upsert_provider_health(
                        provider_id,
                        ProviderHealthState::Healthy,
                        now_unix_ms,
                        None,
                        None,
                        0,
                    )?;
                    for snapshot in provider_snapshots {
                        if snapshot.provider != provider_id {
                            return Err(SamplerError::InvalidData(format!(
                                "market provider {provider_id} returned snapshot attributed to {}",
                                snapshot.provider
                            )));
                        }
                        if snapshot.base_mint != candidate.mint {
                            return Err(SamplerError::InvalidData(format!(
                                "market provider {provider_id} returned mint {} while sampling {}",
                                snapshot.base_mint, candidate.mint
                            )));
                        }
                        self.db
                            .insert_market_snapshot(candidate.candidate_id, &snapshot)?;
                        report.persisted_snapshot_count =
                            report.persisted_snapshot_count.saturating_add(1);
                        snapshots.push(snapshot);
                    }
                }
                Err(error) => {
                    self.market[index].consecutive_failures =
                        self.market[index].consecutive_failures.saturating_add(1);
                    report.market_provider_failure_count =
                        report.market_provider_failure_count.saturating_add(1);
                    self.record_provider_error(
                        &error,
                        now_unix_ms,
                        self.market[index].consecutive_failures,
                    )?;
                }
            }
        }

        if any_provider_success {
            let activity = if let Some(sample) = representative_sample(&snapshots) {
                self.registry
                    .get_mut(candidate.candidate_id)
                    .ok_or_else(|| {
                        SamplerError::InvalidData(format!(
                            "candidate {} disappeared from Observer V2 registry",
                            candidate.candidate_id
                        ))
                    })?
                    .record_sample(sample)?
            } else {
                ActivityClass::Calm
            };
            self.registry
                .get_mut(candidate.candidate_id)
                .ok_or_else(|| {
                    SamplerError::InvalidData(format!(
                        "candidate {} disappeared from Observer V2 registry",
                        candidate.candidate_id
                    ))
                })?
                .schedule_after_success(now_unix_ms, &self.policy, activity);
            report.completed_checkpoint_count = report
                .completed_checkpoint_count
                .saturating_add(
                    self.db
                        .finalize_due_outcome_checkpoints(candidate.candidate_id, now_unix_ms)?,
                );
        } else {
            self.registry
                .get_mut(candidate.candidate_id)
                .ok_or_else(|| {
                    SamplerError::InvalidData(format!(
                        "candidate {} disappeared from Observer V2 registry",
                        candidate.candidate_id
                    ))
                })?
                .schedule_after_failure(now_unix_ms, &self.policy);
        }
        Ok(())
    }

    fn record_provider_error(
        &self,
        error: &ProviderError,
        now_unix_ms: i64,
        consecutive_failures: u64,
    ) -> Result<(), SamplerError> {
        self.db.upsert_provider_health(
            error.provider,
            error.health_state(),
            now_unix_ms,
            None,
            Some(&error.message),
            consecutive_failures,
        )?;
        Ok(())
    }
}

#[derive(Debug)]
pub enum SamplerError {
    Storage(StorageError),
    Sampling(SamplingError),
    Clock(SystemTimeError),
    InvalidData(String),
}

impl fmt::Display for SamplerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Storage(error) => write!(formatter, "Observer V2 storage error: {error}"),
            Self::Sampling(error) => write!(formatter, "Observer V2 sampling error: {error}"),
            Self::Clock(error) => write!(formatter, "Observer V2 clock error: {error}"),
            Self::InvalidData(message) => write!(formatter, "Observer V2 rejected invalid data: {message}"),
        }
    }
}

impl Error for SamplerError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Storage(error) => Some(error),
            Self::Sampling(error) => Some(error),
            Self::Clock(error) => Some(error),
            Self::InvalidData(_) => None,
        }
    }
}

impl From<StorageError> for SamplerError {
    fn from(error: StorageError) -> Self {
        Self::Storage(error)
    }
}

impl From<SamplingError> for SamplerError {
    fn from(error: SamplingError) -> Self {
        Self::Sampling(error)
    }
}

impl From<SystemTimeError> for SamplerError {
    fn from(error: SystemTimeError) -> Self {
        Self::Clock(error)
    }
}

fn unix_time_ms() -> Result<i64, SamplerError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH)?;
    i64::try_from(elapsed.as_millis()).map_err(|_| {
        SamplerError::InvalidData("system clock exceeds i64 milliseconds".to_owned())
    })
}
