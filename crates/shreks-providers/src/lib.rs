//! External data-provider boundaries for Shreks.

pub mod dexscreener;
pub mod helius;
pub mod http;
pub mod jupiter;
pub mod meteora;

use std::{error::Error, fmt};

use async_trait::async_trait;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, QuoteRequest, QuoteSnapshot, TokenMintState,
};

/// Stable error categories used by every provider adapter.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ProviderErrorKind {
    Unauthorized,
    NotFound,
    RateLimited,
    Timeout,
    Unavailable,
    InvalidRequest,
    InvalidResponse,
}

impl ProviderErrorKind {
    pub const fn is_retryable(self) -> bool {
        matches!(self, Self::RateLimited | Self::Timeout | Self::Unavailable)
    }
}

/// Provider failure with enough structure for later health/backoff logic.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProviderError {
    pub provider: ProviderId,
    pub kind: ProviderErrorKind,
    pub message: String,
    pub retry_after_ms: Option<u64>,
}

impl ProviderError {
    pub fn new(
        provider: ProviderId,
        kind: ProviderErrorKind,
        message: impl Into<String>,
    ) -> Self {
        Self {
            provider,
            kind,
            message: message.into(),
            retry_after_ms: None,
        }
    }

    pub const fn is_retryable(&self) -> bool {
        self.kind.is_retryable()
    }

    pub const fn with_retry_after_ms(mut self, retry_after_ms: u64) -> Self {
        self.retry_after_ms = Some(retry_after_ms);
        self
    }
}

impl fmt::Display for ProviderError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{} provider {:?}: {}",
            self.provider, self.kind, self.message
        )
    }
}

impl Error for ProviderError {}

#[async_trait]
pub trait DiscoveryProvider: Send + Sync {
    fn provider_id(&self) -> ProviderId;

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError>;
}

#[async_trait]
pub trait MarketDataProvider: Send + Sync {
    fn provider_id(&self) -> ProviderId;

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError>;
}

#[async_trait]
pub trait ChainDataProvider: Send + Sync {
    fn provider_id(&self) -> ProviderId;

    async fn token_mint_state(&self, token_mint: &str) -> Result<TokenMintState, ProviderError>;
}

#[async_trait]
pub trait QuoteProvider: Send + Sync {
    fn provider_id(&self) -> ProviderId;

    async fn quote(&self, request: &QuoteRequest) -> Result<QuoteSnapshot, ProviderError>;
}
