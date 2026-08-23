use shreks_core::{ProviderId, VenueId};
use shreks_providers::dexscreener::classify_dex_venue;

#[test]
fn meteora_is_a_provider_and_venues_are_separate() {
    assert_eq!(ProviderId::Meteora.as_str(), "meteora");
    assert_eq!(VenueId::PumpFunBondingCurve.as_str(), "pump_fun_bonding_curve");
    assert_eq!(VenueId::PumpSwap.as_str(), "pump_swap");
    assert_eq!(VenueId::MeteoraDlmm.as_str(), "meteora_dlmm");
    assert_eq!(VenueId::MeteoraDammV2.as_str(), "meteora_damm_v2");
    assert_eq!(VenueId::OtherSolana.as_str(), "other_solana");
}

#[test]
fn dexscreener_dex_ids_map_to_first_class_venues() {
    assert_eq!(classify_dex_venue("pumpfun"), VenueId::PumpFunBondingCurve);
    assert_eq!(classify_dex_venue("pumpswap"), VenueId::PumpSwap);
    assert_eq!(classify_dex_venue("meteora"), VenueId::OtherSolana);
    assert_eq!(classify_dex_venue("raydium"), VenueId::OtherSolana);
}
