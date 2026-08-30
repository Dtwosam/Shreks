//! Free-tier-aware provider runtime configuration.

use std::fmt;

const DEFAULT_HELIUS_RPC_RPS: u32 = 8;
const DEFAULT_JUPITER_GENERAL_RPS: u32 = 1;
const DEFAULT_DEXSCREENER_MARKET_RPS: u32 = 4;
const DEFAULT_METEORA_MARKET_RPS: u32 = 1;

/// Runtime configuration for Shreks' free provider adapters.
///
/// Keyed providers are disabled when their runtime key/endpoint is absent or blank.
/// Public providers remain enabled. Request budgets intentionally sit at or
/// below the free/public ceilings Shreks is designed around.
pub struct ProviderConfig {
    helius_api_key: Option<String>,
    alchemy_api_key: Option<String>,
    chainstack_solana_wss_url: Option<String>,
    jupiter_api_key: Option<String>,
    pub dexscreener_enabled: bool,
    pub meteora_enabled: bool,
    pub helius_rpc_rps: u32,
    pub observer_helius_max_requests_per_process: Option<u64>,
    pub jupiter_general_rps: u32,
    pub dexscreener_market_rps: u32,
    pub meteora_market_rps: u32,
}

impl ProviderConfig {
    /// Build configuration from any environment-like lookup function.
    ///
    /// This keeps tests independent of process-global environment mutation and
    /// lets the runtime use `std::env::var` later without a second code path.
    pub fn from_lookup<F>(lookup: F) -> Self
    where
        F: Fn(&str) -> Option<String>,
    {
        Self {
            helius_api_key: non_blank(lookup("HELIUS_API_KEY")),
            alchemy_api_key: non_blank(lookup("ALCHEMY_API_KEY")),
            chainstack_solana_wss_url: non_blank(lookup("CHAINSTACK_SOLANA_WSS_URL")),
            jupiter_api_key: non_blank(lookup("JUPITER_API_KEY")),
            dexscreener_enabled: true,
            meteora_enabled: true,
            helius_rpc_rps: DEFAULT_HELIUS_RPC_RPS,
            observer_helius_max_requests_per_process: positive_u64(non_blank(lookup(
                "SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS",
            ))),
            jupiter_general_rps: DEFAULT_JUPITER_GENERAL_RPS,
            dexscreener_market_rps: DEFAULT_DEXSCREENER_MARKET_RPS,
            meteora_market_rps: DEFAULT_METEORA_MARKET_RPS,
        }
    }

    pub fn from_env() -> Self {
        Self::from_lookup(|name| std::env::var(name).ok())
    }

    pub fn helius_enabled(&self) -> bool {
        self.helius_api_key.is_some()
    }

    pub fn alchemy_enabled(&self) -> bool {
        self.alchemy_api_key.is_some()
    }

    pub fn chainstack_enabled(&self) -> bool {
        self.chainstack_solana_wss_url.is_some()
    }

    pub fn jupiter_enabled(&self) -> bool {
        self.jupiter_api_key.is_some()
    }

    pub fn helius_api_key(&self) -> Option<&str> {
        self.helius_api_key.as_deref()
    }

    pub fn alchemy_api_key(&self) -> Option<&str> {
        self.alchemy_api_key.as_deref()
    }

    pub fn chainstack_solana_wss_url(&self) -> Option<&str> {
        self.chainstack_solana_wss_url.as_deref()
    }

    pub fn jupiter_api_key(&self) -> Option<&str> {
        self.jupiter_api_key.as_deref()
    }
}

impl fmt::Debug for ProviderConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("ProviderConfig")
            .field("helius_enabled", &self.helius_enabled())
            .field("alchemy_enabled", &self.alchemy_enabled())
            .field("chainstack_enabled", &self.chainstack_enabled())
            .field("jupiter_enabled", &self.jupiter_enabled())
            .field("dexscreener_enabled", &self.dexscreener_enabled)
            .field("meteora_enabled", &self.meteora_enabled)
            .field("helius_rpc_rps", &self.helius_rpc_rps)
            .field(
                "observer_helius_max_requests_per_process",
                &self.observer_helius_max_requests_per_process,
            )
            .field("jupiter_general_rps", &self.jupiter_general_rps)
            .field("dexscreener_market_rps", &self.dexscreener_market_rps)
            .field("meteora_market_rps", &self.meteora_market_rps)
            .finish()
    }
}

fn non_blank(value: Option<String>) -> Option<String> {
    value.filter(|candidate| !candidate.trim().is_empty())
}

fn positive_u64(value: Option<String>) -> Option<u64> {
    value?.parse::<u64>().ok().filter(|candidate| *candidate > 0)
}
