use std::{
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    time::Duration,
};

use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use shreks_core::ProviderId;
use shreks_providers::{
    bounded_pump_realtime::{BoundedPumpRealtimeLogStream, BoundedPumpRealtimeLogStreamConfig},
    ProviderErrorKind,
};
use tokio::{net::TcpListener, sync::watch};
use tokio_tungstenite::{accept_async, tungstenite::Message};

async fn acknowledge_initial_pump_subscription(
    socket: &mut tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>,
    subscription_id: u64,
) {
    let request = socket
        .next()
        .await
        .expect("subscription frame")
        .expect("valid websocket frame")
        .into_text()
        .expect("text subscription");
    let request: Value = serde_json::from_str(&request).expect("valid subscription JSON");
    assert_eq!(request["method"], "logsSubscribe");
    let request_id = request["id"].as_u64().expect("subscription request id");
    socket
        .send(Message::Text(
            json!({"jsonrpc":"2.0","id":request_id,"result":subscription_id})
                .to_string()
                .into(),
        ))
        .await
        .expect("subscription acknowledgement");
}

#[tokio::test]
async fn solana_public_reconnects_after_one_invalid_post_subscription_frame() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let connections = Arc::new(AtomicUsize::new(0));
    let server_connections = connections.clone();

    let server = tokio::spawn(async move {
        let (tcp, _) = listener.accept().await.expect("first public websocket connection");
        server_connections.fetch_add(1, Ordering::SeqCst);
        let mut socket = accept_async(tcp).await.expect("first websocket handshake");
        acknowledge_initial_pump_subscription(&mut socket, 101).await;
        socket
            .send(Message::Text("{malformed-public-frame".into()))
            .await
            .expect("malformed public frame");

        let (tcp, _) = listener
            .accept()
            .await
            .expect("public stream must reconnect after transient invalid response");
        server_connections.fetch_add(1, Ordering::SeqCst);
        let mut socket = accept_async(tcp).await.expect("second websocket handshake");
        acknowledge_initial_pump_subscription(&mut socket, 201).await;
        tokio::time::sleep(Duration::from_millis(150)).await;
    });

    let (_targets_sender, targets_receiver) = watch::channel(Vec::<String>::new());
    let config = BoundedPumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::SolanaPublic,
        format!("ws://{address}"),
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(3);
    let mut stream = BoundedPumpRealtimeLogStream::new(config, targets_receiver).unwrap();
    let client = tokio::spawn(async move { stream.next_realtime_notification().await });

    tokio::time::timeout(Duration::from_millis(500), async {
        while connections.load(Ordering::SeqCst) < 2 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("Solana public transient invalid response must cause a bounded reconnect");

    assert_eq!(connections.load(Ordering::SeqCst), 2);
    assert!(
        !client.is_finished(),
        "one transient public InvalidResponse must not terminate the realtime lane"
    );

    client.abort();
    let _ = client.await;
    server.await.unwrap();
}

#[tokio::test]
async fn solana_public_still_fails_closed_after_bounded_invalid_response_exhaustion() {
    const ATTEMPTS: usize = 3;

    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let connections = Arc::new(AtomicUsize::new(0));
    let server_connections = connections.clone();

    let server = tokio::spawn(async move {
        for index in 0..ATTEMPTS {
            let (tcp, _) = listener
                .accept()
                .await
                .expect("bounded public reconnect attempt");
            server_connections.fetch_add(1, Ordering::SeqCst);
            let mut socket = accept_async(tcp).await.expect("websocket handshake");
            acknowledge_initial_pump_subscription(&mut socket, 300 + index as u64).await;
            socket
                .send(Message::Text("{persistently-malformed-public-frame".into()))
                .await
                .expect("malformed public frame");
        }
    });

    let (_targets_sender, targets_receiver) = watch::channel(Vec::<String>::new());
    let config = BoundedPumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::SolanaPublic,
        format!("ws://{address}"),
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(ATTEMPTS as u32);
    let mut stream = BoundedPumpRealtimeLogStream::new(config, targets_receiver).unwrap();

    let error = tokio::time::timeout(
        Duration::from_secs(1),
        stream.next_realtime_notification(),
    )
    .await
    .expect("persistent public invalid responses must fail within a bounded interval")
    .expect_err("persistent public invalid responses must fail closed");

    assert_eq!(connections.load(Ordering::SeqCst), ATTEMPTS);
    assert_eq!(error.provider, ProviderId::SolanaPublic);
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
    server.await.unwrap();
}
