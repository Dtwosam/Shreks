use shreks_core::ProviderId;
use shreks_providers::dexscreener::{parse_discovery_json, parse_token_pairs_json, token_pairs_url};

#[test]
fn token_pairs_url_is_solanas_public_endpoint() {
    assert_eq!(
        token_pairs_url("Mint111"),
        "https://api.dexscreener.com/token-pairs/v1/solana/Mint111"
    );
}

#[test]
fn parses_pair_market_data_into_shreks_types() {
    let body = r#"[
      {
        "chainId":"solana",
        "dexId":"pumpfun",
        "pairAddress":"Pair111",
        "baseToken":{"address":"Mint111","name":"Shrek","symbol":"SHREK"},
        "quoteToken":{"address":"So11111111111111111111111111111111111111112","name":"Wrapped SOL","symbol":"SOL"},
        "priceNative":"0.00123",
        "priceUsd":"0.25",
        "txns":{"m5":{"buys":11,"sells":4},"h1":{"buys":90,"sells":50}},
        "volume":{"m5":1200.5,"h1":9000.0,"h6":22000.0,"h24":50000.0},
        "liquidity":{"usd":25000.0,"base":100000.0,"quote":25.0},
        "fdv":250000.0,
        "marketCap":200000.0,
        "pairCreatedAt":1787486400000
      }
    ]"#;

    let pairs = parse_token_pairs_json(body, 1_787_486_500_000).expect("valid fixture");
    assert_eq!(pairs.len(), 1);

    let pair = &pairs[0];
    assert_eq!(pair.provider, ProviderId::DexScreener);
    assert_eq!(pair.chain_id, "solana");
    assert_eq!(pair.dex_id, "pumpfun");
    assert_eq!(pair.pair_address, "Pair111");
    assert_eq!(pair.base_mint, "Mint111");
    assert_eq!(pair.base_symbol.as_deref(), Some("SHREK"));
    assert_eq!(pair.price_usd.as_deref(), Some("0.25"));
    assert_eq!(pair.liquidity_usd, Some(25_000.0));
    assert_eq!(pair.volume_5m, Some(1_200.5));
    assert_eq!(pair.volume_24h, Some(50_000.0));
    assert_eq!(pair.transactions.len(), 2);
    assert_eq!(pair.fdv_usd, Some(250_000.0));
    assert_eq!(pair.market_cap_usd, Some(200_000.0));
    assert_eq!(pair.pair_created_at_unix_ms, Some(1_787_486_400_000));
    assert_eq!(pair.observed_at_unix_ms, 1_787_486_500_000);
}

#[test]
fn optional_market_fields_can_be_absent() {
    let body = r#"[{
      "chainId":"solana",
      "dexId":"unknown",
      "pairAddress":"Pair222",
      "baseToken":{"address":"Mint222"},
      "quoteToken":{"address":"Quote222"},
      "priceNative":"1"
    }]"#;

    let pairs = parse_token_pairs_json(body, 99).expect("valid sparse pair");
    let pair = &pairs[0];
    assert_eq!(pair.price_usd, None);
    assert_eq!(pair.liquidity_usd, None);
    assert!(pair.transactions.is_empty());
}

#[test]
fn malformed_pair_payload_is_rejected() {
    assert!(parse_token_pairs_json("{not-json", 1).is_err());
}

#[test]
fn discovery_parser_keeps_only_solana_and_deduplicates_mints() {
    let body = r#"[
      {"chainId":"solana","tokenAddress":"MintA"},
      {"chainId":"ethereum","tokenAddress":"0xabc"},
      {"chainId":"solana","tokenAddress":"MintA"},
      {"chainId":"solana","tokenAddress":"MintB"}
    ]"#;

    let discovered = parse_discovery_json(body, 123).expect("valid discovery fixture");
    assert_eq!(discovered.len(), 2);
    assert_eq!(discovered[0].mint, "MintA");
    assert_eq!(discovered[1].mint, "MintB");
    assert!(discovered.iter().all(|item| item.source == ProviderId::DexScreener));
}
