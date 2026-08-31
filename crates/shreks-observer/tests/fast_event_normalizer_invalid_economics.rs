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
use shreks_providers::pump::WRAPPED_SOL_MINT;
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const EVENT_SECONDS: i64 = 1_780_000_000;
const INVALID_OBSERVED_MS: i64 = 1_780_000_000_100;
const VALID_OBSERVED_MS: i64 = 1_780_000_000_200;
const ACCEPTED_MS: i64 = 1_780_000_000_500;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-normalizer-invalid-economics-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn verify_decimals(db: &ShreksDb, mint: &str, decimals: u8) {
    let candidate_id = db
        .upsert_candidate(&DiscoveredToken {
            mint: mint.to_owned(),
            pair_address: None,
            dex_id: Some("pumpfun".to_owned()),
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms: INVALID_OBSERVED_MS - 100,
            source: ProviderId::SolanaPublic,
        })
        .unwrap();
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
            slot: 499,
            observed_at_unix_ms: INVALID_OBSERVED_MS - 50,
        },
    )
    .unwrap();
}

fn raw_trade(signature: &str, observed_at_unix_ms: i64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 500,
        observed_at_unix_ms,
        mint: "mint-a".to_owned(),
        quote_mint: WRAPPED_SOL_MINT.to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 0,
        timestamp_unix_seconds: EVENT_SECONDS,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: "buy".to_owned(),
    }
}

#[test]
fn zero_quote_raw_evidence_is_retained_noncanonical_and_does_not_block_later_events() {
    let root = unique_test_dir("zero-quote");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    verify_decimals(&db, "mint-a", 6);

    let mut invalid = raw_trade("invalid-zero-quote", INVALID_OBSERVED_MS);
    invalid.sol_amount_raw = 0;
    db.record_pump_trade_evidence(&invalid).unwrap();
    db.record_pump_trade_evidence(&raw_trade("valid-after-invalid", VALID_OBSERVED_MS))
        .unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(report.scanned, 2);
    assert_eq!(report.invalid_economics, 1);
    assert_eq!(report.normalized, 1);
    assert_eq!(report.unresolved_decimals, 0);

    assert_eq!(
        db.pump_trade_evidence_for_signature("invalid-zero-quote")
            .unwrap()
            .len(),
        1,
        "malformed raw evidence must remain immutable and auditable"
    );

    let canonical = db
        .fast_events_for_market(
            "mint-a",
            WRAPPED_SOL_MINT,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap();
    assert_eq!(canonical.len(), 1);
    assert_eq!(canonical[0].event.id.signature, "valid-after-invalid");
    assert_eq!(canonical[0].event.provider, ProviderId::SolanaPublic);
    assert_eq!(canonical[0].event.sequence, 1);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 2);

    let pending = db.pending_pump_trade_evidence(32).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].signature, "invalid-zero-quote");

    let replay = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS + 1).unwrap();
    assert_eq!(replay.scanned, 1);
    assert_eq!(replay.invalid_economics, 1);
    assert_eq!(replay.normalized, 0);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 2);

    cleanup_dir(&root);
}

#[test]
fn zero_base_raw_evidence_is_retained_noncanonical_without_consuming_sequence() {
    let root = unique_test_dir("zero-base");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    verify_decimals(&db, "mint-a", 6);

    let mut invalid = raw_trade("invalid-zero-base", INVALID_OBSERVED_MS);
    invalid.token_amount_raw = 0;
    db.record_pump_trade_evidence(&invalid).unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 32, ACCEPTED_MS).unwrap();
    assert_eq!(report.scanned, 1);
    assert_eq!(report.invalid_economics, 1);
    assert_eq!(report.normalized, 0);
    assert_eq!(report.unresolved_decimals, 0);
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);
    assert!(
        db.fast_events_for_market(
            "mint-a",
            WRAPPED_SOL_MINT,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap()
        .is_empty()
    );

    cleanup_dir(&root);
}
