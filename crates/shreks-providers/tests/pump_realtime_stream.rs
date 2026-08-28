use std::time::Duration;

use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use shreks_core::ProviderId;
use shreks_providers::{
    pump::{PUMP_AMM_PROGRAM_ID, PUMP_PROGRAM_ID, WRAPPED_SOL_MINT},
    pump_realtime::{
        forward_pump_realtime_signals, PumpRealtimeFailoverStream, PumpRealtimeLogStream,
        PumpRealtimeLogStreamConfig,
    },
    pump_trade::PUMP_TRADE_EVENT_DISCRIMINATOR,
};
use tokio::{
    net::{TcpListener, TcpStream},
    sync::mpsc,
};
use tokio_tungstenite::{accept_async, tungstenite::Message, WebSocketStream};

const MINT: &str = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump";
const USER: &str = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA";
const DEFAULT_QUOTE_MINT: &str = "11111111111111111111111111111111";

async fn accept_pump_subscriptions(listener: &TcpListener) -> WebSocketStream<TcpStream> {
    let (stream, _) = listener.accept().await.expect("accept local socket");
    let mut socket = accept_async(stream).await.expect("websocket handshake");

    for (request_id, program_id, subscription_id) in [
        (1_u64, PUMP_PROGRAM_ID, 24_040_u64),
        (2_u64, PUMP_AMM_PROGRAM_ID, 24_041_u64),
    ] {
        let request = socket
            .next()
            .await
            .expect("subscription frame")
            .expect("valid websocket frame")
            .into_text()
            .expect("text subscription");
        let request: Value = serde_json::from_str(&request).expect("valid subscription JSON");
        assert_eq!(request["id"], request_id);
        assert_eq!(request["method"], "logsSubscribe");
        assert_eq!(request["params"][0]["mentions"][0], program_id);
        assert_eq!(request["params"][1]["commitment"], "confirmed");
        socket
            .send(Message::Text(
                json!({"jsonrpc": "2.0", "result": subscription_id, "id": request_id})
                    .to_string()
                    .into(),
            ))
            .await
            .expect("subscription ack");
    }

    socket
}

fn push_pubkey(output: &mut Vec<u8>, value: &str) {
    let decoded = bs58::decode(value).into_vec().expect("valid fixture pubkey");
    assert_eq!(decoded.len(), 32);
    output.extend_from_slice(&decoded);
}

fn push_u64(output: &mut Vec<u8>, value: u64) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn push_i64(output: &mut Vec<u8>, value: i64) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn push_bool(output: &mut Vec<u8>, value: bool) {
    output.push(u8::from(value));
}

fn push_string(output: &mut Vec<u8>, value: &str) {
    let len = u32::try_from(value.len()).unwrap();
    output.extend_from_slice(&len.to_le_bytes());
    output.extend_from_slice(value.as_bytes());
}

fn trade_event_program_data() -> String {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&PUMP_TRADE_EVENT_DISCRIMINATOR);
    push_pubkey(&mut bytes, MINT);
    push_u64(&mut bytes, 2_500_000_000);
    push_u64(&mut bytes, 500_000_000);
    push_bool(&mut bytes, true);
    push_pubkey(&mut bytes, USER);
    push_i64(&mut bytes, 1_770_000_000);
    push_u64(&mut bytes, 32_000_000_000);
    push_u64(&mut bytes, 900_000_000_000_000);
    push_u64(&mut bytes, 10_000_000_000);
    push_u64(&mut bytes, 600_000_000_000_000);
    push_pubkey(&mut bytes, WRAPPED_SOL_MINT);
    push_u64(&mut bytes, 125);
    push_u64(&mut bytes, 31_250_000);
    push_pubkey(&mut bytes, PUMP_PROGRAM_ID);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_bool(&mut bytes, true);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 2_500_000_000);
    push_i64(&mut bytes, 1_770_000_000);
    push_string(&mut bytes, "buy");
    push_bool(&mut bytes, false);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    bytes.extend_from_slice(&0_u32.to_le_bytes());
    push_pubkey(&mut bytes, DEFAULT_QUOTE_MINT);
    push_u64(&mut bytes, 2_500_000_000);
    push_u64(&mut bytes, 32_000_000_000);
    push_u64(&mut bytes, 10_000_000_000);
    BASE64_STANDARD.encode(bytes)
}

fn trade_notification(signature: &str, slot: u64) -> String {
    json!({
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": slot},
                "value": {
                    "signature": signature,
                    "err": null,
                    "logs": [
                        format!("Program {PUMP_PROGRAM_ID} invoke [1]"),
                        "Program log: Instruction: BuyV2",
                        format!("Program data: {}", trade_event_program_data()),
                        format!("Program {PUMP_PROGRAM_ID} success")
                    ]
                }
            },
            "subscription": 24040
        }
    })
    .to_string()
}

async fn unavailable_ws_endpoint() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    format!("ws://{address}")
}

#[tokio::test]
async fn realtime_stream_uses_one_socket_for_pump_and_pumpswap_subscriptions() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let mut socket = accept_pump_subscriptions(&listener).await;
        socket
            .send(Message::Text(trade_notification("trade-1", 77).into()))
            .await
            .unwrap();
    });

    let config = PumpRealtimeLogStreamConfig::for_endpoint(format!("ws://{address}"))
        .unwrap()
        .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
        .with_heartbeat_interval(Duration::from_secs(60));
    let mut stream = PumpRealtimeLogStream::new(config);
    let realtime = tokio::time::timeout(
        Duration::from_secs(2),
        stream.next_realtime_notification(),
    )
    .await
    .expect("realtime notification before timeout")
    .expect("valid realtime stream event");

    assert_eq!(realtime.provider, ProviderId::Helius);
    assert_eq!(realtime.signature, "trade-1");
    assert_eq!(realtime.slot, 77);
    assert!(realtime.lifecycle.is_none());
    assert_eq!(realtime.trades.len(), 1);
    assert_eq!(realtime.trades[0].token_amount_raw, 500_000_000);
    server.await.unwrap();
}

