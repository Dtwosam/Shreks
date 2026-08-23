use std::{error::Error, fmt, path::PathBuf, sync::Arc, time::Duration};

use shreks_core::ProviderId;
use shreks_providers::{
    config::ProviderConfig,
    dexscreener::DexScreenerProvider,
    helius::HeliusProvider,
    meteora::MeteoraProvider,
    ProviderError,
};
use shreks_storage::ShreksDb;

use crate::Observer;

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
    }

    ObserveProviderPlan {
        discovery,
        market,
        chain,
        transactions,
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

fn non_blank(value: Option<String>) -> Option<String> {
    value.filter(|candidate| !candidate.trim().is_empty())
}
