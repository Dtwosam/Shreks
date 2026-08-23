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
use shreks_providers::{
    ChainDataProvider, DiscoveryProvider, MarketDataProvider, ProviderError,
};
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-observer-path-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn now_unix_ms() -> i64 {
    i64::try_from(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis(),
    )
    .unwrap()
}

fn candidate(mint: impl Into<String>, discovered_at_unix_ms: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.into(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms,
        source: ProviderId::DexScreener,
    }
}

fn seed_candidate(db: &ShreksDb, mint: &str, discovered_at_unix_ms: i64) -> i64 {
    let candidate = candidate(mint, discovered_at_unix_ms);
    let candidate_id = db.upsert_candidate(&candidate).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at_unix_ms)
        .unwrap();
    db.ensure_path_sampling(candidate_id, discovered_at_unix_ms)
        .unwrap();
    candidate_id
}

#[derive(Clone)]
struct RecordingMarket {
    calls: Arc<Mutex<Vec<String>>>,
}

#[async_trait]
impl MarketDataProvider for RecordingMarket {
    fn provider_id(&self) -> ProviderId {
        // Jupiter is deliberately unpaced in the observer's market lane. The
        // fixture returns no snapshots, so the provider identity is only used
        // to observe deterministic revisit selection without test sleeps.
        ProviderId::Jupiter
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls.lock().unwrap().push(token_mint.to_owned());
        Ok(Vec::new())
    }
}

#[derive(Clone)]
struct CountingChain {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl ChainDataProvider for CountingChain {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn token_mint_state(&self, _token_mint: &str) -> Result<TokenMintState, ProviderError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        unreachable!("adaptive-only revisits must not request chain state")
    }
}

#[derive(Clone)]
struct StaticDiscovery {
    items: Vec<DiscoveredToken>,
}

#[async_trait]
impl DiscoveryProvider for StaticDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        Ok(self.items.clone())
    }
}

#[tokio::test(flavor = "current_thread")]
async fn checkpoint_candidates_exhaust_the_shared_sixteen_candidate_budget() {
    let root = unique_test_dir("checkpoint-full");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let now = now_unix_ms();

    for index in 0..16 {
        seed_candidate(&db, &format!("checkpoint-{index:02}"), now - 70_000);
    }
    for index in 0..8 {
        seed_candidate(&db, &format!("adaptive-{index:02}"), now - 40_000);
    }

    let calls = Arc::new(Mutex::new(Vec::new()));
    let market = Arc::new(RecordingMarket {
        calls: calls.clone(),
    });
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();

    let calls = calls.lock().unwrap().clone();
    assert_eq!(calls.len(), 16);
    assert!(calls.iter().all(|mint| mint.starts_with("checkpoint-")));

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn checkpoint_candidates_are_first_and_adaptive_only_candidates_fill_unused_budget() {
    let root = unique_test_dir("priority-fill");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let now = now_unix_ms();

    let expected_checkpoints: Vec<String> = (0..7)
        .map(|index| format!("checkpoint-{index:02}"))
        .collect();
    for mint in &expected_checkpoints {
        seed_candidate(&db, mint, now - 70_000);
    }
    for index in 0..20 {
        seed_candidate(&db, &format!("adaptive-{index:02}"), now - 40_000);
    }

    let calls = Arc::new(Mutex::new(Vec::new()));
    let market = Arc::new(RecordingMarket {
        calls: calls.clone(),
    });
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();

    let calls = calls.lock().unwrap().clone();
    assert_eq!(calls.len(), 16);
    assert_eq!(&calls[..7], expected_checkpoints.as_slice());
    assert!(calls[7..].iter().all(|mint| mint.starts_with("adaptive-")));

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn candidate_due_for_checkpoint_and_path_sampling_is_revisited_once() {
    let root = unique_test_dir("overlap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let now = now_unix_ms();
    seed_candidate(&db, "overlap", now - 70_000);

    let calls = Arc::new(Mutex::new(Vec::new()));
    let market = Arc::new(RecordingMarket {
        calls: calls.clone(),
    });
    let mut observer = Observer::new(db).with_market_provider(market);
    observer.run_cycle().await.unwrap();

    assert_eq!(calls.lock().unwrap().as_slice(), ["overlap"]);

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn newly_rediscovered_candidate_that_is_path_due_is_observed_once_through_normal_processing() {
    let root = unique_test_dir("new-dedupe");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let now = now_unix_ms();
    let rediscovered = candidate("rediscovered", now - 40_000);
    let candidate_id = db.upsert_candidate(&rediscovered).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, rediscovered.discovered_at_unix_ms)
        .unwrap();
    db.ensure_path_sampling(candidate_id, rediscovered.discovered_at_unix_ms)
        .unwrap();

    let calls = Arc::new(Mutex::new(Vec::new()));
    let market = Arc::new(RecordingMarket {
        calls: calls.clone(),
    });
    let discovery = Arc::new(StaticDiscovery {
        items: vec![rediscovered],
    });
    let mut observer = Observer::new(db)
        .with_discovery_provider(discovery)
        .with_market_provider(market);
    observer.run_cycle().await.unwrap();

    assert_eq!(calls.lock().unwrap().as_slice(), ["rediscovered"]);

    cleanup_dir(&root);
}

#[tokio::test(flavor = "current_thread")]
async fn adaptive_only_revisit_performs_market_work_without_chain_work() {
    let root = unique_test_dir("market-only");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let now = now_unix_ms();
    seed_candidate(&db, "adaptive-only", now - 40_000);

    let market_calls = Arc::new(Mutex::new(Vec::new()));
    let chain_calls = Arc::new(AtomicUsize::new(0));
    let market = Arc::new(RecordingMarket {
        calls: market_calls.clone(),
    });
    let chain = Arc::new(CountingChain {
        calls: chain_calls.clone(),
    });
    let mut observer = Observer::new(db)
        .with_market_provider(market)
        .with_chain_provider(chain);
    observer.run_cycle().await.unwrap();

    assert_eq!(market_calls.lock().unwrap().as_slice(), ["adaptive-only"]);
    assert_eq!(chain_calls.load(Ordering::SeqCst), 0);

    cleanup_dir(&root);
}
