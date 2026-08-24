use shreks_core::{
    ProviderId, VenueId, WalletActionKind, WalletObservation, WalletObservationEvidence,
};

#[test]
fn wallet_action_and_evidence_strings_are_stable() {
    assert_eq!(WalletActionKind::Buy.as_str(), "buy");
    assert_eq!(WalletActionKind::Sell.as_str(), "sell");
    assert_eq!(WalletActionKind::Transfer.as_str(), "transfer");
    assert_eq!(WalletActionKind::LiquidityEvent.as_str(), "liquidity_event");
    assert_eq!(WalletActionKind::CreatorAction.as_str(), "creator_action");
    assert_eq!(WalletActionKind::Other.as_str(), "other");

    assert_eq!(WalletObservationEvidence::Direct.as_str(), "direct");
    assert_eq!(WalletObservationEvidence::Inferred.as_str(), "inferred");
}

#[test]
fn wallet_observation_preserves_full_width_slot_and_signed_raw_amounts() {
    let beyond_i64 = i128::from(i64::MAX) + 123_456;
    let observation = WalletObservation {
        provider: ProviderId::Helius,
        wallet: "Wallet111".to_owned(),
        candidate_mint: "Mint111".to_owned(),
        action: WalletActionKind::Buy,
        evidence: WalletObservationEvidence::Direct,
        signature: "Sig111".to_owned(),
        event_index: u32::MAX,
        slot: u64::MAX,
        observed_at_unix_ms: 1_000,
        occurred_at_unix_ms: Some(900),
        candidate_token_delta_raw: Some(beyond_i64),
        counter_asset_mint: Some("So11111111111111111111111111111111111111112".to_owned()),
        counter_asset_delta_raw: Some(-beyond_i64),
        venue: Some(VenueId::PumpSwap),
        counterparty: Some("Pool111".to_owned()),
    };

    assert_eq!(observation.slot, u64::MAX);
    assert_eq!(observation.event_index, u32::MAX);
    assert_eq!(observation.candidate_token_delta_raw, Some(beyond_i64));
    assert_eq!(observation.counter_asset_delta_raw, Some(-beyond_i64));
    assert_eq!(observation.evidence, WalletObservationEvidence::Direct);
}
