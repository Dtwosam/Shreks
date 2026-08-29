use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
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
        "shreks-pump-transaction-failover-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn verified_transaction_body() -> String {
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
                            "programId":"{PUMP_PROGRAM_ID}"
                        }}]
                    }}
                }}
            }},
            "id":"shreks-pump-transaction"
        }}"#
    )
}

#[derive(Clone)]
struct CountingTransactionProvider {
    provider: ProviderId,
    response: Result<String, ProviderError>,
    calls: Arc<AtomicUsize>,
}

impl CountingTransactionProvider {
    fn rate_limited(provider: ProviderId, calls: Arc<AtomicUsize>) -> Self {
        Self {
            provider,
            response: Err(ProviderError::new(
                provider,
                ProviderErrorKind::RateLimited,
                "fixture quota exhausted",
            )),
            calls,
        }
    }

    fn body(provider: ProviderId, body: String, calls: Arc<AtomicUsize>) -> Self {
        Self {
            provider,
            response: Ok(body),
            calls,
        }
    }
}

#[async_trait]
impl TransactionProvider for CountingTransactionProvider {
    fn provider_id(&self) -> ProviderId {
        self.provider
    }

    async fn transaction_json(&self, _signature: &str) -> Result<String, ProviderError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        self.response.clone()
    }
}

#[tokio::test]
async fn retryable_helius_failure_falls_through_to_chainstack_transaction_rpc() {
    let root = unique_test_dir("rate-limit");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_launch_signal("sig-failover", 10, 100)
        .unwrap();

    let helius_calls = Arc::new(AtomicUsize::new(0));
    let chainstack_calls = Arc::new(AtomicUsize::new(0));

    let helius = Arc::new(CountingTransactionProvider::rate_limited(
        ProviderId::Helius,
        helius_calls.clone(),
    ));
    let chainstack = Arc::new(CountingTransactionProvider::body(
        ProviderId::Chainstack,
        verified_transaction_body(),
        chainstack_calls.clone(),
    ));

    let mut observer = Observer::new(db)
        .with_transaction_provider(helius)
        .with_transaction_provider(chainstack);

    let report = observer.run_cycle().await.unwrap();

    assert_eq!(helius_calls.load(Ordering::SeqCst), 1);
    assert_eq!(chainstack_calls.load(Ordering::SeqCst), 1);
    assert_eq!(report.pump_signals_processed, 1);
    assert_eq!(report.pump_signals_verified, 1);
    assert_eq!(report.pump_signals_pending, 0);

    cleanup_dir(&root);
}

#[tokio::test]
async fn nonretryable_primary_failure_does_not_change_provider_authority() {
    let root = unique_test_dir("nonretryable");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_launch_signal("sig-no-failover", 10, 100)
        .unwrap();

    let primary_calls = Arc::new(AtomicUsize::new(0));
    let secondary_calls = Arc::new(AtomicUsize::new(0));

    let primary = Arc::new(CountingTransactionProvider {
        provider: ProviderId::Helius,
        response: Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            "fixture malformed authoritative response",
        )),
        calls: primary_calls.clone(),
    });
    let secondary = Arc::new(CountingTransactionProvider::body(
        ProviderId::Chainstack,
        verified_transaction_body(),
        secondary_calls.clone(),
    ));

    let mut observer = Observer::new(db)
        .with_transaction_provider(primary)
        .with_transaction_provider(secondary);

    let report = observer.run_cycle().await.unwrap();

    assert_eq!(primary_calls.load(Ordering::SeqCst), 1);
    assert_eq!(secondary_calls.load(Ordering::SeqCst), 0);
    assert_eq!(report.pump_signals_verified, 0);
    assert_eq!(report.pump_signals_pending, 1);

    cleanup_dir(&root);
}
