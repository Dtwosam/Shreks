use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::ProviderId;
use shreks_observer::Observer;
use shreks_providers::{
    pump::{
        PUMP_AMM_PROGRAM_ID, PUMP_MIGRATE_V2_DISCRIMINATOR, PUMP_PROGRAM_ID,
    },
    ProviderError, ProviderErrorKind, TransactionProvider,
};
use shreks_storage::ShreksDb;

const MINT: &str = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump";
const QUOTE: &str = "quote-mint-111111111111111111111111111111111";
const POOL: &str = "pump-swap-pool-1111111111111111111111111111111";
const CREATE_V2_DATA: &str = "ctY7UoGVwdd";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pump-migration-observer-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn migrate_v2_body(block_time: &str) -> String {
    let data = bs58::encode(PUMP_MIGRATE_V2_DISCRIMINATOR).into_string();
    format!(
        r#"{{
          "jsonrpc":"2.0",
          "result":{{
            "slot":999,
            "blockTime":{block_time},
            "meta":{{"err":null,"innerInstructions":[]}},
            "transaction":{{"message":{{"instructions":[{{
              "programId":"{PUMP_PROGRAM_ID}",
              "data":"{data}",
              "accounts":[
                "global","withdraw-authority","{MINT}","{QUOTE}",
                "bonding-curve","associated-bonding-curve","user",
                "system-program","token-program","{PUMP_AMM_PROGRAM_ID}","{POOL}"
              ]
            }}]}}}}
          }},
          "id":"shreks-pump-migration"
        }}"#
    )
}

fn create_body() -> String {
    format!(
        r#"{{
          "jsonrpc":"2.0",
          "result":{{
            "slot":123,
            "meta":{{"err":null}},
            "transaction":{{"message":{{"instructions":[{{
              "accounts":["{MINT}","authority","curve"],
              "data":"{CREATE_V2_DATA}",
              "programId":"{PUMP_PROGRAM_ID}"
            }}]}}}}
          }},
          "id":"shreks-pump-transaction"
        }}"#
    )
}

#[derive(Clone)]
struct RecordingTransactionProvider {
    provider_id: ProviderId,
    calls: Arc<Mutex<Vec<String>>>,
    failure: Option<ProviderError>,
}

impl RecordingTransactionProvider {
    fn new(provider_id: ProviderId) -> Self {
        Self {
            provider_id,
            calls: Arc::new(Mutex::new(Vec::new())),
            failure: None,
        }
    }

    fn failing(provider_id: ProviderId, error: ProviderError) -> Self {
        Self {
            provider_id,
            calls: Arc::new(Mutex::new(Vec::new())),
            failure: Some(error),
        }
    }

    fn calls(&self) -> Vec<String> {
        self.calls.lock().unwrap().clone()
    }
}

#[async_trait]
impl TransactionProvider for RecordingTransactionProvider {
    fn provider_id(&self) -> ProviderId {
        self.provider_id
    }

