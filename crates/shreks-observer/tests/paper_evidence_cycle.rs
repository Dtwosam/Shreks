use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, QuoteRequest, QuoteSnapshot,
    TokenDistributionRequest, TokenHolderDistribution, VenueId,
};
use shreks_observer::SafetyEvidenceCollector;
use shreks_providers::{
    DistributionDataProvider, ProviderError, ProviderErrorKind, QuoteProvider,
};
use shreks_storage::ShreksDb;

#[path = "../src/bin/shreks-paper-evidence/candidate_store.rs"]
mod candidate_store;
#[path = "../src/bin/shreks-paper-evidence/config.rs"]
mod config;
#[path = "../src/bin/shreks-paper-evidence/cycle.rs"]
mod cycle;

use candidate_store::EvidenceCandidateStore;
use config::PaperEvidenceRuntimeConfig;
use cycle::run_paper_evidence_cycle;

const WSOL: &str = "So11111111111111111111111111111111111111112";
const TAKER: &str = "Taker111111111111111111111111111111111111";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-paper-evidence-cycle-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str, discovered_at_unix_ms: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: Some(format!("Pair-{mint}")),
        dex_id: Some("pumpswap".to_owned()),
        venue: Some(VenueId::PumpSwap),
        discovered_at_unix_ms,
        source: ProviderId::DexScreener,
    }
}

fn snapshot(mint: &str, observed_at_unix_ms: i64) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pumpswap".to_owned(),
        pair_address: format!("Pair-{mint}"),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: WSOL.to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: None,
        liquidity_usd: None,
        volume_5m: None,
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: Vec::new(),
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: Some(9_000),
        observed_at_unix_ms,
    }
}

fn runtime_config(db_path: &Path, max_candidates: usize) -> PaperEvidenceRuntimeConfig {
    let db = db_path.to_string_lossy().into_owned();
    let values = HashMap::from([
        ("SHREKS_DB_PATH", db),
        ("SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS", "30".to_owned()),
        ("SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS", "1".to_owned()),
        ("SHREKS_PAPER_EVIDENCE_MAX_PAIR_AGE_SECONDS", "2".to_owned()),
        (
            "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS",
            "0".to_owned(),
        ),
        (
            "SHREKS_PAPER_EVIDENCE_MARKET_SOURCES",
            "dexscreener".to_owned(),
        ),
        (
            "SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES",
            max_candidates.to_string(),
        ),
        ("SHREKS_PAPER_PROBE_POLICY_VERSION", "paper-probe-v1".to_owned()),
        ("SHREKS_PAPER_QUOTE_ASSET_MINT", WSOL.to_owned()),
        ("SHREKS_PAPER_QUOTE_TAKER", TAKER.to_owned()),
        ("SHREKS_PAPER_ENTRY_INPUT_AMOUNT", "2000".to_owned()),
        ("SHREKS_PAPER_EXIT_INPUT_AMOUNT", "1000".to_owned()),
        ("SHREKS_PAPER_SLIPPAGE_BPS", "75".to_owned()),
        ("SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE", "100".to_owned()),
        ("SHREKS_PAPER_DISTRIBUTION_MAX_PAGES", "2".to_owned()),
        ("HELIUS_API_KEY", "helius-test-secret".to_owned()),
        ("JUPITER_API_KEY", "jupiter-test-secret".to_owned()),
    ]);
    PaperEvidenceRuntimeConfig::from_lookup(|name| values.get(name).cloned()).unwrap()
}

fn holder_result(request: &TokenDistributionRequest) -> TokenHolderDistribution {
    TokenHolderDistribution {
        provider: ProviderId::Helius,
        mint: request.mint.clone(),
        last_indexed_slot: 123,
        observed_at_unix_ms: 10_000,
        reported_total_accounts: 2,
        accounts_scanned: 2,
        unique_owners: 2,
        pages_scanned: 1,
        complete: true,
        total_balance_raw: 1_000,
        largest_owner: Some("Owner111".to_owned()),
        largest_owner_balance_raw: Some(600),
        top_holder_concentration_pct: Some(60.0),
    }
}

fn quote_result(request: &QuoteRequest) -> QuoteSnapshot {
    QuoteSnapshot {
        provider: ProviderId::Jupiter,
        input_mint: request.input_mint.clone(),
        output_mint: request.output_mint.clone(),
        input_amount: request.amount,
        output_amount: request.amount.saturating_sub(100),
        minimum_output_amount: request.amount.saturating_sub(150),
        slippage_bps: request.slippage_bps,
        price_impact_pct: Some("0.2".to_owned()),
        route_labels: vec!["RouteA".to_owned()],
        route_available: true,
        quoted_at_unix_ms: 10_000,
    }
}

