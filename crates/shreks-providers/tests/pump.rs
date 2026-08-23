use std::time::Duration;

use shreks_core::{ProviderId, VenueId};
use shreks_providers::{
    pump::{
        classify_pump_creation_transaction, parse_pump_creation_transaction,
        parse_pump_log_notification, parse_pump_subscription_ack, pump_logs_subscribe_request,
        pump_reconnect_delay, PumpCreationVerification, PUMP_AMM_PROGRAM_ID,
        PUMP_CREATE_DISCRIMINATOR, PUMP_CREATE_V2_DISCRIMINATOR, PUMP_PROGRAM_ID,
    },
    ProviderErrorKind,
};

const MINT: &str = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump";

fn transaction_body(program_id: &str, discriminator: [u8; 8]) -> String {
    let data = bs58::encode(discriminator).into_string();
    format!(
        r#"{{
            "jsonrpc":"2.0",
            "result":{{
                "slot":123,
                "blockTime":1770000000,
                "meta":{{"err":null}},
                "transaction":{{
                    "message":{{
                        "instructions":[
                            {{
                                "accounts":["{MINT}","mint-authority","bonding-curve","other"],
                                "data":"{data}",
                                "programId":"{program_id}"
                            }}
                        ]
                    }}
                }}
            }},
            "id":1
        }}"#
    )
}

#[test]
fn official_pump_program_ids_are_stable() {
    assert_eq!(
        PUMP_PROGRAM_ID,
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    );
    assert_eq!(
        PUMP_AMM_PROGRAM_ID,
        "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    );
}

#[test]
fn standard_logs_subscription_mentions_only_pump_at_confirmed_commitment() {
    let request = pump_logs_subscribe_request();

    assert_eq!(request["jsonrpc"], "2.0");
    assert_eq!(request["id"], 1);
    assert_eq!(request["method"], "logsSubscribe");
    assert_eq!(request["params"][0]["mentions"][0], PUMP_PROGRAM_ID);
    assert_eq!(request["params"][0]["mentions"].as_array().unwrap().len(), 1);
    assert_eq!(request["params"][1]["commitment"], "confirmed");
}

#[test]
fn subscription_ack_is_parsed_without_confusing_notifications_for_acks() {
    let ack = r#"{"jsonrpc":"2.0","result":24040,"id":1}"#;
    assert_eq!(parse_pump_subscription_ack(ack).unwrap(), Some(24040));

    let notification = r#"{"jsonrpc":"2.0","method":"logsNotification","params":{}}"#;
    assert_eq!(parse_pump_subscription_ack(notification).unwrap(), None);

    let rejected = r#"{"jsonrpc":"2.0","error":{"code":-32602,"message":"Invalid params"},"id":1}"#;
    let error = parse_pump_subscription_ack(rejected).unwrap_err();
    assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
}

#[test]
fn reconnect_backoff_is_exponential_but_capped() {
    assert_eq!(pump_reconnect_delay(0), Duration::from_secs(1));
    assert_eq!(pump_reconnect_delay(1), Duration::from_secs(2));
    assert_eq!(pump_reconnect_delay(2), Duration::from_secs(4));
    assert_eq!(pump_reconnect_delay(4), Duration::from_secs(16));
    assert_eq!(pump_reconnect_delay(5), Duration::from_secs(30));
    assert_eq!(pump_reconnect_delay(12), Duration::from_secs(30));
}

#[test]
fn create_v2_log_notification_emits_only_successful_creation_signals() {
    let create = r#"{
        "jsonrpc":"2.0",
        "method":"logsNotification",
        "params":{
            "result":{
                "context":{"slot":42},
                "value":{
                    "signature":"launch-signature",
                    "err":null,
                    "logs":[
                        "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]",
                        "Program log: Instruction: CreateV2"
                    ]
                }
            },
            "subscription":7
        }
    }"#;
    let signal = parse_pump_log_notification(create).unwrap().unwrap();
    assert_eq!(signal.signature, "launch-signature");
    assert_eq!(signal.slot, 42);

    let buy = create.replace("CreateV2", "BuyV2");
    assert!(parse_pump_log_notification(&buy).unwrap().is_none());

    let failed = create.replace("\"err\":null", "\"err\":{\"InstructionError\":[0,1]}");
    assert!(parse_pump_log_notification(&failed).unwrap().is_none());
}

#[test]
fn transaction_not_available_yet_is_pending_instead_of_rejected() {
    let body = r#"{"jsonrpc":"2.0","result":null,"id":"shreks-pump-transaction"}"#;
    let outcome = classify_pump_creation_transaction(&body, "launch-signature", 123).unwrap();
    assert_eq!(outcome, PumpCreationVerification::Pending);
}

#[test]
fn fetched_non_creation_transaction_is_terminally_rejected() {
    let spoofed = transaction_body(PUMP_AMM_PROGRAM_ID, PUMP_CREATE_V2_DISCRIMINATOR);
    let outcome = classify_pump_creation_transaction(&spoofed, "spoof", 123).unwrap();

    match outcome {
        PumpCreationVerification::Rejected(reason) => {
            assert!(reason.contains("no verified Create/CreateV2"));
        }
        other => panic!("expected rejected outcome, got {other:?}"),
    }
}

#[test]
fn malformed_transaction_response_is_provider_error_not_token_rejection() {
    let error = classify_pump_creation_transaction("not-json", "launch-signature", 123)
        .unwrap_err();
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
}

#[test]
fn create_v2_transaction_extracts_first_pump_account_as_new_mint() {
    let body = transaction_body(PUMP_PROGRAM_ID, PUMP_CREATE_V2_DISCRIMINATOR);
    let outcome = classify_pump_creation_transaction(
        &body,
        "launch-signature",
        1_770_000_000_123,
    )
    .unwrap();
    let PumpCreationVerification::Verified(candidate) = outcome else {
        panic!("expected verified Pump creation");
    };

    assert_eq!(candidate.mint, MINT);
    assert_eq!(candidate.source, ProviderId::Helius);
    assert_eq!(candidate.venue, Some(VenueId::PumpFunBondingCurve));
    assert_eq!(candidate.dex_id.as_deref(), Some("pumpfun"));
    assert_eq!(candidate.pair_address, None);
    assert_eq!(candidate.discovered_at_unix_ms, 1_770_000_000_123);

    let legacy_api =
        parse_pump_creation_transaction(&body, "launch-signature", 1_770_000_000_123).unwrap();
    assert_eq!(legacy_api.mint, MINT);
}

#[test]
fn legacy_create_is_still_recognized_while_it_remains_onchain() {
    let body = transaction_body(PUMP_PROGRAM_ID, PUMP_CREATE_DISCRIMINATOR);
    let candidate = parse_pump_creation_transaction(&body, "legacy", 123).unwrap();
    assert_eq!(candidate.mint, MINT);
}

#[test]
fn spoofed_program_or_missing_create_instruction_is_rejected() {
    let spoofed = transaction_body(PUMP_AMM_PROGRAM_ID, PUMP_CREATE_V2_DISCRIMINATOR);
    let error = parse_pump_creation_transaction(&spoofed, "spoof", 123).unwrap_err();
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);

    let buy = transaction_body(PUMP_PROGRAM_ID, [102, 6, 61, 18, 1, 218, 235, 234]);
    let error = parse_pump_creation_transaction(&buy, "buy", 123).unwrap_err();
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
}
