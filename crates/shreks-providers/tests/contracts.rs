use shreks_core::{ProviderHealthState, ProviderId, QuoteRequest};
use shreks_providers::{ProviderError, ProviderErrorKind};

#[test]
fn provider_identifiers_are_stable() {
    assert_eq!(ProviderId::DexScreener.as_str(), "dexscreener");
    assert_eq!(ProviderId::Helius.as_str(), "helius");
    assert_eq!(ProviderId::Jupiter.as_str(), "jupiter");
    assert_eq!(ProviderId::Meteora.as_str(), "meteora");
}

#[test]
fn provider_health_states_are_stable() {
    assert_eq!(ProviderHealthState::Healthy.as_str(), "healthy");
    assert_eq!(ProviderHealthState::Degraded.as_str(), "degraded");
    assert_eq!(ProviderHealthState::RateLimited.as_str(), "rate_limited");
    assert_eq!(ProviderHealthState::Unavailable.as_str(), "unavailable");
}

#[test]
fn retryability_is_explicit() {
    for kind in [
        ProviderErrorKind::RateLimited,
        ProviderErrorKind::Unavailable,
        ProviderErrorKind::Timeout,
    ] {
        assert!(kind.is_retryable(), "{kind:?} should be retryable");
    }

    for kind in [
        ProviderErrorKind::Unauthorized,
        ProviderErrorKind::NotFound,
        ProviderErrorKind::InvalidRequest,
        ProviderErrorKind::InvalidResponse,
    ] {
        assert!(!kind.is_retryable(), "{kind:?} should not be retryable");
    }
}

#[test]
fn provider_error_preserves_retry_after() {
    let error = ProviderError::new(
        ProviderId::DexScreener,
        ProviderErrorKind::RateLimited,
        "slow down",
    )
    .with_retry_after_ms(2_000);

    assert_eq!(error.provider, ProviderId::DexScreener);
    assert_eq!(error.kind, ProviderErrorKind::RateLimited);
    assert_eq!(error.retry_after_ms, Some(2_000));
    assert!(error.is_retryable());
}

#[test]
fn provider_errors_map_to_operational_health_without_becoming_market_signals() {
    let cases = [
        (ProviderErrorKind::RateLimited, ProviderHealthState::RateLimited),
        (ProviderErrorKind::Timeout, ProviderHealthState::Unavailable),
        (ProviderErrorKind::Unavailable, ProviderHealthState::Unavailable),
        (ProviderErrorKind::Unauthorized, ProviderHealthState::Degraded),
        (ProviderErrorKind::NotFound, ProviderHealthState::Degraded),
        (ProviderErrorKind::InvalidRequest, ProviderHealthState::Degraded),
        (ProviderErrorKind::InvalidResponse, ProviderHealthState::Degraded),
    ];

    for (kind, expected) in cases {
        let error = ProviderError::new(ProviderId::Meteora, kind, "fixture failure");
        assert_eq!(error.health_state(), expected, "wrong health mapping for {kind:?}");
    }
}

#[test]
fn quote_request_validates_critical_fields() {
    let quote = QuoteRequest::new(
        "So11111111111111111111111111111111111111112",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        1_000_000,
        "11111111111111111111111111111111",
        100,
    )
    .expect("valid quote request");

    assert_eq!(quote.amount, 1_000_000);
    assert_eq!(quote.slippage_bps, 100);

    assert!(QuoteRequest::new("", "out", 1, "taker", 1).is_err());
    assert!(QuoteRequest::new("in", "", 1, "taker", 1).is_err());
    assert!(QuoteRequest::new("same", "same", 1, "taker", 1).is_err());
    assert!(QuoteRequest::new("in", "out", 0, "taker", 1).is_err());
    assert!(QuoteRequest::new("in", "out", 1, "", 1).is_err());
    assert!(QuoteRequest::new("in", "out", 1, "taker", 10_001).is_err());
}
