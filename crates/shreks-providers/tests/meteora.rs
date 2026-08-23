use shreks_core::{ProviderId, VenueId};
use shreks_providers::meteora::{
    damm_v2_pools_url, dlmm_pools_url, parse_pool_page_json,
};

#[test]
fn query_urls_target_official_public_meteora_data_apis() {
    assert_eq!(
        dlmm_pools_url("Mint111"),
        "https://dlmm.datapi.meteora.ag/pools?page=1&page_size=100&query=Mint111"
    );
    assert_eq!(
        damm_v2_pools_url("Mint111"),
        "https://damm-v2.datapi.meteora.ag/pools?page=1&page_size=100&query=Mint111"
    );
}

#[test]
fn parses_dlmm_pool_and_orients_requested_token_as_base() {
    let body = r#"{
      "current_page":1,
      "data":[{
        "address":"PoolDLMM",
        "created_at":1787486400,
        "current_price":0.25,
        "is_blacklisted":false,
        "name":"SHREK-SOL",
        "token_x":{"address":"Mint111","name":"Shrek","symbol":"SHREK","price":0.25,"market_cap":250000.0},
        "token_y":{"address":"So11111111111111111111111111111111111111112","name":"Wrapped SOL","symbol":"SOL","price":150.0,"market_cap":0.0},
        "tvl":25000.0,
        "volume":{"5m":1200.0,"1h":9000.0,"6h":22000.0,"24h":50000.0},
        "launchpad":"dynamic-bonding-curve"
      }],
      "page_size":100,
      "pages":1,
      "total":1
    }"#;

    let pairs = parse_pool_page_json(body, "Mint111", VenueId::MeteoraDlmm, 1_787_486_500_000)
        .expect("valid DLMM fixture");
    assert_eq!(pairs.len(), 1);
    let pair = &pairs[0];
    assert_eq!(pair.provider, ProviderId::Meteora);
    assert_eq!(pair.venue, VenueId::MeteoraDlmm);
    assert_eq!(pair.dex_id, "meteora_dlmm");
    assert_eq!(pair.pair_address, "PoolDLMM");
    assert_eq!(pair.base_mint, "Mint111");
    assert_eq!(pair.quote_mint, "So11111111111111111111111111111111111111112");
    assert_eq!(pair.price_usd.as_deref(), Some("0.25"));
    assert_eq!(pair.liquidity_usd, Some(25_000.0));
    assert_eq!(pair.volume_5m, Some(1_200.0));
    assert_eq!(pair.volume_1h, Some(9_000.0));
    assert_eq!(pair.volume_6h, Some(22_000.0));
    assert_eq!(pair.volume_24h, Some(50_000.0));
    assert_eq!(pair.market_cap_usd, Some(250_000.0));
    assert_eq!(pair.pair_created_at_unix_ms, Some(1_787_486_400_000));
}

#[test]
fn parses_damm_v2_and_can_reverse_token_orientation() {
    let body = r#"{
      "current_page":1,
      "data":[{
        "address":"PoolDAMM",
        "created_at":1787486400,
        "current_price":2.0,
        "is_blacklisted":false,
        "name":"USDC-MEME",
        "token_x":{"address":"USDC111","name":"USD Coin","symbol":"USDC","price":1.0,"market_cap":1000000.0},
        "token_y":{"address":"MintMeme","name":"Meme","symbol":"MEME","price":0.5,"market_cap":500000.0},
        "tvl":75000.0,
        "volume":{"1h":15000.0,"24h":100000.0},
        "launchpad":null
      }],
      "page_size":100,
      "pages":1,
      "total":1
    }"#;

    let pairs = parse_pool_page_json(body, "MintMeme", VenueId::MeteoraDammV2, 42)
        .expect("valid DAMM fixture");
    let pair = &pairs[0];
    assert_eq!(pair.venue, VenueId::MeteoraDammV2);
    assert_eq!(pair.base_mint, "MintMeme");
    assert_eq!(pair.quote_mint, "USDC111");
    assert_eq!(pair.price_usd.as_deref(), Some("0.5"));
    assert_eq!(pair.market_cap_usd, Some(500_000.0));
}

#[test]
fn ignores_pools_that_do_not_contain_requested_token() {
    let body = r#"{
      "current_page":1,
      "data":[{
        "address":"PoolOther",
        "created_at":1,
        "current_price":1.0,
        "is_blacklisted":false,
        "name":"A-B",
        "token_x":{"address":"A"},
        "token_y":{"address":"B"},
        "tvl":1.0,
        "volume":{}
      }],
      "page_size":100,
      "pages":1,
      "total":1
    }"#;

    let pairs = parse_pool_page_json(body, "MintMissing", VenueId::MeteoraDlmm, 1)
        .expect("valid response");
    assert!(pairs.is_empty());
}

#[test]
fn malformed_meteora_payload_is_rejected() {
    assert!(parse_pool_page_json("not json", "Mint", VenueId::MeteoraDlmm, 1).is_err());
}