    async fn transaction_json(&self, signature: &str) -> Result<String, ProviderError> {
        self.calls.lock().unwrap().push(signature.to_owned());
        if let Some(error) = &self.failure {
            return Err(error.clone());
        }
        if signature.starts_with("migration-pending") {
            return Ok(r#"{"jsonrpc":"2.0","result":null,"id":"pending"}"#.to_owned());
        }
        if signature.starts_with("migration-reject") {
            return Ok(create_body());
        }
        if signature.starts_with("migration-") {
            return Ok(migrate_v2_body("1770000000"));
        }
        Ok(create_body())
    }
}

#[tokio::test]
async fn verified_migration_stores_normalized_event_with_actual_provider_identity() {
    let root = unique_test_dir("verified");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_migration_signal("migration-verified", u64::MAX, 123_456)
        .unwrap();

    let provider = Arc::new(RecordingTransactionProvider::new(ProviderId::Jupiter));
    let mut observer = Observer::new(db).with_transaction_provider(provider);
    let report = observer.run_cycle().await.unwrap();

    assert_eq!(report.pump_migration_signals_processed, 1);
    assert_eq!(report.pump_migration_signals_verified, 1);
    assert_eq!(report.pump_migration_signals_pending, 0);
    assert_eq!(report.pump_migration_signals_rejected, 0);
    assert_eq!(report.lifecycle_events_stored, 1);

    drop(observer);
    let connection = Connection::open(&db_path).unwrap();
    let signal: (String, i64) = connection
        .query_row(
            "SELECT status, attempt_count FROM pump_migration_signals WHERE signature = 'migration-verified'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(signal.0, "verified");
    assert_eq!(signal.1, 1);

    let event: (String, String, String, String, String, String, String, String, i64, Option<i64>) = connection
        .query_row(
            "SELECT event_type, provider, mint, quote_mint, from_venue, to_venue, pool_address, slot, detected_at_unix_ms, occurred_at_unix_ms FROM token_lifecycle_events WHERE signature = 'migration-verified'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?, row.get(5)?, row.get(6)?, row.get(7)?, row.get(8)?, row.get(9)?)),
        )
        .unwrap();
    assert_eq!(event.0, "pump_graduation");
    assert_eq!(event.1, "jupiter");
    assert_eq!(event.2, MINT);
    assert_eq!(event.3, QUOTE);
    assert_eq!(event.4, "pump_fun_bonding_curve");
    assert_eq!(event.5, "pump_swap");
    assert_eq!(event.6, POOL);
    assert_eq!(event.7, u64::MAX.to_string());
    assert_eq!(event.8, 123_456);
    assert_eq!(event.9, Some(1_770_000_000_000));

    cleanup_dir(&root);
}

#[tokio::test]
async fn pending_rejected_and_provider_failure_keep_their_distinct_terminal_semantics() {
    let root = unique_test_dir("states");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_migration_signal("migration-pending-1", 1, 100)
        .unwrap();
    db.record_pump_migration_signal("migration-reject-1", 2, 101)
        .unwrap();

    let provider = Arc::new(RecordingTransactionProvider::new(ProviderId::Helius));
    let mut observer = Observer::new(db).with_transaction_provider(provider);
    let report = observer.run_cycle().await.unwrap();
    assert_eq!(report.pump_migration_signals_processed, 2);
    assert_eq!(report.pump_migration_signals_pending, 1);
    assert_eq!(report.pump_migration_signals_rejected, 1);

    drop(observer);
    let connection = Connection::open(&db_path).unwrap();
    let pending: (String, i64) = connection
        .query_row(
            "SELECT status, attempt_count FROM pump_migration_signals WHERE signature = 'migration-pending-1'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    let rejected: (String, i64) = connection
        .query_row(
            "SELECT status, attempt_count FROM pump_migration_signals WHERE signature = 'migration-reject-1'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(pending, ("pending".to_owned(), 1));
    assert_eq!(rejected, ("rejected".to_owned(), 1));
    drop(connection);

    let reopened = ShreksDb::open(&db_path).unwrap();
    let retryable = reopened.pending_pump_migration_signals(10).unwrap();
    assert_eq!(retryable.len(), 1);
    assert_eq!(retryable[0].signature, "migration-pending-1");
    drop(reopened);

    let db = ShreksDb::open(&db_path).unwrap();
    let error = ProviderError::new(
        ProviderId::Helius,
        ProviderErrorKind::Unavailable,
        "temporary transaction outage",
    );
    let failing = Arc::new(RecordingTransactionProvider::failing(ProviderId::Helius, error));
    let mut observer = Observer::new(db).with_transaction_provider(failing);
    let failure_report = observer.run_cycle().await.unwrap();
    assert_eq!(failure_report.pump_migration_signals_pending, 1);
    assert_eq!(failure_report.provider_failures, 1);

    cleanup_dir(&root);
}

#[tokio::test]
async fn migration_reservation_and_creation_sharing_never_exceed_32_transaction_calls() {
    let root = unique_test_dir("budget");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    for index in 0..40 {
        db.record_pump_migration_signal(
            &format!("migration-{index:02}"),
            index,
            1_000 + index as i64,
        )
        .unwrap();
        db.record_pump_launch_signal(
            &format!("create-{index:02}"),
            100 + index,
            2_000 + index as i64,
        )
        .unwrap();
    }

    let provider = Arc::new(RecordingTransactionProvider::new(ProviderId::Helius));
    let handle = provider.clone();
    let mut observer = Observer::new(db).with_transaction_provider(provider);
    let report = observer.run_cycle().await.unwrap();
    let calls = handle.calls();

    assert_eq!(calls.len(), 32);
    assert_eq!(report.pump_migration_signals_processed, 8);
    assert_eq!(report.pump_signals_processed, 24);
    assert!(calls[..8]
        .iter()
        .all(|signature| signature.starts_with("migration-")));
    assert!(calls[8..]
        .iter()
        .all(|signature| signature.starts_with("create-")));

    cleanup_dir(&root);
}

#[tokio::test]
async fn spare_creation_capacity_is_reused_by_additional_migrations() {
    let root = unique_test_dir("spare-budget");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    for index in 0..40 {
        db.record_pump_migration_signal(
            &format!("migration-{index:02}"),
            index,
            1_000 + index as i64,
        )
        .unwrap();
    }
    for index in 0..4 {
        db.record_pump_launch_signal(
            &format!("create-{index:02}"),
            100 + index,
            2_000 + index as i64,
        )
        .unwrap();
    }

    let provider = Arc::new(RecordingTransactionProvider::new(ProviderId::Helius));
    let handle = provider.clone();
    let mut observer = Observer::new(db).with_transaction_provider(provider);
    let report = observer.run_cycle().await.unwrap();
    let calls = handle.calls();

    assert_eq!(calls.len(), 32);
    assert_eq!(report.pump_signals_processed, 4);
    assert_eq!(report.pump_migration_signals_processed, 28);
    assert!(calls[..8]
        .iter()
        .all(|signature| signature.starts_with("migration-")));
    assert!(calls[8..12]
        .iter()
        .all(|signature| signature.starts_with("create-")));
    assert!(calls[12..]
        .iter()
        .all(|signature| signature.starts_with("migration-")));

    cleanup_dir(&root);
}
