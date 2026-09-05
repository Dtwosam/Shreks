use shreks_core::{
    project_entry, EntryProjectionError, FastReserveContext,
};

fn pump(real_base_reserve_raw: u64) -> FastReserveContext {
    FastReserveContext::PumpCurve {
        virtual_base_reserve_raw: 1_000,
        virtual_quote_reserve_raw: 1_000,
        real_base_reserve_raw,
        real_quote_reserve_raw: 900,
        base_decimals: 0,
        quote_decimals: 0,
    }
}

fn pumpswap(
    virtual_quote_reserve_raw: Option<i128>,
    pool_base_reserve_raw: u64,
) -> FastReserveContext {
    FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw,
        pool_quote_reserve_raw: 500,
        virtual_quote_reserve_raw,
        base_decimals: 0,
        quote_decimals: 0,
    }
}

#[test]
fn pump_entry_projection_uses_integer_ceiling_and_worsens_with_size() {
    let reserves = pump(900);

    let small = project_entry(&reserves, 100).unwrap();
    assert_eq!(small.base_quantity_raw, 100);
    assert_eq!(small.quote_input_raw, 112);
    assert_eq!(small.base_quantity, 100.0);
    assert_eq!(small.quote_input, 112.0);
    assert_eq!(small.average_price_quote, 1.12);

    let larger = project_entry(&reserves, 250).unwrap();
    assert_eq!(larger.quote_input_raw, 334);
    assert_eq!(larger.average_price_quote, 334.0 / 250.0);
    assert!(larger.average_price_quote > small.average_price_quote);
}

#[test]
fn pumpswap_entry_projection_uses_known_signed_virtual_quote_reserve() {
    let reserves = pumpswap(Some(500), 1_000);
    let projected = project_entry(&reserves, 100).unwrap();

    assert_eq!(projected.quote_input_raw, 112);
    assert_eq!(projected.average_price_quote, 1.12);
}

#[test]
fn entry_projection_rejects_physical_or_effective_base_exhaustion() {
    assert_eq!(
        project_entry(&pump(100), 101).unwrap_err(),
        EntryProjectionError::PhysicalBaseReserveExhausted
    );
    assert_eq!(
        project_entry(&pumpswap(Some(500), 100), 100).unwrap_err(),
        EntryProjectionError::BaseReserveExhausted
    );
}

#[test]
fn entry_projection_rejects_zero_or_missing_pumpswap_virtual_quote_evidence() {
    assert_eq!(
        project_entry(&pump(900), 0).unwrap_err(),
        EntryProjectionError::ZeroBaseQuantity
    );
    assert_eq!(
        project_entry(&pumpswap(None, 1_000), 100).unwrap_err(),
        EntryProjectionError::MissingPumpSwapVirtualQuoteReserve
    );
    assert_eq!(
        project_entry(&pumpswap(Some(-500), 1_000), 100).unwrap_err(),
        EntryProjectionError::NonPositiveEffectiveQuoteReserve
    );
}
