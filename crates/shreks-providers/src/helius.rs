//! Helius-backed Solana chain-data adapter.

use std::time::{SystemTime, UNIX_EPOCH};

use async_trait::async_trait;
use serde::Deserialize;
use serde_json::json;
use shreks_core::{ProviderId, TokenMintState};

use crate::{
    http::classify_http_failure, ChainDataProvider, ProviderError, ProviderErrorKind,
};

const MAINNET_RPC_BASE: &str = "https://mainnet.helius-rpc.com/?api-key=";

pub fn helius_rpc_url(api_key: &str) -> String {
    format!("{MAINNET_RPC_BASE}{api_key}")
}

#[derive(Debug, Deserialize)]
struct RpcResponse {
    result: Option<AccountInfoResult>,
    error: Option<RpcError>,
}

#[derive(Debug, Deserialize)]
struct RpcError {
    code: i64,
    message: String,
}

#[derive(Debug, Deserialize)]
struct AccountInfoResult {
    context: RpcContext,
    value: Option<AccountValue>,
}

#[derive(Debug, Deserialize)]
struct RpcContext {
    slot: u64,
}

#[derive(Debug, Deserialize)]
struct AccountValue {
    data: ParsedAccountData,
    owner: String,
}

#[derive(Debug, Deserialize)]
struct ParsedAccountData {
    parsed: ParsedAccount,
}

#[derive(Debug, Deserialize)]
struct ParsedAccount {
    #[serde(rename = "type")]
    account_type: String,
    info: MintInfo,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct MintInfo {
    decimals: u8,
    freeze_authority: Option<String>,
    is_initialized: bool,
    mint_authority: Option<String>,
    supply: String,
}

pub fn parse_mint_account_response(
    body: &str,
    mint: &str,
    observed_at_unix_ms: i64,
) -> Result<TokenMintState, ProviderError> {
    let response: RpcResponse = serde_json::from_str(body).map_err(|error| {
        ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            format!("invalid Helius JSON-RPC response: {error}"),
        )
    })?;

    if let Some(error) = response.error {
        let kind = match error.code {
            -32600..=-32602 => ProviderErrorKind::InvalidRequest,
            _ => ProviderErrorKind::Unavailable,
        };
        return Err(ProviderError::new(
            ProviderId::Helius,
            kind,
            format!("Solana JSON-RPC error {}: {}", error.code, error.message),
        ));
    }

    let result = response.result.ok_or_else(|| {
        ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            "Helius response contained neither result nor error",
        )
    })?;

    let value = result.value.ok_or_else(|| {
        ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::NotFound,
            format!("mint account {mint} does not exist"),
        )
    })?;

    if value.data.parsed.account_type != "mint" {
        return Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            format!(
                "account {mint} parsed as '{}' instead of mint",
                value.data.parsed.account_type
            ),
        ));
    }

    let info = value.data.parsed.info;
    if !info.is_initialized {
        return Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            format!("mint account {mint} is not initialized"),
        ));
    }

    let supply = info.supply.parse::<u64>().map_err(|error| {
        ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            format!("invalid mint supply for {mint}: {error}"),
        )
    })?;

    Ok(TokenMintState {
        provider: ProviderId::Helius,
        mint: mint.to_owned(),
        owner_program: value.owner,
        supply,
        decimals: info.decimals,
        mint_authority: info.mint_authority,
        freeze_authority: info.freeze_authority,
        slot: result.context.slot,
        observed_at_unix_ms,
    })
}

pub struct HeliusProvider {
    api_key: String,
    client: reqwest::Client,
}

impl HeliusProvider {
    pub fn new(api_key: impl Into<String>) -> Result<Self, ProviderError> {
        let api_key = api_key.into();
        if api_key.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::InvalidRequest,
                "Helius API key must not be empty",
            ));
        }

        Ok(Self {
            api_key,
            client: reqwest::Client::new(),
        })
    }
}

#[async_trait]
impl ChainDataProvider for HeliusProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn token_mint_state(&self, token_mint: &str) -> Result<TokenMintState, ProviderError> {
        if token_mint.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::InvalidRequest,
                "token mint must not be empty",
            ));
        }

        let payload = json!({
            "jsonrpc": "2.0",
            "id": "shreks-mint-state",
            "method": "getAccountInfo",
            "params": [
                token_mint,
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed"
                }
            ]
        });

        let response = self
            .client
            .post(helius_rpc_url(&self.api_key))
            .json(&payload)
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
                ProviderId::Helius,
                status.as_u16(),
                retry_after.as_deref(),
                &body,
            ));
        }

        parse_mint_account_response(&body, token_mint, unix_time_ms()?)
    }
}

fn map_reqwest_error(error: reqwest::Error) -> ProviderError {
    let (kind, message) = if error.is_timeout() {
        (ProviderErrorKind::Timeout, "Helius request timed out")
    } else {
        (
            ProviderErrorKind::Unavailable,
            "Helius transport request failed",
        )
    };

    // Do not include reqwest's Display string: the request URL contains the
    // Helius API key as a query parameter.
    ProviderError::new(ProviderId::Helius, kind, message)
}

fn unix_time_ms() -> Result<i64, ProviderError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|error| {
        ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            format!("system clock before Unix epoch: {error}"),
        )
    })?;
    i64::try_from(elapsed.as_millis()).map_err(|_| {
        ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            "system clock exceeds i64 milliseconds",
        )
    })
}
