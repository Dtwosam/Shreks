use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FastReserveContext, ProviderId, VenueId,
};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapMarket, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite,
    ShreksDb,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-reserve-source-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn pump_raw(signature: &str) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 55,
        observed_at_unix_ms: 1_100,
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

fn pump_event(signature: &str) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, 0).unwrap(),
        1,
        ProviderId::Helius,
        FastMarketKey::new("mint-a", WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        55,
        1_000,
        1_300,
        2.0,
        0.1,
        0.05,
    )
    .unwrap()
}

fn expected_pump_context() -> FastReserveContext {
    FastReserveContext::PumpCurve {
        virtual_base_reserve_raw: 20_000_000_000,
        virtual_quote_reserve_raw: 10_000_000_000,
        real_base_reserve_raw: 10_000_000_000,
        real_quote_reserve_raw: 5_000_000_000,
        base_decimals: 6,
        quote_decimals: 9,
    }
}

fn pumpswap_raw(signature: &str, log_index: u32) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms: 1_100,
        pool: "pool-a".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: 1,
        pool_base_reserves_raw: 9_500_000_000,
        pool_quote_reserves_raw: 52_500_000_000,
    }
}

fn pumpswap_market() -> PumpSwapMarket {
    PumpSwapMarket {
        mint: "mint-a".to_owned(),
        quote_mint: WSOL.to_owned(),
        pool_address: "pool-a".to_owned(),
    }
}

fn pumpswap_event(signature: &str, log_index: u32) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, pump_swap_event_ordinal(log_index).unwrap()).unwrap(),
        1,
        ProviderId::Helius,
        FastMarketKey::new("mint-a", WSOL, VenueId::PumpSwap).unwrap(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        900,
        1_000,
        1_300,
        500.0,
        2.5,
        0.005,
    )
    .unwrap()
}

fn expected_pumpswap_context() -> FastReserveContext {
    FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: 9_500_000_000,
        pool_quote_reserve_raw: 52_500_000_000,
        virtual_quote_reserve_raw: None,
        base_decimals: 6,
        quote_decimals: 9,
    }
}

#[test]
fn pump_replay_derives_reserve_context_from_immutable_source() {
    let root = unique_test_dir("pump-direct");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let raw = pump_raw("pump-direct");
    db.record_pump_trade_evidence(&raw).unwrap();

    let deliberately_wrong_ephemeral_context = FastReserveContext::PumpCurve {
        virtual_base_reserve_raw: 1,
        virtual_quote_reserve_raw: 2,
        real_base_reserve_raw: 3,
        real_quote_reserve_raw: 4,
        base_decimals: 6,
        quote_decimals: 9,
    };
    let event = pump_event("pump-direct")
        .with_reserve_context(deliberately_wrong_ephemeral_context)
        .unwrap();
    assert!(db
        .record_pump_fast_event_from_source(&event, &raw, 6, 9)
        .unwrap());

    let replay = db
        .fast_events_for_market_with_reserve_context(
            "mint-a",
            WSOL,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap();
    assert_eq!(replay.len(), 1);
    assert_eq!(replay[0].event.reserve_context, Some(expected_pump_context()));

    cleanup_dir(&root);
}

#[test]
fn legacy_pump_record_wrapper_enriches_reserve_aware_replay() {
    let root = unique_test_dir("pump-wrapper");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let raw = pump_raw("pump-wrapper");
    db.record_pump_trade_evidence(&raw).unwrap();

    assert!(db
        .record_fast_event(&pump_event("pump-wrapper"), 1_100, 6, 9)
        .unwrap());
    let replay = db
        .fast_events_for_market_with_reserve_context(
            "mint-a",
            WSOL,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap();
    assert_eq!(replay.len(), 1);
    assert_eq!(replay[0].event.reserve_context, Some(expected_pump_context()));

    cleanup_dir(&root);
}

#[test]
fn pumpswap_replay_derives_reserve_context_from_immutable_source() {
    let root = unique_test_dir("pumpswap-direct");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let raw = pumpswap_raw("swap-direct", 7);
    db.record_pump_swap_trade_evidence(&raw).unwrap();

    let deliberately_wrong_ephemeral_context = FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: 1,
        pool_quote_reserve_raw: 2,
        virtual_quote_reserve_raw: None,
        base_decimals: 6,
        quote_decimals: 9,
    };
    let event = pumpswap_event("swap-direct", 7)
        .with_reserve_context(deliberately_wrong_ephemeral_context)
        .unwrap();
    assert!(db
        .record_pump_swap_fast_event_from_source(&event, &raw, &pumpswap_market(), 6, 9)
        .unwrap());

    let replay = db
        .fast_events_for_market_with_reserve_context("mint-a", WSOL, VenueId::PumpSwap)
        .unwrap();
    assert_eq!(replay.len(), 1);
    assert_eq!(
        replay[0].event.reserve_context,
        Some(expected_pumpswap_context())
    );

    cleanup_dir(&root);
}
