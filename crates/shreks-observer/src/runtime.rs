#[path = "sqlite_busy_retry.rs"]
mod sqlite_busy_retry;

use std::{
    error::Error,
    fmt,
    path::PathBuf,
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_providers::{
    config::ProviderConfig,
    dexscreener::DexScreenerProvider,
    meteora::MeteoraProvider,
    pump::PumpLifecycleSignal,
    bounded_pump_realtime_failover::BoundedPumpRealtimeSessionNotification,
    pump_realtime::PumpRealtimeNotification,
    solana_rpc::StandardSolanaRpcProvider,
    ProviderError,
};
use shreks_storage::{
    pump_swap_event_ordinal, EvidenceWriteOutcome, PumpSwapExecutionEconomicsWrite,
    PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, PumpTradeExecutionEconomicsWrite, ShreksDb,
    StorageError,
};
use sqlite_busy_retry::{is_storage_sqlite_busy_or_locked, retry_bounded};
use tokio::sync::mpsc;

use crate::{Observer, ObserverError};

const DEFAULT_DB_PATH: &str = "data/shreks.db";
const DEFAULT_CYCLE_INTERVAL_SECONDS: u64 = 30;
const PUMPSWAP_TRACKING_MAX_AGE_SECONDS_ENV: &str =
    "SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS";
const PUMPSWAP_MAX_TRACKED_POOLS_ENV: &str = "SHREKS_PUMPSWAP_MAX_TRACKED_POOLS";

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RuntimeConfigError {
    InvalidCycleInterval(String),
    MissingPumpSwapTrackingMaxAge,
    InvalidPumpSwapTrackingMaxAge(String),
    MissingPumpSwapMaxTrackedPools,
    InvalidPumpSwapMaxTrackedPools(String),
}

impl fmt::Display for RuntimeConfigError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidCycleInterval(value) => write!(
                formatter,
                "SHREKS_OBSERVER_INTERVAL_SECONDS must be a positive integer; got '{value}'"
            ),
            Self::MissingPumpSwapTrackingMaxAge => write!(
                formatter,
                "{PUMPSWAP_TRACKING_MAX_AGE_SECONDS_ENV} must be a positive integer for bounded public realtime observation"
            ),
            Self::InvalidPumpSwapTrackingMaxAge(value) => write!(
                formatter,
                "{PUMPSWAP_TRACKING_MAX_AGE_SECONDS_ENV} must be a positive integer representable in milliseconds; got '{value}'"
            ),
            Self::MissingPumpSwapMaxTrackedPools => write!(
                formatter,
                "{PUMPSWAP_MAX_TRACKED_POOLS_ENV} must be a positive integer for bounded public realtime observation"
            ),
            Self::InvalidPumpSwapMaxTrackedPools(value) => write!(
                formatter,
                "{PUMPSWAP_MAX_TRACKED_POOLS_ENV} must be a positive integer; got '{value}'"
            ),
        }
    }
}

impl Error for RuntimeConfigError {}

/// Environment-derived configuration for the observe-only process.
///
/// Paid provider configuration is retained for other binaries, but broad FL1
/// observation is pinned to public Solana transport and therefore always
/// requires explicit PumpSwap scope bounds.
pub struct ObserverRuntimeConfig {
    pub db_path: PathBuf,
    pub cycle_interval: Duration,
    pub pumpswap_tracking_max_age: Option<Duration>,
    pub pumpswap_max_tracked_pools: Option<usize>,
    pub providers: ProviderConfig,
}

impl ObserverRuntimeConfig {
    pub fn from_lookup<F>(lookup: F) -> Result<Self, RuntimeConfigError>
    where
        F: Fn(&str) -> Option<String>,
    {
        let db_path = non_blank(lookup("SHREKS_DB_PATH"))
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(DEFAULT_DB_PATH));

        let cycle_interval = match non_blank(lookup("SHREKS_OBSERVER_INTERVAL_SECONDS")) {
            None => Duration::from_secs(DEFAULT_CYCLE_INTERVAL_SECONDS),
            Some(raw) => {
                let seconds = raw
                    .parse::<u64>()
                    .ok()
                    .filter(|seconds| *seconds > 0)
                    .ok_or_else(|| RuntimeConfigError::InvalidCycleInterval(raw.clone()))?;
                Duration::from_secs(seconds)
            }
        };

