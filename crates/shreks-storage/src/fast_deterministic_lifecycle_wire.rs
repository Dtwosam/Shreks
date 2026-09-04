use std::{
    collections::{HashMap, HashSet},
    error::Error,
    fmt,
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use shreks_core::{FastBaselineKind, FastLaneAction};

use crate::{
    FastDeterministicLifecycleBatchAssessment, FastDeterministicLifecycleDecision,
    FastDeterministicLifecyclePolicy, FAST_DETERMINISTIC_LIFECYCLE_VERSION,
};

pub const FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME: &str =
    "shreks.fast_deterministic_lifecycle_results";
pub const FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicLifecyclePolicyWire {
    pub version: u16,
    pub entry_baseline_kind: String,
    pub manager_baseline_kind: String,
    pub entry_target_exposure_fraction: f64,
    pub reduce_remaining_fraction: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicLifecycleDecisionWire {
    pub source_event_id: String,
    pub market_key: String,
    pub source_sequence: u64,
    pub as_of_unix_ms: i64,
    pub posture: String,
    pub component_kind: String,
    pub component_version: u16,
    pub action: String,
    pub current_exposure_fraction: Option<f64>,
    pub target_exposure_fraction: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicLifecycleResultsWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub policy: FastDeterministicLifecyclePolicyWire,
    pub decisions: Vec<FastDeterministicLifecycleDecisionWire>,
    pub batch_fingerprint_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastDeterministicLifecycleWireError {
    Json(String),
    Invalid(String),
    FingerprintMismatch,
}

impl fmt::Display for FastDeterministicLifecycleWireError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(message) => write!(formatter, "deterministic lifecycle wire JSON error: {message}"),
            Self::Invalid(message) => write!(formatter, "invalid deterministic lifecycle wire: {message}"),
            Self::FingerprintMismatch => {
                formatter.write_str("deterministic lifecycle wire fingerprint mismatch")
            }
        }
    }
}

impl Error for FastDeterministicLifecycleWireError {}

pub fn fast_deterministic_lifecycle_to_wire(
    batch: &FastDeterministicLifecycleBatchAssessment,
) -> Result<FastDeterministicLifecycleResultsWire, FastDeterministicLifecycleWireError> {
    if batch.version != FAST_DETERMINISTIC_LIFECYCLE_VERSION {
        return invalid("lifecycle batch version is unsupported");
    }
    validate_source_policy(&batch.policy)?;
    if batch.decisions.is_empty() {
        return invalid("lifecycle batch decisions cannot be empty");
    }

    let policy = FastDeterministicLifecyclePolicyWire {
        version: batch.policy.version,
        entry_baseline_kind: baseline_kind_str(batch.policy.entry_baseline_kind).to_owned(),
        manager_baseline_kind: baseline_kind_str(batch.policy.manager_baseline_kind).to_owned(),
        entry_target_exposure_fraction: batch.policy.entry_target_exposure_fraction,
        reduce_remaining_fraction: batch.policy.reduce_remaining_fraction,
    };

    let mut decisions = Vec::with_capacity(batch.decisions.len());
    for decision in &batch.decisions {
        validate_source_decision(decision)?;
        decisions.push(FastDeterministicLifecycleDecisionWire {
            source_event_id: decision.source_event_id.clone(),
            market_key: decision.market_key.clone(),
            source_sequence: decision.source_sequence,
            as_of_unix_ms: decision.as_of_unix_ms,
            posture: if decision.current_exposure_fraction.is_some() {
                "OPEN".to_owned()
            } else {
                "FLAT".to_owned()
            },
            component_kind: baseline_kind_str(decision.component_kind).to_owned(),
            component_version: decision.component_version,
            action: decision.action.as_str().to_owned(),
            current_exposure_fraction: decision.current_exposure_fraction,
            target_exposure_fraction: decision.target_exposure_fraction,
        });
    }

    let mut results = FastDeterministicLifecycleResultsWire {
        schema_name: FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME.to_owned(),
        schema_version: FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION,
        policy,
        decisions,
        batch_fingerprint_sha256: "0".repeat(64),
    };
    validate_results_semantics(&results)?;
    results.batch_fingerprint_sha256 = results_fingerprint_sha256(&results)?;
    Ok(results)
}

