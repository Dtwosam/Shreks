use std::{
    fs,
    path::PathBuf,
    process,
    sync::{Arc, Mutex},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{ProviderId, TokenMintState};
use shreks_observer::Observer;
use shreks_providers::{pump_quote::SYSTEM_SOL_QUOTE_MINT, ChainDataProvider, ProviderError};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const MINT: &str = "HydrateBusyMint11111111111111111111111111111";
const OBSERVED_MS: i64 = 1_788_203_000_000;
const BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT: Duration = Duration::from_millis(5_200);

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-metadata-busy-{}-{nanos}",
        process::id()
    ))
}

fn raw_trade() -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: "sig-hydrate-busy".to_owned(),
        ordinal: 0,
        slot: 42,
        observed_at_unix_ms: OBSERVED_MS,
        mint: MINT.to_owned(),
        quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
        user: "user-hydrate-busy".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 2_500_000_000,
        timestamp_unix_seconds: OBSERVED_MS / 1_000,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 32_000_000_000,
        real_quote_reserves_raw: 10_000_000_000,
        ix_name: "buy".to_owned(),
    }
}

fn mint_state(mint: &str) -> TokenMintState {
    TokenMintState {
        provider: ProviderId::SolanaPublic,
        mint: mint.to_owned(),
        owner_program: "Tokenkeg1111111111111111111111111111111111".to_owned(),
        supply: 1_000_000_000_000,
        decimals: 6,
        mint_authority: None,
        freeze_authority: None,
        slot: 43,
        observed_at_unix_ms: OBSERVED_MS + 100_000,
    }
}

struct RecordingPublicChain {
    requests: Arc<Mutex<Vec<String>>>,
}

#[async_trait]
impl ChainDataProvider for RecordingPublicChain {
    fn provider_id(&self) -> ProviderId {
        ProviderId::SolanaPublic
    }

    async fn token_mint_state(&self, mint: &str) -> Result<TokenMintState, ProviderError> {
        self.requests.lock().unwrap().push(mint.to_owned());
        Ok(mint_state(mint))
    }
}

struct LockBeforeMintStateWritePublicChain {
    db_path: PathBuf,
    requests: Arc<Mutex<Vec<String>>>,
    release_lock: Arc<Mutex<Option<thread::JoinHandle<()>>>>,
}

#[async_trait]
impl ChainDataProvider for LockBeforeMintStateWritePublicChain {
    fn provider_id(&self) -> ProviderId {
        ProviderId::SolanaPublic
    }

    async fn token_mint_state(&self, mint: &str) -> Result<TokenMintState, ProviderError> {
        self.requests.lock().unwrap().push(mint.to_owned());

        // Candidate upsert has already succeeded when the provider is called.
        // Acquire the competing writer here so the following mint-state insert,
        // not the candidate upsert, is the operation that crosses busy_timeout.
        let blocker = Connection::open(&self.db_path).unwrap();
        blocker
            .execute_batch("PRAGMA journal_mode=WAL; BEGIN IMMEDIATE;")
            .unwrap();
        let handle = thread::spawn(move || {
            thread::sleep(BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT);
            blocker.execute_batch("COMMIT;").unwrap();
        });
        *self.release_lock.lock().unwrap() = Some(handle);

        Ok(mint_state(mint))
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn candidate_upsert_survives_one_transient_sqlite_busy_interval() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade()).unwrap();

    // Hold a real competing writer lock just beyond ShreksDb's existing
    // five-second SQLite busy timeout before the observer reaches upsert.
    let blocker = Connection::open(&db_path).unwrap();
    blocker
        .execute_batch("PRAGMA journal_mode=WAL; BEGIN IMMEDIATE;")
        .unwrap();
    let release_lock = thread::spawn(move || {
        thread::sleep(BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT);
        blocker.execute_batch("COMMIT;").unwrap();
    });

    let requests = Arc::new(Mutex::new(Vec::new()));
    let mut observer = Observer::new(db).with_chain_provider(Arc::new(RecordingPublicChain {
        requests: Arc::clone(&requests),
    }));

    let report = tokio::time::timeout(Duration::from_secs(8), observer.run_cycle())
        .await
        .expect("bounded SQLite busy recovery must complete after the competing lock clears")
        .expect("one transient SQLite busy interval must not terminate candidate upsert");

    release_lock.join().unwrap();
    assert_eq!(requests.lock().unwrap().as_slice(), &[MINT.to_owned()]);
    assert_eq!(report.mint_states_stored, 1);

    drop(observer);
    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.verified_mint_decimals(MINT).unwrap(), Some(6));

    drop(reopened);
    let _ = fs::remove_dir_all(root);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn mint_state_insert_survives_one_transient_sqlite_busy_without_replaying_provider_call() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade()).unwrap();

    let requests = Arc::new(Mutex::new(Vec::new()));
    let release_lock = Arc::new(Mutex::new(None));
    let mut observer = Observer::new(db).with_chain_provider(Arc::new(
        LockBeforeMintStateWritePublicChain {
            db_path: db_path.clone(),
            requests: Arc::clone(&requests),
            release_lock: Arc::clone(&release_lock),
        },
    ));

    let report = tokio::time::timeout(Duration::from_secs(8), observer.run_cycle())
        .await
        .expect("bounded SQLite busy recovery must complete after the insert lock clears")
        .expect("one transient SQLite busy interval must not terminate mint-state insert");

    release_lock
        .lock()
        .unwrap()
        .take()
        .expect("provider must have installed the competing writer lock")
        .join()
        .unwrap();

    // SQLite recovery is per durability operation. It must not replay the
    // public RPC request merely because the post-request insert hit BUSY.
    assert_eq!(requests.lock().unwrap().as_slice(), &[MINT.to_owned()]);
    assert_eq!(report.mint_states_stored, 1);

    drop(observer);
    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.verified_mint_decimals(MINT).unwrap(), Some(6));

    drop(reopened);
    let _ = fs::remove_dir_all(root);
}
