use shreks_core::{
    assess_longer_runner, ExecutionLegCostInput, FastLaneAction, FastMarketKey, FastMarketSnapshot,
    LongerRunnerContinuationEvidence, LongerRunnerError, LongerRunnerPolicy,
    LongerRunnerProtectiveState, LongerRunnerReason, VenueId, LONGER_RUNNER_BASELINE_VERSION,
    LONGER_RUNNER_EVIDENCE_VERSION,
};

fn market() -> FastMarketKey {
    FastMarketKey::new("MINT", "SOL", VenueId::PumpSwap).expect("valid test market")
}

fn snapshot() -> FastMarketSnapshot {
    FastMarketSnapshot {
        market: market(),
        as_of_unix_ms: 500_000,
        last_sequence: None,
        last_price_quote: Some(1.0),
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: vec![],
    }
}

fn zero_costs() -> ExecutionLegCostInput {
    ExecutionLegCostInput {
        effective_fee_bps: 0,
        expected_impact_bps: 0,
        expected_slippage_bps: 0,
        expected_latency_bps: 0,
        network_fee_quote: 0.0,
        priority_fee_quote: 0.0,
        expected_failure_cost_quote: 0.0,
    }
}

fn protective() -> LongerRunnerProtectiveState {
    LongerRunnerProtectiveState {
        market: market(),
        as_of_unix_ms: 500_000,
        hard_stop_triggered: false,
        risk_limit_exit_required: false,
        liquidity_exit_required: false,
    }
}

fn policy() -> LongerRunnerPolicy {
    LongerRunnerPolicy {
        version: LONGER_RUNNER_BASELINE_VERSION,
        downside_risk_weight: 0.5,
        min_risk_adjusted_continuation_bps_for_hold: 100.0,
        max_risk_adjusted_continuation_bps_for_sell: 0.0,
    }
}

fn continuation(
    future_price: f64,
    downside_price: f64,
) -> LongerRunnerContinuationEvidence {
    LongerRunnerContinuationEvidence {
        version: LONGER_RUNNER_EVIDENCE_VERSION,
        market: market(),
        as_of_unix_ms: 500_000,
        forecast_source_version: "deterministic-continuation-test-v1".to_owned(),
        forecast_horizon_ms: 60_000,
        base_quantity: 10.0,
        current_executable_exit_price_quote: 1.0,
        expected_future_exit_price_quote: future_price,
        downside_exit_price_quote: downside_price,
        current_exit_capacity_base: 20.0,
        expected_future_exit_capacity_base: 20.0,
        expected_holding_cost_quote: 0.0,
        current_exit_costs: zero_costs(),
        future_exit_costs: zero_costs(),
    }
}

#[test]
fn favorable_cost_risk_adjusted_continuation_holds() {
    let evidence = continuation(1.05, 0.95);
    let result = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &policy())
        .expect("favorable continuation is valid");

    assert_eq!(result.action, FastLaneAction::Hold);
    assert!(result.risk_adjusted_continuation_bps.unwrap() >= 100.0);
    assert_eq!(
        result.reasons,
        vec![
            LongerRunnerReason::ContinuationAtOrAboveHoldThreshold,
            LongerRunnerReason::HoldConditionsMet,
        ]
    );
}

#[test]
fn marginal_continuation_reduces() {
    let evidence = continuation(1.01, 0.99);
    let result = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &policy())
        .expect("marginal continuation is valid");

    assert_eq!(result.action, FastLaneAction::Reduce);
    assert!(result.risk_adjusted_continuation_bps.unwrap() > 0.0);
    assert!(result.risk_adjusted_continuation_bps.unwrap() < 100.0);
    assert!(result.reasons.contains(&LongerRunnerReason::ContinuationBetweenThresholds));
}

#[test]
fn unfavorable_continuation_sells() {
    let evidence = continuation(0.99, 0.95);
    let result = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &policy())
        .expect("unfavorable continuation is valid");

    assert_eq!(result.action, FastLaneAction::Sell);
    assert!(result.risk_adjusted_continuation_bps.unwrap() <= 0.0);
    assert!(result.reasons.contains(&LongerRunnerReason::ContinuationAtOrBelowSellThreshold));
}