#[tokio::test]
async fn provider_aware_stream_preserves_alchemy_source_identity() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let mut socket = accept_pump_subscriptions(&listener).await;
        socket
            .send(Message::Text(trade_notification("alchemy-trade", 88).into()))
            .await
            .unwrap();
    });

    let config = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Alchemy,
        format!("ws://{address}"),
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5));
    let mut stream = PumpRealtimeLogStream::new(config);
    let realtime = tokio::time::timeout(
        Duration::from_secs(2),
        stream.next_realtime_notification(),
    )
    .await
    .expect("realtime notification before timeout")
    .expect("valid realtime stream event");

    assert_eq!(realtime.provider, ProviderId::Alchemy);
    assert_eq!(realtime.signature, "alchemy-trade");
    server.await.unwrap();
}

#[tokio::test]
async fn provider_aware_stream_preserves_chainstack_source_identity() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let mut socket = accept_pump_subscriptions(&listener).await;
        socket
            .send(Message::Text(trade_notification("chainstack-trade", 89).into()))
            .await
            .unwrap();
    });

    let config = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Chainstack,
        format!("ws://{address}"),
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5));
    let mut stream = PumpRealtimeLogStream::new(config);
    let realtime = tokio::time::timeout(
        Duration::from_secs(2),
        stream.next_realtime_notification(),
    )
    .await
    .expect("realtime notification before timeout")
    .expect("valid realtime stream event");

    assert_eq!(realtime.provider, ProviderId::Chainstack);
    assert_eq!(realtime.signature, "chainstack-trade");
    server.await.unwrap();
}

#[tokio::test]
async fn realtime_stream_returns_after_bounded_connection_failures() {
    let config = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Helius,
        unavailable_ws_endpoint().await,
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(2);
    let mut stream = PumpRealtimeLogStream::new(config);

    let error = tokio::time::timeout(
        Duration::from_secs(1),
        stream.next_realtime_notification(),
    )
    .await
    .expect("bounded retries must finish")
    .expect_err("unavailable endpoint must fail");

    assert_eq!(error.provider, ProviderId::Helius);
    assert!(error.is_retryable());
}

#[tokio::test]
async fn failover_stream_rotates_from_unavailable_helius_to_chainstack() {
    let chainstack_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let chainstack_address = chainstack_listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let mut socket = accept_pump_subscriptions(&chainstack_listener).await;
        socket
            .send(Message::Text(trade_notification("chainstack-fallback", 98).into()))
            .await
            .unwrap();
    });

    let helius = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Helius,
        unavailable_ws_endpoint().await,
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);
    let chainstack = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Chainstack,
        format!("ws://{chainstack_address}"),
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);

    let mut stream = PumpRealtimeFailoverStream::new(vec![helius, chainstack]).unwrap();
    let realtime = tokio::time::timeout(
        Duration::from_secs(2),
        stream.next_realtime_notification(),
    )
    .await
    .expect("fallback notification before timeout")
    .expect("Chainstack fallback should succeed");

    assert_eq!(realtime.provider, ProviderId::Chainstack);
    assert_eq!(realtime.signature, "chainstack-fallback");
    server.await.unwrap();
}

#[tokio::test]
async fn failover_stream_rotates_from_unavailable_helius_to_alchemy() {
    let alchemy_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let alchemy_address = alchemy_listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let mut socket = accept_pump_subscriptions(&alchemy_listener).await;
        socket
            .send(Message::Text(trade_notification("fallback-trade", 99).into()))
            .await
            .unwrap();
    });

    let helius = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Helius,
        unavailable_ws_endpoint().await,
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);
    let alchemy = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Alchemy,
        format!("ws://{alchemy_address}"),
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);

    let mut stream = PumpRealtimeFailoverStream::new(vec![helius, alchemy]).unwrap();
    let realtime = tokio::time::timeout(
        Duration::from_secs(2),
        stream.next_realtime_notification(),
    )
    .await
    .expect("fallback notification before timeout")
    .expect("secondary provider should succeed");

    assert_eq!(realtime.provider, ProviderId::Alchemy);
    assert_eq!(realtime.signature, "fallback-trade");
    server.await.unwrap();
}

#[tokio::test]
async fn realtime_forwarder_is_storage_free_and_stops_when_consumer_is_gone() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let mut socket = accept_pump_subscriptions(&listener).await;
        socket
            .send(Message::Text(trade_notification("trade-2", 78).into()))
            .await
            .unwrap();
    });

    let config = PumpRealtimeLogStreamConfig::for_endpoint(format!("ws://{address}"))
        .unwrap()
        .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5));
    let stream = PumpRealtimeLogStream::new(config);
    let (sender, receiver) = mpsc::channel(1);
    drop(receiver);

    tokio::time::timeout(Duration::from_secs(2), forward_pump_realtime_signals(stream, sender))
        .await
        .expect("forwarder should stop after receiver closes")
        .expect("receiver closure is not a provider failure");
    server.await.unwrap();
}
