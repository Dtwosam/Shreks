use std::{fmt, time::Duration};

use async_trait::async_trait;
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use shreks_core::ProviderId;
use tokio::{
    net::TcpStream,
    sync::mpsc,
    time::{sleep, timeout},
};
use tokio_tungstenite::{
    connect_async, tungstenite::Message, MaybeTlsStream, WebSocketStream,
};

use crate::{
    helius::helius_ws_url,
    pump::{
        parse_pump_lifecycle_log_notification, PumpLifecycleSignal, PUMP_AMM_PROGRAM_ID,
        PUMP_PROGRAM_ID,
    },
    pump_swap_trade::{parse_pump_swap_trade_logs, PumpSwapTradeEvidence},
    pump_trade::{
        classify_pump_trade_transaction, PumpTradeEvidence, PumpTradeVerification,
        PUMP_BUY_DISCRIMINATOR, PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR,
        PUMP_BUY_V2_DISCRIMINATOR, PUMP_SELL_DISCRIMINATOR, PUMP_SELL_V2_DISCRIMINATOR,
    },
    ProviderError, ProviderErrorKind,
};

const DEFAULT_RECONNECT_BASE: Duration = Duration::from_secs(1);
const DEFAULT_RECONNECT_MAX: Duration = Duration::from_secs(30);
const DEFAULT_HEARTBEAT_INTERVAL: Duration = Duration::from_secs(60);
const DEFAULT_MAX_CONNECT_ATTEMPTS: u32 = 5;
const SUBSCRIPTION_ACK_TIMEOUT: Duration = Duration::from_secs(10);
const PUMP_SUBSCRIPTION_REQUEST_ID: u64 = 1;
const PUMPSWAP_SUBSCRIPTION_REQUEST_ID: u64 = 2;
const ALCHEMY_MAINNET_WS_BASE: &str = "wss://solana-mainnet.g.alchemy.com/v2/";
const DEFAULT_SOLANA_SIGNATURE: &str =
    "1111111111111111111111111111111111111111111111111111111111111111";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpRealtimeNotification {
    pub provider: ProviderId,
    pub signature: String,
    pub slot: u64,
    pub lifecycle: Option<PumpLifecycleSignal>,
    pub trades: Vec<PumpTradeEvidence>,
    pub pump_swap_trades: Vec<PumpSwapTradeEvidence>,
}

/// Runtime configuration for one standard-Solana Pump realtime stream.
/// The endpoint is intentionally redacted because provider websocket URLs may
/// embed API keys.
#[derive(Clone)]
pub struct PumpRealtimeLogStreamConfig {
    provider: ProviderId,
    endpoint: String,
    reconnect_base: Duration,
    reconnect_max: Duration,
    heartbeat_interval: Duration,
    max_connect_attempts: u32,
}

