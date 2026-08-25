//! Helius-backed Solana chain-data adapter.

use std::{
    collections::{BTreeMap, HashSet},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use serde::Deserialize;
use serde_json::{json, Value};
use shreks_core::{
    ProviderId, TokenDistributionRequest, TokenHolderDistribution, TokenMintState,
    MAX_TOKEN_DISTRIBUTION_PAGE_SIZE,
};

use crate::{
    http::classify_http_failure, ChainDataProvider, DistributionDataProvider, ProviderError,
    ProviderErrorKind, TransactionProvider,
};

const MAINNET_RPC_BASE: &str = "https://mainnet.helius-rpc.com/?api-key=";
const MAINNET_WS_BASE: &str = "wss://mainnet.helius-rpc.com/?api-key=";

pub fn helius_rpc_url(api_key: &str) -> String {
    format!("{MAINNET_RPC_BASE}{api_key}")
}

/// Build Helius' standard Solana mainnet PubSub endpoint.
///
/// Callers must never log or expose the returned URL because it contains the
/// API key as a query parameter.
pub fn helius_ws_url(api_key: &str) -> String {
    format!("{MAINNET_WS_BASE}{api_key}")
}

/// Build the current object-form Solana `getTransaction` request used to
/// verify a cheap websocket launch signal before it can become a candidate.
pub fn get_transaction_request(signature: &str) -> Result<Value, ProviderError> {
    if signature.trim().is_empty() {
        return Err(ProviderError::new(
            ProviderId::Helius,
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
        invalid_response(format!("invalid Helius JSON-RPC response: {error}"))
    })?;

    if let Some(error) = response.error {
        return Err(rpc_error(error));
    }

    let result = response.result.ok_or_else(|| {
        invalid_response("Helius response contained neither result nor error")
    })?;

    let value = result.value.ok_or_else(|| {
        ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::NotFound,
            format!("mint account {mint} does not exist"),
        )
    })?;

    if value.data.parsed.account_type != "mint" {
        return Err(invalid_response(format!(
            "account {mint} parsed as '{}' instead of mint",
            value.data.parsed.account_type
        )));
    }

    let info = value.data.parsed.info;
    if !info.is_initialized {
        return Err(invalid_response(format!(
            "mint account {mint} is not initialized"
        )));
    }

    let supply = info.supply.parse::<u64>().map_err(|error| {
        invalid_response(format!("invalid mint supply for {mint}: {error}"))
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

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct TokenAccountBalanceRow {
    pub address: String,
    pub mint: String,
    pub owner: String,
    #[serde(rename = "amount")]
    pub amount_raw: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TokenAccountsPage {
    pub last_indexed_slot: u64,
    pub total: u64,
    pub limit: usize,
    pub cursor: Option<String>,
    pub accounts: Vec<TokenAccountBalanceRow>,
}

#[derive(Debug, Deserialize)]
struct TokenAccountsRpcResponse {
    result: Option<TokenAccountsResult>,
    error: Option<RpcError>,
}

#[derive(Debug, Deserialize)]
struct TokenAccountsResult {
    last_indexed_slot: u64,
    total: u64,
    limit: usize,
    #[serde(default)]
    cursor: Option<String>,
    token_accounts: Vec<TokenAccountBalanceRow>,
}

pub fn get_token_accounts_request(
    request: &TokenDistributionRequest,
    page: usize,
) -> Result<Value, ProviderError> {
    if page == 0 || page > request.max_pages {
        return Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidRequest,
            format!(
                "holder distribution page must be within 1..={}; got {page}",
                request.max_pages
            ),
        ));
    }

    Ok(json!({
        "jsonrpc": "2.0",
        "id": "shreks-holder-distribution",
        "method": "getTokenAccounts",
        "params": {
            "mint": request.mint,
            "page": page,
            "limit": request.page_size,
            "options": {
                "showZeroBalance": false
            }
        }
    }))
}

pub fn parse_token_accounts_page(
    body: &str,
    expected_mint: &str,
) -> Result<TokenAccountsPage, ProviderError> {
    if expected_mint.trim().is_empty() {
        return Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidRequest,
            "holder distribution expected mint must not be empty",
        ));
    }

    let response: TokenAccountsRpcResponse = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!("invalid Helius getTokenAccounts response: {error}"))
    })?;

    if let Some(error) = response.error {
        return Err(rpc_error(error));
    }

    let result = response.result.ok_or_else(|| {
        invalid_response("Helius getTokenAccounts response contained neither result nor error")
    })?;

    if result.limit == 0 || result.limit > MAX_TOKEN_DISTRIBUTION_PAGE_SIZE {
        return Err(invalid_response(format!(
            "Helius holder page returned invalid limit {}",
            result.limit
        )));
    }
    if result.token_accounts.len() > result.limit {
        return Err(invalid_response(format!(
            "Helius holder page returned {} accounts above limit {}",
            result.token_accounts.len(),
            result.limit
        )));
    }

    for account in &result.token_accounts {
        if account.address.trim().is_empty() || account.owner.trim().is_empty() {
            return Err(invalid_response(
                "Helius holder page contained blank token-account address or owner",
            ));
        }
        if account.mint != expected_mint {
            return Err(invalid_response(format!(
                "Helius holder account mint {} did not match requested mint {expected_mint}",
                account.mint
            )));
        }
    }

    Ok(TokenAccountsPage {
        last_indexed_slot: result.last_indexed_slot,
        total: result.total,
        limit: result.limit,
        cursor: result.cursor,
        accounts: result.token_accounts,
    })
}

