use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{DiscoveredToken, ProviderId, VenueId};
use shreks_storage::{OutcomeCheckpointStatus, ShreksDb, OUTCOME_HORIZONS_SECONDS};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-outcome-checkpoints-{label}-{}-{nanos}",
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
fn migration_four_schedules_the_exact_approved_horizons_idempotently() {
    let root = unique_test_dir("schema-schedule");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 4);

    let discovered_at = 1_000_000_i64;
    let candidate_id = db.upsert_candidate(&candidate("mint-a", discovered_at)).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at).unwrap();

    let checkpoints = db.outcome_checkpoints(candidate_id).unwrap();
    assert_eq!(checkpoints.len(), 7);
    assert_eq!(OUTCOME_HORIZONS_SECONDS, [60, 300, 900, 1_800, 3_600, 14_400, 86_400]);

    let horizons: Vec<u32> = checkpoints.iter().map(|row| row.horizon_seconds).collect();
    assert_eq!(horizons, OUTCOME_HORIZONS_SECONDS);
    for checkpoint in &checkpoints {
        assert_eq!(checkpoint.status, OutcomeCheckpointStatus::Pending);
        assert_eq!(
            checkpoint.due_at_unix_ms,
            discovered_at + i64::from(checkpoint.horizon_seconds) * 1_000
        );
        assert_eq!(checkpoint.completed_at_unix_ms, None);
        assert_eq!(checkpoint.baseline_snapshot_id, None);
        assert_eq!(checkpoint.checkpoint_snapshot_id, None);
    }
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    reopened
        .ensure_outcome_checkpoints(candidate_id, discovered_at)
        .unwrap();
    assert_eq!(reopened.outcome_checkpoints(candidate_id).unwrap().len(), 7);

    cleanup_dir(&root);
}

#[test]
fn due_query_returns_only_arrived_pending_rows_in_deterministic_order() {
    let root = unique_test_dir("due-order");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let first_id = db.upsert_candidate(&candidate("mint-first", 1_000)).unwrap();
    let second_id = db.upsert_candidate(&candidate("mint-second", 2_000)).unwrap();
    db.ensure_outcome_checkpoints(first_id, 1_000).unwrap();
    db.ensure_outcome_checkpoints(second_id, 2_000).unwrap();

    assert!(db.due_outcome_checkpoints(60_999, 50).unwrap().is_empty());

    let due = db.due_outcome_checkpoints(62_000, 50).unwrap();
    assert_eq!(due.len(), 2);
    assert_eq!(due[0].candidate_id, first_id);
    assert_eq!(due[0].mint, "mint-first");
    assert_eq!(due[0].horizon_seconds, 60);
    assert_eq!(due[0].due_at_unix_ms, 61_000);
    assert_eq!(due[1].candidate_id, second_id);
    assert_eq!(due[1].mint, "mint-second");
    assert_eq!(due[1].due_at_unix_ms, 62_000);

    let limited = db.due_outcome_checkpoints(62_000, 1).unwrap();
    assert_eq!(limited.len(), 1);
    assert_eq!(limited[0].candidate_id, first_id);

    cleanup_dir(&root);
}

#[test]
fn scheduling_rejects_timestamp_overflow_without_partial_rows() {
    let root = unique_test_dir("overflow");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db
        .upsert_candidate(&candidate("mint-overflow", i64::MAX - 1_000))
        .unwrap();

    let error = db
        .ensure_outcome_checkpoints(candidate_id, i64::MAX - 1_000)
        .unwrap_err();
    assert!(error.to_string().contains("overflow"));
    assert!(db.outcome_checkpoints(candidate_id).unwrap().is_empty());

    cleanup_dir(&root);
}