pub fn encode_fast_deterministic_lifecycle_results_json(
    results: &FastDeterministicLifecycleResultsWire,
) -> Result<String, FastDeterministicLifecycleWireError> {
    validate_sha256(
        "batch_fingerprint_sha256",
        &results.batch_fingerprint_sha256,
    )?;
    if results_fingerprint_sha256(results)? != results.batch_fingerprint_sha256 {
        return Err(FastDeterministicLifecycleWireError::FingerprintMismatch);
    }
    validate_results_semantics(results)?;

    let value = serde_json::to_value(results)
        .map_err(|error| FastDeterministicLifecycleWireError::Json(error.to_string()))?;
    serde_json::to_string(&value)
        .map_err(|error| FastDeterministicLifecycleWireError::Json(error.to_string()))
}

pub fn decode_fast_deterministic_lifecycle_results_json(
    input: &str,
) -> Result<FastDeterministicLifecycleResultsWire, FastDeterministicLifecycleWireError> {
    if input.is_empty() {
        return invalid("JSON payload must be non-empty");
    }
    let results: FastDeterministicLifecycleResultsWire = serde_json::from_str(input)
        .map_err(|error| FastDeterministicLifecycleWireError::Json(error.to_string()))?;
    validate_sha256(
        "batch_fingerprint_sha256",
        &results.batch_fingerprint_sha256,
    )?;
    if results_fingerprint_sha256(&results)? != results.batch_fingerprint_sha256 {
        return Err(FastDeterministicLifecycleWireError::FingerprintMismatch);
    }
    validate_results_semantics(&results)?;
    Ok(results)
}

fn validate_source_policy(
    policy: &FastDeterministicLifecyclePolicy,
) -> Result<(), FastDeterministicLifecycleWireError> {
    if policy.version == 0 {
        return invalid("source lifecycle policy version must be positive");
    }
    if !is_entry_kind(policy.entry_baseline_kind) {
        return invalid("source lifecycle entry baseline kind is invalid");
    }
    if !is_manager_kind(policy.manager_baseline_kind) {
        return invalid("source lifecycle manager baseline kind is invalid");
    }
    validate_fraction(
        "source entry target exposure fraction",
        policy.entry_target_exposure_fraction,
        false,
    )?;
    validate_fraction(
        "source reduce remaining fraction",
        policy.reduce_remaining_fraction,
        true,
    )?;
    Ok(())
}

fn validate_source_decision(
    decision: &FastDeterministicLifecycleDecision,
) -> Result<(), FastDeterministicLifecycleWireError> {
    if decision.version != FAST_DETERMINISTIC_LIFECYCLE_VERSION {
        return invalid("source lifecycle decision version is unsupported");
    }
    if decision.component_kind != decision.component.baseline_kind {
        return invalid("source lifecycle component kind diverges from component assessment");
    }
    if decision.component_version != decision.component.baseline_version {
        return invalid("source lifecycle component version diverges from component assessment");
    }
    if decision.component.assessment.action() != Some(decision.action) {
        return invalid("source lifecycle action diverges from component assessment");
    }
    if decision.source_event_id != decision.component.source_event_id
        || decision.market_key != decision.component.market_key
        || decision.source_sequence != decision.component.source_sequence
        || decision.as_of_unix_ms != decision.component.as_of_unix_ms
    {
        return invalid("source lifecycle decision identity diverges from component assessment");
    }
    Ok(())
}

