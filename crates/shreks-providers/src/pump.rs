//! Direct Pump.fun lifecycle discovery from standard Solana logs and transactions.
//!
//! This module deliberately separates cheap websocket signals from verified
//! transaction decoding. Logs only identify signatures worth fetching; only
//! pinned Pump-program instructions are allowed to become normalized evidence.

use std::{fmt, time::Duration};

use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use shreks_core::{DiscoveredToken, ProviderId, VenueId};
use tokio::{
    net::TcpStream,
    time::{sleep, timeout},
};
use tokio_tungstenite::{
    connect_async, tungstenite::Message, MaybeTlsStream, WebSocketStream,
};

use crate::{helius::helius_ws_url, ProviderError, ProviderErrorKind};

pub const PUMP_PROGRAM_ID: &str = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P";
pub const PUMP_AMM_PROGRAM_ID: &str = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA";
pub const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";

pub const PUMP_CREATE_DISCRIMINATOR: [u8; 8] = [24, 30, 200, 40, 5, 28, 7, 119];
pub const PUMP_CREATE_V2_DISCRIMINATOR: [u8; 8] = [214, 144, 76, 236, 95, 139, 49, 180];
pub const PUMP_MIGRATE_DISCRIMINATOR: [u8; 8] = [155, 234, 231, 146, 236, 158, 162, 30];
pub const PUMP_MIGRATE_V2_DISCRIMINATOR: [u8; 8] = [187, 203, 18, 31, 206, 237, 254, 41];

const DEFAULT_RECONNECT_BASE: Duration = Duration::from_secs(1);
const DEFAULT_RECONNECT_MAX: Duration = Duration::from_secs(30);
const DEFAULT_HEARTBEAT_INTERVAL: Duration = Duration::from_secs(60);
const SUBSCRIPTION_ACK_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpCreationSignal {
    pub signature: String,
    pub slot: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpMigrationSignal {
    pub signature: String,
    pub slot: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PumpLifecycleSignal {
    Creation(PumpCreationSignal),
    Migration(PumpMigrationSignal),
}

/// Result of verifying a cheap Pump websocket launch signal against the
/// confirmed transaction body.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PumpCreationVerification {
    Pending,
    Verified(DiscoveredToken),
    Rejected(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpMigrationEvidence {
    pub mint: String,
    pub quote_mint: String,
    pub pool_address: String,
    pub occurred_at_unix_ms: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PumpMigrationVerification {
    Pending,
    Verified(Vec<PumpMigrationEvidence>),
    Rejected(String),
}

/// Runtime configuration for the standard Pump log stream.
/// The endpoint is intentionally omitted from `Debug` because a Helius endpoint
/// embeds its API key in the query string.
#[derive(Clone)]
pub struct PumpLogStreamConfig {
    endpoint: String,
    reconnect_base: Duration,
    reconnect_max: Duration,
    heartbeat_interval: Duration,
}

impl PumpLogStreamConfig {
    pub fn helius(api_key: &str) -> Result<Self, ProviderError> {
        if api_key.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::InvalidRequest,
                "Helius API key must not be empty",
            ));
        }
        Self::for_endpoint(helius_ws_url(api_key))
    }

    pub fn for_endpoint(endpoint: impl Into<String>) -> Result<Self, ProviderError> {
        let endpoint = endpoint.into();
        let trimmed = endpoint.trim();
        if trimmed.is_empty()
            || !(trimmed.starts_with("ws://") || trimmed.starts_with("wss://"))
        {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::InvalidRequest,
                "Pump websocket endpoint must use ws:// or wss://",
            ));
        }

        Ok(Self {
            endpoint,
            reconnect_base: DEFAULT_RECONNECT_BASE,
            reconnect_max: DEFAULT_RECONNECT_MAX,
            heartbeat_interval: DEFAULT_HEARTBEAT_INTERVAL,
        })
    }

    pub fn with_reconnect_bounds(mut self, base: Duration, max: Duration) -> Self {
        self.reconnect_base = base;
        self.reconnect_max = max;
        self
    }

    pub fn with_heartbeat_interval(mut self, interval: Duration) -> Self {
        self.heartbeat_interval = interval;
        self
    }

    fn reconnect_delay(&self, attempt: u32) -> Duration {
        let multiplier = 1_u32.checked_shl(attempt.min(31)).unwrap_or(u32::MAX);
        self.reconnect_base
            .saturating_mul(multiplier)
            .min(self.reconnect_max)
    }
}