impl PumpRealtimeLogStreamConfig {
    pub fn helius(api_key: &str) -> Result<Self, ProviderError> {
        if api_key.trim().is_empty() {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::InvalidRequest,
                "Helius API key must not be empty",
            ));
        }
        Self::for_provider_endpoint(ProviderId::Helius, helius_ws_url(api_key))
    }

    pub fn alchemy(api_key: &str) -> Result<Self, ProviderError> {
        let api_key = api_key.trim();
        if api_key.is_empty() {
            return Err(ProviderError::new(
                ProviderId::Alchemy,
                ProviderErrorKind::InvalidRequest,
                "Alchemy API key must not be empty",
            ));
        }
        Self::for_provider_endpoint(
            ProviderId::Alchemy,
            format!("{ALCHEMY_MAINNET_WS_BASE}{api_key}"),
        )
    }

    pub fn chainstack(endpoint: &str) -> Result<Self, ProviderError> {
        let endpoint = endpoint.trim();
        if endpoint.is_empty() {
            return Err(ProviderError::new(
                ProviderId::Chainstack,
                ProviderErrorKind::InvalidRequest,
                "Chainstack Solana websocket endpoint must not be empty",
            ));
        }
        Self::for_provider_endpoint(ProviderId::Chainstack, endpoint.to_owned())
    }

    /// Backward-compatible local/test constructor. Historical endpoint-only
    /// callers represented the Helius lane, so Helius remains the default.
    pub fn for_endpoint(endpoint: impl Into<String>) -> Result<Self, ProviderError> {
        Self::for_provider_endpoint(ProviderId::Helius, endpoint)
    }

    pub fn for_provider_endpoint(
        provider: ProviderId,
        endpoint: impl Into<String>,
    ) -> Result<Self, ProviderError> {
        if !is_realtime_provider(provider) {
            return Err(ProviderError::new(
                provider,
                ProviderErrorKind::InvalidRequest,
                "Pump realtime provider must be Helius, Chainstack, or Alchemy",
            ));
        }

        let endpoint = endpoint.into();
        let trimmed = endpoint.trim();
        if trimmed.is_empty()
            || !(trimmed.starts_with("ws://") || trimmed.starts_with("wss://"))
        {
            return Err(ProviderError::new(
                provider,
                ProviderErrorKind::InvalidRequest,
                "Pump realtime websocket endpoint must use ws:// or wss://",
            ));
        }

        Ok(Self {
            provider,
            endpoint,
            reconnect_base: DEFAULT_RECONNECT_BASE,
            reconnect_max: DEFAULT_RECONNECT_MAX,
            heartbeat_interval: DEFAULT_HEARTBEAT_INTERVAL,
            max_connect_attempts: DEFAULT_MAX_CONNECT_ATTEMPTS,
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

    pub fn with_max_connect_attempts(mut self, attempts: u32) -> Self {
        self.max_connect_attempts = attempts.max(1);
        self
    }

    fn reconnect_delay(&self, attempt: u32) -> Duration {
        let multiplier = 1_u32.checked_shl(attempt.min(31)).unwrap_or(u32::MAX);
        self.reconnect_base
            .saturating_mul(multiplier)
            .min(self.reconnect_max)
    }
}

impl fmt::Debug for PumpRealtimeLogStreamConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("PumpRealtimeLogStreamConfig")
            .field("provider", &self.provider)
            .field("endpoint", &"<redacted>")
            .field("reconnect_base", &self.reconnect_base)
            .field("reconnect_max", &self.reconnect_max)
            .field("heartbeat_interval", &self.heartbeat_interval)
            .field("max_connect_attempts", &self.max_connect_attempts)
            .finish()
    }
}

type PumpRealtimeSocket = WebSocketStream<MaybeTlsStream<TcpStream>>;

/// One Pump websocket carrying both bonding-curve and PumpSwap subscriptions.
/// It emits lifecycle and trade economics from confirmed log notifications,
/// performs no SQLite writes, and performs no per-trade transaction RPC calls.
pub struct PumpRealtimeLogStream {
    config: PumpRealtimeLogStreamConfig,
    socket: Option<PumpRealtimeSocket>,
    reconnect_attempt: u32,
}

impl PumpRealtimeLogStream {
    pub fn new(config: PumpRealtimeLogStreamConfig) -> Self {
        Self {
            config,
            socket: None,
            reconnect_attempt: 0,
        }
    }

    pub async fn next_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError> {
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
                    if let Some(notification) = parse_pump_realtime_log_notification_for_provider(
                        &text.to_string(),
                        self.config.provider,
                    )? {
                        return Ok(notification);
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
                    self.reconnect_attempt = self.reconnect_attempt.saturating_add(1);
                    if self.reconnect_attempt >= self.config.max_connect_attempts {
                        return Err(error);
                    }
                    let delay = self
                        .config
                        .reconnect_delay(self.reconnect_attempt.saturating_sub(1));
                    sleep(delay).await;
                }
                Err(error) => return Err(error),
            }
        }
        Ok(())
    }

    async fn connect_once(&self) -> Result<PumpRealtimeSocket, ProviderError> {
        let provider = self.config.provider;
        let (mut socket, _) = connect_async(self.config.endpoint.as_str())
            .await
            .map_err(|_| {
                websocket_unavailable(
                    provider,
                    format!("{provider} Pump realtime websocket connection failed"),
                )
            })?;

        for (request_id, program_id, lane_name) in [
            (PUMP_SUBSCRIPTION_REQUEST_ID, PUMP_PROGRAM_ID, "Pump bonding-curve"),
            (
                PUMPSWAP_SUBSCRIPTION_REQUEST_ID,
                PUMP_AMM_PROGRAM_ID,
                "PumpSwap",
            ),
        ] {
            socket
                .send(Message::Text(
                    realtime_logs_subscribe_request(request_id, program_id)
                        .to_string()
                        .into(),
                ))
                .await
                .map_err(|_| {
                    websocket_unavailable(
                        provider,
                        format!("{provider} {lane_name} realtime subscription send failed"),
                    )
                })?;
            await_subscription_ack(&mut socket, request_id, lane_name, provider).await?;
        }

        Ok(socket)
    }

    async fn disconnect_and_backoff(&mut self) {
        self.socket = None;
        let delay = self.config.reconnect_delay(self.reconnect_attempt);
        self.reconnect_attempt = self.reconnect_attempt.saturating_add(1);
        sleep(delay).await;
    }
}

