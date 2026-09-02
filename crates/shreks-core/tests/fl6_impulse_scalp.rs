use shreks_core::{
    assess_impulse_scalp, ExecutionCostModel, ExecutionLegCostInput, ExecutionTradeInput,
    FastLaneAction, FastMarketKey, FastMarketSnapshot, FastWindowSummary, ImpulseScalpError,
    ImpulseScalpExecutionInput, ImpulseScalpPolicy, ImpulseScalpReason, VenueId,
    EXECUTION_ECONOMICS_VERSION, IMPULSE_SCALP_BASELINE_VERSION,
};

fn market() -> FastMarketKey {
    FastMarketKey::new("mint-1", "quote-1", VenueId::PumpFunBondingCurve).unwrap()
}

fn window(window_ms: u64) -> FastWindowSummary {
    FastWindowSummary {
        window_ms,
        buy_count: 0,
        sell_count: 0,
        unique_buy_actors: 0,
        unique_sell_actors: 0,
        buy_arrival_rate_per_second: 0.0,
        sell_arrival_rate_per_second: 0.0,
        count_imbalance: 0.0,
        buy_base_quantity: 0.0,
        sell_base_quantity: 0.0,
        buy_quote_quantity: 0.0,
        sell_quote_quantity: 0.0,
        net_quote_quantity: 0.0,
        quote_flow_imbalance: 0.0,
        quote_flow_velocity_per_second: 0.0,
        quote_flow_acceleration_per_second2: 0.0,
        local_high_price_quote: Some(0.0102),
        local_low_price_quote: Some(0.0095),
        last_price_quote: Some(0.0101),
        drawdown_from_local_high: 0.009_803_921_568_627_45,
        recovery_from_local_low: 0.063_157_894_736_842_1,
    }
}

fn strong_signal() -> FastWindowSummary {
    let mut value = window(500);
    value.buy_count = 8;
    value.sell_count = 2;
    value.unique_buy_actors = 6;
    value.unique_sell_actors = 2;
    value.buy_arrival_rate_per_second = 16.0;
    value.sell_arrival_rate_per_second = 4.0;
    value.count_imbalance = 0.6;
    value.buy_quote_quantity = 4.5;
    value.sell_quote_quantity = 0.8;
    value.net_quote_quantity = 3.7;
    value.quote_flow_imbalance = 3.7 / 5.3;
    value.quote_flow_velocity_per_second = 7.4;
    value.quote_flow_acceleration_per_second2 = 12.0;
    value
}

fn context_window() -> FastWindowSummary {
    let mut value = window(2_000);
    value.buy_count = 12;
    value.sell_count = 8;
    value.unique_buy_actors = 8;
    value.unique_sell_actors = 6;
    value.count_imbalance = 0.2;
    value.buy_quote_quantity = 7.0;
    value.sell_quote_quantity = 3.0;
    value.net_quote_quantity = 4.0;
    value.quote_flow_imbalance = 0.4;
    value.quote_flow_velocity_per_second = 2.0;
    value.quote_flow_acceleration_per_second2 = 1.0;
    value
}

fn snapshot(signal: FastWindowSummary, context: FastWindowSummary) -> FastMarketSnapshot {
    FastMarketSnapshot {
        market: market(),
        as_of_unix_ms: 10_000,
        last_sequence: Some(42),
        last_price_quote: Some(0.0101),
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: vec![signal, context],
    }
}

fn policy() -> ImpulseScalpPolicy {
    ImpulseScalpPolicy {
        version: IMPULSE_SCALP_BASELINE_VERSION,
        signal_window_ms: 500,
        context_window_ms: 2_000,
        min_buy_count: 5,
        min_unique_buy_actors: 4,
        min_count_imbalance: 0.50,
        min_quote_flow_imbalance: 0.50,
        min_quote_flow_velocity_per_second: 3.0,
        min_quote_flow_acceleration_per_second2: 5.0,
        min_velocity_expansion_ratio: 2.0,
        min_recovery_from_local_low: 0.02,
        max_drawdown_from_local_high: 0.03,
    }
}

fn leg() -> ExecutionLegCostInput {
    ExecutionLegCostInput {
        effective_fee_bps: 50,
        expected_impact_bps: 20,
        expected_slippage_bps: 20,
        expected_latency_bps: 10,
        network_fee_quote: 0.0001,
        priority_fee_quote: 0.0,
        expected_failure_cost_quote: 0.0,
    }
}

