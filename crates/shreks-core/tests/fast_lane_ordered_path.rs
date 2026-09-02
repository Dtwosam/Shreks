use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FastMarketState, ProviderId, VenueId,
};

fn market() -> FastMarketKey {
    FastMarketKey::new("mint-ordered-path", "quote-sol", VenueId::PumpFunBondingCurve).unwrap()
}

fn event(sequence: u64, observed_at_unix_ms: i64, kind: FastEventKind, price: f64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(format!("ordered-{sequence}"), 0).unwrap(),
        sequence,
        ProviderId::Helius,
        market(),
        kind,
        Some(format!("wallet-{sequence}")),
        1_000 + sequence,
        observed_at_unix_ms,
        observed_at_unix_ms,
        100.0,
        price * 100.0,
        price,
    )
    .unwrap()
}

#[test]
fn summary_preserves_ordered_impulse_peak_post_high_trough_and_reclaim() {
    let mut state = FastMarketState::with_default_windows(market());
    state.apply(event(1, 1_000, FastEventKind::Buy, 0.0100)).unwrap();
    state.apply(event(2, 1_100, FastEventKind::Buy, 0.0120)).unwrap();
    state.apply(event(3, 1_200, FastEventKind::Sell, 0.0110)).unwrap();
    state.apply(event(4, 1_300, FastEventKind::Buy, 0.0117)).unwrap();

    let snapshot = state.snapshot(1_300).unwrap();
    let window = snapshot.window(2_000).unwrap();

    assert_eq!(window.local_low_price_quote, Some(0.0100));
    assert_eq!(window.local_low_sequence, Some(1));
    assert_eq!(window.local_low_observed_at_unix_ms, Some(1_000));
    assert_eq!(window.local_high_price_quote, Some(0.0120));
    assert_eq!(window.local_high_sequence, Some(2));
    assert_eq!(window.local_high_observed_at_unix_ms, Some(1_100));
    assert_eq!(window.post_high_low_price_quote, Some(0.0110));
    assert_eq!(window.post_high_low_sequence, Some(3));
    assert_eq!(window.post_high_low_observed_at_unix_ms, Some(1_200));
    assert_eq!(window.last_price_quote, Some(0.0117));
}

#[test]
fn strictly_higher_new_peak_resets_post_high_trough_evidence() {
    let mut state = FastMarketState::with_default_windows(market());
    state.apply(event(1, 2_000, FastEventKind::Buy, 0.0100)).unwrap();
    state.apply(event(2, 2_100, FastEventKind::Buy, 0.0120)).unwrap();
    state.apply(event(3, 2_200, FastEventKind::Sell, 0.0110)).unwrap();
    state.apply(event(4, 2_300, FastEventKind::Buy, 0.0130)).unwrap();

    let snapshot = state.snapshot(2_300).unwrap();
    let window = snapshot.window(2_000).unwrap();

    assert_eq!(window.local_high_price_quote, Some(0.0130));
    assert_eq!(window.local_high_sequence, Some(4));
    assert_eq!(window.local_high_observed_at_unix_ms, Some(2_300));
    assert_eq!(window.post_high_low_price_quote, None);
    assert_eq!(window.post_high_low_sequence, None);
    assert_eq!(window.post_high_low_observed_at_unix_ms, None);
}

#[test]
fn equal_price_peak_retest_does_not_rewrite_peak_identity_or_trough() {
    let mut state = FastMarketState::with_default_windows(market());
    state.apply(event(1, 3_000, FastEventKind::Buy, 0.0100)).unwrap();
    state.apply(event(2, 3_100, FastEventKind::Buy, 0.0120)).unwrap();
    state.apply(event(3, 3_200, FastEventKind::Sell, 0.0110)).unwrap();
    state.apply(event(4, 3_300, FastEventKind::Buy, 0.0120)).unwrap();

    let snapshot = state.snapshot(3_300).unwrap();
    let window = snapshot.window(2_000).unwrap();

    assert_eq!(window.local_high_sequence, Some(2));
    assert_eq!(window.local_high_observed_at_unix_ms, Some(3_100));
    assert_eq!(window.post_high_low_price_quote, Some(0.0110));
    assert_eq!(window.post_high_low_sequence, Some(3));
    assert_eq!(window.post_high_low_observed_at_unix_ms, Some(3_200));
}

#[test]
fn ordered_path_summary_is_replay_deterministic() {
    let events = vec![
        event(1, 4_000, FastEventKind::Buy, 0.0100),
        event(2, 4_100, FastEventKind::Buy, 0.0120),
        event(3, 4_200, FastEventKind::Sell, 0.0110),
        event(4, 4_300, FastEventKind::Buy, 0.0117),
    ];

    let mut left = FastMarketState::with_default_windows(market());
    let mut right = FastMarketState::with_default_windows(market());
    for item in events {
        left.apply(item.clone()).unwrap();
        right.apply(item).unwrap();
    }

    assert_eq!(left.snapshot(4_300).unwrap(), right.snapshot(4_300).unwrap());
}