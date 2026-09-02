use shreks_core::{
    FastEvent, FastEventError, FastEventId, FastEventKind, FastMarketKey, FastMarketState,
    FastReserveContext, ProviderId, VenueId,
};

fn pump_market() -> FastMarketKey {
    FastMarketKey::new(
        "PumpMint111111111111111111111111111111111111",
        "So11111111111111111111111111111111111111112",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap()
}

fn pumpswap_market() -> FastMarketKey {
    FastMarketKey::new(
        "SwapMint111111111111111111111111111111111111",
        "So11111111111111111111111111111111111111112",
        VenueId::PumpSwap,
    )
    .unwrap()
}

fn event(market: FastMarketKey, sequence: u64, observed_at_unix_ms: i64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(format!("sig-{sequence}"), sequence as u32).unwrap(),
        sequence,
        ProviderId::SolanaPublic,
        market,
        FastEventKind::Buy,
        Some("wallet-1".to_owned()),
        10_000 + sequence,
        observed_at_unix_ms,
        observed_at_unix_ms,
        1.0,
        0.1,
        0.1,
    )
    .unwrap()
}

#[test]
fn pump_reserve_context_survives_into_latest_market_snapshot() {
    let market = pump_market();
    let reserve = FastReserveContext::PumpCurve {
        virtual_base_reserve_raw: 900_000_000_000_000,
        virtual_quote_reserve_raw: 32_000_000_000,
        real_base_reserve_raw: 700_000_000_000_000,
        real_quote_reserve_raw: 10_000_000_000,
        base_decimals: 6,
        quote_decimals: 9,
    };
    let event = event(market.clone(), 1, 1_000)
        .with_reserve_context(reserve.clone())
        .unwrap();

    let mut state = FastMarketState::with_default_windows(market);
    state.apply(event).unwrap();

    let snapshot = state.snapshot(1_000).unwrap();
    assert_eq!(snapshot.last_reserve_context, Some(reserve));
}

#[test]
fn pumpswap_reserve_context_survives_into_latest_market_snapshot() {
    let market = pumpswap_market();
    let reserve = FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: 250_000_000_000,
        pool_quote_reserve_raw: 20_000_000_000,
        virtual_quote_reserve_raw: None,
        base_decimals: 6,
        quote_decimals: 9,
    };
    let event = event(market.clone(), 1, 1_000)
        .with_reserve_context(reserve.clone())
        .unwrap();

    let mut state = FastMarketState::with_default_windows(market);
    state.apply(event).unwrap();

    assert_eq!(
        state.snapshot(1_000).unwrap().last_reserve_context,
        Some(reserve)
    );
}

#[test]
fn reserve_context_rejects_the_wrong_venue() {
    let reserve = FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: 1,
        pool_quote_reserve_raw: 1,
        virtual_quote_reserve_raw: None,
        base_decimals: 6,
        quote_decimals: 9,
    };
    let error = event(pump_market(), 1, 1_000)
        .with_reserve_context(reserve)
        .unwrap_err();

    assert_eq!(error, FastEventError::ReserveContextVenueMismatch);
}

#[test]
fn reserve_context_is_optional_for_backward_compatible_event_construction() {
    let market = pump_market();
    let event = event(market.clone(), 1, 1_000);
    assert_eq!(event.reserve_context, None);

    let mut state = FastMarketState::with_default_windows(market);
    state.apply(event).unwrap();
    assert_eq!(state.snapshot(1_000).unwrap().last_reserve_context, None);
}
