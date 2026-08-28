use shreks_providers::{
    pump::WRAPPED_SOL_MINT,
    pump_quote::pump_quote_is_sol,
};

#[test]
fn pump_quote_identity_recognizes_system_sol_and_wrapped_sol_only() {
    assert!(pump_quote_is_sol("11111111111111111111111111111111"));
    assert!(pump_quote_is_sol(WRAPPED_SOL_MINT));
    assert!(!pump_quote_is_sol(
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    ));
}
