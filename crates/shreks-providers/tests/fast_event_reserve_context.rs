use shreks_core::FastReserveContext;
use shreks_providers::{
    pump::WRAPPED_SOL_MINT,
    pump_swap_trade::{
        PumpSwapCurrentEconomicsEvidence, PumpSwapTradeEvidence,
        pump_swap_trade_evidence_to_fast_event,
    },
    pump_trade::{PumpTradeEvidence, pump_trade_evidence_to_fast_event},
};

const SYSTEM_SOL: &str = "11111111111111111111111111111111";

#[test]
fn pump_conversion_carries_exact_source_reserves_into_fast_event() {
    let evidence = PumpTradeEvidence {
        mint: "mint-a".to_owned(),
        quote_mint: SYSTEM_SOL.to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        token_amount_raw: 2_000_000,
        sol_amount_raw: 100_000_000,
        quote_amount_raw: 0,
        timestamp_unix_seconds: 1,
        virtual_sol_reserves_raw: 10_000_000_000,
        virtual_token_reserves_raw: 20_000_000_000,
        real_sol_reserves_raw: 5_000_000_000,
        real_token_reserves_raw: 10_000_000_000,
        virtual_quote_reserves_raw: 77,
        real_quote_reserves_raw: 88,
        fee_recipient: "fee-recipient".to_owned(),
        fee_basis_points: 95,
        fee_raw: 950_000,
        creator: "creator".to_owned(),
        creator_fee_basis_points: 30,
        creator_fee_raw: 300_000,
        cashback_fee_basis_points: 5,
        cashback_raw: 50_000,
        buyback_fee_basis_points: 7,
        buyback_fee_raw: 70_000,
        ix_name: "buy".to_owned(),
    };

    let event =
        pump_trade_evidence_to_fast_event(&evidence, "pump-sig", 0, 1, 10, 1_100, 6, 9).unwrap();

    assert_eq!(
        event.reserve_context,
        Some(FastReserveContext::PumpCurve {
            virtual_base_reserve_raw: 20_000_000_000,
            virtual_quote_reserve_raw: 10_000_000_000,
            real_base_reserve_raw: 10_000_000_000,
            real_quote_reserve_raw: 5_000_000_000,
            base_decimals: 6,
            quote_decimals: 9,
        })
    );
}

fn pumpswap_evidence(
    current_economics: Option<PumpSwapCurrentEconomicsEvidence>,
) -> PumpSwapTradeEvidence {
    PumpSwapTradeEvidence {
        log_index: 7,
        pool: "pool-a".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: 1,
        pool_base_reserves_raw: 9_500_000_000,
        pool_quote_reserves_raw: 52_500_000_000,
        lp_fee_basis_points: 20,
        lp_fee_raw: 5_000_000,
        protocol_fee_basis_points: 93,
        protocol_fee_raw: 23_250_000,
        quote_amount_with_or_without_lp_fee_raw: 2_505_000_000,
        current_economics,
    }
}

#[test]
fn legacy_pumpswap_conversion_keeps_virtual_quote_reserve_unknown() {
    let evidence = pumpswap_evidence(None);

    let event = pump_swap_trade_evidence_to_fast_event(
        &evidence,
        "swap-sig",
        7,
        1,
        10,
        1_100,
        "mint-a",
        WRAPPED_SOL_MINT,
        6,
        9,
    )
    .unwrap();

    assert_eq!(
        event.reserve_context,
        Some(FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw: 9_500_000_000,
            pool_quote_reserve_raw: 52_500_000_000,
            virtual_quote_reserve_raw: None,
            base_decimals: 6,
            quote_decimals: 9,
        })
    );
}

#[test]
fn current_pumpswap_conversion_carries_signed_virtual_quote_reserve() {
    let evidence = pumpswap_evidence(Some(PumpSwapCurrentEconomicsEvidence {
        coin_creator: "creator-a".to_owned(),
        coin_creator_fee_basis_points: 30,
        coin_creator_fee_raw: 7_500_000,
        cashback_fee_basis_points: 5,
        cashback_raw: 1_250_000,
        buyback_fee_basis_points: 7,
        buyback_fee_raw: 1_750_000,
        virtual_quote_reserves_raw: 17_000_000_000,
        can_boost: true,
        base_supply_raw: 1_000_000_000_000,
    }));

    let event = pump_swap_trade_evidence_to_fast_event(
        &evidence,
        "swap-current",
        7,
        1,
        10,
        1_100,
        "mint-a",
        WRAPPED_SOL_MINT,
        6,
        9,
    )
    .unwrap();

    assert_eq!(
        event.reserve_context,
        Some(FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw: 9_500_000_000,
            pool_quote_reserve_raw: 52_500_000_000,
            virtual_quote_reserve_raw: Some(17_000_000_000),
            base_decimals: 6,
            quote_decimals: 9,
        })
    );
}
