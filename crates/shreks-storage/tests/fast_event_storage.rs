use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    DiscoveredToken, FastEvent, FastEventId, FastEventKind, FastMarketKey, ProviderId,
    TokenMintState, VenueId,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb, StorageError, StoredFastEvent};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-storage-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw_trade(signature: &str, ordinal: u32, observed_at_unix_ms: i64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal,
        slot: 55,
        observed_at_unix_ms,
        mint: "mint-a".to_owned(),
        quote_mint: WSOL.to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        token_amount_raw: 2_000_000,
        sol_amount_raw: 100_000_000,
        quote_amount_raw: 0,
        timestamp_unix_seconds: 1,
        virtual_sol_reserves_raw: 10_000_000_000,
        virtual_token_reserves_raw: 20_000_000_000,
        real_sol_reserves_raw: 5_000_000_000,
        real_token_reserves_raw: 10_000_000_000,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: "buy".to_owned(),
    }
}

fn fast_event(signature: &str, ordinal: u32, sequence: u64, observed_at_unix_ms: i64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, ordinal).unwrap(),
        sequence,
        ProviderId::Helius,
        FastMarketKey::new("mint-a", WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        55,
        1_000,
        observed_at_unix_ms,
        2.0,
        0.1,
        0.05,
    )
    .unwrap()
}

fn candidate(mint: &str, pair: &str) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: Some(pair.to_owned()),
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms: 10,
        source: ProviderId::DexScreener,
    }
}

fn mint_state(mint: &str, decimals: u8, slot: u64) -> TokenMintState {
    TokenMintState {
        provider: ProviderId::Helius,
        mint: mint.to_owned(),
        owner_program: "TokenProgram".to_owned(),
        supply: 1_000_000_000,
        decimals,
        mint_authority: None,
        freeze_authority: None,
        slot,
        observed_at_unix_ms: i64::try_from(slot).unwrap(),
    }
}

#[test]
fn canonical_fast_event_sequence_is_stable_restart_safe_and_replay_ordered() {
    let root = unique_test_dir("restart");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 12);

    let raw_one = raw_trade("sig-a", 0, 1_100);
    let raw_two = raw_trade("sig-b", 0, 1_200);
    assert!(db.record_pump_trade_evidence(&raw_one).unwrap());
    assert!(db.record_pump_trade_evidence(&raw_two).unwrap());

    let sequence_one = db.next_fast_event_sequence().unwrap();
    assert_eq!(sequence_one, 1);
    let event_one = fast_event("sig-a", 0, sequence_one, 1_300);
    assert!(db.record_fast_event(&event_one, 1_100, 6, 9).unwrap());

    let sequence_two = db.next_fast_event_sequence().unwrap();
    assert_eq!(sequence_two, 2);
    let event_two = fast_event("sig-b", 0, sequence_two, 1_400);
    assert!(db.record_fast_event(&event_two, 1_200, 6, 9).unwrap());

    drop(db);
    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.next_fast_event_sequence().unwrap(), 3);

    let replay = reopened
        .fast_events_for_market("mint-a", WSOL, VenueId::PumpFunBondingCurve)
        .unwrap();
    assert_eq!(replay.len(), 2);
    assert_eq!(replay[0].event.sequence, 1);
    assert_eq!(replay[1].event.sequence, 2);
    assert_eq!(replay[0].source_observed_at_unix_ms, 1_100);
    assert_eq!(replay[0].base_decimals, 6);
    assert_eq!(replay[0].quote_decimals, 9);

    cleanup_dir(&root);
}

