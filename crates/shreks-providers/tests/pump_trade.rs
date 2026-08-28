use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use serde_json::json;
use shreks_core::{FastEventKind, ProviderId, VenueId};
use shreks_providers::{
    pump::{PUMP_AMM_PROGRAM_ID, PUMP_PROGRAM_ID, WRAPPED_SOL_MINT},
    pump_trade::{
        classify_pump_trade_transaction, parse_pump_trade_log_notification,
        pump_trade_evidence_to_fast_event, PumpTradeEvidence, PumpTradeVerification,
        PUMP_BUY_DISCRIMINATOR, PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR,
        PUMP_BUY_V2_DISCRIMINATOR, PUMP_SELL_DISCRIMINATOR, PUMP_SELL_V2_DISCRIMINATOR,
        PUMP_TRADE_EVENT_DISCRIMINATOR,
    },
    ProviderErrorKind,
};

const MINT: &str = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump";
const USER: &str = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA";
const DEFAULT_QUOTE_MINT: &str = "11111111111111111111111111111111";
const USDC_MINT: &str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const EVENT_TIMESTAMP_SECONDS: i64 = 1_770_000_000;
const TOKEN_AMOUNT_RAW: u64 = 500_000_000;

fn push_pubkey(output: &mut Vec<u8>, value: &str) {
    let decoded = bs58::decode(value).into_vec().expect("valid fixture pubkey");
    assert_eq!(decoded.len(), 32, "fixture pubkey must decode to 32 bytes");
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
    let len = u32::try_from(value.len()).expect("fixture string length fits u32");
    output.extend_from_slice(&len.to_le_bytes());
    output.extend_from_slice(value.as_bytes());
}

fn trade_event_program_data(
    is_buy: bool,
    quote_mint: &str,
    sol_amount_raw: u64,
    quote_amount_raw: u64,
    ix_name: &str,
) -> String {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&PUMP_TRADE_EVENT_DISCRIMINATOR);
    push_pubkey(&mut bytes, MINT);
    push_u64(&mut bytes, sol_amount_raw);
    push_u64(&mut bytes, TOKEN_AMOUNT_RAW);
    push_bool(&mut bytes, is_buy);
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
    push_u64(&mut bytes, sol_amount_raw);
    push_i64(&mut bytes, EVENT_TIMESTAMP_SECONDS);
    push_string(&mut bytes, ix_name);
    push_bool(&mut bytes, false);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    push_u64(&mut bytes, 0);
    bytes.extend_from_slice(&0_u32.to_le_bytes());
    push_pubkey(&mut bytes, quote_mint);
    push_u64(&mut bytes, quote_amount_raw);
    push_u64(&mut bytes, 32_000_000_000);
    push_u64(&mut bytes, 10_000_000_000);
    BASE64_STANDARD.encode(bytes)
}

fn pump_trade_transaction(
    program_data: &str,
    instruction_program: &str,
    instruction_discriminator: [u8; 8],
    log_program: &str,
) -> String {
    let instruction_data = bs58::encode(instruction_discriminator).into_string();
    json!({
        "jsonrpc": "2.0",
        "result": {
            "slot": 123_u64,
            "blockTime": EVENT_TIMESTAMP_SECONDS,
            "meta": {
                "err": null,
                "logMessages": [
                    format!("Program {log_program} invoke [1]"),
                    "Program log: Instruction: BuyV2",
                    format!("Program data: {program_data}"),
                    format!("Program {log_program} success")
                ],
                "innerInstructions": []
            },
            "transaction": {
                "message": {
                    "instructions": [
                        {
                            "accounts": [MINT, USER],
                            "data": instruction_data,
                            "programId": instruction_program
                        }
                    ]
                }
            }
        },
        "id": "shreks-pump-transaction"
    })
    .to_string()
}

fn verified_evidence(
    is_buy: bool,
    quote_mint: &str,
    sol_amount_raw: u64,
    quote_amount_raw: u64,
    ix_name: &str,
    discriminator: [u8; 8],
) -> PumpTradeEvidence {
    let program_data = trade_event_program_data(
        is_buy,
        quote_mint,
        sol_amount_raw,
        quote_amount_raw,
        ix_name,
    );
    let body = pump_trade_transaction(
        &program_data,
        PUMP_PROGRAM_ID,
        discriminator,
        PUMP_PROGRAM_ID,
    );
    let PumpTradeVerification::Verified(mut events) =
        classify_pump_trade_transaction(&body, "trade-signature").unwrap()
    else {
        panic!("expected verified Pump trade");
    };
    assert_eq!(events.len(), 1);
    events.remove(0)
}

