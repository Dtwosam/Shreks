use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fl7-3-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn migration_seventeen_creates_fast_paper_skip_audit_schema_once() {
    let root = unique_test_dir("migration");
    let db_path = root.join("shreks.db");

    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 17);
    drop(db);

    let connection = Connection::open(&db_path).unwrap();
    for table in ["fast_paper_skip_records"] {
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?1",
                [table],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 1, "missing table: {table}");
    }

    for index in [
        "idx_fast_paper_skip_records_future_labels",
        "idx_fast_paper_skip_records_market_time",
    ] {
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' AND name = ?1",
                [index],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 1, "missing index: {index}");
    }

    for trigger in [
        "fast_paper_skip_records_canonical_source_guard",
        "fast_paper_skip_records_restrict_canonical_delete",
    ] {
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger' AND name = ?1",
                [trigger],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 1, "missing trigger: {trigger}");
    }

    let migration_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 17",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(migration_count, 1);
    drop(connection);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.diagnostics().unwrap().schema_version, 17);
    drop(reopened);

    let connection = Connection::open(&db_path).unwrap();
    let migration_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 17",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(migration_count, 1, "migration 17 must remain singular after reopen");

    drop(connection);
    cleanup_dir(&root);
}
