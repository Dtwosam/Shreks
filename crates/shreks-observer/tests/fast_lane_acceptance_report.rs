use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::{params, Connection};
use shreks_storage::ShreksDb;

#[path = "../src/bin/shreks-fast-lane-acceptance/report.rs"]
mod report;

use report::{FastLaneAcceptanceStore, LatencySummary};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-acceptance-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn initialize_schema(path: &Path) {
    drop(ShreksDb::open(path).unwrap());
}

fn insert_pump_raw(
    connection: &Connection,
    signature: &str,
    observed_at_unix_ms: i64,
) {
    connection
        .execute(
            r#"INSERT INTO pump_trade_evidence (
                   signature, ordinal, provider, slot, observed_at_unix_ms,
                   mint, quote_mint, user, is_buy,
                   token_amount_raw, sol_amount_raw, quote_amount_raw,
                   timestamp_unix_seconds,
                   virtual_sol_reserves_raw, virtual_token_reserves_raw,
                   real_sol_reserves_raw, real_token_reserves_raw,
                   virtual_quote_reserves_raw, real_quote_reserves_raw, ix_name
               ) VALUES (
                   ?1, 0, 'helius', '55', ?2,
                   'mint-a', 'So11111111111111111111111111111111111111112', 'wallet-a', 1,
                   '2000000', '100000000', '0',
                   1,
                   '10000000000', '20000000000',
                   '5000000000', '10000000000',
                   '0', '0', 'buy'
               )"#,
            params![signature, observed_at_unix_ms],
        )
        .unwrap();
}

fn insert_pumpswap_raw(
    connection: &Connection,
    signature: &str,
    observed_at_unix_ms: i64,
) {
    connection
        .execute(
            r#"INSERT INTO pump_swap_trade_evidence (
                   signature, ordinal, log_index, provider, slot, observed_at_unix_ms,
                   pool, user, is_buy,
                   base_amount_raw, quote_amount_raw, user_quote_amount_raw,
                   timestamp_unix_seconds, pool_base_reserves_raw, pool_quote_reserves_raw
               ) VALUES (
                   ?1, 2147483649, 1, 'helius', '900', ?2,
                   'pool-a', 'wallet-swap', 1,
                   '500000000', '2500000000', '2530000000',
                   1, '9500000000', '52500000000'
               )"#,
            params![signature, observed_at_unix_ms],
        )
        .unwrap();
}

fn insert_fast_event(
    connection: &Connection,
    sequence: i64,
    signature: &str,
    ordinal: i64,
    venue: &str,
    slot: &str,
    source_observed_at_unix_ms: i64,
    observed_at_unix_ms: i64,
) {
    connection
        .execute(
            r#"INSERT INTO fast_events (
                   sequence, signature, ordinal, provider, slot,
                   source_observed_at_unix_ms, occurred_at_unix_ms, observed_at_unix_ms,
                   mint, quote_mint, venue, kind, actor,
                   base_quantity, quote_quantity, price_quote,
                   base_decimals, quote_decimals
               ) VALUES (
                   ?1, ?2, ?3, 'helius', ?4,
                   ?5, 1000, ?6,
                   'mint-a', 'So11111111111111111111111111111111111111112', ?7, 'buy', 'wallet-a',
                   2.0, 0.1, 0.05,
                   6, 9
               )"#,
            params![
                sequence,
                signature,
                ordinal,
                slot,
                source_observed_at_unix_ms,
                observed_at_unix_ms,
                venue
            ],
        )
        .unwrap();
}

fn seeded_database(path: &Path) {
    initialize_schema(path);
    let connection = Connection::open(path).unwrap();

    insert_pump_raw(&connection, "pump-a", 1_100);
    insert_pump_raw(&connection, "pump-b", 1_200);
    insert_pump_raw(&connection, "pump-pending", 1_400);
    insert_pumpswap_raw(&connection, "swap-a", 1_300);

    insert_fast_event(
        &connection,
        1,
        "pump-a",
        0,
        "pump_fun_bonding_curve",
        "55",
        1_100,
        1_150,
    );
    insert_fast_event(
        &connection,
        2,
        "pump-b",
        0,
        "pump_fun_bonding_curve",
        "55",
        1_200,
        1_300,
    );
    insert_fast_event(
        &connection,
        3,
        "swap-a",
        2_147_483_649,
        "pump_swap",
        "900",
        1_300,
        1_500,
    );
}

