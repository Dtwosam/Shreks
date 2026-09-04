use std::{
    collections::{BTreeMap, VecDeque},
    fmt,
    time::Duration,
};

use futures_util::{SinkExt, StreamExt};
use serde_json::Value;
use shreks_core::ProviderId;
use tokio::{
    net::TcpStream,
    sync::watch,
    time::{sleep, timeout},
};
use tokio_tungstenite::{
    connect_async, tungstenite::Message, MaybeTlsStream, WebSocketStream,
};

use crate::{
    helius::helius_ws_url,
    pump::PUMP_PROGRAM_ID,
    pump_realtime::{parse_pump_realtime_log_notification, PumpRealtimeNotification},
    realtime_scope::{
        parse_pump_realtime_unsubscribe_ack, pump_realtime_initial_mentions,
        pump_realtime_logs_subscribe_request, pump_realtime_logs_unsubscribe_request,
        pump_realtime_subscription_changes, PumpRealtimeSubscriptionChange,
    },
    ProviderError, ProviderErrorKind,
};

const DEFAULT_RECONNECT_BASE: Duration = Duration::from_secs(1);
const DEFAULT_RECONNECT_MAX: Duration = Duration::from_secs(30);
const DEFAULT_HEARTBEAT_INTERVAL: Duration = Duration::from_secs(60);
const DEFAULT_MAX_CONNECT_ATTEMPTS: u32 = 5;
const SUBSCRIPTION_ACK_TIMEOUT: Duration = Duration::from_secs(10);
const ALCHEMY_MAINNET_WS_BASE: &str = "wss://solana-mainnet.g.alchemy.com/v2/";
const SOLANA_PUBLIC_MAINNET_WS_URL: &str = "wss://api.mainnet.solana.com";

type BoundedPumpRealtimeSocket = WebSocketStream<MaybeTlsStream<TcpStream>>;
type BoundedPumpRealtimeFrame = Option<Result<Message, tokio_tungstenite::tungstenite::Error>>;

enum BoundedPumpRealtimeWake {
    TargetsChanged(Result<(), watch::error::RecvError>),
    SocketFrame(Result<BoundedPumpRealtimeFrame, tokio::time::error::Elapsed>),
}

#[derive(Clone)]
pub struct BoundedPumpRealtimeLogStreamConfig {
    provider: ProviderId,
    endpoint: String,
    reconnect_base: Duration,
    reconnect_max: Duration,
    heartbeat_interval: Duration,
    max_connect_attempts: u32,
}

impl BoundedPumpRealtimeLogStreamConfig {
    pub fn helius(api_key: &str) -> Result<Self, ProviderError> {
        if api_key.trim().is_empty() {
            return Err(invalid_request(
                ProviderId::Helius,
                "Helius API key must not be empty",
            ));
        }
        Self::for_provider_endpoint(ProviderId::Helius, helius_ws_url(api_key))
    }

    pub fn chainstack(endpoint: &str) -> Result<Self, ProviderError> {
        Self::for_provider_endpoint(ProviderId::Chainstack, endpoint)
    }

    pub fn alchemy(api_key: &str) -> Result<Self, ProviderError> {
        let api_key = api_key.trim();
        if api_key.is_empty() {
            return Err(invalid_request(
                ProviderId::Alchemy,
                "Alchemy API key must not be empty",
            ));
        }
        Self::for_provider_endpoint(
            ProviderId::Alchemy,
            format!("{ALCHEMY_MAINNET_WS_BASE}{api_key}"),
        )
    }

    pub fn solana_public() -> Result<Self, ProviderError> {
        Self::for_provider_endpoint(
            ProviderId::SolanaPublic,
            SOLANA_PUBLIC_MAINNET_WS_URL,
        )
    }

