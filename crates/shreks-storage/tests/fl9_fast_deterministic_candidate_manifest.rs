use shreks_core::{
    FastBaselineKind, GraduationFlowPolicy, ImpulseScalpPolicy, LongerRunnerPolicy,
    MicroPullbackPolicy, PreGraduationPolicy, WalletCohortPolicy,
    GRADUATION_FLOW_BASELINE_VERSION, IMPULSE_SCALP_BASELINE_VERSION,
    LONGER_RUNNER_BASELINE_VERSION, MICRO_PULLBACK_BASELINE_VERSION,
    PRE_GRADUATION_BASELINE_VERSION, WALLET_COHORT_BASELINE_VERSION,
};
use shreks_storage::{
    build_fast_deterministic_candidate_manifest,
    decode_fast_deterministic_candidate_manifest_json,
    encode_fast_deterministic_candidate_manifest_json,
    FastDeterministicEntryPolicyRef, FastDeterministicLifecyclePolicy,
    FastDeterministicManagerPolicyRef,
    FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME,
    FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION,
    FAST_DETERMINISTIC_LIFECYCLE_VERSION,
};

const GOLDEN: &str = include_str!(
    "../../../python/tests/fixtures/fast_deterministic_candidate_manifest_v1.json"
);

fn lifecycle(
    entry: FastBaselineKind,
    manager: FastBaselineKind,
) -> FastDeterministicLifecyclePolicy {
    FastDeterministicLifecyclePolicy {
        version: FAST_DETERMINISTIC_LIFECYCLE_VERSION,
        entry_baseline_kind: entry,
        manager_baseline_kind: manager,
        entry_target_exposure_fraction: 0.8,
        reduce_remaining_fraction: 0.5,
    }
}

fn impulse() -> ImpulseScalpPolicy {
    ImpulseScalpPolicy {
        version: IMPULSE_SCALP_BASELINE_VERSION,
        signal_window_ms: 500,
        context_window_ms: 2_000,
        min_buy_count: 5,
        min_unique_buy_actors: 4,
        min_count_imbalance: 0.5,
        min_quote_flow_imbalance: 0.5,
        min_quote_flow_velocity_per_second: 3.0,
        min_quote_flow_acceleration_per_second2: 5.0,
        min_velocity_expansion_ratio: 2.0,
        min_recovery_from_local_low: 0.02,
        max_drawdown_from_local_high: 0.03,
    }
}

fn longer() -> LongerRunnerPolicy {
    LongerRunnerPolicy {
        version: LONGER_RUNNER_BASELINE_VERSION,
        downside_risk_weight: 1.0,
        min_risk_adjusted_continuation_bps_for_hold: 100.0,
        max_risk_adjusted_continuation_bps_for_sell: -100.0,
    }
}

fn kind_str(kind: FastBaselineKind) -> &'static str {
    match kind {
        FastBaselineKind::ImpulseScalp => "IMPULSE_SCALP",
        FastBaselineKind::MicroPullback => "MICRO_PULLBACK",
        FastBaselineKind::PreGraduation => "PRE_GRADUATION",
        FastBaselineKind::GraduationFlow => "GRADUATION_FLOW",
        FastBaselineKind::WalletCohort => "WALLET_COHORT",
        FastBaselineKind::LongerRunner => "LONGER_RUNNER",
    }
}

fn build(
    impulse: &ImpulseScalpPolicy,
    longer: &LongerRunnerPolicy,
) -> shreks_storage::FastDeterministicCandidateManifestWire {
    build_fast_deterministic_candidate_manifest(
        "fl9-baseline-impulse-scalp-longer-runner-v1",
        "impulse-scalp__longer-runner-v1",
        &lifecycle(FastBaselineKind::ImpulseScalp, FastBaselineKind::LongerRunner),
        FastDeterministicEntryPolicyRef::ImpulseScalp(impulse),
        FastDeterministicManagerPolicyRef::LongerRunner(longer),
    )
    .unwrap()
}

#[test]
fn typed_builder_matches_shared_golden_candidate_manifest_exactly() {
    let built = build(&impulse(), &longer());

    assert_eq!(
        built.schema_name,
        FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME
    );
    assert_eq!(
        built.schema_version,
        FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION
    );
    assert_eq!(
        built.candidate_fingerprint_sha256,
        "7377f016783f80c6d3935ff41efd7a66b8da280df13cd7be8d2e6c03146a8676"
    );
    assert_eq!(
        encode_fast_deterministic_candidate_manifest_json(&built).unwrap(),
        GOLDEN
    );

    let decoded = decode_fast_deterministic_candidate_manifest_json(GOLDEN).unwrap();
    assert_eq!(decoded, built);
}

