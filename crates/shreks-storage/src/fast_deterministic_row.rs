use std::{error::Error, fmt};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use shreks_core::{
    ExecutionCostModel, ExecutionLegCostInput, ExecutionTradeInput, FastBaselineKind,
    FastMarketKey, FastMarketSnapshot, GraduationBoostContext, GraduationFlowExecutionInput,
    ImpulseScalpExecutionInput, LongerRunnerContinuationEvidence, LongerRunnerProtectiveState,
    MicroPullbackExecutionInput, PreGraduationExecutionInput, WalletCohortEvidence,
    WalletCohortPositionInput, WalletCohortSideSummary,
};

use crate::{
    decode_fast_training_feature_record_json, evaluate_fast_deterministic_lifecycle_batch,
    fast_deterministic_lifecycle_to_wire, hydrate_fast_baseline_snapshot,
    materialize_fast_deterministic_candidate_manifest, FastBaselineCampaignInput,
    FastDeterministicCandidateManifestError, FastDeterministicCandidateManifestWire,
    FastDeterministicEntryPolicy, FastDeterministicLifecycleError,
    FastDeterministicLifecyclePolicyWire, FastDeterministicLifecyclePostureInput,
    FastDeterministicLifecycleRequest, FastDeterministicLifecycleDecisionWire,
    FastDeterministicManagerPolicy, FastDeterministicLifecycleWireError,
    FastTrainingLifecycleEvent, FastTrainingReserveContext, FastTrainingWindowSummary,
    StorageError,
};
use crate::{
    fast_baseline_hydration::{
        hydrate_lifecycle_event, hydrate_reserve_context, hydrate_window,
    },
    training_features::parse_training_venue,
};

pub const FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_NAME: &str =
    "shreks.fast_deterministic_row_request";
pub const FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_VERSION: u16 = 1;
pub const FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_NAME: &str =
    "shreks.fast_deterministic_row_result";
pub const FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicRowRequestWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub manifest: FastDeterministicCandidateManifestWire,
    pub record: Value,
    pub posture: FastDeterministicRowPostureWire,
    pub evidence: FastDeterministicRowEvidenceWire,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind")]
