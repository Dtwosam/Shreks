use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use serde_json::{json, Value};
use shreks_providers::{
    pump::{PUMP_AMM_PROGRAM_ID, PUMP_PROGRAM_ID, WRAPPED_SOL_MINT},
    pump_realtime::parse_pump_realtime_log_notification,
    pump_trade::{
        classify_pump_trade_transaction, PumpTradeVerification, PUMP_BUY_V2_DISCRIMINATOR,
        PUMP_TRADE_EVENT_DISCRIMINATOR,
    },
    pump_swap_trade::{parse_pump_swap_trade_logs, PUMPSWAP_BUY_EVENT_DISCRIMINATOR},
};

const MINT: &str = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump";
const USER: &str = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA";
const POOL: &str = PUMP_AMM_PROGRAM_ID;
const EVENT_TIMESTAMP_SECONDS: i64 = 1_780_000_000;

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

fn pump_trade_program_data() -> String {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&PUMP_TRADE_EVENT_DISCRIMINATOR);
    push_pubkey(&mut bytes, MINT);
    push_u64(&mut bytes, 2_500_000_000); // sol amount
    push_u64(&mut bytes, 500_000_000); // token amount
    push_bool(&mut bytes, true);
    push_pubkey(&mut bytes, USER);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_u64(&mut bytes, 32_000_000_000);
    push_u64(&mut bytes, 900_000_000_000_000);
    push_u64(&mut bytes, 10_000_000_000);
    push_u64(&mut bytes, 600_000_000_000_000);
    push_pubkey(&mut bytes, WRAPPED_SOL_MINT); // fee recipient
    push_u64(&mut bytes, 95); // fee bps
    push_u64(&mut bytes, 23_750_000); // fee raw
    push_pubkey(&mut bytes, PUMP_PROGRAM_ID); // creator
    push_u64(&mut bytes, 30); // creator fee bps
    push_u64(&mut bytes, 7_500_000); // creator fee raw
    push_bool(&mut bytes, true);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 2_500_000_000);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_string(&mut bytes, "buy");
    push_bool(&mut bytes, false);
    push_u64(&mut bytes, 5); // cashback bps
    push_u64(&mut bytes, 1_250_000); // cashback raw
    push_u64(&mut bytes, 7); // buyback bps
    push_u64(&mut bytes, 1_750_000); // buyback raw
    bytes.extend_from_slice(&0_u32.to_le_bytes()); // shareholders
    push_pubkey(&mut bytes, "11111111111111111111111111111111");
    push_u64(&mut bytes, 2_500_000_000);
    push_u64(&mut bytes, 32_000_000_000);
    push_u64(&mut bytes, 10_000_000_000);
    BASE64_STANDARD.encode(bytes)
}

fn pump_transaction(program_data: &str) -> String {
    let instruction_data = bs58::encode(PUMP_BUY_V2_DISCRIMINATOR).into_string();
    json!({
        "jsonrpc": "2.0",
        "result": {
            "slot": 123_u64,
            "blockTime": EVENT_TIMESTAMP_SECONDS,
            "meta": {
                "err": null,
                "logMessages": [
                    format!("Program {PUMP_PROGRAM_ID} invoke [1]"),
                    "Program log: Instruction: BuyV2",
                    format!("Program data: {program_data}"),
                    format!("Program {PUMP_PROGRAM_ID} success")
                ],
                "innerInstructions": []
            },
            "transaction": {"message": {"instructions": [{
                "accounts": [MINT, USER],
                "data": instruction_data,
                "programId": PUMP_PROGRAM_ID
            }]}}
        },
        "id": "fl3-pump-fee-evidence"
    })
    .to_string()
}

fn pumpswap_prefix_bytes() -> Vec<u8> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&PUMPSWAP_BUY_EVENT_DISCRIMINATOR);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_u64(&mut bytes, 500_000_000); // base amount out
    push_u64(&mut bytes, 2_600_000_000); // max quote in
    push_u64(&mut bytes, 1_000_000_000); // user base reserves
    push_u64(&mut bytes, 8_000_000_000); // user quote reserves
    push_u64(&mut bytes, 600_000_000_000_000); // pool base reserves
    push_u64(&mut bytes, 32_000_000_000); // pool quote reserves
    push_u64(&mut bytes, 2_500_000_000); // quote amount in
    push_u64(&mut bytes, 20); // LP fee bps
    push_u64(&mut bytes, 5_000_000); // LP fee raw
    push_u64(&mut bytes, 93); // protocol fee bps
    push_u64(&mut bytes, 23_250_000); // protocol fee raw
    push_u64(&mut bytes, 2_505_000_000); // quote with LP fee
    push_u64(&mut bytes, 2_535_000_000); // user quote amount
    push_pubkey(&mut bytes, POOL);
    push_pubkey(&mut bytes, USER);
    bytes
}