fn validate_results_semantics(
    results: &FastDeterministicLifecycleResultsWire,
) -> Result<(), FastDeterministicLifecycleWireError> {
    if results.schema_name != FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME {
        return invalid("schema_name is incompatible");
    }
    if results.schema_version != FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION {
        return invalid("schema_version is incompatible");
    }

    let entry_kind = parse_kind(&results.policy.entry_baseline_kind)?;
    let manager_kind = parse_kind(&results.policy.manager_baseline_kind)?;
    if results.policy.version == 0 {
        return invalid("policy version must be positive");
    }
    if !is_entry_kind(entry_kind) {
        return invalid("entry baseline kind must be FL6.1, FL6.2, FL6.3, or FL6.4");
    }
    if !is_manager_kind(manager_kind) {
        return invalid("manager baseline kind must be FL6.5 or FL6.6");
    }
    validate_fraction(
        "entry target exposure fraction",
        results.policy.entry_target_exposure_fraction,
        false,
    )?;
    validate_fraction(
        "reduce remaining fraction",
        results.policy.reduce_remaining_fraction,
        true,
    )?;

    if results.decisions.is_empty() {
        return invalid("decisions cannot be empty");
    }

    let mut ids = HashSet::<&str>::with_capacity(results.decisions.len());
    let mut latest_by_market = HashMap::<&str, (u64, i64)>::new();
    for decision in &results.decisions {
        require_non_empty("source_event_id", &decision.source_event_id)?;
        require_non_empty("market_key", &decision.market_key)?;
        if !ids.insert(decision.source_event_id.as_str()) {
            return invalid("duplicate source_event_id");
        }
        if decision.source_sequence == 0 {
            return invalid("source_sequence must be positive");
        }
        if decision.as_of_unix_ms < 0 {
            return invalid("as_of_unix_ms must be non-negative");
        }

        let component_kind = parse_kind(&decision.component_kind)?;
        if decision.component_version != component_kind.baseline_version() {
            return invalid("component_version does not match declared baseline kind");
        }
        if !decision.target_exposure_fraction.is_finite()
            || !(0.0..=1.0).contains(&decision.target_exposure_fraction)
        {
            return invalid("target exposure fraction must be finite and within [0, 1]");
        }

        match decision.posture.as_str() {
            "FLAT" => validate_flat_decision(
                decision,
                component_kind,
                entry_kind,
                results.policy.entry_target_exposure_fraction,
            )?,
            "OPEN" => validate_open_decision(
                decision,
                component_kind,
                manager_kind,
                results.policy.reduce_remaining_fraction,
            )?,
            _ => return invalid("posture must be FLAT or OPEN"),
        }

        if let Some((previous_sequence, previous_at)) =
            latest_by_market.get(decision.market_key.as_str()).copied()
        {
            if decision.source_sequence <= previous_sequence {
                return invalid("per-market source sequence must strictly increase");
            }
            if decision.as_of_unix_ms < previous_at {
                return invalid("per-market timestamp cannot move backward");
            }
        }
        latest_by_market.insert(
            decision.market_key.as_str(),
            (decision.source_sequence, decision.as_of_unix_ms),
        );
    }

    Ok(())
}

fn validate_flat_decision(
    decision: &FastDeterministicLifecycleDecisionWire,
    component_kind: FastBaselineKind,
    entry_kind: FastBaselineKind,
    entry_target: f64,
) -> Result<(), FastDeterministicLifecycleWireError> {
    if component_kind != entry_kind {
        return invalid("FLAT component kind does not match lifecycle entry baseline");
    }
    if decision.current_exposure_fraction.is_some() {
        return invalid("FLAT decision current exposure must be null");
    }
    match decision.action.as_str() {
        "BUY" => {
            if !nearly_equal(decision.target_exposure_fraction, entry_target) {
                return invalid("BUY target exposure does not match lifecycle entry target");
            }
        }
        "SKIP" => {
            if decision.target_exposure_fraction != 0.0 {
                return invalid("SKIP target exposure must be zero");
            }
        }
        _ => return invalid("FLAT action must be BUY or SKIP"),
    }
    Ok(())
}