impl fmt::Debug for PumpLogStreamConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("PumpLogStreamConfig")
            .field("endpoint", &"<redacted>")
            .field("reconnect_base", &self.reconnect_base)
            .field("reconnect_max", &self.reconnect_max)
            .field("heartbeat_interval", &self.heartbeat_interval)
            .finish()
    }
}

type PumpSocket = WebSocketStream<MaybeTlsStream<TcpStream>>;

/// Restarting standard-WebSocket Pump log client using one Pump subscription.
pub struct PumpLogStream {
    config: PumpLogStreamConfig,
    socket: Option<PumpSocket>,
    reconnect_attempt: u32,
}

impl PumpLogStream {
    pub fn new(config: PumpLogStreamConfig) -> Self {
        Self {
            config,
            socket: None,
            reconnect_attempt: 0,
        }
    }

    /// Compatibility API for creation-only callers. Migration signals are
    /// ignored here and remain available to lifecycle-aware callers through
    /// `next_lifecycle_signal` once Task 3 moves the observer to that API.
    pub async fn next_signal(&mut self) -> Result<PumpCreationSignal, ProviderError> {
        loop {
            match self.next_lifecycle_signal().await? {
                PumpLifecycleSignal::Creation(signal) => return Ok(signal),
                PumpLifecycleSignal::Migration(_) => {}
            }
        }
    }

    /// Return the next successful Pump Create/CreateV2 or Migrate/MigrateV2
    /// signal from the same standard Solana websocket subscription.
    pub async fn next_lifecycle_signal(&mut self) -> Result<PumpLifecycleSignal, ProviderError> {
        loop {
            self.ensure_connected().await?;
            let heartbeat_interval = self.config.heartbeat_interval;

            let next_frame = {
                let socket = self
                    .socket
                    .as_mut()
                    .expect("ensure_connected establishes a websocket");
                timeout(heartbeat_interval, socket.next()).await
            };

            match next_frame {
                Err(_) => {
                    let sent = self
                        .socket
                        .as_mut()
                        .expect("connected socket exists for heartbeat")
                        .send(Message::Ping(Vec::new().into()))
                        .await;
                    if sent.is_err() {
                        self.disconnect_and_backoff().await;
                    }
                }
                Ok(Some(Ok(Message::Text(text)))) => {
                    if let Some(signal) =
                        parse_pump_lifecycle_log_notification(&text.to_string())?
                    {
                        return Ok(signal);
                    }
                }
                Ok(Some(Ok(Message::Ping(payload)))) => {
                    let sent = self
                        .socket
                        .as_mut()
                        .expect("connected socket exists for pong")
                        .send(Message::Pong(payload))
                        .await;
                    if sent.is_err() {
                        self.disconnect_and_backoff().await;
                    }
                }
                Ok(Some(Ok(Message::Pong(_))))
                | Ok(Some(Ok(Message::Binary(_))))
                | Ok(Some(Ok(Message::Frame(_)))) => {}
                Ok(Some(Ok(Message::Close(_)))) | Ok(Some(Err(_))) | Ok(None) => {
                    self.disconnect_and_backoff().await;
                }
            }
        }
    }

    async fn ensure_connected(&mut self) -> Result<(), ProviderError> {
        while self.socket.is_none() {
            match self.connect_once().await {
                Ok(socket) => {
                    self.socket = Some(socket);
                    self.reconnect_attempt = 0;
                }
                Err(error) if error.is_retryable() => {
                    self.backoff().await;
                }
                Err(error) => return Err(error),
            }
        }
        Ok(())
    }

