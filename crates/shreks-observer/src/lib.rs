//! Restart-safe, observe-only orchestration for Shreks.
//!
//! This crate is intentionally incapable of creating or executing trade
//! intents. Its only responsibilities are provider orchestration, normalized
//! persistence, pacing, and operational provider-health tracking.

mod runtime;
pub use runtime::{
    build_free_observer, free_observe_provider_plan, ObserveProviderPlan, ObserverRuntimeConfig,
    RuntimeConfigError,
};

use std::{
    collections::{HashMap, HashSet},
    error::Error,
    fmt,
    future::Future,
    sync::Arc,
    time::{Duration, SystemTime, SystemTimeError, UNIX_EPOCH},
};

use shreks_core::{DiscoveredToken, ProviderHealthState, ProviderId};
use shreks_providers::{
    config::ProviderConfig,
    pump::{
        classify_pump_creation_transaction, PumpCreationSignal, PumpCreationVerification,
    },
    ChainDataProvider, DiscoveryProvider, MarketDataProvider, ProviderError, ProviderErrorKind,
    TransactionProvider,
};
use shreks_storage::{ShreksDb, StorageError};
use tokio::{
    sync::mpsc,
    time::{sleep, sleep_until, Instant},
};

const DISCOVERY_WATERMARK_STREAM: &str = "discovery_watermark_unix_ms";
const FAILURE_STREAK_STREAM: &str = "provider_consecutive_failures";
const DEXSCREENER_DISCOVERY_RPS: u32 = 1;
const PUMP_PENDING_BATCH_LIMIT: usize = 32;
const PUMP_TRANSACTION_NOT_AVAILABLE: &str = "confirmed Pump transaction not available yet";

/// Summary of one finite observer pass.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ObserverCycleReport {
    pub discovery_items_seen: usize,
    pub candidates_processed: usize,
    pub market_snapshots_stored: usize,
    pub mint_states_stored: usize,
    pub provider_failures: usize,
    pub pump_signals_received: usize,
    pub pump_signals_processed: usize,
    pub pump_signals_pending: usize,
    pub pump_signals_verified: usize,
    pub pump_signals_rejected: usize,
}

/// Fatal observer errors. Provider failures are deliberately not fatal; they
/// are recorded as provider health and reflected in the cycle report.
#[derive(Debug)]
pub enum ObserverError {
    Storage(StorageError),
    Clock(SystemTimeError),
    ClockOverflow,
    InvalidCheckpoint {
        provider: ProviderId,
        stream: &'static str,
        value: String,
    },
}

impl fmt::Display for ObserverError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Storage(error) => write!(formatter, "observer storage error: {error}"),
            Self::Clock(error) => write!(formatter, "observer clock error: {error}"),
            Self::ClockOverflow => formatter.write_str("observer clock exceeds i64 milliseconds"),
            Self::InvalidCheckpoint {
                provider,
                stream,
                value,
            } => write!(
                formatter,
                "observer checkpoint {provider}/{stream} contained invalid value '{value}'"
            ),
        }
    }
}

