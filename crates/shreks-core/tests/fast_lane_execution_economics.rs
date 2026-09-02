use shreks_core::{
    ExecutionCostModel, ExecutionEconomics, ExecutionLegCostInput, ExecutionTradeInput,
    EXECUTION_ECONOMICS_VERSION,
};

fn assert_close(actual: f64, expected: f64) {
    let scale = expected.abs().max(1.0);
    assert!(
        (actual - expected).abs() <= 1e-12 * scale,
        "actual={actual:.15} expected={expected:.15}"
    );
}

fn leg(
    fee_bps: u32,
    impact_bps: u32,
    slippage_bps: u32,
    latency_bps: u32,
    network_fee_quote: f64,
    priority_fee_quote: f64,
    expected_failure_cost_quote: f64,
) -> ExecutionLegCostInput {
    ExecutionLegCostInput {
        effective_fee_bps: fee_bps,
        expected_impact_bps: impact_bps,
        expected_slippage_bps: slippage_bps,
        expected_latency_bps: latency_bps,
        network_fee_quote,
        priority_fee_quote,
        expected_failure_cost_quote,
    }
}

fn model() -> ExecutionCostModel {
    ExecutionCostModel {
        version: EXECUTION_ECONOMICS_VERSION,
        entry: leg(100, 50, 25, 25, 0.001, 0.0005, 0.0),
        exit: leg(100, 40, 20, 40, 0.0005, 0.0005, 0.0),
    }
}

fn trade(base_quantity: f64) -> ExecutionTradeInput {
    ExecutionTradeInput {
        base_quantity,
        executable_entry_price_quote: 0.01,
        forecast_exit_price_quote: 0.012,
        exit_capacity_base: base_quantity,
        required_edge_bps: 200,
        risk_margin_bps: 100,
    }
}

#[test]
fn round_trip_cost_break_even_and_max_entry_use_all_explicit_costs() {
    let economics = ExecutionEconomics::assess(&model(), &trade(100.0)).unwrap();

    let entry_rate = 0.02;
    let exit_rate = 0.02;
    let entry_fixed = 0.0015;
    let exit_fixed = 0.001;
    let required_return_rate = 0.03;

    let expected_entry_total = 100.0 * 0.01 * (1.0 + entry_rate) + entry_fixed;
    let expected_forecast_exit_net = 100.0 * 0.012 * (1.0 - exit_rate) - exit_fixed;
    let expected_break_even =
        (expected_entry_total + exit_fixed) / (100.0 * (1.0 - exit_rate));
    let expected_break_even_move_bps = (expected_break_even / 0.01 - 1.0) * 10_000.0;
    let max_entry_total = expected_forecast_exit_net / (1.0 + required_return_rate);
    let expected_max_entry =
        (max_entry_total - entry_fixed) / (100.0 * (1.0 + entry_rate));

    assert_eq!(economics.version, EXECUTION_ECONOMICS_VERSION);
    assert_close(economics.entry_total_quote, expected_entry_total);
    assert_close(economics.forecast_exit_net_quote, expected_forecast_exit_net);
    assert_close(
        economics.forecast_net_pnl_quote,
        expected_forecast_exit_net - expected_entry_total,
    );
    assert_close(economics.break_even_exit_price_quote, expected_break_even);
    assert_close(economics.break_even_move_bps, expected_break_even_move_bps);
    assert_close(
        economics.maximum_acceptable_entry_price_quote,
        expected_max_entry,
    );
    assert_close(economics.exit_capacity_base, 100.0);
}

#[test]
fn fixed_quote_costs_raise_break_even_move_more_for_small_notional() {
    let small = ExecutionEconomics::assess(&model(), &trade(10.0)).unwrap();
    let large = ExecutionEconomics::assess(&model(), &trade(1_000.0)).unwrap();

    assert!(small.break_even_move_bps > large.break_even_move_bps);
}

