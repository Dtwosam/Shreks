use shreks_core::{
    maximum_exit_capacity, project_exit, ExecutionCostModel, ExecutionEconomics,
    ExecutionLegCostInput, ExecutionTradeInput, FastReserveContext, EXECUTION_ECONOMICS_VERSION,
};

fn assert_close(actual: f64, expected: f64) {
    let scale = expected.abs().max(1.0);
    assert!(
        (actual - expected).abs() <= 1e-12 * scale,
        "actual={actual:.15} expected={expected:.15}"
    );
}

fn leg(variable_fee_bps: u32) -> ExecutionLegCostInput {
    ExecutionLegCostInput {
        effective_fee_bps: variable_fee_bps,
        expected_impact_bps: 0,
        expected_slippage_bps: 0,
        expected_latency_bps: 0,
        network_fee_quote: 0.0,
        priority_fee_quote: 0.0,
        expected_failure_cost_quote: 0.0,
    }
}

#[test]
fn reserve_capacity_economics_and_immediate_reprice_form_one_deterministic_gate() {
    let reserves = FastReserveContext::PumpCurve {
        virtual_base_reserve_raw: 1_000,
        virtual_quote_reserve_raw: 1_000,
        real_base_reserve_raw: 900,
        real_quote_reserve_raw: 900,
        base_decimals: 0,
        quote_decimals: 0,
    };

    let capacity = maximum_exit_capacity(&reserves, 0.8).unwrap();
    assert_eq!(capacity.maximum_base_quantity_raw, 250);
    assert_eq!(capacity.boundary_quote_output_raw, 200);

    let intended_base_quantity_raw = 200_u64;
    let executable_exit = project_exit(&reserves, intended_base_quantity_raw).unwrap();
    assert_eq!(executable_exit.quote_output_raw, 166);
    assert_close(executable_exit.average_price_quote, 166.0 / 200.0);

    let model = ExecutionCostModel {
        version: EXECUTION_ECONOMICS_VERSION,
        entry: leg(100),
        exit: leg(200),
    };
    let trade = ExecutionTradeInput {
        base_quantity: intended_base_quantity_raw as f64,
        executable_entry_price_quote: 0.70,
        forecast_exit_price_quote: executable_exit.average_price_quote,
        exit_capacity_base: capacity.maximum_base_quantity,
        required_edge_bps: 300,
        risk_margin_bps: 200,
    };

    let economics = ExecutionEconomics::assess(&model, &trade).unwrap();
    let expected_ceiling = executable_exit.average_price_quote * 0.98 / (1.05 * 1.01);
    assert_close(
        economics.maximum_acceptable_entry_price_quote,
        expected_ceiling,
    );
    assert!(trade.executable_entry_price_quote < expected_ceiling);

    let ceiling = economics.maximum_acceptable_entry_price_quote;
    assert!(economics
        .entry_price_is_acceptable(
            ceiling,
            capacity.maximum_base_quantity,
            trade.base_quantity,
        )
        .unwrap());

    let one_ulp_above = f64::from_bits(ceiling.to_bits() + 1);
    assert!(one_ulp_above > ceiling);
    assert!(!economics
        .entry_price_is_acceptable(
            one_ulp_above,
            capacity.maximum_base_quantity,
            trade.base_quantity,
        )
        .unwrap());

    assert!(!economics
        .entry_price_is_acceptable(
            ceiling,
            f64::from_bits(trade.base_quantity.to_bits() - 1),
            trade.base_quantity,
        )
        .unwrap());
}