/// Ordered standard-Solana realtime sources. The currently working source is
/// sticky; retryable exhaustion rotates to the next configured provider. One
/// complete failed pass returns an error so the observer can fail closed.
pub struct PumpRealtimeFailoverStream {
    streams: Vec<PumpRealtimeLogStream>,
    active_index: usize,
}

impl PumpRealtimeFailoverStream {
    pub fn new(configs: Vec<PumpRealtimeLogStreamConfig>) -> Result<Self, ProviderError> {
        if configs.is_empty() {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::InvalidRequest,
                "Pump realtime failover requires at least one provider",
            ));
        }
        Ok(Self {
            streams: configs.into_iter().map(PumpRealtimeLogStream::new).collect(),
            active_index: 0,
        })
    }

    pub async fn next_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError> {
        let stream_count = self.streams.len();
        let start = self.active_index;
        let mut last_retryable_error = None;

        for offset in 0..stream_count {
            let index = (start + offset) % stream_count;
            match self.streams[index].next_realtime_notification().await {
                Ok(notification) => {
                    self.active_index = index;
                    return Ok(notification);
                }
                Err(error) if error.is_retryable() => {
                    self.active_index = (index + 1) % stream_count;
                    last_retryable_error = Some(error);
                }
                Err(error) => return Err(error),
            }
        }

        Err(last_retryable_error.expect("non-empty provider set produced a retryable error"))
    }
}

async fn await_subscription_ack(
    socket: &mut PumpRealtimeSocket,
    expected_request_id: u64,
    lane_name: &str,
    provider: ProviderId,
) -> Result<u64, ProviderError> {
    loop {
        let frame = timeout(SUBSCRIPTION_ACK_TIMEOUT, socket.next())
            .await
            .map_err(|_| {
                websocket_unavailable(
                    provider,
                    format!("{provider} {lane_name} realtime subscription timed out"),
                )
            })?;

        match frame {
            Some(Ok(Message::Text(text))) => {
                if let Some(subscription_id) = parse_realtime_subscription_ack(
                    &text.to_string(),
                    expected_request_id,
                    provider,
                )? {
                    return Ok(subscription_id);
                }
            }
            Some(Ok(Message::Ping(payload))) => {
                socket.send(Message::Pong(payload)).await.map_err(|_| {
                    websocket_unavailable(
                        provider,
                        format!("{provider} {lane_name} realtime pong failed"),
                    )
                })?;
            }
            Some(Ok(Message::Pong(_)))
            | Some(Ok(Message::Binary(_)))
            | Some(Ok(Message::Frame(_))) => {}
            Some(Ok(Message::Close(_))) | Some(Err(_)) | None => {
                return Err(websocket_unavailable(
                    provider,
                    format!(
                        "{provider} {lane_name} realtime websocket closed before subscription acknowledgement"
                    ),
                ));
            }
        }
    }
}

fn realtime_logs_subscribe_request(request_id: u64, program_id: &str) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "logsSubscribe",
        "params": [
            {"mentions": [program_id]},
            {"commitment": "confirmed"}
        ]
    })
}

