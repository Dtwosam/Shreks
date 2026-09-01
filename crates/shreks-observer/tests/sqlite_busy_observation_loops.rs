use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{
        atomic::{AtomicUsize, Ordering},
        mpsc as std_mpsc,
        Arc,
    },
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId};
use shreks_observer::{Observer, ObserverError};
use shreks_providers::{
    pump::{PumpCreationSignal, PumpLifecycleSignal},
    DiscoveryProvider, MarketDataProvider, ProviderError,
};
use shreks_storage::ShreksDb;
use tokio::sync::{mpsc, oneshot};

#[path = "../src/bin/observer_v2/sampling.rs"]
mod sampling;
#[path = "../src/bin/observer_v2/sampler.rs"]
mod sampler;

use sampler::{HighResolutionSampler, SamplerProvider};
use sampling::SamplingPolicy;

const BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT: Duration = Duration::from_millis(6_500);
const GUARANTEED_FIRST_BUSY_INTERVAL: Duration = Duration::from_millis(5_300);

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-observation-busy-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn spawn_writer_lock(
    db_path: PathBuf,
    hold_for: Duration,
) -> (thread::JoinHandle<()>, std_mpsc::Receiver<()>) {
    let (ready_tx, ready_rx) = std_mpsc::channel();
    let handle = thread::spawn(move || {
        let connection = Connection::open(db_path).unwrap();
        connection.execute_batch("BEGIN IMMEDIATE").unwrap();
        ready_tx.send(()).unwrap();
        thread::sleep(hold_for);
        connection.execute_batch("ROLLBACK").unwrap();
    });
    (handle, ready_rx)
}

fn spawn_writer_lock_until_released(
    db_path: PathBuf,
) -> (
    thread::JoinHandle<()>,
    std_mpsc::Receiver<()>,
    std_mpsc::Sender<()>,
) {
    let (ready_tx, ready_rx) = std_mpsc::channel();
    let (release_tx, release_rx) = std_mpsc::channel();
    let handle = thread::spawn(move || {
        let connection = Connection::open(db_path).unwrap();
        connection.execute_batch("BEGIN IMMEDIATE").unwrap();
        ready_tx.send(()).unwrap();
        release_rx
            .recv_timeout(Duration::from_secs(12))
            .expect("test controller must release SQLite writer lock");
        connection.execute_batch("ROLLBACK").unwrap();
    });
    (handle, ready_rx, release_tx)
}

fn wait_for_writer_lock(ready: std_mpsc::Receiver<()>) {
    ready
        .recv_timeout(Duration::from_secs(5))
        .expect("writer lock thread must acquire BEGIN IMMEDIATE before observer starts");
}

#[derive(Clone)]
struct StaticDiscovery {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl DiscoveryProvider for StaticDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(vec![DiscoveredToken {
            mint: "busy-observer-mint".to_owned(),
            pair_address: None,
            dex_id: None,
            venue: None,
            discovered_at_unix_ms: 1,
            source: ProviderId::DexScreener,
        }])
    }
}

#[derive(Clone)]
struct EmptyMarket;

#[async_trait]
impl MarketDataProvider for EmptyMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, _token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        Ok(Vec::new())
    }
}

