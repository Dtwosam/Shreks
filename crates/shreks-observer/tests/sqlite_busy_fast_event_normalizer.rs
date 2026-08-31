use std::{
    fs,
    path::PathBuf,
    process,
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

#[path = "../src/fast_event_normalizer.rs"]
mod fast_event_normalizer;

use fast_event_normalizer::normalize_pending_pump_trade_evidence_at;
use rusqlite::Connection;
use shreks_core::{DiscoveredToken, ProviderId, TokenMintState, VenueId};
use shreks_providers::pump::WRAPPED_SOL_MINT;
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT: Duration = Duration::from_millis(5_200);

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-sqlite-busy-fast-event-normalizer-red-proof-{}-{nanos}",
        process::id()
    ))
}

#[test]
fn fast_event_normalizer_survives_one_transient_sqlite_busy_interval() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let candidate_id = db
        .upsert_candidate(&DiscoveredToken {
            mint: "mint-busy-normalizer".to_owned(),
            pair_address: None,
            dex_id: Some("pumpfun".to_owned()),
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms: 1_000,
            source: ProviderId::SolanaPublic,
        })
        .unwrap();
    db.insert_mint_state(
        candidate_id,
        &TokenMintState {
            provider: ProviderId::SolanaPublic,
            mint: "mint-busy-normalizer".to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1_000_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 40,
            observed_at_unix_ms: 1_050,
        },
    )
    .unwrap();
    db.record_pump_trade_evidence(&PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: "SqliteBusyNormalizer111".to_owned(),
        ordinal: 0,
        slot: 41,
        observed_at_unix_ms: 1_100,
        mint: "mint-busy-normalizer".to_owned(),
        quote_mint: WRAPPED_SOL_MINT.to_owned(),
        user: "wallet-busy-normalizer".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 2_500_000_000,
        timestamp_unix_seconds: 1,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 32_000_000_000,
        real_quote_reserves_raw: 10_000_000_000,
        ix_name: "buy".to_owned(),
    })
    .unwrap();

    let blocker = Connection::open(&db_path).unwrap();
    blocker
        .execute_batch("PRAGMA journal_mode=WAL; BEGIN IMMEDIATE;")
        .unwrap();
    let release_lock = thread::spawn(move || {
        thread::sleep(BLOCK_LONGER_THAN_STORAGE_BUSY_TIMEOUT);
        blocker.execute_batch("COMMIT;").unwrap();
    });

    let report = normalize_pending_pump_trade_evidence_at(&db, 1, 2_000)
        .expect("one transient SQLite busy interval must not terminate canonicalization");
    assert_eq!(report.normalized, 1);
    release_lock.join().unwrap();

    let events = db
        .fast_events_for_market(
            "mint-busy-normalizer",
            WRAPPED_SOL_MINT,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap();
    assert_eq!(events.len(), 1);
    assert_eq!(events[0].event.provider, ProviderId::SolanaPublic);

    drop(db);
    let _ = fs::remove_dir_all(root);
}
