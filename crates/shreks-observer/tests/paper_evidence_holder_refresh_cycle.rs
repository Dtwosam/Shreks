use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    process,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, QuoteRequest, QuoteSnapshot,
    TokenDistributionRequest, TokenHolderDistribution, VenueId,
};
use shreks_observer::SafetyEvidenceCollector;
use shreks_providers::{DistributionDataProvider, ProviderError, QuoteProvider};
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
        "shreks-paper-holder-refresh-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate() -> DiscoveredToken {
    DiscoveredToken {
        mint: "MintRefresh".to_owned(),
        pair_address: Some("PairRefresh".to_owned()),
        dex_id: Some("pumpswap".to_owned()),
        venue: Some(VenueId::PumpSwap),
        discovered_at_unix_ms: 100,
        source: ProviderId::DexScreener,
    }
}

fn snapshot() -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pumpswap".to_owned(),
        pair_address: "PairRefresh".to_owned(),
        base_mint: "MintRefresh".to_owned(),
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
        observed_at_unix_ms: 9_500,
    }
}

fn holder(observed_at_unix_ms: i64) -> TokenHolderDistribution {
    TokenHolderDistribution {
        provider: ProviderId::Helius,
        mint: "MintRefresh".to_owned(),
        last_indexed_slot: 123,
        observed_at_unix_ms,
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

fn runtime_config(db_path: &Path) -> PaperEvidenceRuntimeConfig {
    let values = HashMap::from([
        ("SHREKS_DB_PATH", db_path.to_string_lossy().into_owned()),
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
        ("SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES", "1".to_owned()),
        ("SHREKS_PAPER_HOLDER_REFRESH_SECONDS", "1".to_owned()),
        (
            "SHREKS_PAPER_HELIUS_MAX_REQUESTS_PER_PROCESS",
            "100".to_owned(),
        ),
        ("SHREKS_PAPER_PROBE_POLICY_VERSION", "probe-v1".to_owned()),
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

struct CountingDistributionProvider {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl DistributionDataProvider for CountingDistributionProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn token_holder_distribution(
        &self,
        request: &TokenDistributionRequest,
    ) -> Result<TokenHolderDistribution, ProviderError> {
        self.calls.fetch_add(1, Ordering::Relaxed);
        Ok(TokenHolderDistribution {
            mint: request.mint.clone(),
            observed_at_unix_ms: 10_000,
            ..holder(10_000)
        })
    }
}

struct QuoteProviderStub;

#[async_trait]
impl QuoteProvider for QuoteProviderStub {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Jupiter
    }

    async fn quote(&self, request: &QuoteRequest) -> Result<QuoteSnapshot, ProviderError> {
        Ok(QuoteSnapshot {
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
        })
    }
}

async fn run_case(label: &str, holder_observed_at: i64) -> (usize, cycle::PaperEvidenceCycleReport) {
    let root = unique_test_dir(label);
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate()).unwrap();
    db.insert_market_snapshot(candidate_id, &snapshot()).unwrap();
    db.insert_holder_distribution(candidate_id, &holder(holder_observed_at))
        .unwrap();
    drop(db);

    let calls = Arc::new(AtomicUsize::new(0));
    let collector = SafetyEvidenceCollector::new(
        ShreksDb::open(&db_path).unwrap(),
        vec![Arc::new(CountingDistributionProvider {
            calls: Arc::clone(&calls),
        })],
        vec![Arc::new(QuoteProviderStub)],
    );
    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let config = runtime_config(&db_path);
    let report = run_paper_evidence_cycle(&store, &collector, &config, 10_000)
        .await
        .unwrap();
    let count = calls.load(Ordering::Relaxed);
    cleanup(&root);
    (count, report)
}

#[tokio::test]
async fn fresh_holder_evidence_suppresses_only_holder_transport() {
    let (calls, report) = run_case("fresh", 9_500).await;
    assert_eq!(calls, 0);
    assert_eq!(report.holder_snapshots_stored, 0);
    assert_eq!(report.quote_snapshots_stored, 2);
}

#[tokio::test]
async fn stale_holder_evidence_triggers_one_holder_refresh() {
    let (calls, report) = run_case("stale", 8_999).await;
    assert_eq!(calls, 1);
    assert_eq!(report.holder_snapshots_stored, 1);
    assert_eq!(report.quote_snapshots_stored, 2);
}
