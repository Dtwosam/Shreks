use shreks_core::{
    assess_pre_graduation_acceleration, ExecutionCostModel, ExecutionLegCostInput,
    ExecutionTradeInput, FastLaneAction, FastMarketKey, FastMarketSnapshot, FastReserveContext,
    FastWindowSummary, LifecycleEventKind, PreGraduationError, PreGraduationExecutionInput,
    PreGraduationPolicy, PreGraduationReason, ProviderId, TokenLifecycleEvent, VenueId,
    EXECUTION_ECONOMICS_VERSION, PRE_GRADUATION_BASELINE_VERSION,
};

fn market() -> FastMarketKey {
    FastMarketKey::new(
        "mint-pre-grad",
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

fn strong_signal() -> FastWindowSummary {
    let mut value = empty_window(500);
    value.buy_count = 6;
    value.sell_count = 1;
    value.unique_buy_actors = 5;
    value.unique_sell_actors = 1;
    value.buy_arrival_rate_per_second = 12.0;
    value.sell_arrival_rate_per_second = 2.0;
    value.count_imbalance = 5.0 / 7.0;
    value.buy_base_quantity = 80.0;
    value.sell_base_quantity = 10.0;
    value.buy_quote_quantity = 3.4;
    value.sell_quote_quantity = 0.6;
    value.net_quote_quantity = 2.8;
    value.quote_flow_imbalance = 0.7;
    value.quote_flow_velocity_per_second = 5.6;
    value.quote_flow_acceleration_per_second2 = 8.0;
    value.last_price_quote = Some(0.0117);
    value
}

fn context_window() -> FastWindowSummary {
    let mut value = empty_window(2_000);
    value.buy_count = 12;
    value.sell_count = 5;
    value.unique_buy_actors = 9;
    value.unique_sell_actors = 4;
    value.buy_arrival_rate_per_second = 6.0;
    value.sell_arrival_rate_per_second = 2.5;
    value.count_imbalance = 7.0 / 17.0;
    value.buy_base_quantity = 140.0;
    value.sell_base_quantity = 45.0;
    value.buy_quote_quantity = 7.0;
    value.sell_quote_quantity = 3.0;
    value.net_quote_quantity = 4.0;
    value.quote_flow_imbalance = 0.4;
    value.quote_flow_velocity_per_second = 2.0;
    value.quote_flow_acceleration_per_second2 = 1.0;
    value.last_price_quote = Some(0.0117);
    value
}

fn curve_reserves(real_base_reserve_raw: u64) -> FastReserveContext {
    FastReserveContext::PumpCurve {
        virtual_base_reserve_raw: 900_000_000,
        virtual_quote_reserve_raw: 32_000_000_000,
        real_base_reserve_raw,
        real_quote_reserve_raw: 10_000_000_000,
        base_decimals: 6,
        quote_decimals: 9,
    }
}

fn snapshot_with_reserve(real_base_reserve_raw: u64) -> FastMarketSnapshot {
    FastMarketSnapshot {
        market: market(),
        as_of_unix_ms: 10_000,
        last_sequence: Some(40),
        last_price_quote: Some(0.0117),
        last_reserve_context: Some(curve_reserves(real_base_reserve_raw)),
        last_lifecycle_event: None,
        windows: vec![strong_signal(), context_window()],
    }
}

fn strong_snapshot() -> FastMarketSnapshot {
    snapshot_with_reserve(300_000_000)
}

fn policy() -> PreGraduationPolicy {
    PreGraduationPolicy {
        version: PRE_GRADUATION_BASELINE_VERSION,
        signal_window_ms: 500,
        context_window_ms: 2_000,
        graduation_target_real_base_reserve_raw: 100_000_000,
        maximum_pre_graduation_real_base_reserve_raw: 500_000_000,
        min_buy_count: 4,
        min_unique_buy_actors: 3,
        min_buy_arrival_rate_per_second: 6.0,
        min_count_imbalance: 0.40,
        min_quote_flow_imbalance: 0.40,
        min_quote_flow_velocity_per_second: 2.0,
        min_quote_flow_acceleration_per_second2: 2.0,
        min_velocity_expansion_ratio: 1.5,
        min_buy_participation_of_remaining: 0.25,
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

fn execution(trade: ExecutionTradeInput) -> PreGraduationExecutionInput {
    PreGraduationExecutionInput {
        market: market(),
        as_of_unix_ms: 10_000,
        cost_model: cost_model(),
        trade,
    }
}

#[test]
fn near_graduation_acceleration_with_positive_economics_is_buy() {
    let snapshot = strong_snapshot();
    let execution = execution(profitable_trade());

    let assessment =
        assess_pre_graduation_acceleration(&snapshot, Some(&execution), &policy()).unwrap();

    assert_eq!(assessment.version, PRE_GRADUATION_BASELINE_VERSION);
    assert_eq!(assessment.policy_version, PRE_GRADUATION_BASELINE_VERSION);
    assert_eq!(assessment.market, market());
    assert_eq!(assessment.action, FastLaneAction::Buy);
    assert_eq!(assessment.reasons, vec![PreGraduationReason::AllConditionsMet]);
    assert_eq!(assessment.current_real_base_reserve_raw, Some(300_000_000));
    assert_eq!(assessment.distance_to_graduation_raw, Some(200_000_000));
    assert!((assessment.buy_participation_of_remaining.unwrap() - 0.40).abs() < 1e-12);
    assert!((assessment.velocity_expansion_ratio.unwrap() - 2.8).abs() < 1e-12);
    assert!(assessment.forecast_net_pnl_quote.is_some_and(|value| value > 0.0));
    assert!(assessment
        .maximum_acceptable_entry_price_quote
        .is_some_and(|maximum| maximum >= 0.0117));
}

#[test]
fn wrong_venue_and_missing_curve_reserve_skip() {
    let mut wrong_venue = strong_snapshot();
    wrong_venue.market = FastMarketKey::new(
        "mint-pre-grad",
        "quote-sol",
        VenueId::PumpSwap,
    )
    .unwrap();
    wrong_venue.last_reserve_context = Some(FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: 300_000_000,
        pool_quote_reserve_raw: 10_000_000_000,
        virtual_quote_reserve_raw: None,
        base_decimals: 6,
        quote_decimals: 9,
    });
    let assessment = assess_pre_graduation_acceleration(
        &wrong_venue,
        None,
        &policy(),
    )
    .unwrap();
    assert!(assessment.reasons.contains(&PreGraduationReason::NotPumpBondingCurve));

    let mut missing = strong_snapshot();
    missing.last_reserve_context = None;
    let assessment = assess_pre_graduation_acceleration(
        &missing,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&PreGraduationReason::PumpCurveReserveUnavailable));
}

#[test]
fn configured_graduation_boundary_is_respected() {
    let reached = snapshot_with_reserve(100_000_000);
    let assessment = assess_pre_graduation_acceleration(
        &reached,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&PreGraduationReason::GraduationTargetReached));

    let far = snapshot_with_reserve(700_000_000);
    let assessment = assess_pre_graduation_acceleration(
        &far,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&PreGraduationReason::TooFarFromGraduation));
}

