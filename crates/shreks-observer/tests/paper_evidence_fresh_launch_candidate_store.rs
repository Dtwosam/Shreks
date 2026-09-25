use std::{fs, path::{Path, PathBuf}, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, TokenMintState, VenueId};
use shreks_storage::ShreksDb;

#[path = "../src/bin/shreks-paper-evidence/candidate_store.rs"]
mod candidate_store;

use candidate_store::EvidenceCandidateStore;

const WSOL: &str = "So11111111111111111111111111111111111111112";
const USDC: &str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

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

fn snapshot_from(
    provider: ProviderId,
    mint: &str,
    observed_at_unix_ms: i64,
    pair_created_at_unix_ms: i64,
) -> PairMarketData {
    PairMarketData {
        provider,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pumpswap".to_owned(),
        pair_address: format!("Pair-{mint}"),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: WSOL.to_owned(),
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

fn snapshot(mint: &str, observed_at_unix_ms: i64, pair_created_at_unix_ms: i64) -> PairMarketData {
    snapshot_from(
        ProviderId::DexScreener,
        mint,
        observed_at_unix_ms,
        pair_created_at_unix_ms,
    )
}

fn snapshot_with_quote(
    mint: &str,
    quote_mint: &str,
    observed_at_unix_ms: i64,
    pair_created_at_unix_ms: i64,
) -> PairMarketData {
    let mut value = snapshot(mint, observed_at_unix_ms, pair_created_at_unix_ms);
    value.quote_mint = quote_mint.to_owned();
    value
}

fn dex_sources() -> Vec<String> {
    vec!["dexscreener".to_owned()]
}

#[test]
fn fresh_launch_candidates_prioritize_entry_window_then_too_young_and_exclude_expired() {
    const AS_OF: i64 = 2_000_000;
    const MARKET_LOOKBACK_MS: i64 = 60_000;
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
            MARKET_LOOKBACK_MS,
            MAX_PAIR_AGE_MS,
            PREFERRED_MIN_PAIR_AGE_MS,
            &dex_sources(),
            WSOL,
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
fn fresh_launch_candidates_prioritize_missing_mint_first_hydration_before_limit() {
    const AS_OF: i64 = 2_000_000;
    const MARKET_LOOKBACK_MS: i64 = 60_000;
    const MAX_PAIR_AGE_MS: i64 = 1_800_000;
    const PREFERRED_MIN_PAIR_AGE_MS: i64 = 60_000;

    let root = unique_test_dir("mint-first-hydration");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let mature_a = db.upsert_candidate(&candidate("MintMatureA", 100)).unwrap();
    let mature_b = db.upsert_candidate(&candidate("MintMatureB", 200)).unwrap();
    let prewarm = db.upsert_candidate(&candidate("MintPrewarm", 300)).unwrap();

    db.insert_market_snapshot(
        mature_a,
        &snapshot("MintMatureA", AS_OF - 100, AS_OF - 600_000),
    ).unwrap();
    db.insert_market_snapshot(
        mature_b,
        &snapshot("MintMatureB", AS_OF - 200, AS_OF - 500_000),
    ).unwrap();
    db.insert_market_snapshot(
        prewarm,
        &snapshot("MintPrewarm", AS_OF - 300, AS_OF - 30_000),
    ).unwrap();

    for (candidate_id, mint, slot) in [
        (mature_a, "MintMatureA", 101_u64),
        (mature_b, "MintMatureB", 102_u64),
    ] {
        db.insert_mint_state(
            candidate_id,
            &TokenMintState {
                provider: ProviderId::Helius,
                mint: mint.to_owned(),
                owner_program: "Tokenkeg1111111111111111111111111111111111".to_owned(),
                supply: 1_000_000_000,
                decimals: 6,
                mint_authority: None,
                freeze_authority: None,
                slot,
                observed_at_unix_ms: AS_OF - 1_000,
            },
        ).unwrap();
    }
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store.fresh_launch_candidates(
        AS_OF,
        MARKET_LOOKBACK_MS,
        MAX_PAIR_AGE_MS,
        PREFERRED_MIN_PAIR_AGE_MS,
        &dex_sources(),
        WSOL,
        2,
    ).unwrap();

    assert_eq!(selected.len(), 2);
    assert_eq!(selected[0].candidate_id, prewarm);
    assert!(selected.iter().any(|item| item.candidate_id == prewarm));

    cleanup_dir(&root);
}

#[test]
fn future_helius_mint_state_does_not_satisfy_first_hydration_readiness() {
    const AS_OF: i64 = 2_000_000;

    let root = unique_test_dir("future-mint-readiness");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let hydrated = db.upsert_candidate(&candidate("MintHydrated", 100)).unwrap();
    let future_only = db.upsert_candidate(&candidate("MintFutureOnly", 200)).unwrap();

    db.insert_market_snapshot(
        hydrated,
        &snapshot("MintHydrated", AS_OF - 1_000, AS_OF - 600_000),
    )
    .unwrap();
    db.insert_market_snapshot(
        future_only,
        &snapshot("MintFutureOnly", AS_OF - 2_000, AS_OF - 30_000),
    )
    .unwrap();

    db.insert_mint_state(
        hydrated,
        &TokenMintState {
            provider: ProviderId::Helius,
            mint: "MintHydrated".to_owned(),
            owner_program: "Tokenkeg1111111111111111111111111111111111".to_owned(),
            supply: 1_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 100,
            observed_at_unix_ms: AS_OF - 5_000,
        },
    )
    .unwrap();
    db.insert_mint_state(
        future_only,
        &TokenMintState {
            provider: ProviderId::Helius,
            mint: "MintFutureOnly".to_owned(),
            owner_program: "Tokenkeg1111111111111111111111111111111111".to_owned(),
            supply: 1_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 101,
            observed_at_unix_ms: AS_OF + 1,
        },
    )
    .unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store
        .fresh_launch_candidates(
            AS_OF,
            60_000,
            1_800_000,
            60_000,
            &dex_sources(),
            WSOL,
            1,
        )
        .unwrap();

    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, future_only);

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
        .fresh_launch_candidates(
            AS_OF,
            60_000,
            1_800_000,
            60_000,
            &dex_sources(),
            WSOL,
            2,
        )
        .unwrap();

    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, too_young);
    assert_eq!(selected[0].mint, "MintTooYoung");

    cleanup_dir(&root);
}

#[test]
fn fresh_launch_candidates_skip_stale_or_disallowed_market_sources() {
    const AS_OF: i64 = 2_000_000;

    let root = unique_test_dir("market-contract");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let eligible = db.upsert_candidate(&candidate("MintEligible", 100)).unwrap();
    let stale = db.upsert_candidate(&candidate("MintStale", 200)).unwrap();
    let wrong_source = db.upsert_candidate(&candidate("MintWrongSource", 300)).unwrap();

    db.insert_market_snapshot(
        eligible,
        &snapshot("MintEligible", AS_OF - 10_000, AS_OF - 600_000),
    )
    .unwrap();
    db.insert_market_snapshot(
        stale,
        &snapshot("MintStale", AS_OF - 61_000, AS_OF - 500_000),
    )
    .unwrap();
    db.insert_market_snapshot(
        wrong_source,
        &snapshot_from(
            ProviderId::Meteora,
            "MintWrongSource",
            AS_OF - 100,
            AS_OF - 400_000,
        ),
    )
    .unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store
        .fresh_launch_candidates(
            AS_OF,
            60_000,
            1_800_000,
            60_000,
            &dex_sources(),
            WSOL,
            3,
        )
        .unwrap();

    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, eligible);
    assert_eq!(selected[0].mint, "MintEligible");

    cleanup_dir(&root);
}


