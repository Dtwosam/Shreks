use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use shreks_core::ProviderId;
use shreks_providers::{
    pump_realtime::{PumpRealtimeFailoverStream, PumpRealtimeLogStreamConfig},
    ProviderErrorKind,
};
use tokio::net::TcpListener;
use tokio_tungstenite::{accept_async, tungstenite::Message};

async fn unavailable_ws_endpoint() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    format!("ws://{address}")
}

async fn method_not_found_ws_endpoint() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();

    tokio::spawn(async move {
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
        assert_eq!(request["id"], 1);
        assert_eq!(request["method"], "logsSubscribe");
        socket
            .send(Message::Text(
                json!({
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": "Method 'logsSubscribe' not found"},
                    "id": 1
                })
                .to_string()
                .into(),
            ))
            .await
            .expect("subscription error response");
    });

    format!("ws://{address}")
}

async fn malformed_evidence_ws_endpoint() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();

    tokio::spawn(async move {
        let (stream, _) = listener.accept().await.expect("accept local socket");
        let mut socket = accept_async(stream).await.expect("websocket handshake");

        for request_id in [1_u64, 2_u64] {
            let request = socket
                .next()
                .await
                .expect("subscription frame")
                .expect("valid websocket frame")
                .into_text()
                .expect("text subscription");
            let request: Value =
                serde_json::from_str(&request).expect("valid subscription JSON");
            assert_eq!(request["id"], request_id);
            assert_eq!(request["method"], "logsSubscribe");
            socket
                .send(Message::Text(
                    json!({"jsonrpc": "2.0", "result": 100 + request_id, "id": request_id})
                        .to_string()
                        .into(),
                ))
                .await
                .expect("subscription acknowledgement");
        }

        socket
            .send(Message::Text(
                json!({
                    "jsonrpc": "2.0",
                    "method": "logsNotification",
                    "params": {
                        "result": {
                            "context": {"slot": 123},
                            "value": {
                                "err": null,
                                "signature": "malformed-evidence"
                            }
                        }
                    }
                })
                .to_string()
                .into(),
            ))
            .await
            .expect("malformed evidence notification");
    });

    format!("ws://{address}")
}

#[tokio::test]
async fn failover_returns_truthful_error_when_every_realtime_provider_is_unavailable() {
    let helius = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Helius,
        unavailable_ws_endpoint().await,
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);
    let alchemy = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Alchemy,
        unavailable_ws_endpoint().await,
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);

    let mut stream = PumpRealtimeFailoverStream::new(vec![helius, alchemy]).unwrap();
    let error = tokio::time::timeout(
        Duration::from_secs(1),
        stream.next_realtime_notification(),
    )
    .await
    .expect("all-provider exhaustion must finish within a bounded timeout")
    .expect_err("all unavailable providers must fail closed");

    assert_eq!(error.provider, ProviderId::Alchemy);
    assert_eq!(error.kind, ProviderErrorKind::Unavailable);
    assert!(error.is_retryable());
    assert!(
        error
            .message
            .contains("failover_attempts=helius:Unavailable,alchemy:Unavailable"),
        "terminal failover error must retain provider/kind-only attempt trace: {}",
        error.message
    );
    assert!(
        !error.message.contains("ws://") && !error.message.contains("wss://"),
        "failover diagnostics must never expose provider endpoints: {}",
        error.message
    );
}

#[tokio::test]
async fn subscription_method_not_found_rotates_as_setup_unavailable_then_fails_closed_if_all_lanes_fail() {
    let alchemy = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Alchemy,
        method_not_found_ws_endpoint().await,
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);
    let helius = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Helius,
        unavailable_ws_endpoint().await,
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);

    let mut stream = PumpRealtimeFailoverStream::new(vec![alchemy, helius]).unwrap();
    let error = tokio::time::timeout(
        Duration::from_secs(1),
        stream.next_realtime_notification(),
    )
    .await
    .expect("setup outage rotation must finish within a bounded timeout when every lane fails")
    .expect_err("complete provider exhaustion must fail closed");

    assert_eq!(error.provider, ProviderId::Helius);
    assert_eq!(error.kind, ProviderErrorKind::Unavailable);
    assert!(
        error
            .message
            .contains("failover_attempts=alchemy:Unavailable,helius:Unavailable"),
        "setup method-not-found must be downgraded only to provider unavailability and preserved in the sanitized rotation trace: {}",
        error.message
    );
}

#[tokio::test]
async fn malformed_post_subscription_evidence_remains_terminal_fail_closed() {
    let helius = PumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Helius,
        malformed_evidence_ws_endpoint().await,
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);

    let mut stream = PumpRealtimeFailoverStream::new(vec![helius]).unwrap();
    let error = tokio::time::timeout(
        Duration::from_secs(1),
        stream.next_realtime_notification(),
    )
    .await
    .expect("malformed evidence must terminate promptly")
    .expect_err("malformed evidence after successful subscription must fail closed");

    assert_eq!(error.provider, ProviderId::Helius);
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
    assert!(error.message.contains("missing logs array"));
}
