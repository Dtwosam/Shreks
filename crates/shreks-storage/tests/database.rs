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
        "shreks-storage-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn open_creates_parent_directory_and_configures_sqlite() {
    let root = unique_test_dir("open");
    let db_path = root.join("nested").join("shreks.db");
    assert!(!db_path.parent().unwrap().exists());

    let db = ShreksDb::open(&db_path).unwrap();
    assert!(db_path.exists());

    let diagnostics = db.diagnostics().unwrap();
    assert_eq!(diagnostics.journal_mode, "wal");
    assert!(diagnostics.foreign_keys_enabled);
    assert_eq!(diagnostics.schema_version, 8);

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn migrations_create_operational_lifecycle_paper_wallet_and_safety_tables() {
    let root = unique_test_dir("tables");
    let db_path = root.join("shreks.db");

    let db = ShreksDb::open(&db_path).unwrap();
    drop(db);

    let connection = Connection::open(&db_path).unwrap();
    for table in [
        "schema_migrations",
        "provider_health",
        "token_candidates",
        "market_snapshots",
        "token_mint_states",
        "raw_observations",
        "ingestion_checkpoints",
        "pump_launch_signals",
        "pump_migration_signals",
        "token_lifecycle_events",
        "candidate_outcome_checkpoints",
        "paper_loop_checkpoints",
        "wallet_observations",
        "token_holder_distributions",
        "exit_quote_snapshots",
    ] {
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
        "idx_paper_loop_checkpoints_run_latest",
        "idx_wallet_observations_mint_time",
        "idx_wallet_observations_wallet_time",
        "idx_wallet_observations_provider_signature",
        "idx_token_holder_distributions_candidate_time",
        "idx_exit_quote_snapshots_candidate_time",
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

    drop(connection);
    cleanup_dir(&root);
}

#[test]
fn reopening_database_does_not_reapply_migrations() {
    let root = unique_test_dir("reopen");
    let db_path = root.join("shreks.db");

    drop(ShreksDb::open(&db_path).unwrap());
    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.diagnostics().unwrap().schema_version, 8);
    drop(reopened);

    let connection = Connection::open(&db_path).unwrap();
    for version in [1_i64, 2_i64, 3_i64, 4_i64, 5_i64, 6_i64, 7_i64, 8_i64] {
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?1",
                [version],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 1, "migration {version} applied more than once");
    }

    drop(connection);
    cleanup_dir(&root);
}
