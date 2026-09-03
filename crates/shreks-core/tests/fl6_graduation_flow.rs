use shreks_core::{
    assess_graduation_flow, ExecutionCostModel, ExecutionLegCostInput, ExecutionTradeInput,
    FastLaneAction, FastMarketKey, FastMarketSnapshot, FastWindowSummary, GraduationBoostContext,
    GraduationFlowError, GraduationFlowExecutionInput, GraduationFlowPolicy, GraduationFlowReason,
    LifecycleEventKind, ProviderId, TokenLifecycleEvent, VenueId, EXECUTION_ECONOMICS_VERSION,
    GRADUATION_FLOW_BASELINE_VERSION,
};

fn pre_market() -> FastMarketKey {
    FastMarketKey::new(
        "mint-graduation-flow",
        "quote-sol",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap()
}

fn post_market() -> FastMarketKey {
    FastMarketKey::new(
        "mint-graduation-flow",
        "quote-sol",
        VenueId::PumpSwap,
    )
    .unwrap()
}

fn other_post_market() -> FastMarketKey {
    FastMarketKey::new("other-mint", "quote-sol", VenueId::PumpSwap).unwrap()
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

fn strong_pre_flow() -> FastWindowSummary {
    let mut value = empty_window(2_000);
    value.buy_count = 8;
    value.sell_count = 2;
    value.unique_buy_actors = 6;
    value.unique_sell_actors = 2;
    value.buy_arrival_rate_per_second = 4.0;
    value.sell_arrival_rate_per_second = 1.0;
    value.count_imbalance = 0.6;
    value.buy_quote_quantity = 10.0;
    value.sell_quote_quantity = 2.0;
    value.net_quote_quantity = 8.0;
    value.quote_flow_imbalance = 2.0 / 3.0;
    value.quote_flow_velocity_per_second = 4.0;
    value.quote_flow_acceleration_per_second2 = 1.5;
    value.last_price_quote = Some(0.0110);
    value
}

fn strong_post_flow() -> FastWindowSummary {
    let mut value = empty_window(2_000);
    value.buy_count = 6;
    value.sell_count = 1;
    value.unique_buy_actors = 5;
    value.unique_sell_actors = 1;
    value.buy_arrival_rate_per_second = 3.0;
    value.sell_arrival_rate_per_second = 0.5;
    value.count_imbalance = 5.0 / 7.0;
    value.buy_quote_quantity = 11.0;
    value.sell_quote_quantity = 1.0;
    value.net_quote_quantity = 10.0;
    value.quote_flow_imbalance = 5.0 / 6.0;
    value.quote_flow_velocity_per_second = 5.0;
    value.quote_flow_acceleration_per_second2 = 2.5;
    value.last_price_quote = Some(0.0117);
    value
}

fn graduation_event() -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::Helius,
        mint: pre_market().mint,
        quote_mint: pre_market().quote_mint,
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: "pump-swap-pool".to_owned(),
        signature: "graduation-signature".to_owned(),
        slot: 50,
        detected_at_unix_ms: 9_500,
        occurred_at_unix_ms: Some(9_450),
    }
}

fn pre_snapshot() -> FastMarketSnapshot {
    FastMarketSnapshot {
        market: pre_market(),
        as_of_unix_ms: 10_000,
        last_sequence: Some(40),
        last_price_quote: Some(0.0110),
        last_reserve_context: None,
        last_lifecycle_event: Some(graduation_event()),
        windows: vec![strong_pre_flow()],
    }
}

fn post_snapshot() -> FastMarketSnapshot {
    FastMarketSnapshot {
        market: post_market(),
        as_of_unix_ms: 10_000,
        last_sequence: Some(5),
        last_price_quote: Some(0.0117),
        last_reserve_context: None,
        last_lifecycle_event: Some(graduation_event()),
        windows: vec![strong_post_flow()],
    }
}

fn policy() -> GraduationFlowPolicy {
    GraduationFlowPolicy {
        version: GRADUATION_FLOW_BASELINE_VERSION,
        flow_window_ms: 2_000,
        max_graduation_age_ms: 1_500,
        min_pre_buy_count: 4,
        min_pre_quote_flow_velocity_per_second: 2.0,
        min_post_buy_count: 4,
        min_post_unique_buy_actors: 3,
        min_post_buy_arrival_rate_per_second: 2.5,
        max_post_sell_arrival_rate_per_second: 1.0,
        min_post_count_imbalance: 0.40,
        min_post_quote_flow_imbalance: 0.40,
        min_post_quote_flow_velocity_per_second: 3.0,
        min_post_quote_flow_acceleration_per_second2: 1.0,
        min_post_to_pre_velocity_ratio: 0.80,
    }
}

