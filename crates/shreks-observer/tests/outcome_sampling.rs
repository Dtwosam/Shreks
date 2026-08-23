use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    },
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, TokenMintState, VenueId};
use shreks_observer::Observer;
use shreks_providers::{ChainDataProvider, MarketDataProvider, ProviderError};
use shreks_storage::ShreksDb;
use tokio::time::Instant;

const EXPECTED_DUE_CANDIDATE_LIMIT: usize = 16;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-outcome-sampling-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn seed_candidate(db: &ShreksDb, mint: &str, discovered_at_unix_ms: i64) -> i64 {
    let candidate = DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms,
        source: ProviderId::Helius,
    };
    let candidate_id = db.upsert_candidate(&candidate).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at_unix_ms)
        .unwrap();
    candidate_id
}

#[derive(Clone, Default)]
struct CountingMarket {
    calls: Arc<Mutex<Vec<(String, Instant)>>>,
}

impl CountingMarket {
    fn mints(&self) -> Vec<String> {
        self.calls
            .lock()
            .unwrap()
            .iter()
            .map(|(mint, _)| mint.clone())
            .collect()
    }

    fn instants(&self) -> Vec<Instant> {
        self.calls
            .lock()
            .unwrap()
            .iter()
            .map(|(_, instant)| *instant)
            .collect()
    }
}

#[async_trait]
impl MarketDataProvider for CountingMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls
            .lock()
            .unwrap()
            .push((token_mint.to_owned(), Instant::now()));
        Ok(Vec::new())
    }
}

#[derive(Clone, Default)]
struct CountingChain {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl ChainDataProvider for CountingChain {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn token_mint_state(&self, token_mint: &str) -> Result<TokenMintState, ProviderError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(TokenMintState {
            provider: ProviderId::Helius,
            mint: token_mint.to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1,
            decimals: 0,
            mint_authority: None,
            freeze_authority: None,
            slot: 1,
            observed_at_unix_ms: 1,
        })
    }
}

#[tokio::test(start_paused = true)]
async fn due_candidate_gets_one_market_pass_even_when_all_horizons_are_overdue_and_no_chain_call() {
    let root = unique_test_dir("dedupe-no-chain");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    seed_candidate(&db, "mint-due", 0);

    let market = Arc::new(CountingMarket::default());
    let chain = Arc::new(CountingChain::default());
    let chain_calls = chain.calls.clone();
    let mut observer = Observer::new(db)
        .with_market_provider(market.clone())
        .with_chain_provider(chain);

    observer.run_cycle().await.unwrap();

    assert_eq!(market.mints(), vec!["mint-due"]);
    assert_eq!(chain_calls.load(Ordering::SeqCst), 0);

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn not_yet_due_candidate_causes_no_outcome_market_call() {
    let root = unique_test_dir("not-due");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    seed_candidate(&db, "mint-future", 4_000_000_000_000);

    let market = Arc::new(CountingMarket::default());
    let mut observer = Observer::new(db).with_market_provider(market.clone());
    observer.run_cycle().await.unwrap();

    assert!(market.mints().is_empty());

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn due_candidate_batch_is_capped_to_protect_free_provider_budgets() {
    let root = unique_test_dir("batch-cap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    for index in 0..=EXPECTED_DUE_CANDIDATE_LIMIT {
        seed_candidate(&db, &format!("mint-{index:02}"), 0);
    }

    let market = Arc::new(CountingMarket::default());
    let mut observer = Observer::new(db).with_market_provider(market.clone());
    observer.run_cycle().await.unwrap();

    let mints = market.mints();
    assert_eq!(mints.len(), EXPECTED_DUE_CANDIDATE_LIMIT);
    assert_eq!(mints.first().map(String::as_str), Some("mint-00"));
    assert_eq!(mints.last().map(String::as_str), Some("mint-15"));
    assert!(!mints.iter().any(|mint| mint == "mint-16"));

    cleanup_dir(&root);
}

#[tokio::test(start_paused = true)]
async fn due_sampling_reuses_existing_dexscreener_market_pacing() {
    let root = unique_test_dir("pacing");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    seed_candidate(&db, "mint-a", 0);
    seed_candidate(&db, "mint-b", 0);

    let market = Arc::new(CountingMarket::default());
    let mut observer = Observer::new(db).with_market_provider(market.clone());
    observer.run_cycle().await.unwrap();

    let instants = market.instants();
    assert_eq!(instants.len(), 2);
    assert!(instants[1].duration_since(instants[0]).as_millis() >= 250);

    cleanup_dir(&root);
}
