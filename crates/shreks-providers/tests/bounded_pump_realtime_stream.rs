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
use tokio::{
    net::TcpListener,
    sync::{oneshot, watch},
};
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

async fn read_json(socket: &mut tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>) -> Value {
    let text = socket.next().await.unwrap().unwrap().into_text().unwrap();
    serde_json::from_str(&text).unwrap()
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
            let request = read_json(&mut socket).await;
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
        tokio::time::sleep(Duration::from_millis(500)).await;
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

#[tokio::test]
async fn target_change_unsubscribes_stale_pool_before_subscribing_replacement_without_market_log() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (initial_ready_sender, initial_ready_receiver) = oneshot::channel();
    let (reconciled_sender, reconciled_receiver) = oneshot::channel();

    let server = tokio::spawn(async move {
        let (tcp, _) = listener.accept().await.unwrap();
        let mut socket = accept_async(tcp).await.unwrap();

        let pump = read_json(&mut socket).await;
        assert_eq!(pump["method"], "logsSubscribe");
        assert_eq!(pump["params"][0]["mentions"][0], PUMP_PROGRAM_ID);
        let pump_request_id = pump["id"].as_u64().unwrap();
        socket.send(Message::Text(
            json!({"jsonrpc":"2.0","id":pump_request_id,"result":100_u64})
                .to_string().into()
        )).await.unwrap();

        let pool_a = read_json(&mut socket).await;
        assert_eq!(pool_a["method"], "logsSubscribe");
        assert_eq!(pool_a["params"][0]["mentions"][0], "pool-a");
        let pool_a_request_id = pool_a["id"].as_u64().unwrap();
        socket.send(Message::Text(
            json!({"jsonrpc":"2.0","id":pool_a_request_id,"result":101_u64})
                .to_string().into()
        )).await.unwrap();
        initial_ready_sender.send(()).unwrap();

        let unsubscribe = tokio::time::timeout(Duration::from_millis(500), read_json(&mut socket))
            .await
            .expect("target change must wake realtime stream without a market log");
        assert_eq!(unsubscribe["method"], "logsUnsubscribe");
        assert_eq!(unsubscribe["params"], json!([101_u64]));
        let unsubscribe_request_id = unsubscribe["id"].as_u64().unwrap();
        socket.send(Message::Text(
            json!({"jsonrpc":"2.0","id":unsubscribe_request_id,"result":true})
                .to_string().into()
        )).await.unwrap();

        let pool_b = read_json(&mut socket).await;
        assert_eq!(pool_b["method"], "logsSubscribe");
        assert_eq!(pool_b["params"][0]["mentions"][0], "pool-b");
        let pool_b_request_id = pool_b["id"].as_u64().unwrap();
        socket.send(Message::Text(
            json!({"jsonrpc":"2.0","id":pool_b_request_id,"result":102_u64})
                .to_string().into()
        )).await.unwrap();

        reconciled_sender.send(()).unwrap();
        tokio::time::sleep(Duration::from_millis(100)).await;
    });

    let (targets_sender, targets_receiver) = watch::channel(vec!["pool-a".to_owned()]);
    let config = BoundedPumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::Chainstack,
        format!("ws://{address}"),
    ).unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(1);
    let mut stream = BoundedPumpRealtimeLogStream::new(config, targets_receiver).unwrap();
    let client = tokio::spawn(async move { stream.next_realtime_notification().await });

    initial_ready_receiver.await.unwrap();
    targets_sender.send(vec!["pool-b".to_owned()]).unwrap();
    tokio::time::timeout(Duration::from_millis(750), reconciled_receiver)
        .await
        .expect("bounded stream must reconcile changed targets promptly")
        .unwrap();

    client.abort();
    let _ = client.await;
    server.await.unwrap();
}