#[test]
fn hard_stop_overrides_highly_favorable_continuation() {
    let evidence = continuation(2.0, 1.5);
    let mut guard = protective();
    guard.hard_stop_triggered = true;

    let result = assess_longer_runner(&snapshot(), &guard, Some(&evidence), &policy())
        .expect("hard stop is valid protective evidence");

    assert_eq!(result.action, FastLaneAction::Sell);
    assert_eq!(result.risk_adjusted_continuation_bps, None);
    assert!(result.reasons.contains(&LongerRunnerReason::HardStopTriggered));
}

#[test]
fn risk_limit_overrides_favorable_continuation() {
    let evidence = continuation(2.0, 1.5);
    let mut guard = protective();
    guard.risk_limit_exit_required = true;

    let result = assess_longer_runner(&snapshot(), &guard, Some(&evidence), &policy())
        .expect("risk limit is valid protective evidence");

    assert_eq!(result.action, FastLaneAction::Sell);
    assert!(result.reasons.contains(&LongerRunnerReason::RiskLimitExitRequired));
}

#[test]
fn liquidity_exit_overrides_favorable_continuation() {
    let evidence = continuation(2.0, 1.5);
    let mut guard = protective();
    guard.liquidity_exit_required = true;

    let result = assess_longer_runner(&snapshot(), &guard, Some(&evidence), &policy())
        .expect("liquidity exit is valid protective evidence");

    assert_eq!(result.action, FastLaneAction::Sell);
    assert!(result.reasons.contains(&LongerRunnerReason::LiquidityExitRequired));
}

#[test]
fn missing_continuation_evidence_reduces_and_never_holds() {
    let result = assess_longer_runner(&snapshot(), &protective(), None, &policy())
        .expect("missing forecast is valid uncertainty");

    assert_eq!(result.action, FastLaneAction::Reduce);
    assert_ne!(result.action, FastLaneAction::Hold);
    assert_eq!(
        result.reasons,
        vec![
            LongerRunnerReason::ContinuationEvidenceUnavailable,
            LongerRunnerReason::ReduceConditionsMet,
        ]
    );
}

#[test]
fn protective_trigger_with_missing_continuation_still_sells() {
    let mut guard = protective();
    guard.hard_stop_triggered = true;

    let result = assess_longer_runner(&snapshot(), &guard, None, &policy())
        .expect("protective exit does not require a forecast");

    assert_eq!(result.action, FastLaneAction::Sell);
    assert!(result.reasons.contains(&LongerRunnerReason::HardStopTriggered));
    assert!(!result.reasons.contains(&LongerRunnerReason::ContinuationEvidenceUnavailable));
}

#[test]
fn insufficient_current_exit_capacity_sells() {
    let mut evidence = continuation(1.20, 1.10);
    evidence.current_exit_capacity_base = 5.0;

    let result = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &policy())
        .expect("capacity shortfall is adverse evidence, not malformed input");

    assert_eq!(result.action, FastLaneAction::Sell);
    assert!(result.reasons.contains(&LongerRunnerReason::CurrentExitCapacityInsufficient));
}

#[test]
fn insufficient_future_exit_capacity_sells() {
    let mut evidence = continuation(1.20, 1.10);
    evidence.expected_future_exit_capacity_base = 5.0;

    let result = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &policy())
        .expect("future capacity shortfall is adverse evidence");

    assert_eq!(result.action, FastLaneAction::Sell);
    assert!(result.reasons.contains(&LongerRunnerReason::FutureExitCapacityInsufficient));
}

#[test]
fn future_exit_costs_can_turn_positive_price_move_into_reduce() {
    let mut evidence = continuation(1.02, 1.0);
    evidence.future_exit_costs.expected_impact_bps = 150;
    let mut no_risk = policy();
    no_risk.downside_risk_weight = 0.0;

    let result = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &no_risk)
        .expect("valid cost-adjusted continuation");

    assert_eq!(result.action, FastLaneAction::Reduce);
    assert!(result.gross_expected_continuation_quote.unwrap() > 0.0);
    assert!(result.risk_adjusted_continuation_bps.unwrap() < 100.0);
}

#[test]
fn holding_cost_can_turn_positive_price_move_into_sell() {
    let mut evidence = continuation(1.01, 1.0);
    evidence.expected_holding_cost_quote = 0.2;
    let mut no_risk = policy();
    no_risk.downside_risk_weight = 0.0;

    let result = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &no_risk)
        .expect("valid holding-cost adjustment");

    assert_eq!(result.action, FastLaneAction::Sell);
    assert!(result.risk_adjusted_continuation_bps.unwrap() < 0.0);
}

