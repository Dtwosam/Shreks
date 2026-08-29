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
async fn failover_stays_alive_when_every_realtime_provider_is_temporarily_unavailable() {
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
    let result = tokio::time::timeout(
        Duration::from_millis(100),
        stream.next_realtime_notification(),
    )
    .await;

    assert!(
        result.is_err(),
        "temporary all-provider exhaustion must remain in bounded self-healing retry instead of terminating the realtime source: {result:?}"
    );
}

#[tokio::test]
async fn subscription_method_not_found_is_a_provider_setup_outage_not_terminal_evidence_failure() {
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
    let result = tokio::time::timeout(
        Duration::from_millis(150),
        stream.next_realtime_notification(),
    )
    .await;

    assert!(
        result.is_err(),
        "a provider-specific subscription capability failure must be retried/rotated as setup unavailability instead of terminating the observer: {result:?}"
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
