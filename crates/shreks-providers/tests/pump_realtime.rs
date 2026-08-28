use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use serde_json::json;
use shreks_providers::{
    pump::{PumpLifecycleSignal, PUMP_PROGRAM_ID, WRAPPED_SOL_MINT},
    pump_realtime::parse_pump_realtime_log_notification,
    pump_trade::PUMP_TRADE_EVENT_DISCRIMINATOR,
};

const MINT: &str = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump";
const USER: &str = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA";
const DEFAULT_QUOTE_MINT: &str = "11111111111111111111111111111111";
const EVENT_TIMESTAMP_SECONDS: i64 = 1_770_000_000;

fn push_pubkey(output: &mut Vec<u8>, value: &str) {
    let decoded = bs58::decode(value).into_vec().expect("valid fixture pubkey");
    assert_eq!(decoded.len(), 32);
    output.extend_from_slice(&decoded);
}

fn push_u64(output: &mut Vec<u8>, value: u64) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn push_i64(output: &mut Vec<u8>, value: i64) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn push_bool(output: &mut Vec<u8>, value: bool) {
    output.push(u8::from(value));
}

fn push_string(output: &mut Vec<u8>, value: &str) {
    let len = u32::try_from(value.len()).unwrap();
    output.extend_from_slice(&len.to_le_bytes());
    output.extend_from_slice(value.as_bytes());
}

fn trade_event_program_data() -> String {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&PUMP_TRADE_EVENT_DISCRIMINATOR);
    push_pubkey(&mut bytes, MINT);
    push_u64(&mut bytes, 2_500_000_000);
    push_u64(&mut bytes, 500_000_000);
    push_bool(&mut bytes, true);
    push_pubkey(&mut bytes, USER);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_u64(&mut bytes, 32_000_000_000);
    push_u64(&mut bytes, 900_000_000_000_000);
    push_u64(&mut bytes, 10_000_000_000);
    push_u64(&mut bytes, 600_000_000_000_000);
    push_pubkey(&mut bytes, WRAPPED_SOL_MINT);
    push_u64(&mut bytes, 125);
    push_u64(&mut bytes, 31_250_000);
    push_pubkey(&mut bytes, PUMP_PROGRAM_ID);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_bool(&mut bytes, true);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 2_500_000_000);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_string(&mut bytes, "buy");
    push_bool(&mut bytes, false);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    bytes.extend_from_slice(&0_u32.to_le_bytes());
    push_pubkey(&mut bytes, DEFAULT_QUOTE_MINT);
    push_u64(&mut bytes, 2_500_000_000);
    push_u64(&mut bytes, 32_000_000_000);
    push_u64(&mut bytes, 10_000_000_000);
    BASE64_STANDARD.encode(bytes)
}

fn notification(logs: Vec<String>, err: serde_json::Value) -> String {
    json!({
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": 777_u64},
                "value": {
                    "signature": "realtime-signature",
                    "err": err,
                    "logs": logs
                }
            },
            "subscription": 24040
        }
    })
    .to_string()
}

#[test]
fn one_confirmed_notification_carries_lifecycle_and_actual_trade_economics() {
    let program_data = trade_event_program_data();
    let body = notification(
        vec![
            format!("Program {PUMP_PROGRAM_ID} invoke [1]"),
            "Program log: Instruction: CreateV2".to_owned(),
            "Program log: Instruction: BuyV2".to_owned(),
            format!("Program data: {program_data}"),
            format!("Program {PUMP_PROGRAM_ID} success"),
        ],
        serde_json::Value::Null,
    );

    let realtime = parse_pump_realtime_log_notification(&body)
        .expect("valid realtime notification")
        .expect("Pump lifecycle/trade notification must be relevant");

    assert_eq!(realtime.signature, "realtime-signature");
    assert_eq!(realtime.slot, 777);
    let Some(PumpLifecycleSignal::Creation(creation)) = realtime.lifecycle else {
        panic!("expected creation lifecycle signal");
    };
    assert_eq!(creation.signature, "realtime-signature");
    assert_eq!(creation.slot, 777);

    assert_eq!(realtime.trades.len(), 1);
    let trade = &realtime.trades[0];
    assert_eq!(trade.mint, MINT);
    assert_eq!(trade.user, USER);
    assert!(trade.is_buy);
    assert_eq!(trade.token_amount_raw, 500_000_000);
    assert_eq!(trade.sol_amount_raw, 2_500_000_000);
    assert_eq!(trade.quote_amount_raw, 2_500_000_000);
    assert_eq!(trade.timestamp_unix_seconds, EVENT_TIMESTAMP_SECONDS);
}

#[test]
fn trade_only_notification_is_relevant_without_inventing_lifecycle() {
    let program_data = trade_event_program_data();
    let body = notification(
        vec![
            format!("Program {PUMP_PROGRAM_ID} invoke [1]"),
            "Program log: Instruction: BuyV2".to_owned(),
            format!("Program data: {program_data}"),
            format!("Program {PUMP_PROGRAM_ID} success"),
        ],
        serde_json::Value::Null,
    );

    let realtime = parse_pump_realtime_log_notification(&body)
        .unwrap()
        .expect("trade-only Pump notification must be emitted");
    assert!(realtime.lifecycle.is_none());
    assert_eq!(realtime.trades.len(), 1);
}

#[test]
fn failed_or_spoofed_program_data_never_becomes_trade_evidence() {
    let program_data = trade_event_program_data();
    let failed = notification(
        vec![
            format!("Program {PUMP_PROGRAM_ID} invoke [1]"),
            "Program log: Instruction: BuyV2".to_owned(),
            format!("Program data: {program_data}"),
            format!("Program {PUMP_PROGRAM_ID} success"),
        ],
        json!({"InstructionError": [0, 1]}),
    );
    assert!(parse_pump_realtime_log_notification(&failed).unwrap().is_none());

    let spoof_program = "11111111111111111111111111111111";
    let spoof = notification(
        vec![
            format!("Program {spoof_program} invoke [1]"),
            "Program log: Instruction: BuyV2".to_owned(),
            format!("Program data: {program_data}"),
            format!("Program {spoof_program} success"),
        ],
        serde_json::Value::Null,
    );
    assert!(parse_pump_realtime_log_notification(&spoof).unwrap().is_none());
}

#[test]
fn malformed_relevant_trade_event_fails_closed() {
    let malformed = BASE64_STANDARD.encode([
        PUMP_TRADE_EVENT_DISCRIMINATOR.as_slice(),
        &[1_u8, 2_u8, 3_u8],
    ]
    .concat());
    let body = notification(
        vec![
            format!("Program {PUMP_PROGRAM_ID} invoke [1]"),
            "Program log: Instruction: BuyV2".to_owned(),
            format!("Program data: {malformed}"),
            format!("Program {PUMP_PROGRAM_ID} success"),
        ],
        serde_json::Value::Null,
    );

    assert!(parse_pump_realtime_log_notification(&body).is_err());
}
