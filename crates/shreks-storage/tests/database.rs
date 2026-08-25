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
    assert_eq!(diagnostics.schema_version, 9);

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
        "paper_quote_snapshots",
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
        "idx_paper_quote_snapshots_candidate_purpose_time",
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
    assert_eq!(reopened.diagnostics().unwrap().schema_version, 9);
    drop(reopened);

    let connection = Connection::open(&db_path).unwrap();
    for version in [1_i64, 2_i64, 3_i64, 4_i64, 5_i64, 6_i64, 7_i64, 8_i64, 9_i64] {
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

#[test]
fn schema_nine_upgrade_preserves_existing_e14_candidate_and_exit_quote_evidence() {
    let root = unique_test_dir("upgrade-eight-to-nine");
    let db_path = root.join("shreks.db");

    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    connection
        .execute_batch(
            r#"
            INSERT INTO token_candidates (
                mint, pair_address, discovery_source, discovered_at_unix_ms, created_at_unix_ms
            ) VALUES ('LegacyMint111', '', 'helius', 100, 100);

            INSERT INTO exit_quote_snapshots (
                candidate_id, provider, probe_policy_version, input_mint, output_mint, taker,
                input_amount, output_amount, minimum_output_amount, slippage_bps,
                route_available, price_impact_pct, route_labels_json, quoted_at_unix_ms
            )
            SELECT id, 'jupiter', 'probe-v1', 'LegacyMint111',
                   'So11111111111111111111111111111111111111112', 'LegacyTaker111',
                   '1000', '900', '850', 75, 1, '0.01', '["LegacyRoute"]', 200
            FROM token_candidates
            WHERE mint = 'LegacyMint111';

            DROP TABLE paper_quote_snapshots;
            DELETE FROM schema_migrations WHERE version = 9;
            "#,
        )
        .unwrap();
    drop(connection);

    let upgraded = ShreksDb::open(&db_path).unwrap();
    assert_eq!(upgraded.diagnostics().unwrap().schema_version, 9);
    drop(upgraded);

    let connection = Connection::open(&db_path).unwrap();
    let candidate_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM token_candidates WHERE mint = 'LegacyMint111'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(candidate_count, 1);

    let exit_quote_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM exit_quote_snapshots WHERE input_mint = 'LegacyMint111'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(exit_quote_count, 1);

    let paper_quote_table_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'paper_quote_snapshots'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(paper_quote_table_count, 1);

    for version in [8_i64, 9_i64] {
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?1",
                [version],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 1, "migration {version} should remain singular after upgrade");
    }

    drop(connection);
    cleanup_dir(&root);
}
