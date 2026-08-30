use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

#[path = "../src/fast_event_normalizer.rs"]
mod fast_event_normalizer;

use fast_event_normalizer::normalize_pending_pump_trade_evidence_at;
use shreks_core::{
    DiscoveredToken, LifecycleEventKind, ProviderId, TokenLifecycleEvent, TokenMintState, VenueId,
};
use shreks_providers::{
    pump::WRAPPED_SOL_MINT,
    pump_quote::SYSTEM_SOL_QUOTE_MINT,
};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
};

const EVENT_SECONDS: i64 = 1_770_000_000;
const ACCEPTED_MS: i64 = 1_770_000_100_000;

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-starvation-{}-{nanos}",
        process::id()
    ))
}

fn verify_decimals(db: &ShreksDb, mint: &str) {
    let candidate_id = db
        .upsert_candidate(&DiscoveredToken {
            mint: mint.to_owned(),
            pair_address: None,
            dex_id: Some("pumpfun".to_owned()),
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms: 100,
            source: ProviderId::Helius,
        })
        .unwrap();

    db.insert_mint_state(
        candidate_id,
        &TokenMintState {
            provider: ProviderId::Helius,
            mint: mint.to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1_000_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 123,
            observed_at_unix_ms: ACCEPTED_MS - 100,
        },
    )
    .unwrap();
}

fn raw_trade(signature: &str, mint: &str, observed_at_unix_ms: i64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Chainstack,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 123,
        observed_at_unix_ms,
        mint: mint.to_owned(),
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

fn raw_pumpswap_trade(
    signature: &str,
    pool: &str,
    observed_at_unix_ms: i64,
) -> PumpSwapTradeEvidenceWrite {
    let log_index = 17;
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms,
        pool: pool.to_owned(),
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

fn verify_pumpswap_market(
    db: &ShreksDb,
    signal_signature: &str,
    mint: &str,
    pool: &str,
    detected_at_unix_ms: i64,
) {
    db.record_pump_migration_signal(signal_signature, 850, detected_at_unix_ms)
        .unwrap();
    db.complete_pump_migration(
        signal_signature,
        detected_at_unix_ms + 1,
        &[TokenLifecycleEvent {
            kind: LifecycleEventKind::PumpGraduation,
            provider: ProviderId::SolanaPublic,
            mint: mint.to_owned(),
            quote_mint: WRAPPED_SOL_MINT.to_owned(),
            from_venue: VenueId::PumpFunBondingCurve,
            to_venue: VenueId::PumpSwap,
            pool_address: pool.to_owned(),
            signature: signal_signature.to_owned(),
            slot: 850,
            detected_at_unix_ms,
            occurred_at_unix_ms: Some(EVENT_SECONDS * 1_000 - 1_000),
        }],
    )
    .unwrap();
}

#[test]
fn unresolved_oldest_row_does_not_starve_newer_ready_row() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_trade_evidence(&raw_trade(
        "sig-unresolved-oldest",
        "mint-without-decimals",
        ACCEPTED_MS - 2_000,
    ))
    .unwrap();

    verify_decimals(&db, "mint-ready");
    db.record_pump_trade_evidence(&raw_trade(
        "sig-ready-newer",
        "mint-ready",
        ACCEPTED_MS - 1_000,
    ))
    .unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 1, ACCEPTED_MS).unwrap();

    assert_eq!(report.normalized, 1, "a bounded unresolved prefix must not block later ready evidence");
    let ready = db
        .fast_events_for_market(
            "mint-ready",
            WRAPPED_SOL_MINT,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap();
    assert_eq!(ready.len(), 1);
    assert_eq!(ready[0].event.id.signature, "sig-ready-newer");

    assert_eq!(db.pending_pump_trade_evidence(32).unwrap().len(), 1);
    assert_eq!(
        db.pending_pump_trade_evidence(32).unwrap()[0].signature,
        "sig-unresolved-oldest"
    );

    let _ = fs::remove_dir_all(root);
}

#[test]
fn deep_unresolved_frontier_does_not_hide_fresh_ready_trade() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    // The production normalizer historically searched at most 8x its requested
    // output limit. Put a ready event beyond that frontier to prove old missing
    // metadata cannot indefinitely hide fresh usable market evidence.
    for index in 0..12_i64 {
        db.record_pump_trade_evidence(&raw_trade(
            &format!("sig-unresolved-{index:02}"),
            &format!("mint-without-decimals-{index:02}"),
            ACCEPTED_MS - 20_000 + index,
        ))
        .unwrap();
    }

    verify_decimals(&db, "mint-ready-deep");
    db.record_pump_trade_evidence(&raw_trade(
        "sig-ready-after-deep-frontier",
        "mint-ready-deep",
        ACCEPTED_MS - 1_000,
    ))
    .unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 1, ACCEPTED_MS).unwrap();
    assert_eq!(
        report.normalized, 1,
        "fresh ready evidence must not be hidden behind an arbitrarily deep unresolved prefix"
    );

    let ready = db
        .fast_events_for_market(
            "mint-ready-deep",
            WRAPPED_SOL_MINT,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap();
    assert_eq!(ready.len(), 1);
    assert_eq!(ready[0].event.id.signature, "sig-ready-after-deep-frontier");
    assert_eq!(ready[0].source_observed_at_unix_ms, ACCEPTED_MS - 1_000);
    assert_eq!(
        ready[0].event.observed_at_unix_ms, ACCEPTED_MS,
        "canonical observation time must remain the later normalization time"
    );

    assert_eq!(
        db.pending_pump_trade_evidence(64).unwrap().len(),
        12,
        "unresolved history must remain durable for later completion"
    );

    let _ = fs::remove_dir_all(root);
}

#[test]
fn deep_unmapped_pumpswap_frontier_does_not_hide_ready_trade() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    for index in 0..12_i64 {
        db.record_pump_swap_trade_evidence(&raw_pumpswap_trade(
            &format!("swap-unmapped-{index:02}"),
            &format!("pool-unmapped-{index:02}"),
            ACCEPTED_MS - 20_000 + index,
        ))
        .unwrap();
    }

    let ready_mint = "mint-ready-pumpswap";
    let ready_pool = "pool-ready-pumpswap";
    verify_decimals(&db, ready_mint);
    verify_pumpswap_market(
        &db,
        "migration-ready-pumpswap",
        ready_mint,
        ready_pool,
        ACCEPTED_MS - 1_500,
    );
    db.record_pump_swap_trade_evidence(&raw_pumpswap_trade(
        "swap-ready-after-deep-frontier",
        ready_pool,
        ACCEPTED_MS - 1_000,
    ))
    .unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 1, ACCEPTED_MS).unwrap();
    assert_eq!(
        report.normalized, 1,
        "verified PumpSwap evidence must not be hidden behind an arbitrarily deep unmapped pool prefix"
    );

    let ready = db
        .fast_events_for_market(ready_mint, WRAPPED_SOL_MINT, VenueId::PumpSwap)
        .unwrap();
    assert_eq!(ready.len(), 1);
    assert_eq!(ready[0].event.id.signature, "swap-ready-after-deep-frontier");
    assert_eq!(ready[0].source_observed_at_unix_ms, ACCEPTED_MS - 1_000);
    assert_eq!(ready[0].event.observed_at_unix_ms, ACCEPTED_MS);

    assert_eq!(
        db.pending_pump_swap_trade_evidence(64).unwrap().len(),
        12,
        "unmapped PumpSwap history must remain durable for later lifecycle completion"
    );

    let _ = fs::remove_dir_all(root);
}
