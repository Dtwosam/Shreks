use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::{
    LifecycleEventKind, ProviderId, TokenLifecycleEvent, VenueId,
};
use shreks_storage::{PumpSignalStatus, ShreksDb};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pump-migration-storage-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn event(
    signature: &str,
    mint: &str,
    quote_mint: &str,
    pool: &str,
    detected_at_unix_ms: i64,
) -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::Helius,
        mint: mint.to_owned(),
        quote_mint: quote_mint.to_owned(),
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: pool.to_owned(),
        signature: signature.to_owned(),
        slot: u64::MAX,
        detected_at_unix_ms,
        occurred_at_unix_ms: Some(1_770_000_000_000),
    }
}

#[test]
fn lifecycle_event_kind_string_is_stable() {
    assert_eq!(LifecycleEventKind::PumpGraduation.as_str(), "pump_graduation");
}

#[test]
fn migration_five_adds_inbox_and_normalized_lifecycle_tables() {
    let root = unique_test_dir("schema");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 8);
    drop(db);

    let connection = Connection::open(&db_path).unwrap();
    for table in ["pump_migration_signals", "token_lifecycle_events"] {
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?1",
                [table],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 1, "missing table {table}");
    }

    let slot_type: String = connection
        .query_row(
            "SELECT type FROM pragma_table_info('pump_migration_signals') WHERE name='slot'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(slot_type, "TEXT");

    cleanup_dir(&root);
}

#[test]
fn migration_signal_is_idempotent_restart_safe_and_oldest_first() {
    let root = unique_test_dir("restart-order");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_migration_signal("sig-late", 3, 300).unwrap();
    db.record_pump_migration_signal("sig-first", u64::MAX, 100)
        .unwrap();
    db.record_pump_migration_signal("sig-middle", 2, 200).unwrap();
    db.record_pump_migration_signal("sig-first", u64::MAX, 150)
        .unwrap();

    let pending = db.pending_pump_migration_signals(2).unwrap();
    assert_eq!(pending.len(), 2);
    assert_eq!(pending[0].signature, "sig-first");
    assert_eq!(pending[0].slot, u64::MAX);
    assert_eq!(pending[0].observed_at_unix_ms, 100);
    assert_eq!(pending[0].status, PumpSignalStatus::Pending);
    assert_eq!(pending[1].signature, "sig-middle");
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    let pending = reopened.pending_pump_migration_signals(10).unwrap();
    assert_eq!(pending.len(), 3);
    assert_eq!(pending[0].signature, "sig-first");
    assert_eq!(pending[0].slot, u64::MAX);

    cleanup_dir(&root);
}

#[test]
fn migration_attempts_remain_pending_and_record_retry_state() {
    let root = unique_test_dir("attempts");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_migration_signal("sig-retry", 42, 100).unwrap();
    db.record_pump_migration_attempt("sig-retry", 150, Some("not available"))
        .unwrap();
    db.record_pump_migration_attempt("sig-retry", 175, None)
        .unwrap();

    let pending = db.pending_pump_migration_signals(10).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].attempt_count, 2);
    assert_eq!(pending[0].last_attempt_at_unix_ms, Some(175));
    assert_eq!(pending[0].last_error, None);

    cleanup_dir(&root);
}

#[test]
fn completion_is_atomic_normalized_and_identical_replay_is_noop() {
    let root = unique_test_dir("complete");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_migration_signal("sig-ok", u64::MAX, 100)
        .unwrap();

    let first = event("sig-ok", "mint-a", "quote-a", "pool-a", 100);
    let second = event("sig-ok", "mint-b", "quote-b", "pool-b", 100);
    let inserted = db
        .complete_pump_migration("sig-ok", 180, &[first.clone(), second.clone()])
        .unwrap();
    assert_eq!(inserted, 2);
    assert!(db.pending_pump_migration_signals(10).unwrap().is_empty());

    let replayed = db
        .complete_pump_migration("sig-ok", 190, &[first.clone(), second.clone()])
        .unwrap();
    assert_eq!(replayed, 0);

    assert_eq!(db.lifecycle_events_for_mint("mint-a").unwrap(), vec![first]);
    assert_eq!(db.lifecycle_events_for_mint("mint-b").unwrap(), vec![second]);

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64, Option<i64>, Option<String>) = connection
        .query_row(
            "SELECT status, attempt_count, last_attempt_at_unix_ms, last_error FROM pump_migration_signals WHERE signature='sig-ok'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(row.0, "verified");
    assert_eq!(row.1, 1);
    assert_eq!(row.2, Some(180));
    assert_eq!(row.3, None);

    cleanup_dir(&root);
}