#[test]
fn official_pump_trade_discriminators_are_pinned() {
    assert_eq!(PUMP_BUY_DISCRIMINATOR, [102, 6, 61, 18, 1, 218, 235, 234]);
    assert_eq!(
        PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR,
        [56, 252, 116, 8, 158, 223, 205, 95]
    );
    assert_eq!(
        PUMP_BUY_V2_DISCRIMINATOR,
        [184, 23, 238, 97, 103, 197, 211, 61]
    );
    assert_eq!(PUMP_SELL_DISCRIMINATOR, [51, 230, 133, 164, 1, 127, 131, 173]);
    assert_eq!(
        PUMP_SELL_V2_DISCRIMINATOR,
        [93, 246, 130, 60, 231, 233, 64, 178]
    );
    assert_eq!(
        PUMP_TRADE_EVENT_DISCRIMINATOR,
        [189, 219, 127, 211, 78, 230, 97, 238]
    );
}

#[test]
fn current_trade_event_decodes_actual_economics_and_reserves() {
    let evidence = verified_evidence(
        true,
        DEFAULT_QUOTE_MINT,
        2_500_000_000,
        2_500_000_000,
        "buy",
        PUMP_BUY_V2_DISCRIMINATOR,
    );

    assert_eq!(evidence.mint, MINT);
    assert_eq!(evidence.quote_mint, DEFAULT_QUOTE_MINT);
    assert_eq!(evidence.user, USER);
    assert!(evidence.is_buy);
    assert_eq!(evidence.token_amount_raw, TOKEN_AMOUNT_RAW);
    assert_eq!(evidence.sol_amount_raw, 2_500_000_000);
    assert_eq!(evidence.quote_amount_raw, 2_500_000_000);
    assert_eq!(evidence.timestamp_unix_seconds, EVENT_TIMESTAMP_SECONDS);
    assert_eq!(evidence.virtual_sol_reserves_raw, 32_000_000_000);
    assert_eq!(evidence.virtual_token_reserves_raw, 900_000_000_000_000);
    assert_eq!(evidence.real_sol_reserves_raw, 10_000_000_000);
    assert_eq!(evidence.real_token_reserves_raw, 600_000_000_000_000);
    assert_eq!(evidence.virtual_quote_reserves_raw, 32_000_000_000);
    assert_eq!(evidence.real_quote_reserves_raw, 10_000_000_000);
    assert_eq!(evidence.ix_name, "buy");
}

#[test]
fn trade_transaction_pending_and_failed_states_are_not_misclassified() {
    let pending = r#"{"jsonrpc":"2.0","result":null,"id":"shreks-pump-transaction"}"#;
    assert_eq!(
        classify_pump_trade_transaction(pending, "pending").unwrap(),
        PumpTradeVerification::Pending
    );

    let program_data = trade_event_program_data(
        true,
        DEFAULT_QUOTE_MINT,
        1_000_000_000,
        1_000_000_000,
        "buy",
    );
    let failed = pump_trade_transaction(
        &program_data,
        PUMP_PROGRAM_ID,
        PUMP_BUY_DISCRIMINATOR,
        PUMP_PROGRAM_ID,
    )
    .replace("\"err\":null", "\"err\":{\"InstructionError\":[0,1]}");
    let outcome = classify_pump_trade_transaction(&failed, "failed").unwrap();
    assert!(matches!(outcome, PumpTradeVerification::Rejected(_)));
}

#[test]
fn matching_program_data_from_non_pump_program_is_not_economic_evidence() {
    let program_data = trade_event_program_data(
        true,
        DEFAULT_QUOTE_MINT,
        1_000_000_000,
        1_000_000_000,
        "buy",
    );
    let body = pump_trade_transaction(
        &program_data,
        PUMP_PROGRAM_ID,
        PUMP_BUY_DISCRIMINATOR,
        PUMP_AMM_PROGRAM_ID,
    );
    let outcome = classify_pump_trade_transaction(&body, "spoofed-log").unwrap();
    assert!(matches!(outcome, PumpTradeVerification::Rejected(_)));
}

#[test]
fn trade_event_without_real_pump_trade_instruction_is_rejected() {
    let program_data = trade_event_program_data(
        true,
        DEFAULT_QUOTE_MINT,
        1_000_000_000,
        1_000_000_000,
        "buy",
    );
    let body = pump_trade_transaction(
        &program_data,
        PUMP_AMM_PROGRAM_ID,
        PUMP_BUY_DISCRIMINATOR,
        PUMP_PROGRAM_ID,
    );
    let outcome = classify_pump_trade_transaction(&body, "missing-trade-ix").unwrap();
    assert!(matches!(outcome, PumpTradeVerification::Rejected(_)));
}

