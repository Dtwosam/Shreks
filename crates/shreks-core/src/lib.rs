//! Shared domain primitives for Shreks.

mod fast_lane;
pub use fast_lane::{
    FastEvent, FastEventError, FastEventId, FastEventKind, FastMarketKey, FastMarketSnapshot,
    FastMarketState, FastReserveContext, FastStateError, FastWindowSummary, DEFAULT_FAST_WINDOWS_MS,
};
mod lifecycle;
pub use lifecycle::{LifecycleEventKind, TokenLifecycleEvent};
mod wallet;
pub use wallet::{WalletActionKind, WalletObservation, WalletObservationEvidence};

use std::{error::Error, fmt, str::FromStr};

/// Operating mode for the Shreks runtime.
///
/// Live execution is represented here as a state only. Permission to enter
/// `Live` will be guarded by later risk and promotion gates.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum RuntimeMode {
    #[default]
    Observe,
    Paper,
    Shadow,
    Live,
    Halted,
}

impl RuntimeMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Observe => "observe",
            Self::Paper => "paper",
            Self::Shadow => "shadow",
            Self::Live => "live",
            Self::Halted => "halted",
        }
    }
}

impl fmt::Display for RuntimeMode {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseRuntimeModeError {
    value: String,
}

impl ParseRuntimeModeError {
    fn new(value: &str) -> Self {
        Self {
            value: value.to_owned(),
        }
    }
}

impl fmt::Display for ParseRuntimeModeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "unsupported runtime mode '{}'", self.value)
    }
}

impl Error for ParseRuntimeModeError {}

impl FromStr for RuntimeMode {
    type Err = ParseRuntimeModeError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value.trim().to_ascii_lowercase().as_str() {
            "observe" => Ok(Self::Observe),
            "paper" => Ok(Self::Paper),
            "shadow" => Ok(Self::Shadow),
            "live" => Ok(Self::Live),
            "halted" => Ok(Self::Halted),
            other => Err(ParseRuntimeModeError::new(other)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ProviderId {
    DexScreener,
    Helius,
    Alchemy,
    Chainstack,
    SolanaPublic,
    Jupiter,
    Meteora,
}

impl ProviderId {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::DexScreener => "dexscreener",
            Self::Helius => "helius",
            Self::Alchemy => "alchemy",
            Self::Chainstack => "chainstack",
            Self::SolanaPublic => "solana_public",
            Self::Jupiter => "jupiter",
            Self::Meteora => "meteora",
        }
    }
}

impl fmt::Display for ProviderId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ProviderHealthState {
    Healthy,
    Degraded,
    Unavailable,
    Exhausted,
}

impl ProviderHealthState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Healthy => "healthy",
            Self::Degraded => "degraded",
            Self::Unavailable => "unavailable",
            Self::Exhausted => "exhausted",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum VenueId {
    PumpFunBondingCurve,
    PumpSwap,
    Raydium,
    MeteoraDlmm,
    Jupiter,
    Unknown,
}

impl VenueId {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::PumpFunBondingCurve => "pump_fun_bonding_curve",
            Self::PumpSwap => "pump_swap",
            Self::Raydium => "raydium",
            Self::MeteoraDlmm => "meteora_dlmm",
            Self::Jupiter => "jupiter",
            Self::Unknown => "unknown",
        }
    }
}

impl fmt::Display for VenueId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct PairMarketData {
    pub mint: String,
    pub quote_mint: String,
    pub venue: VenueId,
    pub price_quote: f64,
    pub liquidity_quote: Option<f64>,
    pub volume_24h_quote: Option<f64>,
    pub buys_24h: Option<u64>,
    pub sells_24h: Option<u64>,
    pub market_cap_quote: Option<f64>,
    pub fdv_quote: Option<f64>,
    pub price_change_5m_pct: Option<f64>,
    pub price_change_1h_pct: Option<f64>,
    pub price_change_6h_pct: Option<f64>,
    pub price_change_24h_pct: Option<f64>,
    pub pair_created_at_unix_ms: Option<i64>,
    pub observed_at_unix_ms: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiscoveredToken {
    pub mint: String,
    pub source: ProviderId,
    pub discovered_at_unix_ms: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TokenMintState {
    pub mint: String,
    pub decimals: u8,
    pub supply_raw: u64,
    pub mint_authority_present: bool,
    pub freeze_authority_present: bool,
    pub observed_at_unix_ms: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TransactionWindow {
    pub wallet: String,
    pub start_unix_ms: i64,
    pub end_unix_ms: i64,
    pub transaction_count: u64,
}