#[test]
fn weak_acceleration_and_participation_skip_in_canonical_order() {
    let mut snapshot = strong_snapshot();
    let signal = snapshot.windows.iter_mut().find(|window| window.window_ms == 500).unwrap();
    signal.buy_count = 2;
    signal.unique_buy_actors = 1;
    signal.buy_arrival_rate_per_second = 4.0;
    signal.count_imbalance = 0.10;
    signal.quote_flow_imbalance = 0.20;
    signal.quote_flow_velocity_per_second = 1.0;
    signal.quote_flow_acceleration_per_second2 = 0.5;
    signal.buy_base_quantity = 20.0;

    let assessment = assess_pre_graduation_acceleration(
        &snapshot,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reasons,
        vec![
            PreGraduationReason::BuyCountBelowMinimum,
            PreGraduationReason::UniqueBuyActorsBelowMinimum,
            PreGraduationReason::BuyArrivalBelowMinimum,
            PreGraduationReason::CountImbalanceBelowMinimum,
            PreGraduationReason::QuoteFlowImbalanceBelowMinimum,
            PreGraduationReason::QuoteFlowVelocityBelowMinimum,
            PreGraduationReason::QuoteFlowAccelerationBelowMinimum,
            PreGraduationReason::VelocityExpansionBelowMinimum,
            PreGraduationReason::BuyParticipationBelowMinimum,
        ]
    );
}