pub fn aggregate_token_account_pages(
    request: &TokenDistributionRequest,
    pages: &[TokenAccountsPage],
    observed_at_unix_ms: i64,
) -> Result<TokenHolderDistribution, ProviderError> {
    if observed_at_unix_ms < 0 {
        return Err(invalid_response(
            "holder distribution observation timestamp must be non-negative",
        ));
    }
    if pages.is_empty() {
        return Err(invalid_response(
            "holder distribution requires at least one provider page",
        ));
    }
    if pages.len() > request.max_pages {
        return Err(invalid_response(format!(
            "holder distribution received {} pages above max {}",
            pages.len(),
            request.max_pages
        )));
    }

    let expected_slot = pages[0].last_indexed_slot;
    let expected_total = pages[0].total;
    let mut accounts_by_address: BTreeMap<String, TokenAccountBalanceRow> = BTreeMap::new();

    for page in pages {
        if page.last_indexed_slot != expected_slot {
            return Err(invalid_response(
                "holder distribution pages disagree on last indexed slot",
            ));
        }
        if page.total != expected_total {
            return Err(invalid_response(
                "holder distribution pages disagree on reported total",
            ));
        }
        if page.limit != request.page_size {
            return Err(invalid_response(format!(
                "holder distribution page limit {} did not match requested {}",
                page.limit, request.page_size
            )));
        }
        if page.accounts.len() > page.limit {
            return Err(invalid_response(
                "holder distribution page exceeded its reported limit",
            ));
        }

        for account in &page.accounts {
            if account.mint != request.mint {
                return Err(invalid_response(
                    "holder distribution account mint changed after parsing",
                ));
            }
            match accounts_by_address.get(&account.address) {
                Some(existing) if existing == account => continue,
                Some(_) => {
                    return Err(invalid_response(format!(
                        "holder distribution token account {} changed across pages",
                        account.address
                    )))
                }
                None => {
                    accounts_by_address.insert(account.address.clone(), account.clone());
                }
            }
        }
    }

    let accounts_scanned = accounts_by_address.len();
    let accounts_scanned_u64 = u64::try_from(accounts_scanned).map_err(|_| {
        invalid_response("holder distribution account count exceeds u64")
    })?;
    if accounts_scanned_u64 > expected_total {
        return Err(invalid_response(format!(
            "holder distribution scanned {accounts_scanned_u64} unique accounts above reported total {expected_total}"
        )));
    }

    let complete = accounts_scanned_u64 == expected_total;
    let mut owner_balances: BTreeMap<String, u64> = BTreeMap::new();
    let mut total_balance_raw = 0_u64;

    for account in accounts_by_address.values() {
        total_balance_raw = total_balance_raw.checked_add(account.amount_raw).ok_or_else(|| {
            invalid_response("holder distribution total raw balance overflowed u64")
        })?;
        let owner_balance = owner_balances.entry(account.owner.clone()).or_default();
        *owner_balance = owner_balance.checked_add(account.amount_raw).ok_or_else(|| {
            invalid_response(format!(
                "holder distribution raw balance overflowed u64 for owner {}",
                account.owner
            ))
        })?;
    }

    let mut largest_owner: Option<String> = None;
    let mut largest_owner_balance_raw: Option<u64> = None;
    for (owner, balance) in &owner_balances {
        if largest_owner_balance_raw.is_none_or(|current| *balance > current) {
            largest_owner = Some(owner.clone());
            largest_owner_balance_raw = Some(*balance);
        }
    }

    let top_holder_concentration_pct = if complete && total_balance_raw > 0 {
        let largest = largest_owner_balance_raw.ok_or_else(|| {
            invalid_response("positive complete holder distribution had no largest owner")
        })?;
        let percentage = (largest as f64 / total_balance_raw as f64) * 100.0;
        if !percentage.is_finite() || !(0.0..=100.0).contains(&percentage) {
            return Err(invalid_response(
                "holder distribution concentration was outside finite [0, 100]",
            ));
        }
        Some(percentage)
    } else {
        None
    };

    Ok(TokenHolderDistribution {
        provider: ProviderId::Helius,
        mint: request.mint.clone(),
        last_indexed_slot: expected_slot,
        observed_at_unix_ms,
        reported_total_accounts: expected_total,
        accounts_scanned,
        unique_owners: owner_balances.len(),
        pages_scanned: pages.len(),
        complete,
        total_balance_raw,
        largest_owner,
        largest_owner_balance_raw,
        top_holder_concentration_pct,
    })
}

