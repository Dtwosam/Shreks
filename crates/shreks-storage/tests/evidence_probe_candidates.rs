use std::{fs, path::{Path, PathBuf}, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, VenueId};
use shreks_storage::{ShreksDb, StorageError};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-evidence-probe-candidates-{label}-{}-{nanos}",
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
fn recent_evidence_probe_candidates_are_point_in_time_deduplicated_ordered_and_bounded() {
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

    let selected = db
        .recent_evidence_probe_candidates(1_000, 100, 10)
        .unwrap();

    assert_eq!(selected.len(), 2);
    assert_eq!(selected[0].candidate_id, first);
    assert_eq!(selected[0].mint, "MintA");
    assert_eq!(selected[0].latest_market_observed_at_unix_ms, 950);
    assert_eq!(selected[1].candidate_id, second);
    assert_eq!(selected[1].mint, "MintB");
    assert_eq!(selected[1].latest_market_observed_at_unix_ms, 950);

    let bounded = db
        .recent_evidence_probe_candidates(1_000, 100, 1)
        .unwrap();
    assert_eq!(bounded.len(), 1);
    assert_eq!(bounded[0].candidate_id, first);

    assert!(db
        .recent_evidence_probe_candidates(1_000, 100, 0)
        .unwrap()
        .is_empty());

    cleanup_dir(&root);
}

#[test]
fn evidence_probe_candidate_window_clamps_at_zero_and_includes_boundaries() {
    let root = unique_test_dir("zero-boundary");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let candidate_id = db.upsert_candidate(&candidate("MintZero", 0)).unwrap();
    db.insert_market_snapshot(candidate_id, &snapshot("MintZero", 0))
        .unwrap();

    let selected = db
        .recent_evidence_probe_candidates(50, 100, 10)
        .unwrap();
    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, candidate_id);
    assert_eq!(selected[0].latest_market_observed_at_unix_ms, 0);

    cleanup_dir(&root);
}

#[test]
fn invalid_evidence_probe_candidate_windows_fail_closed() {
    let root = unique_test_dir("invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let negative_as_of = db
        .recent_evidence_probe_candidates(-1, 100, 10)
        .unwrap_err();
    assert!(matches!(
        negative_as_of,
        StorageError::InvalidData(message) if message.contains("as_of_unix_ms")
    ));

    for invalid_lookback in [0, -1] {
        let error = db
            .recent_evidence_probe_candidates(1_000, invalid_lookback, 10)
            .unwrap_err();
        assert!(matches!(
            error,
            StorageError::InvalidData(message) if message.contains("lookback_ms")
        ));
    }

    cleanup_dir(&root);
}