    async fn connect_once(&self) -> Result<PumpSocket, ProviderError> {
        let (mut socket, _) = connect_async(self.config.endpoint.as_str())
            .await
            .map_err(|_| websocket_unavailable("Helius standard websocket connection failed"))?;

        socket
            .send(Message::Text(
                pump_logs_subscribe_request().to_string().into(),
            ))
            .await
            .map_err(|_| websocket_unavailable("Helius Pump log subscription send failed"))?;

        loop {
            let frame = timeout(SUBSCRIPTION_ACK_TIMEOUT, socket.next())
                .await
                .map_err(|_| websocket_unavailable("Helius Pump log subscription timed out"))?;

            match frame {
                Some(Ok(Message::Text(text))) => {
                    if parse_pump_subscription_ack(&text.to_string())?.is_some() {
                        return Ok(socket);
                    }
                }
                Some(Ok(Message::Ping(payload))) => {
                    socket
                        .send(Message::Pong(payload))
                        .await
                        .map_err(|_| websocket_unavailable("Helius Pump websocket pong failed"))?;
                }
                Some(Ok(Message::Pong(_)))
                | Some(Ok(Message::Binary(_)))
                | Some(Ok(Message::Frame(_))) => {}
                Some(Ok(Message::Close(_))) | Some(Err(_)) | None => {
                    return Err(websocket_unavailable(
                        "Helius Pump websocket closed before subscription acknowledgement",
                    ));
                }
            }
        }
    }

    async fn disconnect_and_backoff(&mut self) {
        self.socket = None;
        self.backoff().await;
    }

    async fn backoff(&mut self) {
        let delay = self.config.reconnect_delay(self.reconnect_attempt);
        self.reconnect_attempt = self.reconnect_attempt.saturating_add(1);
        sleep(delay).await;
    }
}

pub fn pump_logs_subscribe_request() -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "logsSubscribe",
        "params": [
            { "mentions": [PUMP_PROGRAM_ID] },
            { "commitment": "confirmed" }
        ]
    })
}

pub fn parse_pump_subscription_ack(body: &str) -> Result<Option<u64>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!("invalid Pump subscription JSON: {error}"))
    })?;

    if value.get("id").and_then(Value::as_u64) != Some(1) {
        return Ok(None);
    }

    if let Some(error) = value.get("error").filter(|error| !error.is_null()) {
        let code = error.get("code").and_then(Value::as_i64);
        let message = error
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("subscription rejected");
        let kind = match code {
            Some(-32602..=-32600) => ProviderErrorKind::InvalidRequest,
            _ => ProviderErrorKind::InvalidResponse,
        };
        return Err(ProviderError::new(
            ProviderId::Helius,
            kind,
            format!("Pump log subscription rejected: {message}"),
        ));
    }

    let subscription_id = value
        .get("result")
        .and_then(Value::as_u64)
        .ok_or_else(|| invalid_response("Pump subscription acknowledgement missing result"))?;
    Ok(Some(subscription_id))
}

pub fn pump_reconnect_delay(attempt: u32) -> Duration {
    let exponent = attempt.min(5);
    let seconds = (1_u64 << exponent).min(30);
    Duration::from_secs(seconds)
}