#[test]
fn required_edge_and_risk_margin_lower_the_maximum_entry_price() {
    let baseline = ExecutionEconomics::assess(&model(), &trade(100.0)).unwrap();

    let mut more_edge = trade(100.0);
    more_edge.required_edge_bps = 500;
    let more_edge = ExecutionEconomics::assess(&model(), &more_edge).unwrap();

    let mut more_margin = trade(100.0);
    more_margin.risk_margin_bps = 400;
    let more_margin = ExecutionEconomics::assess(&model(), &more_margin).unwrap();

    assert!(
        more_edge.maximum_acceptable_entry_price_quote
            < baseline.maximum_acceptable_entry_price_quote
    );
    assert!(
        more_margin.maximum_acceptable_entry_price_quote
            < baseline.maximum_acceptable_entry_price_quote
    );
}

#[test]
fn immediate_reprice_accepts_the_ceiling_and_aborts_above_it_or_without_capacity() {
    let economics = ExecutionEconomics::assess(&model(), &trade(100.0)).unwrap();
    let ceiling = economics.maximum_acceptable_entry_price_quote;

    assert!(economics
        .entry_price_is_acceptable(ceiling, 100.0, 100.0)
        .unwrap());
    assert!(!economics
        .entry_price_is_acceptable(f64::from_bits(ceiling.to_bits() + 1), 100.0, 100.0)
        .unwrap());
    assert!(!economics
        .entry_price_is_acceptable(ceiling, 99.999, 100.0)
        .unwrap());
}

#[test]
fn assessment_fails_closed_when_exit_capacity_is_insufficient() {
    let mut input = trade(100.0);
    input.exit_capacity_base = 99.0;
    assert!(ExecutionEconomics::assess(&model(), &input).is_err());
}

#[test]
fn assessment_rejects_invalid_rates_prices_quantities_costs_and_version() {
    let mut invalid_model = model();
    invalid_model.version = 0;
    assert!(ExecutionEconomics::assess(&invalid_model, &trade(100.0)).is_err());

    let mut invalid_rate = model();
    invalid_rate.entry.effective_fee_bps = 10_001;
    assert!(ExecutionEconomics::assess(&invalid_rate, &trade(100.0)).is_err());

    let mut impossible_exit_rate = model();
    impossible_exit_rate.exit = leg(2_500, 2_500, 2_500, 2_500, 0.0, 0.0, 0.0);
    assert!(ExecutionEconomics::assess(&impossible_exit_rate, &trade(100.0)).is_err());

    let mut negative_fixed = model();
    negative_fixed.entry.network_fee_quote = -0.1;
    assert!(ExecutionEconomics::assess(&negative_fixed, &trade(100.0)).is_err());

    let mut nan_fixed = model();
    nan_fixed.exit.priority_fee_quote = f64::NAN;
    assert!(ExecutionEconomics::assess(&nan_fixed, &trade(100.0)).is_err());

    for invalid in [0.0, -1.0, f64::NAN, f64::INFINITY] {
        let mut input = trade(100.0);
        input.base_quantity = invalid;
        assert!(ExecutionEconomics::assess(&model(), &input).is_err());

        let mut input = trade(100.0);
        input.executable_entry_price_quote = invalid;
        assert!(ExecutionEconomics::assess(&model(), &input).is_err());

        let mut input = trade(100.0);
        input.forecast_exit_price_quote = invalid;
        assert!(ExecutionEconomics::assess(&model(), &input).is_err());
    }
}

#[test]
fn forecast_with_no_positive_affordable_entry_fails_closed() {
    let expensive_fixed_model = ExecutionCostModel {
        version: EXECUTION_ECONOMICS_VERSION,
        entry: leg(0, 0, 0, 0, 10.0, 0.0, 0.0),
        exit: leg(0, 0, 0, 0, 0.0, 0.0, 0.0),
    };

    assert!(ExecutionEconomics::assess(&expensive_fixed_model, &trade(100.0)).is_err());
}
