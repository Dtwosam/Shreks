use shreks_core::{
    assess_continuous_action, FastActionConstraints, FastActionForecastSet,
    FastActionPositionState, FastContinuousActionError, FastContinuousActionPolicy,
    FastContinuousActionReason, FastForecastPrediction, FastForecastTarget, FastLaneAction,
    FastReduceExecutionCost, CONTINUOUS_ACTION_POLICY_VERSION,
};

fn prediction(
    target: FastForecastTarget,
    horizon_ms: u64,
    value: f64,
    model_version: &str,
) -> FastForecastPrediction {
    FastForecastPrediction {
        model_version: model_version.to_string(),
        target,
        horizon_ms,
        predicted_value: value,
    }
}

fn add_complete_horizon(
    predictions: &mut Vec<FastForecastPrediction>,
    horizon_ms: u64,
    entry_cost_adjusted_return_bps: f64,
    endpoint_return_bps: f64,
    mae_bps: f64,
    reversal_probability: f64,
    route_unavailability_probability: f64,
) {
    predictions.extend([
        prediction(
            FastForecastTarget::EndpointCostAdjustedReturnBps,
            horizon_ms,
            entry_cost_adjusted_return_bps,
            &format!("entry-{horizon_ms}"),
        ),
        prediction(
            FastForecastTarget::EndpointReturnBps,
            horizon_ms,
            endpoint_return_bps,
            &format!("endpoint-{horizon_ms}"),
        ),
        prediction(
            FastForecastTarget::MaeBps,
            horizon_ms,
            mae_bps,
            &format!("mae-{horizon_ms}"),
        ),
        prediction(
            FastForecastTarget::ReversalOccurred,
            horizon_ms,
            reversal_probability,
            &format!("reversal-{horizon_ms}"),
        ),
        prediction(
            FastForecastTarget::RouteUnavailabilityObserved,
            horizon_ms,
            route_unavailability_probability,
            &format!("route-{horizon_ms}"),
        ),
    ]);
}

fn forecast_set(rows: &[(u64, f64, f64, f64, f64, f64)]) -> FastActionForecastSet {
    let mut predictions = Vec::new();
    for &(horizon, entry_return, endpoint_return, mae, reversal, route) in rows {
        add_complete_horizon(
            &mut predictions,
            horizon,
            entry_return,
            endpoint_return,
            mae,
            reversal,
            route,
        );
    }
    FastActionForecastSet {
        champion_version: "champion-v1".to_string(),
        champion_fingerprint_sha256:
            "1111111111111111111111111111111111111111111111111111111111111111"
                .to_string(),
        predictions,
    }
}

fn policy() -> FastContinuousActionPolicy {
    FastContinuousActionPolicy {
        version: CONTINUOUS_ACTION_POLICY_VERSION,
        horizons_ms: vec![1_000, 3_000],
        entry_exposure_candidates: vec![0.25, 0.5, 1.0],
        reduce_target_exposure_candidates: vec![0.25, 0.5],
        adverse_excursion_weight: 0.5,
        reversal_penalty_bps: 100.0,
        route_unavailability_penalty_bps: 100.0,
        horizon_disagreement_weight: 0.2,
        minimum_buy_value_bps: 5.0,
        minimum_hold_value_bps: 0.0,
        missing_forecast_open_action: FastLaneAction::Reduce,
    }
}

fn constraints() -> FastActionConstraints {
    FastActionConstraints {
        max_exposure_fraction: 1.0,
        buy_economically_allowed: true,
        expected_future_exit_cost_bps: 20.0,
        reduce_execution_costs: vec![
            FastReduceExecutionCost {
                target_exposure_fraction: 0.25,
                execution_cost_bps: 15.0,
            },
            FastReduceExecutionCost {
                target_exposure_fraction: 0.5,
                execution_cost_bps: 10.0,
            },
        ],
        sell_executable: true,
        sell_now_cost_bps: 8.0,
        force_sell: false,
    }
}

fn incomplete_forecast_set() -> FastActionForecastSet {
    FastActionForecastSet {
        champion_version: "champion-v1".to_string(),
        champion_fingerprint_sha256:
            "1111111111111111111111111111111111111111111111111111111111111111"
                .to_string(),
        predictions: vec![prediction(
            FastForecastTarget::EndpointReturnBps,
            1_000,
            100.0,
            "partial",
        )],
    }
}

