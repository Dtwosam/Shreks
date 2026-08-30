use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use shreks_core::{LifecycleEventKind, ProviderId, TokenLifecycleEvent, VenueId};
use shreks_storage::ShreksDb;
use tokio::sync::watch;

#[path = "../src/bin/shreks-observe/realtime_targets.rs"]
mod realtime_targets;
#[path = "../src/bin/shreks-observe/realtime_target_publisher.rs"]
mod realtime_target_publisher;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pumpswap-realtime-publisher-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn graduation(signature: &str, mint: &str, pool: &str, detected_at_unix_ms: i64) -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::Helius,
        mint: mint.to_owned(),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: pool.to_owned(),
        signature: signature.to_owned(),
        slot: 1,
        detected_at_unix_ms,
        occurred_at_unix_ms: Some(detected_at_unix_ms),
    }
}

fn persist_graduation(db: &ShreksDb, signature: &str, mint: &str, pool: &str, detected_at_unix_ms: i64) {
    db.record_pump_migration_signal(signature, 1, detected_at_unix_ms)
        .unwrap();
    db.complete_pump_migration(
        signature,
        detected_at_unix_ms,
        &[graduation(signature, mint, pool, detected_at_unix_ms)],
    )
    .unwrap();
}

#[test]
fn refresh_publishes_only_changed_canonical_target_sets() {
    let root = unique_test_dir("refresh");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    persist_graduation(&db, "sig-old", "mint-old", "pool-old", 700);
    persist_graduation(&db, "sig-b", "mint-b", "pool-b", 950);
    persist_graduation(&db, "sig-a", "mint-a", "pool-a", 980);

    let (sender, mut receiver) = watch::channel(Vec::<String>::new());
    let changed = realtime_target_publisher::refresh_pumpswap_realtime_targets(
        &db_path,
        1_000,
        200,
        2,
        &sender,
    )
    .unwrap();
    assert!(changed);
    assert_eq!(receiver.borrow_and_update().as_slice(), ["pool-a", "pool-b"]);

    let unchanged = realtime_target_publisher::refresh_pumpswap_realtime_targets(
        &db_path,
        1_000,
        200,
        2,
        &sender,
    )
    .unwrap();
    assert!(!unchanged, "identical target set must not publish a duplicate watch version");
    assert!(!receiver.has_changed().unwrap());

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn refresh_failure_is_returned_without_replacing_last_known_targets() {
    let root = unique_test_dir("failure");
    let missing_db = root.join("missing.db");
    let (sender, receiver) = watch::channel(vec!["pool-known".to_owned()]);

    let error = realtime_target_publisher::refresh_pumpswap_realtime_targets(
        &missing_db,
        1_000,
        200,
        2,
        &sender,
    )
    .expect_err("missing read-only database must fail closed");
    assert!(error.to_string().contains("target"));
    assert_eq!(receiver.borrow().as_slice(), ["pool-known"]);

    cleanup_dir(&root);
}

#[test]
fn publisher_refresh_cadence_is_fixed_small_and_slower_than_event_handling() {
    let cadence = realtime_target_publisher::PUMPSWAP_TARGET_REFRESH_INTERVAL;
    assert!(cadence >= Duration::from_secs(1));
    assert!(cadence <= Duration::from_secs(30));
}
