use shreks_core::ProviderId;
use shreks_providers::{
    solana_rpc::{chainstack_http_url, parse_mint_account_response_for_provider},
    ProviderErrorKind,
};

#[test]
fn derives_chainstack_https_rpc_url_from_protected_websocket_endpoint() {
    let url = chainstack_http_url(
        "wss://solana-mainnet.core.chainstack.com/fixture-chainstack-key",
    )
    .expect("valid Chainstack WSS endpoint");

    assert_eq!(
        url,
        "https://solana-mainnet.core.chainstack.com/fixture-chainstack-key"
    );

    let error = chainstack_http_url("https://example.invalid/not-websocket")
        .expect_err("non-websocket endpoint must fail");
    assert_eq!(error.provider, ProviderId::Chainstack);
    assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
}

#[test]
fn parses_standard_mint_state_with_chainstack_provenance() {
    let body = r#"{
      "jsonrpc":"2.0",
      "id":"shreks-mint-state",
      "result":{
        "context":{"slot":442600000},
        "value":{
          "data":{
            "program":"spl-token",
            "parsed":{
              "type":"mint",
              "info":{
                "decimals":6,
                "freezeAuthority":null,
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

    let state = parse_mint_account_response_for_provider(
        ProviderId::Chainstack,
        body,
        "Mint111",
        1_788_000_000_000,
    )
    .expect("valid standard Solana mint response");

    assert_eq!(state.provider, ProviderId::Chainstack);
    assert_eq!(state.mint, "Mint111");
    assert_eq!(state.decimals, 6);
    assert_eq!(state.slot, 442_600_000);
    assert_eq!(state.observed_at_unix_ms, 1_788_000_000_000);
}
