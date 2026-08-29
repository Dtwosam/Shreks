use std::time::Duration;

use shreks_core::ProviderId;
use shreks_providers::pump_realtime::{
    PumpRealtimeFailoverStream, PumpRealtimeLogStreamConfig,
};
use tokio::net::TcpListener;

async fn unavailable_ws_endpoint() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    format!("ws://{address}")
}

#[tokio::test]
async fn failover_returns_error_when_every_realtime_provider_is_unavailable() {
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
    assert!(error.is_retryable());
    assert!(
        error
            .message
            .contains("failover_attempts=helius:Unavailable,alchemy:Unavailable"),
        "terminal failover error must retain a provider/kind-only attempt trace: {}",
        error.message
    );
    assert!(
        !error.message.contains("ws://") && !error.message.contains("wss://"),
        "failover diagnostics must never expose provider endpoints: {}",
        error.message
    );
}
