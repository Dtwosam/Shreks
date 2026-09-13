use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::{
    DiscoveredToken, LifecycleEventKind, ProviderId, TokenLifecycleEvent, TokenMintState, VenueId,
};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
};

const ACCEPTED_MS: i64 = 1_770_000_100_000;
const EVENT_SECONDS: i64 = 1_770_000_000;
const SYSTEM_SOL_QUOTE_MINT: &str = "11111111111111111111111111111111";
const EXPECTED_RECENT_RAW_FRONTIER: usize = 2_048;
const READY_PUMPSWAP_POOL: &str = "pool-ready-beyond-frontier";
const UNRESOLVED_PUMPSWAP_POOL: &str = "pool-unresolved-newer";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-normalizer-recent-frontier-{label}-{}-{nanos}",
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

fn raw_pump_swap_trade(
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

fn verify_pump_swap_market(db: &ShreksDb, mint: &str) {
    let signature = "migration-ready-beyond-frontier";
    db.record_pump_migration_signal(signature, 850, ACCEPTED_MS - 21_000)
        .unwrap();
    db.complete_pump_migration(
        signature,
        ACCEPTED_MS - 20_500,
        &[TokenLifecycleEvent {
            kind: LifecycleEventKind::PumpGraduation,
            provider: ProviderId::SolanaPublic,
            mint: mint.to_owned(),
            quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
            from_venue: VenueId::PumpFunBondingCurve,
            to_venue: VenueId::PumpSwap,
            pool_address: READY_PUMPSWAP_POOL.to_owned(),
            signature: signature.to_owned(),
            slot: 850,
            detected_at_unix_ms: ACCEPTED_MS - 21_000,
            occurred_at_unix_ms: Some((EVENT_SECONDS - 1) * 1_000),
        }],
    )
    .unwrap();
}

#[test]
fn recent_ready_pump_selector_does_not_scan_past_bounded_raw_frontier() {
    let root = unique_test_dir("pump");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let ready_mint = "mint-ready-beyond-frontier";
    verify_decimals(&db, ready_mint);
    db.record_pump_trade_evidence(&raw_trade(
        "sig-ready-beyond-frontier",
        ready_mint,
        ACCEPTED_MS - 20_000,
    ))
    .unwrap();

    for index in 0..=EXPECTED_RECENT_RAW_FRONTIER {
        db.record_pump_trade_evidence(&raw_trade(
            &format!("sig-unresolved-newer-{index:04}"),
            &format!("mint-unresolved-newer-{index:04}"),
            ACCEPTED_MS - 10_000 + i64::try_from(index).unwrap(),
        ))
        .unwrap();
    }

    let selected = db
        .recent_normalizable_pump_trade_evidence(1, ACCEPTED_MS)
        .unwrap();

    assert!(
        selected.is_empty(),
        "the fresh lane must inspect only a bounded newest raw frontier; historical debt is handled by the durable keyset lane"
    );

    let _ = fs::remove_dir_all(root);
}

#[test]
fn recent_ready_pumpswap_selector_does_not_scan_past_bounded_raw_frontier() {
    let root = unique_test_dir("pumpswap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let ready_mint = "mint-pumpswap-ready-beyond-frontier";
    verify_decimals(&db, ready_mint);
    verify_pump_swap_market(&db, ready_mint);
    db.record_pump_swap_trade_evidence(&raw_pump_swap_trade(
        "sig-pumpswap-ready-beyond-frontier",
        READY_PUMPSWAP_POOL,
        ACCEPTED_MS - 20_000,
    ))
    .unwrap();

    for index in 0..=EXPECTED_RECENT_RAW_FRONTIER {
        db.record_pump_swap_trade_evidence(&raw_pump_swap_trade(
            &format!("sig-pumpswap-unresolved-newer-{index:04}"),
            UNRESOLVED_PUMPSWAP_POOL,
            ACCEPTED_MS - 10_000 + i64::try_from(index).unwrap(),
        ))
        .unwrap();
    }

    let selected = db
        .recent_normalizable_pump_swap_trade_evidence(1, ACCEPTED_MS)
        .unwrap();

    assert!(
        selected.is_empty(),
        "the PumpSwap fresh lane must inspect only a bounded newest raw frontier; historical debt is handled by the durable keyset lane"
    );

    let _ = fs::remove_dir_all(root);
}
