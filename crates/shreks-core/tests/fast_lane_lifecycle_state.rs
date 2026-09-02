use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FastMarketState, FastStateError,
    LifecycleEventKind, ProviderId, TokenLifecycleEvent, VenueId,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn market() -> FastMarketKey {
    FastMarketKey::new("mint-a", WSOL, VenueId::PumpFunBondingCurve).unwrap()
}

fn trade(sequence: u64, observed_at_unix_ms: i64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(format!("trade-{sequence}"), 0).unwrap(),
        sequence,
        ProviderId::SolanaPublic,
        market(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        10,
        observed_at_unix_ms,
        observed_at_unix_ms,
        10.0,
        1.0,
        0.1,
    )
    .unwrap()
}

fn graduation(detected_at_unix_ms: i64) -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::SolanaPublic,
        mint: "mint-a".to_owned(),
        quote_mint: WSOL.to_owned(),
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: "pool-a".to_owned(),
        signature: format!("graduation-{detected_at_unix_ms}"),
        slot: 11,
        detected_at_unix_ms,
        occurred_at_unix_ms: Some(detected_at_unix_ms - 50),
    }
}

#[test]
fn lifecycle_uses_its_own_detection_clock_instead_of_trade_sequence_order() {
    let mut state = FastMarketState::with_default_windows(market());
    state.apply(trade(1, 1_000)).unwrap();

    let lifecycle = graduation(900);
    state.apply_lifecycle(lifecycle.clone()).unwrap();

    let snapshot = state.snapshot(1_000).unwrap();
    assert_eq!(snapshot.last_lifecycle_event, Some(lifecycle));
}

#[test]
fn snapshot_cannot_precede_latest_lifecycle_detection() {
    let mut state = FastMarketState::with_default_windows(market());
    state.apply_lifecycle(graduation(1_100)).unwrap();

    let error = state.snapshot(1_099).unwrap_err();
    assert_eq!(
        error,
        FastStateError::SnapshotBeforeLastLifecycleObservation {
            last_detected_at_unix_ms: 1_100,
            as_of_unix_ms: 1_099,
        }
    );
}

#[test]
fn lifecycle_must_map_to_the_state_market() {
    let mut state = FastMarketState::with_default_windows(market());
    let mut lifecycle = graduation(1_000);
    lifecycle.mint = "other-mint".to_owned();

    assert_eq!(
        state.apply_lifecycle(lifecycle).unwrap_err(),
        FastStateError::LifecycleMarketMismatch
    );
}

#[test]
fn lifecycle_detection_time_cannot_move_backward_within_lifecycle_stream() {
    let mut state = FastMarketState::with_default_windows(market());
    state.apply_lifecycle(graduation(1_000)).unwrap();

    let error = state.apply_lifecycle(graduation(999)).unwrap_err();
    assert_eq!(
        error,
        FastStateError::LifecycleObservationTimeMovedBackward {
            last: 1_000,
            incoming: 999,
        }
    );
}
