use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::{DiscoveredToken, ProviderId, VenueId};
use shreks_storage::{PumpSignalStatus, ShreksDb};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pump-signal-storage-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn verified_candidate(signature: &str) -> DiscoveredToken {
    DiscoveredToken {
        mint: format!("mint-{signature}"),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms: 100,
        source: ProviderId::Helius,
    }
}

#[test]
fn migration_three_adds_durable_pump_signal_inbox() {
    let root = unique_test_dir("schema");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 3);
    drop(db);

    let connection = Connection::open(&db_path).unwrap();
    let exists: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'pump_launch_signals'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(exists, 1);

    let slot_type: String = connection
        .query_row(
            "SELECT type FROM pragma_table_info('pump_launch_signals') WHERE name = 'slot'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(slot_type, "TEXT");

    cleanup_dir(&root);
}

#[test]
fn received_signal_is_idempotent_pending_and_survives_restart() {
    let root = unique_test_dir("pending-restart");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_launch_signal("sig-a", u64::MAX, 200).unwrap();
    db.record_pump_launch_signal("sig-a", u64::MAX, 250).unwrap();

    let pending = db.pending_pump_launch_signals(10).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].signature, "sig-a");
    assert_eq!(pending[0].slot, u64::MAX);
    assert_eq!(pending[0].observed_at_unix_ms, 200);
    assert_eq!(pending[0].status, PumpSignalStatus::Pending);
    assert_eq!(pending[0].attempt_count, 0);
    assert_eq!(pending[0].candidate_id, None);
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    let pending = reopened.pending_pump_launch_signals(10).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].signature, "sig-a");
    assert_eq!(pending[0].slot, u64::MAX);

    cleanup_dir(&root);
}

#[test]
fn failed_verification_attempt_stays_pending_and_records_retry_state() {
    let root = unique_test_dir("attempt");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_launch_signal("sig-retry", 42, 100).unwrap();
    db.record_pump_launch_attempt(
        "sig-retry",
        150,
        Some("transaction not available yet"),
    )
    .unwrap();
    db.record_pump_launch_attempt("sig-retry", 175, None)
        .unwrap();

    let pending = db.pending_pump_launch_signals(10).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].status, PumpSignalStatus::Pending);
    assert_eq!(pending[0].attempt_count, 2);
    assert_eq!(pending[0].last_attempt_at_unix_ms, Some(175));
    assert_eq!(pending[0].last_error, None);

    cleanup_dir(&root);
}

#[test]
fn verified_signal_links_candidate_and_leaves_pending_queue() {
    let root = unique_test_dir("verified");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_launch_signal("sig-ok", 55, 100).unwrap();
    let candidate_id = db
        .upsert_candidate(&verified_candidate("sig-ok"))
        .unwrap();
    db.mark_pump_launch_verified("sig-ok", candidate_id).unwrap();

    assert!(db.pending_pump_launch_signals(10).unwrap().is_empty());

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64) = connection
        .query_row(
            "SELECT status, candidate_id FROM pump_launch_signals WHERE signature = 'sig-ok'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(row.0, "verified");
    assert_eq!(row.1, candidate_id);

    cleanup_dir(&root);
}

#[test]
fn rejected_signal_is_auditable_but_not_retried() {
    let root = unique_test_dir("rejected");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_launch_signal("sig-bad", 77, 100).unwrap();
    db.mark_pump_launch_rejected("sig-bad", 180, "not a verified Pump create")
        .unwrap();

    assert!(db.pending_pump_launch_signals(10).unwrap().is_empty());

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, Option<String>, Option<i64>) = connection
        .query_row(
            "SELECT status, last_error, last_attempt_at_unix_ms FROM pump_launch_signals WHERE signature = 'sig-bad'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(row.0, "rejected");
    assert_eq!(row.1.as_deref(), Some("not a verified Pump create"));
    assert_eq!(row.2, Some(180));

    cleanup_dir(&root);
}

#[test]
fn pending_query_is_bounded_and_oldest_first() {
    let root = unique_test_dir("ordering");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_launch_signal("sig-late", 3, 300).unwrap();
    db.record_pump_launch_signal("sig-first", 1, 100).unwrap();
    db.record_pump_launch_signal("sig-middle", 2, 200).unwrap();

    let pending = db.pending_pump_launch_signals(2).unwrap();
    let signatures: Vec<_> = pending.iter().map(|row| row.signature.as_str()).collect();
    assert_eq!(signatures, vec!["sig-first", "sig-middle"]);

    cleanup_dir(&root);
}
