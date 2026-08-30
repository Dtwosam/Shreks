use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use shreks_core::ProviderId;
use shreks_providers::{
    bounded_pump_realtime::{
        BoundedPumpRealtimeLogStream, BoundedPumpRealtimeLogStreamConfig,
    },
    pump::{PUMP_AMM_PROGRAM_ID, PUMP_PROGRAM_ID},
};
use tokio::{net::TcpListener, sync::watch};
use tokio_tungstenite::{accept_async, tungstenite::Message};

fn irrelevant_notification(signature: &str) -> String {
    json!({
        "jsonrpc":"2.0",
        "method":"logsNotification",
        "params": {
            "result": {
                "context":{"slot":77},
                "value": {
                    "signature": signature,
                    "err": null,
                    "logs": ["Program 11111111111111111111111111111111 invoke [1]", "Program 11111111111111111111111111111111 success"]
                }
            },
            "subscription": 24040
        }
    }).to_string()
}

#[tokio::test]
async fn bounded_stream_subscribes_to_pump_and_explicit_pools_only() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let (tcp, _) = listener.accept().await.unwrap();
        let mut socket = accept_async(tcp).await.unwrap();
        let mut mentions = Vec::new();

        for subscription_id in [24_040_u64, 24_041_u64] {
            let text = socket.next().await.unwrap().unwrap().into_text().unwrap();
            let request: Value = serde_json::from_str(&text).unwrap();
            assert_eq!(request["method"], "logsSubscribe");
            let request_id = request["id"].as_u64().unwrap();
            mentions.push(request["params"][0]["mentions"][0].as_str().unwrap().to_owned());
            socket.send(Message::Text(
                json!({"jsonrpc":"2.0","id":request_id,"result":subscription_id})
                    .to_string().into()
            )).await.unwrap();
        }

        assert_eq!(mentions, vec![PUMP_PROGRAM_ID.to_owned(), "pool-a".to_owned()]);
        assert!(!mentions.iter().any(|value| value == PUMP_AMM_PROGRAM_ID));

        socket.send(Message::Text(irrelevant_notification("ignored").into())).await.unwrap();
    });

    let (_targets_sender, targets_receiver) = watch::channel(vec!["pool-a".to_owned()]);
    let config = BoundedPumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Chainstack,
        format!("ws://{address}"),
    ).unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);
    let mut stream = BoundedPumpRealtimeLogStream::new(config, targets_receiver).unwrap();

    let result = tokio::time::timeout(Duration::from_millis(250), stream.next_realtime_notification()).await;
    assert!(result.is_err(), "irrelevant notification should not become evidence");
    server.await.unwrap();
}
