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
    DiscoveredToken, FastEventKind, LifecycleEventKind, ProviderId, TokenLifecycleEvent,
    TokenMintState, VenueId,
};
use shreks_providers::{pump::WRAPPED_SOL_MINT, pump_quote::SYSTEM_SOL_QUOTE_MINT};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
};

const EVENT_SECONDS: i64 = 1_770_000_000;
const SOURCE_OBSERVED_MS: i64 = 1_770_000_000_100;
const ACCEPTED_MS: i64 = 1_770_000_000_250;
const USDC_MINT: &str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const PUMPSWAP_POOL: &str = "PumpSwapPoolNormalizer111";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-normalizer-{label}-{}-{nanos}",
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
        source: ProviderId::Helius,
    }
}

fn verify_decimals(db: &ShreksDb, mint: &str, decimals: u8) {
    let candidate_id = db.upsert_candidate(&candidate(mint)).unwrap();
    db.insert_mint_state(
        candidate_id,
        &TokenMintState {
            provider: ProviderId::Helius,
            mint: mint.to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1_000_000_000_000,
            decimals,
            mint_authority: None,
            freeze_authority: None,
            slot: 123,
            observed_at_unix_ms: SOURCE_OBSERVED_MS - 50,
        },
    )
    .unwrap();
}

fn raw_trade(signature: &str, quote_mint: &str, is_buy: bool) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 123,
        observed_at_unix_ms: SOURCE_OBSERVED_MS,
        mint: "mint-a".to_owned(),
        quote_mint: quote_mint.to_owned(),
        user: "user-a".to_owned(),
        is_buy,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 1_250_000_000,
        timestamp_unix_seconds: EVENT_SECONDS,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 32_000_000_000,
        real_quote_reserves_raw: 10_000_000_000,
        ix_name: if is_buy { "buy" } else { "sell" }.to_owned(),
    }
}

fn raw_pump_swap_trade(signature: &str, is_buy: bool) -> PumpSwapTradeEvidenceWrite {
    let log_index = 17;
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms: SOURCE_OBSERVED_MS,
        pool: PUMPSWAP_POOL.to_owned(),
        user: "swap-user-a".to_owned(),
        is_buy,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: EVENT_SECONDS,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    }
}

fn verify_pump_swap_market(db: &ShreksDb, signature: &str, quote_mint: &str) {
    db.record_pump_migration_signal(signature, 850, SOURCE_OBSERVED_MS - 200)
        .unwrap();
    db.complete_pump_migration(
        signature,
        SOURCE_OBSERVED_MS - 100,
        &[TokenLifecycleEvent {
            kind: LifecycleEventKind::PumpGraduation,
            provider: ProviderId::Helius,
            mint: "mint-a".to_owned(),
            quote_mint: quote_mint.to_owned(),
            from_venue: VenueId::PumpFunBondingCurve,
            to_venue: VenueId::PumpSwap,
            pool_address: PUMPSWAP_POOL.to_owned(),
            signature: signature.to_owned(),
            slot: 850,
            detected_at_unix_ms: SOURCE_OBSERVED_MS - 200,
            occurred_at_unix_ms: Some(EVENT_SECONDS * 1_000 - 1_000),
        }],
    )
    .unwrap();
}

#[test]
fn sol_quote_normalizes_once_with_verified_base_decimals_and_exact_provenance() {
    let root = unique_test_dir("sol");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    verify_decimals(&db, "mint-a", 6);
    db.record_pump_trade_evidence(&raw_trade("sig-sol", SYSTEM_SOL_QUOTE_MINT, true))
        .unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(report.scanned, 1);
    assert_eq!(report.normalized, 1);
    assert_eq!(report.unresolved_decimals, 0);

    let rows = db
        .fast_events_for_market("mint-a", WRAPPED_SOL_MINT, VenueId::PumpFunBondingCurve)
        .unwrap();
    assert_eq!(rows.len(), 1);
    let stored = &rows[0];
    assert_eq!(stored.event.id.signature, "sig-sol");
    assert_eq!(stored.event.id.ordinal, 0);
    assert_eq!(stored.event.sequence, 1);
    assert_eq!(stored.event.observed_at_unix_ms, ACCEPTED_MS);
    assert_eq!(stored.source_observed_at_unix_ms, SOURCE_OBSERVED_MS);
    assert_eq!(stored.base_decimals, 6);
    assert_eq!(stored.quote_decimals, 9);
    assert!((stored.event.base_quantity - 500.0).abs() < 1e-12);
    assert!((stored.event.quote_quantity - 2.5).abs() < 1e-12);
    assert!((stored.event.price_quote - 0.005).abs() < 1e-12);
    assert!(db.pending_pump_trade_evidence(32).unwrap().is_empty());

    let replay = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS + 1).unwrap();
    assert_eq!(replay.scanned, 0);
    assert_eq!(replay.normalized, 0);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 2);

    cleanup_dir(&root);
}