fn cost_model() -> ExecutionCostModel {
    ExecutionCostModel {
        version: EXECUTION_ECONOMICS_VERSION,
        entry: leg(),
        exit: leg(),
    }
}

fn execution(trade: ExecutionTradeInput) -> ImpulseScalpExecutionInput {
    ImpulseScalpExecutionInput {
        market: market(),
        as_of_unix_ms: 10_000,
        cost_model: cost_model(),
        trade,
    }
}

fn profitable_trade() -> ExecutionTradeInput {
    ExecutionTradeInput {
        base_quantity: 100.0,
        executable_entry_price_quote: 0.0100,
        forecast_exit_price_quote: 0.0120,
        exit_capacity_base: 125.0,
        required_edge_bps: 200,
        risk_margin_bps: 100,
    }
}

#[test]
fn strong_impulse_with_positive_executable_economics_is_buy() {
    let snapshot = snapshot(strong_signal(), context_window());
    let execution = execution(profitable_trade());

    let assessment = assess_impulse_scalp(&snapshot, Some(&execution), &policy()).unwrap();

    assert_eq!(assessment.version, IMPULSE_SCALP_BASELINE_VERSION);
    assert_eq!(assessment.policy_version, IMPULSE_SCALP_BASELINE_VERSION);
    assert_eq!(assessment.market, market());
    assert_eq!(assessment.as_of_unix_ms, 10_000);
    assert_eq!(assessment.action, FastLaneAction::Buy);
    assert_eq!(assessment.reasons, vec![ImpulseScalpReason::AllConditionsMet]);
    assert_eq!(assessment.signal_window_ms, 500);
    assert_eq!(assessment.context_window_ms, 2_000);
    assert_eq!(assessment.intended_base_quantity, Some(100.0));
    assert_eq!(assessment.executable_entry_price_quote, Some(0.0100));
    assert_eq!(assessment.forecast_exit_price_quote, Some(0.0120));
    assert_eq!(assessment.exit_capacity_base, Some(125.0));
    assert!(assessment.forecast_net_pnl_quote.is_some_and(|value| value > 0.0));
    assert!(assessment.break_even_move_bps.is_some_and(|value| value > 0.0));
    assert!(assessment
        .maximum_acceptable_entry_price_quote
        .is_some_and(|value| value >= 0.0100));
}

#[test]
fn weak_signal_records_all_failed_conditions_in_canonical_order() {
    let mut signal = strong_signal();
    signal.buy_count = 2;
    signal.unique_buy_actors = 1;
    signal.count_imbalance = 0.1;
    signal.quote_flow_imbalance = 0.2;
    signal.quote_flow_velocity_per_second = 1.0;
    signal.quote_flow_acceleration_per_second2 = -2.0;
    signal.recovery_from_local_low = 0.005;
    signal.drawdown_from_local_high = 0.08;
    let mut context = context_window();
    context.quote_flow_velocity_per_second = 1.0;
    let snapshot = snapshot(signal, context);
    let execution = execution(profitable_trade());

    let assessment = assess_impulse_scalp(&snapshot, Some(&execution), &policy()).unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reasons,
        vec![
            ImpulseScalpReason::BuyCountBelowMinimum,
            ImpulseScalpReason::UniqueBuyActorsBelowMinimum,
            ImpulseScalpReason::CountImbalanceBelowMinimum,
            ImpulseScalpReason::QuoteFlowImbalanceBelowMinimum,
            ImpulseScalpReason::QuoteFlowVelocityBelowMinimum,
            ImpulseScalpReason::QuoteFlowAccelerationBelowMinimum,
            ImpulseScalpReason::VelocityExpansionBelowMinimum,
            ImpulseScalpReason::RecoveryBelowMinimum,
            ImpulseScalpReason::DrawdownAboveMaximum,
        ]
    );
}

#[test]
fn signal_velocity_must_expand_against_context_window() {
    let signal = strong_signal();
    let mut context = context_window();
    context.quote_flow_velocity_per_second = 4.0;
    let snapshot = snapshot(signal, context);
    let execution = execution(profitable_trade());

    let assessment = assess_impulse_scalp(&snapshot, Some(&execution), &policy()).unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reasons,
        vec![ImpulseScalpReason::VelocityExpansionBelowMinimum]
    );
}

