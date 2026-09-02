use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    maximum_exit_capacity, FastEvent, FastEventId, FastEventKind, FastMarketKey,
    FastReserveContext, ProviderId, VenueId,
};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapExecutionEconomicsWrite, PumpSwapMarket,
    PumpSwapTradeEvidenceWrite, ShreksDb,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fl3-exit-capacity-replay-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn pumpswap_replay_recovers_virtual_quote_reserve_and_exact_capacity() {
    let root = unique_test_dir("pumpswap");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let ordinal = pump_swap_event_ordinal(7).unwrap();

    let raw = PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: "swap-capacity".to_owned(),
        ordinal,
        log_index: 7,
        slot: 900,
        observed_at_unix_ms: 1_100,
        pool: "pool-a".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        base_amount_raw: 100,
        quote_amount_raw: 90,
        user_quote_amount_raw: 91,
        timestamp_unix_seconds: 1,
        pool_base_reserves_raw: 1_000,
        pool_quote_reserves_raw: 500,
    };
    assert!(db.record_pump_swap_trade_evidence(&raw).unwrap());

    let economics = PumpSwapExecutionEconomicsWrite {
        signature: raw.signature.clone(),
        ordinal,
        lp_fee_basis_points: 20,
        lp_fee_raw: 1,
        protocol_fee_basis_points: 10,
        protocol_fee_raw: 1,
        quote_amount_with_or_without_lp_fee_raw: 90,
        coin_creator: Some("creator-a".to_owned()),
        coin_creator_fee_basis_points: Some(5),
        coin_creator_fee_raw: Some(1),
        cashback_fee_basis_points: Some(1),
        cashback_raw: Some(0),
        buyback_fee_basis_points: Some(1),
        buyback_fee_raw: Some(0),
        virtual_quote_reserves_raw: Some(500),
        can_boost: Some(true),
        base_supply_raw: Some(10_000),
    };
    assert!(db.record_pump_swap_execution_economics(&economics).unwrap());

    let market = PumpSwapMarket {
        mint: "mint-a".to_owned(),
        quote_mint: WSOL.to_owned(),
        pool_address: "pool-a".to_owned(),
    };
    let event = FastEvent::new(
        FastEventId::new(&raw.signature, ordinal).unwrap(),
        1,
        ProviderId::Helius,
        FastMarketKey::new("mint-a", WSOL, VenueId::PumpSwap).unwrap(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        raw.slot,
        1_000,
        1_300,
        100.0,
        90.0,
        0.9,
    )
    .unwrap();
    assert!(db
        .record_pump_swap_fast_event_from_source(&event, &raw, &market, 0, 0)
        .unwrap());

    let replay = db
        .fast_events_for_market_with_reserve_context("mint-a", WSOL, VenueId::PumpSwap)
        .unwrap();
    assert_eq!(replay.len(), 1);
    assert_eq!(
        replay[0].event.reserve_context,
        Some(FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw: 1_000,
            pool_quote_reserve_raw: 500,
            virtual_quote_reserve_raw: Some(500),
            base_decimals: 0,
            quote_decimals: 0,
        })
    );

    let replay_capacity =
        maximum_exit_capacity(replay[0].event.reserve_context.as_ref().unwrap(), 0.8).unwrap();
    assert_eq!(replay_capacity.maximum_base_quantity_raw, 250);
    assert_eq!(replay_capacity.boundary_quote_output_raw, 200);

    cleanup_dir(&root);
}
