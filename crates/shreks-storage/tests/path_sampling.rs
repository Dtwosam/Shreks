use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{DiscoveredToken, ProviderId, VenueId};
use shreks_storage::{
    path_sampling_interval_seconds, PathSamplingStatus, ShreksDb, PATH_CADENCE_VERSION,
};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-path-sampling-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str, discovered_at_unix_ms: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms,
        source: ProviderId::Helius,
    }
}

#[test]
fn lifecycle_v0_cadence_has_exact_approved_boundaries() {
    assert_eq!(PATH_CADENCE_VERSION, "lifecycle_v0");
    assert_eq!(path_sampling_interval_seconds(0), Some(30));
    assert_eq!(path_sampling_interval_seconds(299_999), Some(30));
    assert_eq!(path_sampling_interval_seconds(300_000), Some(60));
    assert_eq!(path_sampling_interval_seconds(899_999), Some(60));
    assert_eq!(path_sampling_interval_seconds(900_000), Some(120));
    assert_eq!(path_sampling_interval_seconds(1_799_999), Some(120));
    assert_eq!(path_sampling_interval_seconds(1_800_000), Some(300));
    assert_eq!(path_sampling_interval_seconds(3_599_999), Some(300));
    assert_eq!(path_sampling_interval_seconds(3_600_000), Some(900));
    assert_eq!(path_sampling_interval_seconds(14_399_999), Some(900));
    assert_eq!(path_sampling_interval_seconds(14_400_000), Some(3_600));
    assert_eq!(path_sampling_interval_seconds(86_399_999), Some(3_600));
    assert_eq!(path_sampling_interval_seconds(86_400_000), None);
    assert_eq!(path_sampling_interval_seconds(-1), None);
}

#[test]
fn schema_five_creates_one_restart_safe_schedule_with_first_due_at_thirty_seconds() {
    let root = unique_test_dir("schedule-restart");
    let db_path = root.join("shreks.db");
    let discovered_at = 1_000_000_i64;

    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 5);
    let candidate_id = db
        .upsert_candidate(&candidate("mint-a", discovered_at))
        .unwrap();
    db.ensure_path_sampling(candidate_id, discovered_at).unwrap();
    db.ensure_path_sampling(candidate_id, discovered_at).unwrap();

    let schedule = db.path_sampling(candidate_id).unwrap().unwrap();
    assert_eq!(schedule.candidate_id, candidate_id);
    assert_eq!(schedule.next_due_at_unix_ms, Some(discovered_at + 30_000));
    assert_eq!(schedule.last_sample_at_unix_ms, None);
    assert_eq!(schedule.sample_count, 0);
    assert_eq!(schedule.status, PathSamplingStatus::Active);
    assert_eq!(schedule.cadence_version, PATH_CADENCE_VERSION);
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    reopened
        .ensure_path_sampling(candidate_id, discovered_at)
        .unwrap();
    let schedule = reopened.path_sampling(candidate_id).unwrap().unwrap();
    assert_eq!(schedule.next_due_at_unix_ms, Some(discovered_at + 30_000));
    assert_eq!(schedule.sample_count, 0);

    cleanup_dir(&root);
}

#[test]
fn due_query_is_bounded_deterministic_and_only_returns_arrived_active_rows() {
    let root = unique_test_dir("due-order");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let first = db.upsert_candidate(&candidate("mint-first", 1_000)).unwrap();
    let second = db.upsert_candidate(&candidate("mint-second", 2_000)).unwrap();
    db.ensure_path_sampling(first, 1_000).unwrap();
    db.ensure_path_sampling(second, 2_000).unwrap();

    assert!(db.due_path_samples(30_999, 10).unwrap().is_empty());
    assert!(db.due_path_samples(40_000, 0).unwrap().is_empty());

    let due = db.due_path_samples(32_000, 10).unwrap();
    assert_eq!(due.len(), 2);
    assert_eq!(due[0].candidate_id, first);
    assert_eq!(due[0].mint, "mint-first");
    assert_eq!(due[0].due_at_unix_ms, 31_000);
    assert_eq!(due[1].candidate_id, second);
    assert_eq!(due[1].mint, "mint-second");
    assert_eq!(due[1].due_at_unix_ms, 32_000);

    let limited = db.due_path_samples(32_000, 1).unwrap();
    assert_eq!(limited.len(), 1);
    assert_eq!(limited[0].candidate_id, first);

    cleanup_dir(&root);
}

#[test]
fn first_due_timestamp_overflow_is_rejected_without_partial_schedule() {
    let root = unique_test_dir("overflow");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let discovered_at = i64::MAX - 10_000;
    let candidate_id = db
        .upsert_candidate(&candidate("mint-overflow", discovered_at))
        .unwrap();

    let error = db
        .ensure_path_sampling(candidate_id, discovered_at)
        .unwrap_err();
    assert!(error.to_string().contains("overflow"));
    assert_eq!(db.path_sampling(candidate_id).unwrap(), None);

    cleanup_dir(&root);
}