fn parse_realtime_subscription_ack(
    body: &str,
    expected_request_id: u64,
    provider: ProviderId,
) -> Result<Option<u64>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(
            provider,
            format!("invalid Pump realtime subscription JSON: {error}"),
        )
    })?;
    if value.get("id").and_then(Value::as_u64) != Some(expected_request_id) {
        return Ok(None);
    }
    if let Some(error) = value.get("error").filter(|error| !error.is_null()) {
        return Err(invalid_response(
            provider,
            format!("Pump realtime subscription request {expected_request_id} failed: {error}"),
        ));
    }
    let subscription = value.get("result").and_then(Value::as_u64).ok_or_else(|| {
        invalid_response(
            provider,
            format!(
                "Pump realtime subscription acknowledgement {expected_request_id} missing numeric result"
            ),
        )
    })?;
    Ok(Some(subscription))
}

#[async_trait]
pub trait PumpRealtimeSignalSource: Send {
    async fn next_pump_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError>;
}

#[async_trait]
impl PumpRealtimeSignalSource for PumpRealtimeLogStream {
    async fn next_pump_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError> {
        self.next_realtime_notification().await
    }
}

#[async_trait]
impl PumpRealtimeSignalSource for PumpRealtimeFailoverStream {
    async fn next_pump_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError> {
        self.next_realtime_notification().await
    }
}

/// Forward Pump realtime envelopes into a bounded consumer channel. The
/// forwarding task is intentionally storage-free; backpressure comes from the
/// bounded channel and a closed consumer terminates cleanly.
pub async fn forward_pump_realtime_signals<S>(
    mut source: S,
    sender: mpsc::Sender<PumpRealtimeNotification>,
) -> Result<(), ProviderError>
where
    S: PumpRealtimeSignalSource,
{
    loop {
        let notification = source.next_pump_realtime_notification().await?;
        if sender.send(notification).await.is_err() {
            return Ok(());
        }
    }
}

/// Parse one confirmed standard-Solana Pump/PumpSwap `logsNotification` into
/// the complete direct evidence Shreks can obtain without an additional RPC
/// request. Historical direct parser callers are Helius fixtures; live streams
/// use the provider-aware internal parser.
pub fn parse_pump_realtime_log_notification(
    body: &str,
) -> Result<Option<PumpRealtimeNotification>, ProviderError> {
    parse_pump_realtime_log_notification_for_provider(body, ProviderId::Helius)
}

fn parse_pump_realtime_log_notification_for_provider(
    body: &str,
    provider: ProviderId,
) -> Result<Option<PumpRealtimeNotification>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(
            provider,
            format!("invalid Pump realtime websocket JSON: {error}"),
        )
    })?;

    if value.get("method").and_then(Value::as_str) != Some("logsNotification") {
        return Ok(None);
    }

    let result = value.pointer("/params/result").ok_or_else(|| {
        invalid_response(
            provider,
            "Pump realtime logsNotification missing params.result",
        )
    })?;
    let slot = result
        .pointer("/context/slot")
        .and_then(Value::as_u64)
        .ok_or_else(|| {
            invalid_response(
                provider,
                "Pump realtime logsNotification missing context.slot",
            )
        })?;
    let notification = result.get("value").ok_or_else(|| {
        invalid_response(provider, "Pump realtime logsNotification missing value")
    })?;

    if !notification.get("err").is_some_and(Value::is_null) {
        return Ok(None);
    }

    let signature = notification
        .get("signature")
        .and_then(Value::as_str)
        .filter(|signature| !signature.trim().is_empty())
        .ok_or_else(|| {
            invalid_response(
                provider,
                "Pump realtime logsNotification missing signature",
            )
        })?;
    if signature == DEFAULT_SOLANA_SIGNATURE {
        return Ok(None);
    }
    let logs = notification
        .get("logs")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            invalid_response(
                provider,
                "Pump realtime logsNotification missing logs array",
            )
        })?;

    let lifecycle = parse_pump_lifecycle_log_notification(body)
        .map_err(|error| reattribute_provider_error(error, provider))?;
    let trade_discriminators = pump_trade_instruction_discriminators(logs);
    let trades = if trade_discriminators.is_empty() {
        Vec::new()
    } else {
        decode_trade_evidence_from_notification_logs(
            signature,
            slot,
            logs,
            &trade_discriminators,
            provider,
        )?
    };
    let pump_swap_trades = parse_pump_swap_trade_logs(logs)
        .map_err(|error| reattribute_provider_error(error, provider))?;

    if lifecycle.is_none() && trades.is_empty() && pump_swap_trades.is_empty() {
        return Ok(None);
    }

    Ok(Some(PumpRealtimeNotification {
        provider,
        signature: signature.to_owned(),
        slot,
        lifecycle,
        trades,
        pump_swap_trades,
    }))
}

