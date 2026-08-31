use std::{
    fs,
    path::PathBuf,
    process,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{ProviderId, TokenMintState};
use shreks_observer::Observer;
use shreks_providers::{pump_quote::SYSTEM_SOL_QUOTE_MINT, ChainDataProvider, ProviderError};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const MINT: &str = "HydrateDeferredBusyMint111111111111111111111111";
const OBSERVED_MS: i64 = 1_788_210_000_000;
// ShreksDb waits up to 5s per write and metadata hydration currently makes two
// total attempts with a 250ms gap. Keep the competing writer beyond that whole
// recovery envelope so this test exercises exhausted contention, not the
// already-covered one-transient-interval case.
const BLOCK_BEYOND_BOUNDED_RETRY: Duration = Duration::from_millis(10_800);

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-metadata-defer-{}-{nanos}",
        process::id()
    ))
}

fn raw_trade() -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: "sig-hydrate-deferred-busy".to_owned(),
        ordinal: 0,
        slot: 42,
        observed_at_unix_ms: OBSERVED_MS,
        mint: MINT.to_owned(),
        quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
        user: "user-hydrate-deferred-busy".to_owned(),
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

struct LockFirstPostRpcWrite {
    db_path: PathBuf,
    did_lock: AtomicBool,
    requests: Arc<Mutex<Vec<String>>>,
    release_lock: Arc<Mutex<Option<thread::JoinHandle<()>>>>,
}

#[async_trait]
impl ChainDataProvider for LockFirstPostRpcWrite {
    fn provider_id(&self) -> ProviderId {
        ProviderId::SolanaPublic
    }

    async fn token_mint_state(&self, mint: &str) -> Result<TokenMintState, ProviderError> {
        self.requests.lock().unwrap().push(mint.to_owned());

        if !self.did_lock.swap(true, Ordering::SeqCst) {
            let blocker = Connection::open(&self.db_path).unwrap();
            blocker
                .execute_batch("PRAGMA journal_mode=WAL; BEGIN IMMEDIATE;")
                .unwrap();
            let handle = thread::spawn(move || {
                thread::sleep(BLOCK_BEYOND_BOUNDED_RETRY);
                blocker.execute_batch("COMMIT;").unwrap();
            });
            *self.release_lock.lock().unwrap() = Some(handle);
        }

        Ok(mint_state(mint))
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn exhausted_metadata_busy_is_deferred_without_killing_observer_and_retries_next_cycle() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade()).unwrap();

    let requests = Arc::new(Mutex::new(Vec::new()));
    let release_lock = Arc::new(Mutex::new(None));
    let provider = Arc::new(LockFirstPostRpcWrite {
        db_path: db_path.clone(),
        did_lock: AtomicBool::new(false),
        requests: Arc::clone(&requests),
        release_lock: Arc::clone(&release_lock),
    });
    let mut observer = Observer::new(db).with_chain_provider(provider);

    let first = tokio::time::timeout(Duration::from_secs(13), observer.run_cycle())
        .await
        .expect("metadata contention handling must remain bounded")
        .expect("exhausted BUSY on retriable metadata must not terminate the observer cycle");
    assert_eq!(first.mint_states_stored, 0);

    release_lock
        .lock()
        .unwrap()
        .take()
        .expect("first provider call must install the competing writer")
        .join()
        .unwrap();

    // The durable raw event remains the queue. No guessed metadata is allowed
    // through while persistence was unavailable.
    assert_eq!(observer.database().verified_mint_decimals(MINT).unwrap(), None);

    let second = observer
        .run_cycle()
        .await
        .expect("the next unlocked cycle must retry deferred metadata");
    assert_eq!(second.mint_states_stored, 1);
    assert_eq!(
        observer.database().verified_mint_decimals(MINT).unwrap(),
        Some(6)
    );
    assert_eq!(
        requests.lock().unwrap().as_slice(),
        &[MINT.to_owned(), MINT.to_owned()]
    );

    drop(observer);
    let _ = fs::remove_dir_all(root);
}
