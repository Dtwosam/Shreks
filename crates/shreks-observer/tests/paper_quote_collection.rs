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
use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, ProviderId, QuoteRequest, QuoteSnapshot, TokenDistributionRequest, VenueId,
};
use shreks_observer::{SafetyEvidenceCollector, SafetyEvidenceProbe};
use shreks_providers::{ProviderError, ProviderErrorKind, QuoteProvider};
use shreks_storage::ShreksDb;

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-paper-quote-collector-{label}-{}-{nanos}",
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

fn exit_request(mint: &str) -> QuoteRequest {
    QuoteRequest::new(mint, WSOL, 1_000, "Taker111", 75).unwrap()
}

fn entry_request(mint: &str) -> QuoteRequest {
    QuoteRequest::new(WSOL, mint, 2_000, "Taker111", 75).unwrap()
}

fn probe(mint: &str) -> SafetyEvidenceProbe {
    SafetyEvidenceProbe {
        probe_policy_version: "probe-v2".to_owned(),
        distribution_request: TokenDistributionRequest::new(mint, 100, 2).unwrap(),
        exit_quote_request: exit_request(mint),
        entry_quote_request: Some(entry_request(mint)),
    }
}

fn quote(request: &QuoteRequest, quoted_at_unix_ms: i64) -> QuoteSnapshot {
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
        quoted_at_unix_ms,
    }
}

struct EchoQuoteProvider {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl QuoteProvider for EchoQuoteProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Jupiter
    }

    async fn quote(&self, request: &QuoteRequest) -> Result<QuoteSnapshot, ProviderError> {
        let sequence = self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(quote(request, 1_000 + i64::try_from(sequence).unwrap()))
    }
}

struct EntryFailingQuoteProvider;

#[async_trait]
impl QuoteProvider for EntryFailingQuoteProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Jupiter
    }

    async fn quote(&self, request: &QuoteRequest) -> Result<QuoteSnapshot, ProviderError> {
        if request.input_mint == WSOL {
            return Err(ProviderError::new(
                ProviderId::Jupiter,
                ProviderErrorKind::Unavailable,
                "entry route provider unavailable",
            ));
        }
        Ok(quote(request, 2_000))
    }
}

#[tokio::test]
async fn explicit_collector_persists_purpose_correct_entry_and_exit_quotes() {
    let root = unique_test_dir("bidirectional");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let collector = SafetyEvidenceCollector::new(
        db,
        Vec::new(),
        vec![Arc::new(EchoQuoteProvider {
            calls: Arc::clone(&calls),
        })],
    );

    let report = collector
        .collect_candidate(candidate_id, "Mint111", &probe("Mint111"))
        .await
        .unwrap();
    assert_eq!(report.quote_snapshots_stored, 2);
    assert_eq!(report.entry_quote_snapshots_stored, 1);
    assert_eq!(report.exit_quote_snapshots_stored, 1);
    assert_eq!(report.quote_provider_failures, 0);
    assert_eq!(report.entry_quote_provider_failures, 0);
    assert_eq!(report.exit_quote_provider_failures, 0);
    assert_eq!(calls.load(Ordering::SeqCst), 2);

    let connection = Connection::open(&db_path).unwrap();
    let rows = connection
        .prepare(
            r#"SELECT purpose, input_mint, output_mint
               FROM paper_quote_snapshots
               WHERE candidate_id = ?1
               ORDER BY purpose ASC"#,
        )
        .unwrap()
        .query_map([candidate_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    assert_eq!(
        rows,
        vec![
            ("entry".to_owned(), WSOL.to_owned(), "Mint111".to_owned()),
            ("exit".to_owned(), "Mint111".to_owned(), WSOL.to_owned()),
        ]
    );

    let legacy_exit_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM exit_quote_snapshots WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(legacy_exit_count, 1);

    cleanup_dir(&root);
}

#[tokio::test]
async fn entry_provider_failure_does_not_erase_successful_exit_evidence() {
    let root = unique_test_dir("entry-failure");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let collector = SafetyEvidenceCollector::new(
        db,
        Vec::new(),
        vec![Arc::new(EntryFailingQuoteProvider)],
    );

    let report = collector
        .collect_candidate(candidate_id, "Mint111", &probe("Mint111"))
        .await
        .unwrap();
    assert_eq!(report.quote_snapshots_stored, 1);
    assert_eq!(report.exit_quote_snapshots_stored, 1);
    assert_eq!(report.entry_quote_snapshots_stored, 0);
    assert_eq!(report.quote_provider_failures, 1);
    assert_eq!(report.exit_quote_provider_failures, 0);
    assert_eq!(report.entry_quote_provider_failures, 1);

    let connection = Connection::open(&db_path).unwrap();
    let exit_rows: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM paper_quote_snapshots WHERE candidate_id = ?1 AND purpose = 'exit'",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    let entry_rows: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM paper_quote_snapshots WHERE candidate_id = ?1 AND purpose = 'entry'",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!((exit_rows, entry_rows), (1, 0));

    cleanup_dir(&root);
}

#[tokio::test]
async fn inconsistent_bidirectional_probe_fails_before_any_provider_call() {
    let root = unique_test_dir("invalid-probe");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let collector = SafetyEvidenceCollector::new(
        db,
        Vec::new(),
        vec![Arc::new(EchoQuoteProvider {
            calls: Arc::clone(&calls),
        })],
    );

    let mut wrong_direction = probe("Mint111");
    wrong_direction.entry_quote_request = Some(
        QuoteRequest::new("OtherQuote", "OtherMint", 2_000, "Taker111", 75).unwrap(),
    );
    assert!(collector
        .collect_candidate(candidate_id, "Mint111", &wrong_direction)
        .await
        .is_err());

    let mut wrong_asset = probe("Mint111");
    wrong_asset.entry_quote_request = Some(
        QuoteRequest::new("OtherQuote", "Mint111", 2_000, "Taker111", 75).unwrap(),
    );
    assert!(collector
        .collect_candidate(candidate_id, "Mint111", &wrong_asset)
        .await
        .is_err());

    let mut wrong_taker = probe("Mint111");
    wrong_taker.entry_quote_request = Some(
        QuoteRequest::new(WSOL, "Mint111", 2_000, "OtherTaker", 75).unwrap(),
    );
    assert!(collector
        .collect_candidate(candidate_id, "Mint111", &wrong_taker)
        .await
        .is_err());

    let mut wrong_slippage = probe("Mint111");
    wrong_slippage.entry_quote_request = Some(
        QuoteRequest::new(WSOL, "Mint111", 2_000, "Taker111", 76).unwrap(),
    );
    assert!(collector
        .collect_candidate(candidate_id, "Mint111", &wrong_slippage)
        .await
        .is_err());

    assert_eq!(calls.load(Ordering::SeqCst), 0);
    let connection = Connection::open(&db_path).unwrap();
    let paper_rows: i64 = connection
        .query_row("SELECT COUNT(*) FROM paper_quote_snapshots", [], |row| row.get(0))
        .unwrap();
    let legacy_rows: i64 = connection
        .query_row("SELECT COUNT(*) FROM exit_quote_snapshots", [], |row| row.get(0))
        .unwrap();
    assert_eq!((paper_rows, legacy_rows), (0, 0));

    cleanup_dir(&root);
}
