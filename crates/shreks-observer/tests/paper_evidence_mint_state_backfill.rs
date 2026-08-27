use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, ProviderId, QuoteRequest, TokenDistributionRequest, TokenMintState, VenueId,
};
use shreks_observer::{SafetyEvidenceCollector, SafetyEvidenceProbe};
use shreks_providers::{ChainDataProvider, ProviderError, ProviderErrorKind};
use shreks_storage::ShreksDb;

const WSOL: &str = "So11111111111111111111111111111111111111112";
const TAKER: &str = "Taker111111111111111111111111111111111111";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-paper-evidence-mint-state-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: Some(format!("Pair-{mint}")),
        dex_id: Some("pumpswap".to_owned()),
        venue: Some(VenueId::PumpSwap),
        discovered_at_unix_ms: 1_000,
        source: ProviderId::DexScreener,
    }
}

fn probe(mint: &str) -> SafetyEvidenceProbe {
    SafetyEvidenceProbe {
        probe_policy_version: "paper-probe-v1".to_owned(),
        distribution_request: TokenDistributionRequest::new(mint, 100, 2).unwrap(),
        exit_quote_request: QuoteRequest::new(mint, WSOL, 1_000, TAKER, 75).unwrap(),
        entry_quote_request: None,
    }
}

struct RecordingChainProvider {
    requests: Arc<Mutex<Vec<String>>>,
    fail: bool,
}

#[async_trait]
impl ChainDataProvider for RecordingChainProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn token_mint_state(&self, mint: &str) -> Result<TokenMintState, ProviderError> {
        self.requests.lock().unwrap().push(mint.to_owned());
        if self.fail {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::Unavailable,
                "test mint state unavailable",
            ));
        }
        Ok(TokenMintState {
            provider: ProviderId::Helius,
            mint: mint.to_owned(),
            owner_program: "Tokenkeg1111111111111111111111111111111111".to_owned(),
            supply: 1_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 123,
            observed_at_unix_ms: 10_000,
        })
    }
}

fn table_count(path: &Path, table: &str) -> i64 {
    Connection::open(path)
        .unwrap()
        .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| row.get(0))
        .unwrap()
}

#[tokio::test]
async fn selected_paper_candidate_backfills_missing_mint_state_once() {
    let root = unique_test_dir("missing");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("MintFresh")).unwrap();
    let requests = Arc::new(Mutex::new(Vec::new()));

    let collector = SafetyEvidenceCollector::new(db, vec![], vec![]).with_chain_provider(
        Arc::new(RecordingChainProvider {
            requests: Arc::clone(&requests),
            fail: false,
        }),
    );

    let first = collector
        .collect_candidate(candidate_id, "MintFresh", &probe("MintFresh"))
        .await
        .unwrap();

    assert_eq!(first.mint_states_stored, 1);
    assert_eq!(first.chain_provider_failures, 0);
    assert_eq!(table_count(&db_path, "token_mint_states"), 1);
    assert_eq!(requests.lock().unwrap().as_slice(), &["MintFresh".to_owned()]);

    let second = collector
        .collect_candidate(candidate_id, "MintFresh", &probe("MintFresh"))
        .await
        .unwrap();

    assert_eq!(second.mint_states_stored, 0);
    assert_eq!(second.chain_provider_failures, 0);
    assert_eq!(table_count(&db_path, "token_mint_states"), 1);
    assert_eq!(requests.lock().unwrap().as_slice(), &["MintFresh".to_owned()]);

    cleanup_dir(&root);
}

#[tokio::test]
async fn mint_state_provider_failure_stays_unknown_and_is_counted() {
    let root = unique_test_dir("provider-failure");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("MintFresh")).unwrap();
    let requests = Arc::new(Mutex::new(Vec::new()));

    let collector = SafetyEvidenceCollector::new(db, vec![], vec![]).with_chain_provider(
        Arc::new(RecordingChainProvider {
            requests: Arc::clone(&requests),
            fail: true,
        }),
    );

    let report = collector
        .collect_candidate(candidate_id, "MintFresh", &probe("MintFresh"))
        .await
        .unwrap();

    assert_eq!(report.mint_states_stored, 0);
    assert_eq!(report.chain_provider_failures, 1);
    assert_eq!(table_count(&db_path, "token_mint_states"), 0);
    assert_eq!(requests.lock().unwrap().as_slice(), &["MintFresh".to_owned()]);

    cleanup_dir(&root);
}
