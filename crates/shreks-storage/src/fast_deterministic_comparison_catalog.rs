use std::{collections::BTreeSet, error::Error, fmt};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use shreks_core::{
    FastBaselineKind, GraduationFlowPolicy, ImpulseScalpPolicy, LongerRunnerPolicy,
    MicroPullbackPolicy, PreGraduationPolicy, WalletCohortPolicy,
    GRADUATION_FLOW_BASELINE_VERSION, IMPULSE_SCALP_BASELINE_VERSION,
    LONGER_RUNNER_BASELINE_VERSION, MICRO_PULLBACK_BASELINE_VERSION,
    PRE_GRADUATION_BASELINE_VERSION, WALLET_COHORT_BASELINE_VERSION,
};

use crate::{
    build_fast_deterministic_candidate_manifest,
    encode_fast_deterministic_candidate_manifest_json,
    FastDeterministicCandidateManifestWire, FastDeterministicEntryPolicyRef,
    FastDeterministicLifecyclePolicy, FastDeterministicManagerPolicyRef,
    FAST_DETERMINISTIC_LIFECYCLE_VERSION,
};

pub const FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME: &str =
    "shreks.fast_deterministic_comparison_catalog";
pub const FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION: u16 = 1;
pub const FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION: &str =
    "fl9-deterministic-comparison-v1";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicComparisonCatalogWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub catalog_version: String,
    pub candidates: Vec<FastDeterministicCandidateManifestWire>,
    pub catalog_fingerprint_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastDeterministicComparisonCatalogError {
    Json(String),
    Invalid(String),
    CandidateManifest(String),
    FingerprintMismatch,
}

impl fmt::Display for FastDeterministicComparisonCatalogError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(message) => {
                write!(formatter, "deterministic comparison catalog JSON error: {message}")
            }
            Self::Invalid(message) => {
                write!(formatter, "invalid deterministic comparison catalog: {message}")
            }
            Self::CandidateManifest(message) => {
                write!(formatter, "invalid catalog candidate manifest: {message}")
            }
            Self::FingerprintMismatch => formatter
                .write_str("deterministic comparison catalog fingerprint mismatch"),
        }
    }
}

impl Error for FastDeterministicComparisonCatalogError {}

pub fn build_fast_deterministic_comparison_catalog(
) -> Result<FastDeterministicComparisonCatalogWire, FastDeterministicComparisonCatalogError> {
    let impulse = impulse_policy();
    let micro = micro_pullback_policy();
    let pre = pre_graduation_policy();
    let graduation = graduation_flow_policy();
    let wallet = wallet_cohort_policy();
    let longer = longer_runner_policy();

    let mut candidates = Vec::with_capacity(8);

    push_candidate(
        &mut candidates,
        "fl9-baseline-graduation-flow-longer-runner-v1",
        "graduation-flow__longer-runner-v1",
        FastBaselineKind::GraduationFlow,
        FastBaselineKind::LongerRunner,
        FastDeterministicEntryPolicyRef::GraduationFlow(&graduation),
        FastDeterministicManagerPolicyRef::LongerRunner(&longer),
    )?;
    push_candidate(
        &mut candidates,
        "fl9-baseline-graduation-flow-wallet-cohort-v1",
        "graduation-flow__wallet-cohort-v1",
        FastBaselineKind::GraduationFlow,
        FastBaselineKind::WalletCohort,
        FastDeterministicEntryPolicyRef::GraduationFlow(&graduation),
        FastDeterministicManagerPolicyRef::WalletCohort(&wallet),
    )?;
    push_candidate(
        &mut candidates,
        "fl9-baseline-impulse-scalp-longer-runner-v1",
        "impulse-scalp__longer-runner-v1",
        FastBaselineKind::ImpulseScalp,
        FastBaselineKind::LongerRunner,
        FastDeterministicEntryPolicyRef::ImpulseScalp(&impulse),
        FastDeterministicManagerPolicyRef::LongerRunner(&longer),
    )?;
    push_candidate(
        &mut candidates,
        "fl9-baseline-impulse-scalp-wallet-cohort-v1",
        "impulse-scalp__wallet-cohort-v1",
        FastBaselineKind::ImpulseScalp,
        FastBaselineKind::WalletCohort,
        FastDeterministicEntryPolicyRef::ImpulseScalp(&impulse),
        FastDeterministicManagerPolicyRef::WalletCohort(&wallet),
    )?;
    push_candidate(
        &mut candidates,
        "fl9-baseline-micro-pullback-longer-runner-v1",
        "micro-pullback__longer-runner-v1",
        FastBaselineKind::MicroPullback,
        FastBaselineKind::LongerRunner,
        FastDeterministicEntryPolicyRef::MicroPullback(&micro),
        FastDeterministicManagerPolicyRef::LongerRunner(&longer),
    )?;
    push_candidate(
        &mut candidates,
        "fl9-baseline-micro-pullback-wallet-cohort-v1",
        "micro-pullback__wallet-cohort-v1",
        FastBaselineKind::MicroPullback,
        FastBaselineKind::WalletCohort,
        FastDeterministicEntryPolicyRef::MicroPullback(&micro),
        FastDeterministicManagerPolicyRef::WalletCohort(&wallet),
    )?;
    push_candidate(
        &mut candidates,
        "fl9-baseline-pre-graduation-longer-runner-v1",
        "pre-graduation__longer-runner-v1",
        FastBaselineKind::PreGraduation,
        FastBaselineKind::LongerRunner,
        FastDeterministicEntryPolicyRef::PreGraduation(&pre),
        FastDeterministicManagerPolicyRef::LongerRunner(&longer),
    )?;
    push_candidate(
        &mut candidates,
        "fl9-baseline-pre-graduation-wallet-cohort-v1",
        "pre-graduation__wallet-cohort-v1",
        FastBaselineKind::PreGraduation,
        FastBaselineKind::WalletCohort,
        FastDeterministicEntryPolicyRef::PreGraduation(&pre),
        FastDeterministicManagerPolicyRef::WalletCohort(&wallet),
    )?;

    let mut catalog = FastDeterministicComparisonCatalogWire {
        schema_name: FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME.to_owned(),
        schema_version: FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION,
        catalog_version: FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION.to_owned(),
        candidates,
        catalog_fingerprint_sha256: "0".repeat(64),
    };
    validate_catalog(&catalog)?;
    catalog.catalog_fingerprint_sha256 = catalog_fingerprint_sha256(&catalog)?;
    Ok(catalog)
}