/// Parse one standard Solana Pump `logsNotification` and classify only exact
/// instruction log tails. Substring matching is intentionally forbidden so
/// `MigrateBondingCurveCreator` can never masquerade as graduation.
pub fn parse_pump_lifecycle_log_notification(
    body: &str,
) -> Result<Option<PumpLifecycleSignal>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!("invalid Pump log websocket JSON: {error}"))
    })?;

    if value.get("method").and_then(Value::as_str) != Some("logsNotification") {
        return Ok(None);
    }

    let result = value
        .pointer("/params/result")
        .ok_or_else(|| invalid_response("Pump logsNotification missing params.result"))?;
    let slot = result
        .pointer("/context/slot")
        .and_then(Value::as_u64)
        .ok_or_else(|| invalid_response("Pump logsNotification missing context.slot"))?;
    let notification = result
        .get("value")
        .ok_or_else(|| invalid_response("Pump logsNotification missing value"))?;

    if !notification.get("err").is_some_and(Value::is_null) {
        return Ok(None);
    }

    let signature = notification
        .get("signature")
        .and_then(Value::as_str)
        .filter(|signature| !signature.trim().is_empty())
        .ok_or_else(|| invalid_response("Pump logsNotification missing signature"))?;
    let logs = notification
        .get("logs")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid_response("Pump logsNotification missing logs array"))?;

    let mut creation = false;
    let mut migration = false;
    for log in logs.iter().filter_map(Value::as_str) {
        match log.trim() {
            "Program log: Instruction: Create" | "Program log: Instruction: CreateV2" => {
                creation = true;
            }
            "Program log: Instruction: Migrate" | "Program log: Instruction: MigrateV2" => {
                migration = true;
            }
            _ => {}
        }
    }

    if migration {
        return Ok(Some(PumpLifecycleSignal::Migration(PumpMigrationSignal {
            signature: signature.to_owned(),
            slot,
        })));
    }
    if creation {
        return Ok(Some(PumpLifecycleSignal::Creation(PumpCreationSignal {
            signature: signature.to_owned(),
            slot,
        })));
    }
    Ok(None)
}

/// Compatibility parser returning only creation signals.
pub fn parse_pump_log_notification(
    body: &str,
) -> Result<Option<PumpCreationSignal>, ProviderError> {
    match parse_pump_lifecycle_log_notification(body)? {
        Some(PumpLifecycleSignal::Creation(signal)) => Ok(Some(signal)),
        Some(PumpLifecycleSignal::Migration(_)) | None => Ok(None),
    }
}

pub fn classify_pump_creation_transaction(
    body: &str,
    signature: &str,
    discovered_at_unix_ms: i64,
) -> Result<PumpCreationVerification, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!(
            "invalid Pump transaction JSON for {signature}: {error}"
        ))
    })?;

    if let Some(error) = value.get("error").filter(|error| !error.is_null()) {
        return Err(invalid_response(format!(
            "Solana RPC returned an error for Pump signature {signature}: {error}"
        )));
    }

    let result = value.get("result").ok_or_else(|| {
        invalid_response(format!(
            "Solana RPC response missing result for Pump signature {signature}"
        ))
    })?;

    if result.is_null() {
        return Ok(PumpCreationVerification::Pending);
    }

    if result
        .pointer("/meta/err")
        .is_some_and(|error| !error.is_null())
    {
        return Ok(PumpCreationVerification::Rejected(format!(
            "Pump signature {signature} failed onchain"
        )));
    }

    if let Some(mint) = find_creation_mint(result) {
        return Ok(PumpCreationVerification::Verified(DiscoveredToken {
            mint,
            pair_address: None,
            dex_id: Some("pumpfun".to_owned()),
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms,
            source: ProviderId::Helius,
        }));
    }

    Ok(PumpCreationVerification::Rejected(format!(
        "Pump signature {signature} contained no verified Create/CreateV2 instruction"
    )))
}

pub fn parse_pump_creation_transaction(
    body: &str,
    signature: &str,
    discovered_at_unix_ms: i64,
) -> Result<DiscoveredToken, ProviderError> {
    match classify_pump_creation_transaction(body, signature, discovered_at_unix_ms)? {
        PumpCreationVerification::Pending => Err(invalid_response(format!(
            "Solana RPC returned no transaction for Pump signature {signature}"
        ))),
        PumpCreationVerification::Verified(candidate) => Ok(candidate),
        PumpCreationVerification::Rejected(reason) => Err(invalid_response(reason)),
    }
}