fn boost(can_boost: bool) -> GraduationBoostContext {
    GraduationBoostContext {
        market: post_market(),
        as_of_unix_ms: 10_000,
        can_boost,
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

fn execution(trade: ExecutionTradeInput) -> GraduationFlowExecutionInput {
    GraduationFlowExecutionInput {
        market: post_market(),
        as_of_unix_ms: 10_000,
        cost_model: cost_model(),
        trade,
    }
}

#[test]
fn verified_recent_migration_with_strong_post_flow_and_economics_is_buy() {
    let pre = pre_snapshot();
    let post = post_snapshot();
    let boost = boost(true);
    let execution = execution(profitable_trade());

    let assessment = assess_graduation_flow(
        &pre,
        &post,
        Some(&boost),
        Some(&execution),
        &policy(),
    )
    .unwrap();

    assert_eq!(assessment.version, GRADUATION_FLOW_BASELINE_VERSION);
    assert_eq!(assessment.policy_version, GRADUATION_FLOW_BASELINE_VERSION);
    assert_eq!(assessment.market, post_market());
    assert_eq!(assessment.action, FastLaneAction::Buy);
    assert_eq!(assessment.reasons, vec![GraduationFlowReason::AllConditionsMet]);
    assert_eq!(assessment.graduation_age_ms, Some(500));
    assert_eq!(assessment.can_boost, Some(true));
    assert_eq!(assessment.pre_quote_flow_velocity_per_second, Some(4.0));
    assert_eq!(assessment.post_quote_flow_velocity_per_second, Some(5.0));
    assert_eq!(assessment.post_to_pre_velocity_ratio, Some(1.25));
    assert!(assessment.forecast_net_pnl_quote.is_some_and(|value| value > 0.0));
}

#[test]
fn missing_or_stale_lifecycle_evidence_skips() {
    let mut pre = pre_snapshot();
    let mut post = post_snapshot();
    pre.last_lifecycle_event = None;
    post.last_lifecycle_event = None;

    let assessment = assess_graduation_flow(
        &pre,
        &post,
        None,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();
    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert!(assessment
        .reasons
        .contains(&GraduationFlowReason::GraduationLifecycleUnavailable));

    let mut event = graduation_event();
    event.detected_at_unix_ms = 8_000;
    let mut pre = pre_snapshot();
    let mut post = post_snapshot();
    pre.last_lifecycle_event = Some(event.clone());
    post.last_lifecycle_event = Some(event);
    let assessment = assess_graduation_flow(
        &pre,
        &post,
        None,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&GraduationFlowReason::GraduationTooOld));
}

#[test]
fn cross_venue_identity_and_timestamp_contradictions_fail_closed() {
    let mut bad_pre = pre_snapshot();
    bad_pre.market.venue = VenueId::PumpSwap;
    assert_eq!(
        assess_graduation_flow(&bad_pre, &post_snapshot(), None, None, &policy()).unwrap_err(),
        GraduationFlowError::InvalidVenueTransition
    );

    let mut bad_post = post_snapshot();
    bad_post.market = other_post_market();
    assert_eq!(
        assess_graduation_flow(&pre_snapshot(), &bad_post, None, None, &policy()).unwrap_err(),
        GraduationFlowError::MarketIdentityMismatch
    );

    let mut bad_post = post_snapshot();
    bad_post.as_of_unix_ms = 10_001;
    assert_eq!(
        assess_graduation_flow(&pre_snapshot(), &bad_post, None, None, &policy()).unwrap_err(),
        GraduationFlowError::SnapshotTimestampMismatch {
            pre: 10_000,
            post: 10_001,
        }
    );
}

#[test]
fn conflicting_lifecycle_truth_fails_closed() {
    let pre = pre_snapshot();
    let mut post = post_snapshot();
    post.last_lifecycle_event.as_mut().unwrap().signature = "other-graduation".to_owned();

    assert_eq!(
        assess_graduation_flow(&pre, &post, None, None, &policy()).unwrap_err(),
        GraduationFlowError::LifecycleMismatch
    );
}

#[test]
fn weak_pre_flow_skips() {
    let mut pre = pre_snapshot();
    let window = pre.windows.first_mut().unwrap();
    window.buy_count = 1;
    window.quote_flow_velocity_per_second = 0.5;

    let assessment = assess_graduation_flow(
        &pre,
        &post_snapshot(),
        None,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();

    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert!(assessment
        .reasons
        .contains(&GraduationFlowReason::PreBuyCountBelowMinimum));
    assert!(assessment
        .reasons
        .contains(&GraduationFlowReason::PreVelocityBelowMinimum));
}

#[test]
fn weak_post_flow_skips_in_canonical_reason_order() {
    let mut post = post_snapshot();
    let window = post.windows.first_mut().unwrap();
    window.buy_count = 2;
    window.unique_buy_actors = 1;
    window.buy_arrival_rate_per_second = 1.0;
    window.sell_arrival_rate_per_second = 2.0;
    window.count_imbalance = 0.0;
    window.quote_flow_imbalance = 0.10;
    window.quote_flow_velocity_per_second = 1.0;
    window.quote_flow_acceleration_per_second2 = 0.0;

    let assessment = assess_graduation_flow(
        &pre_snapshot(),
        &post,
        None,
        Some(&execution(profitable_trade())),
        &policy(),
    )
    .unwrap();

    assert_eq!(
        assessment.reasons,
        vec![
            GraduationFlowReason::PostBuyCountBelowMinimum,
            GraduationFlowReason::PostUniqueBuyActorsBelowMinimum,
            GraduationFlowReason::PostBuyArrivalBelowMinimum,
            GraduationFlowReason::PostSellArrivalAboveMaximum,
            GraduationFlowReason::PostCountImbalanceBelowMinimum,
            GraduationFlowReason::PostQuoteFlowImbalanceBelowMinimum,
            GraduationFlowReason::PostVelocityBelowMinimum,
            GraduationFlowReason::PostAccelerationBelowMinimum,
            GraduationFlowReason::PostVelocityRetentionBelowMinimum,
        ]
    );
}

#[test]
fn low_post_to_pre_velocity_retention_skips() {
    let mut post = post_snapshot();
    post.windows.first_mut().unwrap().quote_flow_velocity_per_second = 2.0;
    let mut relaxed = policy();
    relaxed.min_post_quote_flow_velocity_per_second = 1.0;

    let assessment = assess_graduation_flow(
        &pre_snapshot(),
        &post,
        None,
        Some(&execution(profitable_trade())),
        &relaxed,
    )
    .unwrap();

    assert!(assessment
        .reasons
        .contains(&GraduationFlowReason::PostVelocityRetentionBelowMinimum));
}

#[test]
fn optional_boost_capability_is_context_not_a_standalone_gate() {
    let execution = execution(profitable_trade());
    let true_assessment = assess_graduation_flow(
        &pre_snapshot(),
        &post_snapshot(),
        Some(&boost(true)),
        Some(&execution),
        &policy(),
    )
    .unwrap();
    let false_assessment = assess_graduation_flow(
        &pre_snapshot(),
        &post_snapshot(),
        Some(&boost(false)),
        Some(&execution),
        &policy(),
    )
    .unwrap();

    assert_eq!(true_assessment.action, FastLaneAction::Buy);
    assert_eq!(false_assessment.action, FastLaneAction::Buy);
    assert_eq!(true_assessment.can_boost, Some(true));
    assert_eq!(false_assessment.can_boost, Some(false));
}

#[test]
fn boost_context_identity_mismatch_fails_closed() {
    let mut wrong = boost(true);
    wrong.market = other_post_market();
    assert_eq!(
        assess_graduation_flow(
            &pre_snapshot(),
            &post_snapshot(),
            Some(&wrong),
            None,
            &policy(),
        )
        .unwrap_err(),
        GraduationFlowError::BoostMarketMismatch
    );

    let mut wrong = boost(true);
    wrong.as_of_unix_ms = 9_999;
    assert_eq!(
        assess_graduation_flow(
            &pre_snapshot(),
            &post_snapshot(),
            Some(&wrong),
            None,
            &policy(),
        )
        .unwrap_err(),
        GraduationFlowError::BoostTimestampMismatch {
            snapshot: 10_000,
            boost: 9_999,
        }
    );
}

#[test]
fn missing_execution_skips_without_fabricated_economics() {
    let assessment = assess_graduation_flow(
        &pre_snapshot(),
        &post_snapshot(),
        Some(&boost(true)),
        None,
        &policy(),
    )
    .unwrap();

    assert_eq!(
        assessment.reasons,
        vec![GraduationFlowReason::ExecutionEconomicsUnavailable]
    );
    assert_eq!(assessment.intended_base_quantity, None);
    assert_eq!(assessment.executable_entry_price_quote, None);
    assert_eq!(assessment.forecast_exit_price_quote, None);
    assert_eq!(assessment.exit_capacity_base, None);
    assert_eq!(assessment.forecast_net_pnl_quote, None);
    assert_eq!(assessment.maximum_acceptable_entry_price_quote, None);
}

#[test]
fn capacity_value_and_entry_boundary_are_tradeability_gates() {
    let mut low_capacity = profitable_trade();
    low_capacity.exit_capacity_base = 99.0;
    let assessment = assess_graduation_flow(
        &pre_snapshot(),
        &post_snapshot(),
        None,
        Some(&execution(low_capacity)),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&GraduationFlowReason::InsufficientExitCapacity));
    assert_eq!(assessment.forecast_net_pnl_quote, None);

    let mut losing = profitable_trade();
    losing.executable_entry_price_quote = 0.0120;
    losing.forecast_exit_price_quote = 0.0110;
    let assessment = assess_graduation_flow(
        &pre_snapshot(),
        &post_snapshot(),
        None,
        Some(&execution(losing)),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&GraduationFlowReason::ForecastNetPnlNotPositive));

    let mut chased = profitable_trade();
    chased.executable_entry_price_quote = 0.0129;
    chased.forecast_exit_price_quote = 0.0130;
    chased.required_edge_bps = 300;
    chased.risk_margin_bps = 200;
    let assessment = assess_graduation_flow(
        &pre_snapshot(),
        &post_snapshot(),
        None,
        Some(&execution(chased)),
        &policy(),
    )
    .unwrap();
    assert!(assessment
        .reasons
        .contains(&GraduationFlowReason::EntryPriceAboveMaximum));
}

#[test]
fn execution_identity_mismatch_fails_closed() {
    let mut wrong_market = execution(profitable_trade());
    wrong_market.market = other_post_market();
    assert_eq!(
        assess_graduation_flow(
            &pre_snapshot(),
            &post_snapshot(),
            None,
            Some(&wrong_market),
            &policy(),
        )
        .unwrap_err(),
        GraduationFlowError::ExecutionMarketMismatch
    );

    let mut wrong_time = execution(profitable_trade());
    wrong_time.as_of_unix_ms = 9_999;
    assert_eq!(
        assess_graduation_flow(
            &pre_snapshot(),
            &post_snapshot(),
            None,
            Some(&wrong_time),
            &policy(),
        )
        .unwrap_err(),
        GraduationFlowError::ExecutionTimestampMismatch {
            snapshot: 10_000,
            execution: 9_999,
        }
    );
}

#[test]
fn invalid_policy_fails_closed() {
    let mut invalid = policy();
    invalid.flow_window_ms = 0;
    assert!(matches!(
        assess_graduation_flow(&pre_snapshot(), &post_snapshot(), None, None, &invalid),
        Err(GraduationFlowError::InvalidPolicy(_))
    ));

    let mut invalid = policy();
    invalid.min_post_to_pre_velocity_ratio = f64::NAN;
    assert!(matches!(
        assess_graduation_flow(&pre_snapshot(), &post_snapshot(), None, None, &invalid),
        Err(GraduationFlowError::InvalidPolicy(_))
    ));
}

#[test]
fn identical_inputs_produce_identical_assessments() {
    let pre = pre_snapshot();
    let post = post_snapshot();
    let boost = boost(true);
    let execution = execution(profitable_trade());
    let policy = policy();

    let left = assess_graduation_flow(&pre, &post, Some(&boost), Some(&execution), &policy).unwrap();
    let right = assess_graduation_flow(&pre, &post, Some(&boost), Some(&execution), &policy).unwrap();
    assert_eq!(left, right);
}
