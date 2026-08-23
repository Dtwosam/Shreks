use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde_json::Value;
use shreks_providers::pump::{
    PumpLifecycleSignal, PumpLogStream, PumpLogStreamConfig, PUMP_PROGRAM_ID,
};
use tokio::net::{TcpListener, TcpStream};
use tokio_tungstenite::{accept_async, tungstenite::Message, WebSocketStream};

async fn accept_pump_subscription(listener: &TcpListener) -> WebSocketStream<TcpStream> {
    let (stream, _) = listener.accept().await.expect("accept local socket");
    let mut socket = accept_async(stream).await.expect("websocket handshake");

    let request = socket
        .next()
        .await
        .expect("subscription frame")
        .expect("valid websocket frame")
        .into_text()
        .expect("text subscription");
    let request: Value = serde_json::from_str(&request).expect("valid subscription JSON");

    assert_eq!(request["method"], "logsSubscribe");
    assert_eq!(request["params"][0]["mentions"][0], PUMP_PROGRAM_ID);
    assert_eq!(request["params"][1]["commitment"], "confirmed");

    socket
        .send(Message::Text(
            r#"{"jsonrpc":"2.0","result":24040,"id":1}"#.into(),
        ))
        .await
        .expect("subscription ack");
    socket
}

fn notification(signature: &str, slot: u64, instruction: &str) -> String {
    format!(
        r#"{{
          "jsonrpc":"2.0",
          "method":"logsNotification",
          "params":{{
            "result":{{
              "context":{{"slot":{slot}}},
              "value":{{
                "signature":"{signature}",
                "err":null,
                "logs":[
                  "Program {PUMP_PROGRAM_ID} invoke [1]",
                  "Program log: Instruction: {instruction}"
                ]
              }}
            }},
            "subscription":24040
          }}
        }}"#
    )
}

#[tokio::test]
async fn reconnects_resubscribes_and_returns_next_verified_creation_signal() {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind local websocket server");
    let address = listener.local_addr().expect("local address");

    let server = tokio::spawn(async move {
        let mut first = accept_pump_subscription(&listener).await;
        first.close(None).await.expect("close first connection");

        let mut second = accept_pump_subscription(&listener).await;
        second
            .send(Message::Text(notification("buy-only", 41, "BuyV2").into()))
            .await
            .expect("send unrelated Pump log");
        second
            .send(Message::Text(notification("launch-42", 42, "CreateV2").into()))
            .await
            .expect("send creation log");
    });

    let config = PumpLogStreamConfig::for_endpoint(format!("ws://{address}"))
        .expect("valid local endpoint")
        .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
        .with_heartbeat_interval(Duration::from_secs(60));
    let mut stream = PumpLogStream::new(config);

    let signal = tokio::time::timeout(Duration::from_secs(2), stream.next_signal())
        .await
        .expect("client should recover before timeout")
        .expect("stream should recover from one disconnect");

    assert_eq!(signal.signature, "launch-42");
    assert_eq!(signal.slot, 42);
    server.await.expect("server task");
}

#[tokio::test]
async fn reconnecting_lifecycle_stream_delivers_migration_from_same_subscription() {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind local websocket server");
    let address = listener.local_addr().expect("local address");

    let server = tokio::spawn(async move {
        let mut first = accept_pump_subscription(&listener).await;
        first.close(None).await.expect("close first connection");

        let mut second = accept_pump_subscription(&listener).await;
        second
            .send(Message::Text(
                notification("migration-77", 77, "MigrateV2").into(),
            ))
            .await
            .expect("send migration log");
    });

    let config = PumpLogStreamConfig::for_endpoint(format!("ws://{address}"))
        .expect("valid local endpoint")
        .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
        .with_heartbeat_interval(Duration::from_secs(60));
    let mut stream = PumpLogStream::new(config);

    let signal = tokio::time::timeout(Duration::from_secs(2), stream.next_lifecycle_signal())
        .await
        .expect("client should recover before timeout")
        .expect("stream should recover from one disconnect");

    let PumpLifecycleSignal::Migration(signal) = signal else {
        panic!("expected migration signal");
    };
    assert_eq!(signal.signature, "migration-77");
    assert_eq!(signal.slot, 77);
    server.await.expect("server task");
}

#[tokio::test]
async fn sends_heartbeat_ping_when_subscription_is_idle() {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind local websocket server");
    let address = listener.local_addr().expect("local address");

    let server = tokio::spawn(async move {
        let mut socket = accept_pump_subscription(&listener).await;
        let frame = tokio::time::timeout(Duration::from_secs(1), socket.next())
            .await
            .expect("heartbeat should arrive")
            .expect("heartbeat frame")
            .expect("valid heartbeat frame");
        assert!(matches!(frame, Message::Ping(_)));

        socket
            .send(Message::Text(
                notification("launch-heartbeat", 99, "Create").into(),
            ))
            .await
            .expect("send creation after heartbeat");
    });

    let config = PumpLogStreamConfig::for_endpoint(format!("ws://{address}"))
        .expect("valid local endpoint")
        .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
        .with_heartbeat_interval(Duration::from_millis(10));
    let mut stream = PumpLogStream::new(config);

    let signal = tokio::time::timeout(Duration::from_secs(2), stream.next_signal())
        .await
        .expect("client should receive post-heartbeat signal")
        .expect("stream should remain healthy");

    assert_eq!(signal.signature, "launch-heartbeat");
    assert_eq!(signal.slot, 99);
    server.await.expect("server task");
}

#[test]
fn stream_config_debug_never_exposes_helius_api_key() {
    let config = PumpLogStreamConfig::helius("super-secret-helius-key")
        .expect("valid Helius key");
    let debug = format!("{config:?}");

    assert!(!debug.contains("super-secret-helius-key"));
    assert!(!debug.contains("api-key="));
}
