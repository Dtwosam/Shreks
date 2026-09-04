use std::{collections::BTreeSet, error::Error, fmt};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use shreks_core::{
    FastBaselineKind, GraduationFlowPolicy, ImpulseScalpPolicy, LongerRunnerPolicy,
    MicroPullbackPolicy, PreGraduationPolicy, WalletCohortPolicy,
};

use crate::{
    FastDeterministicLifecyclePolicy, FastDeterministicLifecyclePolicyWire,
    FAST_DETERMINISTIC_LIFECYCLE_VERSION,
};

pub const FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME: &str =
    "shreks.fast_deterministic_candidate_manifest";
pub const FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION: u16 = 1;
pub const FAST_DETERMINISTIC_CANDIDATE_STRATEGY_FAMILY: &str =
    "fast_deterministic_lifecycle";

#[derive(Debug, Clone, Copy)]
pub enum FastDeterministicEntryPolicyRef<'a> {
    ImpulseScalp(&'a ImpulseScalpPolicy),
    MicroPullback(&'a MicroPullbackPolicy),
    PreGraduation(&'a PreGraduationPolicy),
    GraduationFlow(&'a GraduationFlowPolicy),
}

impl FastDeterministicEntryPolicyRef<'_> {
    pub const fn baseline_kind(self) -> FastBaselineKind {
        match self {
            Self::ImpulseScalp(_) => FastBaselineKind::ImpulseScalp,
            Self::MicroPullback(_) => FastBaselineKind::MicroPullback,
            Self::PreGraduation(_) => FastBaselineKind::PreGraduation,
            Self::GraduationFlow(_) => FastBaselineKind::GraduationFlow,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub enum FastDeterministicManagerPolicyRef<'a> {
    WalletCohort(&'a WalletCohortPolicy),
    LongerRunner(&'a LongerRunnerPolicy),
}

impl FastDeterministicManagerPolicyRef<'_> {
    pub const fn baseline_kind(self) -> FastBaselineKind {
        match self {
            Self::WalletCohort(_) => FastBaselineKind::WalletCohort,
            Self::LongerRunner(_) => FastBaselineKind::LongerRunner,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicComponentPolicyWire {
    pub kind: String,
    pub parameters: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicCandidateManifestWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub candidate_version: String,
    pub strategy_family: String,
    pub strategy_version: String,
    pub lifecycle_policy: FastDeterministicLifecyclePolicyWire,
    pub entry_policy: FastDeterministicComponentPolicyWire,
    pub manager_policy: FastDeterministicComponentPolicyWire,
    pub candidate_fingerprint_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastDeterministicCandidateManifestError {
    Json(String),
    Invalid(String),
    FingerprintMismatch,
}

impl fmt::Display for FastDeterministicCandidateManifestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(message) => {
                write!(formatter, "deterministic candidate manifest JSON error: {message}")
            }
            Self::Invalid(message) => {
                write!(formatter, "invalid deterministic candidate manifest: {message}")
            }
            Self::FingerprintMismatch => {
                formatter.write_str("deterministic candidate manifest fingerprint mismatch")
            }
        }
    }
}

impl Error for FastDeterministicCandidateManifestError {}

pub fn build_fast_deterministic_candidate_manifest(
    candidate_version: &str,
    strategy_version: &str,
    lifecycle_policy: &FastDeterministicLifecyclePolicy,
    entry_policy: FastDeterministicEntryPolicyRef<'_>,
    manager_policy: FastDeterministicManagerPolicyRef<'_>,
) -> Result<FastDeterministicCandidateManifestWire, FastDeterministicCandidateManifestError> {
    require_non_empty("candidate_version", candidate_version)?;
    require_non_empty("strategy_version", strategy_version)?;
    validate_lifecycle_source(lifecycle_policy)?;

    if entry_policy.baseline_kind() != lifecycle_policy.entry_baseline_kind {
        return invalid("entry policy kind does not match lifecycle entry kind");
    }
    if manager_policy.baseline_kind() != lifecycle_policy.manager_baseline_kind {
        return invalid("manager policy kind does not match lifecycle manager kind");
    }

    let lifecycle_wire = FastDeterministicLifecyclePolicyWire {
        version: lifecycle_policy.version,
        entry_baseline_kind: kind_str(lifecycle_policy.entry_baseline_kind).to_owned(),
        manager_baseline_kind: kind_str(lifecycle_policy.manager_baseline_kind).to_owned(),
        entry_target_exposure_fraction: lifecycle_policy.entry_target_exposure_fraction,
        reduce_remaining_fraction: lifecycle_policy.reduce_remaining_fraction,
    };

    let entry_policy = entry_policy_wire(entry_policy);
    let manager_policy = manager_policy_wire(manager_policy);

    let mut manifest = FastDeterministicCandidateManifestWire {
        schema_name: FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME.to_owned(),
        schema_version: FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION,
        candidate_version: candidate_version.to_owned(),
        strategy_family: FAST_DETERMINISTIC_CANDIDATE_STRATEGY_FAMILY.to_owned(),
        strategy_version: strategy_version.to_owned(),
        lifecycle_policy: lifecycle_wire,
        entry_policy,
        manager_policy,
        candidate_fingerprint_sha256: "0".repeat(64),
    };
    validate_manifest_semantics(&manifest)?;
    manifest.candidate_fingerprint_sha256 = candidate_fingerprint_sha256(&manifest)?;
    Ok(manifest)
}

pub fn encode_fast_deterministic_candidate_manifest_json(
    manifest: &FastDeterministicCandidateManifestWire,
) -> Result<String, FastDeterministicCandidateManifestError> {
    validate_sha256(
        "candidate_fingerprint_sha256",
        &manifest.candidate_fingerprint_sha256,
    )?;
    if candidate_fingerprint_sha256(manifest)? != manifest.candidate_fingerprint_sha256 {
        return Err(FastDeterministicCandidateManifestError::FingerprintMismatch);
    }
    validate_manifest_semantics(manifest)?;
    let value = serde_json::to_value(manifest)
        .map_err(|error| FastDeterministicCandidateManifestError::Json(error.to_string()))?;
    serde_json::to_string(&value)
        .map_err(|error| FastDeterministicCandidateManifestError::Json(error.to_string()))
}

pub fn decode_fast_deterministic_candidate_manifest_json(
    input: &str,
) -> Result<FastDeterministicCandidateManifestWire, FastDeterministicCandidateManifestError> {
    if input.is_empty() {
        return invalid("JSON payload must be non-empty");
    }
    let manifest: FastDeterministicCandidateManifestWire = serde_json::from_str(input)
        .map_err(|error| FastDeterministicCandidateManifestError::Json(error.to_string()))?;
    validate_sha256(
        "candidate_fingerprint_sha256",
        &manifest.candidate_fingerprint_sha256,
    )?;
    if candidate_fingerprint_sha256(&manifest)? != manifest.candidate_fingerprint_sha256 {
        return Err(FastDeterministicCandidateManifestError::FingerprintMismatch);
    }
    validate_manifest_semantics(&manifest)?;
    Ok(manifest)
}

fn validate_lifecycle_source(
    policy: &FastDeterministicLifecyclePolicy,
) -> Result<(), FastDeterministicCandidateManifestError> {
    if policy.version != FAST_DETERMINISTIC_LIFECYCLE_VERSION {
        return invalid("lifecycle policy version is unsupported");
    }
    if !is_entry_kind(policy.entry_baseline_kind) {
        return invalid("lifecycle entry kind is not an FL6.1-FL6.4 family");
    }
    if !is_manager_kind(policy.manager_baseline_kind) {
        return invalid("lifecycle manager kind is not an FL6.5-FL6.6 family");
    }
    validate_fraction(
        "entry_target_exposure_fraction",
        policy.entry_target_exposure_fraction,
        false,
    )?;
    validate_fraction(
        "reduce_remaining_fraction",
        policy.reduce_remaining_fraction,
        true,
    )
}

fn validate_manifest_semantics(
    manifest: &FastDeterministicCandidateManifestWire,
) -> Result<(), FastDeterministicCandidateManifestError> {
    if manifest.schema_name != FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME {
        return invalid("schema_name is incompatible");
    }
    if manifest.schema_version != FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION {
        return invalid("schema_version is incompatible");
    }
    require_non_empty("candidate_version", &manifest.candidate_version)?;
    if manifest.strategy_family != FAST_DETERMINISTIC_CANDIDATE_STRATEGY_FAMILY {
        return invalid("strategy_family is incompatible");
    }
    require_non_empty("strategy_version", &manifest.strategy_version)?;

    if manifest.lifecycle_policy.version != FAST_DETERMINISTIC_LIFECYCLE_VERSION {
        return invalid("lifecycle policy version is unsupported");
    }
    let entry_kind = parse_kind(&manifest.lifecycle_policy.entry_baseline_kind)?;
    let manager_kind = parse_kind(&manifest.lifecycle_policy.manager_baseline_kind)?;
    if !is_entry_kind(entry_kind) {
        return invalid("lifecycle entry kind is not an FL6.1-FL6.4 family");
    }
    if !is_manager_kind(manager_kind) {
        return invalid("lifecycle manager kind is not an FL6.5-FL6.6 family");
    }
    validate_fraction(
        "entry_target_exposure_fraction",
        manifest.lifecycle_policy.entry_target_exposure_fraction,
        false,
    )?;
    validate_fraction(
        "reduce_remaining_fraction",
        manifest.lifecycle_policy.reduce_remaining_fraction,
        true,
    )?;

    let actual_entry_kind = parse_kind(&manifest.entry_policy.kind)?;
    if actual_entry_kind != entry_kind {
        return invalid("entry policy kind does not match lifecycle entry kind");
    }
    let actual_manager_kind = parse_kind(&manifest.manager_policy.kind)?;
    if actual_manager_kind != manager_kind {
        return invalid("manager policy kind does not match lifecycle manager kind");
    }

    validate_component_policy(&manifest.entry_policy)?;
    validate_component_policy(&manifest.manager_policy)?;
    Ok(())
}

fn entry_policy_wire(
    policy: FastDeterministicEntryPolicyRef<'_>,
) -> FastDeterministicComponentPolicyWire {
    match policy {
        FastDeterministicEntryPolicyRef::ImpulseScalp(value) => component(
            FastBaselineKind::ImpulseScalp,
            json!({
                "version": value.version,
                "signal_window_ms": value.signal_window_ms,
                "context_window_ms": value.context_window_ms,
                "min_buy_count": value.min_buy_count,
                "min_unique_buy_actors": value.min_unique_buy_actors,
                "min_count_imbalance": value.min_count_imbalance,
                "min_quote_flow_imbalance": value.min_quote_flow_imbalance,
                "min_quote_flow_velocity_per_second": value.min_quote_flow_velocity_per_second,
                "min_quote_flow_acceleration_per_second2": value.min_quote_flow_acceleration_per_second2,
                "min_velocity_expansion_ratio": value.min_velocity_expansion_ratio,
                "min_recovery_from_local_low": value.min_recovery_from_local_low,
                "max_drawdown_from_local_high": value.max_drawdown_from_local_high,
            }),
        ),
        FastDeterministicEntryPolicyRef::MicroPullback(value) => component(
            FastBaselineKind::MicroPullback,
            json!({
                "version": value.version,
                "reclaim_window_ms": value.reclaim_window_ms,
                "structure_window_ms": value.structure_window_ms,
                "min_impulse_move_fraction": value.min_impulse_move_fraction,
                "min_pullback_depth_fraction": value.min_pullback_depth_fraction,
                "max_pullback_depth_fraction": value.max_pullback_depth_fraction,
                "min_reclaim_fraction": value.min_reclaim_fraction,
                "min_reclaim_buy_count": value.min_reclaim_buy_count,
                "min_reclaim_unique_buy_actors": value.min_reclaim_unique_buy_actors,
                "min_reclaim_buy_arrival_rate_per_second": value.min_reclaim_buy_arrival_rate_per_second,
                "max_reclaim_sell_arrival_rate_per_second": value.max_reclaim_sell_arrival_rate_per_second,
                "min_reclaim_count_imbalance": value.min_reclaim_count_imbalance,
                "min_reclaim_quote_flow_imbalance": value.min_reclaim_quote_flow_imbalance,
                "min_reclaim_quote_flow_velocity_per_second": value.min_reclaim_quote_flow_velocity_per_second,
                "min_reclaim_quote_flow_acceleration_per_second2": value.min_reclaim_quote_flow_acceleration_per_second2,
            }),
        ),
        FastDeterministicEntryPolicyRef::PreGraduation(value) => component(
            FastBaselineKind::PreGraduation,
            json!({
                "version": value.version,
                "signal_window_ms": value.signal_window_ms,
                "context_window_ms": value.context_window_ms,
                "graduation_target_real_base_reserve_raw": value.graduation_target_real_base_reserve_raw,
                "maximum_pre_graduation_real_base_reserve_raw": value.maximum_pre_graduation_real_base_reserve_raw,
                "min_buy_count": value.min_buy_count,
                "min_unique_buy_actors": value.min_unique_buy_actors,
                "min_buy_arrival_rate_per_second": value.min_buy_arrival_rate_per_second,
                "min_count_imbalance": value.min_count_imbalance,
                "min_quote_flow_imbalance": value.min_quote_flow_imbalance,
                "min_quote_flow_velocity_per_second": value.min_quote_flow_velocity_per_second,
                "min_quote_flow_acceleration_per_second2": value.min_quote_flow_acceleration_per_second2,
                "min_velocity_expansion_ratio": value.min_velocity_expansion_ratio,
                "min_buy_participation_of_remaining": value.min_buy_participation_of_remaining,
            }),
        ),
        FastDeterministicEntryPolicyRef::GraduationFlow(value) => component(
            FastBaselineKind::GraduationFlow,
            json!({
                "version": value.version,
                "flow_window_ms": value.flow_window_ms,
                "max_graduation_age_ms": value.max_graduation_age_ms,
                "min_pre_buy_count": value.min_pre_buy_count,
                "min_pre_quote_flow_velocity_per_second": value.min_pre_quote_flow_velocity_per_second,
                "min_post_buy_count": value.min_post_buy_count,
                "min_post_unique_buy_actors": value.min_post_unique_buy_actors,
                "min_post_buy_arrival_rate_per_second": value.min_post_buy_arrival_rate_per_second,
                "max_post_sell_arrival_rate_per_second": value.max_post_sell_arrival_rate_per_second,
                "min_post_count_imbalance": value.min_post_count_imbalance,
                "min_post_quote_flow_imbalance": value.min_post_quote_flow_imbalance,
                "min_post_quote_flow_velocity_per_second": value.min_post_quote_flow_velocity_per_second,
                "min_post_quote_flow_acceleration_per_second2": value.min_post_quote_flow_acceleration_per_second2,
                "min_post_to_pre_velocity_ratio": value.min_post_to_pre_velocity_ratio,
            }),
        ),
    }
}

fn manager_policy_wire(
    policy: FastDeterministicManagerPolicyRef<'_>,
) -> FastDeterministicComponentPolicyWire {
    match policy {
        FastDeterministicManagerPolicyRef::WalletCohort(value) => component(
            FastBaselineKind::WalletCohort,
            json!({
                "version": value.version,
                "min_support_wallet_count_for_ride": value.min_support_wallet_count_for_ride,
                "min_confidence_weighted_support_for_ride": value.min_confidence_weighted_support_for_ride,
                "min_independent_support_wallet_count_for_ride": value.min_independent_support_wallet_count_for_ride,
                "min_hold_horizon_wallet_weight_for_ride": value.min_hold_horizon_wallet_weight_for_ride,
                "reduce_after_median_hold_ratio": value.reduce_after_median_hold_ratio,
                "min_confidence_weighted_exit_for_reduce": value.min_confidence_weighted_exit_for_reduce,
                "min_exit_pressure_ratio_for_reduce": value.min_exit_pressure_ratio_for_reduce,
                "min_confidence_weighted_exit_for_sell": value.min_confidence_weighted_exit_for_sell,
                "min_exit_pressure_ratio_for_sell": value.min_exit_pressure_ratio_for_sell,
                "min_independent_exit_wallet_count_for_sell": value.min_independent_exit_wallet_count_for_sell,
            }),
        ),
        FastDeterministicManagerPolicyRef::LongerRunner(value) => component(
            FastBaselineKind::LongerRunner,
            json!({
                "version": value.version,
                "downside_risk_weight": value.downside_risk_weight,
                "min_risk_adjusted_continuation_bps_for_hold": value.min_risk_adjusted_continuation_bps_for_hold,
                "max_risk_adjusted_continuation_bps_for_sell": value.max_risk_adjusted_continuation_bps_for_sell,
            }),
        ),
    }
}

fn component(kind: FastBaselineKind, parameters: Value) -> FastDeterministicComponentPolicyWire {
    FastDeterministicComponentPolicyWire {
        kind: kind_str(kind).to_owned(),
        parameters,
    }
}

fn validate_component_policy(
    policy: &FastDeterministicComponentPolicyWire,
) -> Result<(), FastDeterministicCandidateManifestError> {
    let kind = parse_kind(&policy.kind)?;
    let object = policy
        .parameters
        .as_object()
        .ok_or_else(|| FastDeterministicCandidateManifestError::Invalid(
            "component policy parameters must be an object".to_owned(),
        ))?;
    require_exact_keys(object.keys().map(String::as_str), expected_keys(kind))?;

    let version = object
        .get("version")
        .and_then(Value::as_u64)
        .ok_or_else(|| FastDeterministicCandidateManifestError::Invalid(
            "component policy version must be a positive integer".to_owned(),
        ))?;
    if version != u64::from(kind.baseline_version()) {
        return invalid("component policy version does not match sealed FL6 baseline version");
    }

    for (name, value) in object {
        if name == "version" {
            continue;
        }
        match value {
            Value::Number(number) => {
                if let Some(float) = number.as_f64() {
                    if !float.is_finite() {
                        return invalid("component policy numeric values must be finite");
                    }
                } else if number.as_u64().is_none() && number.as_i64().is_none() {
                    return invalid("component policy numeric value is unsupported");
                }
            }
            _ => return invalid("component policy parameters must contain only numeric values"),
        }
    }
    Ok(())
}

fn expected_keys(kind: FastBaselineKind) -> &'static [&'static str] {
    match kind {
        FastBaselineKind::ImpulseScalp => &[
            "version",
            "signal_window_ms",
            "context_window_ms",
            "min_buy_count",
            "min_unique_buy_actors",
            "min_count_imbalance",
            "min_quote_flow_imbalance",
            "min_quote_flow_velocity_per_second",
            "min_quote_flow_acceleration_per_second2",
            "min_velocity_expansion_ratio",
            "min_recovery_from_local_low",
            "max_drawdown_from_local_high",
        ],
        FastBaselineKind::MicroPullback => &[
            "version",
            "reclaim_window_ms",
            "structure_window_ms",
            "min_impulse_move_fraction",
            "min_pullback_depth_fraction",
            "max_pullback_depth_fraction",
            "min_reclaim_fraction",
            "min_reclaim_buy_count",
            "min_reclaim_unique_buy_actors",
            "min_reclaim_buy_arrival_rate_per_second",
            "max_reclaim_sell_arrival_rate_per_second",
            "min_reclaim_count_imbalance",
            "min_reclaim_quote_flow_imbalance",
            "min_reclaim_quote_flow_velocity_per_second",
            "min_reclaim_quote_flow_acceleration_per_second2",
        ],
        FastBaselineKind::PreGraduation => &[
            "version",
            "signal_window_ms",
            "context_window_ms",
            "graduation_target_real_base_reserve_raw",
            "maximum_pre_graduation_real_base_reserve_raw",
            "min_buy_count",
            "min_unique_buy_actors",
            "min_buy_arrival_rate_per_second",
            "min_count_imbalance",
            "min_quote_flow_imbalance",
            "min_quote_flow_velocity_per_second",
            "min_quote_flow_acceleration_per_second2",
            "min_velocity_expansion_ratio",
            "min_buy_participation_of_remaining",
        ],
        FastBaselineKind::GraduationFlow => &[
            "version",
            "flow_window_ms",
            "max_graduation_age_ms",
            "min_pre_buy_count",
            "min_pre_quote_flow_velocity_per_second",
            "min_post_buy_count",
            "min_post_unique_buy_actors",
            "min_post_buy_arrival_rate_per_second",
            "max_post_sell_arrival_rate_per_second",
            "min_post_count_imbalance",
            "min_post_quote_flow_imbalance",
            "min_post_quote_flow_velocity_per_second",
            "min_post_quote_flow_acceleration_per_second2",
            "min_post_to_pre_velocity_ratio",
        ],
        FastBaselineKind::WalletCohort => &[
            "version",
            "min_support_wallet_count_for_ride",
            "min_confidence_weighted_support_for_ride",
            "min_independent_support_wallet_count_for_ride",
            "min_hold_horizon_wallet_weight_for_ride",
            "reduce_after_median_hold_ratio",
            "min_confidence_weighted_exit_for_reduce",
            "min_exit_pressure_ratio_for_reduce",
            "min_confidence_weighted_exit_for_sell",
            "min_exit_pressure_ratio_for_sell",
            "min_independent_exit_wallet_count_for_sell",
        ],
        FastBaselineKind::LongerRunner => &[
            "version",
            "downside_risk_weight",
            "min_risk_adjusted_continuation_bps_for_hold",
            "max_risk_adjusted_continuation_bps_for_sell",
        ],
    }
}

fn require_exact_keys<'a>(
    actual: impl Iterator<Item = &'a str>,
    expected: &[&str],
) -> Result<(), FastDeterministicCandidateManifestError> {
    let actual = actual.collect::<BTreeSet<_>>();
    let expected = expected.iter().copied().collect::<BTreeSet<_>>();
    if actual != expected {
        return invalid("component policy parameters contain unknown or missing fields");
    }
    Ok(())
}

fn candidate_fingerprint_sha256(
    manifest: &FastDeterministicCandidateManifestWire,
) -> Result<String, FastDeterministicCandidateManifestError> {
    let mut value = serde_json::to_value(manifest)
        .map_err(|error| FastDeterministicCandidateManifestError::Json(error.to_string()))?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| FastDeterministicCandidateManifestError::Invalid(
            "manifest serialization must be an object".to_owned(),
        ))?;
    object.remove("candidate_fingerprint_sha256");
    let payload = serde_json::to_vec(&value)
        .map_err(|error| FastDeterministicCandidateManifestError::Json(error.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(payload)))
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

fn parse_kind(value: &str) -> Result<FastBaselineKind, FastDeterministicCandidateManifestError> {
    match value {
        "IMPULSE_SCALP" => Ok(FastBaselineKind::ImpulseScalp),
        "MICRO_PULLBACK" => Ok(FastBaselineKind::MicroPullback),
        "PRE_GRADUATION" => Ok(FastBaselineKind::PreGraduation),
        "GRADUATION_FLOW" => Ok(FastBaselineKind::GraduationFlow),
        "WALLET_COHORT" => Ok(FastBaselineKind::WalletCohort),
        "LONGER_RUNNER" => Ok(FastBaselineKind::LongerRunner),
        _ => invalid("baseline kind is unsupported"),
    }
}

fn is_entry_kind(kind: FastBaselineKind) -> bool {
    matches!(
        kind,
        FastBaselineKind::ImpulseScalp
            | FastBaselineKind::MicroPullback
            | FastBaselineKind::PreGraduation
            | FastBaselineKind::GraduationFlow
    )
}

fn is_manager_kind(kind: FastBaselineKind) -> bool {
    matches!(kind, FastBaselineKind::WalletCohort | FastBaselineKind::LongerRunner)
}

fn validate_fraction(
    name: &str,
    value: f64,
    upper_open: bool,
) -> Result<(), FastDeterministicCandidateManifestError> {
    let upper_ok = if upper_open { value < 1.0 } else { value <= 1.0 };
    if !value.is_finite() || value <= 0.0 || !upper_ok {
        return invalid(&format!("{name} is outside its permitted interval"));
    }
    Ok(())
}

fn require_non_empty(
    name: &str,
    value: &str,
) -> Result<(), FastDeterministicCandidateManifestError> {
    if value.trim().is_empty() {
        return invalid(&format!("{name} must be non-empty"));
    }
    Ok(())
}

fn validate_sha256(
    name: &str,
    value: &str,
) -> Result<(), FastDeterministicCandidateManifestError> {
    if value.len() != 64
        || value != value.to_ascii_lowercase()
        || value.bytes().any(|byte| !matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    {
        return invalid(&format!("{name} must be lowercase SHA-256 hex"));
    }
    Ok(())
}

fn invalid<T>(message: &str) -> Result<T, FastDeterministicCandidateManifestError> {
    Err(FastDeterministicCandidateManifestError::Invalid(message.to_owned()))
}
