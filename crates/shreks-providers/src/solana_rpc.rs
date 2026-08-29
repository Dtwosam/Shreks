//! Read-only standard Solana JSON-RPC adapter used when provider-specific
//! enriched APIs are unavailable. The protected endpoint may contain credential
//! material and is therefore never exposed through Debug or error messages.

use std::{
    fmt,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use serde_json::{json, Value};
use shreks_core::{ProviderId, TokenMintState};
use tokio::{
    sync::Mutex,
    time::{sleep_until, Instant},
};

use crate::{
    helius::parse_mint_account_response,
    http::classify_http_failure,
    ChainDataProvider, ProviderError, ProviderErrorKind, TransactionProvider,
};

const CHAINSTACK_RPC_INTERVAL: Duration = Duration::from_millis(125); // 8 RPS.
pub const TRANSPORT_PROVIDER_FIELD: &str = "_shreks_transport_provider";

/// Derive the HTTPS JSON-RPC endpoint from the protected Chainstack websocket
/// endpoint already provisioned on the runtime host. The returned URL is still
/// credential material and callers must not log it.
pub fn chainstack_http_url(websocket_endpoint: &str) -> Result<String, ProviderError> {
    let endpoint = websocket_endpoint.trim();
    if let Some(rest) = endpoint.strip_prefix("wss://") {
        if !rest.is_empty() {
            return Ok(format!("https://{rest}"));
        }
    }
    if let Some(rest) = endpoint.strip_prefix("ws://") {
        if !rest.is_empty() {
            return Ok(format!("http://{rest}"));
        }
    }

    Err(ProviderError::new(
        ProviderId::Chainstack,
        ProviderErrorKind::InvalidRequest,
        "Chainstack Solana RPC endpoint must originate from a non-empty ws:// or wss:// endpoint",
    ))
}

/// Parse the standard `getAccountInfo` jsonParsed mint response while
/// preserving the actual transport provider as durable provenance.
pub fn parse_mint_account_response_for_provider(
    provider: ProviderId,
    body: &str,
    mint: &str,
    observed_at_unix_ms: i64,
) -> Result<TokenMintState, ProviderError> {
    if !matches!(provider, ProviderId::Helius | ProviderId::Chainstack) {
        return Err(ProviderError::new(
            provider,
            ProviderErrorKind::InvalidRequest,
            "standard Solana mint-state parser requires an approved read-only RPC provider",
        ));
    }

    match parse_mint_account_response(body, mint, observed_at_unix_ms) {
        Ok(mut state) => {
            state.provider = provider;
            Ok(state)
        }
        Err(mut error) => {
            error.provider = provider;
            if provider != ProviderId::Helius {
                error.message = error.message.replace("Helius", "standard Solana RPC");
            }
            Err(error)
        }
    }
}

/// Add internal transport provenance to a valid standard JSON-RPC transaction
/// response. The marker contains only the provider id, never endpoint material.
pub fn annotate_transaction_response_for_provider(
    provider: ProviderId,
    body: &str,
) -> Result<String, ProviderError> {
    let mut value: Value = serde_json::from_str(body).map_err(|_| {
        ProviderError::new(
            provider,
            ProviderErrorKind::InvalidResponse,
            "standard Solana transaction RPC returned invalid JSON",
        )
    })?;
    let object = value.as_object_mut().ok_or_else(|| {
        ProviderError::new(
            provider,
            ProviderErrorKind::InvalidResponse,
            "standard Solana transaction RPC returned a non-object response",
        )
    })?;
    object.insert(
        TRANSPORT_PROVIDER_FIELD.to_owned(),
        Value::String(provider.as_str().to_owned()),
    );
    serde_json::to_string(&value).map_err(|_| {
        ProviderError::new(
            provider,
            ProviderErrorKind::InvalidResponse,
            "standard Solana transaction RPC response could not be normalized",
        )
    })
}

/// Chainstack adapter restricted to the two standard read-only calls FL1 needs:
/// confirmed transaction verification and SPL mint-state inspection.
pub struct StandardSolanaRpcProvider {
    provider: ProviderId,
    rpc_url: String,
    client: reqwest::Client,
    next_allowed: Mutex<Instant>,
}

impl StandardSolanaRpcProvider {
    pub fn chainstack(websocket_endpoint: &str) -> Result<Self, ProviderError> {
        Ok(Self {
            provider: ProviderId::Chainstack,
            rpc_url: chainstack_http_url(websocket_endpoint)?,
            client: reqwest::Client::new(),
            next_allowed: Mutex::new(Instant::now()),
        })
    }

    async fn pace(&self) {
        let mut next_allowed = self.next_allowed.lock().await;
        let now = Instant::now();
        if *next_allowed > now {
            sleep_until(*next_allowed).await;
        }
        *next_allowed = Instant::now() + CHAINSTACK_RPC_INTERVAL;
    }

    async fn post_rpc(&self, payload: &Value) -> Result<String, ProviderError> {
        self.pace().await;

        let response = self
            .client
            .post(&self.rpc_url)
            .json(payload)
            .send()
            .await
            .map_err(|_| {
                ProviderError::new(
                    self.provider,
                    ProviderErrorKind::Unavailable,
                    "Chainstack standard Solana RPC transport failed",
                )
            })?;

        let status = response.status();
        let retry_after = response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|value| value.to_str().ok())
            .map(str::to_owned);
        let body = response.text().await.map_err(|_| {
            ProviderError::new(
                self.provider,
                ProviderErrorKind::Unavailable,
                "Chainstack standard Solana RPC response body could not be read",
            )
        })?;

        if !status.is_success() {
            // Provider error bodies are deliberately excluded from the message:
            // the protected endpoint is credential material and must never leak
            // through an upstream diagnostic echo.
            return Err(classify_http_failure(
                self.provider,
                status.as_u16(),
                retry_after.as_deref(),
                "",
            ));
        }

        Ok(body)
    }

    fn mint_state_request(token_mint: &str) -> Result<Value, ProviderError> {
        if token_mint.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::Chainstack,
                ProviderErrorKind::InvalidRequest,
                "token mint must not be empty",
            ));
        }

        Ok(json!({
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
        }))
    }

    fn transaction_request(signature: &str) -> Result<Value, ProviderError> {
        if signature.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::Chainstack,
                ProviderErrorKind::InvalidRequest,
                "transaction signature must not be empty",
            ));
        }

        Ok(json!({
            "jsonrpc": "2.0",
            "id": "shreks-pump-transaction",
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0
                }
            ]
        }))
    }
}

