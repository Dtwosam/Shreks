use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

#[path = "../src/fast_event_normalizer.rs"]
mod fast_event_normalizer;

use fast_event_normalizer::normalize_pending_pump_trade_evidence_at;
use shreks_core::{DiscoveredToken, ProviderId, TokenMintState, VenueId};
use shreks_providers::pump_quote::SYSTEM_SOL_QUOTE_MINT;
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const BASE_MS: i64 = 1_780_000_000_000;
const CURSOR_STREAM: &str = "fast_lane_normalizer_pump_debt_cursor_v1";

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-normalizer-debt-cursor-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw(signature: &str, mint: &str, observed_at_unix_ms: i64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 123,
        observed_at_unix_ms,
        mint: mint.to_owned(),
        quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
        user: "user".to_owned(),
        is_buy: true,
        token_amount_raw: 1_000_000,
        sol_amount_raw: 1_000_000_000,
        quote_amount_raw: 1_000_000_000,
        timestamp_unix_seconds: observed_at_unix_ms / 1000,
        virtual_sol_reserves_raw: 10,
        virtual_token_reserves_raw: 10,
        real_sol_reserves_raw: 10,
        real_token_reserves_raw: 10,
        virtual_quote_reserves_raw: 10,
        real_quote_reserves_raw: 10,
        ix_name: "buy".to_owned(),
    }
}

fn verify_decimals(db: &ShreksDb, mint: &str) {
    let candidate = DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: None,
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms: BASE_MS,
        source: ProviderId::SolanaPublic,
    };
    let candidate_id = db.upsert_candidate(&candidate).unwrap();
    db.insert_mint_state(
        candidate_id,
        &TokenMintState {
            provider: ProviderId::SolanaPublic,
            mint: mint.to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 123,
            observed_at_unix_ms: BASE_MS,
        },
    )
    .unwrap();
}

#[test]
fn production_burst_advances_bounded_debt_cursor_and_keeps_fresh_capacity() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    // Historical rows deliberately lack mint state. The debt lane should inspect
    // a bounded page and advance rather than repeatedly issuing an absolute-oldest
    // ready scan over the durable backlog.
    for i in 0..4 {
        db.record_pump_trade_evidence(&raw(
            &format!("old-{i}"),
            &format!("old-mint-{i}"),
            BASE_MS + i,
        ))
        .unwrap();
    }

    verify_decimals(&db, "fresh-mint");
    db.record_pump_trade_evidence(&raw(
        "fresh-ready",
        "fresh-mint",
        BASE_MS + 10_000,
    ))
    .unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 8, BASE_MS + 20_000).unwrap();
    assert_eq!(report.normalized, 1, "fresh ready evidence must retain capacity");

    let cursor = db
        .ingestion_checkpoint(ProviderId::SolanaPublic, CURSOR_STREAM)
        .unwrap();
    assert!(cursor.is_some(), "production debt lane must durably advance its Pump keyset cursor");

    cleanup_dir(&root);
}
