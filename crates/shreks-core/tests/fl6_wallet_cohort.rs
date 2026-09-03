use shreks_core::{
    assess_wallet_cohort_ride_fade, FastLaneAction, FastMarketKey, FastMarketSnapshot,
    VenueId, WalletCohortError, WalletCohortEvidence, WalletCohortPolicy,
    WalletCohortPositionInput, WalletCohortPosture, WalletCohortReason,
    WalletCohortSideSummary, WALLET_COHORT_BASELINE_VERSION,
    WALLET_COHORT_EVIDENCE_VERSION,
};

fn market() -> FastMarketKey {
    FastMarketKey::new("MINT", "SOL", VenueId::PumpSwap).expect("valid test market")
}

fn snapshot() -> FastMarketSnapshot {
    FastMarketSnapshot {
        market: market(),
        as_of_unix_ms: 200_000,
        last_sequence: None,
        last_price_quote: None,
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: vec![],
    }
}

fn position() -> WalletCohortPositionInput {
    WalletCohortPositionInput {
        market: market(),
        as_of_unix_ms: 200_000,
        opened_at_unix_ms: 140_000,
    }
}

fn policy() -> WalletCohortPolicy {
    WalletCohortPolicy {
        version: WALLET_COHORT_BASELINE_VERSION,
        min_support_wallet_count_for_ride: 2,
        min_confidence_weighted_support_for_ride: 1.5,
        min_independent_support_wallet_count_for_ride: 2,
        min_hold_horizon_wallet_weight_for_ride: 1.0,
        reduce_after_median_hold_ratio: 1.0,
        min_confidence_weighted_exit_for_reduce: 0.75,
        min_exit_pressure_ratio_for_reduce: 0.35,
        min_confidence_weighted_exit_for_sell: 1.5,
        min_exit_pressure_ratio_for_sell: 0.60,
        min_independent_exit_wallet_count_for_sell: 2,
    }
}

fn side(
    strong_wallet_count: u64,
    confidence_weighted_strong_count: f64,
    independently_strong_wallet_count: Option<u64>,
    all_pairs_independent_under_evidence: Option<bool>,
) -> WalletCohortSideSummary {
    WalletCohortSideSummary {
        strong_wallet_count,
        confidence_weighted_strong_count,
        independently_strong_wallet_count,
        all_pairs_independent_under_evidence,
    }
}

fn evidence(
    support: WalletCohortSideSummary,
    exits: WalletCohortSideSummary,
    support_hold_horizon_wallet_weight: f64,
    confidence_weighted_support_median_hold_ms: Option<f64>,
) -> WalletCohortEvidence {
    WalletCohortEvidence {
        version: WALLET_COHORT_EVIDENCE_VERSION,
        as_of_unix_ms: 200_000,
        candidate_mint: "MINT".to_owned(),
        wallet_feature_policy_version: "d5-wallet-policy-test".to_owned(),
        profile_policy_version: Some("d3-profile-policy-test".to_owned()),
        relationship_policy_version: "d4-relationship-policy-test".to_owned(),
        support,
        exits,
        support_hold_horizon_wallet_weight,
        confidence_weighted_support_median_hold_ms,
    }
}

fn ride_evidence() -> WalletCohortEvidence {
    evidence(
        side(3, 2.4, Some(3), Some(true)),
        side(0, 0.0, Some(0), None),
        2.0,
        Some(120_000.0),
    )
}

#[test]
fn strong_independent_support_with_remaining_horizon_rides() {
    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&ride_evidence()),
        &position(),
        &policy(),
    )
    .expect("valid ride evidence");

    assert_eq!(assessment.version, WALLET_COHORT_BASELINE_VERSION);
    assert_eq!(assessment.action, FastLaneAction::Hold);
    assert_eq!(assessment.posture, WalletCohortPosture::Ride);
    assert_eq!(assessment.position_age_ms, 60_000);
    assert_eq!(assessment.exit_pressure_ratio, Some(0.0));
    assert_eq!(assessment.ride_horizon_ms, Some(120_000.0));
    assert_eq!(assessment.remaining_horizon_ms, Some(60_000.0));
    assert!(
        assessment
            .reasons
            .contains(&WalletCohortReason::RideConditionsMet)
    );
}

