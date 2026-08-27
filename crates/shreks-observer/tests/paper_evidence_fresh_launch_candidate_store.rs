use std::{fs, path::{Path, PathBuf}, process, time::{SystemTime, UNIX_EPOCH}};

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
        "shreks-paper-evidence-fresh-launch-{label}-{}-{nanos}",
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

fn snapshot(mint: &str, observed_at_unix_ms: i64, pair_created_at_unix_ms: i64) -> PairMarketData {
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
        pair_created_at_unix_ms: Some(pair_created_at_unix_ms),
        observed_at_unix_ms,
    }
}

#[test]
fn fresh_launch_candidates_prioritize_entry_window_then_too_young_and_exclude_expired() {
    const AS_OF: i64 = 2_000_000;
    const MAX_PAIR_AGE_MS: i64 = 1_800_000;
    const PREFERRED_MIN_PAIR_AGE_MS: i64 = 60_000;

    let root = unique_test_dir("priority");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let expired = db.upsert_candidate(&candidate("MintExpired", 100)).unwrap();
    let too_young = db.upsert_candidate(&candidate("MintTooYoung", 200)).unwrap();
    let in_window = db.upsert_candidate(&candidate("MintInWindow", 300)).unwrap();

    db.insert_market_snapshot(
        expired,
        &snapshot("MintExpired", AS_OF - 100, AS_OF - 1_900_000),
    )
    .unwrap();
    db.insert_market_snapshot(
        too_young,
        &snapshot("MintTooYoung", AS_OF - 200, AS_OF - 30_000),
    )
    .unwrap();
    db.insert_market_snapshot(
        in_window,
        &snapshot("MintInWindow", AS_OF - 300, AS_OF - 600_000),
    )
    .unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store
        .fresh_launch_candidates(
            AS_OF,
            MAX_PAIR_AGE_MS,
            PREFERRED_MIN_PAIR_AGE_MS,
            2,
        )
        .unwrap();

    assert_eq!(selected.len(), 2);
    assert_eq!(selected[0].candidate_id, in_window);
    assert_eq!(selected[0].mint, "MintInWindow");
    assert_eq!(selected[1].candidate_id, too_young);
    assert_eq!(selected[1].mint, "MintTooYoung");
    assert!(selected.iter().all(|item| item.candidate_id != expired));

    cleanup_dir(&root);
}

#[test]
fn fresh_launch_candidates_use_too_young_when_entry_window_is_empty() {
    const AS_OF: i64 = 2_000_000;

    let root = unique_test_dir("fallback");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let expired = db.upsert_candidate(&candidate("MintExpired", 100)).unwrap();
    let too_young = db.upsert_candidate(&candidate("MintTooYoung", 200)).unwrap();

    db.insert_market_snapshot(
        expired,
        &snapshot("MintExpired", AS_OF - 100, AS_OF - 1_900_000),
    )
    .unwrap();
    db.insert_market_snapshot(
        too_young,
        &snapshot("MintTooYoung", AS_OF - 200, AS_OF - 30_000),
    )
    .unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store
        .fresh_launch_candidates(AS_OF, 1_800_000, 60_000, 2)
        .unwrap();

    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, too_young);
    assert_eq!(selected[0].mint, "MintTooYoung");

    cleanup_dir(&root);
}
