use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use serde_json::json;
use shreks_providers::{
    pump::{PUMP_AMM_PROGRAM_ID, PUMP_PROGRAM_ID, WRAPPED_SOL_MINT},
    pump_realtime::parse_pump_realtime_log_notification,
};

const BUY_EVENT_DISCRIMINATOR: [u8; 8] = [103, 244, 82, 31, 44, 245, 119, 119];
const SELL_EVENT_DISCRIMINATOR: [u8; 8] = [62, 47, 55, 10, 165, 3, 220, 42];
const POOL: &str = PUMP_AMM_PROGRAM_ID;
const USER: &str = PUMP_PROGRAM_ID;
const EVENT_TIMESTAMP_SECONDS: i64 = 1_777_000_000;

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

fn push_i128(output: &mut Vec<u8>, value: i128) {
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

fn push_common_pubkey_tail(output: &mut Vec<u8>) {
    push_pubkey(output, WRAPPED_SOL_MINT);
    push_pubkey(output, WRAPPED_SOL_MINT);
    push_pubkey(output, PUMP_PROGRAM_ID);
    push_pubkey(output, PUMP_PROGRAM_ID);
    push_pubkey(output, USER);
}

fn buy_event_program_data() -> String {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&BUY_EVENT_DISCRIMINATOR);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_u64(&mut bytes, 500_000_000); // base_amount_out
    push_u64(&mut bytes, 2_600_000_000); // max_quote_amount_in
    push_u64(&mut bytes, 1_000_000_000);
    push_u64(&mut bytes, 8_000_000_000);
    push_u64(&mut bytes, 600_000_000_000_000);
    push_u64(&mut bytes, 32_000_000_000);
    push_u64(&mut bytes, 2_500_000_000); // quote_amount_in
    push_u64(&mut bytes, 20);
    push_u64(&mut bytes, 5_000_000);
    push_u64(&mut bytes, 100);
    push_u64(&mut bytes, 25_000_000);
    push_u64(&mut bytes, 2_505_000_000);
    push_u64(&mut bytes, 2_530_000_000); // user_quote_amount_in
    push_pubkey(&mut bytes, POOL);
    push_pubkey(&mut bytes, USER);
    push_common_pubkey_tail(&mut bytes);
    push_u64(&mut bytes, 50);
    push_u64(&mut bytes, 12_500_000);
    push_bool(&mut bytes, true);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 2_530_000_000);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_u64(&mut bytes, 499_000_000);
    push_string(&mut bytes, "buy");
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_i128(&mut bytes, 0);
    push_bool(&mut bytes, false);
    push_u64(&mut bytes, 1_000_000_000_000_000);
    BASE64_STANDARD.encode(bytes)
}

fn sell_event_program_data() -> String {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&SELL_EVENT_DISCRIMINATOR);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS + 1);
    push_u64(&mut bytes, 250_000_000); // base_amount_in
    push_u64(&mut bytes, 1_100_000_000); // min_quote_amount_out
    push_u64(&mut bytes, 750_000_000);
    push_u64(&mut bytes, 9_200_000_000);
    push_u64(&mut bytes, 600_250_000_000_000);
    push_u64(&mut bytes, 30_800_000_000);
    push_u64(&mut bytes, 1_250_000_000); // quote_amount_out
    push_u64(&mut bytes, 20);
    push_u64(&mut bytes, 2_500_000);
    push_u64(&mut bytes, 100);
    push_u64(&mut bytes, 12_500_000);
    push_u64(&mut bytes, 1_247_500_000);
    push_u64(&mut bytes, 1_235_000_000); // user_quote_amount_out
    push_pubkey(&mut bytes, POOL);
    push_pubkey(&mut bytes, USER);
    push_common_pubkey_tail(&mut bytes);
    push_u64(&mut bytes, 50);
    push_u64(&mut bytes, 6_250_000);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_i128(&mut bytes, 0);
    push_bool(&mut bytes, false);
    push_u64(&mut bytes, 1_000_000_000_000_000);
    BASE64_STANDARD.encode(bytes)
}

fn notification(logs: Vec<String>) -> String {
    json!({
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": 888_u64},
                "value": {
                    "signature": "pumpswap-signature",
                    "err": null,
                    "logs": logs
                }
            },
            "subscription": 24041
        }
    })
    .to_string()
}

#[test]
fn pumpswap_buy_and_sell_events_are_decoded_from_direct_logs() {
    let body = notification(vec![
        format!("Program {PUMP_AMM_PROGRAM_ID} invoke [1]"),
        "Program log: Instruction: Buy".to_owned(),
        format!("Program data: {}", buy_event_program_data()),
        "Program log: Instruction: Sell".to_owned(),
        format!("Program data: {}", sell_event_program_data()),
        format!("Program {PUMP_AMM_PROGRAM_ID} success"),
    ]);

    let realtime = parse_pump_realtime_log_notification(&body)
        .expect("valid PumpSwap realtime notification")
        .expect("PumpSwap trade notification must be relevant");

    assert!(realtime.lifecycle.is_none());
    assert!(realtime.trades.is_empty());
    assert_eq!(realtime.pump_swap_trades.len(), 2);

    let buy = &realtime.pump_swap_trades[0];
    assert!(buy.is_buy);
    assert_eq!(buy.log_index, 2);
    assert_eq!(buy.pool, POOL);
    assert_eq!(buy.user, USER);
    assert_eq!(buy.base_amount_raw, 500_000_000);
    assert_eq!(buy.quote_amount_raw, 2_500_000_000);
    assert_eq!(buy.user_quote_amount_raw, 2_530_000_000);
    assert_eq!(buy.pool_base_reserves_raw, 600_000_000_000_000);
    assert_eq!(buy.pool_quote_reserves_raw, 32_000_000_000);
    assert_eq!(buy.timestamp_unix_seconds, EVENT_TIMESTAMP_SECONDS);

    let sell = &realtime.pump_swap_trades[1];
    assert!(!sell.is_buy);
    assert_eq!(sell.log_index, 4);
    assert_eq!(sell.base_amount_raw, 250_000_000);
    assert_eq!(sell.quote_amount_raw, 1_250_000_000);
    assert_eq!(sell.user_quote_amount_raw, 1_235_000_000);
    assert_eq!(sell.timestamp_unix_seconds, EVENT_TIMESTAMP_SECONDS + 1);
}

#[test]
fn pumpswap_program_data_under_another_program_is_ignored() {
    let spoof_program = "11111111111111111111111111111111";
    let body = notification(vec![
        format!("Program {spoof_program} invoke [1]"),
        "Program log: Instruction: Buy".to_owned(),
        format!("Program data: {}", buy_event_program_data()),
        format!("Program {spoof_program} success"),
    ]);

    assert!(parse_pump_realtime_log_notification(&body).unwrap().is_none());
}

#[test]
fn malformed_pumpswap_trade_event_fails_closed() {
    let malformed = BASE64_STANDARD.encode([
        BUY_EVENT_DISCRIMINATOR.as_slice(),
        &[1_u8, 2_u8, 3_u8],
    ]
    .concat());
    let body = notification(vec![
        format!("Program {PUMP_AMM_PROGRAM_ID} invoke [1]"),
        "Program log: Instruction: Buy".to_owned(),
        format!("Program data: {malformed}"),
        format!("Program {PUMP_AMM_PROGRAM_ID} success"),
    ]);

    assert!(parse_pump_realtime_log_notification(&body).is_err());
}
