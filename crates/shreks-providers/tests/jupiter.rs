use shreks_core::{ProviderId, QuoteRequest};
use shreks_providers::{
    jupiter::{build_url, parse_build_response},
    ProviderErrorKind,
};

fn request() -> QuoteRequest {
    QuoteRequest::new(
        "So11111111111111111111111111111111111111112",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        100_000_000,
        "11111111111111111111111111111111",
        75,
    )
    .expect("valid request")
}

#[test]
fn build_url_uses_current_swap_v2_endpoint() {
    assert_eq!(
        build_url(&request()),
        "https://api.jup.ag/swap/v2/build?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=100000000&taker=11111111111111111111111111111111&slippageBps=75"
    );
}

#[test]
fn parses_quote_and_keeps_route_labels_only() {
    let body = r#"{
      "inputMint":"So11111111111111111111111111111111111111112",
      "outputMint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
      "inAmount":"100000000",
      "outAmount":"17057460",
      "otherAmountThreshold":"16929529",
      "swapMode":"ExactIn",
      "slippageBps":75,
      "priceImpactPct":"0.0012",
      "routePlan":[
        {"swapInfo":{"ammKey":"Amm1","label":"Meteora DLMM","inputMint":"So11111111111111111111111111111111111111112","outputMint":"MidMint","inAmount":"100000000","outAmount":"50000000"},"bps":6000,"usdValue":10.0},
        {"swapInfo":{"ammKey":"Amm2","label":"PumpSwap","inputMint":"MidMint","outputMint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","inAmount":"50000000","outAmount":"17057460"},"bps":4000,"usdValue":7.0}
      ],
      "computeBudgetInstructions":[{"programId":"ComputeBudget111","accounts":[],"data":"secret-instruction-data"}],
      "setupInstructions":[],
      "swapInstruction":{"programId":"Swap111","accounts":[],"data":"raw-swap-data"},
      "cleanupInstruction":null,
      "otherInstructions":[],
      "tipInstruction":null,
      "addressesByLookupTableAddress":{},
      "blockhashWithMetadata":{"blockhash":[1,2,3],"lastValidBlockHeight":123}
    }"#;

    let quote = parse_build_response(body, 1_700_000_000_000).expect("valid build response");
    assert_eq!(quote.provider, ProviderId::Jupiter);
    assert_eq!(quote.input_amount, 100_000_000);
    assert_eq!(quote.output_amount, 17_057_460);
    assert_eq!(quote.minimum_output_amount, 16_929_529);
    assert_eq!(quote.slippage_bps, 75);
    assert_eq!(quote.price_impact_pct.as_deref(), Some("0.0012"));
    assert_eq!(quote.route_labels, vec!["Meteora DLMM", "PumpSwap"]);
    assert!(quote.route_available);
    assert_eq!(quote.quoted_at_unix_ms, 1_700_000_000_000);
}

#[test]
fn duplicate_route_labels_are_deduplicated_in_order() {
    let body = r#"{
      "inputMint":"A","outputMint":"B","inAmount":"10","outAmount":"8",
      "otherAmountThreshold":"7","swapMode":"ExactIn","slippageBps":50,
      "priceImpactPct":"0.01",
      "routePlan":[
        {"swapInfo":{"ammKey":"1","label":"PumpSwap","inputMint":"A","outputMint":"X","inAmount":"10","outAmount":"9"},"bps":5000},
        {"swapInfo":{"ammKey":"2","label":"PumpSwap","inputMint":"X","outputMint":"B","inAmount":"9","outAmount":"8"},"bps":5000}
      ]
    }"#;
    let quote = parse_build_response(body, 1).expect("valid response");
    assert_eq!(quote.route_labels, vec!["PumpSwap"]);
}

#[test]
fn empty_route_is_preserved_as_unavailable_instead_of_inventing_a_route() {
    let body = r#"{
      "inputMint":"A","outputMint":"B","inAmount":"10","outAmount":"0",
      "otherAmountThreshold":"0","swapMode":"ExactIn","slippageBps":50,
      "priceImpactPct":null,"routePlan":[]
    }"#;
    let quote = parse_build_response(body, 1).expect("valid empty route response");
    assert!(!quote.route_available);
    assert!(quote.route_labels.is_empty());
}

#[test]
fn malformed_or_api_error_payload_is_rejected() {
    assert!(parse_build_response("not json", 1).is_err());

    let error = parse_build_response(r#"{"error":"No route found","errorCode":"NO_ROUTE"}"#, 1)
        .expect_err("API error must not become a quote");
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
}
