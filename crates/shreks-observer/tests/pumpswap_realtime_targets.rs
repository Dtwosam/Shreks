use std::{fs, path::{Path, PathBuf}, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::{LifecycleEventKind, ProviderId, TokenLifecycleEvent, VenueId};
use shreks_storage::ShreksDb;

#[path = "../src/bin/shreks-observe/realtime_targets.rs"]
mod realtime_targets;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pumpswap-realtime-targets-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn graduation(
    signature: &str,
    mint: &str,
    pool: &str,
    detected_at_unix_ms: i64,
) -> TokenLifecycleEvent {
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

fn persist_graduation(
    db: &ShreksDb,
    signature: &str,
    mint: &str,
    pool: &str,
    detected_at_unix_ms: i64,
) {
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
fn verified_targets_are_point_in_time_bounded_deduplicated_and_deterministic() {
    let root = unique_test_dir("bounded");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    persist_graduation(&db, "sig-old", "mint-old", "pool-old", 700);
    persist_graduation(&db, "sig-z", "mint-z", "pool-z", 950);
    persist_graduation(&db, "sig-a", "mint-a", "pool-a", 950);
    persist_graduation(&db, "sig-dup-new", "mint-dup-new", "pool-dup", 990);
    persist_graduation(&db, "sig-dup-old", "mint-dup-old", "pool-dup", 900);
    persist_graduation(&db, "sig-boundary", "mint-boundary", "pool-boundary", 1_000);
    persist_graduation(&db, "sig-future", "mint-future", "pool-future", 1_001);

    let targets = realtime_targets::load_verified_pumpswap_targets(&db_path, 1_000, 200, 3)
        .unwrap();

    assert_eq!(targets, vec!["pool-dup", "pool-a", "pool-z"]);
    assert!(!targets.iter().any(|pool| pool == "pool-old"));
    assert!(!targets.iter().any(|pool| pool == "pool-boundary"));
    assert!(!targets.iter().any(|pool| pool == "pool-future"));
    assert_eq!(targets.iter().filter(|pool| *pool == "pool-dup").count(), 1);

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn target_reader_rejects_unbounded_or_invalid_queries() {
    let root = unique_test_dir("invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    assert!(realtime_targets::load_verified_pumpswap_targets(&db_path, -1, 1_000, 1).is_err());
    assert!(realtime_targets::load_verified_pumpswap_targets(&db_path, 1_000, 0, 1).is_err());
    assert!(realtime_targets::load_verified_pumpswap_targets(&db_path, 1_000, 1_000, 0).is_err());

    drop(db);
    cleanup_dir(&root);
}