/// Classify a fetched confirmed transaction as official Pump graduation
/// evidence using pinned Pump IDL discriminators and account positions.
pub fn classify_pump_migration_transaction(
    body: &str,
    signature: &str,
) -> Result<PumpMigrationVerification, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!(
            "invalid Pump migration transaction JSON for {signature}: {error}"
        ))
    })?;

    if let Some(error) = value.get("error").filter(|error| !error.is_null()) {
        return Err(invalid_response(format!(
            "Solana RPC returned an error for Pump migration signature {signature}: {error}"
        )));
    }

    let result = value.get("result").ok_or_else(|| {
        invalid_response(format!(
            "Solana RPC response missing result for Pump migration signature {signature}"
        ))
    })?;
    if result.is_null() {
        return Ok(PumpMigrationVerification::Pending);
    }
    if result
        .pointer("/meta/err")
        .is_some_and(|error| !error.is_null())
    {
        return Ok(PumpMigrationVerification::Rejected(format!(
            "Pump migration signature {signature} failed onchain"
        )));
    }

    let occurred_at_unix_ms = parse_block_time_ms(result, signature)?;
    let evidence = find_migration_evidence(result, occurred_at_unix_ms);
    if evidence.is_empty() {
        return Ok(PumpMigrationVerification::Rejected(format!(
            "Pump migration signature {signature} contained no verified Migrate/MigrateV2 instruction"
        )));
    }
    Ok(PumpMigrationVerification::Verified(evidence))
}

fn parse_block_time_ms(result: &Value, signature: &str) -> Result<Option<i64>, ProviderError> {
    let Some(value) = result.get("blockTime") else {
        return Ok(None);
    };
    if value.is_null() {
        return Ok(None);
    }
    let seconds = value.as_i64().ok_or_else(|| {
        invalid_response(format!(
            "Pump migration signature {signature} has invalid blockTime"
        ))
    })?;
    if seconds < 0 {
        return Err(invalid_response(format!(
            "Pump migration signature {signature} has negative blockTime"
        )));
    }
    seconds.checked_mul(1_000).map(Some).ok_or_else(|| {
        invalid_response(format!(
            "Pump migration signature {signature} blockTime milliseconds overflow"
        ))
    })
}

fn find_migration_evidence(
    result: &Value,
    occurred_at_unix_ms: Option<i64>,
) -> Vec<PumpMigrationEvidence> {
    let mut evidence = Vec::new();

    if let Some(instructions) = result
        .pointer("/transaction/message/instructions")
        .and_then(Value::as_array)
    {
        collect_migration_evidence(instructions, occurred_at_unix_ms, &mut evidence);
    }

    if let Some(inner_groups) = result
        .pointer("/meta/innerInstructions")
        .and_then(Value::as_array)
    {
        for group in inner_groups {
            if let Some(instructions) = group.get("instructions").and_then(Value::as_array) {
                collect_migration_evidence(instructions, occurred_at_unix_ms, &mut evidence);
            }
        }
    }

    evidence.sort_by(|left, right| {
        (
            left.mint.as_str(),
            left.quote_mint.as_str(),
            left.pool_address.as_str(),
            left.occurred_at_unix_ms,
        )
            .cmp(&(
                right.mint.as_str(),
                right.quote_mint.as_str(),
                right.pool_address.as_str(),
                right.occurred_at_unix_ms,
            ))
    });
    evidence.dedup();
    evidence
}

fn collect_migration_evidence(
    instructions: &[Value],
    occurred_at_unix_ms: Option<i64>,
    output: &mut Vec<PumpMigrationEvidence>,
) {
    for instruction in instructions {
        if instruction.get("programId").and_then(Value::as_str) != Some(PUMP_PROGRAM_ID) {
            continue;
        }
        let Some(data) = instruction.get("data").and_then(Value::as_str) else {
            continue;
        };
        let Ok(decoded) = bs58::decode(data).into_vec() else {
            continue;
        };
        let Some(discriminator) = decoded.get(..8) else {
            continue;
        };
        let Some(accounts) = instruction.get("accounts").and_then(Value::as_array) else {
            continue;
        };

        let decoded = if discriminator == PUMP_MIGRATE_DISCRIMINATOR {
            decode_legacy_migration(accounts, occurred_at_unix_ms)
        } else if discriminator == PUMP_MIGRATE_V2_DISCRIMINATOR {
            decode_v2_migration(accounts, occurred_at_unix_ms)
        } else {
            None
        };
        if let Some(evidence) = decoded {
            output.push(evidence);
        }
    }
}