fn pumpswap_current_program_data() -> String {
    let mut bytes = pumpswap_prefix_bytes();
    // Current BuyEvent tail: user token accounts, protocol recipient/account, creator.
    push_pubkey(&mut bytes, WRAPPED_SOL_MINT);
    push_pubkey(&mut bytes, WRAPPED_SOL_MINT);
    push_pubkey(&mut bytes, PUMP_PROGRAM_ID);
    push_pubkey(&mut bytes, PUMP_PROGRAM_ID);
    push_pubkey(&mut bytes, USER);
    push_u64(&mut bytes, 30); // creator fee bps
    push_u64(&mut bytes, 7_500_000); // creator fee raw
    push_bool(&mut bytes, true); // track volume
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 2_535_000_000);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_u64(&mut bytes, 499_000_000); // min base amount out
    push_string(&mut bytes, "buy");
    push_u64(&mut bytes, 5); // cashback bps
    push_u64(&mut bytes, 1_250_000); // cashback raw
    push_u64(&mut bytes, 7); // buyback bps
    push_u64(&mut bytes, 1_750_000); // buyback raw
    push_i128(&mut bytes, 4_000_000_000); // virtual quote reserve
    push_bool(&mut bytes, true); // can boost
    push_u64(&mut bytes, 1_000_000_000_000_000); // base supply
    BASE64_STANDARD.encode(bytes)
}

fn pumpswap_legacy_prefix_program_data() -> String {
    BASE64_STANDARD.encode(pumpswap_prefix_bytes())
}

fn direct_pumpswap_logs(program_data: String) -> Vec<Value> {
    vec![
        Value::String(format!("Program {PUMP_AMM_PROGRAM_ID} invoke [1]")),
        Value::String(format!("Program data: {program_data}")),
        Value::String(format!("Program {PUMP_AMM_PROGRAM_ID} success")),
    ]
}

#[test]
fn pump_trade_preserves_authoritative_fee_evidence_already_present_in_event() {
    let body = pump_transaction(&pump_trade_program_data());
    let PumpTradeVerification::Verified(events) =
        classify_pump_trade_transaction(&body, "fl3-pump").unwrap()
    else {
        panic!("expected verified Pump event");
    };
    let evidence = &events[0];

    assert_eq!(evidence.fee_recipient, WRAPPED_SOL_MINT);
    assert_eq!(evidence.fee_basis_points, 95);
    assert_eq!(evidence.fee_raw, 23_750_000);
    assert_eq!(evidence.creator, PUMP_PROGRAM_ID);
    assert_eq!(evidence.creator_fee_basis_points, 30);
    assert_eq!(evidence.creator_fee_raw, 7_500_000);
    assert_eq!(evidence.cashback_fee_basis_points, 5);
    assert_eq!(evidence.cashback_raw, 1_250_000);
    assert_eq!(evidence.buyback_fee_basis_points, 7);
    assert_eq!(evidence.buyback_fee_raw, 1_750_000);
}

#[test]
fn pumpswap_preserves_stable_prefix_fees_and_current_optional_economics_suffix() {
    let events = parse_pump_swap_trade_logs(&direct_pumpswap_logs(
        pumpswap_current_program_data(),
    ))
    .unwrap();
    let evidence = &events[0];

    assert_eq!(evidence.lp_fee_basis_points, 20);
    assert_eq!(evidence.lp_fee_raw, 5_000_000);
    assert_eq!(evidence.protocol_fee_basis_points, 93);
    assert_eq!(evidence.protocol_fee_raw, 23_250_000);
    assert_eq!(evidence.quote_amount_with_or_without_lp_fee_raw, 2_505_000_000);

    let current = evidence
        .current_economics
        .as_ref()
        .expect("current PumpSwap suffix should be retained");
    assert_eq!(current.coin_creator, USER);
    assert_eq!(current.coin_creator_fee_basis_points, 30);
    assert_eq!(current.coin_creator_fee_raw, 7_500_000);
    assert_eq!(current.cashback_fee_basis_points, 5);
    assert_eq!(current.cashback_raw, 1_250_000);
    assert_eq!(current.buyback_fee_basis_points, 7);
    assert_eq!(current.buyback_fee_raw, 1_750_000);
    assert_eq!(current.virtual_quote_reserves_raw, 4_000_000_000_i128);
    assert!(current.can_boost);
    assert_eq!(current.base_supply_raw, 1_000_000_000_000_000);
}

#[test]
fn pumpswap_legacy_prefix_stays_parseable_and_marks_newer_suffix_unknown() {
    let body = json!({
        "jsonrpc":"2.0",
        "method":"logsNotification",
        "params":{
            "result":{
                "context":{"slot":999_u64},
                "value":{
                    "signature":"legacy-prefix",
                    "err":null,
                    "logs":[
                        format!("Program {PUMP_AMM_PROGRAM_ID} invoke [1]"),
                        format!("Program data: {}", pumpswap_legacy_prefix_program_data()),
                        format!("Program {PUMP_AMM_PROGRAM_ID} success")
                    ]
                }
            },
            "subscription":1
        }
    })
    .to_string();

    let realtime = parse_pump_realtime_log_notification(&body)
        .unwrap()
        .expect("legacy prefix remains relevant");
    let evidence = &realtime.pump_swap_trades[0];
    assert_eq!(evidence.lp_fee_basis_points, 20);
    assert_eq!(evidence.protocol_fee_basis_points, 93);
    assert!(evidence.current_economics.is_none());
}
