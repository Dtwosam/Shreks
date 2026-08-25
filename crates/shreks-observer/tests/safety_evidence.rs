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
    DiscoveredToken, ProviderId, QuoteRequest, QuoteSnapshot, TokenDistributionRequest,
    TokenHolderDistribution, VenueId,
};
use shreks_observer::{
    free_observe_provider_plan, SafetyEvidenceCollector, SafetyEvidenceProbe,
};
use shreks_providers::{
    config::ProviderConfig, DistributionDataProvider, ProviderError, ProviderErrorKind, QuoteProvider,
};
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-safety-evidence-collector-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
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

fn distribution(mint: &str, provider: ProviderId, observed_at_unix_ms: i64) -> TokenHolderDistribution {
    TokenHolderDistribution {
        provider,
        mint: mint.to_owned(),
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

fn quote(request: &QuoteRequest, provider: ProviderId, quoted_at_unix_ms: i64) -> QuoteSnapshot {
    QuoteSnapshot {
        provider,
        input_mint: request.input_mint.clone(),
        output_mint: request.output_mint.clone(),
        input_amount: request.amount,
        output_amount: 900,
        minimum_output_amount: 850,
        slippage_bps: request.slippage_bps,
        price_impact_pct: Some("0.25".to_owned()),
        route_labels: vec!["RouteA".to_owned()],
        route_available: true,
        quoted_at_unix_ms,
    }
}

struct StaticDistributionProvider {
    id: ProviderId,
    result: Result<TokenHolderDistribution, ProviderError>,
}

#[async_trait]
impl DistributionDataProvider for StaticDistributionProvider {
    fn provider_id(&self) -> ProviderId {
        self.id
    }

    async fn token_holder_distribution(
        &self,
        _request: &TokenDistributionRequest,
    ) -> Result<TokenHolderDistribution, ProviderError> {
        self.result.clone()
    }
}

struct StaticQuoteProvider {
    id: ProviderId,
    result: Result<QuoteSnapshot, ProviderError>,
}

#[async_trait]
impl QuoteProvider for StaticQuoteProvider {
    fn provider_id(&self) -> ProviderId {
        self.id
    }

    async fn quote(&self, _request: &QuoteRequest) -> Result<QuoteSnapshot, ProviderError> {
        self.result.clone()
    }
}

fn row_count(path: &Path, table: &str) -> i64 {
    let connection = Connection::open(path).unwrap();
    connection
        .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| row.get(0))
        .unwrap()
}

#[tokio::test]
async fn explicit_collector_persists_successful_holder_and_quote_evidence_idempotently() {
    let root = unique_test_dir("success");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let probe = probe("Mint111");

    let distribution_provider = Arc::new(StaticDistributionProvider {
        id: ProviderId::Helius,
        result: Ok(distribution("Mint111", ProviderId::Helius, 1_000)),
    });
    let quote_provider = Arc::new(StaticQuoteProvider {
        id: ProviderId::Jupiter,
        result: Ok(quote(
            &probe.exit_quote_request,
            ProviderId::Jupiter,
            1_100,
        )),
    });

    let collector = SafetyEvidenceCollector::new(
        db,
        vec![distribution_provider],
        vec![quote_provider],
    );
    let report = collector
        .collect_candidate(candidate_id, "Mint111", &probe)
        .await
        .unwrap();
    assert_eq!(report.holder_snapshots_stored, 1);
    assert_eq!(report.quote_snapshots_stored, 1);
    assert_eq!(report.distribution_provider_failures, 0);
    assert_eq!(report.quote_provider_failures, 0);

    let replay = collector
        .collect_candidate(candidate_id, "Mint111", &probe)
        .await
        .unwrap();
    assert_eq!(replay.holder_snapshots_stored, 1);
    assert_eq!(replay.quote_snapshots_stored, 1);
    assert_eq!(row_count(&db_path, "token_holder_distributions"), 1);
    assert_eq!(row_count(&db_path, "exit_quote_snapshots"), 1);
    assert_eq!(row_count(&db_path, "paper_quote_snapshots"), 1);

    cleanup_dir(&root);
}

#[tokio::test]
async fn candidate_identity_must_match_both_probe_requests_before_any_provider_call() {
    let root = unique_test_dir("probe-identity");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();

    let distribution_provider = Arc::new(StaticDistributionProvider {
        id: ProviderId::Helius,
        result: Ok(distribution("Mint111", ProviderId::Helius, 1_000)),
    });
    let exit_quote_request = probe("Mint111").exit_quote_request;
    let quote_provider = Arc::new(StaticQuoteProvider {
        id: ProviderId::Jupiter,
        result: Ok(quote(
            &exit_quote_request,
            ProviderId::Jupiter,
            1_100,
        )),
    });
    let collector = SafetyEvidenceCollector::new(
        db,
        vec![distribution_provider],
        vec![quote_provider],
    );

    let wrong_distribution = SafetyEvidenceProbe {
        probe_policy_version: "probe-v1".to_owned(),
        distribution_request: TokenDistributionRequest::new("OtherMint", 100, 2).unwrap(),
        exit_quote_request: probe("Mint111").exit_quote_request,
        entry_quote_request: None,
    };
    assert!(collector
        .collect_candidate(candidate_id, "Mint111", &wrong_distribution)
        .await
        .is_err());

    let wrong_quote = SafetyEvidenceProbe {
        probe_policy_version: "probe-v1".to_owned(),
        distribution_request: probe("Mint111").distribution_request,
        exit_quote_request: QuoteRequest::new(
            "OtherMint",
            "So11111111111111111111111111111111111111112",
            1_000,
            "Taker111",
            75,
        )
        .unwrap(),
        entry_quote_request: None,
    };
    assert!(collector
        .collect_candidate(candidate_id, "Mint111", &wrong_quote)
        .await
        .is_err());

    assert_eq!(row_count(&db_path, "token_holder_distributions"), 0);
    assert_eq!(row_count(&db_path, "exit_quote_snapshots"), 0);
    assert_eq!(row_count(&db_path, "paper_quote_snapshots"), 0);
    cleanup_dir(&root);
}

#[tokio::test]
async fn provider_failures_and_misattributed_results_never_synthesize_evidence_rows() {
    let root = unique_test_dir("provider-failures");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let probe = probe("Mint111");

    let distribution_provider = Arc::new(StaticDistributionProvider {
        id: ProviderId::Helius,
        result: Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::RateLimited,
            "budget exhausted",
        )),
    });
    let quote_provider = Arc::new(StaticQuoteProvider {
        id: ProviderId::Jupiter,
        result: Ok(quote(
            &probe.exit_quote_request,
            ProviderId::Helius,
            1_100,
        )),
    });
    let collector = SafetyEvidenceCollector::new(
        db,
        vec![distribution_provider],
        vec![quote_provider],
    );

    let report = collector
        .collect_candidate(candidate_id, "Mint111", &probe)
        .await
        .unwrap();
    assert_eq!(report.holder_snapshots_stored, 0);
    assert_eq!(report.quote_snapshots_stored, 0);
    assert_eq!(report.distribution_provider_failures, 1);
    assert_eq!(report.quote_provider_failures, 1);
    assert_eq!(row_count(&db_path, "token_holder_distributions"), 0);
    assert_eq!(row_count(&db_path, "exit_quote_snapshots"), 0);
    assert_eq!(row_count(&db_path, "paper_quote_snapshots"), 0);

    cleanup_dir(&root);
}

