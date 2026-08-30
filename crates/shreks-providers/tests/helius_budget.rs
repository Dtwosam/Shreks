use shreks_providers::{
    helius::HeliusProvider,
    ProviderErrorKind,
};

#[test]
fn helius_request_budget_is_explicit_and_secret_safe() {
    let provider = HeliusProvider::new("super-secret-helius-key")
        .expect("valid provider")
        .with_request_budget(3)
        .expect("positive budget");

    let usage = provider.request_usage();
    assert_eq!(usage.attempted, 0);
    assert_eq!(usage.limit, Some(3));
    assert_eq!(usage.remaining, Some(3));
    assert!(!usage.exhausted);

    let debug = format!("{provider:?}");
    assert!(debug.contains("request_budget"));
    assert!(!debug.contains("super-secret-helius-key"));
}

#[test]
fn helius_request_budget_rejects_zero_limit() {
    let error = HeliusProvider::new("test-key")
        .expect("valid provider")
        .with_request_budget(0)
        .expect_err("zero request budget must fail closed");

    assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
}