fn decode_trade_evidence_from_notification_logs(
    signature: &str,
    slot: u64,
    logs: &[Value],
    discriminators: &[[u8; 8]],
    provider: ProviderId,
) -> Result<Vec<PumpTradeEvidence>, ProviderError> {
    let instructions: Vec<Value> = discriminators
        .iter()
        .map(|discriminator| {
            json!({
                "accounts": [],
                "data": bs58::encode(discriminator).into_string(),
                "programId": PUMP_PROGRAM_ID
            })
        })
        .collect();

    let synthetic = json!({
        "jsonrpc": "2.0",
        "result": {
            "slot": slot,
            "meta": {
                "err": null,
                "logMessages": logs,
                "innerInstructions": []
            },
            "transaction": {
                "message": {
                    "instructions": instructions
                }
            }
        },
        "id": "shreks-pump-realtime"
    });

    match classify_pump_trade_transaction(&synthetic.to_string(), signature)
        .map_err(|error| reattribute_provider_error(error, provider))?
    {
        PumpTradeVerification::Verified(events) => Ok(events),
        PumpTradeVerification::Pending => Err(invalid_response(
            provider,
            format!("Pump realtime signature {signature} unexpectedly classified as pending"),
        )),
        PumpTradeVerification::Rejected(reason) => Err(invalid_response(
            provider,
            format!(
                "Pump realtime signature {signature} contained a trade instruction but no authoritative trade evidence: {reason}"
            ),
        )),
    }
}

fn pump_trade_instruction_discriminators(logs: &[Value]) -> Vec<[u8; 8]> {
    let mut stack: Vec<String> = Vec::new();
    let mut output = Vec::new();

    for log in logs.iter().filter_map(Value::as_str) {
        if let Some(program) = invocation_program(log) {
            stack.push(program.to_owned());
            continue;
        }
        if let Some(program) = terminated_program(log) {
            if stack.last().is_some_and(|active| active == program) {
                stack.pop();
            }
            continue;
        }
        if stack.last().map(String::as_str) != Some(PUMP_PROGRAM_ID) {
            continue;
        }

        let discriminator = match log.trim() {
            "Program log: Instruction: Buy" => Some(PUMP_BUY_DISCRIMINATOR),
            "Program log: Instruction: BuyExactSolIn" => {
                Some(PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR)
            }
            "Program log: Instruction: BuyV2" => Some(PUMP_BUY_V2_DISCRIMINATOR),
            "Program log: Instruction: Sell" => Some(PUMP_SELL_DISCRIMINATOR),
            "Program log: Instruction: SellV2" => Some(PUMP_SELL_V2_DISCRIMINATOR),
            _ => None,
        };
        if let Some(discriminator) = discriminator {
            output.push(discriminator);
        }
    }

    output
}

fn invocation_program(log: &str) -> Option<&str> {
    let rest = log.strip_prefix("Program ")?;
    rest.split_once(" invoke [").map(|(program, _)| program)
}

fn terminated_program(log: &str) -> Option<&str> {
    let rest = log.strip_prefix("Program ")?;
    if let Some(program) = rest.strip_suffix(" success") {
        return Some(program);
    }
    rest.split_once(" failed:").map(|(program, _)| program)
}

fn is_realtime_provider(provider: ProviderId) -> bool {
    matches!(
        provider,
        ProviderId::Helius | ProviderId::Chainstack | ProviderId::Alchemy
    )
}

fn websocket_unavailable(provider: ProviderId, message: impl Into<String>) -> ProviderError {
    ProviderError::new(provider, ProviderErrorKind::Unavailable, message)
}

fn invalid_response(provider: ProviderId, message: impl Into<String>) -> ProviderError {
    ProviderError::new(provider, ProviderErrorKind::InvalidResponse, message)
}

fn reattribute_provider_error(error: ProviderError, provider: ProviderId) -> ProviderError {
    let mut mapped = ProviderError::new(provider, error.kind, error.message);
    if let Some(retry_after_ms) = error.retry_after_ms {
        mapped = mapped.with_retry_after_ms(retry_after_ms);
    }
    mapped
}
