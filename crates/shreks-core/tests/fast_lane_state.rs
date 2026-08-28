use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FastMarketState, FastStateError,
    ProviderId, VenueId, DEFAULT_FAST_WINDOWS_MS,
};

fn pump_market() -> FastMarketKey {
    FastMarketKey::new(
        "Mint111111111111111111111111111111111111111",
        "So11111111111111111111111111111111111111112",
        VenueId::PumpFunBondingCurve,
    )
    .expect("test market must be valid")
}

fn other_market() -> FastMarketKey {
    FastMarketKey::new(
        "Mint222222222222222222222222222222222222222",
        "So11111111111111111111111111111111111111112",
        VenueId::PumpFunBondingCurve,
    )
    .expect("test market must be valid")
}

fn trade_event(
    market: FastMarketKey,
    sequence: u64,
    ordinal: u32,
    kind: FastEventKind,
    occurred_at_unix_ms: i64,
    base_quantity: f64,
    quote_quantity: f64,
    price_quote: f64,
) -> FastEvent {
    FastEvent::new(
        FastEventId::new(format!("sig-{sequence}"), ordinal).expect("event id must be valid"),
        sequence,
        ProviderId::Helius,
        market,
        kind,
        Some("wallet-1".to_owned()),
        100 + sequence,
        occurred_at_unix_ms,
        occurred_at_unix_ms + 5,
        base_quantity,
        quote_quantity,
        price_quote,
    )
    .expect("test event must be valid")
}

#[test]
fn default_windows_capture_short_flow_without_turning_windows_into_timers() {
    assert_eq!(
        DEFAULT_FAST_WINDOWS_MS,
        [100, 250, 500, 1_000, 2_000, 5_000, 10_000]
    );

    let market = pump_market();
    let mut state = FastMarketState::with_default_windows(market.clone());
    state
        .apply(trade_event(
            market.clone(),
            1,
            0,
            FastEventKind::Buy,
            1_000,
            100.0,
            2.0,
            0.020,
        ))
        .unwrap();
    state
        .apply(trade_event(
            market.clone(),
            2,
            0,
            FastEventKind::Sell,
            1_250,
            20.0,
            0.5,
            0.025,
        ))
        .unwrap();

    let snapshot = state.snapshot(1_300).unwrap();
    assert_eq!(snapshot.market, market);
    assert_eq!(snapshot.last_sequence, Some(2));
    assert_eq!(snapshot.last_price_quote, Some(0.025));

    let window_100 = snapshot.window(100).unwrap();
    assert_eq!(window_100.buy_count, 0);
    assert_eq!(window_100.sell_count, 1);
    assert_eq!(window_100.buy_quote_quantity, 0.0);
    assert_eq!(window_100.sell_quote_quantity, 0.5);
    assert_eq!(window_100.net_quote_quantity, -0.5);

    let window_250 = snapshot.window(250).unwrap();
    assert_eq!(window_250.buy_count, 0);
    assert_eq!(window_250.sell_count, 1);
    assert_eq!(window_250.sell_base_quantity, 20.0);

    let window_500 = snapshot.window(500).unwrap();
    assert_eq!(window_500.buy_count, 1);
    assert_eq!(window_500.sell_count, 1);
    assert_eq!(window_500.buy_base_quantity, 100.0);
    assert_eq!(window_500.sell_base_quantity, 20.0);
    assert_eq!(window_500.buy_quote_quantity, 2.0);
    assert_eq!(window_500.sell_quote_quantity, 0.5);
    assert_eq!(window_500.net_quote_quantity, 1.5);
}

#[test]
fn exact_lower_window_boundary_is_inclusive() {
    let market = pump_market();
    let mut state = FastMarketState::with_default_windows(market.clone());
    state
        .apply(trade_event(
            market,
            1,
            0,
            FastEventKind::Buy,
            1_000,
            10.0,
            1.0,
            0.1,
        ))
        .unwrap();

    let snapshot = state.snapshot(1_250).unwrap();
    let window = snapshot.window(250).unwrap();
    assert_eq!(window.buy_count, 1);
    assert_eq!(window.buy_quote_quantity, 1.0);
}

