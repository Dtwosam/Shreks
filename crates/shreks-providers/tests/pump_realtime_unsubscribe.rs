use serde_json::json;
use shreks_core::ProviderId;
use shreks_providers::{
    realtime_scope::{
        parse_pump_realtime_unsubscribe_ack, pump_realtime_logs_unsubscribe_request,
    },
    ProviderErrorKind,
};

#[test]
fn unsubscribe_request_uses_exact_provider_subscription_id() {
    let request = pump_realtime_logs_unsubscribe_request(41, 9001);
    assert_eq!(request["jsonrpc"], "2.0");
    assert_eq!(request["id"], 41);
    assert_eq!(request["method"], "logsUnsubscribe");
    assert_eq!(request["params"], json!([9001]));
}

#[test]
fn unsubscribe_requires_true_ack_and_preserves_provider_identity() {
    let accepted = json!({"jsonrpc":"2.0","id":41,"result":true}).to_string();
    assert!(matches!(
        parse_pump_realtime_unsubscribe_ack(&accepted, 41, ProviderId::Chainstack).unwrap(),
        Some(())
    ));

    let unrelated = json!({"jsonrpc":"2.0","id":99,"result":true}).to_string();
    assert!(parse_pump_realtime_unsubscribe_ack(&unrelated, 41, ProviderId::Chainstack)
        .unwrap()
        .is_none());

    for rejected in [
        json!({"jsonrpc":"2.0","id":41,"result":false}).to_string(),
        json!({"jsonrpc":"2.0","id":41,"result":null}).to_string(),
        json!({"jsonrpc":"2.0","id":41,"error":{"code":-32602,"message":"bad"}}).to_string(),
        "not-json".to_owned(),
    ] {
        let error = parse_pump_realtime_unsubscribe_ack(&rejected, 41, ProviderId::Chainstack)
            .expect_err("unsubscribe rejection must fail closed");
        assert_eq!(error.provider, ProviderId::Chainstack);
        assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
        assert!(!error.message.contains("http"));
    }
}
