use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, LifecycleEventKind, ProviderId,
    TokenLifecycleEvent, VenueId,
};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapMarket, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite,
    ShreksDb, StorageError,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    std::env::temp_dir().join(format!("shreks-prevalidated-fast-event-{label}-{}-{nanos}", process::id()))
}

fn pump_raw(signature: &str, observed_at_unix_ms: i64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
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

fn pump_event(signature: &str, sequence: u64, observed_at_unix_ms: i64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, 0).unwrap(),
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
    ).unwrap()
}

fn swap_raw(signature: &str, log_index: u32, observed_at_unix_ms: i64) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms,
        pool: "pool-a".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: 1_777_000_000,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    }
}

fn swap_event(signature: &str, ordinal: u32, sequence: u64, observed_at_unix_ms: i64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, ordinal).unwrap(),
        sequence,
        ProviderId::Helius,
        FastMarketKey::new("mint-a", WSOL, VenueId::PumpSwap).unwrap(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        900,
        1_777_000_000_000,
        observed_at_unix_ms,
        500.0,
        2.5,
        0.005,
    ).unwrap()
}

fn migration() -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::Helius,
        mint: "mint-a".to_owned(),
        quote_mint: WSOL.to_owned(),
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: "pool-a".to_owned(),
        signature: "migration-a".to_owned(),
        slot: 850,
        detected_at_unix_ms: 1_776_999_900_000,
        occurred_at_unix_ms: Some(1_776_999_899_000),
    }
}

#[test]
fn prevalidated_pump_source_preserves_identity_and_source_checks() {
    let root = unique_test_dir("pump");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let raw = pump_raw("sig-a", 1_100);
    db.record_pump_trade_evidence(&raw).unwrap();

    let event = pump_event("sig-a", 1, 1_300);
    assert!(db.record_pump_fast_event_from_source(&event, &raw, 6, 9).unwrap());

    let mut mismatched = pump_raw("sig-b", 1_100);
    mismatched.ordinal = 1;
    let error = db.record_pump_fast_event_from_source(&event, &mismatched, 6, 9).unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));

    drop(db);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn prevalidated_pumpswap_source_requires_matching_verified_market() {
    let root = unique_test_dir("pumpswap");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    db.record_pump_migration_signal("migration-a", 850, 1_776_999_900_000).unwrap();
    db.complete_pump_migration("migration-a", 1_776_999_900_100, &[migration()]).unwrap();

    let raw = swap_raw("swap-a", 17, 1_777_000_000_100);
    db.record_pump_swap_trade_evidence(&raw).unwrap();
    let market = db.pump_swap_market_for_pool("pool-a").unwrap().unwrap();
    let event = swap_event("swap-a", raw.ordinal, 1, 1_777_000_000_200);
    assert!(db.record_pump_swap_fast_event_from_source(&event, &raw, &market, 6, 9).unwrap());

    let wrong_market = PumpSwapMarket {
        mint: market.mint.clone(),
        quote_mint: market.quote_mint.clone(),
        pool_address: "pool-other".to_owned(),
    };
    let error = db.record_pump_swap_fast_event_from_source(&event, &raw, &wrong_market, 6, 9).unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));

    drop(db);
    let _ = fs::remove_dir_all(root);
}
