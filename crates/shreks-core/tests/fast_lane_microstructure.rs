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

#[allow(clippy::too_many_arguments)]
fn event(
    sequence: u64,
    kind: FastEventKind,
    observed_at_unix_ms: i64,
    quote_quantity: f64,
    price_quote: f64,
    actor: Option<&str>,
) -> FastEvent {
    FastEvent::new(
        FastEventId::new(format!("sig-{sequence}"), 0).expect("event id must be valid"),
        sequence,
        ProviderId::SolanaPublic,
        market(),
        kind,
        actor.map(str::to_owned),
        10_000 + sequence,
        observed_at_unix_ms,
        observed_at_unix_ms,
        quote_quantity / price_quote,
        quote_quantity,
        price_quote,
    )
    .expect("test event must be valid")
}

fn assert_close(actual: f64, expected: f64) {
    let tolerance = 1e-12_f64.max(expected.abs() * 1e-12);
    assert!(
        (actual - expected).abs() <= tolerance,
        "expected {expected}, got {actual}"
    );
}

#[test]
fn one_second_window_exposes_flow_rates_imbalance_extrema_and_recovery() {
    let mut state = FastMarketState::with_default_windows(market());
    for item in [
        event(1, FastEventKind::Buy, 1_000, 4.0, 0.04, Some("buyer-a")),
        event(2, FastEventKind::Buy, 1_300, 2.0, 0.05, Some("buyer-b")),
        event(3, FastEventKind::Sell, 1_700, 3.0, 0.03, Some("seller-a")),
        event(4, FastEventKind::Buy, 1_900, 6.0, 0.06, Some("buyer-a")),
        event(5, FastEventKind::Sell, 1_950, 1.5, 0.045, Some("seller-b")),
    ] {
        state.apply(item).unwrap();
    }

    let snapshot = state.snapshot(2_000).unwrap();
    let window = snapshot.window(1_000).unwrap();

    assert_eq!(window.buy_count, 3);
    assert_eq!(window.sell_count, 2);
    assert_eq!(window.unique_buy_actors, 2);
    assert_eq!(window.unique_sell_actors, 2);

    assert_close(window.buy_arrival_rate_per_second, 3.0);
    assert_close(window.sell_arrival_rate_per_second, 2.0);
    assert_close(window.count_imbalance, 0.2);

    assert_close(window.buy_quote_quantity, 12.0);
    assert_close(window.sell_quote_quantity, 4.5);
    assert_close(window.net_quote_quantity, 7.5);
    assert_close(window.quote_flow_imbalance, 7.5 / 16.5);
    assert_close(window.quote_flow_velocity_per_second, 7.5);

    // Older half [1000,1500): net +6 quote => +12 quote/s.
    // Recent half [1500,2000]: net +1.5 quote => +3 quote/s.
    // Acceleration = (3 - 12) / 0.5s = -18 quote/s^2.
    assert_close(window.quote_flow_acceleration_per_second2, -18.0);

    assert_eq!(window.local_high_price_quote, Some(0.06));
    assert_eq!(window.local_low_price_quote, Some(0.03));
    assert_eq!(window.last_price_quote, Some(0.045));
    assert_close(window.drawdown_from_local_high, 0.25);
    assert_close(window.recovery_from_local_low, 0.5);
}

#[test]
fn half_window_boundary_belongs_only_to_recent_half_for_acceleration() {
    let mut state = FastMarketState::with_default_windows(market());
    state
        .apply(event(
            1,
            FastEventKind::Buy,
            1_000,
            1.0,
            0.01,
            Some("buyer-a"),
        ))
        .unwrap();
    state
        .apply(event(
            2,
            FastEventKind::Buy,
            1_050,
            2.0,
            0.02,
            Some("buyer-b"),
        ))
        .unwrap();

    let snapshot = state.snapshot(1_100).unwrap();
    let window = snapshot.window(100).unwrap();

    // [1000,1050): +1 quote / .05s = +20 quote/s.
    // [1050,1100]: +2 quote / .05s = +40 quote/s.
    // (40 - 20) / .05s = +400 quote/s^2.
    assert_close(window.quote_flow_acceleration_per_second2, 400.0);
}

#[test]
fn empty_window_has_zero_rates_and_no_price_extrema() {
    let mut state = FastMarketState::with_default_windows(market());
    state
        .apply(event(
            1,
            FastEventKind::Buy,
            1_000,
            1.0,
            0.01,
            Some("buyer-a"),
        ))
        .unwrap();

    let snapshot = state.snapshot(12_000).unwrap();
    let window = snapshot.window(100).unwrap();

    assert_eq!(window.buy_count, 0);
    assert_eq!(window.sell_count, 0);
    assert_eq!(window.unique_buy_actors, 0);
    assert_eq!(window.unique_sell_actors, 0);
    assert_close(window.buy_arrival_rate_per_second, 0.0);
    assert_close(window.sell_arrival_rate_per_second, 0.0);
    assert_close(window.count_imbalance, 0.0);
    assert_close(window.quote_flow_imbalance, 0.0);
    assert_close(window.quote_flow_velocity_per_second, 0.0);
    assert_close(window.quote_flow_acceleration_per_second2, 0.0);
    assert_eq!(window.local_high_price_quote, None);
    assert_eq!(window.local_low_price_quote, None);
    assert_eq!(window.last_price_quote, None);
    assert_close(window.drawdown_from_local_high, 0.0);
    assert_close(window.recovery_from_local_low, 0.0);
}

#[test]
fn actor_counts_ignore_missing_actor_without_affecting_flow() {
    let mut state = FastMarketState::with_default_windows(market());
    state
        .apply(event(1, FastEventKind::Buy, 1_000, 2.0, 0.02, None))
        .unwrap();
    state
        .apply(event(
            2,
            FastEventKind::Sell,
            1_010,
            1.0,
            0.01,
            Some("seller-a"),
        ))
        .unwrap();

    let snapshot = state.snapshot(1_100).unwrap();
    let window = snapshot.window(100).unwrap();

    assert_eq!(window.buy_count, 1);
    assert_eq!(window.sell_count, 1);
    assert_eq!(window.unique_buy_actors, 0);
    assert_eq!(window.unique_sell_actors, 1);
    assert_close(window.net_quote_quantity, 1.0);
}