#[test]
fn verified_replay_cannot_append_or_mutate_lifecycle_truth() {
    let root = unique_test_dir("immutable-terminal");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_migration_signal("sig-ok", 9, 100).unwrap();

    let original = event("sig-ok", "mint-a", "quote-a", "pool-a", 100);
    db.complete_pump_migration("sig-ok", 180, std::slice::from_ref(&original))
        .unwrap();

    let changed = event("sig-ok", "mint-a", "quote-a", "pool-changed", 100);
    assert!(db
        .complete_pump_migration("sig-ok", 190, &[original.clone(), changed])
        .is_err());
    assert_eq!(db.lifecycle_events_for_mint("mint-a").unwrap(), vec![original]);

    db.record_pump_migration_signal("sig-ok", 9, 50).unwrap();
    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64) = connection
        .query_row(
            "SELECT status, observed_at_unix_ms FROM pump_migration_signals WHERE signature='sig-ok'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(row.0, "verified");
    assert_eq!(row.1, 50);

    cleanup_dir(&root);
}

#[test]
fn lifecycle_lookup_is_deterministic_by_detection_signature_and_pool() {
    let root = unique_test_dir("lookup-order");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    for (signature, detected, pool) in [
        ("sig-c", 300, "pool-c"),
        ("sig-b", 100, "pool-z"),
        ("sig-a", 100, "pool-a"),
    ] {
        db.record_pump_migration_signal(signature, 1, detected).unwrap();
        let row = event(signature, "mint-one", "quote", pool, detected);
        db.complete_pump_migration(signature, detected + 1, &[row])
            .unwrap();
    }

    let rows = db.lifecycle_events_for_mint("mint-one").unwrap();
    let order: Vec<_> = rows
        .iter()
        .map(|row| (row.detected_at_unix_ms, row.signature.as_str(), row.pool_address.as_str()))
        .collect();
    assert_eq!(
        order,
        vec![
            (100, "sig-a", "pool-a"),
            (100, "sig-b", "pool-z"),
            (300, "sig-c", "pool-c"),
        ]
    );

    cleanup_dir(&root);
}

#[test]
fn rejection_is_terminal_auditable_and_duplicate_signal_does_not_reset_it() {
    let root = unique_test_dir("reject");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_migration_signal("sig-bad", 7, 100).unwrap();
    db.mark_pump_migration_rejected("sig-bad", 180, "not a verified migration")
        .unwrap();
    db.record_pump_migration_signal("sig-bad", 7, 90).unwrap();

    assert!(db.pending_pump_migration_signals(10).unwrap().is_empty());
    assert!(db
        .complete_pump_migration(
            "sig-bad",
            190,
            &[event("sig-bad", "mint", "quote", "pool", 90)],
        )
        .is_err());

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64, Option<String>, Option<i64>) = connection
        .query_row(
            "SELECT status, observed_at_unix_ms, last_error, last_attempt_at_unix_ms FROM pump_migration_signals WHERE signature='sig-bad'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(row.0, "rejected");
    assert_eq!(row.1, 90);
    assert_eq!(row.2.as_deref(), Some("not a verified migration"));
    assert_eq!(row.3, Some(180));

    cleanup_dir(&root);
}

#[test]
fn invalid_completion_inputs_fail_closed_without_partial_event_rows() {
    let root = unique_test_dir("invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    assert!(db.record_pump_migration_signal("", 1, 100).is_err());
    assert!(db.record_pump_migration_signal("sig-negative", 1, -1).is_err());
    assert!(db
        .complete_pump_migration("unknown", 100, &[event("unknown", "m", "q", "p", 100)])
        .is_err());

    db.record_pump_migration_signal("sig-empty", 1, 100).unwrap();
    assert!(db.complete_pump_migration("sig-empty", 120, &[]).is_err());

    let mut invalid = event("sig-empty", "mint", "quote", "pool", 100);
    invalid.pool_address.clear();
    assert!(db
        .complete_pump_migration("sig-empty", 120, &[invalid])
        .is_err());

    let mut wrong_signature = event("other", "mint", "quote", "pool", 100);
    wrong_signature.occurred_at_unix_ms = None;
    assert!(db
        .complete_pump_migration("sig-empty", 120, &[wrong_signature])
        .is_err());

    let connection = Connection::open(&db_path).unwrap();
    let events: i64 = connection
        .query_row("SELECT COUNT(*) FROM token_lifecycle_events", [], |row| row.get(0))
        .unwrap();
    assert_eq!(events, 0);

    cleanup_dir(&root);
}
