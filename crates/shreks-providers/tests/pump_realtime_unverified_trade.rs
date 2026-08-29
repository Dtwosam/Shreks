use serde_json::json;
use shreks_providers::{
    pump::PUMP_PROGRAM_ID,
    pump_realtime::parse_pump_realtime_log_notification,
};

#[test]
fn successful_trade_instruction_without_authoritative_trade_event_is_ignored() {
    let body = json!({
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": 442575999_u64},
                "value": {
                    "signature": "UVaRtc8n35w8oUpmiW94VrMW9ajnmbxm4BzksERjXtLGD91u3RngvUaKC8qpm2r2r6sz19G1b11zfqqvixbLUv9",
                    "err": null,
                    "logs": [
                        format!("Program {PUMP_PROGRAM_ID} invoke [1]"),
                        "Program log: Instruction: BuyV2",
                        format!("Program {PUMP_PROGRAM_ID} success")
                    ]
                }
            },
            "subscription": 24040
        }
    })
    .to_string();

    let parsed = parse_pump_realtime_log_notification(&body)
        .expect("absence of authoritative tradeEvent is not a malformed websocket frame");

    assert!(
        parsed.is_none(),
        "a trade instruction without authoritative tradeEvent evidence must be ignored"
    );
}