#[derive(Clone)]
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

    /// Fetch a confirmed transaction as raw JSON for a protocol-specific
    /// verifier such as the Pump creation parser. The Helius API key never
    /// appears in returned transport errors.
    pub async fn transaction_json(&self, signature: &str) -> Result<String, ProviderError> {
        let payload = get_transaction_request(signature)?;
        self.post_rpc(&payload).await
    }

    async fn post_rpc(&self, payload: &Value) -> Result<String, ProviderError> {
        let response = self
            .client
            .post(helius_rpc_url(&self.api_key))
            .json(payload)
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

        Ok(body)
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

        let body = self.post_rpc(&payload).await?;
        parse_mint_account_response(&body, token_mint, unix_time_ms()?)
    }
}

#[async_trait]
impl DistributionDataProvider for HeliusProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn token_holder_distribution(
        &self,
        request: &TokenDistributionRequest,
    ) -> Result<TokenHolderDistribution, ProviderError> {
        let mut pages = Vec::with_capacity(request.max_pages);
        let mut seen_addresses = HashSet::new();

        for page_number in 1..=request.max_pages {
            let payload = get_token_accounts_request(request, page_number)?;
            let body = self.post_rpc(&payload).await?;
            let page = parse_token_accounts_page(&body, &request.mint)?;
            for account in &page.accounts {
                seen_addresses.insert(account.address.clone());
            }
            let reported_total = page.total;
            pages.push(page);
            let seen_count = u64::try_from(seen_addresses.len()).map_err(|_| {
                invalid_response("holder distribution seen-account count exceeds u64")
            })?;
            if seen_count >= reported_total {
                break;
            }
        }

        aggregate_token_account_pages(request, &pages, unix_time_ms()?)
    }
}

#[async_trait]
impl TransactionProvider for HeliusProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn transaction_json(&self, signature: &str) -> Result<String, ProviderError> {
        HeliusProvider::transaction_json(self, signature).await
    }
}

fn rpc_error(error: RpcError) -> ProviderError {
    let kind = match error.code {
        -32602..=-32600 => ProviderErrorKind::InvalidRequest,
        _ => ProviderErrorKind::Unavailable,
    };
    ProviderError::new(
        ProviderId::Helius,
        kind,
        format!("Solana JSON-RPC error {}: {}", error.code, error.message),
    )
}

fn invalid_response(message: impl Into<String>) -> ProviderError {
    ProviderError::new(
        ProviderId::Helius,
        ProviderErrorKind::InvalidResponse,
        message,
    )
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
        invalid_response(format!("system clock before Unix epoch: {error}"))
    })?;
    i64::try_from(elapsed.as_millis()).map_err(|_| {
        invalid_response("system clock exceeds i64 milliseconds")
    })
}
