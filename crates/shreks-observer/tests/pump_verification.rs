use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::ProviderId;
use shreks_observer::Observer;
use shreks_providers::{ProviderError, ProviderErrorKind, TransactionProvider};
use shreks_storage::ShreksDb;

const MINT: &str = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump";
const PUMP_PROGRAM_ID: &str = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P";
const CREATE_V2_DATA: &str = "ctY7UoGVwdd";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pump-verification-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn verified_transaction_body(program_id: &str) -> String {
    format!(
        r#"{{
            "jsonrpc":"2.0",
            "result":{{
                "slot":123,
                "meta":{{"err":null}},
                "transaction":{{
                    "message":{{
                        "instructions":[{{
                            "accounts":["{MINT}","authority","curve"],
                            "data":"{CREATE_V2_DATA}",
                            "programId":"{program_id}"
                        }}]
                    }}
                }}
            }},
            "id":"shreks-pump-transaction"
        }}"#
    )
}

#[derive(Clone)]
struct StaticTransactionProvider {
    response: Result<String, ProviderError>,
}

impl StaticTransactionProvider {
    fn body(body: impl Into<String>) -> Self {
        Self {
            response: Ok(body.into()),
        }
    }

    fn error(kind: ProviderErrorKind, message: &'static str) -> Self {
        Self {
            response: Err(ProviderError::new(ProviderId::Helius, kind, message)),
        }
    }
}

#[async_trait]
impl TransactionProvider for StaticTransactionProvider {
    fn provider_id(&self) -> ProviderId {
        ProviderId::Helius
    }

    async fn transaction_json(&self, _signature: &str) -> Result<String, ProviderError> {
        self.response.clone()
    }
}

#[tokio::test]
async fn unavailable_confirmed_transaction_stays_pending_for_retry() {
    let root = unique_test_dir("pending");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_launch_signal("sig-pending", 10, 100).unwrap();

    let provider = Arc::new(StaticTransactionProvider::body(
        r#"{"jsonrpc":"2.0","result":null,"id":"shreks-pump-transaction"}"#,
    ));
    let mut observer = Observer::new(db).with_transaction_provider(provider);
    let report = observer.run_cycle().await.unwrap();

    assert_eq!(report.pump_signals_processed, 1);
    assert_eq!(report.pump_signals_pending, 1);
    assert_eq!(report.pump_signals_verified, 0);
    assert_eq!(report.pump_signals_rejected, 0);

    drop(observer);
    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64, Option<String>) = connection
        .query_row(
            "SELECT status, attempt_count, last_error FROM pump_launch_signals WHERE signature = 'sig-pending'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(row.0, "pending");
    assert_eq!(row.1, 1);
    assert!(row.2.unwrap().contains("not available"));

    cleanup_dir(&root);
}

#[tokio::test]
async fn verified_pump_creation_becomes_candidate_with_outcome_and_path_schedules() {
    let root = unique_test_dir("verified");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_launch_signal("sig-ok", 11, 101).unwrap();

    let provider = Arc::new(StaticTransactionProvider::body(verified_transaction_body(
        PUMP_PROGRAM_ID,
    )));
    let mut observer = Observer::new(db).with_transaction_provider(provider);
    let report = observer.run_cycle().await.unwrap();

    assert_eq!(report.pump_signals_processed, 1);
    assert_eq!(report.pump_signals_verified, 1);
    assert_eq!(report.pump_signals_pending, 0);
    assert_eq!(report.pump_signals_rejected, 0);
    assert_eq!(report.candidates_processed, 1);

    drop(observer);
    let connection = Connection::open(&db_path).unwrap();
    let signal: (String, i64, Option<i64>) = connection
        .query_row(
            "SELECT status, attempt_count, candidate_id FROM pump_launch_signals WHERE signature = 'sig-ok'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(signal.0, "verified");
    assert_eq!(signal.1, 1);
    assert!(signal.2.is_some());
    let candidate_id = signal.2.unwrap();

    let candidate: (String, String, Option<String>) = connection
        .query_row(
            "SELECT mint, discovery_source, venue FROM token_candidates WHERE id = ?1",
            [candidate_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(candidate.0, MINT);
    assert_eq!(candidate.1, "helius");
    assert_eq!(candidate.2.as_deref(), Some("pump_fun_bonding_curve"));

    let checkpoint_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM candidate_outcome_checkpoints WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    let path_schedule_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM candidate_path_sampling WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(checkpoint_count, 7);
    assert_eq!(path_schedule_count, 1);

    cleanup_dir(&root);
}

#[tokio::test]
async fn fetched_non_creation_is_rejected_once_and_gets_no_candidate_schedules() {
    let root = unique_test_dir("rejected");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_launch_signal("sig-bad", 12, 102).unwrap();

    let provider = Arc::new(StaticTransactionProvider::body(verified_transaction_body(
        "11111111111111111111111111111111",
    )));
    let mut observer = Observer::new(db).with_transaction_provider(provider);
    let first = observer.run_cycle().await.unwrap();
    let second = observer.run_cycle().await.unwrap();

    assert_eq!(first.pump_signals_rejected, 1);
    assert_eq!(second.pump_signals_processed, 0);

    drop(observer);
    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64, Option<String>) = connection
        .query_row(
            "SELECT status, attempt_count, last_error FROM pump_launch_signals WHERE signature = 'sig-bad'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(row.0, "rejected");
    assert_eq!(row.1, 1);
    assert!(row.2.unwrap().contains("no verified Create/CreateV2"));

    let candidates: i64 = connection
        .query_row("SELECT COUNT(*) FROM token_candidates", [], |row| row.get(0))
        .unwrap();
    let checkpoints: i64 = connection
        .query_row("SELECT COUNT(*) FROM candidate_outcome_checkpoints", [], |row| row.get(0))
        .unwrap();
    let path_schedules: i64 = connection
        .query_row("SELECT COUNT(*) FROM candidate_path_sampling", [], |row| row.get(0))
        .unwrap();
    assert_eq!(candidates, 0);
    assert_eq!(checkpoints, 0);
    assert_eq!(path_schedules, 0);

    cleanup_dir(&root);
}

#[tokio::test]
async fn provider_failure_is_audited_but_does_not_reject_signal() {
    let root = unique_test_dir("provider-failure");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_launch_signal("sig-retry", 13, 103).unwrap();

    let provider = Arc::new(StaticTransactionProvider::error(
        ProviderErrorKind::Unavailable,
        "temporary Helius outage",
    ));
    let mut observer = Observer::new(db).with_transaction_provider(provider);
    let report = observer.run_cycle().await.unwrap();

    assert_eq!(report.pump_signals_processed, 1);
    assert_eq!(report.pump_signals_pending, 1);
    assert_eq!(report.provider_failures, 1);

    drop(observer);
    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64, Option<String>) = connection
        .query_row(
            "SELECT status, attempt_count, last_error FROM pump_launch_signals WHERE signature = 'sig-retry'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(row.0, "pending");
    assert_eq!(row.1, 1);
    assert!(row.2.unwrap().contains("temporary Helius outage"));

    cleanup_dir(&root);
}