#[test]
fn moderate_exit_pressure_reduces() {
    let wallet_evidence = evidence(
        side(2, 1.6, Some(2), Some(true)),
        side(1, 0.9, Some(1), Some(true)),
        1.5,
        Some(120_000.0),
    );

    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect("valid reduce evidence");

    assert_eq!(assessment.action, FastLaneAction::Reduce);
    assert_eq!(assessment.posture, WalletCohortPosture::Fade);
    assert!(
        assessment
            .reasons
            .contains(&WalletCohortReason::ReduceConditionsMet)
    );
}

#[test]
fn strong_independent_exit_pressure_sells() {
    let wallet_evidence = evidence(
        side(1, 0.5, Some(1), Some(true)),
        side(3, 2.4, Some(3), Some(true)),
        0.5,
        Some(120_000.0),
    );

    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect("valid sell evidence");

    assert_eq!(assessment.action, FastLaneAction::Sell);
    assert_eq!(assessment.posture, WalletCohortPosture::Fade);
    assert!(
        assessment
            .reasons
            .contains(&WalletCohortReason::SellConditionsMet)
    );
}

#[test]
fn unknown_exit_independence_caps_at_reduce() {
    let wallet_evidence = evidence(
        side(1, 0.5, Some(1), Some(true)),
        side(3, 2.4, None, None),
        0.5,
        Some(120_000.0),
    );

    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect("unknown independence is valid uncertainty");

    assert_eq!(assessment.action, FastLaneAction::Reduce);
    assert_ne!(assessment.action, FastLaneAction::Sell);
    assert!(
        assessment
            .reasons
            .contains(&WalletCohortReason::ExitIndependenceUnknown)
    );
}

#[test]
fn exhausted_reliable_hold_horizon_reduces_but_never_sells_by_itself() {
    let wallet_evidence = evidence(
        side(3, 2.4, Some(3), Some(true)),
        side(0, 0.0, Some(0), None),
        2.0,
        Some(50_000.0),
    );

    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect("valid historical horizon evidence");

    assert_eq!(assessment.action, FastLaneAction::Reduce);
    assert_ne!(assessment.action, FastLaneAction::Sell);
    assert_eq!(assessment.posture, WalletCohortPosture::Fade);
    assert!(
        assessment
            .reasons
            .contains(&WalletCohortReason::HistoricalHoldHorizonExhausted)
    );
}

#[test]
fn missing_hold_horizon_does_not_fabricate_expiry() {
    let wallet_evidence = evidence(
        side(3, 2.4, Some(3), Some(true)),
        side(0, 0.0, Some(0), None),
        0.0,
        None,
    );

    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect("missing horizon is valid unknown evidence");

    assert_eq!(assessment.action, FastLaneAction::Hold);
    assert_eq!(assessment.posture, WalletCohortPosture::Neutral);
    assert_eq!(assessment.ride_horizon_ms, None);
    assert!(
        assessment
            .reasons
            .contains(&WalletCohortReason::HoldHorizonUnavailable)
    );
}

#[test]
fn missing_wallet_evidence_is_neutral_hold() {
    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        None,
        &position(),
        &policy(),
    )
    .expect("missing wallet evidence is not contradictory");

    assert_eq!(assessment.action, FastLaneAction::Hold);
    assert_eq!(assessment.posture, WalletCohortPosture::Neutral);
    assert_eq!(assessment.evidence_version, None);
    assert_eq!(
        assessment.reasons,
        vec![
            WalletCohortReason::WalletEvidenceUnavailable,
            WalletCohortReason::NeutralHold,
        ]
    );
}

#[test]
fn unknown_support_independence_prevents_ride_without_forcing_exit() {
    let wallet_evidence = evidence(
        side(3, 2.4, None, None),
        side(0, 0.0, Some(0), None),
        2.0,
        Some(120_000.0),
    );

    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect("unknown support independence is valid");

    assert_eq!(assessment.action, FastLaneAction::Hold);
    assert_eq!(assessment.posture, WalletCohortPosture::Neutral);
    assert!(
        assessment
            .reasons
            .contains(&WalletCohortReason::SupportIndependenceUnknown)
    );
}

#[test]
fn overlapping_support_and_exit_churn_is_valid() {
    let wallet_evidence = evidence(
        side(3, 2.2, Some(3), Some(true)),
        side(2, 0.8, Some(2), Some(true)),
        2.0,
        Some(120_000.0),
    );

    let assessment = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect("support and exit cohorts need not be disjoint");

    assert_eq!(assessment.action, FastLaneAction::Hold);
}

