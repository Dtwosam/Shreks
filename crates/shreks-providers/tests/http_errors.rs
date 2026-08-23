use shreks_core::ProviderId;
use shreks_providers::{
    http::classify_http_failure,
    ProviderErrorKind,
};

#[test]
fn auth_failures_are_not_retryable() {
    for status in [401, 403] {
        let error = classify_http_failure(ProviderId::Helius, status, None, "denied");
        assert_eq!(error.kind, ProviderErrorKind::Unauthorized);
        assert!(!error.is_retryable());
    }
}

#[test]
fn not_found_is_explicit() {
    let error = classify_http_failure(ProviderId::DexScreener, 404, None, "missing");
    assert_eq!(error.kind, ProviderErrorKind::NotFound);
    assert!(!error.is_retryable());
}

#[test]
fn rate_limit_preserves_retry_after_seconds() {
    let error = classify_http_failure(ProviderId::Jupiter, 429, Some("3"), "slow down");
    assert_eq!(error.kind, ProviderErrorKind::RateLimited);
    assert_eq!(error.retry_after_ms, Some(3_000));
    assert!(error.is_retryable());
}

#[test]
fn server_errors_are_retryable_unavailable_failures() {
    for status in [500, 502, 503, 504] {
        let error = classify_http_failure(ProviderId::Helius, status, None, "upstream");
        assert_eq!(error.kind, ProviderErrorKind::Unavailable);
        assert!(error.is_retryable());
    }
}

#[test]
fn other_client_failures_are_invalid_requests() {
    let error = classify_http_failure(ProviderId::Jupiter, 400, None, "bad request");
    assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
    assert!(!error.is_retryable());
}