#[test]
fn malformed_pump_trade_event_is_provider_error() {
    let malformed = BASE64_STANDARD.encode([
        PUMP_TRADE_EVENT_DISCRIMINATOR.as_slice(),
        &[1_u8, 2_u8, 3_u8],
    ]
    .concat());
    let body = pump_trade_transaction(
        &malformed,
        PUMP_PROGRAM_ID,
        PUMP_BUY_DISCRIMINATOR,
        PUMP_PROGRAM_ID,
    );
    let error = classify_pump_trade_transaction(&body, "malformed").unwrap_err();
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
}

#[test]
fn pump_trade_evidence_converts_to_sol_fast_event_only_with_supplied_decimals() {
    let evidence = verified_evidence(
        true,
        DEFAULT_QUOTE_MINT,
        2_500_000_000,
        2_500_000_000,
        "buy",
        PUMP_BUY_V2_DISCRIMINATOR,
    );

    let event = pump_trade_evidence_to_fast_event(
        &evidence,
        "trade-signature",
        7,
        99,
        123,
        1_770_000_000_250,
        6,
        9,
    )
    .unwrap();

    assert_eq!(event.id.signature, "trade-signature");
    assert_eq!(event.id.ordinal, 7);
    assert_eq!(event.sequence, 99);
    assert_eq!(event.provider, ProviderId::Helius);
    assert_eq!(event.market.mint, MINT);
    assert_eq!(event.market.quote_mint, WRAPPED_SOL_MINT);
    assert_eq!(event.market.venue, VenueId::PumpFunBondingCurve);
    assert_eq!(event.kind, FastEventKind::Buy);
    assert_eq!(event.actor.as_deref(), Some(USER));
    assert_eq!(event.slot, 123);
    assert_eq!(event.occurred_at_unix_ms, 1_770_000_000_000);
    assert_eq!(event.observed_at_unix_ms, 1_770_000_000_250);
    assert!((event.base_quantity - 500.0).abs() < 1e-12);
    assert!((event.quote_quantity - 2.5).abs() < 1e-12);
    assert!((event.price_quote - 0.005).abs() < 1e-12);
}

#[test]
fn non_sol_quote_fast_event_uses_quote_amount_and_quote_decimals() {
    let evidence = verified_evidence(
        false,
        USDC_MINT,
        0,
        1_250_000_000,
        "sell",
        PUMP_SELL_V2_DISCRIMINATOR,
    );

    let event = pump_trade_evidence_to_fast_event(
        &evidence,
        "usdc-sell",
        0,
        100,
        124,
        1_770_000_000_500,
        6,
        6,
    )
    .unwrap();

    assert_eq!(event.market.quote_mint, USDC_MINT);
    assert_eq!(event.kind, FastEventKind::Sell);
    assert!((event.base_quantity - 500.0).abs() < 1e-12);
    assert!((event.quote_quantity - 1_250.0).abs() < 1e-12);
    assert!((event.price_quote - 2.5).abs() < 1e-12);
}

#[test]
fn invalid_economic_quantity_and_impossible_observation_time_fail_closed() {
    let mut evidence = verified_evidence(
        true,
        DEFAULT_QUOTE_MINT,
        1_000_000_000,
        1_000_000_000,
        "buy",
        PUMP_BUY_DISCRIMINATOR,
    );
    evidence.token_amount_raw = 0;
    let error = pump_trade_evidence_to_fast_event(
        &evidence,
        "zero",
        0,
        1,
        123,
        1_770_000_000_100,
        6,
        9,
    )
    .unwrap_err();
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);

    evidence.token_amount_raw = TOKEN_AMOUNT_RAW;
    let error = pump_trade_evidence_to_fast_event(
        &evidence,
        "early",
        0,
        2,
        123,
        1_769_999_999_999,
        6,
        9,
    )
    .unwrap_err();
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
}

#[test]
fn exact_trade_instruction_logs_are_cheap_signals_only() {
    let body = json!({
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": 555},
                "value": {
                    "signature": "trade-signal",
                    "err": null,
                    "logs": [
                        format!("Program {PUMP_PROGRAM_ID} invoke [1]"),
                        "Program log: Instruction: BuyV2"
                    ]
                }
            },
            "subscription": 7
        }
    })
    .to_string();

    let signal = parse_pump_trade_log_notification(&body).unwrap().unwrap();
    assert_eq!(signal.signature, "trade-signal");
    assert_eq!(signal.slot, 555);

    let sell = body.replace("BuyV2", "SellV2");
    assert!(parse_pump_trade_log_notification(&sell).unwrap().is_some());

    let spoof = body.replace("BuyV2", "BuyV2Fake");
    assert!(parse_pump_trade_log_notification(&spoof).unwrap().is_none());

    let failed = body.replace("\"err\":null", "\"err\":{\"InstructionError\":[0,1]}");
    assert!(parse_pump_trade_log_notification(&failed).unwrap().is_none());
}