#[test]
fn alchemy_source_provenance_survives_raw_storage_and_canonical_normalization() {
    let root = unique_test_dir("alchemy");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    verify_decimals(&db, "mint-a", 6);

    let mut raw = raw_trade("sig-alchemy", SYSTEM_SOL_QUOTE_MINT, true);
    raw.provider = ProviderId::Alchemy;
    db.record_pump_trade_evidence(&raw).unwrap();
    assert_eq!(
        db.pump_trade_evidence_for_signature("sig-alchemy")
            .unwrap()[0]
            .provider,
        ProviderId::Alchemy
    );

    let report = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(report.normalized, 1);

    let rows = db
        .fast_events_for_market("mint-a", WRAPPED_SOL_MINT, VenueId::PumpFunBondingCurve)
        .unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].event.provider, ProviderId::Alchemy);
    assert_eq!(rows[0].event.id.signature, "sig-alchemy");

    cleanup_dir(&root);
}

#[test]
fn missing_decimals_remain_pending_without_consuming_sequence() {
    let root = unique_test_dir("pending");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade("sig-pending", SYSTEM_SOL_QUOTE_MINT, true))
        .unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(report.scanned, 1);
    assert_eq!(report.normalized, 0);
    assert_eq!(report.unresolved_decimals, 1);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);
    assert_eq!(db.pending_pump_trade_evidence(32).unwrap().len(), 1);

    verify_decimals(&db, "mint-a", 6);
    let retried = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS + 10).unwrap();
    assert_eq!(retried.normalized, 1);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 2);

    cleanup_dir(&root);
}

#[test]
fn non_sol_quote_requires_its_own_verified_decimals_before_normalization() {
    let root = unique_test_dir("non-sol");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    verify_decimals(&db, "mint-a", 6);
    db.record_pump_trade_evidence(&raw_trade("sig-usdc", USDC_MINT, false))
        .unwrap();

    let pending = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(pending.normalized, 0);
    assert_eq!(pending.unresolved_decimals, 1);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);

    verify_decimals(&db, USDC_MINT, 6);
    let normalized = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS + 10).unwrap();
    assert_eq!(normalized.normalized, 1);

    let rows = db
        .fast_events_for_market("mint-a", USDC_MINT, VenueId::PumpFunBondingCurve)
        .unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].quote_decimals, 6);
    assert!((rows[0].event.quote_quantity - 1_250.0).abs() < 1e-12);
    assert!((rows[0].event.price_quote - 2.5).abs() < 1e-12);

    cleanup_dir(&root);
}

#[test]
fn pumpswap_waits_for_verified_market_then_normalizes_market_quote_with_exact_provenance() {
    let root = unique_test_dir("pumpswap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    verify_decimals(&db, "mint-a", 6);
    let raw = raw_pump_swap_trade("swap-sig", true);
    db.record_pump_swap_trade_evidence(&raw).unwrap();

    let unresolved = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(unresolved.scanned, 1);
    assert_eq!(unresolved.normalized, 0);
    assert_eq!(unresolved.unresolved_decimals, 0);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);
    assert_eq!(db.pending_pump_swap_trade_evidence(32).unwrap(), vec![raw.clone()]);

    verify_pump_swap_market(&db, "migration-pumpswap", WRAPPED_SOL_MINT);
    let normalized = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS + 10).unwrap();
    assert_eq!(normalized.scanned, 1);
    assert_eq!(normalized.normalized, 1);
    assert_eq!(normalized.unresolved_decimals, 0);

    let rows = db
        .fast_events_for_market("mint-a", WRAPPED_SOL_MINT, VenueId::PumpSwap)
        .unwrap();
    assert_eq!(rows.len(), 1);
    let stored = &rows[0];
    assert_eq!(stored.event.id.signature, "swap-sig");
    assert_eq!(stored.event.id.ordinal, raw.ordinal);
    assert_eq!(stored.event.sequence, 1);
    assert_eq!(stored.event.kind, FastEventKind::Buy);
    assert_eq!(stored.event.actor.as_deref(), Some("swap-user-a"));
    assert_eq!(stored.event.slot, 900);
    assert_eq!(stored.event.occurred_at_unix_ms, EVENT_SECONDS * 1_000);
    assert_eq!(stored.event.observed_at_unix_ms, ACCEPTED_MS + 10);
    assert_eq!(stored.source_observed_at_unix_ms, SOURCE_OBSERVED_MS);
    assert_eq!(stored.base_decimals, 6);
    assert_eq!(stored.quote_decimals, 9);
    assert!((stored.event.base_quantity - 500.0).abs() < 1e-12);
    assert!((stored.event.quote_quantity - 2.5).abs() < 1e-12);
    assert!((stored.event.price_quote - 0.005).abs() < 1e-12);
    assert!(db.pending_pump_swap_trade_evidence(32).unwrap().is_empty());
    assert_eq!(db.next_fast_event_sequence().unwrap(), 2);

    cleanup_dir(&root);
}
