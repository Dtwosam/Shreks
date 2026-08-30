use shreks_core::ProviderId;

#[test]
fn solana_public_provider_has_stable_provenance_name() {
    assert_eq!(ProviderId::SolanaPublic.as_str(), "solana_public");
    assert_eq!(ProviderId::SolanaPublic.to_string(), "solana_public");
}
