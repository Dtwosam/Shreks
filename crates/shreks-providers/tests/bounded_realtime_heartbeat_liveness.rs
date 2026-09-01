use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use shreks_core::ProviderId;
use shreks_providers::{
    bounded_pump_realtime::{BoundedPumpRealtimeLogStream, BoundedPumpRealtimeLogStreamConfig},
    pump::PUMP_PROGRAM_ID,
};
use tokio::{
    net::TcpListener,
    sync::{oneshot, watch},
};
use tokio_tungstenite::{accept_async, tungstenite::Message};

async fn read_json(socket: &mut tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>) -> Value {
    let text = socket.next().await.unwrap().unwrap().into_text().unwrap();
    serde_json::from_str(&text).unwrap()
}

async fn acknowledge_pump_subscription(
    socket: &mut tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>,
    subscription_id: u64,
) {
    let request = read_json(socket).await;
    assert_eq!(request["method"], "logsSubscribe");
    assert_eq!(request["params"][0]["mentions"][0], PUMP_PROGRAM_ID);
    let request_id = request["id"].as_u64().unwrap();
    socket
        .send(Message::Text(
            json!({"jsonrpc":"2.0","id":request_id,"result":subscription_id})
                .to_string()
                .into(),
        ))
        .await
        .unwrap();
}

#[tokio::test]
async fn bounded_stream_reconnects_when_heartbeat_ping_receives_no_inbound_frame() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (second_connection_sender, second_connection_receiver) = oneshot::channel();

    let server = tokio::spawn(async move {
        let (first_tcp, _) = listener.accept().await.unwrap();
        let mut first_socket = accept_async(first_tcp).await.unwrap();
        acknowledge_pump_subscription(&mut first_socket, 100).await;

        let first_ping = tokio::time::timeout(Duration::from_millis(250), first_socket.next())
            .await
            .expect("client must send a heartbeat ping on an idle subscribed socket")
            .unwrap()
            .unwrap();
        assert!(matches!(first_ping, Message::Ping(_)));

        // Keep the first TCP/WebSocket connection open but deliberately send no
        // Pong, notification, or any other inbound frame. A healthy client must
        // not consider successful Ping writes proof that this half-open lane is
        // still delivering realtime evidence.
        let (second_tcp, _) = tokio::time::timeout(Duration::from_millis(500), listener.accept())
            .await
            .expect("missing heartbeat response must force a reconnect")
            .unwrap();
        let mut second_socket = accept_async(second_tcp).await.unwrap();
        acknowledge_pump_subscription(&mut second_socket, 101).await;
        second_connection_sender.send(()).unwrap();

        tokio::time::sleep(Duration::from_millis(100)).await;
    });

    let (_targets_sender, targets_receiver) = watch::channel(Vec::<String>::new());
    let config = BoundedPumpRealtimeLogStreamConfig::for_provider_endpoint(
        ProviderId::SolanaPublic,
        format!("ws://{address}"),
    )
    .unwrap()
    .with_heartbeat_interval(Duration::from_millis(30))
    .with_reconnect_bounds(Duration::from_millis(5), Duration::from_millis(5))
    .with_max_connect_attempts(2);
    let mut stream = BoundedPumpRealtimeLogStream::new(config, targets_receiver).unwrap();
    let client = tokio::spawn(async move { stream.next_realtime_notification().await });

    tokio::time::timeout(Duration::from_millis(750), second_connection_receiver)
        .await
        .expect("heartbeat watchdog must reconnect a silent half-open websocket")
        .unwrap();

    client.abort();
    let _ = client.await;
    server.await.unwrap();
}
