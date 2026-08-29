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
use shreks_storage::{EvidenceWriteOutcome, PumpTradeEvidenceWrite, ShreksDb};

const EVENT_SECONDS: i64 = 1_780_000_000;
const SOURCE_OBSERVED_MS: i64 = 1_780_000_000_100;
const ACCEPTED_MS: i64 = 1_780_000_000_250;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-normalizer-conflict-quarantine-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn verify_decimals(db: &ShreksDb) {
    let candidate_id = db
        .upsert_candidate(&DiscoveredToken {
            mint: "mint-conflict".to_owned(),
            pair_address: None,
            dex_id: Some("pumpfun".to_owned()),
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms: 100,
            source: ProviderId::Chainstack,
        })
        .unwrap();
    db.insert_mint_state(
        candidate_id,
        &TokenMintState {
            provider: ProviderId::Chainstack,
            mint: "mint-conflict".to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1_000_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 123,
            observed_at_unix_ms: SOURCE_OBSERVED_MS - 50,
        },
    )
    .unwrap();
}

fn trade(sol_amount_raw: u64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Chainstack,
        signature: "QuarantinedPumpIdentity111".to_owned(),
        ordinal: 0,
        slot: 500,
        observed_at_unix_ms: SOURCE_OBSERVED_MS,
        mint: "mint-conflict".to_owned(),
        quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
        user: "wallet-conflict".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw,
        quote_amount_raw: sol_amount_raw,
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
fn quarantined_ready_identity_is_not_canonicalized() {
    let root = unique_test_dir("pump");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    verify_decimals(&db);

    let first = trade(2_500_000_000);
    assert_eq!(
        db.record_pump_trade_evidence_or_quarantine(&first).unwrap(),
        EvidenceWriteOutcome::Inserted
    );

    let mut conflict = trade(2_500_000_001);
    conflict.slot += 2;
    conflict.observed_at_unix_ms += 500;
    assert_eq!(
        db.record_pump_trade_evidence_or_quarantine(&conflict)
            .unwrap(),
        EvidenceWriteOutcome::QuarantinedConflict
    );

    let report = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(report.scanned, 0);
    assert_eq!(report.normalized, 0);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);

    let canonical = db
        .fast_events_for_market(
            "mint-conflict",
            shreks_providers::pump::WRAPPED_SOL_MINT,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap();
    assert!(canonical.is_empty());

    cleanup_dir(&root);
}
