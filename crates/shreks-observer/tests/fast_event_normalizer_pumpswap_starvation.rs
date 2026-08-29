use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

#[path = "../src/fast_event_normalizer.rs"]
mod fast_event_normalizer;

use fast_event_normalizer::normalize_pending_pump_trade_evidence_at;
use shreks_core::{
    DiscoveredToken, LifecycleEventKind, ProviderId, TokenLifecycleEvent, TokenMintState, VenueId,
};
use shreks_providers::pump::WRAPPED_SOL_MINT;
use shreks_storage::{pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, ShreksDb};

const BASE_MS: i64 = 1_770_000_000_000;
const ACCEPTED_MS: i64 = BASE_MS + 100_000;
const READY_MINT: &str = "mint-ready";
const READY_POOL: &str = "pool-ready";

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pumpswap-starvation-{}-{nanos}",
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
            discovered_at_unix_ms: BASE_MS - 1_000,
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
            observed_at_unix_ms: BASE_MS - 900,
        },
    )
    .unwrap();
}

fn verify_ready_market(db: &ShreksDb) {
    let signature = "migration-ready";
    db.record_pump_migration_signal(signature, 850, BASE_MS - 800)
        .unwrap();
    db.complete_pump_migration(
        signature,
        BASE_MS - 700,
        &[TokenLifecycleEvent {
            kind: LifecycleEventKind::PumpGraduation,
            provider: ProviderId::Helius,
            mint: READY_MINT.to_owned(),
            quote_mint: WRAPPED_SOL_MINT.to_owned(),
            from_venue: VenueId::PumpFunBondingCurve,
            to_venue: VenueId::PumpSwap,
            pool_address: READY_POOL.to_owned(),
            signature: signature.to_owned(),
            slot: 850,
            detected_at_unix_ms: BASE_MS - 800,
            occurred_at_unix_ms: Some(BASE_MS - 900),
        }],
    )
    .unwrap();
}

fn swap_row(signature: String, pool: String, observed_at_unix_ms: i64) -> PumpSwapTradeEvidenceWrite {
    let log_index = 17;
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Chainstack,
        signature,
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms,
        pool,
        user: "swap-user".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: BASE_MS / 1_000,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    }
}

#[test]
fn ready_pumpswap_row_at_rank_1071_is_not_starved_by_unmapped_prefix() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    for index in 0..1_070_i64 {
        db.record_pump_swap_trade_evidence(&swap_row(
            format!("sig-unresolved-{index:04}"),
            format!("pool-unmapped-{index:04}"),
            BASE_MS + index,
        ))
        .unwrap();
    }

    verify_decimals(&db, READY_MINT);
    verify_ready_market(&db);
    db.record_pump_swap_trade_evidence(&swap_row(
        "sig-ready-1071".to_owned(),
        READY_POOL.to_owned(),
        BASE_MS + 1_070,
    ))
    .unwrap();

    assert_eq!(db.pending_pump_swap_trade_evidence(2_000).unwrap().len(), 1_071);

    let report = normalize_pending_pump_trade_evidence_at(&db, 1_024, ACCEPTED_MS).unwrap();

    assert_eq!(report.normalized, 1, "the production rank-1071 ready PumpSwap row must be reached");
    let canonical = db
        .fast_events_for_market(READY_MINT, WRAPPED_SOL_MINT, VenueId::PumpSwap)
        .unwrap();
    assert_eq!(canonical.len(), 1);
    assert_eq!(canonical[0].event.id.signature, "sig-ready-1071");

    let _ = fs::remove_dir_all(root);
}
