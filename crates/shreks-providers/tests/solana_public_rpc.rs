use std::time::Duration;

use shreks_core::ProviderId;
use shreks_providers::{
    solana_rpc::{
        annotate_transaction_response_for_provider, parse_mint_account_response_for_provider,
        StandardSolanaRpcProvider, SOLANA_PUBLIC_RPC_INTERVAL,
    },
    ChainDataProvider,
};

#[test]
fn solana_public_constructor_has_truthful_identity_redacted_endpoint_and_four_rps_ceiling() {
    let provider = StandardSolanaRpcProvider::solana_public()
        .expect("official Solana public RPC configuration must be valid");

    assert_eq!(ChainDataProvider::provider_id(&provider), ProviderId::SolanaPublic);
    assert!(SOLANA_PUBLIC_RPC_INTERVAL >= Duration::from_millis(250));

    let debug = format!("{provider:?}");
    assert!(debug.contains("SolanaPublic"));
    assert!(debug.contains("<redacted>"));
    assert!(!debug.contains("api.mainnet.solana.com"));
}

#[test]
fn standard_mint_parser_preserves_solana_public_provenance() {
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
        ProviderId::SolanaPublic,
        body,
        "Mint111",
        1_788_000_000_000,
    )
    .expect("valid public standard Solana mint response");

    assert_eq!(state.provider, ProviderId::SolanaPublic);
    assert_eq!(state.mint, "Mint111");
    assert_eq!(state.decimals, 6);
    assert_eq!(state.slot, 442_600_000);
}

#[test]
fn transaction_annotation_uses_solana_public_provider_marker() {
    let annotated = annotate_transaction_response_for_provider(
        ProviderId::SolanaPublic,
        r#"{"jsonrpc":"2.0","id":"shreks-pump-transaction","result":null}"#,
    )
    .expect("valid JSON-RPC response");

    let value: serde_json::Value = serde_json::from_str(&annotated).unwrap();
    assert_eq!(
        value["_shreks_transport_provider"],
        serde_json::Value::String("solana_public".to_owned())
    );
}