#[test]
fn fresh_launch_candidates_use_current_pair_instead_of_requiring_uniform_pair_history() {
    const AS_OF: i64 = 2_000_000;

    let root = unique_test_dir("multi-pair-current-row");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let candidate_id = db
        .upsert_candidate(&candidate("MintMultiPair", 100))
        .unwrap();

    db.insert_market_snapshot(
        candidate_id,
        &snapshot(
            "MintMultiPair",
            AS_OF - 40_000,
            AS_OF - 900_000,
        ),
    )
    .unwrap();
    db.insert_market_snapshot(
        candidate_id,
        &snapshot(
            "MintMultiPair",
            AS_OF - 10_000,
            AS_OF - 300_000,
        ),
    )
    .unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store
        .fresh_launch_candidates(
            AS_OF,
            60_000,
            1_800_000,
            60_000,
            &dex_sources(),
            WSOL,
            2,
        )
        .unwrap();

    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, candidate_id);
    assert_eq!(selected[0].mint, "MintMultiPair");
    assert_eq!(
        selected[0].latest_market_observed_at_unix_ms,
        AS_OF - 10_000
    );

    cleanup_dir(&root);
}


#[test]
fn fresh_launch_candidates_filter_quote_identity_before_applying_limit() {
    const AS_OF: i64 = 2_000_000;

    let root = unique_test_dir("quote-before-limit");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let wrong_quote = db
        .upsert_candidate(&candidate("MintWrongQuote", 100))
        .unwrap();
    let exact_quote = db
        .upsert_candidate(&candidate("MintExactQuote", 200))
        .unwrap();

    db.insert_market_snapshot(
        wrong_quote,
        &snapshot_with_quote(
            "MintWrongQuote",
            USDC,
            AS_OF - 1_000,
            AS_OF - 600_000,
        ),
    )
    .unwrap();
    db.insert_market_snapshot(
        exact_quote,
        &snapshot_with_quote(
            "MintExactQuote",
            WSOL,
            AS_OF - 2_000,
            AS_OF - 600_000,
        ),
    )
    .unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    let selected = store
        .fresh_launch_candidates(
            AS_OF,
            60_000,
            1_800_000,
            60_000,
            &dex_sources(),
            WSOL,
            1,
        )
        .unwrap();

    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].candidate_id, exact_quote);
    assert_eq!(selected[0].mint, "MintExactQuote");

    cleanup_dir(&root);
}