fn validate_open_decision(
    decision: &FastDeterministicLifecycleDecisionWire,
    component_kind: FastBaselineKind,
    manager_kind: FastBaselineKind,
    reduce_remaining_fraction: f64,
) -> Result<(), FastDeterministicLifecycleWireError> {
    if component_kind != manager_kind {
        return invalid("OPEN component kind does not match lifecycle manager baseline");
    }
    let Some(current) = decision.current_exposure_fraction else {
        return invalid("OPEN decision current exposure is required");
    };
    if !current.is_finite() || current <= 0.0 || current > 1.0 {
        return invalid("OPEN current exposure must be finite and within (0, 1]");
    }

    match decision.action.as_str() {
        "HOLD" => {
            if !nearly_equal(decision.target_exposure_fraction, current) {
                return invalid("HOLD target exposure must equal current exposure");
            }
        }
        "REDUCE" => {
            let expected = current * reduce_remaining_fraction;
            if !expected.is_finite()
                || expected <= 0.0
                || expected >= current
                || !nearly_equal(decision.target_exposure_fraction, expected)
            {
                return invalid("REDUCE target exposure does not match lifecycle remaining fraction");
            }
        }
        "SELL" => {
            if decision.target_exposure_fraction != 0.0 {
                return invalid("SELL target exposure must be zero");
            }
        }
        _ => return invalid("OPEN action must be HOLD, REDUCE, or SELL"),
    }
    Ok(())
}

fn results_fingerprint_sha256(
    results: &FastDeterministicLifecycleResultsWire,
) -> Result<String, FastDeterministicLifecycleWireError> {
    let mut value = serde_json::to_value(results)
        .map_err(|error| FastDeterministicLifecycleWireError::Json(error.to_string()))?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| FastDeterministicLifecycleWireError::Invalid(
            "result serialization must be an object".to_owned(),
        ))?;
    object.remove("batch_fingerprint_sha256");
    let payload = serde_json::to_vec(&value)
        .map_err(|error| FastDeterministicLifecycleWireError::Json(error.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(payload)))
}

fn baseline_kind_str(kind: FastBaselineKind) -> &'static str {
    match kind {
        FastBaselineKind::ImpulseScalp => "IMPULSE_SCALP",
        FastBaselineKind::MicroPullback => "MICRO_PULLBACK",
        FastBaselineKind::PreGraduation => "PRE_GRADUATION",
        FastBaselineKind::GraduationFlow => "GRADUATION_FLOW",
        FastBaselineKind::WalletCohort => "WALLET_COHORT",
        FastBaselineKind::LongerRunner => "LONGER_RUNNER",
    }
}

fn parse_kind(value: &str) -> Result<FastBaselineKind, FastDeterministicLifecycleWireError> {
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
) -> Result<(), FastDeterministicLifecycleWireError> {
    let upper_ok = if upper_open { value < 1.0 } else { value <= 1.0 };
    if !value.is_finite() || value <= 0.0 || !upper_ok {
        return invalid(&format!("{name} is outside its permitted interval"));
    }
    Ok(())
}

fn require_non_empty(
    name: &str,
    value: &str,
) -> Result<(), FastDeterministicLifecycleWireError> {
    if value.trim().is_empty() {
        return invalid(&format!("{name} must be non-empty"));
    }
    Ok(())
}

fn validate_sha256(
    name: &str,
    value: &str,
) -> Result<(), FastDeterministicLifecycleWireError> {
    if value.len() != 64
        || value != value.to_ascii_lowercase()
        || value.bytes().any(|byte| !matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    {
        return invalid(&format!("{name} must be lowercase SHA-256 hex"));
    }
    Ok(())
}

fn nearly_equal(left: f64, right: f64) -> bool {
    const REL_TOL: f64 = 1e-12;
    const ABS_TOL: f64 = 1e-12;
    (left - right).abs() <= ABS_TOL.max(REL_TOL * left.abs().max(right.abs()))
}

fn invalid<T>(message: &str) -> Result<T, FastDeterministicLifecycleWireError> {
    Err(FastDeterministicLifecycleWireError::Invalid(message.to_owned()))
}