#[test]
fn missing_database_is_not_created_by_acceptance_open() {
    let root = unique_test_dir("missing");
    let db_path = root.join("missing.db");
    assert!(!db_path.exists());

    assert!(FastLaneAcceptanceStore::open(&db_path).is_err());
    assert!(!db_path.exists(), "read-only acceptance must never create a DB");

    cleanup_dir(&root);
}

#[test]
fn missing_fl1_schema_fails_closed() {
    let root = unique_test_dir("schema");
    fs::create_dir_all(&root).unwrap();
    let db_path = root.join("empty.db");
    drop(Connection::open(&db_path).unwrap());

    assert!(FastLaneAcceptanceStore::open(&db_path).is_err());

    cleanup_dir(&root);
}

#[test]
fn report_counts_backlog_sequence_and_exact_latency_percentiles() {
    let root = unique_test_dir("report");
    let db_path = root.join("shreks.db");
    seeded_database(&db_path);
    let bytes_before = fs::metadata(&db_path).unwrap().len();

    let store = FastLaneAcceptanceStore::open(&db_path).unwrap();
    let acceptance = store.report(1_000, 2_000).unwrap();

    assert_eq!(acceptance.window_start_unix_ms, 1_000);
    assert_eq!(acceptance.as_of_unix_ms, 2_000);
    assert_eq!(acceptance.pump_raw_events, 3);
    assert_eq!(acceptance.pumpswap_raw_events, 1);
    assert_eq!(acceptance.canonical_events, 3);
    assert_eq!(acceptance.pending_pump_events, 1);
    assert_eq!(acceptance.pending_pumpswap_events, 0);
    assert_eq!(acceptance.sequence_integrity_violations, 0);
    assert!(acceptance.database_bytes >= bytes_before);

    assert_eq!(
        acceptance.source_latency,
        LatencySummary {
            samples: 4,
            p50_ms: Some(200),
            p95_ms: Some(400),
            p99_ms: Some(400),
            max_ms: Some(400),
        }
    );
    assert_eq!(
        acceptance.normalization_latency,
        LatencySummary {
            samples: 3,
            p50_ms: Some(100),
            p95_ms: Some(200),
            p99_ms: Some(200),
            max_ms: Some(200),
        }
    );
    assert_eq!(
        acceptance.end_to_end_latency,
        LatencySummary {
            samples: 3,
            p50_ms: Some(300),
            p95_ms: Some(500),
            p99_ms: Some(500),
            max_ms: Some(500),
        }
    );

    drop(store);
    assert_eq!(fs::metadata(&db_path).unwrap().len(), bytes_before);

    cleanup_dir(&root);
}

#[test]
fn invalid_window_and_negative_timing_fail_closed() {
    let root = unique_test_dir("invalid-time");
    let db_path = root.join("shreks.db");
    initialize_schema(&db_path);

    let store = FastLaneAcceptanceStore::open(&db_path).unwrap();
    assert!(store.report(-1, 2_000).is_err());
    assert!(store.report(2_000, 2_000).is_err());
    assert!(store.report(2_001, 2_000).is_err());
    drop(store);

    let connection = Connection::open(&db_path).unwrap();
    insert_pump_raw(&connection, "clock-skew", 900);
    drop(connection);

    let store = FastLaneAcceptanceStore::open(&db_path).unwrap();
    assert!(
        store.report(0, 2_000).is_err(),
        "source observation before chain occurrence must be rejected"
    );

    cleanup_dir(&root);
}

#[test]
fn sequence_gap_is_reported_without_repairing_history() {
    let root = unique_test_dir("sequence-gap");
    let db_path = root.join("shreks.db");
    seeded_database(&db_path);

    let connection = Connection::open(&db_path).unwrap();
    connection
        .execute("UPDATE fast_events SET sequence = 4 WHERE sequence = 3", [])
        .unwrap();
    drop(connection);

    let store = FastLaneAcceptanceStore::open(&db_path).unwrap();
    let acceptance = store.report(1_000, 2_000).unwrap();
    assert_eq!(acceptance.sequence_integrity_violations, 1);

    cleanup_dir(&root);
}
