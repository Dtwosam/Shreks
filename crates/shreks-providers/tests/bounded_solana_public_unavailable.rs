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
    bounded_pump_realtime::BoundedPumpRealtimeLogStreamConfig,
    bounded_pump_realtime_failover::BoundedPumpRealtimeFailoverStream,
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

fn public_failover(
    address: std::net::SocketAddr,
    targets_receiver: watch::Receiver<Vec<String>>,
) -> BoundedPumpRealtimeFailoverStream {
    let config = BoundedPumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::SolanaPublic,
        format!("ws://{address}"),
    )
    .unwrap()
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(3);

    BoundedPumpRealtimeFailoverStream::new(vec![config], targets_receiver)
        .unwrap()
        .with_public_invalid_response_reconnect_policy(3, Duration::from_millis(10))
}

#[tokio::test]
async fn solana_public_reconnects_after_transient_unavailable_exhausts_inner_attempts() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let subscriptions = Arc::new(AtomicUsize::new(0));
    let server_subscriptions = subscriptions.clone();

    let server = tokio::spawn(async move {
        let (tcp, _) = listener.accept().await.expect("initial public connection");
        let mut socket = accept_async(tcp).await.expect("initial websocket handshake");
        acknowledge_initial_pump_subscription(&mut socket, 101).await;
        server_subscriptions.fetch_add(1, Ordering::SeqCst);

        socket.close(None).await.expect("close initial public socket");
        drop(socket);
        drop(listener);

        // Keep the endpoint unavailable long enough for the raw stream's three
        // bounded connection attempts to exhaust. The outer public supervisor
        // must then rebuild the same public lane instead of terminating the
        // production forwarder.
        tokio::time::sleep(Duration::from_millis(40)).await;

        let listener = TcpListener::bind(address)
            .await
            .expect("public endpoint can recover on the same address");
        let (tcp, _) = listener
            .accept()
            .await
            .expect("outer public supervisor must reconnect after recovery");
        let mut socket = accept_async(tcp).await.expect("recovery websocket handshake");
        acknowledge_initial_pump_subscription(&mut socket, 201).await;
        server_subscriptions.fetch_add(1, Ordering::SeqCst);
        tokio::time::sleep(Duration::from_millis(150)).await;
    });

    let (_targets_sender, targets_receiver) = watch::channel(Vec::<String>::new());
    let mut stream = public_failover(address, targets_receiver);
    let client = tokio::spawn(async move { stream.next_realtime_notification().await });

    tokio::time::timeout(Duration::from_secs(1), async {
        while subscriptions.load(Ordering::SeqCst) < 2 {
            assert!(
                !client.is_finished(),
                "transient Solana public Unavailable must not terminate the realtime lane"
            );
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("same public endpoint should recover after bounded outer reconnect");

    assert_eq!(subscriptions.load(Ordering::SeqCst), 2);
    assert!(
        !client.is_finished(),
        "recovered public lane must remain active after reconnect"
    );

    client.abort();
    let _ = client.await;
    server.await.unwrap();
}