#[tokio::test]
async fn explicit_route_unavailable_result_is_persisted_as_successful_quote_evidence() {
    let root = unique_test_dir("route-unavailable");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let probe = probe("Mint111");

    let mut unavailable = quote(&probe.exit_quote_request, ProviderId::Jupiter, 1_200);
    unavailable.output_amount = 0;
    unavailable.minimum_output_amount = 0;
    unavailable.price_impact_pct = None;
    unavailable.route_labels.clear();
    unavailable.route_available = false;

    let collector = SafetyEvidenceCollector::new(
        db,
        Vec::new(),
        vec![Arc::new(StaticQuoteProvider {
            id: ProviderId::Jupiter,
            result: Ok(unavailable),
        })],
    );
    let report = collector
        .collect_candidate(candidate_id, "Mint111", &probe)
        .await
        .unwrap();
    assert_eq!(report.quote_snapshots_stored, 1);
    assert_eq!(report.quote_provider_failures, 0);

    let connection = Connection::open(&db_path).unwrap();
    let value: i64 = connection
        .query_row(
            "SELECT route_available FROM exit_quote_snapshots WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(value, 0);
    let paper_value: i64 = connection
        .query_row(
            "SELECT route_available FROM paper_quote_snapshots WHERE candidate_id = ?1 AND purpose = 'exit'",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(paper_value, 0);
    cleanup_dir(&root);
}

#[test]
fn default_observer_provider_plan_still_excludes_jupiter() {
    let config = ProviderConfig::from_lookup(|name| match name {
        "HELIUS_API_KEY" => Some("helius-key".to_owned()),
        "JUPITER_API_KEY" => Some("jupiter-key".to_owned()),
        _ => None,
    });
    let plan = free_observe_provider_plan(&config);
    assert!(!plan.all_providers().contains(&ProviderId::Jupiter));
}

#[test]
fn safety_evidence_public_surface_contains_no_execution_authority_types() {
    let source = include_str!("../src/safety_evidence.rs").to_ascii_lowercase();
    for forbidden in [
        "tradeintent",
        "signedtransaction",
        "sign_transaction",
        "submit_transaction",
        "privatekey",
        "secretkey",
        "registrycandidate",
        "promote",
    ] {
        assert!(
            !source.contains(forbidden),
            "collector must not gain execution/promotion authority via {forbidden}"
        );
    }
}