#[test]
fn flat_strong_reward_low_risk_buys_best_high_exposure() {
    let forecasts = forecast_set(&[
        (1_000, 200.0, 220.0, -20.0, 0.05, 0.02),
        (3_000, 250.0, 260.0, -30.0, 0.05, 0.02),
    ]);
    let assessment = assess_continuous_action(
        &policy(),
        &forecasts,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("strong flat opportunity must assess");

    assert_eq!(assessment.action, FastLaneAction::Buy);
    assert_eq!(assessment.reason, FastContinuousActionReason::BuySelected);
    assert_eq!(assessment.selected_horizon_ms, Some(3_000));
    assert_eq!(assessment.current_exposure_fraction, 0.0);
    assert_eq!(assessment.target_exposure_fraction, 1.0);
    assert_eq!(assessment.champion_version, "champion-v1");
    assert_eq!(assessment.policy_version, CONTINUOUS_ACTION_POLICY_VERSION);
    assert!(assessment.selected_value_bps > 0.0);
}

#[test]
fn flat_high_risk_prefers_smaller_buy_exposure() {
    let forecasts = forecast_set(&[
        (1_000, 100.0, 100.0, -200.0, 0.4, 0.2),
        (3_000, 100.0, 100.0, -200.0, 0.4, 0.2),
    ]);
    let assessment = assess_continuous_action(
        &policy(),
        &forecasts,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("risk-aware flat opportunity must assess");

    assert_eq!(assessment.action, FastLaneAction::Buy);
    assert_eq!(assessment.target_exposure_fraction, 0.25);
    assert_eq!(assessment.selected_horizon_ms, Some(1_000));
    assert_eq!(assessment.selected_reward_bps, 100.0);
    assert_eq!(assessment.selected_risk_bps, 160.0);
    assert_eq!(assessment.selected_value_bps, 15.0);
}

#[test]
fn horizon_disagreement_increases_risk_and_can_shrink_entry() {
    let mut p = policy();
    p.horizon_disagreement_weight = 1.0;
    let forecasts = forecast_set(&[
        (1_000, 120.0, 200.0, 0.0, 0.0, 0.0),
        (3_000, 120.0, 20.0, 0.0, 0.0, 0.0),
    ]);
    let assessment = assess_continuous_action(
        &p,
        &forecasts,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("disagreement-aware flat opportunity must assess");

    assert_eq!(assessment.action, FastLaneAction::Buy);
    assert_eq!(assessment.target_exposure_fraction, 0.25);
    assert!(assessment
        .horizon_evidence
        .iter()
        .all(|evidence| evidence.disagreement_bps == 180.0));
}

#[test]
fn flat_hard_economics_veto_zero_cap_and_threshold_choose_skip() {
    let forecasts = forecast_set(&[(1_000, 500.0, 500.0, 0.0, 0.0, 0.0)]);
    let mut p = policy();
    p.horizons_ms = vec![1_000];

    let mut veto = constraints();
    veto.buy_economically_allowed = false;
    let assessment = assess_continuous_action(
        &p,
        &forecasts,
        &FastActionPositionState::Flat,
        &veto,
    )
    .expect("hard veto must return SKIP assessment");
    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(assessment.reason, FastContinuousActionReason::SkipSelected);

    let mut zero_cap = constraints();
    zero_cap.max_exposure_fraction = 0.0;
    let assessment = assess_continuous_action(
        &p,
        &forecasts,
        &FastActionPositionState::Flat,
        &zero_cap,
    )
    .expect("zero cap must return SKIP assessment");
    assert_eq!(assessment.action, FastLaneAction::Skip);

    p.minimum_buy_value_bps = 10_000.0;
    let assessment = assess_continuous_action(
        &p,
        &forecasts,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("threshold miss must return SKIP assessment");
    assert_eq!(assessment.action, FastLaneAction::Skip);
}

#[test]
fn flat_incomplete_or_nearby_horizon_forecasts_skip_without_imputation() {
    let assessment = assess_continuous_action(
        &policy(),
        &incomplete_forecast_set(),
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("incomplete flat evidence must fail closed to SKIP");
    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reason,
        FastContinuousActionReason::ForecastEvidenceIncomplete
    );
    assert!(assessment.horizon_evidence.is_empty());

    let mut p = policy();
    p.horizons_ms = vec![1_000];
    let nearby = forecast_set(&[(1_001, 300.0, 300.0, -5.0, 0.0, 0.0)]);
    let assessment = assess_continuous_action(
        &p,
        &nearby,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("nearby horizon cannot substitute exact configured horizon");
    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(
        assessment.reason,
        FastContinuousActionReason::ForecastEvidenceIncomplete
    );
}

#[test]
fn open_strong_continuation_holds_and_uses_sunk_cost_correctly() {
    let forecasts = forecast_set(&[
        (1_000, -500.0, 200.0, -20.0, 0.05, 0.02),
        (3_000, -500.0, 180.0, -20.0, 0.05, 0.02),
    ]);
    let assessment = assess_continuous_action(
        &policy(),
        &forecasts,
        &FastActionPositionState::Open {
            current_exposure_fraction: 0.8,
        },
        &constraints(),
    )
    .expect("strong open continuation must assess");

    assert_eq!(assessment.action, FastLaneAction::Hold);
    assert_eq!(assessment.reason, FastContinuousActionReason::HoldSelected);
    assert_eq!(assessment.target_exposure_fraction, 0.8);
    assert_eq!(assessment.selected_horizon_ms, Some(1_000));
    assert!(assessment.selected_reward_bps > 0.0);
    assert!(assessment.selected_value_bps > 0.0);
    // Entry cost-adjusted forecast is deliberately terrible; open continuation
    // still uses raw endpoint return because entry cost is already sunk.
    assert!(assessment
        .horizon_evidence
        .iter()
        .all(|evidence| evidence.entry_cost_adjusted_return_bps == -500.0));
}

#[test]
fn open_high_risk_prefers_exact_executable_reduction_target() {
    let forecasts = forecast_set(&[
        (1_000, 0.0, 100.0, -200.0, 0.3, 0.2),
        (3_000, 0.0, 100.0, -200.0, 0.3, 0.2),
    ]);
    let assessment = assess_continuous_action(
        &policy(),
        &forecasts,
        &FastActionPositionState::Open {
            current_exposure_fraction: 1.0,
        },
        &constraints(),
    )
    .expect("high-risk open state must assess");

    assert_eq!(assessment.action, FastLaneAction::Reduce);
    assert_eq!(assessment.reason, FastContinuousActionReason::ReduceSelected);
    assert_eq!(assessment.target_exposure_fraction, 0.25);
    assert_eq!(assessment.selected_horizon_ms, Some(1_000));
    assert_eq!(assessment.selected_reward_bps, 80.0);
    assert_eq!(assessment.selected_risk_bps, 150.0);
    assert_eq!(assessment.selected_execution_cost_bps, 11.25);
    assert_eq!(assessment.selected_value_bps, -0.625);
}

#[test]
fn open_weak_continuation_sells_and_charges_current_sell_cost() {
    let forecasts = forecast_set(&[
        (1_000, 1_000.0, -50.0, -20.0, 0.05, 0.02),
        (3_000, 1_000.0, -60.0, -20.0, 0.05, 0.02),
    ]);
    let assessment = assess_continuous_action(
        &policy(),
        &forecasts,
        &FastActionPositionState::Open {
            current_exposure_fraction: 1.0,
        },
        &constraints(),
    )
    .expect("weak open state must assess");

    assert_eq!(assessment.action, FastLaneAction::Sell);
    assert_eq!(assessment.reason, FastContinuousActionReason::SellSelected);
    assert_eq!(assessment.selected_horizon_ms, None);
    assert_eq!(assessment.target_exposure_fraction, 0.0);
    assert_eq!(assessment.selected_execution_cost_bps, 8.0);
    assert_eq!(assessment.selected_value_bps, -8.0);
}

#[test]
fn reduction_requires_exact_current_cost_evidence() {
    let forecasts = forecast_set(&[
        (1_000, 0.0, 100.0, -200.0, 0.3, 0.2),
        (3_000, 0.0, 100.0, -200.0, 0.3, 0.2),
    ]);
    let mut c = constraints();
    c.reduce_execution_costs.retain(|cost| cost.target_exposure_fraction == 0.5);
    let assessment = assess_continuous_action(
        &policy(),
        &forecasts,
        &FastActionPositionState::Open {
            current_exposure_fraction: 1.0,
        },
        &c,
    )
    .expect("only exact executable reduction target can be considered");

    assert!(assessment
        .candidates
        .iter()
        .filter(|candidate| candidate.action == FastLaneAction::Reduce)
        .all(|candidate| candidate.target_exposure_fraction == 0.5));
}

#[test]
fn dynamic_horizon_changes_without_policy_mutation() {
    let mut p = policy();
    p.minimum_hold_value_bps = 0.0;
    let first = forecast_set(&[
        (1_000, 0.0, 180.0, -10.0, 0.0, 0.0),
        (3_000, 0.0, 60.0, -10.0, 0.0, 0.0),
    ]);
    let second = forecast_set(&[
        (1_000, 0.0, 60.0, -10.0, 0.0, 0.0),
        (3_000, 0.0, 180.0, -10.0, 0.0, 0.0),
    ]);
    let position = FastActionPositionState::Open {
        current_exposure_fraction: 0.5,
    };

    let first_assessment = assess_continuous_action(&p, &first, &position, &constraints())
        .expect("first dynamic horizon assessment");
    let second_assessment = assess_continuous_action(&p, &second, &position, &constraints())
        .expect("second dynamic horizon assessment");

    assert_eq!(first_assessment.action, FastLaneAction::Hold);
    assert_eq!(second_assessment.action, FastLaneAction::Hold);
    assert_eq!(first_assessment.selected_horizon_ms, Some(1_000));
    assert_eq!(second_assessment.selected_horizon_ms, Some(3_000));
}

#[test]
fn exposure_cap_forces_derisk_and_force_sell_overrides_forecasts() {
    let forecasts = forecast_set(&[
        (1_000, 500.0, 300.0, 0.0, 0.0, 0.0),
        (3_000, 500.0, 300.0, 0.0, 0.0, 0.0),
    ]);
    let position = FastActionPositionState::Open {
        current_exposure_fraction: 0.8,
    };
    let mut capped = constraints();
    capped.max_exposure_fraction = 0.5;
    let assessment = assess_continuous_action(&policy(), &forecasts, &position, &capped)
        .expect("over-cap exposure must de-risk");
    assert_eq!(assessment.action, FastLaneAction::Reduce);
    assert_eq!(assessment.target_exposure_fraction, 0.5);

    let mut forced = constraints();
    forced.force_sell = true;
    let assessment = assess_continuous_action(&policy(), &forecasts, &position, &forced)
        .expect("force sell must override learned value");
    assert_eq!(assessment.action, FastLaneAction::Sell);
    assert_eq!(assessment.reason, FastContinuousActionReason::ForceSell);
}

#[test]
fn force_sell_and_missing_forecast_safe_actions_fail_closed_when_unavailable() {
    let forecasts = forecast_set(&[(1_000, 500.0, 300.0, 0.0, 0.0, 0.0)]);
    let mut p = policy();
    p.horizons_ms = vec![1_000];
    let position = FastActionPositionState::Open {
        current_exposure_fraction: 0.8,
    };
    let mut forced = constraints();
    forced.force_sell = true;
    forced.sell_executable = false;
    assert!(matches!(
        assess_continuous_action(&p, &forecasts, &position, &forced),
        Err(FastContinuousActionError::ForceSellUnavailable)
    ));

    let missing = incomplete_forecast_set();
    let mut unavailable = constraints();
    unavailable.reduce_execution_costs.clear();
    assert!(matches!(
        assess_continuous_action(&p, &missing, &position, &unavailable),
        Err(FastContinuousActionError::MissingForecastSafeActionUnavailable {
            action: FastLaneAction::Reduce
        })
    ));
}

#[test]
fn missing_open_forecast_reduce_fallback_uses_largest_legal_target() {
    let position = FastActionPositionState::Open {
        current_exposure_fraction: 0.8,
    };
    let assessment = assess_continuous_action(
        &policy(),
        &incomplete_forecast_set(),
        &position,
        &constraints(),
    )
    .expect("missing open forecast must use explicit safe reduction");

    assert_eq!(assessment.action, FastLaneAction::Reduce);
    assert_eq!(
        assessment.reason,
        FastContinuousActionReason::ForecastEvidenceIncomplete
    );
    assert_eq!(assessment.selected_horizon_ms, None);
    assert_eq!(assessment.target_exposure_fraction, 0.5);
    assert_eq!(assessment.selected_execution_cost_bps, 3.0);
    assert!(assessment.horizon_evidence.is_empty());
}

#[test]
fn missing_open_forecast_sell_fallback_uses_current_sell_cost() {
    let mut p = policy();
    p.missing_forecast_open_action = FastLaneAction::Sell;
    let position = FastActionPositionState::Open {
        current_exposure_fraction: 0.5,
    };
    let assessment = assess_continuous_action(
        &p,
        &incomplete_forecast_set(),
        &position,
        &constraints(),
    )
    .expect("missing forecast SELL fallback must assess when executable");

    assert_eq!(assessment.action, FastLaneAction::Sell);
    assert_eq!(
        assessment.reason,
        FastContinuousActionReason::ForecastEvidenceIncomplete
    );
    assert_eq!(assessment.selected_execution_cost_bps, 4.0);
    assert_eq!(assessment.selected_value_bps, -4.0);
}

#[test]
fn invalid_forecast_policy_constraint_and_position_inputs_fail_closed() {
    let mut duplicate = forecast_set(&[(1_000, 100.0, 100.0, -10.0, 0.1, 0.1)]);
    duplicate.predictions.push(duplicate.predictions[0].clone());
    assert!(matches!(
        assess_continuous_action(
            &policy(),
            &duplicate,
            &FastActionPositionState::Flat,
            &constraints(),
        ),
        Err(FastContinuousActionError::InvalidForecastSet(_))
    ));

    let mut invalid_probability = forecast_set(&[(1_000, 100.0, 100.0, -10.0, 1.2, 0.1)]);
    assert!(matches!(
        assess_continuous_action(
            &policy(),
            &invalid_probability,
            &FastActionPositionState::Flat,
            &constraints(),
        ),
        Err(FastContinuousActionError::InvalidForecastSet(_))
    ));
    invalid_probability.predictions[0].predicted_value = f64::NAN;
    assert!(matches!(
        assess_continuous_action(
            &policy(),
            &invalid_probability,
            &FastActionPositionState::Flat,
            &constraints(),
        ),
        Err(FastContinuousActionError::InvalidForecastSet(_))
    ));

    let mut bad_sha = forecast_set(&[(1_000, 100.0, 100.0, -10.0, 0.1, 0.1)]);
    bad_sha.champion_fingerprint_sha256 = "ABC".to_string();
    assert!(matches!(
        assess_continuous_action(
            &policy(),
            &bad_sha,
            &FastActionPositionState::Flat,
            &constraints(),
        ),
        Err(FastContinuousActionError::InvalidForecastSet(_))
    ));

    let forecasts = forecast_set(&[(1_000, 100.0, 100.0, -10.0, 0.1, 0.1)]);
    let mut bad_policy = policy();
    bad_policy.horizons_ms = vec![3_000, 1_000];
    assert!(matches!(
        assess_continuous_action(
            &bad_policy,
            &forecasts,
            &FastActionPositionState::Flat,
            &constraints(),
        ),
        Err(FastContinuousActionError::InvalidPolicy(_))
    ));

    let mut bad_constraints = constraints();
    bad_constraints.sell_now_cost_bps = -1.0;
    assert!(matches!(
        assess_continuous_action(
            &policy(),
            &forecasts,
            &FastActionPositionState::Flat,
            &bad_constraints,
        ),
        Err(FastContinuousActionError::InvalidConstraints(_))
    ));

    assert!(matches!(
        assess_continuous_action(
            &policy(),
            &forecasts,
            &FastActionPositionState::Open {
                current_exposure_fraction: 1.2,
            },
            &constraints(),
        ),
        Err(FastContinuousActionError::InvalidPosition(_))
    ));
}

#[test]
fn policy_rejects_invalid_fallback_and_reduction_contracts() {
    let forecasts = forecast_set(&[(1_000, 100.0, 100.0, -10.0, 0.1, 0.1)]);
    let mut p = policy();
    p.missing_forecast_open_action = FastLaneAction::Hold;
    assert!(matches!(
        assess_continuous_action(
            &p,
            &forecasts,
            &FastActionPositionState::Flat,
            &constraints(),
        ),
        Err(FastContinuousActionError::InvalidPolicy(_))
    ));

    p = policy();
    p.reduce_target_exposure_candidates = vec![0.5, 0.25];
    assert!(matches!(
        assess_continuous_action(
            &p,
            &forecasts,
            &FastActionPositionState::Flat,
            &constraints(),
        ),
        Err(FastContinuousActionError::InvalidPolicy(_))
    ));

    let mut c = constraints();
    c.reduce_execution_costs.swap(0, 1);
    assert!(matches!(
        assess_continuous_action(
            &policy(),
            &forecasts,
            &FastActionPositionState::Flat,
            &c,
        ),
        Err(FastContinuousActionError::InvalidConstraints(_))
    ));
}

#[test]
fn deterministic_audit_output_is_canonical_and_selected_values_reconcile() {
    let forecasts = forecast_set(&[
        (1_000, 200.0, 220.0, -20.0, 0.05, 0.02),
        (3_000, 250.0, 260.0, -30.0, 0.05, 0.02),
    ]);
    let first = assess_continuous_action(
        &policy(),
        &forecasts,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("first deterministic assessment");
    let second = assess_continuous_action(
        &policy(),
        &forecasts,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("second deterministic assessment");
    assert_eq!(first, second);

    assert_eq!(
        first
            .horizon_evidence
            .iter()
            .map(|evidence| evidence.horizon_ms)
            .collect::<Vec<_>>(),
        vec![1_000, 3_000]
    );
    assert!(first.candidates.windows(2).all(|window| {
        let left = &window[0];
        let right = &window[1];
        (left.action.as_str(), left.target_exposure_fraction, left.horizon_ms)
            <= (right.action.as_str(), right.target_exposure_fraction, right.horizon_ms)
    }));

    let selected = first
        .candidates
        .iter()
        .find(|candidate| {
            candidate.eligible
                && candidate.action == first.action
                && candidate.horizon_ms == first.selected_horizon_ms
                && candidate.target_exposure_fraction == first.target_exposure_fraction
        })
        .expect("selected candidate must be preserved in audit output");
    assert_eq!(selected.reward_bps, first.selected_reward_bps);
    assert_eq!(selected.risk_bps, first.selected_risk_bps);
    assert_eq!(
        selected.execution_cost_penalty_bps,
        first.selected_execution_cost_bps
    );
    assert_eq!(selected.comparison_value_bps, first.selected_value_bps);
}

#[test]
fn equal_value_ties_prefer_lower_exposure_then_shorter_horizon() {
    let mut p = policy();
    p.horizons_ms = vec![1_000, 3_000];
    p.entry_exposure_candidates = vec![0.25, 0.5];
    p.adverse_excursion_weight = 0.0;
    p.reversal_penalty_bps = 0.0;
    p.route_unavailability_penalty_bps = 0.0;
    p.horizon_disagreement_weight = 0.0;
    p.minimum_buy_value_bps = 0.0;
    let forecasts = forecast_set(&[
        (1_000, 0.0, 10.0, 0.0, 0.0, 0.0),
        (3_000, 0.0, 10.0, 0.0, 0.0, 0.0),
    ]);
    let assessment = assess_continuous_action(
        &p,
        &forecasts,
        &FastActionPositionState::Flat,
        &constraints(),
    )
    .expect("tie assessment must be deterministic");

    // BUY candidates tie SKIP at zero value; lower exposure wins first,
    // therefore SKIP at exposure 0 is the deterministic safe tie winner.
    assert_eq!(assessment.action, FastLaneAction::Skip);
    assert_eq!(assessment.target_exposure_fraction, 0.0);
}