use std::{
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
    DiscoveredToken, ProviderId, QuoteRequest, QuoteSnapshot, TokenDistributionRequest,
    TokenHolderDistribution, VenueId,
};
use shreks_observer::{SafetyEvidenceCollector, SafetyEvidenceProbe};
use shreks_providers::{DistributionDataProvider, ProviderError, QuoteProvider};
use shreks_storage::ShreksDb;

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-safety-holder-policy-{}-{nanos}",
        process::id()
    ))
}

fn cleanup(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms: 100,
        source: ProviderId::Helius,
    }
}

fn probe(mint: &str) -> SafetyEvidenceProbe {
    SafetyEvidenceProbe {
        probe_policy_version: "probe-v1".to_owned(),
        distribution_request: TokenDistributionRequest::new(mint, 100, 2).unwrap(),
        exit_quote_request: QuoteRequest::new(
            mint,
            "So11111111111111111111111111111111111111112",
            1_000,
            "Taker111",
            75,
        )
        .unwrap(),
        entry_quote_request: None,
    }
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
            provider: ProviderId::Helius,
            mint: request.mint.clone(),
            last_indexed_slot: 123,
            observed_at_unix_ms: 1_000,
            reported_total_accounts: 2,
            accounts_scanned: 2,
            unique_owners: 2,
            pages_scanned: 1,
            complete: true,
            total_balance_raw: 1_000,
            largest_owner: Some("Owner111".to_owned()),
            largest_owner_balance_raw: Some(600),
            top_holder_concentration_pct: Some(60.0),
        })
    }
}

struct CountingQuoteProvider {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl QuoteProvider for CountingQuoteProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Jupiter
    }

    async fn quote(&self, request: &QuoteRequest) -> Result<QuoteSnapshot, ProviderError> {
        self.calls.fetch_add(1, Ordering::Relaxed);
        Ok(QuoteSnapshot {
            provider: ProviderId::Jupiter,
            input_mint: request.input_mint.clone(),
            output_mint: request.output_mint.clone(),
            input_amount: request.amount,
            output_amount: 900,
            minimum_output_amount: 850,
            slippage_bps: request.slippage_bps,
            price_impact_pct: Some("0.25".to_owned()),
            route_labels: vec!["RouteA".to_owned()],
            route_available: true,
            quoted_at_unix_ms: 1_100,
        })
    }
}

#[tokio::test]
async fn holder_probe_can_be_suppressed_without_suppressing_quotes() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let probe = probe("Mint111");

    let distribution_calls = Arc::new(AtomicUsize::new(0));
    let quote_calls = Arc::new(AtomicUsize::new(0));
    let collector = SafetyEvidenceCollector::new(
        db,
        vec![Arc::new(CountingDistributionProvider {
            calls: Arc::clone(&distribution_calls),
        })],
        vec![Arc::new(CountingQuoteProvider {
            calls: Arc::clone(&quote_calls),
        })],
    );

    let report = collector
        .collect_candidate_with_holder_probe(candidate_id, "Mint111", &probe, false)
        .await
        .unwrap();

    assert_eq!(distribution_calls.load(Ordering::Relaxed), 0);
    assert_eq!(quote_calls.load(Ordering::Relaxed), 1);
    assert_eq!(report.holder_snapshots_stored, 0);
    assert_eq!(report.quote_snapshots_stored, 1);

    let report = collector
        .collect_candidate_with_holder_probe(candidate_id, "Mint111", &probe, true)
        .await
        .unwrap();
    assert_eq!(distribution_calls.load(Ordering::Relaxed), 1);
    assert_eq!(quote_calls.load(Ordering::Relaxed), 2);
    assert_eq!(report.holder_snapshots_stored, 1);
    assert_eq!(report.quote_snapshots_stored, 1);

    cleanup(&root);
}
