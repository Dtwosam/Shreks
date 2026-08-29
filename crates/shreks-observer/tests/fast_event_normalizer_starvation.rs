use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

#[path = "../src/fast_event_normalizer.rs"]
mod fast_event_normalizer;

use fast_event_normalizer::normalize_pending_pump_trade_evidence_at;
use shreks_core::{DiscoveredToken, ProviderId, TokenMintState, VenueId};
use shreks_providers::pump_quote::SYSTEM_SOL_QUOTE_MINT;
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

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
            shreks_providers::pump::WRAPPED_SOL_MINT,
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
