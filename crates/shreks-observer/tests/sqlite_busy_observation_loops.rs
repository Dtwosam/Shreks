use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{mpsc as std_mpsc, Arc},
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
use tokio::sync::mpsc;

#[path = "../src/bin/observer_v2/sampling.rs"]
mod sampling;
#[path = "../src/bin/observer_v2/sampler.rs"]
mod sampler;

use sampler::{HighResolutionSampler, SamplerProvider};
use sampling::SamplingPolicy;

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

fn wait_for_writer_lock(ready: std_mpsc::Receiver<()>) {
    ready
        .recv_timeout(Duration::from_secs(5))
        .expect("writer lock thread must acquire BEGIN IMMEDIATE before observer starts");
}

#[derive(Clone)]
struct StaticDiscovery;

#[async_trait]
impl DiscoveryProvider for StaticDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
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

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn legacy_observer_defers_reconstructible_cycle_after_persistent_sqlite_busy() {
    let root = unique_test_dir("legacy");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let (blocker, ready) = spawn_writer_lock(db_path.clone(), Duration::from_millis(6_500));
    wait_for_writer_lock(ready);

    let mut observer = Observer::new(db).with_discovery_provider(Arc::new(StaticDiscovery));
    let result = tokio::time::timeout(
        Duration::from_secs(14),
        observer.run_until_shutdown(Duration::from_millis(50), async {
            tokio::time::sleep(Duration::from_secs(11)).await;
        }),
    )
    .await
    .expect("observer BUSY handling must stay bounded");

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
    let (blocker, ready) = spawn_writer_lock(db_path.clone(), Duration::from_millis(6_500));
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
    let (blocker, ready) = spawn_writer_lock(db_path.clone(), Duration::from_millis(6_500));
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
