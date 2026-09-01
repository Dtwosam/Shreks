use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_storage::ShreksDb;

const EXPECTED_INDEX: &str = "idx_token_lifecycle_events_pumpswap_pool_market";

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pumpswap-lifecycle-pool-index-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn pumpswap_market_lookup_uses_pool_leading_index() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    drop(db);

    let connection = Connection::open(&db_path).unwrap();
    let mut statement = connection
        .prepare(
            r#"EXPLAIN QUERY PLAN
               SELECT DISTINCT mint, quote_mint
               FROM token_lifecycle_events
               WHERE pool_address = 'pool-a'
                 AND event_type = 'pump_graduation'
                 AND to_venue = 'pump_swap'
               ORDER BY mint ASC, quote_mint ASC"#,
        )
        .unwrap();
    let plan = statement
        .query_map([], |row| row.get::<_, String>(3))
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();

    assert!(
        plan.iter().any(|detail| detail.contains(EXPECTED_INDEX)),
        "PumpSwap canonicalization resolves a lifecycle market for every row, so the pool lookup must use the dedicated pool-leading covering index; plan={plan:?}"
    );

    drop(statement);
    drop(connection);
    cleanup_dir(&root);
}
