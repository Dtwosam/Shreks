use shreks_core::ProviderId;
use shreks_providers::{
    helius::{
        get_transaction_request, helius_rpc_url, parse_mint_account_response,
    },
    ProviderErrorKind,
};

#[test]
fn builds_mainnet_rpc_url_without_mutating_key() {
    assert_eq!(
        helius_rpc_url("test-key"),
        "https://mainnet.helius-rpc.com/?api-key=test-key"
    );
}

#[test]
fn get_transaction_request_uses_current_object_form_and_json_parsed_encoding() {
    let request = get_transaction_request("signature111").expect("valid signature");

    assert_eq!(request["jsonrpc"], "2.0");
    assert_eq!(request["method"], "getTransaction");
    assert_eq!(request["params"][0], "signature111");
    assert_eq!(request["params"][1]["commitment"], "confirmed");
    assert_eq!(request["params"][1]["encoding"], "jsonParsed");
    assert_eq!(request["params"][1]["maxSupportedTransactionVersion"], 0);
}

#[test]
fn get_transaction_request_rejects_blank_signature() {
    let error = get_transaction_request("   ").expect_err("blank signature must fail");
    assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
}

#[test]
fn parses_json_parsed_spl_mint_state() {
    let body = r#"{
      "jsonrpc":"2.0",
      "id":"1",
      "result":{
        "context":{"slot":123456789},
        "value":{
          "data":{
            "program":"spl-token",
            "parsed":{
              "type":"mint",
              "info":{
                "decimals":6,
                "freezeAuthority":"Freeze111",
                "isInitialized":true,
                "mintAuthority":"MintAuth111",
                "supply":"1000000000"
              }
            },
            "space":82
          },
          "executable":false,
          "lamports":1461600,
          "owner":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
          "rentEpoch":1,
          "space":82
        }
      }
    }"#;

    let mint = parse_mint_account_response(body, "Mint111", 1_700_000_000_000)
        .expect("valid mint response");
    assert_eq!(mint.provider, ProviderId::Helius);
    assert_eq!(mint.mint, "Mint111");
    assert_eq!(mint.owner_program, "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
    assert_eq!(mint.supply, 1_000_000_000);
    assert_eq!(mint.decimals, 6);
    assert_eq!(mint.mint_authority.as_deref(), Some("MintAuth111"));
    assert_eq!(mint.freeze_authority.as_deref(), Some("Freeze111"));
    assert_eq!(mint.slot, 123_456_789);
    assert_eq!(mint.observed_at_unix_ms, 1_700_000_000_000);
}

#[test]
fn fixed_supply_and_no_freeze_authority_parse_as_none() {
    let body = r#"{
      "jsonrpc":"2.0","id":"1",
      "result":{"context":{"slot":9},"value":{
        "data":{"program":"spl-token-2022","parsed":{"type":"mint","info":{
          "decimals":9,"freezeAuthority":null,"isInitialized":true,
          "mintAuthority":null,"supply":"42"
        }},"space":82},
        "executable":false,"lamports":1,
        "owner":"TokenzQdBNbLqP5VEhdkAS6EPFLC1PHn7gcJYhHnD",
        "rentEpoch":1,"space":82
      }}
    }"#;

    let mint = parse_mint_account_response(body, "Mint222", 7).expect("valid token-2022 mint");
    assert_eq!(mint.mint_authority, None);
    assert_eq!(mint.freeze_authority, None);
    assert_eq!(mint.decimals, 9);
}

#[test]
fn missing_account_is_not_found() {
    let body = r#"{"jsonrpc":"2.0","id":"1","result":{"context":{"slot":1},"value":null}}"#;
    let error = parse_mint_account_response(body, "MissingMint", 1).expect_err("must fail");
    assert_eq!(error.kind, ProviderErrorKind::NotFound);
}

#[test]
fn rpc_error_is_classified_without_guessing_mint_state() {
    let body = r#"{"jsonrpc":"2.0","id":"1","error":{"code":-32602,"message":"Invalid params"}}"#;
    let error = parse_mint_account_response(body, "BadMint", 1).expect_err("must fail");
    assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
}

#[test]
fn non_mint_or_malformed_parsed_data_is_rejected() {
    let body = r#"{
      "jsonrpc":"2.0","id":"1",
      "result":{"context":{"slot":1},"value":{
        "data":{"program":"spl-token","parsed":{"type":"account","info":{}},"space":165},
        "executable":false,"lamports":1,"owner":"TokenProgram","rentEpoch":1,"space":165
      }}
    }"#;
    let error = parse_mint_account_response(body, "NotMint", 1).expect_err("must reject account");
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
    assert!(parse_mint_account_response("not json", "Mint", 1).is_err());
}