#[test]
fn canonical_fast_event_duplicate_is_idempotent_but_conflict_fails_closed() {
    let root = unique_test_dir("identity");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade("sig-a", 0, 1_100))
        .unwrap();

    let original = fast_event("sig-a", 0, 1, 1_300);
    assert!(db.record_fast_event(&original, 1_100, 6, 9).unwrap());

    let duplicate_with_new_proposed_sequence = fast_event("sig-a", 0, 2, 1_300);
    assert!(!db
        .record_fast_event(&duplicate_with_new_proposed_sequence, 1_100, 6, 9)
        .unwrap());
    assert_eq!(db.next_fast_event_sequence().unwrap(), 2);

    let mut conflict = fast_event("sig-a", 0, 2, 1_300);
    conflict.quote_quantity = 0.2;
    conflict.price_quote = 0.1;
    let error = db
        .record_fast_event(&conflict, 1_100, 6, 9)
        .unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));

    let replay: Vec<StoredFastEvent> = db
        .fast_events_for_market("mint-a", WSOL, VenueId::PumpFunBondingCurve)
        .unwrap();
    assert_eq!(replay.len(), 1);
    assert_eq!(replay[0].event.sequence, 1);
    assert_eq!(replay[0].event.quote_quantity, 0.1);

    cleanup_dir(&root);
}

#[test]
fn new_canonical_identity_cannot_skip_durable_append_sequence() {
    let root = unique_test_dir("sequence-gap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade("sig-a", 0, 1_100))
        .unwrap();

    let skipped = fast_event("sig-a", 0, 2, 1_300);
    let error = db.record_fast_event(&skipped, 1_100, 6, 9).unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);

    let contiguous = fast_event("sig-a", 0, 1, 1_300);
    assert!(db.record_fast_event(&contiguous, 1_100, 6, 9).unwrap());
    assert_eq!(db.next_fast_event_sequence().unwrap(), 2);

    cleanup_dir(&root);
}

#[test]
fn canonical_fast_event_rejects_backdated_source_provenance() {
    let root = unique_test_dir("provenance");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade("sig-a", 0, 1_100))
        .unwrap();

    let event = fast_event("sig-a", 0, 1, 1_300);
    let error = db.record_fast_event(&event, 1_301, 6, 9).unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));
    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);

    cleanup_dir(&root);
}

#[test]
fn verified_mint_decimals_are_consistent_or_fail_closed() {
    let root = unique_test_dir("decimals");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    assert_eq!(db.verified_mint_decimals("mint-a").unwrap(), None);

    let first = db.upsert_candidate(&candidate("mint-a", "pair-a")).unwrap();
    db.insert_mint_state(first, &mint_state("mint-a", 6, 100))
        .unwrap();
    db.insert_mint_state(first, &mint_state("mint-a", 6, 101))
        .unwrap();
    assert_eq!(db.verified_mint_decimals("mint-a").unwrap(), Some(6));

    let second = db.upsert_candidate(&candidate("mint-a", "pair-b")).unwrap();
    db.insert_mint_state(second, &mint_state("mint-a", 9, 102))
        .unwrap();
    let error = db.verified_mint_decimals("mint-a").unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));

    cleanup_dir(&root);
}

#[test]
fn pending_pump_trade_evidence_is_bounded_oldest_first_and_excludes_canonical_rows() {
    let root = unique_test_dir("pending");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    for (signature, observed) in [("sig-c", 300), ("sig-a", 100), ("sig-b", 200)] {
        db.record_pump_trade_evidence(&raw_trade(signature, 0, observed))
            .unwrap();
    }

    assert!(db.pending_pump_trade_evidence(0).unwrap().is_empty());
    let pending = db.pending_pump_trade_evidence(2).unwrap();
    assert_eq!(pending.len(), 2);
    assert_eq!(pending[0].signature, "sig-a");
    assert_eq!(pending[1].signature, "sig-b");

    let event = fast_event("sig-a", 0, 1, 1_300);
    db.record_fast_event(&event, 100, 6, 9).unwrap();
    let pending = db.pending_pump_trade_evidence(10).unwrap();
    assert_eq!(
        pending
            .iter()
            .map(|row| row.signature.as_str())
            .collect::<Vec<_>>(),
        vec!["sig-b", "sig-c"]
    );

    cleanup_dir(&root);
}
