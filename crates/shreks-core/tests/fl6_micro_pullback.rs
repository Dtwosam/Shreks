use shreks_core::{
    assess_micro_pullback, ExecutionCostModel, ExecutionLegCostInput, ExecutionTradeInput,
    FastLaneAction, FastMarketKey, FastMarketSnapshot, FastWindowSummary, MicroPullbackError,
    MicroPullbackExecutionInput, MicroPullbackPolicy, MicroPullbackReason, VenueId,
    EXECUTION_ECONOMICS_VERSION, MICRO_PULLBACK_BASELINE_VERSION,
};

fn market() -> FastMarketKey {
    FastMarketKey::new(
        "mint-pullback",
        "quote-sol",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap()
}

fn other_market() -> FastMarketKey {
    FastMarketKey::new(
        "other-mint",
        "quote-sol",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap()
}

fn empty_window(window_ms: u64) -> FastWindowSummary {
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
        local_high_price_quote: None,
        local_high_sequence: None,
        local_high_observed_at_unix_ms: None,
        local_low_price_quote: None,
        local_low_sequence: None,
        local_low_observed_at_unix_ms: None,
        post_high_low_price_quote: None,
        post_high_low_sequence: None,
        post_high_low_observed_at_unix_ms: None,
        last_price_quote: None,
        drawdown_from_local_high: 0.0,
        recovery_from_local_low: 0.0,
    }
}

fn strong_structure() -> FastWindowSummary {
    let mut value = empty_window(2_000);
    value.buy_count = 12;
    value.sell_count = 6;
    value.unique_buy_actors = 9;
    value.unique_sell_actors = 5;
    value.buy_arrival_rate_per_second = 6.0;
    value.sell_arrival_rate_per_second = 3.0;
    value.count_imbalance = 1.0 / 3.0;
    value.buy_quote_quantity = 8.0;
    value.sell_quote_quantity = 3.0;
    value.net_quote_quantity = 5.0;
    value.quote_flow_imbalance = 5.0 / 11.0;
    value.quote_flow_velocity_per_second = 2.5;
    value.quote_flow_acceleration_per_second2 = 1.0;
    value.local_low_price_quote = Some(0.0100);
    value.local_low_sequence = Some(10);
    value.local_low_observed_at_unix_ms = Some(8_500);
    value.local_high_price_quote = Some(0.0120);
    value.local_high_sequence = Some(20);
    value.local_high_observed_at_unix_ms = Some(9_000);
    value.post_high_low_price_quote = Some(0.0110);
    value.post_high_low_sequence = Some(30);
    value.post_high_low_observed_at_unix_ms = Some(9_500);
    value.last_price_quote = Some(0.0117);
    value.drawdown_from_local_high = 0.025;
    value.recovery_from_local_low = 0.17;
    value
}

fn strong_reclaim() -> FastWindowSummary {
    let mut value = empty_window(500);
    value.buy_count = 6;
    value.sell_count = 1;
    value.unique_buy_actors = 5;
    value.unique_sell_actors = 1;
    value.buy_arrival_rate_per_second = 12.0;
    value.sell_arrival_rate_per_second = 2.0;
    value.count_imbalance = 5.0 / 7.0;
    value.buy_quote_quantity = 3.4;
    value.sell_quote_quantity = 0.6;
    value.net_quote_quantity = 2.8;
    value.quote_flow_imbalance = 0.7;
    value.quote_flow_velocity_per_second = 5.6;
    value.quote_flow_acceleration_per_second2 = 8.0;
    value.local_low_price_quote = Some(0.0110);
    value.local_low_sequence = Some(30);
    value.local_low_observed_at_unix_ms = Some(9_500);
    value.local_high_price_quote = Some(0.0117);
    value.local_high_sequence = Some(40);
    value.local_high_observed_at_unix_ms = Some(10_000);
    value.last_price_quote = Some(0.0117);
    value.drawdown_from_local_high = 0.0;
    value.recovery_from_local_low = 0.7 / 11.0;
    value
}

fn snapshot(structure: FastWindowSummary, reclaim: FastWindowSummary) -> FastMarketSnapshot {
    FastMarketSnapshot {
        market: market(),
        as_of_unix_ms: 10_000,
        last_sequence: Some(40),
        last_price_quote: Some(0.0117),
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: vec![reclaim, structure],
    }
}

fn policy() -> MicroPullbackPolicy {
    MicroPullbackPolicy {
        version: MICRO_PULLBACK_BASELINE_VERSION,
        reclaim_window_ms: 500,
        structure_window_ms: 2_000,
        min_impulse_move_fraction: 0.10,
        min_pullback_depth_fraction: 0.03,
        max_pullback_depth_fraction: 0.15,
        min_reclaim_fraction: 0.50,
        min_reclaim_buy_count: 4,
        min_reclaim_unique_buy_actors: 3,
        min_reclaim_buy_arrival_rate_per_second: 6.0,
        max_reclaim_sell_arrival_rate_per_second: 4.0,
        min_reclaim_count_imbalance: 0.40,
        min_reclaim_quote_flow_imbalance: 0.40,
        min_reclaim_quote_flow_velocity_per_second: 2.0,
        min_reclaim_quote_flow_acceleration_per_second2: 2.0,
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

fn profitable_trade() -> ExecutionTradeInput {
    ExecutionTradeInput {
        base_quantity: 100.0,
        executable_entry_price_quote: 0.0117,
        forecast_exit_price_quote: 0.0135,
        exit_capacity_base: 125.0,
        required_edge_bps: 100,
        risk_margin_bps: 50,
    }
}

fn execution(trade: ExecutionTradeInput) -> MicroPullbackExecutionInput {
    MicroPullbackExecutionInput {
        market: market(),
        as_of_unix_ms: 10_000,
        cost_model: cost_model(),
        trade,
    }
}

fn strong_snapshot() -> FastMarketSnapshot {
    snapshot(strong_structure(), strong_reclaim())
}

#[test]
fn ordered_impulse_pullback_reclaim_with_positive_economics_is_buy() {
    let snapshot = strong_snapshot();
    let execution = execution(profitable_trade());

    let assessment = assess_micro_pullback(&snapshot, Some(&execution), &policy()).unwrap();

    assert_eq!(assessment.version, MICRO_PULLBACK_BASELINE_VERSION);
    assert_eq!(assessment.policy_version, MICRO_PULLBACK_BASELINE_VERSION);
    assert_eq!(assessment.market, market());
    assert_eq!(assessment.as_of_unix_ms, 10_000);
    assert_eq!(assessment.action, FastLaneAction::Buy);
    assert_eq!(assessment.reasons, vec![MicroPullbackReason::AllConditionsMet]);
    assert!((assessment.impulse_move_fraction.unwrap() - 0.20).abs() < 1e-12);
    assert!((assessment.pullback_depth_fraction.unwrap() - (1.0 / 12.0)).abs() < 1e-12);
    assert!((assessment.reclaim_fraction.unwrap() - 0.70).abs() < 1e-12);
    assert_eq!(assessment.intended_base_quantity, Some(100.0));
    assert_eq!(assessment.executable_entry_price_quote, Some(0.0117));
    assert_eq!(assessment.forecast_exit_price_quote, Some(0.0135));
    assert_eq!(assessment.exit_capacity_base, Some(125.0));
    assert!(assessment.forecast_net_pnl_quote.is_some_and(|value| value > 0.0));
    assert!(assessment
        .maximum_acceptable_entry_price_quote
        .is_some_and(|maximum| maximum >= 0.0117));
}

#[test]
fn ordered_structure_is_required_and_trough_must_precede_reclaim() {
    let mut structure = strong_structure();
    structure.local_low_sequence = Some(25);
    let assessment = assess_micro_pullback(
        &snapshot(structure, strong_reclaim()),
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();
    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::MissingOrderedImpulseLow));

    let mut structure = strong_structure();
    structure.post_high_low_sequence = Some(40);
    let assessment = assess_micro_pullback(
        &snapshot(structure, strong_reclaim()),
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();
    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::ReclaimNotAfterTrough));
}

#[test]
fn weak_impulse_shallow_or_deep_pullback_and_incomplete_reclaim_skip() {
    let exec = execution(profitable_trade());

    let mut structure = strong_structure();
    structure.local_low_price_quote = Some(0.0112);
    let assessment = assess_micro_pullback(
        &snapshot(structure, strong_reclaim()),
        Some(&exec),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::ImpulseMoveBelowMinimum));

    let mut structure = strong_structure();
    structure.post_high_low_price_quote = Some(0.0118);
    let assessment = assess_micro_pullback(
        &snapshot(structure, strong_reclaim()),
        Some(&exec),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::PullbackTooShallow));

    let mut structure = strong_structure();
    structure.post_high_low_price_quote = Some(0.0095);
    let assessment = assess_micro_pullback(
        &snapshot(structure, strong_reclaim()),
        Some(&exec),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::PullbackTooDeep));

    let mut structure = strong_structure();
    structure.last_price_quote = Some(0.0113);
    let assessment = assess_micro_pullback(
        &snapshot(structure, strong_reclaim()),
        Some(&exec),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::ReclaimFractionBelowMinimum));
}