pub fn encode_fast_deterministic_comparison_catalog_json(
    catalog: &FastDeterministicComparisonCatalogWire,
) -> Result<String, FastDeterministicComparisonCatalogError> {
    validate_sha256(
        "catalog_fingerprint_sha256",
        &catalog.catalog_fingerprint_sha256,
    )?;
    if catalog_fingerprint_sha256(catalog)? != catalog.catalog_fingerprint_sha256 {
        return Err(FastDeterministicComparisonCatalogError::FingerprintMismatch);
    }
    validate_catalog(catalog)?;
    let value = serde_json::to_value(catalog)
        .map_err(|error| FastDeterministicComparisonCatalogError::Json(error.to_string()))?;
    serde_json::to_string(&value)
        .map_err(|error| FastDeterministicComparisonCatalogError::Json(error.to_string()))
}

pub fn decode_fast_deterministic_comparison_catalog_json(
    input: &str,
) -> Result<FastDeterministicComparisonCatalogWire, FastDeterministicComparisonCatalogError> {
    if input.is_empty() {
        return invalid("JSON payload must be non-empty");
    }
    let catalog: FastDeterministicComparisonCatalogWire = serde_json::from_str(input)
        .map_err(|error| FastDeterministicComparisonCatalogError::Json(error.to_string()))?;
    validate_sha256(
        "catalog_fingerprint_sha256",
        &catalog.catalog_fingerprint_sha256,
    )?;
    if catalog_fingerprint_sha256(&catalog)? != catalog.catalog_fingerprint_sha256 {
        return Err(FastDeterministicComparisonCatalogError::FingerprintMismatch);
    }
    validate_catalog(&catalog)?;
    Ok(catalog)
}

fn push_candidate(
    candidates: &mut Vec<FastDeterministicCandidateManifestWire>,
    candidate_version: &str,
    strategy_version: &str,
    entry_kind: FastBaselineKind,
    manager_kind: FastBaselineKind,
    entry_policy: FastDeterministicEntryPolicyRef<'_>,
    manager_policy: FastDeterministicManagerPolicyRef<'_>,
) -> Result<(), FastDeterministicComparisonCatalogError> {
    let lifecycle = FastDeterministicLifecyclePolicy {
        version: FAST_DETERMINISTIC_LIFECYCLE_VERSION,
        entry_baseline_kind: entry_kind,
        manager_baseline_kind: manager_kind,
        entry_target_exposure_fraction: 0.8,
        reduce_remaining_fraction: 0.5,
    };
    let candidate = build_fast_deterministic_candidate_manifest(
        candidate_version,
        strategy_version,
        &lifecycle,
        entry_policy,
        manager_policy,
    )
    .map_err(|error| {
        FastDeterministicComparisonCatalogError::CandidateManifest(error.to_string())
    })?;
    candidates.push(candidate);
    Ok(())
}

