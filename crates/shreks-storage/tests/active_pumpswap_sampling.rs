use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::{params, Connection};
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, TransactionWindow, VenueId,
};
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-active-pumpswap-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn insert_fast_event(
    db_path: &Path,
    sequence: i64,
    mint: &str,
    venue: &str,
    observed_at_unix_ms: i64,
) {
    let connection = Connection::open(db_path).unwrap();
    let signature = format!("sig-{sequence}");
    let log_index = sequence;
    let ordinal = 2_147_483_648_i64 + log_index;

    if venue == "pump_swap" {
        connection
            .execute(
                r#"INSERT INTO pump_swap_trade_evidence (
                       signature, ordinal, log_index, provider, slot,
                       observed_at_unix_ms, pool, user, is_buy,
                       base_amount_raw, quote_amount_raw, user_quote_amount_raw,
                       timestamp_unix_seconds, pool_base_reserves_raw,
                       pool_quote_reserves_raw
                   ) VALUES (
                       ?1, ?2, ?3, 'solana_public', '1',
                       ?4, 'test-pool', 'actor', 1,
                       '1000000', '1000000000', '1000000000',
                       ?5, '1000000', '1000000000'
                   )"#,
                params![
                    signature,
                    ordinal,
                    log_index,
                    observed_at_unix_ms,
                    observed_at_unix_ms / 1000,
                ],
            )
            .unwrap();
    } else {
        connection
            .execute(
                r#"INSERT INTO pump_trade_evidence (
                       signature, ordinal, provider, slot,
                       observed_at_unix_ms, mint, quote_mint, user, is_buy,
                       token_amount_raw, sol_amount_raw, quote_amount_raw,
                       timestamp_unix_seconds, virtual_sol_reserves_raw,
                       virtual_token_reserves_raw, real_sol_reserves_raw,
                       real_token_reserves_raw, virtual_quote_reserves_raw,
                       real_quote_reserves_raw, ix_name
                   ) VALUES (
                       ?1, 0, 'solana_public', '1',
                       ?2, ?3,
                       'So11111111111111111111111111111111111111112',
                       'actor', 1, '1000000', '1000000000', '1000000000',
                       ?4, '1000000000', '1000000', '1000000000',
                       '1000000', '1000000000', '1000000000', 'buy'
                   )"#,
                params![
                    signature,
                    observed_at_unix_ms,
                    mint,
                    observed_at_unix_ms / 1000,
                ],
            )
            .unwrap();
    }

    connection
        .execute(
            r#"INSERT INTO fast_events (
                   sequence, signature, ordinal, provider, slot,
                   source_observed_at_unix_ms, occurred_at_unix_ms,
                   observed_at_unix_ms, mint, quote_mint, venue, kind,
                   actor, base_quantity, quote_quantity, price_quote,
                   base_decimals, quote_decimals
               ) VALUES (
                   ?1, ?2, ?3, 'solana_public', '1',
                   ?4, ?4, ?4, ?5,
                   'So11111111111111111111111111111111111111112',
                   ?6, 'buy', 'actor', 1.0, 1.0, 1.0, 6, 9
               )"#,
            params![
                sequence,
                signature,
                if venue == "pump_swap" { ordinal } else { 0 },
                observed_at_unix_ms,
                mint,
                venue,
            ],
        )
        .unwrap();
}

fn snapshot(mint: &str, at: i64) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pump_swap".to_owned(),
        pair_address: format!("pair-{mint}"),
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
        volume_24h: Some(25_000.0),
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 1,
            sells: 1,
        }],
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: Some(0),
        observed_at_unix_ms: at,
    }
}

#[test]
fn selector_returns_recent_pumpswap_mints_without_fresh_dex_snapshot() {
    let root = unique_test_dir("selector");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let as_of = 100_000;
    insert_fast_event(&db_path, 1, "mint-stale", "pump_swap", 95_000);
    insert_fast_event(&db_path, 2, "mint-fresh", "pump_swap", 96_000);
    insert_fast_event(&db_path, 3, "mint-newest", "pump_swap", 99_000);
    insert_fast_event(
        &db_path,
        4,
        "mint-bonding",
        "pump_fun_bonding_curve",
        99_500,
    );
    insert_fast_event(&db_path, 5, "mint-old", "pump_swap", 30_000);

    let fresh_candidate = db
        .upsert_candidate(&DiscoveredToken {
            mint: "mint-fresh".to_owned(),
            pair_address: None,
            dex_id: None,
            venue: Some(VenueId::PumpSwap),
            discovered_at_unix_ms: 0,
            source: ProviderId::DexScreener,
        })
        .unwrap();
    db.insert_market_snapshot(
        fresh_candidate,
        &snapshot("mint-fresh", 80_000),
    )
    .unwrap();

    let selected = db
        .active_pump_swap_mints_needing_dexscreener_snapshot(
            as_of,
            60_000,
            45_000,
            32,
        )
        .unwrap();

    assert_eq!(
        selected
            .iter()
            .map(|row| (row.mint.as_str(), row.last_event_at_unix_ms))
            .collect::<Vec<_>>(),
        vec![
            ("mint-newest", 99_000),
            ("mint-stale", 95_000),
        ]
    );

    cleanup_dir(&root);
}

#[test]
fn selector_treats_snapshot_at_freshness_floor_as_fresh() {
    let root = unique_test_dir("freshness-boundary");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let as_of = 100_000;
    insert_fast_event(&db_path, 1, "mint-boundary", "pump_swap", 99_000);

    let candidate_id = db
        .upsert_candidate(&DiscoveredToken {
            mint: "mint-boundary".to_owned(),
            pair_address: None,
            dex_id: None,
            venue: Some(VenueId::PumpSwap),
            discovered_at_unix_ms: 0,
            source: ProviderId::DexScreener,
        })
        .unwrap();
    db.insert_market_snapshot(
        candidate_id,
        &snapshot("mint-boundary", 55_000),
    )
    .unwrap();

    let selected = db
        .active_pump_swap_mints_needing_dexscreener_snapshot(
            as_of,
            60_000,
            45_000,
            32,
        )
        .unwrap();

    assert!(selected.is_empty());

    cleanup_dir(&root);
}