#[test]
fn already_observed_graduation_skips_pre_graduation_baseline() {
    let mut snapshot = strong_snapshot();
    snapshot.last_lifecycle_event = Some(TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::Helius,
        mint: market().mint,
        quote_mint: market().quote_mint,
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: "pool".to_owned(),
        signature: "graduation-signature".to_owned(),
        slot: 50,
        detected_at_unix_ms: 9_900,
        occurred_at_unix_ms: Some(9_850),
    });

    let assessment = assess_pre_graduation_acceleration(
        &snapshot,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();
    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert!(assessment
        .reasons
        .contains(&PreGraduationReason::AlreadyGraduated));
}

#[test]
fn missing_execution_skips_without_fabricated_economics() {
    let assessment = assess_pre_graduation_acceleration(&strong_snapshot(), None, &policy()).unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reasons,
        vec![PreGraduationReason::ExecutionEconomicsUnavailable]
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
fn capacity_value_and_entry_boundary_are_tradeability_gates() {
    let mut low_capacity = profitable_trade();
    low_capacity.exit_capacity_base = 99.0;
    let assessment = assess_pre_graduation_acceleration(
        &strong_snapshot(),
        Some(&execution(low_capacity)),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&PreGraduationReason::InsufficientExitCapacity));
    assert_eq!(assessment.forecast_net_pnl_quote, None);

    let mut losing = profitable_trade();
    losing.executable_entry_price_quote = 0.0120;
    losing.forecast_exit_price_quote = 0.0110;
    let assessment = assess_pre_graduation_acceleration(
        &strong_snapshot(),
        Some(&execution(losing)),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&PreGraduationReason::ForecastNetPnlNotPositive));

    let mut chased = profitable_trade();
    chased.executable_entry_price_quote = 0.0129;
    chased.forecast_exit_price_quote = 0.0130;
    chased.required_edge_bps = 300;
    chased.risk_margin_bps = 200;
    let assessment = assess_pre_graduation_acceleration(
        &strong_snapshot(),
        Some(&execution(chased)),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&PreGraduationReason::EntryPriceAboveMaximum));
}

#[test]
fn execution_identity_mismatch_fails_closed() {
    let snapshot = strong_snapshot();
    let mut wrong_market = execution(profitable_trade());
    wrong_market.market = other_market();
    assert_eq!(
        assess_pre_graduation_acceleration(&snapshot, Some(&wrong_market), &policy()).unwrap_err(),
        PreGraduationError::ExecutionMarketMismatch
    );

    let mut wrong_time = execution(profitable_trade());
    wrong_time.as_of_unix_ms = 9_999;
    assert_eq!(
        assess_pre_graduation_acceleration(&snapshot, Some(&wrong_time), &policy()).unwrap_err(),
        PreGraduationError::ExecutionTimestampMismatch {
            snapshot: 10_000,
            execution: 9_999,
        }
    );
}

#[test]
fn invalid_policy_fails_closed() {
    let mut invalid = policy();
    invalid.graduation_target_real_base_reserve_raw =
        invalid.maximum_pre_graduation_real_base_reserve_raw;
    assert!(matches!(
        assess_pre_graduation_acceleration(&strong_snapshot(), None, &invalid),
        Err(PreGraduationError::InvalidPolicy(_))
    ));

    let mut invalid = policy();
    invalid.min_velocity_expansion_ratio = f64::NAN;
    assert!(matches!(
        assess_pre_graduation_acceleration(&strong_snapshot(), None, &invalid),
        Err(PreGraduationError::InvalidPolicy(_))
    ));
}

#[test]
fn identical_inputs_produce_identical_assessments() {
    let snapshot = strong_snapshot();
    let execution = execution(profitable_trade());
    let policy = policy();

    let left = assess_pre_graduation_acceleration(&snapshot, Some(&execution), &policy).unwrap();
    let right = assess_pre_graduation_acceleration(&snapshot, Some(&execution), &policy).unwrap();
    assert_eq!(left, right);
}