#[test]
fn every_selected_impulse_and_longer_policy_field_is_fingerprint_sensitive() {
    let base_impulse = impulse();
    let base_longer = longer();
    let baseline = build(&base_impulse, &base_longer).candidate_fingerprint_sha256;

    let mut impulse_variants = Vec::new();
    let mut value = base_impulse.clone();
    value.version += 1;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.signal_window_ms += 1;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.context_window_ms += 1;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.min_buy_count += 1;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.min_unique_buy_actors += 1;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.min_count_imbalance += 0.01;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.min_quote_flow_imbalance += 0.01;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.min_quote_flow_velocity_per_second += 0.01;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.min_quote_flow_acceleration_per_second2 += 0.01;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.min_velocity_expansion_ratio += 0.01;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.min_recovery_from_local_low += 0.001;
    impulse_variants.push(value);
    let mut value = base_impulse.clone();
    value.max_drawdown_from_local_high += 0.001;
    impulse_variants.push(value);

    for changed in impulse_variants {
        let result = build_fast_deterministic_candidate_manifest(
            "fl9-baseline-impulse-scalp-longer-runner-v1",
            "impulse-scalp__longer-runner-v1",
            &lifecycle(FastBaselineKind::ImpulseScalp, FastBaselineKind::LongerRunner),
            FastDeterministicEntryPolicyRef::ImpulseScalp(&changed),
            FastDeterministicManagerPolicyRef::LongerRunner(&base_longer),
        );
        match result {
            Ok(manifest) => assert_ne!(manifest.candidate_fingerprint_sha256, baseline),
            Err(_) => assert_ne!(changed.version, base_impulse.version),
        }
    }

    let mut longer_variants = Vec::new();
    let mut value = base_longer.clone();
    value.version += 1;
    longer_variants.push(value);
    let mut value = base_longer.clone();
    value.downside_risk_weight += 0.01;
    longer_variants.push(value);
    let mut value = base_longer.clone();
    value.min_risk_adjusted_continuation_bps_for_hold += 1.0;
    longer_variants.push(value);
    let mut value = base_longer.clone();
    value.max_risk_adjusted_continuation_bps_for_sell -= 1.0;
    longer_variants.push(value);

    for changed in longer_variants {
        let result = build_fast_deterministic_candidate_manifest(
            "fl9-baseline-impulse-scalp-longer-runner-v1",
            "impulse-scalp__longer-runner-v1",
            &lifecycle(FastBaselineKind::ImpulseScalp, FastBaselineKind::LongerRunner),
            FastDeterministicEntryPolicyRef::ImpulseScalp(&base_impulse),
            FastDeterministicManagerPolicyRef::LongerRunner(&changed),
        );
        match result {
            Ok(manifest) => assert_ne!(manifest.candidate_fingerprint_sha256, baseline),
            Err(_) => assert_ne!(changed.version, base_longer.version),
        }
    }
}

#[test]
fn lifecycle_kind_and_selected_policy_variant_must_match() {
    let error = build_fast_deterministic_candidate_manifest(
        "candidate-v1",
        "strategy-v1",
        &lifecycle(FastBaselineKind::MicroPullback, FastBaselineKind::LongerRunner),
        FastDeterministicEntryPolicyRef::ImpulseScalp(&impulse()),
        FastDeterministicManagerPolicyRef::LongerRunner(&longer()),
    )
    .unwrap_err()
    .to_string();

    assert!(error.contains("entry") && error.contains("kind"), "{error}");
}

