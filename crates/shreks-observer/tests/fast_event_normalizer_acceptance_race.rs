use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

#[path = "../src/fast_event_normalizer.rs"]
mod fast_event_normalizer;

use fast_event_normalizer::normalize_pending_pump_trade_evidence_at;
use shreks_core::{
    DiscoveredToken, LifecycleEventKind, ProviderId, TokenLifecycleEvent, TokenMintState, VenueId,
};
use shreks_providers::{pump::WRAPPED_SOL_MINT, pump_quote::SYSTEM_SOL_QUOTE_MINT};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
};

const EVENT_SECONDS: i64 = 1_770_000_000;
const ACCEPTED_MS: i64 = 1_770_000_000_250;
const FUTURE_SOURCE_MS: i64 = ACCEPTED_MS + 1;
const PUMPSWAP_POOL: &str = "PumpSwapPoolAcceptanceRace111";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-normalizer-acceptance-race-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms: 100,
        source: ProviderId::SolanaPublic,
    }
}

fn verify_decimals(db: &ShreksDb, mint: &str, decimals: u8) {
    let candidate_id = db.upsert_candidate(&candidate(mint)).unwrap();
    db.insert_mint_state(
        candidate_id,
        &TokenMintState {
            provider: ProviderId::SolanaPublic,
            mint: mint.to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1_000_000_000_000,
            decimals,
            mint_authority: None,
            freeze_authority: None,
            slot: 123,
            observed_at_unix_ms: ACCEPTED_MS - 100,
        },
    )
    .unwrap();
}

fn future_pump_trade(signature: &str) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 123,
        observed_at_unix_ms: FUTURE_SOURCE_MS,
        mint: "mint-a".to_owned(),
        quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
        user: "user-a".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 2_500_000_000,
        timestamp_unix_seconds: EVENT_SECONDS,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 32_000_000_000,
        real_quote_reserves_raw: 10_000_000_000,
        ix_name: "buy".to_owned(),
    }
}

fn future_pump_swap_trade(signature: &str) -> PumpSwapTradeEvidenceWrite {
    let log_index = 17;
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms: FUTURE_SOURCE_MS,
        pool: PUMPSWAP_POOL.to_owned(),
        user: "swap-user-a".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: EVENT_SECONDS,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    }
}

fn verify_pump_swap_market(db: &ShreksDb) {
    let signature = "migration-acceptance-race";
    db.record_pump_migration_signal(signature, 850, ACCEPTED_MS - 200)
        .unwrap();
    db.complete_pump_migration(
        signature,
        ACCEPTED_MS - 100,
        &[TokenLifecycleEvent {
            kind: LifecycleEventKind::PumpGraduation,
            provider: ProviderId::SolanaPublic,
            mint: "mint-a".to_owned(),
            quote_mint: WRAPPED_SOL_MINT.to_owned(),
            from_venue: VenueId::PumpFunBondingCurve,
            to_venue: VenueId::PumpSwap,
            pool_address: PUMPSWAP_POOL.to_owned(),
            signature: signature.to_owned(),
            slot: 850,
            detected_at_unix_ms: ACCEPTED_MS - 200,
            occurred_at_unix_ms: Some(EVENT_SECONDS * 1_000 - 1_000),
        }],
    )
    .unwrap();
}

#[test]
fn pump_row_newer_than_batch_snapshot_waits_for_next_burst() {
    let root = unique_test_dir("pump");
    let db = ShreksDb::open(&root.join("shreks.db")).unwrap();
    verify_decimals(&db, "mint-a", 6);
    db.record_pump_trade_evidence(&future_pump_trade("future-pump"))
        .unwrap();

    let first = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(first.normalized, 0);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);
    assert_eq!(db.pending_pump_trade_evidence(32).unwrap().len(), 1);

    let second =
        normalize_pending_pump_trade_evidence_at(&db, 32, FUTURE_SOURCE_MS + 1).unwrap();
    assert_eq!(second.normalized, 1);
    assert!(db.pending_pump_trade_evidence(32).unwrap().is_empty());

    cleanup_dir(&root);
}

#[test]
fn pumpswap_row_newer_than_batch_snapshot_waits_for_next_burst() {
    let root = unique_test_dir("pumpswap");
    let db = ShreksDb::open(&root.join("shreks.db")).unwrap();
    verify_decimals(&db, "mint-a", 6);
    verify_pump_swap_market(&db);
    db.record_pump_swap_trade_evidence(&future_pump_swap_trade("future-pumpswap"))
        .unwrap();

    let first = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(first.normalized, 0);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);
    assert_eq!(db.pending_pump_swap_trade_evidence(32).unwrap().len(), 1);

    let second =
        normalize_pending_pump_trade_evidence_at(&db, 32, FUTURE_SOURCE_MS + 1).unwrap();
    assert_eq!(second.normalized, 1);
    assert!(db.pending_pump_swap_trade_evidence(32).unwrap().is_empty());

    cleanup_dir(&root);
}