#[test]
fn seller_exhaustion_and_renewed_demand_are_required_in_reclaim_window() {
    let mut reclaim = strong_reclaim();
    reclaim.buy_count = 2;
    reclaim.unique_buy_actors = 1;
    reclaim.buy_arrival_rate_per_second = 4.0;
    reclaim.sell_arrival_rate_per_second = 8.0;
    reclaim.count_imbalance = -0.2;
    reclaim.quote_flow_imbalance = -0.1;
    reclaim.quote_flow_velocity_per_second = -1.0;
    reclaim.quote_flow_acceleration_per_second2 = -3.0;

    let assessment = assess_micro_pullback(
        &snapshot(strong_structure(), reclaim),
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reasons,
        vec![
            MicroPullbackReason::ReclaimBuyCountBelowMinimum,
            MicroPullbackReason::ReclaimUniqueBuyActorsBelowMinimum,
            MicroPullbackReason::ReclaimBuyArrivalBelowMinimum,
            MicroPullbackReason::ReclaimSellArrivalAboveMaximum,
            MicroPullbackReason::ReclaimCountImbalanceBelowMinimum,
            MicroPullbackReason::ReclaimQuoteFlowImbalanceBelowMinimum,
            MicroPullbackReason::ReclaimVelocityBelowMinimum,
            MicroPullbackReason::ReclaimAccelerationBelowMinimum,
        ]
    );
}