#[test]
fn builder_exposes_all_six_fl6_policy_families_without_market_evidence() {
    let micro = MicroPullbackPolicy {
        version: MICRO_PULLBACK_BASELINE_VERSION,
        reclaim_window_ms: 500,
        structure_window_ms: 2_000,
        min_impulse_move_fraction: 0.05,
        min_pullback_depth_fraction: 0.01,
        max_pullback_depth_fraction: 0.10,
        min_reclaim_fraction: 0.5,
        min_reclaim_buy_count: 3,
        min_reclaim_unique_buy_actors: 2,
        min_reclaim_buy_arrival_rate_per_second: 1.0,
        max_reclaim_sell_arrival_rate_per_second: 2.0,
        min_reclaim_count_imbalance: 0.1,
        min_reclaim_quote_flow_imbalance: 0.1,
        min_reclaim_quote_flow_velocity_per_second: 0.1,
        min_reclaim_quote_flow_acceleration_per_second2: 0.0,
    };
    let pre = PreGraduationPolicy {
        version: PRE_GRADUATION_BASELINE_VERSION,
        signal_window_ms: 500,
        context_window_ms: 2_000,
        graduation_target_real_base_reserve_raw: 100,
        maximum_pre_graduation_real_base_reserve_raw: 90,
        min_buy_count: 3,
        min_unique_buy_actors: 2,
        min_buy_arrival_rate_per_second: 1.0,
        min_count_imbalance: 0.1,
        min_quote_flow_imbalance: 0.1,
        min_quote_flow_velocity_per_second: 0.1,
        min_quote_flow_acceleration_per_second2: 0.0,
        min_velocity_expansion_ratio: 1.0,
        min_buy_participation_of_remaining: 0.01,
    };
    let graduation = GraduationFlowPolicy {
        version: GRADUATION_FLOW_BASELINE_VERSION,
        flow_window_ms: 1_000,
        max_graduation_age_ms: 10_000,
        min_pre_buy_count: 1,
        min_pre_quote_flow_velocity_per_second: 0.1,
        min_post_buy_count: 1,
        min_post_unique_buy_actors: 1,
        min_post_buy_arrival_rate_per_second: 0.1,
        max_post_sell_arrival_rate_per_second: 2.0,
        min_post_count_imbalance: 0.0,
        min_post_quote_flow_imbalance: 0.0,
        min_post_quote_flow_velocity_per_second: 0.1,
        min_post_quote_flow_acceleration_per_second2: 0.0,
        min_post_to_pre_velocity_ratio: 0.5,
    };
    let wallet = WalletCohortPolicy {
        version: WALLET_COHORT_BASELINE_VERSION,
        min_support_wallet_count_for_ride: 2,
        min_confidence_weighted_support_for_ride: 1.0,
        min_independent_support_wallet_count_for_ride: 2,
        min_hold_horizon_wallet_weight_for_ride: 1.0,
        reduce_after_median_hold_ratio: 1.0,
        min_confidence_weighted_exit_for_reduce: 1.0,
        min_exit_pressure_ratio_for_reduce: 0.5,
        min_confidence_weighted_exit_for_sell: 2.0,
        min_exit_pressure_ratio_for_sell: 0.8,
        min_independent_exit_wallet_count_for_sell: 2,
    };

    let entry_values = [
        (
            FastBaselineKind::MicroPullback,
            FastDeterministicEntryPolicyRef::MicroPullback(&micro),
        ),
        (
            FastBaselineKind::PreGraduation,
            FastDeterministicEntryPolicyRef::PreGraduation(&pre),
        ),
        (
            FastBaselineKind::GraduationFlow,
            FastDeterministicEntryPolicyRef::GraduationFlow(&graduation),
        ),
    ];

    for (kind, entry) in entry_values {
        let manifest = build_fast_deterministic_candidate_manifest(
            "candidate-v1",
            "strategy-v1",
            &lifecycle(kind, FastBaselineKind::LongerRunner),
            entry,
            FastDeterministicManagerPolicyRef::LongerRunner(&longer()),
        )
        .unwrap();
        assert_eq!(manifest.entry_policy.kind, kind_str(kind));
    }

    let manifest = build_fast_deterministic_candidate_manifest(
        "candidate-v1",
        "strategy-v1",
        &lifecycle(FastBaselineKind::ImpulseScalp, FastBaselineKind::WalletCohort),
        FastDeterministicEntryPolicyRef::ImpulseScalp(&impulse()),
        FastDeterministicManagerPolicyRef::WalletCohort(&wallet),
    )
    .unwrap();
    assert_eq!(manifest.manager_policy.kind, "WALLET_COHORT");
}

#[test]
fn deterministic_candidate_manifest_source_has_no_dynamic_or_execution_authority() {
    let source = include_str!("../src/fast_deterministic_candidate_manifest.rs");

    for forbidden in [
        "FastTrainingFeatureRecord",
        "FastMarketSnapshot",
        "FastPaper",
        "PaperLedger",
        "RiskContext",
        "TradeIntent",
        "rusqlite",
        "reqwest",
        "std::fs",
        "std::net",
        "RuntimeMode::Live",
        "Signer",
        "submit_transaction",
        "promote",
    ] {
        assert!(
            !source.contains(forbidden),
            "candidate manifest must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "ImpulseScalpPolicy",
        "MicroPullbackPolicy",
        "PreGraduationPolicy",
        "GraduationFlowPolicy",
        "WalletCohortPolicy",
        "LongerRunnerPolicy",
        "candidate_fingerprint_sha256",
        "Sha256",
    ] {
        assert!(
            source.contains(required),
            "candidate manifest must preserve full policy provenance seam: {required}"
        );
    }
}
