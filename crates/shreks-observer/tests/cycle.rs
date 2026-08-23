use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, TokenMintState, TransactionWindow, VenueId,
};
use shreks_observer::Observer;
use shreks_providers::{
    ChainDataProvider, DiscoveryProvider, MarketDataProvider, ProviderError, ProviderErrorKind,
};
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-observer-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate() -> DiscoveredToken {
    DiscoveredToken {
        mint: "mint-a".to_owned(),
        pair_address: Some("pump-pair-a".to_owned()),
        dex_id: Some("pumpswap".to_owned()),
        venue: Some(VenueId::PumpSwap),
        discovered_at_unix_ms: 10,
        source: ProviderId::DexScreener,
    }
}

fn market_snapshot() -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pumpswap".to_owned(),
        pair_address: "pump-pair-a".to_owned(),
        base_mint: "mint-a".to_owned(),
        base_name: Some("Token A".to_owned()),
        base_symbol: Some("TKA".to_owned()),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: Some("Wrapped SOL".to_owned()),
        quote_symbol: Some("SOL".to_owned()),
        price_native: Some("0.002".to_owned()),
        price_usd: Some("0.33".to_owned()),
        liquidity_usd: Some(90_000.0),
        volume_5m: Some(8_000.0),
        volume_1h: Some(42_000.0),
        volume_6h: Some(110_000.0),
        volume_24h: Some(300_000.0),
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 41,
            sells: 17,
        }],
        fdv_usd: Some(330_000.0),
        market_cap_usd: Some(300_000.0),
        pair_created_at_unix_ms: Some(5),
        observed_at_unix_ms: 100,
    }
}

fn mint_state() -> TokenMintState {
    TokenMintState {
        provider: ProviderId::Helius,
        mint: "mint-a".to_owned(),
        owner_program: "TokenProgram".to_owned(),
        supply: 1_000_000_000,
        decimals: 6,
        mint_authority: None,
        freeze_authority: None,
        slot: 123,
        observed_at_unix_ms: 101,
    }
}

struct FakeDiscovery {
    provider: ProviderId,
    result: Result<Vec<DiscoveredToken>, ProviderError>,
}

#[async_trait]
impl DiscoveryProvider for FakeDiscovery {
    fn provider_id(&self) -> ProviderId {
        self.provider
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        self.result.clone()
    }
}

struct FakeMarket {
    provider: ProviderId,
    result: Result<Vec<PairMarketData>, ProviderError>,
}

#[async_trait]
impl MarketDataProvider for FakeMarket {
    fn provider_id(&self) -> ProviderId {
        self.provider
    }

    async fn token_pairs(&self, _token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.result.clone()
    }
}

struct FakeChain {
    provider: ProviderId,
    result: Result<TokenMintState, ProviderError>,
}

#[async_trait]
impl ChainDataProvider for FakeChain {
    fn provider_id(&self) -> ProviderId {
        self.provider
    }

    async fn token_mint_state(&self, _token_mint: &str) -> Result<TokenMintState, ProviderError> {
        self.result.clone()
    }
}

#[tokio::test(flavor = "current_thread")]
async fn cycle_deduplicates_discovery_keeps_good_data_and_isolates_provider_failures() {
    let root = unique_test_dir("isolation");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let duplicate = candidate();
    let discovery = Arc::new(FakeDiscovery {
        provider: ProviderId::DexScreener,
        result: Ok(vec![duplicate.clone(), duplicate]),
    });
    let healthy_market = Arc::new(FakeMarket {
        provider: ProviderId::DexScreener,
        result: Ok(vec![market_snapshot()]),
    });
    let rate_limited_market = Arc::new(FakeMarket {
        provider: ProviderId::Meteora,
        result: Err(ProviderError::new(
            ProviderId::Meteora,
            ProviderErrorKind::RateLimited,
            "fixture rate limit",
        )),
    });
    let unavailable_chain = Arc::new(FakeChain {
        provider: ProviderId::Helius,
        result: Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::Unavailable,
            "fixture outage",
        )),
    });

    let mut observer = Observer::new(db)
        .with_discovery_provider(discovery)
        .with_market_provider(healthy_market)
        .with_market_provider(rate_limited_market)
        .with_chain_provider(unavailable_chain);

    let report = observer.run_cycle().await.unwrap();
    assert_eq!(report.discovery_items_seen, 2);
    assert_eq!(report.candidates_processed, 1);
    assert_eq!(report.market_snapshots_stored, 1);
    assert_eq!(report.mint_states_stored, 0);
    assert_eq!(report.provider_failures, 2);

    let connection = Connection::open(&db_path).unwrap();
    let candidates: i64 = connection
        .query_row("SELECT COUNT(*) FROM token_candidates", [], |row| row.get(0))
        .unwrap();
    let snapshots: i64 = connection
        .query_row("SELECT COUNT(*) FROM market_snapshots", [], |row| row.get(0))
        .unwrap();
    let mint_states: i64 = connection
        .query_row("SELECT COUNT(*) FROM token_mint_states", [], |row| row.get(0))
        .unwrap();
    assert_eq!(candidates, 1);
    assert_eq!(snapshots, 1);
    assert_eq!(mint_states, 0);

    for (provider, expected) in [
        ("dexscreener", "healthy"),
        ("meteora", "rate_limited"),
        ("helius", "unavailable"),
    ] {
        let state: String = connection
            .query_row(
                "SELECT status FROM provider_health WHERE provider = ?1",
                [provider],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(state, expected, "wrong health for {provider}");
    }

    drop(connection);
    drop(observer);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn successful_chain_observation_persists_mint_state_and_marks_provider_healthy() {
    let root = unique_test_dir("chain-success");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let observer_discovery = Arc::new(FakeDiscovery {
        provider: ProviderId::DexScreener,
        result: Ok(vec![candidate()]),
    });
    let chain = Arc::new(FakeChain {
        provider: ProviderId::Helius,
        result: Ok(mint_state()),
    });

    let mut observer = Observer::new(db)
        .with_discovery_provider(observer_discovery)
        .with_chain_provider(chain);
    let report = observer.run_cycle().await.unwrap();

    assert_eq!(report.candidates_processed, 1);
    assert_eq!(report.mint_states_stored, 1);
    assert_eq!(report.provider_failures, 0);

    let connection = Connection::open(&db_path).unwrap();
    let mint_states: i64 = connection
        .query_row("SELECT COUNT(*) FROM token_mint_states", [], |row| row.get(0))
        .unwrap();
    let helius_health: String = connection
        .query_row(
            "SELECT status FROM provider_health WHERE provider = 'helius'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(mint_states, 1);
    assert_eq!(helius_health, "healthy");

    drop(connection);
    drop(observer);
    cleanup_dir(&root);
}