#[test]
fn candidate_mint_mismatch_fails_closed() {
    let mut wallet_evidence = ride_evidence();
    wallet_evidence.candidate_mint = "OTHER".to_owned();

    let error = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect_err("wrong candidate mint must fail closed");

    assert_eq!(error, WalletCohortError::EvidenceMintMismatch);
}

#[test]
fn evidence_timestamp_mismatch_fails_closed() {
    let mut wallet_evidence = ride_evidence();
    wallet_evidence.as_of_unix_ms = 199_999;

    let error = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&wallet_evidence),
        &position(),
        &policy(),
    )
    .expect_err("stale evidence clock must fail closed");

    assert_eq!(
        error,
        WalletCohortError::EvidenceTimestampMismatch {
            snapshot: 200_000,
            evidence: 199_999,
        }
    );
}

#[test]
fn position_market_or_timestamp_mismatch_fails_closed() {
    let wrong_market = FastMarketKey::new("OTHER", "SOL", VenueId::PumpSwap)
        .expect("valid wrong test market");
    let mut wrong_position = position();
    wrong_position.market = wrong_market;

    let market_error = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&ride_evidence()),
        &wrong_position,
        &policy(),
    )
    .expect_err("wrong position market must fail closed");
    assert_eq!(market_error, WalletCohortError::PositionMarketMismatch);

    let mut wrong_clock = position();
    wrong_clock.as_of_unix_ms = 199_999;
    let clock_error = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&ride_evidence()),
        &wrong_clock,
        &policy(),
    )
    .expect_err("wrong position clock must fail closed");
    assert_eq!(
        clock_error,
        WalletCohortError::PositionTimestampMismatch {
            snapshot: 200_000,
            position: 199_999,
        }
    );
}

#[test]
fn future_position_open_time_fails_closed() {
    let mut future = position();
    future.opened_at_unix_ms = 200_001;

    let error = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&ride_evidence()),
        &future,
        &policy(),
    )
    .expect_err("future position open time must fail closed");

    assert_eq!(
        error,
        WalletCohortError::PositionOpenedAfterDecision {
            opened: 200_001,
            as_of: 200_000,
        }
    );
}

#[test]
fn invalid_nan_policy_or_evidence_fails_closed() {
    let mut invalid_policy = policy();
    invalid_policy.min_confidence_weighted_support_for_ride = f64::NAN;
    let policy_error = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&ride_evidence()),
        &position(),
        &invalid_policy,
    )
    .expect_err("NaN policy must fail closed");
    assert!(matches!(policy_error, WalletCohortError::InvalidPolicy(_)));

    let mut invalid_evidence = ride_evidence();
    invalid_evidence.support.confidence_weighted_strong_count = f64::NAN;
    let evidence_error = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&invalid_evidence),
        &position(),
        &policy(),
    )
    .expect_err("NaN evidence must fail closed");
    assert!(matches!(
        evidence_error,
        WalletCohortError::InvalidEvidence(_)
    ));
}

#[test]
fn identical_inputs_are_identical_and_reason_order_is_stable() {
    let first = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&ride_evidence()),
        &position(),
        &policy(),
    )
    .expect("first deterministic assessment");
    let second = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&ride_evidence()),
        &position(),
        &policy(),
    )
    .expect("second deterministic assessment");

    assert_eq!(first, second);
    assert_eq!(first.reasons, vec![WalletCohortReason::RideConditionsMet]);
}

#[test]
fn wallet_baseline_never_emits_buy_or_skip() {
    let ride = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&ride_evidence()),
        &position(),
        &policy(),
    )
    .unwrap();

    let reduce_evidence = evidence(
        side(2, 1.6, Some(2), Some(true)),
        side(1, 0.9, Some(1), Some(true)),
        1.5,
        Some(120_000.0),
    );
    let reduce = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&reduce_evidence),
        &position(),
        &policy(),
    )
    .unwrap();

    let sell_evidence = evidence(
        side(1, 0.5, Some(1), Some(true)),
        side(3, 2.4, Some(3), Some(true)),
        0.5,
        Some(120_000.0),
    );
    let sell = assess_wallet_cohort_ride_fade(
        &snapshot(),
        Some(&sell_evidence),
        &position(),
        &policy(),
    )
    .unwrap();

    for action in [ride.action, reduce.action, sell.action] {
        assert!(!matches!(action, FastLaneAction::Buy | FastLaneAction::Skip));
    }
}