fn decode_legacy_migration(
    accounts: &[Value],
    occurred_at_unix_ms: Option<i64>,
) -> Option<PumpMigrationEvidence> {
    if accounts.len() < 15 || account(accounts, 8)? != PUMP_AMM_PROGRAM_ID {
        return None;
    }
    if account(accounts, 14)? != WRAPPED_SOL_MINT {
        return None;
    }
    Some(PumpMigrationEvidence {
        mint: nonempty_account(accounts, 2)?.to_owned(),
        quote_mint: WRAPPED_SOL_MINT.to_owned(),
        pool_address: nonempty_account(accounts, 9)?.to_owned(),
        occurred_at_unix_ms,
    })
}

fn decode_v2_migration(
    accounts: &[Value],
    occurred_at_unix_ms: Option<i64>,
) -> Option<PumpMigrationEvidence> {
    if accounts.len() < 11 || account(accounts, 9)? != PUMP_AMM_PROGRAM_ID {
        return None;
    }
    Some(PumpMigrationEvidence {
        mint: nonempty_account(accounts, 2)?.to_owned(),
        quote_mint: nonempty_account(accounts, 3)?.to_owned(),
        pool_address: nonempty_account(accounts, 10)?.to_owned(),
        occurred_at_unix_ms,
    })
}

fn account(accounts: &[Value], index: usize) -> Option<&str> {
    accounts.get(index)?.as_str()
}

fn nonempty_account(accounts: &[Value], index: usize) -> Option<&str> {
    account(accounts, index).filter(|value| !value.trim().is_empty())
}

fn find_creation_mint(result: &Value) -> Option<String> {
    if let Some(instructions) = result
        .pointer("/transaction/message/instructions")
        .and_then(Value::as_array)
    {
        if let Some(mint) = find_creation_mint_in_instructions(instructions) {
            return Some(mint);
        }
    }

    let inner_groups = result
        .pointer("/meta/innerInstructions")
        .and_then(Value::as_array)?;
    for group in inner_groups {
        let Some(instructions) = group.get("instructions").and_then(Value::as_array) else {
            continue;
        };
        if let Some(mint) = find_creation_mint_in_instructions(instructions) {
            return Some(mint);
        }
    }

    None
}

fn find_creation_mint_in_instructions(instructions: &[Value]) -> Option<String> {
    for instruction in instructions {
        if instruction.get("programId").and_then(Value::as_str) != Some(PUMP_PROGRAM_ID) {
            continue;
        }

        let Some(data) = instruction.get("data").and_then(Value::as_str) else {
            continue;
        };
        let Ok(decoded) = bs58::decode(data).into_vec() else {
            continue;
        };
        let Some(discriminator) = decoded.get(..8) else {
            continue;
        };
        if discriminator != PUMP_CREATE_DISCRIMINATOR
            && discriminator != PUMP_CREATE_V2_DISCRIMINATOR
        {
            continue;
        }

        let Some(mint) = instruction
            .get("accounts")
            .and_then(Value::as_array)
            .and_then(|accounts| accounts.first())
            .and_then(Value::as_str)
            .filter(|mint| !mint.trim().is_empty())
        else {
            continue;
        };

        return Some(mint.to_owned());
    }

    None
}

fn websocket_unavailable(message: &'static str) -> ProviderError {
    ProviderError::new(
        ProviderId::Helius,
        ProviderErrorKind::Unavailable,
        message,
    )
}

fn invalid_response(message: impl Into<String>) -> ProviderError {
    ProviderError::new(
        ProviderId::Helius,
        ProviderErrorKind::InvalidResponse,
        message,
    )
}
