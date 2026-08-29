use serde_json::json;
use shreks_core::ProviderId;
use shreks_providers::{
    pump_realtime::parse_pump_realtime_log_notification, ProviderErrorKind,
};

const DEFAULT_SOLANA_SIGNATURE: &str =
    "1111111111111111111111111111111111111111111111111111111111111111";

#[test]
fn successful_realtime_notification_rejects_default_zero_signature() {
    let body = json!({
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": 442_574_499_u64},
                "value": {
                    "signature": DEFAULT_SOLANA_SIGNATURE,
                    "err": null,
                    "logs": []
                }
            },
            "subscription": 24_040_u64
        }
    })
    .to_string();

    let error = parse_pump_realtime_log_notification(&body)
        .expect_err("the all-zero/default Solana signature must never become realtime evidence");

    assert_eq!(error.provider, ProviderId::Helius);
    assert!(matches!(error.kind, ProviderErrorKind::InvalidResponse));
    assert!(error.message.contains("default Solana signature"));
}