#[test]
fn state_rejects_market_mismatch_and_non_monotonic_event_order() {
    let market = pump_market();
    let mut state = FastMarketState::with_default_windows(market.clone());
    state
        .apply(trade_event(
            market.clone(),
            10,
            0,
            FastEventKind::Buy,
            2_000,
            10.0,
            1.0,
            0.1,
        ))
        .unwrap();

    let mismatch = state.apply(trade_event(
        other_market(),
        11,
        0,
        FastEventKind::Buy,
        2_100,
        10.0,
        1.0,
        0.1,
    ));
    assert!(matches!(mismatch, Err(FastStateError::MarketMismatch)));

    let duplicate_sequence = state.apply(trade_event(
        market.clone(),
        10,
        1,
        FastEventKind::Sell,
        2_100,
        5.0,
        0.5,
        0.1,
    ));
    assert!(matches!(
        duplicate_sequence,
        Err(FastStateError::NonMonotonicSequence {
            last: 10,
            incoming: 10
        })
    ));

    let backward_time = state.apply(trade_event(
        market.clone(),
        11,
        0,
        FastEventKind::Sell,
        1_999,
        5.0,
        0.5,
        0.1,
    ));
    assert!(matches!(
        backward_time,
        Err(FastStateError::EventTimeMovedBackward {
            last: 2_000,
            incoming: 1_999
        })
    ));

    state
        .apply(trade_event(
            market,
            11,
            0,
            FastEventKind::Sell,
            2_000,
            5.0,
            0.5,
            0.1,
        ))
        .expect("same occurrence time is valid when sequence increases");
}

#[test]
fn replaying_the_same_events_produces_the_same_snapshot() {
    let market = pump_market();
    let events = vec![
        trade_event(
            market.clone(),
            1,
            0,
            FastEventKind::Buy,
            10_000,
            100.0,
            4.0,
            0.04,
        ),
        trade_event(
            market.clone(),
            2,
            0,
            FastEventKind::Buy,
            10_150,
            50.0,
            2.5,
            0.05,
        ),
        trade_event(
            market.clone(),
            3,
            0,
            FastEventKind::Sell,
            10_300,
            20.0,
            1.2,
            0.06,
        ),
    ];

    let mut left = FastMarketState::with_default_windows(market.clone());
    let mut right = FastMarketState::with_default_windows(market);
    for event in &events {
        left.apply(event.clone()).unwrap();
        right.apply(event.clone()).unwrap();
    }

    assert_eq!(left.snapshot(10_400).unwrap(), right.snapshot(10_400).unwrap());
}

#[test]
fn fast_event_constructors_reject_invalid_identity_time_and_economics() {
    assert!(FastMarketKey::new("", "SOL", VenueId::PumpFunBondingCurve).is_err());
    assert!(FastMarketKey::new("MINT", "", VenueId::PumpFunBondingCurve).is_err());
    assert!(FastEventId::new("", 0).is_err());

    let market = pump_market();
    let id = FastEventId::new("sig-valid", 0).unwrap();

    let invalid_actor = FastEvent::new(
        id.clone(),
        1,
        ProviderId::Helius,
        market.clone(),
        FastEventKind::Buy,
        Some("   ".to_owned()),
        1,
        1_000,
        1_001,
        1.0,
        1.0,
        1.0,
    );
    assert!(invalid_actor.is_err());

    let negative_time = FastEvent::new(
        id.clone(),
        1,
        ProviderId::Helius,
        market.clone(),
        FastEventKind::Buy,
        None,
        1,
        -1,
        0,
        1.0,
        1.0,
        1.0,
    );
    assert!(negative_time.is_err());

    let observed_before_occurrence = FastEvent::new(
        id.clone(),
        1,
        ProviderId::Helius,
        market.clone(),
        FastEventKind::Buy,
        None,
        1,
        1_000,
        999,
        1.0,
        1.0,
        1.0,
    );
    assert!(observed_before_occurrence.is_err());

    for (base_quantity, quote_quantity, price_quote) in [
        (0.0, 1.0, 1.0),
        (1.0, 0.0, 1.0),
        (-1.0, 1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 0.0),
        (f64::NAN, 1.0, 1.0),
        (1.0, f64::INFINITY, 1.0),
        (1.0, 1.0, f64::NAN),
    ] {
        let result = FastEvent::new(
            id.clone(),
            1,
            ProviderId::Helius,
            market.clone(),
            FastEventKind::Buy,
            None,
            1,
            1_000,
            1_001,
            base_quantity,
            quote_quantity,
            price_quote,
        );
        assert!(result.is_err());
    }
}

#[test]
fn snapshot_rejects_time_before_the_latest_accepted_event() {
    let market = pump_market();
    let mut state = FastMarketState::with_default_windows(market.clone());
    state
        .apply(trade_event(
            market,
            1,
            0,
            FastEventKind::Buy,
            5_000,
            1.0,
            1.0,
            1.0,
        ))
        .unwrap();

    assert!(matches!(
        state.snapshot(4_999),
        Err(FastStateError::SnapshotBeforeLastEvent {
            last_event_at_unix_ms: 5_000,
            as_of_unix_ms: 4_999
        })
    ));
}