fn validate_catalog(
    catalog: &FastDeterministicComparisonCatalogWire,
) -> Result<(), FastDeterministicComparisonCatalogError> {
    if catalog.schema_name != FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME {
        return invalid("schema_name is incompatible");
    }
    if catalog.schema_version != FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION {
        return invalid("schema_version is incompatible");
    }
    if catalog.catalog_version != FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION {
        return invalid("catalog_version is incompatible");
    }
    if catalog.candidates.len() != 8 {
        return invalid("catalog must contain exactly eight candidates");
    }

    let versions = catalog
        .candidates
        .iter()
        .map(|candidate| candidate.candidate_version.as_str())
        .collect::<Vec<_>>();
    if !versions.windows(2).all(|pair| pair[0] < pair[1]) {
        return invalid("candidate versions must be unique and lexical");
    }

    let fingerprints = catalog
        .candidates
        .iter()
        .map(|candidate| candidate.candidate_fingerprint_sha256.as_str())
        .collect::<BTreeSet<_>>();
    if fingerprints.len() != catalog.candidates.len() {
        return invalid("candidate fingerprints must be unique");
    }

    let expected_versions = [
        "fl9-baseline-graduation-flow-longer-runner-v1",
        "fl9-baseline-graduation-flow-wallet-cohort-v1",
        "fl9-baseline-impulse-scalp-longer-runner-v1",
        "fl9-baseline-impulse-scalp-wallet-cohort-v1",
        "fl9-baseline-micro-pullback-longer-runner-v1",
        "fl9-baseline-micro-pullback-wallet-cohort-v1",
        "fl9-baseline-pre-graduation-longer-runner-v1",
        "fl9-baseline-pre-graduation-wallet-cohort-v1",
    ];
    if versions.as_slice() != expected_versions {
        return invalid("candidate version set does not match catalog v1");
    }

    let mut pairs = BTreeSet::new();
    for candidate in &catalog.candidates {
        encode_fast_deterministic_candidate_manifest_json(candidate).map_err(|error| {
            FastDeterministicComparisonCatalogError::CandidateManifest(error.to_string())
        })?;
        pairs.insert((
            candidate.lifecycle_policy.entry_baseline_kind.as_str(),
            candidate.lifecycle_policy.manager_baseline_kind.as_str(),
        ));
    }
    let expected_pairs = [
        ("GRADUATION_FLOW", "LONGER_RUNNER"),
        ("GRADUATION_FLOW", "WALLET_COHORT"),
        ("IMPULSE_SCALP", "LONGER_RUNNER"),
        ("IMPULSE_SCALP", "WALLET_COHORT"),
        ("MICRO_PULLBACK", "LONGER_RUNNER"),
        ("MICRO_PULLBACK", "WALLET_COHORT"),
        ("PRE_GRADUATION", "LONGER_RUNNER"),
        ("PRE_GRADUATION", "WALLET_COHORT"),
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    if pairs != expected_pairs {
        return invalid("catalog must contain the exact four-by-two family product");
    }

    Ok(())
}

fn catalog_fingerprint_sha256(
    catalog: &FastDeterministicComparisonCatalogWire,
) -> Result<String, FastDeterministicComparisonCatalogError> {
    let mut value = serde_json::to_value(catalog)
        .map_err(|error| FastDeterministicComparisonCatalogError::Json(error.to_string()))?;
    let object = value.as_object_mut().ok_or_else(|| {
        FastDeterministicComparisonCatalogError::Invalid(
            "catalog serialization must be an object".to_owned(),
        )
    })?;
    object.remove("catalog_fingerprint_sha256");
    let payload = serde_json::to_vec(&value)
        .map_err(|error| FastDeterministicComparisonCatalogError::Json(error.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(payload)))
}

fn validate_sha256(
    name: &str,
    value: &str,
) -> Result<(), FastDeterministicComparisonCatalogError> {
    if value.len() != 64
        || value.bytes().any(|byte| {
            !byte.is_ascii_hexdigit() || byte.is_ascii_uppercase()
        })
    {
        return invalid(&format!("{name} must be lowercase SHA-256 hex"));
    }
    Ok(())
}

fn invalid<T>(
    message: &str,
) -> Result<T, FastDeterministicComparisonCatalogError> {
    Err(FastDeterministicComparisonCatalogError::Invalid(
        message.to_owned(),
    ))
}

fn impulse_policy() -> ImpulseScalpPolicy {
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

fn micro_pullback_policy() -> MicroPullbackPolicy {
    MicroPullbackPolicy {
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
    }
}

fn pre_graduation_policy() -> PreGraduationPolicy {
    PreGraduationPolicy {
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
    }
}

fn graduation_flow_policy() -> GraduationFlowPolicy {
    GraduationFlowPolicy {
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
    }
}

fn wallet_cohort_policy() -> WalletCohortPolicy {
    WalletCohortPolicy {
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
    }
}

fn longer_runner_policy() -> LongerRunnerPolicy {
    LongerRunnerPolicy {
        version: LONGER_RUNNER_BASELINE_VERSION,
        downside_risk_weight: 1.0,
        min_risk_adjusted_continuation_bps_for_hold: 100.0,
        max_risk_adjusted_continuation_bps_for_sell: -100.0,
    }
}