#[test]
fn missing_execution_evidence_skips_without_zero_filled_economics() {
    let snapshot = snapshot(strong_signal(), context_window());

    let assessment = assess_impulse_scalp(&snapshot, None, &policy()).unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reasons,
        vec![ImpulseScalpReason::ExecutionEconomicsUnavailable]
    );
    assert_eq!(assessment.intended_base_quantity, None);
    assert_eq!(assessment.executable_entry_price_quote, None);
    assert_eq!(assessment.forecast_exit_price_quote, None);
    assert_eq!(assessment.exit_capacity_base, None);
    assert_eq!(assessment.forecast_net_pnl_quote, None);
    assert_eq!(assessment.break_even_move_bps, None);
    assert_eq!(assessment.maximum_acceptable_entry_price_quote, None);
}

#[test]
fn insufficient_exit_capacity_is_a_tradeability_skip_not_a_fabricated_fill() {
    let snapshot = snapshot(strong_signal(), context_window());
    let mut trade = profitable_trade();
    trade.exit_capacity_base = 99.0;
    let execution = execution(trade);

    let assessment = assess_impulse_scalp(&snapshot, Some(&execution), &policy()).unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reasons,
        vec![ImpulseScalpReason::InsufficientExitCapacity]
    );
    assert_eq!(assessment.forecast_net_pnl_quote, None);
    assert_eq!(assessment.maximum_acceptable_entry_price_quote, None);
}

#[test]
fn non_positive_post_cost_forecast_is_skip() {
    let snapshot = snapshot(strong_signal(), context_window());
    let mut trade = profitable_trade();
    trade.executable_entry_price_quote = 0.0120;
    trade.forecast_exit_price_quote = 0.0110;
    let execution = execution(trade);

    let assessment = assess_impulse_scalp(&snapshot, Some(&execution), &policy()).unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert!(assessment
        .reasons
        .contains(&ImpulseScalpReason::ForecastNetPnlNotPositive));
    assert!(assessment.forecast_net_pnl_quote.is_some_and(|value| value <= 0.0));
}

#[test]
fn executable_entry_above_maximum_acceptable_price_is_skip() {
    let snapshot = snapshot(strong_signal(), context_window());
    let mut trade = profitable_trade();
    trade.executable_entry_price_quote = 0.0117;
    trade.forecast_exit_price_quote = 0.0120;
    trade.required_edge_bps = 300;
    trade.risk_margin_bps = 200;
    let execution = execution(trade);

    let assessment = assess_impulse_scalp(&snapshot, Some(&execution), &policy()).unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert!(assessment
        .reasons
        .contains(&ImpulseScalpReason::EntryPriceAboveMaximum));
    assert!(assessment
        .maximum_acceptable_entry_price_quote
        .is_some_and(|maximum| 0.0117 > maximum));
}

#[test]
fn execution_market_or_timestamp_mismatch_fails_closed() {
    let snapshot = snapshot(strong_signal(), context_window());
    let mut wrong_market = execution(profitable_trade());
    wrong_market.market = FastMarketKey::new(
        "other-mint",
        "quote-1",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap();
    assert_eq!(
        assess_impulse_scalp(&snapshot, Some(&wrong_market), &policy()).unwrap_err(),
        ImpulseScalpError::ExecutionMarketMismatch
    );

    let mut wrong_time = execution(profitable_trade());
    wrong_time.as_of_unix_ms = 9_999;
    assert_eq!(
        assess_impulse_scalp(&snapshot, Some(&wrong_time), &policy()).unwrap_err(),
        ImpulseScalpError::ExecutionTimestampMismatch {
            snapshot: 10_000,
            execution: 9_999,
        }
    );
}

#[test]
fn invalid_policy_fails_closed() {
    let snapshot = snapshot(strong_signal(), context_window());
    let execution = execution(profitable_trade());
    let mut invalid = policy();
    invalid.signal_window_ms = invalid.context_window_ms;

    assert!(matches!(
        assess_impulse_scalp(&snapshot, Some(&execution), &invalid),
        Err(ImpulseScalpError::InvalidPolicy(_))
    ));

    let mut invalid = policy();
    invalid.min_quote_flow_imbalance = f64::NAN;
    assert!(matches!(
        assess_impulse_scalp(&snapshot, Some(&execution), &invalid),
        Err(ImpulseScalpError::InvalidPolicy(_))
    ));
}

#[test]
fn repeated_identical_input_is_deterministic() {
    let snapshot = snapshot(strong_signal(), context_window());
    let execution = execution(profitable_trade());
    let policy = policy();

    let first = assess_impulse_scalp(&snapshot, Some(&execution), &policy).unwrap();
    let second = assess_impulse_scalp(&snapshot, Some(&execution), &policy).unwrap();

    assert_eq!(first, second);
}
