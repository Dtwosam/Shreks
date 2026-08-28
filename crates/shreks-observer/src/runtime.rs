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
    helius::HeliusProvider,
    meteora::MeteoraProvider,
    pump::PumpLifecycleSignal,
    pump_realtime::PumpRealtimeNotification,
    ProviderError,
};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
    StorageError,
};
use tokio::sync::mpsc;

use crate::{Observer, ObserverError};

const DEFAULT_DB_PATH: &str = "data/shreks.db";
const DEFAULT_CYCLE_INTERVAL_SECONDS: u64 = 30;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RuntimeConfigError {
    InvalidCycleInterval(String),
}

impl fmt::Display for RuntimeConfigError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidCycleInterval(value) => write!(
                formatter,
                "SHREKS_OBSERVER_INTERVAL_SECONDS must be a positive integer; got '{value}'"
            ),
        }
    }
}

impl Error for RuntimeConfigError {}

/// Environment-derived configuration for the observe-only process.
///
/// ProviderConfig's Debug implementation intentionally exposes only enablement
/// and request budgets, never API-key contents.
pub struct ObserverRuntimeConfig {
    pub db_path: PathBuf,
    pub cycle_interval: Duration,
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

        Ok(Self {
            db_path,
            cycle_interval,
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
/// Jupiter is deliberately absent: quotes/execution do not belong in Phase A
/// observation even when a Jupiter API key happens to be configured.
pub fn free_observe_provider_plan(config: &ProviderConfig) -> ObserveProviderPlan {
    let mut discovery = Vec::new();
    let mut market = Vec::new();
    let mut chain = Vec::new();
    let mut transactions = Vec::new();
    let mut realtime = Vec::new();

    if config.dexscreener_enabled {
        discovery.push(ProviderId::DexScreener);
        market.push(ProviderId::DexScreener);
    }
    if config.meteora_enabled {
        market.push(ProviderId::Meteora);
    }
    if config.helius_enabled() {
        chain.push(ProviderId::Helius);
        transactions.push(ProviderId::Helius);
        realtime.push(ProviderId::Helius);
    }
    if config.chainstack_enabled() {
        realtime.push(ProviderId::Chainstack);
    }
    if config.alchemy_enabled() {
        realtime.push(ProviderId::Alchemy);
    }

    ObserveProviderPlan {
        discovery,
        market,
        chain,
        transactions,
        realtime,
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

    if let Some(api_key) = config.helius_api_key() {
        let helius = Arc::new(HeliusProvider::new(api_key)?);
        observer = observer
            .with_chain_provider(helius.clone())
            .with_transaction_provider(helius);
    }

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
            validate_realtime_identity(&notification)?;
            let observed_at_unix_ms = realtime_observed_at_unix_ms()?;

            if let Some(lifecycle) = &notification.lifecycle {
                match lifecycle {
                    PumpLifecycleSignal::Creation(signal) => db.record_pump_launch_signal(
                        &signal.signature,
                        signal.slot,
                        observed_at_unix_ms,
                    )?,
                    PumpLifecycleSignal::Migration(signal) => db.record_pump_migration_signal(
                        &signal.signature,
                        signal.slot,
                        observed_at_unix_ms,
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

                if db.record_pump_trade_evidence(&write)? {
                    trade_rows_inserted = increment_trade_rows(trade_rows_inserted)?;
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

                if db.record_pump_swap_trade_evidence(&write)? {
                    trade_rows_inserted = increment_trade_rows(trade_rows_inserted)?;
                }
            }
        }

        Ok(trade_rows_inserted)
    }
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
        ProviderId::Helius | ProviderId::Chainstack | ProviderId::Alchemy
    ) {
        return Err(ObserverError::Storage(StorageError::InvalidData(
            "Pump realtime notification provider must be Helius, Chainstack, or Alchemy".to_owned(),
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