struct RecordingDistributionProvider {
    requests: Arc<Mutex<Vec<TokenDistributionRequest>>>,
    fail: bool,
}

#[async_trait]
impl DistributionDataProvider for RecordingDistributionProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn token_holder_distribution(
        &self,
        request: &TokenDistributionRequest,
    ) -> Result<TokenHolderDistribution, ProviderError> {
        self.requests.lock().unwrap().push(request.clone());
        if self.fail {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::Unavailable,
                "test distribution unavailable",
            ));
        }
        Ok(holder_result(request))
    }
}

struct RecordingQuoteProvider {
    requests: Arc<Mutex<Vec<QuoteRequest>>>,
    fail: bool,
}

#[async_trait]
impl QuoteProvider for RecordingQuoteProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Jupiter
    }

    async fn quote(&self, request: &QuoteRequest) -> Result<QuoteSnapshot, ProviderError> {
        self.requests.lock().unwrap().push(request.clone());
        if self.fail {
            return Err(ProviderError::new(
                ProviderId::Jupiter,
                ProviderErrorKind::Unavailable,
                "test quote unavailable",
            ));
        }
        Ok(quote_result(request))
    }
}

fn table_count(path: &Path, table: &str) -> i64 {
    Connection::open(path)
        .unwrap()
        .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| row.get(0))
        .unwrap()
}

#[tokio::test]
async fn cycle_collects_exact_bidirectional_evidence_for_selected_candidates_only() {
    let root = unique_test_dir("selected");
    let db_path = root.join("shreks.db");
    let seed = ShreksDb::open(&db_path).unwrap();
    let recent = seed.upsert_candidate(&candidate("MintRecent", 100)).unwrap();
    let old = seed.upsert_candidate(&candidate("MintOld", 100)).unwrap();
    let future = seed.upsert_candidate(&candidate("MintFuture", 100)).unwrap();
    seed.insert_market_snapshot(recent, &snapshot("MintRecent", 9_500)).unwrap();
    seed.insert_market_snapshot(old, &snapshot("MintOld", 8_999)).unwrap();
    seed.insert_market_snapshot(future, &snapshot("MintFuture", 10_001)).unwrap();
    drop(seed);

    let config = runtime_config(&db_path, 10);
    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let distribution_requests = Arc::new(Mutex::new(Vec::new()));
    let quote_requests = Arc::new(Mutex::new(Vec::new()));
    let collector = SafetyEvidenceCollector::new(
        ShreksDb::open(&db_path).unwrap(),
        vec![Arc::new(RecordingDistributionProvider {
            requests: Arc::clone(&distribution_requests),
            fail: false,
        })],
        vec![Arc::new(RecordingQuoteProvider {
            requests: Arc::clone(&quote_requests),
            fail: false,
        })],
    );

    let report = run_paper_evidence_cycle(&store, &collector, &config, 10_000)
        .await
        .unwrap();

    assert_eq!(report.candidates_selected, 1);
    assert_eq!(report.holder_snapshots_stored, 1);
    assert_eq!(report.quote_snapshots_stored, 2);
    assert_eq!(report.entry_quote_snapshots_stored, 1);
    assert_eq!(report.exit_quote_snapshots_stored, 1);
    assert_eq!(report.distribution_provider_failures, 0);
    assert_eq!(report.quote_provider_failures, 0);

    let distributions = distribution_requests.lock().unwrap();
    assert_eq!(distributions.len(), 1);
    assert_eq!(distributions[0].mint, "MintRecent");
    drop(distributions);

    let quotes = quote_requests.lock().unwrap();
    assert_eq!(quotes.len(), 2);
    assert_eq!(quotes[0].input_mint, "MintRecent");
    assert_eq!(quotes[0].output_mint, WSOL);
    assert_eq!(quotes[0].amount, 1_000);
    assert_eq!(quotes[1].input_mint, WSOL);
    assert_eq!(quotes[1].output_mint, "MintRecent");
    assert_eq!(quotes[1].amount, 2_000);
    drop(quotes);

    assert_eq!(table_count(&db_path, "token_holder_distributions"), 1);
    assert_eq!(table_count(&db_path, "paper_quote_snapshots"), 2);

    cleanup_dir(&root);
}

