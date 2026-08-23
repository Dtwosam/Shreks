//! Jupiter Swap V2 read-only quote/build adapter.

use std::{collections::HashSet, time::{SystemTime, UNIX_EPOCH}};

use async_trait::async_trait;
use serde::Deserialize;
use shreks_core::{ProviderId, QuoteRequest, QuoteSnapshot};

use crate::{
    http::classify_http_failure, ProviderError, ProviderErrorKind, QuoteProvider,
};

const BUILD_ENDPOINT: &str = "https://api.jup.ag/swap/v2/build";

pub fn build_url(request: &QuoteRequest) -> String {
    format!(
        "{BUILD_ENDPOINT}?inputMint={}&outputMint={}&amount={}&taker={}&slippageBps={}",
        request.input_mint,
        request.output_mint,
        request.amount,
        request.taker,
        request.slippage_bps
    )
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct BuildResponse {
    input_mint: String,
    output_mint: String,
    in_amount: String,
    out_amount: String,
    other_amount_threshold: String,
    slippage_bps: u16,
    price_impact_pct: Option<String>,
    route_plan: Vec<RouteStep>,
}

#[derive(Debug, Deserialize)]
struct RouteStep {
    #[serde(rename = "swapInfo")]
    swap_info: SwapInfo,
}

#[derive(Debug, Deserialize)]
struct SwapInfo {
    label: String,
}

pub fn parse_build_response(
    body: &str,
    quoted_at_unix_ms: i64,
) -> Result<QuoteSnapshot, ProviderError> {
    let value: serde_json::Value = serde_json::from_str(body).map_err(|error| {
        ProviderError::new(
            ProviderId::Jupiter,
            ProviderErrorKind::InvalidResponse,
            format!("invalid Jupiter Swap V2 JSON: {error}"),
        )
    })?;

    if let Some(error) = value.get("error").and_then(serde_json::Value::as_str) {
        let code = value
            .get("errorCode")
            .and_then(serde_json::Value::as_str)
            .map(|code| format!(" ({code})"))
            .unwrap_or_default();
        return Err(ProviderError::new(
            ProviderId::Jupiter,
            ProviderErrorKind::InvalidResponse,
            format!("Jupiter Swap V2 error{code}: {error}"),
        ));
    }

    let response: BuildResponse = serde_json::from_value(value).map_err(|error| {
        ProviderError::new(
            ProviderId::Jupiter,
            ProviderErrorKind::InvalidResponse,
            format!("invalid Jupiter Swap V2 build response: {error}"),
        )
    })?;

    let input_amount = parse_amount("inAmount", &response.in_amount)?;
    let output_amount = parse_amount("outAmount", &response.out_amount)?;
    let minimum_output_amount = parse_amount(
        "otherAmountThreshold",
        &response.other_amount_threshold,
    )?;

    let mut seen = HashSet::new();
    let route_labels = response
        .route_plan
        .into_iter()
        .map(|step| step.swap_info.label)
        .filter(|label| !label.trim().is_empty())
        .filter(|label| seen.insert(label.clone()))
        .collect::<Vec<_>>();

    Ok(QuoteSnapshot {
        provider: ProviderId::Jupiter,
        input_mint: response.input_mint,
        output_mint: response.output_mint,
        input_amount,
        output_amount,
        minimum_output_amount,
        slippage_bps: response.slippage_bps,
        price_impact_pct: response.price_impact_pct,
        route_available: !route_labels.is_empty(),
        route_labels,
        quoted_at_unix_ms,
    })
}

pub struct JupiterProvider {
    api_key: String,
    client: reqwest::Client,
}

impl JupiterProvider {
    pub fn new(api_key: impl Into<String>) -> Result<Self, ProviderError> {
        let api_key = api_key.into();
        if api_key.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::Jupiter,
                ProviderErrorKind::InvalidRequest,
                "Jupiter API key must not be empty",
            ));
        }

        Ok(Self {
            api_key,
            client: reqwest::Client::new(),
        })
    }
}

#[async_trait]
impl QuoteProvider for JupiterProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Jupiter
    }

    async fn quote(&self, request: &QuoteRequest) -> Result<QuoteSnapshot, ProviderError> {
        let response = self
            .client
            .get(build_url(request))
            .header("x-api-key", &self.api_key)
            .send()
            .await
            .map_err(map_reqwest_error)?;
        let status = response.status();
        let retry_after = response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|value| value.to_str().ok())
            .map(str::to_owned);
        let body = response.text().await.map_err(map_reqwest_error)?;

        if !status.is_success() {
            return Err(classify_http_failure(
                ProviderId::Jupiter,
                status.as_u16(),
                retry_after.as_deref(),
                &body,
            ));
        }

        let quote = parse_build_response(&body, unix_time_ms()?)?;
        validate_matches_request(request, quote)
    }
}

fn validate_matches_request(
    request: &QuoteRequest,
    quote: QuoteSnapshot,
) -> Result<QuoteSnapshot, ProviderError> {
    if quote.input_mint != request.input_mint
        || quote.output_mint != request.output_mint
        || quote.input_amount != request.amount
        || quote.slippage_bps != request.slippage_bps
    {
        return Err(ProviderError::new(
            ProviderId::Jupiter,
            ProviderErrorKind::InvalidResponse,
            "Jupiter quote does not match the requested mints, amount, or slippage",
        ));
    }

    Ok(quote)
}

fn parse_amount(field: &str, raw: &str) -> Result<u64, ProviderError> {
    raw.parse::<u64>().map_err(|error| {
        ProviderError::new(
            ProviderId::Jupiter,
            ProviderErrorKind::InvalidResponse,
            format!("invalid Jupiter {field} value: {error}"),
        )
    })
}

fn map_reqwest_error(error: reqwest::Error) -> ProviderError {
    let (kind, message) = if error.is_timeout() {
        (ProviderErrorKind::Timeout, "Jupiter request timed out")
    } else {
        (
            ProviderErrorKind::Unavailable,
            "Jupiter transport request failed",
        )
    };

    // Keep transport errors generic so API credentials and future sensitive
    // request metadata cannot accidentally reach logs through reqwest URLs.
    ProviderError::new(ProviderId::Jupiter, kind, message)
}

fn unix_time_ms() -> Result<i64, ProviderError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|error| {
        ProviderError::new(
            ProviderId::Jupiter,
            ProviderErrorKind::InvalidResponse,
            format!("system clock before Unix epoch: {error}"),
        )
    })?;
    i64::try_from(elapsed.as_millis()).map_err(|_| {
        ProviderError::new(
            ProviderId::Jupiter,
            ProviderErrorKind::InvalidResponse,
            "system clock exceeds i64 milliseconds",
        )
    })
}
