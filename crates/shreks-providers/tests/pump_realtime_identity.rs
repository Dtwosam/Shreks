use serde_json::json;
use shreks_providers::pump_realtime::parse_pump_realtime_log_notification;

const DEFAULT_SOLANA_SIGNATURE: &str =
    "1111111111111111111111111111111111111111111111111111111111111111";

#[test]
fn successful_realtime_notification_drops_default_zero_signature() {
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

    let parsed = parse_pump_realtime_log_notification(&body)
        .expect("the default signature must be ignored without terminating the realtime stream");

    assert!(parsed.is_none());
}
