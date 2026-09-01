use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::Arc,
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId};
use shreks_observer::Observer;
use shreks_providers::{DiscoveryProvider, MarketDataProvider, ProviderError};
use shreks_storage::ShreksDb;

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

fn spawn_writer_lock(db_path: PathBuf, hold_for: Duration) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let connection = Connection::open(db_path).unwrap();
        connection.execute_batch("BEGIN IMMEDIATE").unwrap();
        thread::sleep(hold_for);
        connection.execute_batch("ROLLBACK").unwrap();
    })
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
    let blocker = spawn_writer_lock(db_path.clone(), Duration::from_millis(6_500));

    // Give the blocking connection time to acquire BEGIN IMMEDIATE before the
    // observer attempts its first reconstructible discovery write.
    tokio::time::sleep(Duration::from_millis(100)).await;

    let mut observer = Observer::new(db).with_discovery_provider(Arc::new(StaticDiscovery));
    let result = tokio::time::timeout(
        Duration::from_secs(10),
        observer.run_until_shutdown(Duration::from_millis(50), async {
            tokio::time::sleep(Duration::from_secs(8)).await;
        }),
    )
    .await
    .expect("observer BUSY handling must stay bounded");

    blocker.join().unwrap();
    assert!(
        result.is_ok(),
        "reconstructible legacy observation must defer persistent SQLite BUSY instead of exiting: {result:?}"
    );

    drop(observer);
    cleanup_dir(&root);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn v2_sampler_defers_reconstructible_cycle_after_persistent_sqlite_busy() {
    let root = unique_test_dir("sampler");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let blocker = spawn_writer_lock(db_path.clone(), Duration::from_millis(6_500));

    tokio::time::sleep(Duration::from_millis(100)).await;

    let mut sampler = HighResolutionSampler::new(
        db,
        None,
        vec![SamplerProvider::unpaced(Arc::new(EmptyMarket))],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let result = tokio::time::timeout(
        Duration::from_secs(10),
        sampler.run_until_shutdown(async {
            tokio::time::sleep(Duration::from_secs(8)).await;
        }),
    )
    .await
    .expect("sampler BUSY handling must stay bounded");

    blocker.join().unwrap();
    assert!(
        result.is_ok(),
        "reconstructible Observer V2 sampling must defer persistent SQLite BUSY instead of exiting: {result:?}"
    );

    drop(sampler);
    cleanup_dir(&root);
}
