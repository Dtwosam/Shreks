//! DEX Screener read-only discovery and market-data adapter.

use std::{collections::{BTreeMap, HashSet}, time::{SystemTime, UNIX_EPOCH}};

use async_trait::async_trait;
use serde::Deserialize;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, TransactionWindow, VenueId,
};

use crate::{
    http::classify_http_failure, DiscoveryProvider, MarketDataProvider, ProviderError,
    ProviderErrorKind,
};

const BASE_URL: &str = "https://api.dexscreener.com";
const LATEST_PROFILES_URL: &str = "https://api.dexscreener.com/token-profiles/latest/v1";
const LATEST_BOOSTS_URL: &str = "https://api.dexscreener.com/token-boosts/latest/v1";

pub fn token_pairs_url(token_mint: &str) -> String {
    format!("{BASE_URL}/token-pairs/v1/solana/{token_mint}")
}

pub fn classify_dex_venue(dex_id: &str) -> VenueId {
    match dex_id.to_ascii_lowercase().as_str() {
        "pumpfun" | "pump.fun" => VenueId::PumpFunBondingCurve,
        "pumpswap" | "pump-swap" => VenueId::PumpSwap,
        // DEX Screener's generic Meteora label does not prove which Meteora
        // pool family is involved. The direct Meteora adapter supplies that.
        _ => VenueId::OtherSolana,
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct DiscoveryItem {
    chain_id: Option<String>,
    token_address: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct TokenRef {
    address: String,
    name: Option<String>,
    symbol: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TransactionCounts {
    buys: u64,
    sells: u64,
}

#[derive(Debug, Deserialize)]
struct Liquidity {
    usd: Option<f64>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct DexPair {
    chain_id: String,
    dex_id: String,
    pair_address: String,
    base_token: TokenRef,
    quote_token: TokenRef,
    price_native: Option<String>,
    price_usd: Option<String>,
    txns: Option<BTreeMap<String, TransactionCounts>>,
    volume: Option<BTreeMap<String, f64>>,
    liquidity: Option<Liquidity>,
    fdv: Option<f64>,
    market_cap: Option<f64>,
    pair_created_at: Option<i64>,
}

pub fn parse_discovery_json(
    body: &str,
    discovered_at_unix_ms: i64,
) -> Result<Vec<DiscoveredToken>, ProviderError> {
    let items: Vec<DiscoveryItem> = serde_json::from_str(body).map_err(|error| {
        ProviderError::new(
            ProviderId::DexScreener,
            ProviderErrorKind::InvalidResponse,
            format!("invalid discovery JSON: {error}"),
        )
    })?;

    let mut seen = HashSet::new();
    let mut discovered = Vec::new();

    for item in items {
        if item.chain_id.as_deref() != Some("solana") {
            continue;
        }
        let Some(mint) = item.token_address.filter(|mint| !mint.trim().is_empty()) else {
            continue;
        };
        if !seen.insert(mint.clone()) {
            continue;
        }

        discovered.push(DiscoveredToken {
            mint,
            pair_address: None,
            dex_id: None,
            venue: None,
            discovered_at_unix_ms,
            source: ProviderId::DexScreener,
        });
    }

    Ok(discovered)
}

pub fn parse_token_pairs_json(
    body: &str,
    observed_at_unix_ms: i64,
) -> Result<Vec<PairMarketData>, ProviderError> {
    let pairs: Vec<DexPair> = serde_json::from_str(body).map_err(|error| {
        ProviderError::new(
            ProviderId::DexScreener,
            ProviderErrorKind::InvalidResponse,
            format!("invalid token-pairs JSON: {error}"),
        )
    })?;

    Ok(pairs
        .into_iter()
        .filter(|pair| pair.chain_id == "solana")
        .map(|pair| {
            let transactions = pair
                .txns
                .unwrap_or_default()
                .into_iter()
                .map(|(window, counts)| TransactionWindow {
                    window,
                    buys: counts.buys,
                    sells: counts.sells,
                })
                .collect();
            let volume = pair.volume.unwrap_or_default();
            let venue = classify_dex_venue(&pair.dex_id);

            PairMarketData {
                provider: ProviderId::DexScreener,
                venue,
                chain_id: pair.chain_id,
                dex_id: pair.dex_id,
                pair_address: pair.pair_address,
                base_mint: pair.base_token.address,
                base_name: pair.base_token.name,
                base_symbol: pair.base_token.symbol,
                quote_mint: pair.quote_token.address,
                quote_name: pair.quote_token.name,
                quote_symbol: pair.quote_token.symbol,
                price_native: pair.price_native,
                price_usd: pair.price_usd,
                liquidity_usd: pair.liquidity.and_then(|liquidity| liquidity.usd),
                volume_5m: volume.get("m5").copied(),
                volume_1h: volume.get("h1").copied(),
                volume_6h: volume.get("h6").copied(),
                volume_24h: volume.get("h24").copied(),
                transactions,
                fdv_usd: pair.fdv,
                market_cap_usd: pair.market_cap,
                pair_created_at_unix_ms: pair.pair_created_at,
                observed_at_unix_ms,
            }
        })
        .collect())
}

pub struct DexScreenerProvider {
    client: reqwest::Client,
}

impl Default for DexScreenerProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl DexScreenerProvider {
    pub fn new() -> Self {
        Self {
            client: reqwest::Client::new(),
        }
    }

    async fn get_text(&self, url: &str) -> Result<String, ProviderError> {
        let response = self.client.get(url).send().await.map_err(map_reqwest_error)?;
        let status = response.status();
        let retry_after = response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|value| value.to_str().ok())
            .map(str::to_owned);
        let body = response.text().await.map_err(map_reqwest_error)?;

        if !status.is_success() {
            return Err(classify_http_failure(
                ProviderId::DexScreener,
                status.as_u16(),
                retry_after.as_deref(),
                &body,
            ));
        }

        Ok(body)
    }
}

#[async_trait]
impl DiscoveryProvider for DexScreenerProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        let observed_at = unix_time_ms()?;
        let profiles = self.get_text(LATEST_PROFILES_URL).await?;
        let boosts = self.get_text(LATEST_BOOSTS_URL).await?;

        let mut combined = parse_discovery_json(&profiles, observed_at)?;
        combined.extend(parse_discovery_json(&boosts, observed_at)?);

        let mut seen = HashSet::new();
        combined.retain(|candidate| seen.insert(candidate.mint.clone()));
        Ok(combined)
    }
}

#[async_trait]
impl MarketDataProvider for DexScreenerProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        if token_mint.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::DexScreener,
                ProviderErrorKind::InvalidRequest,
                "token mint must not be empty",
            ));
        }

        let body = self.get_text(&token_pairs_url(token_mint)).await?;
        parse_token_pairs_json(&body, unix_time_ms()?)
    }
}

fn map_reqwest_error(error: reqwest::Error) -> ProviderError {
    let kind = if error.is_timeout() {
        ProviderErrorKind::Timeout
    } else {
        ProviderErrorKind::Unavailable
    };
    ProviderError::new(ProviderId::DexScreener, kind, error.to_string())
}

fn unix_time_ms() -> Result<i64, ProviderError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|error| {
        ProviderError::new(
            ProviderId::DexScreener,
            ProviderErrorKind::InvalidResponse,
            format!("system clock before Unix epoch: {error}"),
        )
    })?;
    i64::try_from(elapsed.as_millis()).map_err(|_| {
        ProviderError::new(
            ProviderId::DexScreener,
            ProviderErrorKind::InvalidResponse,
            "system clock exceeds i64 milliseconds",
        )
    })
}
