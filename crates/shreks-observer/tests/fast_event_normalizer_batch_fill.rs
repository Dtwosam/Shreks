use std::{
    fs,
    path::PathBuf,
    process,
    time::{SystemTime, UNIX_EPOCH},
};

#[path = "../src/fast_event_normalizer.rs"]
mod fast_event_normalizer;

use fast_event_normalizer::normalize_pending_pump_trade_evidence_at;
use rusqlite::Connection;
use shreks_core::{DiscoveredToken, ProviderId, TokenMintState, VenueId};
use shreks_providers::{
    pump::WRAPPED_SOL_MINT,
    pump_quote::SYSTEM_SOL_QUOTE_MINT,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const EVENT_SECONDS: i64 = 1_770_000_000;
const ACCEPTED_MS: i64 = 1_770_000_100_000;

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-batch-fill-{}-{nanos}",
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
        provider: ProviderId::SolanaPublic,
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

fn canonical_count(db: &ShreksDb, mint: &str) -> usize {
    db.fast_events_for_market(
        mint,
        WRAPPED_SOL_MINT,
        VenueId::PumpFunBondingCurve,
    )
    .unwrap()
    .len()
}

#[test]
fn partial_ready_frontier_fills_remaining_batch_from_ready_evidence() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    // The first four pending rows contain three unresolved rows and one ready
    // row. Production used to stop after normalizing that single ready row,
    // wasting 75% of the requested output budget and rescanning the same
    // unresolved prefix on the next burst.
    for index in 0..3_i64 {
        db.record_pump_trade_evidence(&raw_trade(
            &format!("sig-unresolved-{index}"),
            &format!("mint-unresolved-{index}"),
            ACCEPTED_MS - 10_000 + index,
        ))
        .unwrap();
    }

    for index in 0..4_i64 {
        let mint = format!("mint-ready-{index}");
        verify_decimals(&db, &mint);
        db.record_pump_trade_evidence(&raw_trade(
            &format!("sig-ready-{index}"),
            &mint,
            ACCEPTED_MS - 9_000 + index,
        ))
        .unwrap();
    }

    let report = normalize_pending_pump_trade_evidence_at(&db, 4, ACCEPTED_MS).unwrap();

    assert_eq!(
        report.normalized, 4,
        "partial progress in a blocked frontier must not leave the rest of the output budget unused"
    );

    let canonical_ready = (0..4_i64)
        .map(|index| canonical_count(&db, &format!("mint-ready-{index}")))
        .sum::<usize>();
    assert_eq!(canonical_ready, 4);
    assert_eq!(
        db.pending_pump_trade_evidence(32).unwrap().len(),
        3,
        "unresolved evidence must remain durable while ready evidence fills the batch"
    );

    let _ = fs::remove_dir_all(root);
}

#[test]
fn production_sized_batch_reserves_fresh_capacity_while_old_debt_progresses() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let old_mints = (0..8_i64)
        .map(|index| format!("mint-old-ready-{index}"))
        .collect::<Vec<_>>();
    for (index, mint) in old_mints.iter().enumerate() {
        verify_decimals(&db, mint);
        db.record_pump_trade_evidence(&raw_trade(
            &format!("sig-old-ready-{index}"),
            mint,
            ACCEPTED_MS - 100_000 + index as i64,
        ))
        .unwrap();
    }

    let fresh_mints = (0..8_i64)
        .map(|index| format!("mint-fresh-ready-{index}"))
        .collect::<Vec<_>>();
    for (index, mint) in fresh_mints.iter().enumerate() {
        verify_decimals(&db, mint);
        db.record_pump_trade_evidence(&raw_trade(
            &format!("sig-fresh-ready-{index}"),
            mint,
            ACCEPTED_MS - 1_000 + index as i64,
        ))
        .unwrap();
    }

    let report = normalize_pending_pump_trade_evidence_at(&db, 8, ACCEPTED_MS).unwrap();
    assert_eq!(report.normalized, 8);

    let old_normalized = old_mints
        .iter()
        .map(|mint| canonical_count(&db, mint))
        .sum::<usize>();
    let fresh_normalized = fresh_mints
        .iter()
        .map(|mint| canonical_count(&db, mint))
        .sum::<usize>();

    assert_eq!(
        old_normalized, 2,
        "one quarter of a production-sized batch must remain reserved for oldest ready debt"
    );
    assert_eq!(
        fresh_normalized, 6,
        "three quarters of a production-sized batch must protect fresh ready evidence from historical starvation"
    );

    let _ = fs::remove_dir_all(root);
}

#[test]
fn normalization_burst_rolls_back_if_a_later_fast_event_write_fails() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    for (signature, mint, observed_at) in [
        ("sig-batch-first", "mint-batch-first", ACCEPTED_MS - 2_000),
        ("sig-batch-fail", "mint-batch-fail", ACCEPTED_MS - 1_000),
    ] {
        verify_decimals(&db, mint);
        db.record_pump_trade_evidence(&raw_trade(signature, mint, observed_at))
            .unwrap();
    }

    let trigger_connection = Connection::open(&db_path).unwrap();
    trigger_connection
        .execute_batch(
            r#"CREATE TRIGGER fail_second_fast_event
               BEFORE INSERT ON fast_events
               WHEN NEW.signature = 'sig-batch-fail'
               BEGIN
                   SELECT RAISE(ABORT, 'forced fast-event batch failure');
               END;"#,
        )
        .unwrap();
    drop(trigger_connection);

    let error = normalize_pending_pump_trade_evidence_at(&db, 2, ACCEPTED_MS)
        .expect_err("forced second write must fail the normalization burst");
    assert!(error.to_string().contains("forced fast-event batch failure"));

    assert_eq!(
        canonical_count(&db, "mint-batch-first"),
        0,
        "a storage failure late in one normalization burst must roll back earlier writes from that same burst"
    );
    assert_eq!(canonical_count(&db, "mint-batch-fail"), 0);

    let _ = fs::remove_dir_all(root);
}