#[tokio::test]
async fn provider_failures_are_counted_without_fabricating_evidence() {
    let root = unique_test_dir("provider-failures");
    let db_path = root.join("shreks.db");
    let seed = ShreksDb::open(&db_path).unwrap();
    let recent = seed.upsert_candidate(&candidate("MintRecent", 100)).unwrap();
    seed.insert_market_snapshot(recent, &snapshot("MintRecent", 9_500)).unwrap();
    drop(seed);

    let config = runtime_config(&db_path, 10);
    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let distribution_requests = Arc::new(Mutex::new(Vec::new()));
    let quote_requests = Arc::new(Mutex::new(Vec::new()));
    let collector = SafetyEvidenceCollector::new(
        ShreksDb::open(&db_path).unwrap(),
        vec![Arc::new(RecordingDistributionProvider {
            requests: Arc::clone(&distribution_requests),
            fail: true,
        })],
        vec![Arc::new(RecordingQuoteProvider {
            requests: Arc::clone(&quote_requests),
            fail: true,
        })],
    );

    let report = run_paper_evidence_cycle(&store, &collector, &config, 10_000)
        .await
        .unwrap();

    assert_eq!(report.candidates_selected, 1);
    assert_eq!(report.holder_snapshots_stored, 0);
    assert_eq!(report.quote_snapshots_stored, 0);
    assert_eq!(report.distribution_provider_failures, 1);
    assert_eq!(report.quote_provider_failures, 2);
    assert_eq!(report.entry_quote_provider_failures, 1);
    assert_eq!(report.exit_quote_provider_failures, 1);
    assert_eq!(distribution_requests.lock().unwrap().len(), 1);
    assert_eq!(quote_requests.lock().unwrap().len(), 2);
    assert_eq!(table_count(&db_path, "token_holder_distributions"), 0);
    assert_eq!(table_count(&db_path, "paper_quote_snapshots"), 0);

    cleanup_dir(&root);
}

#[tokio::test]
async fn empty_selection_makes_zero_provider_calls() {
    let root = unique_test_dir("empty");
    let db_path = root.join("shreks.db");
    ShreksDb::open(&db_path).unwrap();
    let config = runtime_config(&db_path, 10);
    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let distribution_requests = Arc::new(Mutex::new(Vec::new()));
    let quote_requests = Arc::new(Mutex::new(Vec::new()));
    let collector = SafetyEvidenceCollector::new(
        ShreksDb::open(&db_path).unwrap(),
        vec![Arc::new(RecordingDistributionProvider {
            requests: Arc::clone(&distribution_requests),
            fail: false,
        })],
        vec![Arc::new(RecordingQuoteProvider {
            requests: Arc::clone(&quote_requests),
            fail: false,
        })],
    );

    let report = run_paper_evidence_cycle(&store, &collector, &config, 10_000)
        .await
        .unwrap();
    assert_eq!(report.candidates_selected, 0);
    assert_eq!(report.quote_snapshots_stored, 0);
    assert!(distribution_requests.lock().unwrap().is_empty());
    assert!(quote_requests.lock().unwrap().is_empty());

    cleanup_dir(&root);
}

#[tokio::test]
async fn candidate_probe_integrity_error_fails_cycle_before_provider_calls() {
    let root = unique_test_dir("probe-integrity");
    let db_path = root.join("shreks.db");
    let seed = ShreksDb::open(&db_path).unwrap();
    let candidate_id = seed.upsert_candidate(&candidate(WSOL, 100)).unwrap();
    seed.insert_market_snapshot(candidate_id, &snapshot(WSOL, 9_500)).unwrap();
    drop(seed);

    let config = runtime_config(&db_path, 10);
    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let distribution_requests = Arc::new(Mutex::new(Vec::new()));
    let quote_requests = Arc::new(Mutex::new(Vec::new()));
    let collector = SafetyEvidenceCollector::new(
        ShreksDb::open(&db_path).unwrap(),
        vec![Arc::new(RecordingDistributionProvider {
            requests: Arc::clone(&distribution_requests),
            fail: false,
        })],
        vec![Arc::new(RecordingQuoteProvider {
            requests: Arc::clone(&quote_requests),
            fail: false,
        })],
    );

    let error = run_paper_evidence_cycle(&store, &collector, &config, 10_000)
        .await
        .unwrap_err();
    assert!(error.to_string().contains("probe"));
    assert!(distribution_requests.lock().unwrap().is_empty());
    assert!(quote_requests.lock().unwrap().is_empty());

    cleanup_dir(&root);
}

#[test]
fn cycle_source_has_no_trade_promotion_or_live_authority() {
    let source = include_str!("../src/bin/shreks-paper-evidence/cycle.rs");
    for forbidden in [
        "trade_intent",
        "RegistryStore",
        "promotion",
        "live_execution",
        "sign_transaction",
        "submit_transaction",
        "private_key",
        "seed_phrase",
    ] {
        assert!(!source.contains(forbidden), "forbidden authority token: {forbidden}");
    }
}
