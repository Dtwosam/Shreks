use std::{fs, path::{Path, PathBuf}, process, time::{SystemTime, UNIX_EPOCH}};

use rusqlite::Connection;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, VenueId};
use shreks_storage::ShreksDb;

#[path = "../src/bin/shreks-paper-evidence/candidate_store.rs"]
mod candidate_store;

use candidate_store::EvidenceCandidateStore;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-paper-evidence-candidate-store-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str, discovered_at_unix_ms: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: Some(format!("Pair-{mint}")),
        dex_id: Some("pumpswap".to_owned()),
        venue: Some(VenueId::PumpSwap),
        discovered_at_unix_ms,
        source: ProviderId::DexScreener,
    }
}

fn snapshot(mint: &str, observed_at_unix_ms: i64) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pumpswap".to_owned(),
        pair_address: format!("Pair-{mint}"),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: None,
        liquidity_usd: None,
        volume_5m: None,
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: Vec::new(),
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: None,
        observed_at_unix_ms,
    }
}

#[test]
fn recent_candidates_are_point_in_time_deduplicated_ordered_and_bounded() {
    let root = unique_test_dir("selection");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let first = db.upsert_candidate(&candidate("MintA", 100)).unwrap();
    let second = db.upsert_candidate(&candidate("MintB", 200)).unwrap();
    let old = db.upsert_candidate(&candidate("MintOld", 300)).unwrap();
    let future = db.upsert_candidate(&candidate("MintFuture", 400)).unwrap();

    db.insert_market_snapshot(first, &snapshot("MintA", 900)).unwrap();
    db.insert_market_snapshot(first, &snapshot("MintA", 950)).unwrap();
    db.insert_market_snapshot(second, &snapshot("MintB", 950)).unwrap();
    db.insert_market_snapshot(old, &snapshot("MintOld", 899)).unwrap();
    db.insert_market_snapshot(future, &snapshot("MintFuture", 1_001)).unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store.recent_candidates(1_000, 100, 10).unwrap();

    assert_eq!(selected.len(), 2);
    assert_eq!(selected[0].candidate_id, first);
    assert_eq!(selected[0].mint, "MintA");
    assert_eq!(selected[0].latest_market_observed_at_unix_ms, 950);
    assert_eq!(selected[1].candidate_id, second);
    assert_eq!(selected[1].mint, "MintB");
    assert_eq!(selected[1].latest_market_observed_at_unix_ms, 950);

    let bounded = store.recent_candidates(1_000, 100, 1).unwrap();
    assert_eq!(bounded.len(), 1);
    assert_eq!(bounded[0].candidate_id, first);
    assert!(store.recent_candidates(1_000, 100, 0).unwrap().is_empty());

    cleanup_dir(&root);
}

#[test]
fn candidate_window_clamps_at_zero_and_includes_lower_boundary() {
    let root = unique_test_dir("zero-boundary");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("MintZero", 0)).unwrap();
    db.insert_market_snapshot(candidate_id, &snapshot("MintZero", 0)).unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store.recent_candidates(50, 100, 10).unwrap();
    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, candidate_id);
    assert_eq!(selected[0].latest_market_observed_at_unix_ms, 0);

    cleanup_dir(&root);
}

#[test]
fn invalid_windows_fail_closed() {
    let root = unique_test_dir("invalid-window");
    let db_path = root.join("shreks.db");
    ShreksDb::open(&db_path).unwrap();
    let store = EvidenceCandidateStore::open(&db_path).unwrap();

    assert!(store
        .recent_candidates(-1, 100, 10)
        .unwrap_err()
        .to_string()
        .contains("as_of_unix_ms"));
    for invalid_lookback in [0, -1] {
        assert!(store
            .recent_candidates(1_000, invalid_lookback, 10)
            .unwrap_err()
            .to_string()
            .contains("lookback_ms"));
    }

    cleanup_dir(&root);
}

#[test]
fn missing_database_is_not_created_by_read_only_open() {
    let root = unique_test_dir("missing-db");
    fs::create_dir_all(&root).unwrap();
    let db_path = root.join("missing.db");

    let error = EvidenceCandidateStore::open(&db_path).unwrap_err();
    assert!(error.to_string().contains("read-only"));
    assert!(!db_path.exists());

    cleanup_dir(&root);
}

#[test]
fn missing_schema_and_malformed_candidate_rows_fail_closed() {
    let root = unique_test_dir("schema");
    fs::create_dir_all(&root).unwrap();

    let missing_market_path = root.join("missing-market.db");
    let connection = Connection::open(&missing_market_path).unwrap();
    connection
        .execute_batch("CREATE TABLE token_candidates (id INTEGER, mint TEXT);")
        .unwrap();
    drop(connection);
    assert!(EvidenceCandidateStore::open(&missing_market_path)
        .unwrap_err()
        .to_string()
        .contains("market_snapshots"));

    let malformed_path = root.join("malformed.db");
    let connection = Connection::open(&malformed_path).unwrap();
    connection
        .execute_batch(
            "CREATE TABLE token_candidates (id INTEGER, mint TEXT);\n\
             CREATE TABLE market_snapshots (candidate_id INTEGER, observed_at_unix_ms INTEGER, source TEXT, pair_created_at_unix_ms INTEGER);\n\
             INSERT INTO token_candidates (id, mint) VALUES (-1, '   ');\n\
             INSERT INTO market_snapshots (candidate_id, observed_at_unix_ms, source, pair_created_at_unix_ms) VALUES (-1, 900, 'dexscreener', NULL);",
        )
        .unwrap();
    drop(connection);

    let store = EvidenceCandidateStore::open(&malformed_path).unwrap();
    assert!(store
        .recent_candidates(1_000, 200, 10)
        .unwrap_err()
        .to_string()
        .contains("candidate"));

    cleanup_dir(&root);
}