pub enum FastDeterministicRowPostureWire {
    #[serde(rename = "FLAT")]
    Flat,
    #[serde(rename = "OPEN")]
    Open {
        current_exposure_fraction: f64,
        opened_at_unix_ms: i64,
    },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind")]
pub enum FastDeterministicRowEvidenceWire {
    #[serde(rename = "IMPULSE_SCALP")]
    ImpulseScalp {
        execution: Option<FastEntryExecutionWire>,
    },
    #[serde(rename = "MICRO_PULLBACK")]
    MicroPullback {
        execution: Option<FastEntryExecutionWire>,
    },
    #[serde(rename = "PRE_GRADUATION")]
    PreGraduation {
        execution: Option<FastEntryExecutionWire>,
    },
    #[serde(rename = "GRADUATION_FLOW")]
    GraduationFlow {
        pre_snapshot: FastMarketSnapshotWire,
        boost_context: Option<bool>,
        execution: Option<FastEntryExecutionWire>,
    },
    #[serde(rename = "WALLET_COHORT")]
    WalletCohort {
        evidence: Option<FastWalletCohortEvidenceWire>,
    },
    #[serde(rename = "LONGER_RUNNER")]
    LongerRunner {
        protective: FastLongerRunnerProtectiveWire,
        continuation: Option<FastLongerRunnerContinuationWire>,
    },
}

impl FastDeterministicRowEvidenceWire {
    pub const fn baseline_kind(&self) -> FastBaselineKind {
        match self {
            Self::ImpulseScalp { .. } => FastBaselineKind::ImpulseScalp,
            Self::MicroPullback { .. } => FastBaselineKind::MicroPullback,
            Self::PreGraduation { .. } => FastBaselineKind::PreGraduation,
            Self::GraduationFlow { .. } => FastBaselineKind::GraduationFlow,
            Self::WalletCohort { .. } => FastBaselineKind::WalletCohort,
            Self::LongerRunner { .. } => FastBaselineKind::LongerRunner,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastExecutionLegCostWire {
    pub effective_fee_bps: u32,
    pub expected_impact_bps: u32,
    pub expected_slippage_bps: u32,
    pub expected_latency_bps: u32,
    pub network_fee_quote: f64,
    pub priority_fee_quote: f64,
    pub expected_failure_cost_quote: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastExecutionCostModelWire {
    pub version: u16,
    pub entry: FastExecutionLegCostWire,
    pub exit: FastExecutionLegCostWire,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastExecutionTradeWire {
    pub base_quantity: f64,
    pub executable_entry_price_quote: f64,
    pub forecast_exit_price_quote: f64,
    pub exit_capacity_base: f64,
    pub required_edge_bps: u32,
    pub risk_margin_bps: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastEntryExecutionWire {
    pub cost_model: FastExecutionCostModelWire,
    pub trade: FastExecutionTradeWire,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastMarketSnapshotWire {
    pub mint: String,
    pub quote_mint: String,
    pub venue: String,
    pub as_of_unix_ms: i64,
    pub last_sequence: Option<u64>,
    pub last_price_quote: Option<f64>,
    pub last_reserve_context: Option<FastTrainingReserveContext>,
    pub last_lifecycle_event: Option<FastTrainingLifecycleEvent>,
    pub windows: Vec<FastTrainingWindowSummary>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastWalletCohortSideSummaryWire {
    pub strong_wallet_count: u64,
    pub confidence_weighted_strong_count: f64,
    pub independently_strong_wallet_count: Option<u64>,
    pub all_pairs_independent_under_evidence: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastWalletCohortEvidenceWire {
    pub version: u16,
    pub wallet_feature_policy_version: String,
    pub profile_policy_version: Option<String>,
    pub relationship_policy_version: String,
    pub support: FastWalletCohortSideSummaryWire,
    pub exits: FastWalletCohortSideSummaryWire,
    pub support_hold_horizon_wallet_weight: f64,
    pub confidence_weighted_support_median_hold_ms: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastLongerRunnerProtectiveWire {
    pub hard_stop_triggered: bool,
    pub risk_limit_exit_required: bool,
    pub liquidity_exit_required: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastLongerRunnerContinuationWire {
    pub version: u16,
    pub forecast_source_version: String,
    pub forecast_horizon_ms: u64,
    pub base_quantity: f64,
    pub current_executable_exit_price_quote: f64,
    pub expected_future_exit_price_quote: f64,
    pub downside_exit_price_quote: f64,
    pub current_exit_capacity_base: f64,
    pub expected_future_exit_capacity_base: f64,
    pub expected_holding_cost_quote: f64,
    pub current_exit_costs: FastExecutionLegCostWire,
    pub future_exit_costs: FastExecutionLegCostWire,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicRowResultWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub candidate_version: String,
    pub candidate_fingerprint_sha256: String,
    pub lifecycle_policy: FastDeterministicLifecyclePolicyWire,
    pub decision: FastDeterministicLifecycleDecisionWire,
    pub result_fingerprint_sha256: String,
}

#[derive(Debug)]
pub enum FastDeterministicRowError {
    Json(String),
    Invalid(String),
    Candidate(FastDeterministicCandidateManifestError),
    Storage(StorageError),
    Lifecycle(FastDeterministicLifecycleError),
    LifecycleWire(FastDeterministicLifecycleWireError),
    FingerprintMismatch,
}

impl fmt::Display for FastDeterministicRowError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(message) => write!(formatter, "deterministic row JSON error: {message}"),
            Self::Invalid(message) => write!(formatter, "invalid deterministic row request: {message}"),
            Self::Candidate(error) => write!(formatter, "deterministic row candidate error: {error}"),
            Self::Storage(error) => write!(formatter, "deterministic row storage evidence error: {error}"),
            Self::Lifecycle(error) => write!(formatter, "deterministic row lifecycle evaluation failed: {error}"),
            Self::LifecycleWire(error) => write!(formatter, "deterministic row lifecycle wire failed: {error}"),
            Self::FingerprintMismatch => formatter.write_str("deterministic row result fingerprint mismatch"),
        }
    }
}

impl Error for FastDeterministicRowError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Candidate(error) => Some(error),
            Self::Storage(error) => Some(error),
            Self::Lifecycle(error) => Some(error),
            Self::LifecycleWire(error) => Some(error),
            _ => None,
        }
    }
}

impl From<FastDeterministicCandidateManifestError> for FastDeterministicRowError {
    fn from(value: FastDeterministicCandidateManifestError) -> Self {
        Self::Candidate(value)
    }
}

impl From<StorageError> for FastDeterministicRowError {
    fn from(value: StorageError) -> Self {
        Self::Storage(value)
    }
}

impl From<FastDeterministicLifecycleError> for FastDeterministicRowError {
    fn from(value: FastDeterministicLifecycleError) -> Self {
        Self::Lifecycle(value)
    }
}

impl From<FastDeterministicLifecycleWireError> for FastDeterministicRowError {
    fn from(value: FastDeterministicLifecycleWireError) -> Self {
        Self::LifecycleWire(value)
    }
}

pub fn decode_fast_deterministic_row_request_json(
    input: &str,
) -> Result<FastDeterministicRowRequestWire, FastDeterministicRowError> {
    if input.is_empty() {
        return invalid("JSON payload must be non-empty");
    }
    let request: FastDeterministicRowRequestWire = serde_json::from_str(input)
        .map_err(|error| FastDeterministicRowError::Json(error.to_string()))?;
    if request.schema_name != FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_NAME {
        return invalid("schema_name is incompatible");
    }
    if request.schema_version != FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_VERSION {
        return invalid("schema_version is incompatible");
    }
    Ok(request)
}

pub fn evaluate_fast_deterministic_row_request(
    request: &FastDeterministicRowRequestWire,
) -> Result<FastDeterministicRowResultWire, FastDeterministicRowError> {
    if request.schema_name != FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_NAME
        || request.schema_version != FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_VERSION
    {
        return invalid("request schema is incompatible");
    }

    let candidate = materialize_fast_deterministic_candidate_manifest(&request.manifest)?;
    let record_json = serde_json::to_string(&request.record)
        .map_err(|error| FastDeterministicRowError::Json(error.to_string()))?;
    let record = decode_fast_training_feature_record_json(&record_json)?;
    let hydration = hydrate_fast_baseline_snapshot(&record)?;
    let expected_kind = match request.posture {
        FastDeterministicRowPostureWire::Flat => candidate.lifecycle_policy.entry_baseline_kind,
        FastDeterministicRowPostureWire::Open { .. } => {
            candidate.lifecycle_policy.manager_baseline_kind
        }
    };
    if request.evidence.baseline_kind() != expected_kind {
        return invalid("evidence baseline kind does not match manifest-selected posture component");
    }

    let batch = match (&request.posture, &request.evidence) {
        (
            FastDeterministicRowPostureWire::Flat,
            FastDeterministicRowEvidenceWire::ImpulseScalp { execution },
        ) => {
            let FastDeterministicEntryPolicy::ImpulseScalp(policy) = &candidate.entry_policy else {
                return invalid("manifest entry policy is not Impulse Scalp");
            };
            let execution = execution
                .as_ref()
                .map(|value| build_impulse_execution(value, &hydration.snapshot))
                .transpose()?;
            evaluate_fast_deterministic_lifecycle_batch(
                &candidate.lifecycle_policy,
                &[FastDeterministicLifecycleRequest {
                    record: &record,
                    posture: FastDeterministicLifecyclePostureInput::Flat {
                        input: FastBaselineCampaignInput::ImpulseScalp {
                            execution: execution.as_ref(),
                            policy,
                        },
                    },
                }],
            )?
        }
        (
            FastDeterministicRowPostureWire::Flat,
            FastDeterministicRowEvidenceWire::MicroPullback { execution },
        ) => {
            let FastDeterministicEntryPolicy::MicroPullback(policy) = &candidate.entry_policy else {
                return invalid("manifest entry policy is not Micro Pullback");
            };
            let execution = execution
                .as_ref()
                .map(|value| build_micro_execution(value, &hydration.snapshot))
                .transpose()?;
            evaluate_fast_deterministic_lifecycle_batch(
                &candidate.lifecycle_policy,
                &[FastDeterministicLifecycleRequest {
                    record: &record,
                    posture: FastDeterministicLifecyclePostureInput::Flat {
                        input: FastBaselineCampaignInput::MicroPullback {
                            execution: execution.as_ref(),
                            policy,
                        },
                    },
                }],
            )?
        }
        (
            FastDeterministicRowPostureWire::Flat,
            FastDeterministicRowEvidenceWire::PreGraduation { execution },
        ) => {
            let FastDeterministicEntryPolicy::PreGraduation(policy) = &candidate.entry_policy else {
                return invalid("manifest entry policy is not Pre-Graduation");
            };
            let execution = execution
                .as_ref()
                .map(|value| build_pre_execution(value, &hydration.snapshot))
                .transpose()?;
            evaluate_fast_deterministic_lifecycle_batch(
                &candidate.lifecycle_policy,
                &[FastDeterministicLifecycleRequest {
                    record: &record,
                    posture: FastDeterministicLifecyclePostureInput::Flat {
                        input: FastBaselineCampaignInput::PreGraduation {
                            execution: execution.as_ref(),
                            policy,
                        },
                    },
                }],
            )?
        }
        (
            FastDeterministicRowPostureWire::Flat,
            FastDeterministicRowEvidenceWire::GraduationFlow {
                pre_snapshot,
                boost_context,
                execution,
            },
        ) => {
            let FastDeterministicEntryPolicy::GraduationFlow(policy) = &candidate.entry_policy else {
                return invalid("manifest entry policy is not Graduation Flow");
            };
            let pre_snapshot = build_snapshot(pre_snapshot)?;
            let boost_context = boost_context.map(|can_boost| GraduationBoostContext {
                market: hydration.snapshot.market.clone(),
                as_of_unix_ms: hydration.snapshot.as_of_unix_ms,
                can_boost,
            });
            let execution = execution
                .as_ref()
                .map(|value| build_graduation_execution(value, &hydration.snapshot))
                .transpose()?;
            evaluate_fast_deterministic_lifecycle_batch(
                &candidate.lifecycle_policy,
                &[FastDeterministicLifecycleRequest {
                    record: &record,
                    posture: FastDeterministicLifecyclePostureInput::Flat {
                        input: FastBaselineCampaignInput::GraduationFlow {
                            pre_snapshot: &pre_snapshot,
                            boost_context: boost_context.as_ref(),
                            execution: execution.as_ref(),
                            policy,
                        },
                    },
                }],
            )?
        }
        (
            FastDeterministicRowPostureWire::Open {
                current_exposure_fraction,
                opened_at_unix_ms,
            },
            FastDeterministicRowEvidenceWire::WalletCohort { evidence },
        ) => {
            validate_open_posture(
                *current_exposure_fraction,
                *opened_at_unix_ms,
                record.decision_observed_at_unix_ms,
            )?;
            let FastDeterministicManagerPolicy::WalletCohort(policy) = &candidate.manager_policy else {
                return invalid("manifest manager policy is not Wallet Cohort");
            };
            let evidence = evidence
                .as_ref()
                .map(|value| build_wallet_evidence(value, &hydration.snapshot));
            let position = WalletCohortPositionInput {
                market: hydration.snapshot.market.clone(),
                as_of_unix_ms: hydration.snapshot.as_of_unix_ms,
                opened_at_unix_ms: *opened_at_unix_ms,
            };
            evaluate_fast_deterministic_lifecycle_batch(
                &candidate.lifecycle_policy,
                &[FastDeterministicLifecycleRequest {
                    record: &record,
                    posture: FastDeterministicLifecyclePostureInput::Open {
                        current_exposure_fraction: *current_exposure_fraction,
                        input: FastBaselineCampaignInput::WalletCohort {
                            evidence: evidence.as_ref(),
                            position: &position,
                            policy,
                        },
                    },
                }],
            )?
        }
        (
            FastDeterministicRowPostureWire::Open {
                current_exposure_fraction,
                opened_at_unix_ms,
            },
            FastDeterministicRowEvidenceWire::LongerRunner {
                protective,
                continuation,
            },
        ) => {
            validate_open_posture(
                *current_exposure_fraction,
                *opened_at_unix_ms,
                record.decision_observed_at_unix_ms,
            )?;
            let FastDeterministicManagerPolicy::LongerRunner(policy) = &candidate.manager_policy else {
                return invalid("manifest manager policy is not Longer Runner");
            };
            let protective = LongerRunnerProtectiveState {
                market: hydration.snapshot.market.clone(),
                as_of_unix_ms: hydration.snapshot.as_of_unix_ms,
                hard_stop_triggered: protective.hard_stop_triggered,
                risk_limit_exit_required: protective.risk_limit_exit_required,
                liquidity_exit_required: protective.liquidity_exit_required,
            };
            let continuation = continuation
                .as_ref()
                .map(|value| build_longer_continuation(value, &hydration.snapshot));
            evaluate_fast_deterministic_lifecycle_batch(
                &candidate.lifecycle_policy,
                &[FastDeterministicLifecycleRequest {
                    record: &record,
                    posture: FastDeterministicLifecyclePostureInput::Open {
                        current_exposure_fraction: *current_exposure_fraction,
                        input: FastBaselineCampaignInput::LongerRunner {
                            protective: &protective,
                            continuation: continuation.as_ref(),
                            policy,
                        },
                    },
                }],
            )?
        }
        _ => return invalid("evidence variant is incompatible with supplied posture"),
    };

    let wire = fast_deterministic_lifecycle_to_wire(&batch)?;
    if wire.decisions.len() != 1 {
        return invalid("one-row lifecycle evaluation did not return exactly one decision");
    }
    let mut result = FastDeterministicRowResultWire {
        schema_name: FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_NAME.to_owned(),
        schema_version: FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_VERSION,
        candidate_version: request.manifest.candidate_version.clone(),
        candidate_fingerprint_sha256: request.manifest.candidate_fingerprint_sha256.clone(),
        lifecycle_policy: wire.policy,
        decision: wire.decisions[0].clone(),
        result_fingerprint_sha256: "0".repeat(64),
    };
    result.result_fingerprint_sha256 = result_fingerprint_sha256(&result)?;
    Ok(result)
}

pub fn encode_fast_deterministic_row_result_json(
    result: &FastDeterministicRowResultWire,
) -> Result<String, FastDeterministicRowError> {
    validate_result(result)?;
    let expected = result_fingerprint_sha256(result)?;
    if result.result_fingerprint_sha256 != expected {
        return Err(FastDeterministicRowError::FingerprintMismatch);
    }
    serde_json::to_string(result)
        .map_err(|error| FastDeterministicRowError::Json(error.to_string()))
}

fn build_impulse_execution(
    value: &FastEntryExecutionWire,
    snapshot: &FastMarketSnapshot,
) -> Result<ImpulseScalpExecutionInput, FastDeterministicRowError> {
    Ok(ImpulseScalpExecutionInput {
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        cost_model: build_cost_model(&value.cost_model),
        trade: build_trade(&value.trade),
    })
}

fn build_micro_execution(
    value: &FastEntryExecutionWire,
    snapshot: &FastMarketSnapshot,
) -> Result<MicroPullbackExecutionInput, FastDeterministicRowError> {
    Ok(MicroPullbackExecutionInput {
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        cost_model: build_cost_model(&value.cost_model),
        trade: build_trade(&value.trade),
    })
}

fn build_pre_execution(
    value: &FastEntryExecutionWire,
    snapshot: &FastMarketSnapshot,
) -> Result<PreGraduationExecutionInput, FastDeterministicRowError> {
    Ok(PreGraduationExecutionInput {
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        cost_model: build_cost_model(&value.cost_model),
        trade: build_trade(&value.trade),
    })
}

fn build_graduation_execution(
    value: &FastEntryExecutionWire,
    snapshot: &FastMarketSnapshot,
) -> Result<GraduationFlowExecutionInput, FastDeterministicRowError> {
    Ok(GraduationFlowExecutionInput {
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        cost_model: build_cost_model(&value.cost_model),
        trade: build_trade(&value.trade),
    })
}

fn build_cost_model(value: &FastExecutionCostModelWire) -> ExecutionCostModel {
    ExecutionCostModel {
        version: value.version,
        entry: build_leg(&value.entry),
        exit: build_leg(&value.exit),
    }
}

fn build_leg(value: &FastExecutionLegCostWire) -> ExecutionLegCostInput {
    ExecutionLegCostInput {
        effective_fee_bps: value.effective_fee_bps,
        expected_impact_bps: value.expected_impact_bps,
        expected_slippage_bps: value.expected_slippage_bps,
        expected_latency_bps: value.expected_latency_bps,
        network_fee_quote: value.network_fee_quote,
        priority_fee_quote: value.priority_fee_quote,
        expected_failure_cost_quote: value.expected_failure_cost_quote,
    }
}

fn build_trade(value: &FastExecutionTradeWire) -> ExecutionTradeInput {
    ExecutionTradeInput {
        base_quantity: value.base_quantity,
        executable_entry_price_quote: value.executable_entry_price_quote,
        forecast_exit_price_quote: value.forecast_exit_price_quote,
        exit_capacity_base: value.exit_capacity_base,
        required_edge_bps: value.required_edge_bps,
        risk_margin_bps: value.risk_margin_bps,
    }
}

fn build_wallet_evidence(
    value: &FastWalletCohortEvidenceWire,
    snapshot: &FastMarketSnapshot,
) -> WalletCohortEvidence {
    WalletCohortEvidence {
        version: value.version,
        as_of_unix_ms: snapshot.as_of_unix_ms,
        candidate_mint: snapshot.market.mint.clone(),
        wallet_feature_policy_version: value.wallet_feature_policy_version.clone(),
        profile_policy_version: value.profile_policy_version.clone(),
        relationship_policy_version: value.relationship_policy_version.clone(),
        support: build_wallet_side(&value.support),
        exits: build_wallet_side(&value.exits),
        support_hold_horizon_wallet_weight: value.support_hold_horizon_wallet_weight,
        confidence_weighted_support_median_hold_ms: value
            .confidence_weighted_support_median_hold_ms,
    }
}

fn build_wallet_side(value: &FastWalletCohortSideSummaryWire) -> WalletCohortSideSummary {
    WalletCohortSideSummary {
        strong_wallet_count: value.strong_wallet_count,
        confidence_weighted_strong_count: value.confidence_weighted_strong_count,
        independently_strong_wallet_count: value.independently_strong_wallet_count,
        all_pairs_independent_under_evidence: value.all_pairs_independent_under_evidence,
    }
}

fn build_longer_continuation(
    value: &FastLongerRunnerContinuationWire,
    snapshot: &FastMarketSnapshot,
) -> LongerRunnerContinuationEvidence {
    LongerRunnerContinuationEvidence {
        version: value.version,
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        forecast_source_version: value.forecast_source_version.clone(),
        forecast_horizon_ms: value.forecast_horizon_ms,
        base_quantity: value.base_quantity,
        current_executable_exit_price_quote: value.current_executable_exit_price_quote,
        expected_future_exit_price_quote: value.expected_future_exit_price_quote,
        downside_exit_price_quote: value.downside_exit_price_quote,
        current_exit_capacity_base: value.current_exit_capacity_base,
        expected_future_exit_capacity_base: value.expected_future_exit_capacity_base,
        expected_holding_cost_quote: value.expected_holding_cost_quote,
        current_exit_costs: build_leg(&value.current_exit_costs),
        future_exit_costs: build_leg(&value.future_exit_costs),
    }
}

fn build_snapshot(
    value: &FastMarketSnapshotWire,
) -> Result<FastMarketSnapshot, FastDeterministicRowError> {
    let venue = parse_training_venue(&value.venue)?;
    let market = FastMarketKey::new(value.mint.clone(), value.quote_mint.clone(), venue)
        .map_err(|error| FastDeterministicRowError::Invalid(format!(
            "invalid companion snapshot market: {error}"
        )))?;
    if value.as_of_unix_ms < 0 {
        return invalid("companion snapshot as_of_unix_ms must be non-negative");
    }
    let last_reserve_context = value
        .last_reserve_context
        .as_ref()
        .map(|item| hydrate_reserve_context(item, venue))
        .transpose()?;
    let last_lifecycle_event = value
        .last_lifecycle_event
        .as_ref()
        .map(|item| hydrate_lifecycle_event(item, &market, value.as_of_unix_ms))
        .transpose()?;
    let windows = value.windows.iter().map(hydrate_window).collect();
    Ok(FastMarketSnapshot {
        market,
        as_of_unix_ms: value.as_of_unix_ms,
        last_sequence: value.last_sequence,
        last_price_quote: value.last_price_quote,
        last_reserve_context,
        last_lifecycle_event,
        windows,
    })
}

fn validate_open_posture(
    current_exposure_fraction: f64,
    opened_at_unix_ms: i64,
    decision_at_unix_ms: i64,
) -> Result<(), FastDeterministicRowError> {
    if !current_exposure_fraction.is_finite()
        || current_exposure_fraction <= 0.0
        || current_exposure_fraction > 1.0
    {
        return invalid("OPEN current exposure must be finite and within (0, 1]");
    }
    if opened_at_unix_ms < 0 || opened_at_unix_ms > decision_at_unix_ms {
        return invalid("OPEN position opening time is outside decision-safe history");
    }
    Ok(())
}

fn validate_result(
    result: &FastDeterministicRowResultWire,
) -> Result<(), FastDeterministicRowError> {
    if result.schema_name != FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_NAME {
        return invalid("result schema_name is incompatible");
    }
    if result.schema_version != FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_VERSION {
        return invalid("result schema_version is incompatible");
    }
    if result.candidate_version.trim().is_empty() {
        return invalid("result candidate_version must be non-empty");
    }
    validate_sha256(
        "candidate_fingerprint_sha256",
        &result.candidate_fingerprint_sha256,
    )?;
    validate_sha256("result_fingerprint_sha256", &result.result_fingerprint_sha256)?;
    Ok(())
}

fn result_fingerprint_sha256(
    result: &FastDeterministicRowResultWire,
) -> Result<String, FastDeterministicRowError> {
    let mut value = serde_json::to_value(result)
        .map_err(|error| FastDeterministicRowError::Json(error.to_string()))?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| FastDeterministicRowError::Invalid(
            "result serialization must be an object".to_owned(),
        ))?;
    object.remove("result_fingerprint_sha256");
    let payload = serde_json::to_vec(&value)
        .map_err(|error| FastDeterministicRowError::Json(error.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(payload)))
}

fn validate_sha256(name: &str, value: &str) -> Result<(), FastDeterministicRowError> {
    if value.len() != 64
        || value != value.to_ascii_lowercase()
        || value
            .bytes()
            .any(|byte| !matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    {
        return invalid(&format!("{name} must be lowercase SHA-256 hex"));
    }
    Ok(())
}

fn invalid<T>(message: &str) -> Result<T, FastDeterministicRowError> {
    Err(FastDeterministicRowError::Invalid(message.to_owned()))
}