async fn wait_until_provider_health_is_durable(db_path: &Path) {
    tokio::time::timeout(Duration::from_secs(4), async {
        loop {
            let count: i64 = {
                let connection = Connection::open(db_path).unwrap();
                connection
                    .query_row("SELECT COUNT(*) FROM provider_health", [], |row| row.get(0))
                    .unwrap()
            };
            if count > 0 {
                return;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    })
    .await
    .expect("legacy observer must reach its end-of-cycle provider-health write after lock release");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn legacy_observer_defers_reconstructible_cycle_after_persistent_sqlite_busy() {
    let root = unique_test_dir("legacy");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let (blocker, ready, release_lock) = spawn_writer_lock_until_released(db_path.clone());
    wait_for_writer_lock(ready);

    let discovery_calls = Arc::new(AtomicUsize::new(0));
    let mut observer = Observer::new(db).with_discovery_provider(Arc::new(StaticDiscovery {
        calls: discovery_calls.clone(),
    }));
    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();

    let controller_db_path = db_path.clone();
    let controller_calls = discovery_calls.clone();
    let controller_task = tokio::spawn(async move {
        tokio::time::timeout(Duration::from_secs(2), async {
            while controller_calls.load(Ordering::SeqCst) == 0 {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("legacy observer must enter discovery while the writer lock is held");

        // Start this interval only after discovery has returned. The candidate
        // upsert follows immediately, so holding the writer for >5s from here
        // guarantees the first write crosses ShreksDb's SQLite busy timeout.
        tokio::time::sleep(GUARANTEED_FIRST_BUSY_INTERVAL).await;
        release_lock.send(()).unwrap();

        // Provider health is persisted at the end of a successful legacy cycle,
        // so this proves more than a second discovery call: the loop recovered,
        // completed reconstructible work, and reached its durable cycle tail.
        wait_until_provider_health_is_durable(&controller_db_path).await;
        assert!(
            controller_calls.load(Ordering::SeqCst) >= 2,
            "legacy observer must retry discovery after deferring the first BUSY cycle"
        );
        shutdown_tx.send(()).unwrap();
    });

    let result = tokio::time::timeout(
        Duration::from_secs(11),
        observer.run_until_shutdown(Duration::from_millis(50), async move {
            let _ = shutdown_rx.await;
        }),
    )
    .await
    .expect("event-driven legacy BUSY recovery must stay bounded");

    controller_task
        .await
        .expect("legacy BUSY recovery controller must complete without panicking");
    blocker.join().unwrap();
    let completed_cycles = result.expect(
        "reconstructible legacy observation must defer persistent SQLite BUSY instead of exiting",
    );
    assert!(
        completed_cycles > 0,
        "legacy observer must complete at least one cycle after the writer lock clears"
    );

    drop(observer);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn v2_sampler_defers_reconstructible_cycle_after_persistent_sqlite_busy() {
    let root = unique_test_dir("sampler");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let (blocker, ready) = spawn_writer_lock(db_path.clone(), BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT);
    wait_for_writer_lock(ready);

    let mut sampler = HighResolutionSampler::new(
        db,
        None,
        vec![SamplerProvider::unpaced(Arc::new(EmptyMarket))],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let result = tokio::time::timeout(
        Duration::from_secs(14),
        sampler.run_until_shutdown(async {
            tokio::time::sleep(Duration::from_secs(11)).await;
        }),
    )
    .await
    .expect("sampler BUSY handling must stay bounded");

    blocker.join().unwrap();
    let completed_cycles = result.expect(
        "reconstructible Observer V2 sampling must defer persistent SQLite BUSY instead of exiting",
    );
    assert!(
        completed_cycles > 0,
        "Observer V2 sampler must complete at least one cycle after the writer lock clears"
    );

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn raw_pump_signal_persistence_remains_fail_closed_on_sqlite_busy() {
    let root = unique_test_dir("raw-signal");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let (blocker, ready) = spawn_writer_lock(db_path.clone(), BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT);
    wait_for_writer_lock(ready);

    let (sender, receiver) = mpsc::channel(1);
    sender
        .send(PumpLifecycleSignal::Creation(PumpCreationSignal {
            signature: "busy-raw-pump-signal".to_owned(),
            slot: 42,
        }))
        .await
        .unwrap();

    let mut observer = Observer::new(db).with_pump_signal_receiver(receiver);
    let result = tokio::time::timeout(
        Duration::from_secs(7),
        observer.run_until_shutdown(Duration::from_secs(60), async {
            tokio::time::sleep(Duration::from_secs(6)).await;
        }),
    )
    .await
    .expect("raw signal BUSY failure must stay bounded");

    blocker.join().unwrap();
    assert!(
        matches!(result, Err(ObserverError::Storage(_))),
        "raw Pump signal durability must remain fail-closed under SQLite BUSY: {result:?}"
    );

    drop(observer);
    cleanup_dir(&root);
}
