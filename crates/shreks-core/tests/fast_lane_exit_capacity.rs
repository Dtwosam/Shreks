use shreks_core::{maximum_exit_capacity, project_exit, ExitCapacityError, FastReserveContext};

fn pump(real_quote_reserve_raw: u64) -> FastReserveContext {
    FastReserveContext::PumpCurve {
        virtual_base_reserve_raw: 1_000,
        virtual_quote_reserve_raw: 1_000,
        real_base_reserve_raw: 900,
        real_quote_reserve_raw,
        base_decimals: 0,
        quote_decimals: 0,
    }
}

fn pumpswap(
    virtual_quote_reserve_raw: Option<i128>,
    physical_quote_reserve_raw: u64,
) -> FastReserveContext {
    FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: 1_000,
        pool_quote_reserve_raw: physical_quote_reserve_raw,
        virtual_quote_reserve_raw,
        base_decimals: 0,
        quote_decimals: 0,
    }
}

#[test]
fn pump_constant_product_projection_worsens_with_size_and_respects_physical_quote_reserve() {
    let roomy = pump(900);
    let small = project_exit(&roomy, 100).unwrap();
    let larger = project_exit(&roomy, 250).unwrap();

    assert_eq!(small.base_quantity_raw, 100);
    assert_eq!(small.quote_output_raw, 90);
    assert_eq!(small.average_price_quote, 0.9);
    assert_eq!(larger.base_quantity_raw, 250);
    assert_eq!(larger.quote_output_raw, 200);
    assert_eq!(larger.average_price_quote, 0.8);
    assert!(larger.average_price_quote < small.average_price_quote);

    assert_eq!(
        project_exit(&pump(100), 200).unwrap_err(),
        ExitCapacityError::PhysicalQuoteReserveExhausted
    );
}

#[test]
fn pump_capacity_is_the_largest_sell_meeting_the_callers_minimum_average_price() {
    let reserves = pump(900);
    let capacity = maximum_exit_capacity(&reserves, 0.8).unwrap();

    assert_eq!(capacity.maximum_base_quantity_raw, 250);
    assert_eq!(capacity.maximum_base_quantity, 250.0);
    assert_eq!(capacity.boundary_quote_output_raw, 200);
    assert_eq!(capacity.boundary_quote_output, 200.0);
    assert_eq!(capacity.boundary_average_price_quote, 0.8);

    let next = project_exit(&reserves, 251).unwrap();
    assert!(next.average_price_quote < 0.8);
}

#[test]
fn pumpswap_capacity_uses_physical_quote_plus_known_signed_virtual_quote_reserve() {
    let reserves = pumpswap(Some(500), 500);
    let capacity = maximum_exit_capacity(&reserves, 0.8).unwrap();

    assert_eq!(capacity.maximum_base_quantity_raw, 250);
    assert_eq!(capacity.boundary_quote_output_raw, 200);
    assert_eq!(capacity.boundary_average_price_quote, 0.8);
}

#[test]
fn pumpswap_missing_or_non_positive_effective_quote_reserve_fails_closed() {
    assert_eq!(
        maximum_exit_capacity(&pumpswap(None, 500), 0.4).unwrap_err(),
        ExitCapacityError::MissingPumpSwapVirtualQuoteReserve
    );
    assert_eq!(
        maximum_exit_capacity(&pumpswap(Some(-500), 500), 0.4).unwrap_err(),
        ExitCapacityError::NonPositiveEffectiveQuoteReserve
    );
}

#[test]
fn capacity_rejects_invalid_or_impossible_price_boundaries_and_zero_quantity() {
    let reserves = pump(900);

    assert_eq!(
        project_exit(&reserves, 0).unwrap_err(),
        ExitCapacityError::ZeroBaseQuantity
    );
    assert_eq!(
        maximum_exit_capacity(&reserves, 0.0).unwrap_err(),
        ExitCapacityError::InvalidMinimumAverageExitPrice
    );
    assert_eq!(
        maximum_exit_capacity(&reserves, f64::NAN).unwrap_err(),
        ExitCapacityError::InvalidMinimumAverageExitPrice
    );
    assert_eq!(
        maximum_exit_capacity(&reserves, 1.1).unwrap_err(),
        ExitCapacityError::ImpossibleMinimumAveragePrice
    );
}
