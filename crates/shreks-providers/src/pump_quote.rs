use crate::pump::WRAPPED_SOL_MINT;

pub const SYSTEM_SOL_QUOTE_MINT: &str = "11111111111111111111111111111111";
pub const SOL_QUOTE_DECIMALS: u8 = 9;

pub fn pump_quote_is_sol(quote_mint: &str) -> bool {
    matches!(quote_mint, SYSTEM_SOL_QUOTE_MINT | WRAPPED_SOL_MINT)
}