    pub fn for_provider_endpoint(
        provider: ProviderId,
        endpoint: impl Into<String>,
    ) -> Result<Self, ProviderError> {
        if !matches!(
            provider,
            ProviderId::Helius
                | ProviderId::Chainstack
                | ProviderId::Alchemy
                | ProviderId::SolanaPublic
        ) {
            return Err(invalid_request(
                provider,
                "bounded Pump realtime provider must be Helius, Chainstack, Alchemy, or SolanaPublic",
            ));
        }
        let endpoint = endpoint.into();
        let trimmed = endpoint.trim();
        if trimmed.is_empty()
            || !(trimmed.starts_with("ws://") || trimmed.starts_with("wss://"))
        {
            return Err(invalid_request(
                provider,
                "bounded Pump realtime websocket endpoint must use ws:// or wss://",
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

impl fmt::Debug for BoundedPumpRealtimeLogStreamConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("BoundedPumpRealtimeLogStreamConfig")
            .field("provider", &self.provider)
            .field("endpoint", &"<redacted>")
            .field("reconnect_base", &self.reconnect_base)
            .field("reconnect_max", &self.reconnect_max)
            .field("heartbeat_interval", &self.heartbeat_interval)
            .field("max_connect_attempts", &self.max_connect_attempts)
            .finish()
    }
}

pub struct BoundedPumpRealtimeLogStream {
    config: BoundedPumpRealtimeLogStreamConfig,
    targets: watch::Receiver<Vec<String>>,
    socket: Option<BoundedPumpRealtimeSocket>,
    pool_subscriptions: BTreeMap<String, u64>,
    pending_notifications: VecDeque<PumpRealtimeNotification>,
    reconnect_attempt: u32,
    next_request_id: u64,
    awaiting_heartbeat_response: bool,
    connection_generation: u64,
}

impl BoundedPumpRealtimeLogStream {
    pub fn new(
        config: BoundedPumpRealtimeLogStreamConfig,
        targets: watch::Receiver<Vec<String>>,
    ) -> Result<Self, ProviderError> {
        pump_realtime_initial_mentions(&targets.borrow())?;
        Ok(Self {
            config,
            targets,
            socket: None,
            pool_subscriptions: BTreeMap::new(),
            pending_notifications: VecDeque::new(),
            reconnect_attempt: 0,
            next_request_id: 1,
            awaiting_heartbeat_response: false,
            connection_generation: 0,
        })
    }

    pub(crate) fn provider(&self) -> ProviderId {
        self.config.provider
    }

    pub(crate) fn connection_generation(&self) -> u64 {
        self.connection_generation
    }

    pub async fn next_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError> {
        loop {
            if let Some(notification) = self.pending_notifications.pop_front() {
                return Ok(notification);
            }
            self.ensure_connected().await?;
            let heartbeat_interval = self.config.heartbeat_interval;
            let wake = {
                let targets = &mut self.targets;
                let socket = self
                    .socket
                    .as_mut()
                    .expect("ensure_connected establishes a websocket");
                tokio::select! {
                    changed = targets.changed() => BoundedPumpRealtimeWake::TargetsChanged(changed),
                    frame = timeout(heartbeat_interval, socket.next()) => {
                        BoundedPumpRealtimeWake::SocketFrame(frame)
                    }
                }
            };

            match wake {
                BoundedPumpRealtimeWake::TargetsChanged(Ok(())) => {
                    if let Err(error) = self.reconcile_targets().await {
                        self.reset_connection();
                        return Err(error);
                    }
                }
                BoundedPumpRealtimeWake::TargetsChanged(Err(_)) => {
                    self.reset_connection();
                    return Err(unavailable(
                        self.config.provider,
                        "bounded realtime target publisher stopped",
                    ));
                }
                BoundedPumpRealtimeWake::SocketFrame(Err(_)) => {
                    if self.awaiting_heartbeat_response {
                        self.disconnect_and_backoff().await;
                        continue;
                    }
                    let sent = self
                        .socket
                        .as_mut()
                        .expect("connected socket exists for heartbeat")
                        .send(Message::Ping(Vec::new().into()))
                        .await;
                    if sent.is_err() {
                        self.disconnect_and_backoff().await;
                    } else {
                        self.awaiting_heartbeat_response = true;
                    }
                }
                BoundedPumpRealtimeWake::SocketFrame(Ok(Some(Ok(Message::Text(text))))) => {
                    self.awaiting_heartbeat_response = false;
                    if let Some(notification) = parse_notification_for_provider(
                        &text.to_string(),
                        self.config.provider,
                    )? {
                        return Ok(notification);
                    }
                }
                BoundedPumpRealtimeWake::SocketFrame(Ok(Some(Ok(Message::Ping(payload))))) => {
                    self.awaiting_heartbeat_response = false;
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
                BoundedPumpRealtimeWake::SocketFrame(Ok(Some(Ok(Message::Pong(_)))))
                | BoundedPumpRealtimeWake::SocketFrame(Ok(Some(Ok(Message::Binary(_)))))
                | BoundedPumpRealtimeWake::SocketFrame(Ok(Some(Ok(Message::Frame(_))))) => {
                    self.awaiting_heartbeat_response = false;
                }
                BoundedPumpRealtimeWake::SocketFrame(Ok(Some(Ok(Message::Close(_)))))
                | BoundedPumpRealtimeWake::SocketFrame(Ok(Some(Err(_))))
                | BoundedPumpRealtimeWake::SocketFrame(Ok(None)) => {
                    self.disconnect_and_backoff().await;
                }
            }
        }
    }

    async fn ensure_connected(&mut self) -> Result<(), ProviderError> {
        while self.socket.is_none() {
            match self.connect_once().await {
                Ok((socket, pool_subscriptions, pending_notifications, next_request_id)) => {
                    let connection_generation = self
                        .connection_generation
                        .checked_add(1)
                        .ok_or_else(|| {
                            invalid_response(
                                self.config.provider,
                                "bounded realtime connection generation overflow",
                            )
                        })?;
                    self.socket = Some(socket);
                    self.pool_subscriptions = pool_subscriptions;
                    self.pending_notifications.extend(pending_notifications);
                    self.reconnect_attempt = 0;
                    self.next_request_id = next_request_id;
                    self.awaiting_heartbeat_response = false;
                    self.connection_generation = connection_generation;
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

    async fn connect_once(
        &self,
    ) -> Result<
        (
            BoundedPumpRealtimeSocket,
            BTreeMap<String, u64>,
            VecDeque<PumpRealtimeNotification>,
            u64,
        ),
        ProviderError,
    > {
        let provider = self.config.provider;
        let (mut socket, _) = connect_async(self.config.endpoint.as_str())
            .await
            .map_err(|_| unavailable(provider, "bounded Pump realtime websocket connection failed"))?;

        let targets = self.targets.borrow().clone();
        let mentions = pump_realtime_initial_mentions(&targets)?;
        let mut pool_subscriptions = BTreeMap::new();
        let mut pending_notifications = VecDeque::new();

        for (index, mention) in mentions.iter().enumerate() {
            let request_id = u64::try_from(index)
                .ok()
                .and_then(|value| value.checked_add(1))
                .ok_or_else(|| invalid_request(provider, "realtime subscription request id overflow"))?;
            let request = pump_realtime_logs_subscribe_request(request_id, mention)?;
            socket
                .send(Message::Text(request.to_string().into()))
                .await
                .map_err(|_| unavailable(provider, "bounded realtime subscription send failed"))?;
            let subscription_id = await_subscription_ack(
                &mut socket,
                request_id,
                provider,
                &mut pending_notifications,
            )
            .await?;
            if mention != PUMP_PROGRAM_ID {
                pool_subscriptions.insert(mention.clone(), subscription_id);
            }
        }

        let next_request_id = u64::try_from(mentions.len())
            .ok()
            .and_then(|value| value.checked_add(1))
            .ok_or_else(|| invalid_request(provider, "realtime subscription request id overflow"))?;

        Ok((
            socket,
            pool_subscriptions,
            pending_notifications,
            next_request_id,
        ))
    }

    async fn reconcile_targets(&mut self) -> Result<(), ProviderError> {
        let targets = self.targets.borrow().clone();
        let changes = pump_realtime_subscription_changes(&self.pool_subscriptions, &targets)?;

        for change in changes {
            let request_id = self.take_request_id()?;
            match change {
                PumpRealtimeSubscriptionChange::Unsubscribe {
                    pool,
                    subscription_id,
                } => {
                    let request =
                        pump_realtime_logs_unsubscribe_request(request_id, subscription_id);
                    {
                        let socket = self
                            .socket
                            .as_mut()
                            .expect("target reconciliation requires a connected websocket");
                        socket
                            .send(Message::Text(request.to_string().into()))
                            .await
                            .map_err(|_| {
                                unavailable(
                                    self.config.provider,
                                    "bounded realtime unsubscribe send failed",
                                )
                            })?;
                        await_unsubscribe_ack(
                            socket,
                            request_id,
                            self.config.provider,
                            &mut self.pending_notifications,
                        )
                        .await?;
                    }
                    self.awaiting_heartbeat_response = false;
                    self.pool_subscriptions.remove(&pool);
                }
                PumpRealtimeSubscriptionChange::Subscribe { pool } => {
                    let request = pump_realtime_logs_subscribe_request(request_id, &pool)?;
                    let subscription_id = {
                        let socket = self
                            .socket
                            .as_mut()
                            .expect("target reconciliation requires a connected websocket");
                        socket
                            .send(Message::Text(request.to_string().into()))
                            .await
                            .map_err(|_| {
                                unavailable(
                                    self.config.provider,
                                    "bounded realtime subscription send failed",
                                )
                            })?;
                        await_subscription_ack(
                            socket,
                            request_id,
                            self.config.provider,
                            &mut self.pending_notifications,
                        )
                        .await?
                    };
                    self.awaiting_heartbeat_response = false;
                    self.pool_subscriptions.insert(pool, subscription_id);
                }
            }
        }

        Ok(())
    }

    fn take_request_id(&mut self) -> Result<u64, ProviderError> {
        let request_id = self.next_request_id;
        self.next_request_id = self.next_request_id.checked_add(1).ok_or_else(|| {
            invalid_request(
                self.config.provider,
                "realtime subscription request id overflow",
            )
        })?;
        Ok(request_id)
    }

    fn reset_connection(&mut self) {
        self.socket = None;
        self.pool_subscriptions.clear();
        self.next_request_id = 1;
        self.awaiting_heartbeat_response = false;
    }

    async fn disconnect_and_backoff(&mut self) {
        self.reset_connection();
        let delay = self.config.reconnect_delay(self.reconnect_attempt);
        self.reconnect_attempt = self.reconnect_attempt.saturating_add(1);
        sleep(delay).await;
    }
}

async fn await_subscription_ack(
    socket: &mut BoundedPumpRealtimeSocket,
    expected_request_id: u64,
    provider: ProviderId,
    pending_notifications: &mut VecDeque<PumpRealtimeNotification>,
) -> Result<u64, ProviderError> {
    loop {
        let frame = timeout(SUBSCRIPTION_ACK_TIMEOUT, socket.next())
            .await
            .map_err(|_| unavailable(provider, "bounded realtime subscription timed out"))?;
        match frame {
            Some(Ok(Message::Text(text))) => {
                let body = text.to_string();
                if let Some(subscription_id) =
                    parse_subscription_ack(&body, expected_request_id, provider)?
                {
                    return Ok(subscription_id);
                }
                if let Some(notification) = parse_notification_for_provider(&body, provider)? {
                    pending_notifications.push_back(notification);
                }
            }
            Some(Ok(Message::Ping(payload))) => {
                socket
                    .send(Message::Pong(payload))
                    .await
                    .map_err(|_| unavailable(provider, "bounded realtime pong failed"))?;
            }
            Some(Ok(Message::Pong(_)))
            | Some(Ok(Message::Binary(_)))
            | Some(Ok(Message::Frame(_))) => {}
            Some(Ok(Message::Close(_))) | Some(Err(_)) | None => {
                return Err(unavailable(
                    provider,
                    "bounded realtime websocket closed before subscription acknowledgement",
                ));
            }
        }
    }
}

async fn await_unsubscribe_ack(
    socket: &mut BoundedPumpRealtimeSocket,
    expected_request_id: u64,
    provider: ProviderId,
    pending_notifications: &mut VecDeque<PumpRealtimeNotification>,
) -> Result<(), ProviderError> {
    loop {
        let frame = timeout(SUBSCRIPTION_ACK_TIMEOUT, socket.next())
            .await
            .map_err(|_| unavailable(provider, "bounded realtime unsubscribe timed out"))?;
        match frame {
            Some(Ok(Message::Text(text))) => {
                let body = text.to_string();
                if parse_pump_realtime_unsubscribe_ack(&body, expected_request_id, provider)?
                    .is_some()
                {
                    return Ok(());
                }
                if let Some(notification) = parse_notification_for_provider(&body, provider)? {
                    pending_notifications.push_back(notification);
                }
            }
            Some(Ok(Message::Ping(payload))) => {
                socket
                    .send(Message::Pong(payload))
                    .await
                    .map_err(|_| unavailable(provider, "bounded realtime pong failed"))?;
            }
            Some(Ok(Message::Pong(_)))
            | Some(Ok(Message::Binary(_)))
            | Some(Ok(Message::Frame(_))) => {}
            Some(Ok(Message::Close(_))) | Some(Err(_)) | None => {
                return Err(unavailable(
                    provider,
                    "bounded realtime websocket closed before unsubscribe acknowledgement",
                ));
            }
        }
    }
}

fn parse_subscription_ack(
    body: &str,
    expected_request_id: u64,
    provider: ProviderId,
) -> Result<Option<u64>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|_| {
        invalid_response(
            provider,
            "invalid realtime subscription acknowledgement JSON",
        )
    })?;
    if value.get("id").and_then(Value::as_u64) != Some(expected_request_id) {
        return Ok(None);
    }
    if value.get("error").is_some_and(|error| !error.is_null()) {
        return Err(invalid_response(
            provider,
            "realtime subscription request was rejected",
        ));
    }
    let subscription_id = value
        .get("result")
        .and_then(Value::as_u64)
        .ok_or_else(|| {
            invalid_response(
                provider,
                "realtime subscription acknowledgement missing numeric result",
            )
        })?;
    Ok(Some(subscription_id))
}

fn parse_notification_for_provider(
    body: &str,
    provider: ProviderId,
) -> Result<Option<PumpRealtimeNotification>, ProviderError> {
    match parse_pump_realtime_log_notification(body) {
        Ok(Some(mut notification)) => {
            notification.provider = provider;
            Ok(Some(notification))
        }
        Ok(None) => Ok(None),
        Err(mut error) => {
            error.provider = provider;
            Err(error)
        }
    }
}

fn invalid_request(provider: ProviderId, message: impl Into<String>) -> ProviderError {
    ProviderError::new(provider, ProviderErrorKind::InvalidRequest, message)
}

fn invalid_response(provider: ProviderId, message: impl Into<String>) -> ProviderError {
    ProviderError::new(provider, ProviderErrorKind::InvalidResponse, message)
}

fn unavailable(provider: ProviderId, message: impl Into<String>) -> ProviderError {
    ProviderError::new(provider, ProviderErrorKind::Unavailable, message)
}