#[test]
fn downside_risk_penalty_can_turn_gross_positive_continuation_into_sell() {
    let evidence = continuation(1.06, 0.80);

    let result = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &policy())
        .expect("valid risk-adjusted continuation");

    assert!(result.gross_expected_continuation_quote.unwrap() > 0.0);
    assert!(result.risk_penalty_quote.unwrap() > 0.0);
    assert!(result.risk_adjusted_continuation_quote.unwrap() < 0.0);
    assert_eq!(result.action, FastLaneAction::Sell);
}

#[test]
fn protective_market_and_timestamp_mismatches_fail_closed() {
    let mut wrong_market = protective();
    wrong_market.market = FastMarketKey::new("OTHER", "SOL", VenueId::PumpSwap).unwrap();
    assert_eq!(
        assess_longer_runner(&snapshot(), &wrong_market, None, &policy()).unwrap_err(),
        LongerRunnerError::ProtectiveMarketMismatch
    );

    let mut wrong_time = protective();
    wrong_time.as_of_unix_ms = 499_999;
    assert_eq!(
        assess_longer_runner(&snapshot(), &wrong_time, None, &policy()).unwrap_err(),
        LongerRunnerError::ProtectiveTimestampMismatch {
            snapshot: 500_000,
            protective: 499_999,
        }
    );
}

#[test]
fn continuation_market_and_timestamp_mismatches_fail_closed() {
    let mut wrong_market = continuation(1.05, 0.95);
    wrong_market.market = FastMarketKey::new("OTHER", "SOL", VenueId::PumpSwap).unwrap();
    assert_eq!(
        assess_longer_runner(&snapshot(), &protective(), Some(&wrong_market), &policy())
            .unwrap_err(),
        LongerRunnerError::ContinuationMarketMismatch
    );

    let mut wrong_time = continuation(1.05, 0.95);
    wrong_time.as_of_unix_ms = 499_999;
    assert_eq!(
        assess_longer_runner(&snapshot(), &protective(), Some(&wrong_time), &policy())
            .unwrap_err(),
        LongerRunnerError::ContinuationTimestampMismatch {
            snapshot: 500_000,
            continuation: 499_999,
        }
    );
}

#[test]
fn invalid_nan_policy_and_cost_state_fail_closed() {
    let evidence = continuation(1.05, 0.95);
    let mut invalid_policy = policy();
    invalid_policy.downside_risk_weight = f64::NAN;
    assert!(matches!(
        assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &invalid_policy)
            .unwrap_err(),
        LongerRunnerError::InvalidPolicy(_)
    ));

    let mut invalid_cost = continuation(1.05, 0.95);
    invalid_cost.future_exit_costs.effective_fee_bps = 10_001;
    assert!(matches!(
        assess_longer_runner(&snapshot(), &protective(), Some(&invalid_cost), &policy())
            .unwrap_err(),
        LongerRunnerError::InvalidExitCosts(_)
    ));
}

#[test]
fn representative_actions_never_emit_buy_or_skip() {
    let hold = assess_longer_runner(
        &snapshot(),
        &protective(),
        Some(&continuation(1.05, 0.95)),
        &policy(),
    )
    .unwrap();
    let reduce = assess_longer_runner(
        &snapshot(),
        &protective(),
        Some(&continuation(1.01, 0.99)),
        &policy(),
    )
    .unwrap();
    let sell = assess_longer_runner(
        &snapshot(),
        &protective(),
        Some(&continuation(0.99, 0.95)),
        &policy(),
    )
    .unwrap();

    for action in [hold.action, reduce.action, sell.action] {
        assert!(!matches!(action, FastLaneAction::Buy | FastLaneAction::Skip));
    }
}

#[test]
fn identical_inputs_produce_identical_output_and_reason_order() {
    let evidence = continuation(1.05, 0.95);
    let first = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &policy())
        .expect("first deterministic result");
    let second = assess_longer_runner(&snapshot(), &protective(), Some(&evidence), &policy())
        .expect("second deterministic result");

    assert_eq!(first, second);
    assert_eq!(
        first.reasons,
        vec![
            LongerRunnerReason::ContinuationAtOrAboveHoldThreshold,
            LongerRunnerReason::HoldConditionsMet,
        ]
    );
}