        let providers = ProviderConfig::from_lookup(|name| lookup(name));

        let raw_age = non_blank(lookup(PUMPSWAP_TRACKING_MAX_AGE_SECONDS_ENV))
            .ok_or(RuntimeConfigError::MissingPumpSwapTrackingMaxAge)?;
        let age_seconds = raw_age
            .parse::<u64>()
            .ok()
            .filter(|seconds| *seconds > 0)
            .filter(|seconds| {
                seconds
                    .checked_mul(1_000)
                    .and_then(|milliseconds| i64::try_from(milliseconds).ok())
                    .is_some()
            })
            .ok_or_else(|| RuntimeConfigError::InvalidPumpSwapTrackingMaxAge(raw_age.clone()))?;

        let raw_count = non_blank(lookup(PUMPSWAP_MAX_TRACKED_POOLS_ENV))
            .ok_or(RuntimeConfigError::MissingPumpSwapMaxTrackedPools)?;
        let max_tracked_pools = raw_count
            .parse::<usize>()
            .ok()
            .filter(|count| *count > 0)
            .ok_or_else(|| RuntimeConfigError::InvalidPumpSwapMaxTrackedPools(raw_count.clone()))?;

        Ok(Self {
            db_path,
            cycle_interval,
            pumpswap_tracking_max_age: Some(Duration::from_secs(age_seconds)),
            pumpswap_max_tracked_pools: Some(max_tracked_pools),
            providers,
        })
    }

    pub fn from_env() -> Result<Self, RuntimeConfigError> {
        Self::from_lookup(|name| std::env::var(name).ok())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObserveProviderPlan {
    pub discovery: Vec<ProviderId>,
    pub market: Vec<ProviderId>,
    pub chain: Vec<ProviderId>,
    pub transactions: Vec<ProviderId>,
    pub realtime: Vec<ProviderId>,
}

impl ObserveProviderPlan {
    pub fn all_providers(&self) -> Vec<ProviderId> {
        let mut providers = Vec::new();
        for provider in self
            .discovery
            .iter()
            .chain(self.market.iter())
            .chain(self.chain.iter())
            .chain(self.transactions.iter())
            .chain(self.realtime.iter())
            .copied()
        {
            if !providers.contains(&provider) {
                providers.push(provider);
            }
        }
        providers
    }
}

/// Resolve the provider set that the observe-only runtime is allowed to use.
/// Broad chain truth, transaction verification, and realtime Pump capture are
/// deliberately public-only. Paid credentials cannot re-enter these FL1 roles.
pub fn free_observe_provider_plan(config: &ProviderConfig) -> ObserveProviderPlan {
    let mut discovery = Vec::new();
    let mut market = Vec::new();

    if config.dexscreener_enabled {
        discovery.push(ProviderId::DexScreener);
        market.push(ProviderId::DexScreener);
    }
    if config.meteora_enabled {
        market.push(ProviderId::Meteora);
    }

    ObserveProviderPlan {
        discovery,
        market,
        chain: vec![ProviderId::SolanaPublic],
        transactions: vec![ProviderId::SolanaPublic],
        realtime: vec![ProviderId::SolanaPublic],
    }
}

/// Assemble the real free-source observer without performing any network I/O.
/// Provider requests begin only when the caller runs an observation cycle.
pub fn build_free_observer(
    db: ShreksDb,
    config: &ProviderConfig,
) -> Result<Observer, ProviderError> {
    let mut observer = Observer::new(db);

    if config.dexscreener_enabled {
        let dexscreener = Arc::new(DexScreenerProvider::new());
        observer = observer
            .with_discovery_provider(dexscreener.clone())
            .with_market_provider(dexscreener);
    }

    if config.meteora_enabled {
        observer = observer.with_market_provider(Arc::new(MeteoraProvider::new()));
    }

    let solana_public = Arc::new(StandardSolanaRpcProvider::solana_public()?);
    observer = observer
        .with_chain_provider(solana_public.clone())
        .with_transaction_provider(solana_public);

    Ok(observer)
}

impl Observer {
    /// Drain confirmed Pump realtime envelopes into durable observe-only storage.
    ///
    /// This writer intentionally performs no provider requests and owns no
    /// strategy, signing, or execution authority. Lifecycle evidence enters the
    /// existing restart-safe inboxes immediately, while bonding-curve and
    /// PumpSwap trade economics are stored immutably by `(signature, ordinal)`
    /// for later normalization.
    pub async fn run_pump_realtime_writer(
        db: ShreksDb,
        mut receiver: mpsc::Receiver<PumpRealtimeNotification>,
    ) -> Result<usize, ObserverError> {
        let mut trade_rows_inserted = 0_usize;

        while let Some(notification) = receiver.recv().await {
            let observed_at_unix_ms = realtime_observed_at_unix_ms()?;
            trade_rows_inserted = persist_pump_realtime_notification(
                &db,
                &notification,
                observed_at_unix_ms,
                trade_rows_inserted,
            )?;
        }

        Ok(trade_rows_inserted)
    }

    pub async fn run_pump_realtime_session_writer(
        db: ShreksDb,
        mut receiver: mpsc::Receiver<BoundedPumpRealtimeSessionNotification>,
    ) -> Result<usize, ObserverError> {
        let mut trade_rows_inserted = 0_usize;
        let mut current_process_session_sequence = None;
        let mut current_durable_session_id = None;

        while let Some(envelope) = receiver.recv().await {
            let notification = &envelope.notification;
            validate_realtime_identity(notification)?;
            let observed_at_unix_ms = realtime_observed_at_unix_ms()?;

            if current_process_session_sequence
                .is_some_and(|current| envelope.session_sequence < current)
            {
                return Err(ObserverError::Storage(StorageError::InvalidData(
                    "realtime coverage process session sequence moved backward".to_owned(),
                )));
            }

            if current_process_session_sequence == Some(envelope.session_sequence) {
                let session_id = current_durable_session_id.ok_or_else(|| {
                    ObserverError::Storage(StorageError::InvalidData(
                        "realtime coverage writer lost current durable session identity"
                            .to_owned(),
                    ))
                })?;
                db.extend_fast_realtime_coverage_session(
                    session_id,
                    notification.provider,
                    envelope.session_sequence,
                    observed_at_unix_ms,
                    notification.slot,
                    &notification.signature,
                )?;
            } else {
                let session = db.begin_fast_realtime_coverage_session(
                    notification.provider,
                    envelope.session_sequence,
                    observed_at_unix_ms,
                    notification.slot,
                    &notification.signature,
                )?;
                current_process_session_sequence = Some(envelope.session_sequence);
                current_durable_session_id = Some(session.session_id);
            }

            trade_rows_inserted = persist_pump_realtime_notification(
                &db,
                notification,
                observed_at_unix_ms,
                trade_rows_inserted,
            )?;
        }

        Ok(trade_rows_inserted)
    }
}

fn persist_pump_realtime_notification(
    db: &ShreksDb,
    notification: &PumpRealtimeNotification,
    observed_at_unix_ms: i64,
    mut trade_rows_inserted: usize,
) -> Result<usize, ObserverError> {
    validate_realtime_identity(notification)?;
    if let Some(lifecycle) = &notification.lifecycle {
        match lifecycle {
            PumpLifecycleSignal::Creation(signal) => retry_bounded(
        || {
            db.record_pump_launch_signal(
                &signal.signature,
                signal.slot,
                observed_at_unix_ms,
            )
        },
        is_storage_sqlite_busy_or_locked,
            )?,
            PumpLifecycleSignal::Migration(signal) => retry_bounded(
        || {
            db.record_pump_migration_signal(
                &signal.signature,
                signal.slot,
                observed_at_unix_ms,
            )
        },
        is_storage_sqlite_busy_or_locked,
            )?,
        }
    }

    for (index, trade) in notification.trades.iter().enumerate() {
        let ordinal = u32::try_from(index).map_err(|_| {
            ObserverError::Storage(StorageError::InvalidData(
        "Pump realtime notification contains more than u32::MAX trade events"
            .to_owned(),
            ))
        })?;

        let write = PumpTradeEvidenceWrite {
            provider: notification.provider,
            signature: notification.signature.clone(),
            ordinal,
            slot: notification.slot,
            observed_at_unix_ms,
            mint: trade.mint.clone(),
            quote_mint: trade.quote_mint.clone(),
            user: trade.user.clone(),
            is_buy: trade.is_buy,
            token_amount_raw: trade.token_amount_raw,
            sol_amount_raw: trade.sol_amount_raw,
            quote_amount_raw: trade.quote_amount_raw,
            timestamp_unix_seconds: trade.timestamp_unix_seconds,
            virtual_sol_reserves_raw: trade.virtual_sol_reserves_raw,
            virtual_token_reserves_raw: trade.virtual_token_reserves_raw,
            real_sol_reserves_raw: trade.real_sol_reserves_raw,
            real_token_reserves_raw: trade.real_token_reserves_raw,
            virtual_quote_reserves_raw: trade.virtual_quote_reserves_raw,
            real_quote_reserves_raw: trade.real_quote_reserves_raw,
            ix_name: trade.ix_name.clone(),
        };
        let economics = PumpTradeExecutionEconomicsWrite {
            signature: notification.signature.clone(),
            ordinal,
            fee_recipient: trade.fee_recipient.clone(),
            fee_basis_points: trade.fee_basis_points,
            fee_raw: trade.fee_raw,
            creator: trade.creator.clone(),
            creator_fee_basis_points: trade.creator_fee_basis_points,
            creator_fee_raw: trade.creator_fee_raw,
            cashback_fee_basis_points: trade.cashback_fee_basis_points,
            cashback_raw: trade.cashback_raw,
            buyback_fee_basis_points: trade.buyback_fee_basis_points,
            buyback_fee_raw: trade.buyback_fee_raw,
        };

        match retry_bounded(
            || {
        db.with_fast_event_write_transaction(
            || -> Result<EvidenceWriteOutcome, StorageError> {
                let outcome = db.record_pump_trade_evidence_or_quarantine(&write)?;
                if matches!(
            outcome,
            EvidenceWriteOutcome::Inserted | EvidenceWriteOutcome::Duplicate
                ) {
            db.record_pump_trade_execution_economics(&economics)?;
                }
                Ok(outcome)
            },
        )
            },
            is_storage_sqlite_busy_or_locked,
        )? {
            EvidenceWriteOutcome::Inserted => {
        trade_rows_inserted = increment_trade_rows(trade_rows_inserted)?;
            }
            EvidenceWriteOutcome::Duplicate
            | EvidenceWriteOutcome::QuarantinedConflict => {}
        }
    }

    for trade in &notification.pump_swap_trades {
        let ordinal = pump_swap_event_ordinal(trade.log_index)?;
        let write = PumpSwapTradeEvidenceWrite {
            provider: notification.provider,
            signature: notification.signature.clone(),
            ordinal,
            log_index: trade.log_index,
            slot: notification.slot,
            observed_at_unix_ms,
            pool: trade.pool.clone(),
            user: trade.user.clone(),
            is_buy: trade.is_buy,
            base_amount_raw: trade.base_amount_raw,
            quote_amount_raw: trade.quote_amount_raw,
            user_quote_amount_raw: trade.user_quote_amount_raw,
            timestamp_unix_seconds: trade.timestamp_unix_seconds,
            pool_base_reserves_raw: trade.pool_base_reserves_raw,
            pool_quote_reserves_raw: trade.pool_quote_reserves_raw,
        };
        let (
            coin_creator,
            coin_creator_fee_basis_points,
            coin_creator_fee_raw,
            cashback_fee_basis_points,
            cashback_raw,
            buyback_fee_basis_points,
            buyback_fee_raw,
            virtual_quote_reserves_raw,
            can_boost,
            base_supply_raw,
        ) = match &trade.current_economics {
            Some(current) => (
        Some(current.coin_creator.clone()),
        Some(current.coin_creator_fee_basis_points),
        Some(current.coin_creator_fee_raw),
        Some(current.cashback_fee_basis_points),
        Some(current.cashback_raw),
        Some(current.buyback_fee_basis_points),
        Some(current.buyback_fee_raw),
        Some(current.virtual_quote_reserves_raw),
        Some(current.can_boost),
        Some(current.base_supply_raw),
            ),
            None => (None, None, None, None, None, None, None, None, None, None),
        };
        let economics = PumpSwapExecutionEconomicsWrite {
            signature: notification.signature.clone(),
            ordinal,
            lp_fee_basis_points: trade.lp_fee_basis_points,
            lp_fee_raw: trade.lp_fee_raw,
            protocol_fee_basis_points: trade.protocol_fee_basis_points,
            protocol_fee_raw: trade.protocol_fee_raw,
            quote_amount_with_or_without_lp_fee_raw: trade
        .quote_amount_with_or_without_lp_fee_raw,
            coin_creator,
            coin_creator_fee_basis_points,
            coin_creator_fee_raw,
            cashback_fee_basis_points,
            cashback_raw,
            buyback_fee_basis_points,
            buyback_fee_raw,
            virtual_quote_reserves_raw,
            can_boost,
            base_supply_raw,
        };

        match retry_bounded(
            || {
        db.with_fast_event_write_transaction(
            || -> Result<EvidenceWriteOutcome, StorageError> {
                let outcome =
            db.record_pump_swap_trade_evidence_or_quarantine(&write)?;
                if matches!(
            outcome,
            EvidenceWriteOutcome::Inserted | EvidenceWriteOutcome::Duplicate
                ) {
            db.record_pump_swap_execution_economics(&economics)?;
                }
                Ok(outcome)
            },
        )
            },
            is_storage_sqlite_busy_or_locked,
        )? {
            EvidenceWriteOutcome::Inserted => {
        trade_rows_inserted = increment_trade_rows(trade_rows_inserted)?;
            }
            EvidenceWriteOutcome::Duplicate
            | EvidenceWriteOutcome::QuarantinedConflict => {}
        }
    }
    Ok(trade_rows_inserted)
}


fn increment_trade_rows(current: usize) -> Result<usize, ObserverError> {
    current.checked_add(1).ok_or_else(|| {
        ObserverError::Storage(StorageError::InvalidData(
            "Pump realtime inserted-row count overflowed usize".to_owned(),
        ))
    })
}

fn validate_realtime_identity(notification: &PumpRealtimeNotification) -> Result<(), ObserverError> {
    if !matches!(
        notification.provider,
        ProviderId::Helius
            | ProviderId::Chainstack
            | ProviderId::Alchemy
            | ProviderId::SolanaPublic
    ) {
        return Err(ObserverError::Storage(StorageError::InvalidData(
            "Pump realtime notification provider must be Helius, Chainstack, Alchemy, or SolanaPublic".to_owned(),
        )));
    }
    if notification.signature.trim().is_empty() {
        return Err(ObserverError::Storage(StorageError::InvalidData(
            "Pump realtime notification signature must not be empty".to_owned(),
        )));
    }

    if let Some(lifecycle) = &notification.lifecycle {
        let (signature, slot) = match lifecycle {
            PumpLifecycleSignal::Creation(signal) => (&signal.signature, signal.slot),
            PumpLifecycleSignal::Migration(signal) => (&signal.signature, signal.slot),
        };
        if signature != &notification.signature || slot != notification.slot {
            return Err(ObserverError::Storage(StorageError::InvalidData(
                "Pump realtime lifecycle identity does not match envelope signature/slot"
                    .to_owned(),
            )));
        }
    }

    Ok(())
}

fn realtime_observed_at_unix_ms() -> Result<i64, ObserverError> {
    let elapsed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(ObserverError::Clock)?;
    i64::try_from(elapsed.as_millis()).map_err(|_| ObserverError::ClockOverflow)
}

fn non_blank(value: Option<String>) -> Option<String> {
    value.filter(|candidate| !candidate.trim().is_empty())
}