impl Error for ObserverError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Storage(error) => Some(error),
            Self::Clock(error) => Some(error),
            Self::ClockOverflow | Self::InvalidCheckpoint { .. } => None,
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
    fn healthy_with_failure_streak(failures: u64) -> Self {
        Self {
            state: ProviderHealthState::Healthy,
            failures,
            detail: None,
        }
    }

    fn record_success(&mut self) {
        self.state = ProviderHealthState::Healthy;
        self.failures = 0;
        self.detail = None;
    }

    fn record_failure(&mut self, error: &ProviderError) {
        self.failures = self.failures.saturating_add(1);
        self.state = error.health_state();
        self.detail = Some(truncate_detail(&error.message));
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum PacingLane {
    Discovery(ProviderId),
    Market(ProviderId),
    Chain(ProviderId),
}

struct RequestPacer {
    intervals: HashMap<PacingLane, Duration>,
    next_allowed: HashMap<PacingLane, Instant>,
}

impl RequestPacer {
    fn free_tier_defaults() -> Self {
        let config = ProviderConfig::from_lookup(|_| None);
        let mut intervals = HashMap::new();

        insert_rps_interval(
            &mut intervals,
            PacingLane::Discovery(ProviderId::DexScreener),
            DEXSCREENER_DISCOVERY_RPS,
        );
        insert_rps_interval(
            &mut intervals,
            PacingLane::Market(ProviderId::DexScreener),
            config.dexscreener_market_rps,
        );
        insert_rps_interval(
            &mut intervals,
            PacingLane::Market(ProviderId::Meteora),
            config.meteora_market_rps,
        );
        insert_rps_interval(
            &mut intervals,
            PacingLane::Chain(ProviderId::Helius),
            config.helius_rpc_rps,
        );

        Self {
            intervals,
            next_allowed: HashMap::new(),
        }
    }

    async fn wait(&mut self, lane: PacingLane) {
        let Some(interval) = self.intervals.get(&lane).copied() else {
            return;
        };

        let now = Instant::now();
        if let Some(next_allowed) = self.next_allowed.get(&lane).copied() {
            if next_allowed > now {
                sleep_until(next_allowed).await;
            }
        }

        self.next_allowed.insert(lane, Instant::now() + interval);
    }
}

/// Observe-only orchestrator. Provider trait objects make the same path usable
/// with deterministic test doubles and real free-tier adapters.
pub struct Observer {
    db: ShreksDb,
    discovery_providers: Vec<Arc<dyn DiscoveryProvider>>,
    market_providers: Vec<Arc<dyn MarketDataProvider>>,
    chain_providers: Vec<Arc<dyn ChainDataProvider>>,
    transaction_providers: Vec<Arc<dyn TransactionProvider>>,
    pump_signal_receiver: Option<mpsc::Receiver<PumpCreationSignal>>,
    pacer: RequestPacer,
}

impl Observer {
    pub fn new(db: ShreksDb) -> Self {
        Self {
            db,
            discovery_providers: Vec::new(),
            market_providers: Vec::new(),
            chain_providers: Vec::new(),
            transaction_providers: Vec::new(),
            pump_signal_receiver: None,
            pacer: RequestPacer::free_tier_defaults(),
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

    pub fn with_transaction_provider(mut self, provider: Arc<dyn TransactionProvider>) -> Self {
        self.transaction_providers.push(provider);
        self
    }

    /// Attach the receiving end of the realtime Pump stream. The producer is
    /// intentionally unable to access SQLite; only this observer drains and
    /// persists signals, preserving the single-writer storage contract.
    pub fn with_pump_signal_receiver(
        mut self,
        receiver: mpsc::Receiver<PumpCreationSignal>,
    ) -> Self {
        self.pump_signal_receiver = Some(receiver);
        self
    }

    /// Run observation cycles until shutdown is signaled.
    ///
    /// A cycle always starts immediately. Shutdown is observed between cycles
    /// and can interrupt a long inter-cycle sleep without waiting for the next
    /// scheduled cycle. In-flight provider calls are allowed to finish so a
    /// cycle's durable state is not left half-written.
    pub async fn run_until_shutdown<F>(
        &mut self,
        cycle_interval: Duration,
        shutdown: F,
    ) -> Result<usize, ObserverError>
    where
        F: Future<Output = ()>,
    {
        tokio::pin!(shutdown);
        let mut completed_cycles = 0usize;

        loop {
            self.run_cycle().await?;
            completed_cycles = completed_cycles.saturating_add(1);

            tokio::select! {
                _ = sleep(cycle_interval) => {}
                _ = &mut shutdown => return Ok(completed_cycles),
            }
        }
    }

    /// Run exactly one observation pass.
    ///
    /// Provider failures are isolated from one another. Storage/clock failures
    /// are fatal because continuing without durable state would break audit and
    /// restart guarantees.
    pub async fn run_cycle(&mut self) -> Result<ObserverCycleReport, ObserverError> {
        let mut report = ObserverCycleReport::default();
        self.drain_pump_signal_queue(&mut report)?;

        let mut health: HashMap<ProviderId, CycleHealth> = HashMap::new();
        let mut candidates = Vec::new();
        let mut seen_candidate_ids = HashSet::new();

        self.process_pending_pump_signals(
            &mut report,
            &mut health,
            &mut candidates,
            &mut seen_candidate_ids,
        )
        .await?;

        for provider in self.discovery_providers.clone() {
            let provider_id = provider.provider_id();
            self.ensure_health(&mut health, provider_id)?;
            self.pacer
                .wait(PacingLane::Discovery(provider_id))
                .await;

            match provider.discover().await {
                Ok(items) => {
                    health
                        .get_mut(&provider_id)
                        .expect("health initialized before provider call")
                        .record_success();
                    report.discovery_items_seen =
                        report.discovery_items_seen.saturating_add(items.len());

                    let mut successful_watermark = None;
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

                        successful_watermark = Some(
                            successful_watermark
                                .map_or(candidate.discovered_at_unix_ms, |current: i64| {
                                    current.max(candidate.discovered_at_unix_ms)
                                }),
                        );

                        let candidate_id = self.db.upsert_candidate(&candidate)?;
                        if seen_candidate_ids.insert(candidate_id) {
                            candidates.push((candidate_id, candidate));
                        }
                    }

                    if let Some(watermark) = successful_watermark {
                        self.persist_monotonic_discovery_watermark(provider_id, watermark)?;
                    }
                }
                Err(error) => {
                    report.provider_failures = report.provider_failures.saturating_add(1);
                    record_adapter_failure(&mut health, provider_id, &error);
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
            let failure_streak = state.failures.to_string();
            self.db.set_ingestion_checkpoint(
                provider,
                FAILURE_STREAK_STREAM,
                Some(&failure_streak),
            )?;
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

    fn drain_pump_signal_queue(
        &mut self,
        report: &mut ObserverCycleReport,
    ) -> Result<(), ObserverError> {
        loop {
            let signal = match self.pump_signal_receiver.as_mut() {
                Some(receiver) => match receiver.try_recv() {
                    Ok(signal) => signal,
                    Err(mpsc::error::TryRecvError::Empty) => break,
                    Err(mpsc::error::TryRecvError::Disconnected) => {
                        self.pump_signal_receiver = None;
                        break;
                    }
                },
                None => break,
            };

            self.db.record_pump_launch_signal(
                &signal.signature,
                signal.slot,
                unix_time_ms()?,
            )?;
            report.pump_signals_received = report.pump_signals_received.saturating_add(1);
        }
        Ok(())
    }

    async fn process_pending_pump_signals(
        &mut self,
        report: &mut ObserverCycleReport,
        health: &mut HashMap<ProviderId, CycleHealth>,
        candidates: &mut Vec<(i64, DiscoveredToken)>,
        seen_candidate_ids: &mut HashSet<i64>,
    ) -> Result<(), ObserverError> {
        let Some(provider) = self.transaction_providers.first().cloned() else {
            return Ok(());
        };
        let provider_id = provider.provider_id();
        self.ensure_health(health, provider_id)?;

        let pending = self
            .db
            .pending_pump_launch_signals(PUMP_PENDING_BATCH_LIMIT)?;
        for signal in pending {
            report.pump_signals_processed = report.pump_signals_processed.saturating_add(1);
            self.pacer.wait(PacingLane::Chain(provider_id)).await;
            let attempted_at = unix_time_ms()?;

            let body = match provider.transaction_json(&signal.signature).await {
                Ok(body) => body,
                Err(error) => {
                    let detail = truncate_detail(&error.message);
                    self.db.record_pump_launch_attempt(
                        &signal.signature,
                        attempted_at,
                        Some(&detail),
                    )?;
                    report.pump_signals_pending = report.pump_signals_pending.saturating_add(1);
                    report.provider_failures = report.provider_failures.saturating_add(1);
                    record_adapter_failure(health, provider_id, &error);
                    continue;
                }
            };

            let verification = match classify_pump_creation_transaction(
                &body,
                &signal.signature,
                signal.observed_at_unix_ms,
            ) {
                Ok(verification) => verification,
                Err(error) => {
                    let detail = truncate_detail(&error.message);
                    self.db.record_pump_launch_attempt(
                        &signal.signature,
                        attempted_at,
                        Some(&detail),
                    )?;
                    report.pump_signals_pending = report.pump_signals_pending.saturating_add(1);
                    report.provider_failures = report.provider_failures.saturating_add(1);
                    record_adapter_failure(health, provider_id, &error);
                    continue;
                }
            };

            health
                .get_mut(&provider_id)
                .expect("health initialized before provider call")
                .record_success();

            match verification {
                PumpCreationVerification::Pending => {
                    self.db.record_pump_launch_attempt(
                        &signal.signature,
                        attempted_at,
                        Some(PUMP_TRANSACTION_NOT_AVAILABLE),
                    )?;
                    report.pump_signals_pending = report.pump_signals_pending.saturating_add(1);
                }
                PumpCreationVerification::Verified(candidate) => {
                    self.db
                        .record_pump_launch_attempt(&signal.signature, attempted_at, None)?;
                    let candidate_id = self.db.upsert_candidate(&candidate)?;
                    self.db
                        .mark_pump_launch_verified(&signal.signature, candidate_id)?;
                    report.pump_signals_verified =
                        report.pump_signals_verified.saturating_add(1);
                    if seen_candidate_ids.insert(candidate_id) {
                        candidates.push((candidate_id, candidate));
                    }
                }
                PumpCreationVerification::Rejected(reason) => {
                    self.db
                        .record_pump_launch_attempt(&signal.signature, attempted_at, None)?;
                    let reason = truncate_detail(&reason);
                    self.db.mark_pump_launch_rejected(
                        &signal.signature,
                        attempted_at,
                        &reason,
                    )?;
                    report.pump_signals_rejected =
                        report.pump_signals_rejected.saturating_add(1);
                }
            }
        }

        Ok(())
    }

    async fn observe_market_data(
        &mut self,
        candidate_id: i64,
        candidate: &DiscoveredToken,
        report: &mut ObserverCycleReport,
        health: &mut HashMap<ProviderId, CycleHealth>,
    ) -> Result<(), ObserverError> {
        for provider in self.market_providers.clone() {
            let provider_id = provider.provider_id();
            self.ensure_health(health, provider_id)?;
            self.pacer.wait(PacingLane::Market(provider_id)).await;

            match provider.token_pairs(&candidate.mint).await {
                Ok(snapshots) => {
                    health
                        .get_mut(&provider_id)
                        .expect("health initialized before provider call")
                        .record_success();
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
                    record_adapter_failure(health, provider_id, &error);
                }
            }
        }
        Ok(())
    }

    async fn observe_chain_data(
        &mut self,
        candidate_id: i64,
        candidate: &DiscoveredToken,
        report: &mut ObserverCycleReport,
        health: &mut HashMap<ProviderId, CycleHealth>,
    ) -> Result<(), ObserverError> {
        for provider in self.chain_providers.clone() {
            let provider_id = provider.provider_id();
            self.ensure_health(health, provider_id)?;
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
                    record_adapter_failure(health, provider_id, &error);
                }
            }
        }
        Ok(())
    }

    fn ensure_health(
        &self,
        health: &mut HashMap<ProviderId, CycleHealth>,
        provider: ProviderId,
    ) -> Result<(), ObserverError> {
        if health.contains_key(&provider) {
            return Ok(());
        }

        let failures = self.load_failure_streak(provider)?;
        health.insert(
            provider,
            CycleHealth::healthy_with_failure_streak(failures),
        );
        Ok(())
    }

    fn load_failure_streak(&self, provider: ProviderId) -> Result<u64, ObserverError> {
        let Some(value) = self
            .db
            .ingestion_checkpoint(provider, FAILURE_STREAK_STREAM)?
        else {
            return Ok(0);
        };

        value
            .parse::<u64>()
            .map_err(|_| ObserverError::InvalidCheckpoint {
                provider,
                stream: FAILURE_STREAK_STREAM,
                value,
            })
    }

    fn persist_monotonic_discovery_watermark(
        &self,
        provider: ProviderId,
        observed_watermark: i64,
    ) -> Result<(), ObserverError> {
        let current = self
            .db
            .ingestion_checkpoint(provider, DISCOVERY_WATERMARK_STREAM)?;
        let current = match current {
            Some(value) => Some(value.parse::<i64>().map_err(|_| {
                ObserverError::InvalidCheckpoint {
                    provider,
                    stream: DISCOVERY_WATERMARK_STREAM,
                    value,
                }
            })?),
            None => None,
        };
        let next = current.map_or(observed_watermark, |value| value.max(observed_watermark));
        let next = next.to_string();
        self.db.set_ingestion_checkpoint(
            provider,
            DISCOVERY_WATERMARK_STREAM,
            Some(&next),
        )?;
        Ok(())
    }
}

fn insert_rps_interval(
    intervals: &mut HashMap<PacingLane, Duration>,
    lane: PacingLane,
    requests_per_second: u32,
) {
    if requests_per_second == 0 {
        return;
    }
    intervals.insert(
        lane,
        Duration::from_secs_f64(1.0 / f64::from(requests_per_second)),
    );
}

fn record_adapter_failure(
    health: &mut HashMap<ProviderId, CycleHealth>,
    adapter_provider: ProviderId,
    error: &ProviderError,
) {
    if error.provider == adapter_provider {
        health
            .get_mut(&adapter_provider)
            .expect("health initialized before provider call")
            .record_failure(error);
        return;
    }

    record_synthetic_failure(
        health,
        adapter_provider,
        format!(
            "adapter {} returned an error attributed to {}",
            adapter_provider, error.provider
        ),
    );
}

fn record_synthetic_failure(
    health: &mut HashMap<ProviderId, CycleHealth>,
    provider: ProviderId,
    message: String,
) {
    let error = ProviderError::new(provider, ProviderErrorKind::InvalidResponse, message);
    health
        .get_mut(&provider)
        .expect("health initialized before provider call")
        .record_failure(&error);
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
