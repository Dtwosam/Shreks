//! Meteora public-data adapter for DLMM and DAMM v2 pools.

use std::time::{SystemTime, UNIX_EPOCH};

use async_trait::async_trait;
use serde::Deserialize;
use shreks_core::{PairMarketData, ProviderId, VenueId};

use crate::{
    http::classify_http_failure, MarketDataProvider, ProviderError, ProviderErrorKind,
};

const DLMM_BASE_URL: &str = "https://dlmm.datapi.meteora.ag";
const DAMM_V2_BASE_URL: &str = "https://damm-v2.datapi.meteora.ag";

pub fn dlmm_pools_url(token_mint: &str) -> String {
    format!("{DLMM_BASE_URL}/pools?page=1&page_size=100&query={token_mint}")
}

pub fn damm_v2_pools_url(token_mint: &str) -> String {
    format!("{DAMM_V2_BASE_URL}/pools?page=1&page_size=100&query={token_mint}")
}

#[derive(Debug, Deserialize)]
struct PoolPage {
    data: Vec<MeteoraPool>,
}

#[derive(Debug, Deserialize)]
struct MeteoraToken {
    address: String,
    name: Option<String>,
    symbol: Option<String>,
    price: Option<f64>,
    market_cap: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct MeteoraPool {
    address: String,
    created_at: Option<i64>,
    #[allow(dead_code)]
    is_blacklisted: Option<bool>,
    token_x: MeteoraToken,
    token_y: MeteoraToken,
    tvl: Option<f64>,
    volume: Option<std::collections::BTreeMap<String, f64>>,
    #[allow(dead_code)]
    launchpad: Option<String>,
}

pub fn parse_pool_page_json(
    body: &str,
    requested_mint: &str,
    venue: VenueId,
    observed_at_unix_ms: i64,
) -> Result<Vec<PairMarketData>, ProviderError> {
    if !matches!(venue, VenueId::MeteoraDlmm | VenueId::MeteoraDammV2) {
        return Err(ProviderError::new(
            ProviderId::Meteora,
            ProviderErrorKind::InvalidRequest,
            "Meteora pool parser requires a Meteora venue",
        ));
    }

    let page: PoolPage = serde_json::from_str(body).map_err(|error| {
        ProviderError::new(
            ProviderId::Meteora,
            ProviderErrorKind::InvalidResponse,
            format!("invalid Meteora pool JSON: {error}"),
        )
    })?;

    let dex_id = match venue {
        VenueId::MeteoraDlmm => "meteora_dlmm",
        VenueId::MeteoraDammV2 => "meteora_damm_v2",
        _ => unreachable!("validated above"),
    };

    let mut normalized = Vec::new();

    for pool in page.data {
        let (base, quote) = if pool.token_x.address == requested_mint {
            (&pool.token_x, &pool.token_y)
        } else if pool.token_y.address == requested_mint {
            (&pool.token_y, &pool.token_x)
        } else {
            continue;
        };

        let volume = pool.volume.unwrap_or_default();
        let pair_created_at_unix_ms = pool
            .created_at
            .and_then(|seconds| seconds.checked_mul(1_000));

        normalized.push(PairMarketData {
            provider: ProviderId::Meteora,
            venue,
            chain_id: "solana".to_owned(),
            dex_id: dex_id.to_owned(),
            pair_address: pool.address,
            base_mint: base.address.clone(),
            base_name: base.name.clone(),
            base_symbol: base.symbol.clone(),
            quote_mint: quote.address.clone(),
            quote_name: quote.name.clone(),
            quote_symbol: quote.symbol.clone(),
            // Meteora's pool-level current-price convention depends on pool
            // orientation. Until orientation semantics are encoded explicitly,
            // do not expose it as a provider-neutral native price.
            price_native: None,
            price_usd: base.price.map(|value| value.to_string()),
            liquidity_usd: pool.tvl,
            volume_5m: volume.get("5m").copied(),
            volume_1h: volume.get("1h").copied(),
            volume_6h: volume.get("6h").copied(),
            volume_24h: volume.get("24h").copied(),
            transactions: Vec::new(),
            fdv_usd: None,
            market_cap_usd: base.market_cap,
            pair_created_at_unix_ms,
            observed_at_unix_ms,
        });
    }

    Ok(normalized)
}

pub struct MeteoraProvider {
    client: reqwest::Client,
}

impl Default for MeteoraProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl MeteoraProvider {
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
                ProviderId::Meteora,
                status.as_u16(),
                retry_after.as_deref(),
                &body,
            ));
        }

        Ok(body)
    }
}

#[async_trait]
impl MarketDataProvider for MeteoraProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Meteora
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        if token_mint.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::Meteora,
                ProviderErrorKind::InvalidRequest,
                "token mint must not be empty",
            ));
        }

        let observed_at = unix_time_ms()?;
        let dlmm = self.get_text(&dlmm_pools_url(token_mint)).await?;
        let damm_v2 = self.get_text(&damm_v2_pools_url(token_mint)).await?;

        let mut pairs = parse_pool_page_json(
            &dlmm,
            token_mint,
            VenueId::MeteoraDlmm,
            observed_at,
        )?;
        pairs.extend(parse_pool_page_json(
            &damm_v2,
            token_mint,
            VenueId::MeteoraDammV2,
            observed_at,
        )?);
        Ok(pairs)
    }
}

fn map_reqwest_error(error: reqwest::Error) -> ProviderError {
    let kind = if error.is_timeout() {
        ProviderErrorKind::Timeout
    } else {
        ProviderErrorKind::Unavailable
    };
    ProviderError::new(ProviderId::Meteora, kind, error.to_string())
}

fn unix_time_ms() -> Result<i64, ProviderError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|error| {
        ProviderError::new(
            ProviderId::Meteora,
            ProviderErrorKind::InvalidResponse,
            format!("system clock before Unix epoch: {error}"),
        )
    })?;
    i64::try_from(elapsed.as_millis()).map_err(|_| {
        ProviderError::new(
            ProviderId::Meteora,
            ProviderErrorKind::InvalidResponse,
            "system clock exceeds i64 milliseconds",
        )
    })
}