#[test]
fn missing_execution_evidence_skips_without_fabricated_costs() {
    let assessment = assess_micro_pullback(&strong_snapshot(), None, &policy()).unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reasons,
        vec![MicroPullbackReason::ExecutionEconomicsUnavailable]
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
fn insufficient_exit_capacity_is_tradeability_skip() {
    let mut trade = profitable_trade();
    trade.exit_capacity_base = 99.0;
    let assessment = assess_micro_pullback(
        &strong_snapshot(),
        Some(&execution(trade)),
        &policy(),
    )
    .unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::InsufficientExitCapacity));
    assert_eq!(assessment.forecast_net_pnl_quote, None);
    assert_eq!(assessment.maximum_acceptable_entry_price_quote, None);
}

#[test]
fn bad_post_cost_value_or_entry_boundary_skips() {
    let mut losing = profitable_trade();
    losing.executable_entry_price_quote = 0.0120;
    losing.forecast_exit_price_quote = 0.0110;
    let assessment = assess_micro_pullback(
        &strong_snapshot(),
        Some(&execution(losing)),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::ForecastNetPnlNotPositive));

    let mut chased = profitable_trade();
    chased.executable_entry_price_quote = 0.0129;
    chased.forecast_exit_price_quote = 0.0130;
    chased.required_edge_bps = 300;
    chased.risk_margin_bps = 200;
    let assessment = assess_micro_pullback(
        &strong_snapshot(),
        Some(&execution(chased)),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&MicroPullbackReason::EntryPriceAboveMaximum));
}

#[test]
fn execution_identity_mismatch_fails_closed() {
    let snapshot = strong_snapshot();
    let mut wrong_market = execution(profitable_trade());
    wrong_market.market = other_market();
    assert_eq!(
        assess_micro_pullback(&snapshot, Some(&wrong_market), &policy()).unwrap_err(),
        MicroPullbackError::ExecutionMarketMismatch
    );

    let mut wrong_time = execution(profitable_trade());
    wrong_time.as_of_unix_ms = 9_999;
    assert_eq!(
        assess_micro_pullback(&snapshot, Some(&wrong_time), &policy()).unwrap_err(),
        MicroPullbackError::ExecutionTimestampMismatch {
            snapshot: 10_000,
            execution: 9_999,
        }
    );
}

#[test]
fn invalid_policy_fails_closed() {
    let snapshot = strong_snapshot();
    let execution = execution(profitable_trade());

    let mut invalid = policy();
    invalid.reclaim_window_ms = invalid.structure_window_ms;
    assert!(matches!(
        assess_micro_pullback(&snapshot, Some(&execution), &invalid),
        Err(MicroPullbackError::InvalidPolicy(_))
    ));

    let mut invalid = policy();
    invalid.min_reclaim_fraction = f64::NAN;
    assert!(matches!(
        assess_micro_pullback(&snapshot, Some(&execution), &invalid),
        Err(MicroPullbackError::InvalidPolicy(_))
    ));
}

#[test]
fn repeated_identical_input_is_deterministic() {
    let snapshot = strong_snapshot();
    let execution = execution(profitable_trade());
    let policy = policy();

    let first = assess_micro_pullback(&snapshot, Some(&execution), &policy).unwrap();
    let second = assess_micro_pullback(&snapshot, Some(&execution), &policy).unwrap();

    assert_eq!(first, second);
}
