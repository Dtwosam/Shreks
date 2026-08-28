use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FastMarketState, ProviderId, VenueId,
};

fn market() -> FastMarketKey {
    FastMarketKey::new(
        "Mint111111111111111111111111111111111111111",
        "So11111111111111111111111111111111111111112",
        VenueId::PumpFunBondingCurve,
    )
    .expect("test market must be valid")
}

fn event(
    market: FastMarketKey,
    sequence: u64,
    kind: FastEventKind,
    occurred_at_unix_ms: i64,
    observed_at_unix_ms: i64,
) -> FastEvent {
    FastEvent::new(
        FastEventId::new(format!("sig-{sequence}"), 0).unwrap(),
        sequence,
        ProviderId::Helius,
        market,
        kind,
        Some(format!("wallet-{sequence}")),
        100 + sequence,
        occurred_at_unix_ms,
        observed_at_unix_ms,
        10.0,
        1.0,
        0.1,
    )
    .unwrap()
}

#[test]
fn subsecond_windows_use_when_shreks_observed_same_second_chain_events() {
    let market = market();
    let mut state = FastMarketState::with_default_windows(market.clone());

    state
        .apply(event(
            market.clone(),
            1,
            FastEventKind::Buy,
            1_000,
            1_010,
        ))
        .unwrap();
    state
        .apply(event(
            market,
            2,
            FastEventKind::Sell,
            1_000,
            1_260,
        ))
        .unwrap();

    let snapshot = state.snapshot(1_300).unwrap();

    let window_100 = snapshot.window(100).unwrap();
    assert_eq!(window_100.buy_count, 0);
    assert_eq!(window_100.sell_count, 1);

    let window_250 = snapshot.window(250).unwrap();
    assert_eq!(window_250.buy_count, 0);
    assert_eq!(window_250.sell_count, 1);

    let window_500 = snapshot.window(500).unwrap();
    assert_eq!(window_500.buy_count, 1);
    assert_eq!(window_500.sell_count, 1);
}

#[test]
fn late_chain_event_is_accepted_when_sequence_and_observation_order_are_monotonic() {
    let market = market();
    let mut state = FastMarketState::with_default_windows(market.clone());

    state
        .apply(event(
            market.clone(),
            1,
            FastEventKind::Buy,
            2_000,
            2_100,
        ))
        .unwrap();

    state
        .apply(event(
            market,
            2,
            FastEventKind::Sell,
            1_500,
            2_200,
        ))
        .expect("late chain evidence is new information when observed later");
}

#[test]
fn observation_time_moving_backward_is_rejected_even_when_chain_time_moves_forward() {
    let market = market();
    let mut state = FastMarketState::with_default_windows(market.clone());

    state
        .apply(event(
            market.clone(),
            1,
            FastEventKind::Buy,
            1_000,
            2_000,
        ))
        .unwrap();

    let result = state.apply(event(
        market,
        2,
        FastEventKind::Sell,
        1_100,
        1_999,
    ));
    assert!(result.is_err(), "observation clock must never move backward");
}

#[test]
fn snapshot_cannot_claim_state_before_latest_observation() {
    let market = market();
    let mut state = FastMarketState::with_default_windows(market.clone());
    state
        .apply(event(
            market,
            1,
            FastEventKind::Buy,
            1_000,
            2_000,
        ))
        .unwrap();

    assert!(
        state.snapshot(1_999).is_err(),
        "snapshot before the time Shreks observed the event would create look-ahead state"
    );
}