impl fmt::Debug for StandardSolanaRpcProvider {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("StandardSolanaRpcProvider")
            .field("provider", &self.provider)
            .field("rpc_url", &"<redacted>")
            .finish_non_exhaustive()
    }
}

#[async_trait]
impl ChainDataProvider for StandardSolanaRpcProvider {
    fn provider_id(&self) -> ProviderId {
        self.provider
    }

    async fn token_mint_state(&self, token_mint: &str) -> Result<TokenMintState, ProviderError> {
        let payload = Self::mint_state_request(token_mint)?;
        let body = self.post_rpc(&payload).await?;
        let observed_at_unix_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| {
                ProviderError::new(
                    self.provider,
                    ProviderErrorKind::Unavailable,
                    "system clock precedes Unix epoch",
                )
            })?
            .as_millis();
        let observed_at_unix_ms = i64::try_from(observed_at_unix_ms).map_err(|_| {
            ProviderError::new(
                self.provider,
                ProviderErrorKind::InvalidResponse,
                "system clock exceeds i64 milliseconds",
            )
        })?;

        parse_mint_account_response_for_provider(
            self.provider,
            &body,
            token_mint,
            observed_at_unix_ms,
        )
    }
}

#[async_trait]
impl TransactionProvider for StandardSolanaRpcProvider {
    fn provider_id(&self) -> ProviderId {
        self.provider
    }

    async fn transaction_json(&self, signature: &str) -> Result<String, ProviderError> {
        let payload = Self::transaction_request(signature)?;
        let body = self.post_rpc(&payload).await?;
        annotate_transaction_response_for_provider(self.provider, &body)
    }
}
