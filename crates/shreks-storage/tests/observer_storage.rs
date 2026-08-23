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
        "shreks-observer-storage-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn table_has_column(connection: &Connection, table: &str, column: &str) -> bool {
    let mut statement = connection
        .prepare(&format!("PRAGMA table_info({table})"))
        .unwrap();
    let found = statement
        .query_map([], |row| row.get::<_, String>(1))
        .unwrap()
        .map(Result::unwrap)
        .any(|name| name == column);
    found
}

#[test]
fn migration_two_adds_venue_aware_observer_schema() {
    let root = unique_test_dir("schema");
    let db_path = root.join("shreks.db");

    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 2);
    drop(db);

    let connection = Connection::open(&db_path).unwrap();
    assert!(table_has_column(&connection, "token_candidates", "venue"));

    for column in [
        "venue",
        "pair_address",
        "dex_id",
        "base_mint",
        "quote_mint",
        "price_native",
    ] {
        assert!(
            table_has_column(&connection, "market_snapshots", column),
            "market_snapshots missing normalized column {column}"
        );
    }

    let mint_state_table: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'token_mint_states'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(mint_state_table, 1);

    cleanup_dir(&root);
}

#[test]
fn market_snapshot_identity_allows_multiple_pairs_at_same_observation_time() {
    let root = unique_test_dir("pair-identity");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    connection
        .execute(
            "INSERT INTO token_candidates (mint, pair_address, discovery_source, discovered_at_unix_ms, created_at_unix_ms) VALUES (?1, ?2, ?3, ?4, ?5)",
            ("mint-a", "", "dexscreener", 1_i64, 1_i64),
        )
        .unwrap();
    let candidate_id = connection.last_insert_rowid();

    for pair in ["pair-one", "pair-two"] {
        connection
            .execute(
                "INSERT INTO market_snapshots (candidate_id, observed_at_unix_ms, source, venue, pair_address, dex_id, base_mint, quote_mint) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
                (
                    candidate_id,
                    10_i64,
                    "dexscreener",
                    "pump_swap",
                    pair,
                    "pumpswap",
                    "mint-a",
                    "sol",
                ),
            )
            .unwrap();
    }

    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM market_snapshots WHERE candidate_id = ?1 AND observed_at_unix_ms = 10",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 2);

    cleanup_dir(&root);
}

#[test]
fn provider_health_schema_accepts_rate_limited_state() {
    let root = unique_test_dir("rate-limit");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    connection
        .execute(
            "INSERT INTO provider_health (provider, status, observed_at_unix_ms, consecutive_failures) VALUES (?1, ?2, ?3, ?4)",
            ("jupiter", "rate_limited", 1_i64, 1_i64),
        )
        .unwrap();

    let state: String = connection
        .query_row(
            "SELECT status FROM provider_health WHERE provider = 'jupiter'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(state, "rate_limited");

    cleanup_dir(&root);
}

#[test]
fn token_mint_states_reference_candidates_and_store_u64_fields_as_text() {
    let root = unique_test_dir("mint-states");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    let mut statement = connection
        .prepare("PRAGMA table_info(token_mint_states)")
        .unwrap();
    let columns: Vec<(String, String)> = statement
        .query_map([], |row| Ok((row.get(1)?, row.get(2)?)))
        .unwrap()
        .map(Result::unwrap)
        .collect();

    assert!(columns.iter().any(|(name, ty)| name == "candidate_id" && ty == "INTEGER"));
    assert!(columns.iter().any(|(name, ty)| name == "supply" && ty == "TEXT"));
    assert!(columns.iter().any(|(name, ty)| name == "slot" && ty == "TEXT"));

    let foreign_key_count: i64 = {
        let mut fk = connection
            .prepare("PRAGMA foreign_key_list(token_mint_states)")
            .unwrap();
        let count = fk
            .query_map([], |_| Ok(1_i64))
            .unwrap()
            .map(Result::unwrap)
            .sum();
        count
    };
    assert!(foreign_key_count >= 1);

    cleanup_dir(&root);
}
