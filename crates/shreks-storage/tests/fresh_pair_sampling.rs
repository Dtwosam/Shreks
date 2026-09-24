use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, TransactionWindow, VenueId};
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fresh-pair-sampling-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(db: &ShreksDb, mint: &str, discovered_at: i64) -> i64 {
    db.upsert_candidate(&DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: None,
        venue: None,
        discovered_at_unix_ms: discovered_at,
        source: ProviderId::DexScreener,
    })
    .unwrap()
}

fn snapshot(
    mint: &str,
    observed_at: i64,
    pair_created_at: i64,
) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pump_swap".to_owned(),
        pair_address: format!("pair-{mint}-{pair_created_at}"),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some("1.0".to_owned()),
        liquidity_usd: Some(10_000.0),
        volume_5m: Some(1_000.0),
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 1,
            sells: 1,
        }],
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: Some(pair_created_at),
        observed_at_unix_ms: observed_at,
    }
}

#[test]
fn selector_returns_stale_recent_pair_and_rejects_old_current_and_future_pairs() {
    let root = unique_test_dir("selector");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let as_of = 5_000_000;
    let recent_pair = as_of - 300_000;

    let stale_id = candidate(&db, "mint-stale-recent", 0);
    db.insert_market_snapshot(
        stale_id,
        &snapshot("mint-stale-recent", as_of - 300_000, recent_pair),
    )
    .unwrap();

    let current_id = candidate(&db, "mint-current-recent", 0);
    db.insert_market_snapshot(
        current_id,
        &snapshot("mint-current-recent", as_of - 30_000, recent_pair),
    )
    .unwrap();

    let old_id = candidate(&db, "mint-old-pair", 0);
    db.insert_market_snapshot(
        old_id,
        &snapshot("mint-old-pair", as_of - 30_000, as_of - 2_000_000),
    )
    .unwrap();

    let future_id = candidate(&db, "mint-future-pair", 0);
    db.insert_market_snapshot(
        future_id,
        &snapshot("mint-future-pair", as_of - 10_000, as_of + 10_000),
    )
    .unwrap();

    let selected = db
        .fresh_pair_mints_needing_dexscreener_snapshot(
            as_of,
            1_800_000,
            45_000,
            32,
        )
        .unwrap();

    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, stale_id);
    assert_eq!(selected[0].mint, "mint-stale-recent");
    assert_eq!(
        selected[0].newest_pair_created_at_unix_ms,
        recent_pair
    );

    cleanup_dir(&root);
}

#[test]
fn selector_treats_snapshot_at_freshness_floor_as_current() {
    let root = unique_test_dir("freshness-boundary");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let as_of = 5_000_000;
    let candidate_id = candidate(&db, "mint-boundary", 0);
    db.insert_market_snapshot(
        candidate_id,
        &snapshot(
            "mint-boundary",
            as_of - 45_000,
            as_of - 300_000,
        ),
    )
    .unwrap();

    let selected = db
        .fresh_pair_mints_needing_dexscreener_snapshot(
            as_of,
            1_800_000,
            45_000,
            32,
        )
        .unwrap();

    assert!(selected.is_empty());

    cleanup_dir(&root);
}
